"""Actual boundary agreement, lifecycle, filesystem failures, and safe inspection."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI
from test_graph import completion, final, route, run

from dealer_evidence_agent.answers import AgentError
from dealer_evidence_agent.cli import main
from dealer_evidence_agent.corpus import load_corpus
from dealer_evidence_agent.graph import request_metadata, run_agent
from dealer_evidence_agent.model_client import ModelClient, RecordingClient
from dealer_evidence_agent.recall_fixtures import DEFAULT_FIXTURE_MANIFEST, replay_recalls
from dealer_evidence_agent.tracing import (
    JsonlTrace,
    RecordingTrace,
    fingerprint,
    inspect_trace,
)


@pytest.fixture
def documents():
    return load_corpus(Path("data/manifest.json"))


def test_metadata_is_reproducible_and_distinguishes_local_source():
    value = request_metadata()
    assert len(value["code"]["revision"]) == 40
    assert len(value["code"]["source_sha256"]) == 64
    assert value["configuration_sha256"] == fingerprint(value["configuration"])
    assert value["configuration"]["max_retries"] == 0
    assert value["code"]["packages"]["openai"]


def test_sdk_body_evidence_and_trace_match_for_both_calls(documents, tmp_path):
    captured = []
    replies = [route(query="loaner return"), final()]

    def respond(request):
        captured.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer M5-SECRET-KEY"
        reply = replies.pop(0)
        reply.update(id="synthetic", object="chat.completion", created=0, model="test")
        reply["choices"][0]["index"] = 0
        reply["choices"][0]["message"]["role"] = "assistant"
        return httpx.Response(200, json=reply)

    trace = JsonlTrace(tmp_path)
    with OpenAI(
        api_key="M5-SECRET-KEY",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as sdk:
        result = run_agent(
            "M5-PRIVATE-QUESTION loaner return",
            identity="tech_demo",
            documents=documents,
            model=ModelClient(sdk.chat.completions.create, provider="offline_sdk_transport"),
            trace=trace,
        )
    trace.close()
    assert result.answer.status == "answered"
    report = inspect_trace(tmp_path, trace.run_id)
    rows = report["events"]
    requests = [r for r in rows if r["event"] == "model_request"]
    for row, body in zip(requests, captured, strict=True):
        assert row["request_sha256"] == fingerprint(body)
        assert row["schema_sha256"] == fingerprint(body["response_format"])
        assert row["prompt_sha256"] == fingerprint(
            [m for m in body["messages"] if m["role"] == "system"]
        )
        evidence = json.loads(body["messages"][-1]["content"]).get("evidence", [])
        assert row["evidence"] == [
            {
                "kind": e["kind"],
                "id": e["id"],
                "content_sha256": hashlib.sha256(e["content"].encode()).hexdigest(),
            }
            for e in evidence
        ]
    assert requests[0]["evidence"] == []
    assert requests[1]["evidence"]
    serialized = trace.path.read_text()
    for forbidden in ("M5-SECRET-KEY", "M5-PRIVATE-QUESTION", "loaner return", "Authorization"):
        assert forbidden not in serialized
    for doc in documents:
        if doc.visibility == "manager_only":
            assert doc.doc_id not in serialized + json.dumps(captured)
            assert doc.text not in json.dumps(captured)
    assert report["usage"] == {"total_tokens": 200}
    assert report["model_attempts"] == 2 and report["tool_calls"] == 1
    assert rows[-1]["event"] == "request_finished"
    selected = next(r for r in rows if r["event"] == "route_selected")
    assert selected["arguments"] == {"query_redacted": True}
    assert selected["arguments_sha256"] == fingerprint({"query": "loaner return"})


@pytest.mark.parametrize("failure", ["identity", "question", "corpus", "configuration"])
def test_setup_failures_have_start_and_terminal_without_provider(
    failure, tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    argv = [
        "ask",
        "M5-question-secret",
        "--identity",
        "tech_demo",
        "--json",
        "--runs-dir",
        str(tmp_path),
    ]
    if failure == "identity":
        argv[3] = "M5-unknown-identity-secret"
    elif failure == "question":
        argv[1] = " "
    elif failure == "corpus":
        argv += ["--manifest", str(tmp_path / "M5-file-secret")]
    assert main(argv) == 1
    output = json.loads(capsys.readouterr().out)
    report = inspect_trace(tmp_path, output["run_id"])
    assert report["complete"] and report["events"][0]["event"] == "request_started"
    assert report["events"][-1]["event"] == "request_failed"
    assert report["model_attempts"] == report["tool_calls"] == 0
    serialized = json.dumps(report)
    assert all(
        x not in serialized
        for x in (
            "M5-question-secret",
            "M5-unknown-identity-secret",
            "M5-file-secret",
        )
    )


@pytest.mark.parametrize(
    "fixture_id,status",
    [
        ("synthetic-empty", "no_records"),
        ("synthetic-malformed", "error"),
        ("synthetic-timeout", "error"),
        ("toyota-corolla-2020", "answered"),
    ],
)
def test_recall_provenance_errors_and_zero_retries(documents, tmp_path, fixture_id, status):
    def lookup(**args):
        return replay_recalls(DEFAULT_FIXTURE_MANIFEST, fixture_id, identity="tech_demo", **args)

    captured = lookup(make="Toyota", model="Corolla", year=2020)
    replies = [route("lookup_recalls", make="Toyota", model="Corolla", year=2020)]
    if status == "answered":
        replies.append(
            final(
                text="Recorded campaigns.",
                refs=[
                    {
                        "kind": "recall_campaign",
                        "id": captured.records[0].campaign_number,
                    }
                ],
            )
        )
    trace = JsonlTrace(tmp_path)
    result, _, _ = run(
        documents,
        replies,
        question="Recalls for 2020 Toyota Corolla?",
        recall_lookup=lookup,
        trace=trace,
    )
    trace.close()
    assert result.answer.status == status
    report = inspect_trace(tmp_path, trace.run_id)
    tool = next(r for r in report["events"] if r["event"] == "tool_completed")
    assert tool["source"] == captured.source and tool["fixture_id"] == fixture_id
    assert len(tool["fixture_sha256"]) == 64
    assert tool["body_sha256"] == captured.body_sha256
    assert tool["network_attempts"] == tool["retry_count"] == 0
    selected = next(r for r in report["events"] if r["event"] == "route_selected")
    assert selected["arguments"] == {"make": "Toyota", "model": "Corolla", "year": 2020}
    assert report["complete"]


def test_provider_failure_is_an_attempt_not_a_response(documents, tmp_path):
    trace = JsonlTrace(tmp_path)
    result, _, _ = run(documents, [TimeoutError("M5-RAW-UPSTREAM-SECRET")], trace=trace)
    trace.close()
    assert result.error_code == "provider_error"
    report = inspect_trace(tmp_path, trace.run_id)
    assert report["model_attempts"] == 1 and report["usage"] == {}
    assert not any(r["event"] == "model_response" for r in report["events"])
    assert report["unconfirmed_attempts"] == []
    assert "M5-RAW-UPSTREAM-SECRET" not in trace.path.read_text()


class FileFault:
    def __init__(self, file, operation):
        self.file, self.operation, self.event, self.failed = file, operation, None, False

    def __getattr__(self, name):
        return getattr(self.file, name)

    def write(self, data):
        self.event = json.loads(data)["event"]
        if self.event == "model_request" and self.operation == "write" and not self.failed:
            self.failed = True
            self.file.write(data[:30])
            raise OSError("partial disk write")
        return self.file.write(data)

    def flush(self):
        if self.event == "model_request" and self.operation == "flush" and not self.failed:
            self.failed = True
            raise OSError("disk flush failure")
        return self.file.flush()

    def close(self):
        self.file.close()
        if self.operation == "close":
            raise OSError("close failure")


@pytest.mark.parametrize("operation", ["write", "flush", "fsync"])
def test_boundary_disk_failure_stops_call_and_recovers_terminal(
    documents, tmp_path, monkeypatch, operation
):
    import dealer_evidence_agent.tracing as tracing

    trace = JsonlTrace(tmp_path)
    wrapper = FileFault(trace._file, operation)
    trace._file = wrapper
    original = tracing.os.fsync
    if operation == "fsync":

        def fail_once(fd):
            if wrapper.event == "model_request" and not wrapper.failed:
                wrapper.failed = True
                raise OSError("disk sync failure")
            return original(fd)

        monkeypatch.setattr(tracing.os, "fsync", fail_once)
    result, client, _ = run(documents, [], trace=trace)
    trace.close()
    assert result.error_code == "trace_write_failed" and client.bodies == []
    # Logical calls include a preparation attempt; no SDK request was persisted or sent.
    rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert rows[-1]["event"] == "request_failed"
    assert not any(r["event"] == "model_request" for r in rows)
    assert inspect_trace(tmp_path, trace.run_id)["outcome"] == "trace_write_failed"


def test_close_failure_replaces_success_with_failure(tmp_path):
    trace = JsonlTrace(tmp_path)
    trace.emit("request_started", **request_metadata())
    trace.emit("request_finished", status="unsupported", model_calls=0, tool_calls=0)
    trace._file = FileFault(trace._file, "close")
    with pytest.raises(AgentError, match="trace_write_failed"):
        trace.close()
    report = inspect_trace(tmp_path, trace.run_id)
    assert report["outcome"] == "trace_write_failed"
    assert not any(r["event"] == "request_finished" for r in report["events"])


def test_provider_cleanup_precedes_success_event(tmp_path, monkeypatch, capsys):
    client = ModelClient(
        RecordingClient(
            [
                completion(
                    {
                        "content": json.dumps(
                            {
                                "decision": {
                                    "action": "unsupported",
                                    "reason": "out_of_scope",
                                }
                            }
                        )
                    }
                )
            ]
        )
    )

    def broken_close():
        raise OSError("M5-CLEANUP-SECRET")

    monkeypatch.setattr(client, "close", broken_close)
    monkeypatch.setattr(ModelClient, "from_environment", lambda path: client)
    assert (
        main(["ask", "test", "--identity", "tech_demo", "--json", "--runs-dir", str(tmp_path)]) == 1
    )
    output = json.loads(capsys.readouterr().out)
    report = inspect_trace(tmp_path, output["run_id"])
    assert report["outcome"] == "provider_close_failed"
    assert "M5-CLEANUP-SECRET" not in json.dumps(report)
    assert not any(r["event"] == "request_finished" for r in report["events"])


def test_incomplete_trace_and_inspection_cli(tmp_path, capsys):
    trace = JsonlTrace(tmp_path)
    trace.emit("request_started", **request_metadata())
    trace.emit("model_request", stage="route", attempt=1, retry_count=0, evidence=[])
    trace.close()
    report = inspect_trace(tmp_path, trace.run_id)
    assert not report["complete"] and report["unconfirmed_attempts"] == [("route", 1)]
    assert main(["trace", "--run-id", trace.run_id, "--runs-dir", str(tmp_path)]) == 1
    assert "Incomplete trace" in capsys.readouterr().out


@pytest.mark.parametrize("run_id", ["../.env", "A" * 32, "0" * 31, "0" * 33, None])
def test_trace_path_input_is_bounded(tmp_path, run_id):
    with pytest.raises(AgentError, match="invalid_run_id"):
        inspect_trace(tmp_path, run_id)


@pytest.mark.parametrize(
    "change", ["version", "sequence", "run_id", "extra", "duplicate", "partial", "size"]
)
def test_corrupt_traces_are_rejected_before_display(tmp_path, change):
    trace = JsonlTrace(tmp_path)
    trace.emit("request_started", **request_metadata())
    trace.close()
    row = json.loads(trace.path.read_text())
    if change == "version":
        row["trace_version"] = True
    elif change == "sequence":
        row["sequence"] = 4
    elif change == "run_id":
        row["run_id"] = "f" * 32
    elif change == "extra":
        row["raw_question"] = "M5-SECRET"
    text = json.dumps(row) + "\n"
    if change == "duplicate":
        text = text.replace("{", '{"event":"request_started",', 1)
    elif change == "partial":
        text = text[:-2]
    elif change == "size":
        text = "x" * 1_000_001
    trace.path.write_text(text)
    with pytest.raises(AgentError):
        inspect_trace(tmp_path, trace.run_id)


def test_raw_fields_and_reserved_envelope_fields_cannot_be_written(tmp_path):
    trace = JsonlTrace(tmp_path)
    for fields in ({"raw_question": "secret"}, {"sequence": 900}, {"run_id": "secret"}):
        with pytest.raises(AgentError, match="invalid_trace_event"):
            trace.emit("request_started", **fields)
    trace.close()
    assert trace.path.read_text() == ""


def test_missing_usage_is_omitted_not_fabricated(documents):
    reply = completion(
        {
            "content": json.dumps(
                {
                    "decision": {
                        "action": "needs_clarification",
                        "reason": "missing_vehicle",
                    }
                }
            )
        }
    )
    reply.pop("usage")
    result, _, trace = run(documents, [reply], trace=RecordingTrace())
    assert result.answer.status == "needs_clarification"
    response = next(r for r in trace.events if r["event"] == "model_response")
    assert "usage" not in response and response["attempt"] == 1


@pytest.mark.parametrize(
    "action,reason",
    [
        ("needs_clarification", "missing_vehicle"),
        ("needs_clarification", "mixed_request"),
        ("unsupported", "out_of_scope"),
    ],
)
def test_terminal_dispositions_have_complete_zero_tool_traces(documents, tmp_path, action, reason):
    trace = JsonlTrace(tmp_path)
    result, _, _ = run(
        documents,
        [
            completion(
                {
                    "content": json.dumps(
                        {
                            "decision": {
                                "action": action,
                                "reason": reason,
                            }
                        }
                    )
                }
            )
        ],
        trace=trace,
    )
    trace.close()
    report = inspect_trace(tmp_path, trace.run_id)
    assert report["complete"] and report["outcome"] == result.answer.status == action
    assert report["model_attempts"] == 1 and report["tool_calls"] == 0
    assert report["unconfirmed_tools"] == []


def test_cannot_create_trace_stops_before_provider_setup(tmp_path, monkeypatch, capsys):
    path = tmp_path / "not-a-directory"
    path.write_text("occupied")

    def forbidden(path):
        raise AssertionError("Provider setup must not run")

    monkeypatch.setattr(ModelClient, "from_environment", forbidden)
    assert (
        main(["ask", "loaner", "--identity", "tech_demo", "--json", "--runs-dir", str(path)]) == 1
    )
    output = json.loads(capsys.readouterr().out)
    assert "trace_write_failed" in output["text"] and output["run_id"] is None


def test_invalid_citation_is_not_echoed_to_disk(documents, tmp_path):
    trace = JsonlTrace(tmp_path)
    result, _, _ = run(
        documents,
        [
            route(query="loaner return"),
            final(
                refs=[
                    {
                        "kind": "policy",
                        "id": "manager_goodwill_review",
                    }
                ]
            ),
        ],
        trace=trace,
    )
    trace.close()
    report = inspect_trace(tmp_path, trace.run_id)
    assert report["outcome"] == result.error_code == "invalid_citation"
    assert "manager_goodwill_review" not in trace.path.read_text()


def test_no_match_trace_skips_answer_request(documents, tmp_path):
    trace = JsonlTrace(tmp_path)
    result, _, _ = run(documents, [route(query="zzzxxyynotapolicy")], trace=trace)
    trace.close()
    report = inspect_trace(tmp_path, trace.run_id)
    assert report["complete"] and result.answer.status == "insufficient_evidence"
    assert report["model_attempts"] == 1 and report["tool_calls"] == 1


def test_duplicate_model_attempt_rejected_by_inspector(tmp_path):
    trace = JsonlTrace(tmp_path)
    trace.emit("request_started", **request_metadata())
    trace.emit("model_request", stage="route", attempt=1, evidence=[])
    trace.emit("model_response", stage="route", attempt=1)
    trace.emit("model_request", stage="route", attempt=1, evidence=[])
    trace.close()
    with pytest.raises(AgentError, match="invalid_trace_attempt"):
        inspect_trace(tmp_path, trace.run_id)
