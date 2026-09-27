"""One provider, zero retries, and evidence derived at the final SDK boundary."""

import copy
import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from openai import APIError, OpenAI

from dealer_evidence_agent.answers import AgentError, parse_json
from dealer_evidence_agent.prompts import PROMPT_VERSION
from dealer_evidence_agent.tracing import Trace, fingerprint

DEFAULT_MODEL = "gpt-4.1-mini-2025-04-14"


def digest(value: object) -> str:
    return fingerprint(value)


def configuration(env_file: Path | None = None) -> tuple[str, str]:
    """Explicit optional dotenv subset: two literal values, no expansion or shell code."""
    values = {}
    if env_file is not None:
        try:
            for line in env_file.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, separator, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key not in {"OPENAI_API_KEY", "OPENAI_MODEL"}:
                    continue
                if not separator or key in values:
                    raise AgentError("invalid_configuration")
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[key] = value
        except (OSError, UnicodeError) as exc:
            raise AgentError("invalid_configuration") from exc
    key = os.environ.get("OPENAI_API_KEY", values.get("OPENAI_API_KEY", ""))
    model = os.environ.get("OPENAI_MODEL", values.get("OPENAI_MODEL", DEFAULT_MODEL))
    if not key.strip() or key == "replace-with-your-personal-api-key":
        raise AgentError("missing_api_key")
    if model != DEFAULT_MODEL:
        raise AgentError("unsupported_model_configuration")
    return key, model


class RecordingClient:
    """Fake SDK create callable; scripted replies are not model quality evidence."""

    def __init__(self, replies: list[dict | Exception]):
        self.replies = list(replies)
        self.bodies: list[dict] = []
        self.timeouts: list[float] = []

    def __call__(self, *, timeout: float, **body) -> dict:
        self.bodies.append(copy.deepcopy(body))
        self.timeouts.append(timeout)
        if not self.replies:
            raise AssertionError("Unexpected model call")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return copy.deepcopy(reply)


class ModelClient:
    def __init__(
        self, create: Callable, *, model: str = DEFAULT_MODEL, provider: str = "recording_fake"
    ):
        self._create = create
        self.model = model
        self.provider = provider
        self._sdk: OpenAI | None = None

    @classmethod
    def from_environment(cls, env_file: Path | None = None) -> "ModelClient":
        key, model = configuration(env_file)
        sdk = OpenAI(
            api_key=key,
            base_url="https://api.openai.com/v1",
            max_retries=0,
            http_client=httpx.Client(trust_env=False, follow_redirects=False),
        )
        client = cls(sdk.chat.completions.create, model=model, provider="openai")
        client._sdk = sdk
        return client

    def close(self) -> None:
        if self._sdk is not None:
            self._sdk.close()

    def complete(self, body: dict, *, stage: str, deadline: float, trace: Trace) -> dict:
        outgoing = copy.deepcopy(
            {
                **body,
                "model": self.model,
                "temperature": 0,
                "max_completion_tokens": 1800,
            }
        )
        payload = parse_json(outgoing["messages"][-1]["content"], max_chars=300_000)
        evidence = [
            {
                "kind": item["kind"],
                "id": item["id"],
                "content_sha256": hashlib.sha256(item["content"].encode()).hexdigest(),
            }
            for item in payload.get("evidence", [])
        ]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentError("request_deadline_exceeded")
        trace.emit(
            "model_request",
            stage=stage,
            provider=self.provider,
            model=self.model,
            prompt_version=PROMPT_VERSION,
            request_sha256=digest(outgoing),
            prompt_sha256=digest([m for m in outgoing["messages"] if m["role"] == "system"]),
            schema_sha256=digest(outgoing.get("response_format")),
            settings={
                "temperature": outgoing["temperature"],
                "max_completion_tokens": outgoing["max_completion_tokens"],
            },
            timeout_seconds=min(25.0, remaining),
            evidence=evidence,
            attempt=1,
            retry_count=0,
        )
        started = time.monotonic()
        try:
            response = self._create(**outgoing, timeout=min(25.0, remaining))
        except (APIError, httpx.HTTPError, TimeoutError, ConnectionError) as exc:
            trace.emit(
                "model_failed",
                stage=stage,
                error="provider_error",
                retry_count=0,
                error_type=type(exc).__name__,
                http_status=getattr(exc, "status_code", None),
                attempt=1,
                elapsed_seconds=time.monotonic() - started,
            )
            raise AgentError("provider_error") from exc
        if not isinstance(response, dict) and callable(getattr(response, "model_dump", None)):
            response = response.model_dump()
        usage = response.get("usage") if isinstance(response, dict) else None
        safe_usage = {
            key: usage[key]
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance(usage, dict) and type(usage.get(key)) is int and usage[key] >= 0
        }
        trace.emit(
            "model_response",
            stage=stage,
            attempt=1,
            elapsed_seconds=time.monotonic() - started,
            **({"usage": safe_usage} if safe_usage else {}),
            retry_count=0,
        )
        if time.monotonic() >= deadline:
            raise AgentError("request_deadline_exceeded")
        if not isinstance(response, dict):
            raise AgentError("invalid_model_output")
        choices = response.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise AgentError("invalid_model_output")
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("finish_reason") not in (
            "stop",
            "tool_calls",
        ):
            raise AgentError("invalid_model_output")
        message = choice.get("message")
        if not isinstance(message, dict) or message.get("refusal"):
            raise AgentError("invalid_model_output")
        if (choice["finish_reason"] == "tool_calls") != bool(message.get("tool_calls")):
            raise AgentError("invalid_model_output")
        return message
