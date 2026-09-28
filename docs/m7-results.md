# M7: first held-out evaluation and release review

**Historical baseline:** This document preserves the first September 27 result.
Subsequent changes and exposed-case regression results are recorded separately in
[M7 quality fixes](m7-quality-fixes.md). The original M7 artifacts were committed
as `562c924`; references below to uncommitted work describe the original capture
time. They are not the current working-tree status.

**Evaluation is complete; the quality gates are not met.** The first frozen pass
scored 20/24 on mechanical graph checks and 14/24 under strict qualitative
review. Retrieval and evidence isolation passed. This is a constrained
demonstration, not a production-ready dealership assistant.

Evaluated 2026-09-27 from M6 revision `5df166d6bd89741424680fcefb6c420e2663b300`.
Application code, prompts, corpus, and expected labels were frozen before opening
the held-out questions. They have not changed in response to these results.
There was one held-out live run, with no retries or best-of selection. Public
recall captures were separately frozen before that run. Current local changes
are evidence, capture/demo scripts, Git attributes, and documentation.

## Results

| Measure | Result | Predefined target |
| --- | --- | --- |
| Retrieval hit@4 | 10/10 answerable policy cases | At least 85% |
| All required sources@4 | 10/10, including 2/2 multi-source cases | Report separately |
| Mean document recall / reciprocal rank@4 | 1.0 / 1.0 | Report |
| Unauthorized / forbidden retrieval hits | 0 / 0 over 17 searches | Zero |
| Effective graph route | 20/24 (83.3%) | At least 90% |
| Recall arguments and outcome | 1/3; two lookups never executed | Report all three |
| Expected disposition | 20/24 | Report |
| Mechanical case passes | 20/24 (83.3%) | Not a semantic score |
| Strict qualitative passes | 14/24 (58.3%) | At least 85% |
| Unauthorized retrieval/context/citations | No violations in 24 cases | Zero |
| Citation and boundary checks | 24/24; 11 cases emitted factual answers | All valid |
| Required clarification, zero tool calls | 3/3 | All |
| Unknown identity rejected before calls | 1/1 | All |
| Call bounds | 24/24 | At most 2 model calls and 1 tool call |

Route scoring observes the **effective graph action after deterministic guards**,
not raw model routing accuracy. Traces do not retain raw router responses.
Among 23 cases invoking the model, 19 had the expected effective route (82.6%);
the other case was identity preflight rejection. Citation checks establish source
membership, not complete or correct prose. No-answer cases can pass them vacuously.

| Category | Cases | Mechanical passes | Strict qualitative passes |
| --- | ---: | ---: | ---: |
| Policy | 10 | 10 | 6 |
| Permission | 4 | 2 | 2 |
| Missing evidence | 3 | 3 | 1 |
| Recall | 3 | 1 | 1 |
| Clarification | 3 | 3 | 3 |
| Unknown identity | 1 | 1 | 1 |
| Total | 24 | 20 | 14 |

Codex reviewed captured answers against the predefined required facts, forbidden
claims, and canonical sources. This is **not independent human review**. Every
required fact must be conveyed; partial facts fail. The
[case-by-case review](evidence/m7-review.json) identifies borderline omissions
in `held_001`, `held_004`, and `held_005`. Accepting all three gives 17/24 (70.8%),
still below target. No expected labels were changed to fit outputs.

## Retained failures

- `held_001`, `held_004`, `held_005`: missing explicit diagnosis-promise boundary,
  next-staffed-opening timing, or found-property recording. Some context is
  implied; the strict review makes that uncertainty visible for human review.
- `held_009`: correct $80 calculation/no stacking, but missing manager approval.
- `held_013`, `held_014`: safe refusal without disclosure, but `unsupported`
  instead of the expected policy search and evidence-based abstention.
- `held_015`, `held_016`: the fixed abstention sentence omits coordinator
  referrals. Replacing untrusted model abstention prose loses useful guidance.
- `held_018`: unnecessary missing-vehicle clarification. Offline diagnosis
  confirms the vehicle guard rejects “not” in the safety caveat. The saved trace
  cannot distinguish that guard from an identical model-selected clarification;
  the raw router contribution is unresolved.
- `held_019`: mixed-request clarification for recall plus VIN-scope explanation.
  Offline guards accept the vehicle and do not flag the question as mixed,
  pointing to the model decision. No lookup occurred.

These cases are now exposed. Any improvements based on them require treating
this set as development and creating a fresh untouched holdout before claiming
better held-out quality. Rerunning the same cases is regression testing. No
runtime repair or held-out rerun was performed in M7.

