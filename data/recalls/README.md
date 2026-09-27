# Recall fixture provenance

Version 1 contains public NHTSA response captures and explicitly synthetic test
scenarios. None is a current live result when replayed.

Source documentation: [NHTSA Datasets and APIs, Recalls](https://www.nhtsa.gov/nhtsa-datasets-and-apis#recalls).
Endpoint: `https://api.nhtsa.gov/recalls/recallsByVehicle`, with query parameters
`make`, `model`, and `modelYear`. No API key or personal vehicle data was sent.

## Recorded responses

| Fixture ID | Query | Records in captured response |
| --- | --- | --- |
| `toyota-corolla-2020` | Toyota / Corolla / 2020 | 3 |
| `honda-accord-2018` | Honda / Accord / 2018 | 6 |
| `ford-escape-2022` | Ford / Escape / 2022 | 19 |

These are the three existing development recall examples. Capture happened on
2026-09-27 UTC (2026-09-26 in America/New_York). Exact observation times, original
URLs, HTTP status/content type, and SHA-256 hashes are in `v1/manifest.json`.
Bodies preserve the response entity bytes returned by HTTPX (after any HTTP
content decoding), without JSON reformatting or newline conversion. Git marks
these JSON files `-text` so exact-byte hashes survive checkout on Windows.
The raw response can contain fields not used by the normalized tool result.

## Synthetic scenarios

| Fixture ID | Simulated condition |
| --- | --- |
| `synthetic-empty` | Valid successful envelope with zero records |
| `synthetic-malformed` | HTTP 200 with invalid JSON |
| `synthetic-rate-limit` | HTTP 429 |
| `synthetic-unavailable` | HTTP 503 |
| `synthetic-timeout` | Transport timeout, no HTTP response |
| `synthetic-network` | Transport connection failure, no HTTP response |

These scenarios use the Toyota/Corolla/2020 request only as a test input. The
synthetic empty result is not a factual assertion about that vehicle. Synthetic
records have `captured_at: null`; transport failures have no body or HTTP status.
The malformed body uses a `.json` filename deliberately but is not valid JSON.

## Integrity and use

The version 1 manifest has a schema version and `fixtures_sha256`, the SHA-256
of its `fixtures` array serialized as compact UTF-8 JSON with sorted object keys
and `ensure_ascii=False`. Array order is significant. This binds query, source,
provenance labels, times, expected status, and exact body hash. Every body is an
adjacent file with a verified SHA-256; path traversal/symlink escape is rejected.
These hashes detect drift, not malicious rewriting by a trusted repository editor.

```powershell
.\.venv\Scripts\dealer-evidence.exe validate-recall-fixtures
.\.venv\Scripts\dealer-evidence.exe lookup-recalls --identity tech_demo --make Toyota --model Corolla --year 2020 --fixture synthetic-timeout --json
```

Validation checks all nine fixtures without a network request. A timeout replay
exits 1 with an explicit tool error; an empty replay exits 0 with `status: empty`.
Replay requires the requested make/model/year to match the recorded query
(case-insensitive labels); it cannot silently reuse another vehicle's results.
There is no automatic live fallback or cache masquerading as a fresh response.

Keep v1 frozen. For a deliberate refresh, capture new public responses in a new
version directory, record actual UTC timestamps/URLs and entity-byte hashes,
review schema compatibility and expected statuses, then compute a new manifest
hash using `fixture_fingerprint()`. Extend `.gitattributes` for the new directory
and run validation against it. Never relabel synthetic data as a real capture or
change held-out cases to fit response observations.
