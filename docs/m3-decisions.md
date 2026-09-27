# M3: public recall lookup and response fixtures

Implementation date: 2026-09-26 local time. M2 was committed as `e7dfb7f` before
this work. The policy corpus and frozen development/held-out cases are unchanged.

## Tool boundary

`RecallLookup(identity=...).lookup_recalls(make, model, year, limit=5)` calls
NHTSA's [documented year/make/model endpoint](https://www.nhtsa.gov/nhtsa-datasets-and-apis#recalls).
Identity is trusted request context, not a model-supplied tool argument. Both
known demo identities may use this public tool; unknown identities are rejected
before client creation. The CLI requires an explicit live or fixture mode.

Make and model must be nonblank vehicle labels up to 80 characters, with ordinary
letters, numbers, spaces, and label punctuation. Controls/URLs are rejected.
Leading/trailing and repeated spaces normalize away; no aliases or inferred
vehicle details are added. Year must be one integer from 1900 through 2100,
matching the fixture argument contract; this range does not assert API coverage
or that the combination exists. Limit must be an integer 1..10 (default 5).
Missing/ambiguous arguments must be clarified by the future router before a call.

## Network and response contract

- Fixed HTTPS host/path; HTTPX encodes make/model/year as query parameters.
- Exactly one network attempt per valid lookup; no retries, redirects, alternate
  service, cache, or fixture fallback. One logical data-tool call remains one
  HTTP request. No API keys, `.env`, model client, or environment proxy settings.
- Connect/pool timeout 3 seconds; read/write timeout 5 seconds. A monotonic
  15-second elapsed budget is checked at response chunks and completion. This
  is not preemptive cancellation: an in-progress I/O operation may run until
  its own timeout before the elapsed budget can be checked.
- Stream and reject bodies above 1,000,000 decoded bytes. Accept JSON content
  types only. Invalid JSON, duplicate JSON keys, non-finite values, unrecognized
  success messages, inconsistent counts, and unexpected record shapes fail closed.
- Validate all records before truncating output. Require matching vehicle fields,
  unique valid campaign numbers, and nonempty manufacturer, component, summary,
  and received-date strings. Upstream text fields are limited to 8,000 characters,
  and the envelope to 500 records. Schema changes produce an explicit error.
- Missing remedy/consequence or source flags remain unknown (`null`), never a
  fabricated remedy or `false`. Received dates preserve the source string; no
  ambiguous day/month conversion is attempted. Upstream prose is untrusted data.
- Sort normalized records by campaign number, then return at most the requested
  limit. Report `total_count` and `truncated`; never imply a capped list is complete.

The result includes query, URL, UTC observation time, exact response-body hash,
HTTP status when available, network attempt count, provenance, and campaign
evidence. Raw HTTP error text is not surfaced as instructions or a diagnosis.

| Status | Meaning | CLI exit |
| --- | --- | --- |
| `ok` | Valid nonempty campaign response | 0 |
| `empty` | Valid successful envelope with zero records | 0 |
| `http_error` | Any HTTP status other than 200, including redirects/429 | 1 |
| `timeout` | I/O timeout or elapsed request budget exhausted | 1 |
| `network_error` | Connection/protocol request failure | 1 |
| `invalid_response` | Invalid JSON/schema/content encoding/type | 1 |
| `response_too_large` | Response exceeds byte limit | 1 |

Failures have `total_count: null`, not zero. Every outcome carries the boundary:
general campaign records do not establish VIN-specific eligibility, completed
repairs, or vehicle safety; an empty response does not prove absence of recalls.

## Versioned offline fixtures

`data/recalls/v1/` contains three public response captures for the existing
development recall queries and six labeled synthetic scenarios. The captured
responses contain 3, 6, and 19 records respectively; these are snapshot counts,
not claims about today's database. See [fixture provenance](../data/recalls/README.md).

Replay validates metadata/body hashes, requires matching query fields, and emits
`recorded_fixture` or `synthetic_fixture`, never `live`. Recorded timestamps remain
the capture timestamps; synthetic timestamps are null and replay always reports
zero network attempts. Corrupt or missing fixtures raise an error without fallback.

Fixture manifest SHA-256:
`499b9afe3e39294e675cc8862eac1584cb8be9dbe52ce38149d1cbc88134a36d`

## Verification

- **192 tests passed, 1 skipped** (the existing Windows symlink permission check).
  All routine tests run offline using MockTransport, recorded data, or synthetic
  data. Tests cover limits, exact query encoding, invalid inputs, pre-network
  authorization, response/schema failures, timeout, single attempts, redirect
  refusal, explicit truncation, fixture integrity, provenance, and CLI exit codes.
- All nine fixtures pass offline validation; all three development recall argument
  sets have matching recorded responses. Held-out cases were not opened or scored.
- A live smoke check through the completed tool returned `ok`, `source: live`,
  one network attempt, and three campaign records for Toyota/Corolla/2020.
- Ruff lint/formatting, diff whitespace checks, dependency lock validation, and
  offline wheel build passed. Wheel inspection confirmed both recall modules and
  excluded credentials, caches, corpus, and fixtures. Existing corpus/development
  fingerprints still validate; Git attributes preserve raw fixture bytes.
- Initial direct shell networking was sandbox-restricted. The authorized fixture
  captures and live smoke check used the escalation mechanism. Tests do not need it.

These checks measure the tool contract, not model routing or final answer quality.
Next is M4: bounded model routing and evidence-grounded answers using the two tools.
