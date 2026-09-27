"""Bounded public NHTSA lookup; results never establish individual vehicle status."""

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx

from dealer_evidence_agent.permissions import resolve_role

ENDPOINT = "https://api.nhtsa.gov/recalls/recallsByVehicle"
MAX_RESPONSE_BYTES = 1_000_000
MAX_RECORDS = 500
MAX_FIELD_CHARS = 8000
DEFAULT_LIMIT = 5
MAX_LIMIT = 10
REQUEST_BUDGET_SECONDS = 15
BOUNDARY = (
    "General year/make/model campaign records only. These do not establish VIN-specific "
    "eligibility, repair completion, or that a vehicle is safe to drive. An empty result "
    "does not prove there are no recalls."
)
Source = Literal["live", "recorded_fixture", "synthetic_fixture"]


class RecallInputError(ValueError):
    """Missing, ambiguous, or invalid tool arguments; no request was made."""


class RecallResponseError(ValueError):
    """The upstream body cannot be used as reliable structured evidence."""


@dataclass(frozen=True)
class VehicleQuery:
    make: str
    model: str
    year: int


@dataclass(frozen=True)
class RecallRecord:
    campaign_number: str
    manufacturer: str
    component: str
    summary: str
    consequence: str | None
    remedy: str | None
    report_received_date: str
    park_it: bool | None
    park_outside: bool | None
    over_the_air_update: bool | None


@dataclass(frozen=True)
class RecallResult:
    status: str
    source: Source
    query: VehicleQuery
    source_url: str
    observed_at: str | None
    body_sha256: str | None
    http_status: int | None
    network_attempts: int
    total_count: int | None
    truncated: bool
    records: tuple[RecallRecord, ...]
    error: str | None
    fixture_id: str | None = None
    boundary: str = BOUNDARY
    fixture_sha256: str | None = None


def validate_query(make: str, model: str, year: int, limit: int = DEFAULT_LIMIT) -> VehicleQuery:
    labels = []
    for name, value in (("make", make), ("model", model)):
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 80
            or not any(char.isalnum() for char in value)
            or any(not (char.isalnum() or char in " .-'&/+()") for char in value)
        ):
            raise RecallInputError(f"{name} must be one vehicle label of 1 to 80 characters.")
        labels.append(" ".join(value.split()))
    if type(year) is not int or not 1900 <= year <= 2100:
        raise RecallInputError("year must be one integer from 1900 to 2100.")
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise RecallInputError(f"limit must be an integer from 1 to {MAX_LIMIT}.")
    return VehicleQuery(labels[0], labels[1], year)


def source_url(query: VehicleQuery) -> str:
    return str(
        httpx.URL(
            ENDPOINT,
            params={
                "make": query.make,
                "model": query.model,
                "modelYear": query.year,
            },
        )
    )


def failure(
    query: VehicleQuery,
    status: str,
    *,
    source: Source,
    observed_at: str | None,
    network_attempts: int,
    http_status: int | None = None,
    body: bytes | None = None,
    fixture_id: str | None = None,
) -> RecallResult:
    messages = {
        "timeout": "NHTSA request timed out; no recall determination is available.",
        "network_error": "NHTSA could not be reached; no recall determination is available.",
        "http_error": (
            "NHTSA returned an unsuccessful HTTP status; no recall determination is available."
        ),
        "invalid_response": (
            "NHTSA response failed validation; no recall determination is available."
        ),
        "response_too_large": "NHTSA response exceeded the configured size limit.",
    }
    return RecallResult(
        status=status,
        source=source,
        query=query,
        source_url=source_url(query),
        observed_at=observed_at,
        body_sha256=hashlib.sha256(body).hexdigest() if body is not None else None,
        http_status=http_status,
        network_attempts=network_attempts,
        total_count=None,
        truncated=False,
        records=(),
        error=messages[status],
        fixture_id=fixture_id,
    )


def _text(row: dict, key: str, *, optional: bool = False) -> str | None:
    value = row.get(key)
    if optional and (value is None or value == ""):
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_FIELD_CHARS:
        raise RecallResponseError(f"Invalid {key}.")
    return value


def _flag(row: dict, key: str) -> bool | None:
    value = row.get(key)
    if value is not None and type(value) is not bool:
        raise RecallResponseError(f"Invalid {key}.")
    return value


