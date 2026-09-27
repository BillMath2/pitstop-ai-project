"""Integrity-checked replay, always labeled as recorded or synthetic data."""

import hashlib
import json
import re
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

from dealer_evidence_agent.permissions import resolve_role
from dealer_evidence_agent.recalls import (
    DEFAULT_LIMIT,
    MAX_RESPONSE_BYTES,
    RecallInputError,
    RecallResult,
    failure,
    response_result,
    source_url,
    validate_query,
)

DEFAULT_FIXTURE_MANIFEST = Path("data/recalls/v1/manifest.json")
_FIELDS = {
    "fixture_id",
    "kind",
    "query",
    "source_url",
    "captured_at",
    "http_status",
    "content_type",
    "transport_error",
    "body_path",
    "body_sha256",
    "expected_status",
}
_STATUSES = {"ok", "empty", "http_error", "timeout", "network_error", "invalid_response"}


class RecallFixtureError(ValueError):
    """A fixture or its provenance has changed or is not valid."""


def fixture_fingerprint(records: list[dict]) -> str:
    canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_fixture_manifest(path: Path) -> tuple[dict, ...]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RecallFixtureError("Cannot read recall fixture manifest.") from exc
    if not isinstance(data, dict) or set(data) != {"schema_version", "fixtures", "fixtures_sha256"}:
        raise RecallFixtureError("Invalid fixture manifest fields.")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise RecallFixtureError("Unsupported fixture manifest schema.")
    records = data["fixtures"]
    if not isinstance(records, list) or not records:
        raise RecallFixtureError("Fixture manifest must contain records.")
    if data["fixtures_sha256"] != fixture_fingerprint(records):
        raise RecallFixtureError("Fixture metadata fingerprint mismatch.")
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != _FIELDS:
            raise RecallFixtureError("Invalid fixture metadata fields.")
        fixture_id = record["fixture_id"]
        if not isinstance(fixture_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", fixture_id):
            raise RecallFixtureError("Invalid fixture ID.")
        if fixture_id in seen:
            raise RecallFixtureError("Duplicate fixture ID.")
        seen.add(fixture_id)
        query = record["query"]
        if not isinstance(query, dict) or set(query) != {"make", "model", "year"}:
            raise RecallFixtureError("Invalid fixture query.")
        try:
            validated = validate_query(**query)
        except RecallInputError as exc:
            raise RecallFixtureError("Invalid fixture query.") from exc
        if query != asdict(validated) or record["source_url"] != source_url(validated):
            raise RecallFixtureError("Fixture source URL/query mismatch.")
        if record["kind"] not in ("recorded", "synthetic"):
            raise RecallFixtureError("Unknown fixture provenance.")
        if record["kind"] == "recorded":
            try:
                captured = datetime.fromisoformat(record["captured_at"])
                if captured.utcoffset() != timedelta(0):
                    raise ValueError("Expected UTC.")
            except (ValueError, TypeError) as exc:
                raise RecallFixtureError("Recorded fixture requires a UTC capture time.") from exc
            if record["transport_error"] is not None:
                raise RecallFixtureError("Transport failure fixtures must be synthetic.")
        elif record["captured_at"] is not None:
            raise RecallFixtureError("Synthetic fixtures must not claim a capture time.")
        if record["expected_status"] not in tuple(_STATUSES):
            raise RecallFixtureError("Unknown expected fixture status.")
        if record["transport_error"] is not None:
            if record["transport_error"] not in ("timeout", "network_error") or any(
                record[key] is not None
                for key in ("http_status", "content_type", "body_path", "body_sha256")
            ):
                raise RecallFixtureError("Invalid synthetic transport failure.")
        else:
            if type(record["http_status"]) is not int or not 100 <= record["http_status"] <= 599:
                raise RecallFixtureError("Invalid fixture HTTP status.")
            if not isinstance(record["content_type"], str):
                raise RecallFixtureError("Invalid fixture content type.")
            if not isinstance(record["body_path"], str) or not re.fullmatch(
                r"[a-z0-9-]+\.json", record["body_path"]
            ):
                raise RecallFixtureError("Fixture body must be an adjacent JSON-named file.")
            if not isinstance(record["body_sha256"], str) or not re.fullmatch(
                r"[0-9a-f]{64}", record["body_sha256"]
            ):
                raise RecallFixtureError("Invalid fixture body fingerprint.")
    return tuple(records)


def _replay(path: Path, record: dict, limit: int) -> RecallResult:
    query = validate_query(**record["query"], limit=limit)
    source = "recorded_fixture" if record["kind"] == "recorded" else "synthetic_fixture"
    context = dict(
        source=source,
        observed_at=record["captured_at"],
        network_attempts=0,
        fixture_id=record["fixture_id"],
    )
    if record["transport_error"] is not None:
        return failure(query, record["transport_error"], **context)
    try:
        root = path.parent.resolve()
        body_path = (root / record["body_path"]).resolve(strict=True)
        if not body_path.is_relative_to(root) or body_path.stat().st_size > MAX_RESPONSE_BYTES:
            raise ValueError("Invalid body location or size.")
        body = body_path.read_bytes()
    except (OSError, ValueError, RuntimeError) as exc:
        raise RecallFixtureError("Cannot read bounded fixture body within its directory.") from exc
    if len(body) > MAX_RESPONSE_BYTES or hashlib.sha256(body).hexdigest() != record["body_sha256"]:
        raise RecallFixtureError("Fixture body fingerprint or size mismatch.")
    return response_result(
        query,
        status_code=record["http_status"],
        content_type=record["content_type"],
        body=body,
        limit=limit,
        **context,
    )


def replay_recalls(
    path: Path,
    fixture_id: str,
    *,
    identity: str,
    make: str,
    model: str,
    year: int,
    limit: int = DEFAULT_LIMIT,
) -> RecallResult:
    resolve_role(identity)
    query = validate_query(make, model, year, limit)
    records = load_fixture_manifest(path)
    record = next((record for record in records if record["fixture_id"] == fixture_id), None)
    if record is None:
        raise RecallFixtureError("Unknown recall fixture ID.")
    stored = record["query"]
    if (stored["make"].casefold(), stored["model"].casefold(), stored["year"]) != (
        query.make.casefold(),
        query.model.casefold(),
        query.year,
    ):
        raise RecallFixtureError("Fixture vehicle does not match the requested vehicle.")
    return replace(_replay(path, record, limit), fixture_sha256=fixture_fingerprint(list(records)))


def validate_recall_fixtures(path: Path) -> dict:
    records = load_fixture_manifest(path)
    for record in records:
        result = _replay(path, record, DEFAULT_LIMIT)
        if result.status != record["expected_status"]:
            raise RecallFixtureError(f"Unexpected replay status for {record['fixture_id']}.")
    return {
        "fixtures": len(records),
        "recorded": sum(r["kind"] == "recorded" for r in records),
        "synthetic": sum(r["kind"] == "synthetic" for r in records),
        "fixtures_sha256": fixture_fingerprint(list(records)),
    }