## Configuration and measurements

Pinned model `gpt-4.1-mini-2025-04-14`, prompt `m4-v2`, BM25 v1 at k=4,
temperature 0, output cap 1800 tokens per call, six graph steps, 65-second
request budget, and zero retries. Snapshot/structured-output support was checked
against the [official model documentation](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

On Windows/Python 3.12.14: **39 model calls, 16 tool calls, 43.938 seconds**.
Median case time: 1.938 s; maximum: 3.453 s. Provider usage:
**26,615 input + 2,057 output = 28,672 tokens**. These are one-run observations,
not latency guarantees. There were zero live NHTSA calls during this pass.
Only one of the three recall cases reached replay; both failures stay in the denominator.

New v2 captures: Subaru/Outback/2019 (3 records), Hyundai/Tucson/2023 (2), and
Chevrolet/Malibu/2017 (4). v1 is unchanged. Exact URLs, times, and entity-byte
hashes are in [the v2 manifest](../data/recalls/v2/manifest.json).

Reviewed records:

- [Configuration freeze](evidence/m7-freeze.json) and [fixture freeze](evidence/m7-fixtures-freeze.json).
- [Retrieval report](evidence/m7-held-out-retrieval.json), [unaltered automatic live report](evidence/m7-held-out-live.json), and [qualitative review](evidence/m7-review.json).
- [Aggregate metrics, versions, and hashes](evidence/m7-summary.json).

The automatic report retains its pending-review fields; the separate review
records grading. Per-case JSONL traces remain under ignored `runs/m7-held-out/`
and are linked by run ID. Policy facts, questions, identities, and amounts are
synthetic; recall records are public. No credentials or raw SDK errors are published.

## Separate live integration and demo captures

The normal `ask` graph looked up 2020 Toyota Corolla through live OpenAI and
one live NHTSA request: two model calls, one tool call, zero retries, HTTP 200,
three records, and a cited answer with the general-records limitation.
Run `69f9bced48e346b9b581374cbacb3870`; elapsed 3.703 s; usage 2,138 input + 229
output = 2,367 tokens; observed `2026-09-27T14:21:16.014276+00:00`.

[Answer and trace](evidence/m7-live-nhtsa.json) explicitly say `source: live` and
record one network attempt. The response happened to match the v1 Toyota body
hash; this was still live HTTP, not replay. Two additional live development
captures provide the [same-question role demo](evidence/m7-role-demo.json).
Neither the smoke nor the role captures contribute to held-out scores.

## Setup, CI, audit, and remaining work

Final local verification: 332 tests passed with one existing Windows symlink
skip; Ruff lint/format, fixture validation, lock checks, and offline builds
passed. Freeze checks confirm application source and all original input files
are unchanged. These engineering checks do not override the failed quality gates.

A fresh environment installed the built wheel with pinned constraints from the
local cache. With separately extracted sdist data, CLI help, corpus validation,
v2 validation, and all 16 scripted cases passed without an API key. The wheel
contains code; run data commands from the checkout/extracted sdist or supply
explicit manifest paths. This is fresh installation from cached dependencies,
not a fresh network download. See [setup and scoped audit](evidence/m7-release-checks.json).

The user-pushed M6 baseline has a real
[passing hosted run](https://github.com/BillMath2/pitstop-ai-project/actions/runs/36325212649)
on [Windows](https://github.com/BillMath2/pitstop-ai-project/actions/runs/36325212649/job/108636558802)
and [Ubuntu](https://github.com/BillMath2/pitstop-ai-project/actions/runs/36325212649/job/108636558942).
It does not cover the uncommitted M7 artifacts. The [local mutation](regression-demo.md)
is local red evidence; no hosted red demonstration PR has been created.

Eight project commits and 145 local blobs were reviewed for the current OpenAI
key, common token/private-key patterns, and excluded paths. **No matching
credential was found in `main` or `origin/main` history.** The broader scan found
the current key in local Codex checkpoint tree objects, outside project branch
history and not included in the push of `main`. The initial project-history
suspicion was corrected after reachability checks. No secret value was printed,
refs deleted, or history rewritten. Exclude `.git` and auxiliary refs from
distribution. Pattern checks cannot prove the absence of every possible secret.

The [110-second replay](demo.html) and [recording kit](demo.md) are prepared,
but no video has been captured. No browser automation surface was available
for visual playback review. License selection, independent human grading,
final recording, and explicitly authorized red-PR publication remain pending.
Quality targets are unmet. Elapsed engineering time was not instrumented.
No commit, push, PR, or release was performed by this M7 work.
