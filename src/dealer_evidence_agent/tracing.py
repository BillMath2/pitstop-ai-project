"""Versioned request traces, safe metadata, and bounded operator inspection."""

import hashlib
import json
import os
import platform
import re
import subprocess
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from dealer_evidence_agent.answers import AgentError, parse_json

TRACE_VERSION = 1
MAX_TRACE_BYTES = 1_000_000
MAX_TRACE_EVENTS = 200
EVENT_FIELDS = {
    "request_started": {"code", "configuration", "configuration_sha256"},
    "identity_validated": {"identity"},
    "request_validated": {"identity", "corpus_sha256"},
    "model_request": {
        "stage",
        "provider",
        "model",
        "prompt_version",
        "request_sha256",
        "evidence",
        "attempt",
        "retry_count",
        "prompt_sha256",
        "schema_sha256",
        "settings",
        "timeout_seconds",
    },
    "model_response": {"stage", "attempt", "elapsed_seconds", "usage", "retry_count"},
    "model_failed": {
        "stage",
        "attempt",
        "elapsed_seconds",
        "error",
        "retry_count",
        "error_type",
        "http_status",
    },
    "route_selected": {"action", "reason", "arguments", "arguments_sha256"},
    "route_proposed": {"action", "reason"},
    "route_guard": {"reason"},
    "answer_guard": {"reason"},
    "route_rejected": {"reason"},
    "tool_started": {"action", "attempt", "retry_count"},
    "tool_completed": {
        "action",
        "status",
        "evidence_ids",
        "source",
        "source_url",
        "body_sha256",
        "total_count",
        "returned_count",
        "fixture_id",
        "fixture_sha256",
        "network_attempts",
        "observed_at",
        "http_status",
        "retry_count",
        "elapsed_seconds",
        "retrieval_version",
        "scope_sha256",
    },
    "request_finished": {"status", "model_calls", "tool_calls", "citation_ids", "elapsed_seconds"},
    "request_failed": {"error", "model_calls", "tool_calls", "elapsed_seconds"},
}
ENVELOPE_FIELDS = {"trace_version", "run_id", "sequence", "time", "event"}


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def code_metadata() -> dict:
    """Only repository revision/status and source hashes, never diffs or environment values."""
    package = Path(__file__).resolve().parent
    files = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(package.glob("*.py"))
    }
    root = package.parent.parent
    revision = dirty = None
    if (root / ".git").exists():
        try:
            revision_result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            candidate = revision_result.stdout.strip()
            if revision_result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", candidate):
                revision = candidate
            status = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if status.returncode == 0:
                dirty = bool(status.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
    dependencies = {}
    for name in ("dealer-evidence-agent", "openai", "langgraph", "httpx", "rank-bm25"):
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = None
    return {
        "revision": revision,
        "working_tree_dirty": dirty,
        "source_sha256": fingerprint(files),
        "python": platform.python_version(),
        "packages": dependencies,
    }


def check_fields(event: str, fields: dict) -> None:
    if event not in EVENT_FIELDS or set(fields) - EVENT_FIELDS[event]:
        raise AgentError("invalid_trace_event")


class Trace(Protocol):
    def emit(self, event: str, **fields) -> None: ...


class RecordingTrace:
    """In-memory sink for offline boundary assertions."""

    def __init__(self):
        self.events: list[dict] = []

    def emit(self, event: str, **fields) -> None:
        check_fields(event, fields)
        self.events.append({"event": event, **fields})


class JsonlTrace:
    def __init__(self, directory: Path):
        self.run_id = uuid4().hex
        self.path = directory / f"{self.run_id}.jsonl"
        self._sequence = 0
        self._terminal_offset = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("x", encoding="utf-8")
        except OSError as exc:
            raise AgentError("trace_write_failed") from exc

    def emit(self, event: str, **fields) -> None:
        check_fields(event, fields)
        row = {
            "trace_version": TRACE_VERSION,
            "run_id": self.run_id,
            "sequence": self._sequence + 1,
            "time": datetime.now(UTC).isoformat(),
            "event": event,
            **fields,
        }
        offset = None
        try:
            line = json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
            offset = self._file.tell()
            self._file.write(line)
            self._file.flush()
            os.fsync(self._file.fileno())
        except (OSError, ValueError) as exc:
            # Remove a partial row when the filesystem still permits recovery.
            try:
                if offset is not None:
                    self._file.seek(offset)
                    self._file.truncate()
            except (OSError, ValueError):
                pass
            raise AgentError("trace_write_failed") from exc
        self._sequence += 1
        if event in ("request_finished", "request_failed"):
            self._terminal_offset = offset

    def close(self) -> None:
        try:
            self._file.close()
        except OSError as exc:
            # Best effort: a close failure must not leave a successful terminal row.
            try:
                with self.path.open("r+", encoding="utf-8") as recovery:
                    if self._terminal_offset is not None:
                        recovery.seek(self._terminal_offset)
                        recovery.truncate()
                    else:
                        recovery.seek(0, 2)
                    row = {
                        "trace_version": TRACE_VERSION,
                        "run_id": self.run_id,
                        "sequence": self._sequence
                        if self._terminal_offset is not None
                        else self._sequence + 1,
                        "time": datetime.now(UTC).isoformat(),
                        "event": "request_failed",
                        "error": "trace_write_failed",
                    }
                    recovery.write(json.dumps(row) + "\n")
                    recovery.flush()
                    os.fsync(recovery.fileno())
            except (OSError, ValueError):
                pass
            raise AgentError("trace_write_failed") from exc


def inspect_trace(directory: Path, run_id: str) -> dict:
    """Read one bounded trace within its directory; reject malformed data before display."""
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise AgentError("invalid_run_id")
    try:
        root = directory.resolve(strict=True)
        path = (root / f"{run_id}.jsonl").resolve(strict=True)
        if not path.is_relative_to(root):
            raise AgentError("invalid_trace_path")
        with path.open("rb") as file:
            raw = file.read(MAX_TRACE_BYTES + 1)
        if len(raw) > MAX_TRACE_BYTES:
            raise AgentError("trace_too_large")
        lines = raw.decode("utf-8").splitlines()
        if not raw.endswith(b"\n") or not 1 <= len(lines) <= MAX_TRACE_EVENTS:
            raise AgentError("invalid_trace")
        try:
            rows = [parse_json(line, max_chars=MAX_TRACE_BYTES) for line in lines]
        except AgentError as exc:
            raise AgentError("invalid_trace") from exc
        pending = set()
        seen = set()
        pending_tools = set()
        tool_calls = 0
        usage = {}
        calls = 0
        for sequence, row in enumerate(rows, 1):
            if (
                not isinstance(row, dict)
                or type(row.get("trace_version")) is not int
                or row.get("trace_version") != TRACE_VERSION
                or row.get("run_id") != run_id
                or type(row.get("sequence")) is not int
                or row["sequence"] != sequence
                or not ENVELOPE_FIELDS <= row.keys()
            ):
                raise AgentError("invalid_trace")
            if datetime.fromisoformat(row["time"]).utcoffset() is None:
                raise AgentError("invalid_trace")
            check_fields(row["event"], {k: v for k, v in row.items() if k not in ENVELOPE_FIELDS})
            event = row["event"]
            if (sequence == 1) != (event == "request_started"):
                raise AgentError("invalid_trace_lifecycle")
            if event in ("request_finished", "request_failed") and sequence != len(rows):
                raise AgentError("invalid_trace_lifecycle")
            if event == "tool_started":
                action = row.get("action")
                if action not in ("search_policies", "lookup_recalls") or tool_calls:
                    raise AgentError("invalid_trace_attempt")
                if row.get("attempt") != 1 or row.get("retry_count") != 0:
                    raise AgentError("invalid_trace_attempt")
                pending_tools.add(action)
                tool_calls += 1
            if event == "tool_completed":
                if row.get("action") not in pending_tools:
                    raise AgentError("invalid_trace_attempt")
                pending_tools.remove(row["action"])
            if event in ("model_request", "model_response", "model_failed"):
                stage, attempt = row.get("stage"), row.get("attempt")
                if stage not in ("route", "answer") or type(attempt) is not int or attempt != 1:
                    raise AgentError("invalid_trace_attempt")
                key = (stage, attempt)
                if event == "model_request":
                    if key in seen or (stage == "answer" and ("route", 1) not in seen):
                        raise AgentError("invalid_trace_attempt")
                    seen.add(key)
                    pending.add(key)
                    calls += 1
                    evidence = row.get("evidence")
                    if not isinstance(evidence, list) or (stage == "route" and evidence):
                        raise AgentError("invalid_trace_evidence")
                    for item in evidence:
                        if (
                            not isinstance(item, dict)
                            or set(item) != {"kind", "id", "content_sha256"}
                            or item["kind"] not in ("policy", "recall_campaign", "recall_response")
                            or not isinstance(item["id"], str)
                            or not isinstance(item["content_sha256"], str)
                            or not re.fullmatch(r"[0-9a-f]{64}", item["content_sha256"])
                        ):
                            raise AgentError("invalid_trace_evidence")
                else:
                    if key not in pending:
                        raise AgentError("invalid_trace_attempt")
                    pending.remove(key)
                    for name, count in row.get("usage", {}).items():
                        if name not in ("prompt_tokens", "completion_tokens", "total_tokens"):
                            raise AgentError("invalid_trace_usage")
                        if type(count) is not int or count < 0:
                            raise AgentError("invalid_trace_usage")
                        usage[name] = usage.get(name, 0) + count
        complete = rows[-1]["event"] in ("request_finished", "request_failed")
        if rows[-1]["event"] == "request_finished" and (pending or pending_tools):
            raise AgentError("invalid_trace_lifecycle")
        if complete:
            for name, actual in (("model_calls", calls), ("tool_calls", tool_calls)):
                if name in rows[-1]:
                    reported = rows[-1][name]
                    limit = 2 if name == "model_calls" else 1
                    # A logical call may fail during preparation, before a persisted attempt.
                    if (
                        type(reported) is not int
                        or not actual <= reported <= limit
                        or (rows[-1]["event"] == "request_finished" and reported != actual)
                    ):
                        raise AgentError("invalid_trace_counts")
        return {
            "run_id": run_id,
            "complete": complete,
            "outcome": rows[-1].get("status", rows[-1].get("error", "incomplete")),
            "model_attempts": calls,
            "unconfirmed_attempts": sorted(pending),
            "unconfirmed_tools": sorted(pending_tools),
            "tool_calls": tool_calls,
            "usage": usage,
            "events": rows,
        }
    except AgentError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise AgentError("invalid_trace") from exc
