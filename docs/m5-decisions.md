# M5: request-boundary JSONL traces

Implemented 2026-09-27 from clean M4 commit `320fcb7`.
**Status: M5 complete; M6 evaluation and CI are next.** M5 uses offline tests and
the real SDK through a mock HTTP transport; no live provider or NHTSA calls were
needed, and no held-out cases were read. M4's live 7/7 result remains a separate
development result, not a new M5 model-quality measurement.

## Lifecycle and failure behavior

`ask` creates a new exclusive `runs/<run_id>.jsonl` and records `request_started`
before identity/question/corpus/configuration validation or provider setup.
Known identity is recorded only after validation. Invalid identities, input,
corpus, and credentials produce a terminal failure with no external call.
The CLI owns finalization, including provider-client cleanup, so cleanup failure
cannot be followed by an apparently successful terminal event. Direct graph
callers own provider cleanup and use the graph's default lifecycle; the CLI
explicitly disables that default to avoid duplicate start/terminal events.

Events have trace version 1, a UUID run ID, increasing sequence number, and UTC
time. Graph events include the route, tool start/outcome, actual model boundary,
and request completion/failure. A logical call count can include preparation that
failed before a persisted `model_request`; the inspector distinguishes logical
counts from recorded attempts. An attempted provider call is not proof of a
confirmed response. `model_response` means a response was observed, even if its
content is subsequently rejected. `model_failed` means a transport/provider
exception was observed. Only provider-reported usage is recorded; absence is
not represented as zero token use.

Each row is flushed and fsynced before execution continues. Write, flush, and
fsync failures become explicit errors and prevent subsequent external work.
Partial rows are rolled back when the filesystem permits it, and failure
finalization is attempted. On close failure the sink attempts to replace its
terminal success with a trace-write failure. A persistently broken filesystem
may prevent any recovery record; the CLI still reports an error. An interrupted
process can leave a valid incomplete trace, which inspection labels incomplete.
This does not promise recovery after every crash or device failure.

## Recorded metadata and privacy

| Event | Recorded evidence |
| --- | --- |
| `request_started` | Git revision, dirty flag, fingerprint of installed package source bytes, Python/dependency versions, execution limits and their fingerprint |
| `request_validated` | Validated demo identity and complete corpus fingerprint |
| `route_selected` | Validated action and arguments fingerprint; readable recall make/model/year; explicit redaction marker for policy-query text |
| `tool_started` | Logical action, attempt 1, retry count 0 |
| Policy `tool_completed` | Accepted document IDs, retrieval version, authorized-scope fingerprint, status and timing |
| Recall `tool_completed` | Campaign IDs, status, URL, observation time, response hash, fixture ID/manifest fingerprint, HTTP status, network attempts, counts and timing |
| `model_request` | Provider/model, stage, prompt version/hash, actual response-schema hash, generation settings, timeout, request hash, exact supplied evidence IDs/content hashes, attempt/retry counts |
| `model_response` / `model_failed` | Stage/attempt, timing, available token usage or safe failure class/status |
| Terminal event | Disposition or fixed error, logical model/tool counts, elapsed time, and validated citation IDs on success |

Source fingerprints distinguish uncommitted code from the Git revision. Git
metadata is null when unavailable, such as an installed wheel outside a checkout;
the source fingerprint and installed package versions remain available. No Git
diff, environment dump, credentials, headers, raw question, evidence body, or
model prose is written. Fixed event-field allowlists also reject reserved
envelope fields and accidental raw-message fields. Errors use safe codes rather
than upstream exception text or invalid model-supplied citation IDs.

Policy tool queries may echo questions or restricted-looking strings supplied
by a caller. They are deliberately represented by a canonical argument hash and
`query_redacted: true`, rather than their raw value. Validated recall fields are
readable because they identify the public lookup. A fingerprint supports checking
known input; it is not encryption or a guarantee against guessing short text.
This metadata reconstructs execution and source membership without reconstructing
private question text. Questions should not contain credentials.

Policy results are logged only after the independent permission/context guard
accepts them. A faulty retriever's rejected IDs do not enter ordinary traces.
Manager runs can contain their authorized manager-policy IDs; technician runs
must not receive those IDs from retrieval, generation, or citations. These remain
local selectable identities, not authentication. The trace command reads local
files; it is not a hosted access-control service or a signed audit log.

## Actual provider boundary

Evidence IDs and content hashes are derived from the final serialized message
payload immediately before the SDK create call. Prompt/schema fingerprints and
generation settings likewise come from that outgoing body. The full canonical
body is hashed, but not persisted. Timeouts are SDK request options and are
recorded separately from the HTTP body hash. Routing evidence is always empty.

The recording client captures this same body. An additional test passes both
routing and answer requests through the installed real OpenAI SDK and captures
the emitted HTTP JSON using MockTransport. It compares full request, prompt,
schema, evidence IDs, exact content, and hashes, including forbidden-source
checks and a sentinel credential in the HTTP Authorization header. That header
does not enter the trace. Recall fixtures add their validated manifest hash to
the result, including synthetic transport failures with no response-body hash.

Retries remain disabled. Both model and tool events accurately record zero
retries; NHTSA network attempts distinguish live transport from zero-network
fixture replay. M5 does not introduce an untested retry path.

## Inspection and example

```powershell
.\.venv\Scripts\dealer-evidence.exe trace --run-id <run-id>
.\.venv\Scripts\dealer-evidence.exe trace --run-id <run-id> --json
.\.venv\Scripts\python.exe scripts/m5_trace_example.py
.\.venv\Scripts\dealer-evidence.exe trace --runs-dir docs/examples --run-id e79271e8fcfc412eabfbb634c06c8b49
```

Inspection bounds the file to 1 MB/200 events, validates the run ID and resolved
path, and rejects malformed JSON, duplicate keys, unknown fields, incorrect
versions, sequence errors, contradictory lifecycles, and inconsistent attempts.
It reports totals and unconfirmed attempts. Incomplete traces return exit 1;
valid completed traces return exit 0 even when the recorded request failed.
Versionless M4 traces remain historical artifacts and are rejected by the M5
inspector; no old execution metadata is invented or backfilled.

The [reviewed example](examples/e79271e8fcfc412eabfbb634c06c8b49.jsonl) uses only
fictional shared policies, an explicit `recording_fake` provider, and scripted
replies. There were no provider or NHTSA calls and no reported tokens. It was
reviewed for allowed evidence IDs/hashes and absence of restricted identifiers,
credentials, questions, headers, and raw messages. Its actual run ID/time/revision
and dirty flag are preserved. It illustrates tracing, not model answer quality.
All other generated runs remain ignored. See [example notes](examples/README.md).

## Verification and next task

The full offline suite passes **317 tests, with one existing Windows symlink
skip** (M4 baseline: 279 passed). The 38 new tests cover real SDK/body agreement,
setup failures, clarification/unsupported/no-match exits, recall provenance and
errors, provider failures, absent usage, credential omission, invalid citations,
partial writes, flush/fsync/close failures, cleanup, corrupt and incomplete files,
and inspection boundaries. Existing permission and graph regressions still pass.

Ruff, dependency/lock validation, offline builds, and packaged-file inspection
also pass. No corpus, evaluation-case, prompt, or model changes were needed.
Elapsed engineering time was not instrumented. No commit, push, or publication
was performed. **Next: M6 evaluation reports, offline CI, and the isolated
production authorization regression demonstration.**
