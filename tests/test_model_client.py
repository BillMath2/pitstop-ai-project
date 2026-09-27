"""Configuration and real SDK serialization with an offline HTTP transport."""

import json
import time

import httpx
import pytest
from openai import OpenAI

from dealer_evidence_agent.answers import AgentError
from dealer_evidence_agent.model_client import DEFAULT_MODEL, ModelClient, configuration, digest
from dealer_evidence_agent.tracing import RecordingTrace


@pytest.fixture(autouse=True)
def clear_configuration(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)


def test_configuration_requires_key_and_never_loads_dotenv_implicitly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=not-a-real-key\n")
    with pytest.raises(AgentError, match="missing_api_key"):
        configuration()
    assert configuration(tmp_path / ".env") == ("not-a-real-key", DEFAULT_MODEL)


def test_configuration_precedence_and_literal_parsing(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("# Example\nOPENAI_API_KEY='literal-${UNEXPANDED}'\nIGNORED=secret\n")
    assert configuration(path)[0] == "literal-${UNEXPANDED}"
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    assert configuration(path)[0] == "environment-key"
    monkeypatch.setenv("OPENAI_MODEL", "unrequested-model")
    with pytest.raises(AgentError, match="unsupported_model_configuration"):
        configuration(path)


def test_config_errors_never_echo_secrets(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=secret\nOPENAI_API_KEY=other-secret\n")
    with pytest.raises(AgentError, match="^invalid_configuration$"):
        configuration(path)


def test_real_sdk_request_body_matches_trace_and_secret_is_not_logged():
    bodies = []

    def respond(request):
        bodies.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer sentinel-test-secret"
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "object": "chat.completion",
                "created": 0,
                "model": DEFAULT_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"status":"unsupported","reason":"out_of_scope"}',
                        },
                    }
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9},
            },
        )

    trace = RecordingTrace()
    with OpenAI(
        api_key="sentinel-test-secret",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as sdk:
        model = ModelClient(sdk.chat.completions.create, provider="openai_test_transport")
        model.complete(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps({"question": "synthetic question", "evidence": []}),
                    }
                ]
            },
            stage="route",
            deadline=time.monotonic() + 10,
            trace=trace,
        )
    assert trace.events[0]["request_sha256"] == digest(bodies[0])
    assert trace.events[1]["usage"]["total_tokens"] == 9
    assert "sentinel-test-secret" not in json.dumps(trace.events)


def test_sdk_retries_disabled_on_server_failure():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"message": "upstream-secret"}})

    trace = RecordingTrace()
    with OpenAI(
        api_key="fake",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as sdk:
        model = ModelClient(sdk.chat.completions.create)
        with pytest.raises(AgentError, match="provider_error"):
            model.complete(
                {"messages": [{"role": "user", "content": '{"question":"test"}'}]},
                stage="route",
                deadline=time.monotonic() + 10,
                trace=trace,
            )
    assert len(calls) == 1
    assert "upstream-secret" not in json.dumps(trace.events)
