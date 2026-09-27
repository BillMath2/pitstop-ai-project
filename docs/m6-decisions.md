# M6: evaluation, offline CI, and a production authorization regression

Implemented 2026-09-27 from M5 revision
`6ec238d88e11b96955db62c63f950a744bdca8da`. M6 is complete locally; hosted
passing/red CI evidence remains an explicitly authorized M7 publication step.
No live model or NHTSA calls were made, and real held-out cases were not read.

## Evaluation modes

```powershell
.\.venv\Scripts\dealer-evidence.exe evaluate --mode retrieval --output runs/m6-retrieval.json
.\.venv\Scripts\dealer-evidence.exe evaluate --mode scripted --output runs/m6-scripted.json
# Explicit, billable model execution; NHTSA responses still come from fixtures:
.\.venv\Scripts\dealer-evidence.exe evaluate --mode live-model --env-file .env --output runs/live-development.json
```

All commands default to `--split development`. `--split held_out` is explicit
and reserved for M7. The loader opens only the selected split. The live-model
path requires matching recorded recall fixtures before execution; missing
fixtures never fall back to public HTTP. There is no scripted held-out answer
file. `ask` retains its ordinary live recall behavior.

Retrieval defaults to k=4 in the new command; the older development-only
`eval-retrieval` command retains k=3. Reports include hit@k, all-required-source
coverage, mean document recall, reciprocal rank, forbidden/unauthorized hits,
unknown-identity rejections, per-case results, and corpus/case fingerprints.
Only answerable policy cases enter retrieval-quality denominators. The new
command returns nonzero for missing required sources, permission violations,
or a failed unknown-identity rejection; it does not enforce an aggregate target
by hiding individual misses.

The graph runner executes each case, records the final provider request bodies
in memory, and persists ordinary JSONL traces. It observes retrieved IDs before
the independent context guard. Scoring then checks routes, normalized recall
arguments, dispositions, independently allowed IDs, canonical policy/recall
content, citation membership, required policy evidence, boundary hashes, call
bounds, recall outcomes, and zero network attempts during fixture replay.
Expected labels are used for scoring and fixture preflight, never as model
instructions or retrieval queries. Policy query arguments remain redacted in
the trace/report; recall arguments are available for exact comparison.

The administrator JSON report includes questions, answers, expected semantic
criteria, actual model/provider IDs, run IDs, per-case timing/usage, source-code
and input fingerprints, and the Git dirty flag. Keep these reports under
ignored `runs/`; they are broader than ordinary user-visible traces. Missing
provider usage is an empty object, not a zero-token claim. Setup/persistence
failures abort with an incomplete-run error; unexpected model errors are
retained as failed cases in the denominator.

## What the results mean

| Local development check | Result |
| --- | --- |
| Retrieval hit@4 | 6/6 answerable policy cases |
| All required sources@4 | 6/6 (these development cases each require one source) |
| Mean document recall / reciprocal rank@4 | 1.0 / 1.0 |
| Unauthorized / forbidden retrieved IDs | 0 / 0 across 10 valid-identity searches |
| Unknown identity rejected | 1/1 |
| Scripted graph mechanical checks | 16/16 cases |
| Scripted recall arguments/outcomes | 3/3 each |
| Semantic answer-quality score | Unassigned; 16 manual reviews pending |

`evals/model_replies/development-scripted.json` contains hand-authored fake
provider replies with explicit synthetic provenance. They exercise the real
graph, BM25, fixture replay, citation validation, and trace persistence. Their
16/16 result measures execution of predetermined contracts, **not routing or
answer quality of an actual model**. M4's seven-case live development result
remains separate; M6 did not rerun it.

Manual grading remains required even when every mechanical check passes.
Use the frozen rubric: answerable cases need all required facts, supporting
citations, and no prohibited claims; missing evidence needs an appropriate
abstention; clarification must identify missing details; successful empty
recall responses must preserve their limited scope. Expected service failures
pass only with the correct error disposition; unexpected errors fail. The
runner intentionally leaves `semantic_pass_rate` null rather than substituting
substring checks or an unreviewed model judge.

The frozen 16/24 corpus has no dedicated service-failure category. Supplemental
tests override a development recall response with labeled synthetic empty,
timeout, malformed, and unavailable fixtures, and inject provider failures.
These are separate tests, not additional frozen evaluation cases. Tests also
verify wrong routes/arguments, invalid citations, missing evidence, label
isolation, and scoring a retrieval breach even when the context guard stops it.

## CI and verification

`.github/workflows/ci.yml` runs on pushes and pull requests on Python 3.12,
Ubuntu and Windows. It installs pinned dependencies, checks dependencies,
runs Ruff lint/format, the unchanged normal pytest suite, and both offline
development reports. No provider credentials or live evaluation steps are
configured. An autouse pytest fixture blocks outbound socket connections;
HTTP mocks and recording clients continue to work. Setup downloads Python,
actions, and packages; application checks make no external service calls.

The workflow follows the official [checkout](https://github.com/actions/checkout)
and [setup-python](https://github.com/actions/setup-python) v7 interfaces, with
read-only repository permission and no persisted checkout credentials.
Hosted Actions and Linux execution have **not** been observed locally.

Local verification: 332 tests passed, one existing Windows symlink-permission
skip; Ruff lint/format, lock/dependency checks, and offline package builds passed.
The [regression record](regression-demo.md) establishes the exact committed
passing base, one-line production mutation, intended red assertion, retained
context defense, and cleanup. No test was marked expected-failure for the demo.

Elapsed engineering time was not instrumented. Changes remain local and
uncommitted. Next: M7 configuration freeze, held-out retrieval/live-model
evaluation with manual grading, release review, and separately authorized
publication/demo CI evidence.