def _parse(body: bytes, query: VehicleQuery) -> tuple[RecallRecord, ...]:
    def reject_constant(value):
        raise RecallResponseError("Non-finite JSON value.")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecallResponseError("Duplicate JSON key.")
            result[key] = value
        return result

    try:
        payload = json.loads(
            body.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_object
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RecallResponseError("Invalid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise RecallResponseError("Expected a response object.")
    count, rows = payload.get("Count"), payload.get("results")
    if (
        type(count) is not int
        or not isinstance(rows, list)
        or count != len(rows)
        or not 0 <= count <= MAX_RECORDS
    ):
        raise RecallResponseError("Invalid response count/results.")
    # A valid empty envelope is not a service error disguised as an empty list.
    if payload.get("Message") != "Results returned successfully":
        raise RecallResponseError("Unrecognized response message.")
    records = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RecallResponseError("Invalid recall record.")
        for key, expected in (("Make", query.make), ("Model", query.model)):
            value = _text(row, key)
            if " ".join(value.split()).casefold() != expected.casefold():
                raise RecallResponseError("Response vehicle does not match the query.")
        if str(row.get("ModelYear")) != str(query.year):
            raise RecallResponseError("Response year does not match the query.")
        campaign = _text(row, "NHTSACampaignNumber")
        if not re.fullmatch(r"\d{2}[A-Z]\d{6}", campaign) or campaign in seen:
            raise RecallResponseError("Invalid or duplicate campaign number.")
        seen.add(campaign)
        records.append(
            RecallRecord(
                campaign_number=campaign,
                manufacturer=_text(row, "Manufacturer"),
                component=_text(row, "Component"),
                summary=_text(row, "Summary"),
                consequence=_text(row, "Consequence", optional=True),
                remedy=_text(row, "Remedy", optional=True),
                report_received_date=_text(row, "ReportReceivedDate"),
                park_it=_flag(row, "parkIt"),
                park_outside=_flag(row, "parkOutSide"),
                over_the_air_update=_flag(row, "overTheAirUpdate"),
            )
        )
    return tuple(sorted(records, key=lambda record: record.campaign_number))


def response_result(
    query: VehicleQuery,
    *,
    status_code: int,
    content_type: str,
    body: bytes,
    source: Source,
    observed_at: str | None,
    network_attempts: int,
    limit: int = DEFAULT_LIMIT,
    fixture_id: str | None = None,
) -> RecallResult:
    context = dict(
        source=source,
        observed_at=observed_at,
        network_attempts=network_attempts,
        http_status=status_code,
        fixture_id=fixture_id,
    )
    if len(body) > MAX_RESPONSE_BYTES:
        return failure(query, "response_too_large", **context)
    if status_code != 200:
        return failure(query, "http_error", body=body, **context)
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime != "application/json" and not (
        mime.startswith("application/") and mime.endswith("+json")
    ):
        return failure(query, "invalid_response", body=body, **context)
    try:
        records = _parse(body, query)
    except RecallResponseError:
        return failure(query, "invalid_response", body=body, **context)
    return RecallResult(
        status="ok" if records else "empty",
        source=source,
        query=query,
        source_url=source_url(query),
        observed_at=observed_at,
        body_sha256=hashlib.sha256(body).hexdigest(),
        http_status=status_code,
        network_attempts=network_attempts,
        total_count=len(records),
        truncated=len(records) > limit,
        records=records[:limit],
        error=None,
        fixture_id=fixture_id,
    )


class RecallLookup:
    """One request, no retries/redirects/fallback; identity comes from trusted context."""

    def __init__(self, *, identity: str, transport: httpx.BaseTransport | None = None):
        resolve_role(identity)
        self._transport = transport

    def lookup_recalls(
        self, make: str, model: str, year: int, *, limit: int = DEFAULT_LIMIT
    ) -> RecallResult:
        query = validate_query(make, model, year, limit)
        deadline = time.monotonic() + REQUEST_BUDGET_SECONDS
        status_code = None
        try:
            with (
                httpx.Client(
                    timeout=httpx.Timeout(5, connect=3, pool=3),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self._transport,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "dealer-evidence-agent/0.1",
                    },
                ) as client,
                client.stream("GET", source_url(query)) as response,
            ):
                status_code = response.status_code
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise httpx.ReadTimeout("Request budget exceeded.")
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        return failure(
                            query,
                            "response_too_large",
                            source="live",
                            observed_at=datetime.now(UTC).isoformat(),
                            network_attempts=1,
                            http_status=status_code,
                        )
                    chunks.append(chunk)
                if time.monotonic() > deadline:
                    raise httpx.ReadTimeout("Request budget exceeded.")
                return response_result(
                    query,
                    status_code=status_code,
                    content_type=response.headers.get("content-type", ""),
                    body=b"".join(chunks),
                    source="live",
                    observed_at=datetime.now(UTC).isoformat(),
                    network_attempts=1,
                    limit=limit,
                )
        except httpx.TimeoutException:
            status = "timeout"
        except httpx.DecodingError:
            status = "invalid_response"
        except httpx.HTTPError:
            status = "network_error"
        return failure(
            query,
            status,
            source="live",
            observed_at=datetime.now(UTC).isoformat(),
            network_attempts=1,
            http_status=status_code,
        )
