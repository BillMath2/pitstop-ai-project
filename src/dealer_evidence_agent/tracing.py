"""M4 boundary hooks and a minimal fail-closed JSONL sink; no raw messages."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from dealer_evidence_agent.answers import AgentError


class Trace(Protocol):
    def emit(self, event: str, **fields) -> None: ...


class RecordingTrace:
    """In-memory sink for offline boundary assertions."""

    def __init__(self):
        self.events: list[dict] = []

    def emit(self, event: str, **fields) -> None:
        self.events.append({"event": event, **fields})


class JsonlTrace:
    def __init__(self, directory: Path):
        self.run_id = uuid4().hex
        self.path = directory / f"{self.run_id}.jsonl"
        self._sequence = 0
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("x", encoding="utf-8")
        except OSError as exc:
            raise AgentError("trace_write_failed") from exc

    def emit(self, event: str, **fields) -> None:
        self._sequence += 1
        row = {
            "run_id": self.run_id,
            "sequence": self._sequence,
            "time": datetime.now(UTC).isoformat(),
            "event": event,
            **fields,
        }
        try:
            self._file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            self._file.flush()
        except (OSError, ValueError) as exc:
            raise AgentError("trace_write_failed") from exc

    def close(self) -> None:
        try:
            self._file.close()
        except OSError as exc:
            raise AgentError("trace_write_failed") from exc
