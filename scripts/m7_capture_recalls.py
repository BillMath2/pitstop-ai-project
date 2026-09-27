"""Explicit public NHTSA captures for M7; no model calls or fixture overwrites.

Run once from the repository root. The response bodies are public campaign
records, not VIN-specific status. Keep the original v1 fixtures frozen.
"""

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from dealer_evidence_agent.recall_fixtures import fixture_fingerprint, validate_recall_fixtures
from dealer_evidence_agent.recalls import (
    MAX_RESPONSE_BYTES,
    response_result,
    source_url,
    validate_query,
)

VEHICLES = (("Subaru", "Outback", 2019), ("Hyundai", "Tucson", 2023), ("Chevrolet", "Malibu", 2017))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/recalls/v2"))
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Output directory already exists; never overwrite a frozen capture.")
    captured = []
    with httpx.Client(
        timeout=10,
        trust_env=False,
        follow_redirects=False,
        headers={"Accept": "application/json", "User-Agent": "dealer-evidence-agent/0.1"},
    ) as client:
        for make, model, year in VEHICLES:
            query = validate_query(make, model, year)
            deadline = time.monotonic() + 15
            chunks, size = [], 0
            with client.stream("GET", source_url(query)) as response:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES or time.monotonic() > deadline:
                        raise RuntimeError("Capture exceeded size/time bound.")
                    chunks.append(chunk)
                body = b"".join(chunks)
                observed = datetime.now(UTC).isoformat()
                result = response_result(
                    query,
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type", ""),
                    body=body,
                    source="live",
                    observed_at=observed,
                    network_attempts=1,
                )
                if result.status not in ("ok", "empty"):
                    raise RuntimeError(f"Capture failed for {make}/{model}/{year}: {result.status}")
                fixture_id = f"{make}-{model}-{year}".lower()
                record = {
                    "fixture_id": fixture_id,
                    "kind": "recorded",
                    "query": asdict(query),
                    "source_url": result.source_url,
                    "captured_at": observed,
                    "http_status": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "transport_error": None,
                    "body_path": f"{fixture_id}.json",
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "expected_status": result.status,
                }
                captured.append((record, body))
                print(f"{fixture_id}: {result.status}, {result.total_count} records", flush=True)
    args.output_dir.mkdir(parents=True)
    for record, body in captured:
        (args.output_dir / record["body_path"]).write_bytes(body)
    records = [record for record, _ in captured]
    manifest = {
        "schema_version": 1,
        "fixtures": records,
        "fixtures_sha256": fixture_fingerprint(records),
    }
    path = args.output_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validate_recall_fixtures(path)))


if __name__ == "__main__":
    main()
