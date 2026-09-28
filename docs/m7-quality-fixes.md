# M7 quality repairs and exposed-case regression

September 28, 2026. These changes address the failures recorded in the
[original M7 review](m7-results.md), starting from commit `562c924`.
The original reports, policy corpus, expected labels, and recall captures are
unchanged. The old `held_out` filename now denotes **exposed regression cases**:
these results cannot establish performance on unseen questions.

## What changed

- Policy answers select canonical source sentence indices across records, timing,
  approvals/handling, follow-up, and limits. Code validates and inserts those
  sentences with source IDs. This makes omitted operational requirements visible
  in the complete answer, including manager approval, initial found-property
  records, and next-staffed-opening timing.
- Abstentions discard model-authored prose, retain only verified source quotations,
  and preserve coordinator contact instructions from cited, authorized policies.
  A fixed service-desk/manager-review suggestion supplies a human next step without
  asserting approval or changing access. A coordinator suggestion does not assert
  that the coordinator has authority to approve unknown terms.
- Explicitly private policy-term requests from technicians conservatively abstain
  after permission-scoped search. This prevents substituting a shared intake
  deadline for a private manager-review deadline. Identity and access remain
  enforced independently of the question or model.
- Routing instructions distinguish policy plus recalls from a recall lookup plus
  an explanation of its limits. A narrow routing-only normalizer separates a
  terminal repair-completion follow-up. Full question text remains available to
  argument/ambiguity guards and answer composition; no vehicle values are inferred.
- The explicit-vehicle guard recognizes negated inference language such as
  “do not assume” while preserving checks for vehicle negations and alternatives.
- Recall composition has its own schema. Policy sentence-selection fields do not
  burden recall responses. Recorded evidence retains its source and scope labels.
- Additive trace events distinguish proposed model routes from code overrides and
  record restricted-scope abstentions without storing questions or model prose.

The pinned model remains `gpt-4.1-mini-2025-04-14`; prompt/schema version is
`m7-v13`. Limits remain two model calls, one tool call, zero retries, four policies,
five recall campaigns, and a 65-second request budget. Prompt changes follow the
specific-instruction and evaluation approach described in the
[OpenAI GPT-4.1 guide](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-4.1).

## Validation

Final verification: **389 offline tests passed, one existing Windows skip**;
Ruff lint and formatting passed. After the final prompt-only revision, the 140
graph, model-boundary, and quality-regression tests passed again. There are 57 new
offline regression cases. Mechanical checks and qualitative review are separate.
Semantic review evaluates the entire
rendered answer, including code-inserted quotations, against the original required
facts, prohibited claims, and canonical policies. Codex review is not independent
human review.

| Final m7-v13 run | Mechanical | Codex qualitative | Provider tokens | Elapsed |
| --- | ---: | ---: | ---: | ---: |
| Exposed M7 cases | 24/24 | 24/24 | 70,013 | 61.6 s |
| Development cases | 16/16 | 16/16 | 41,544 | 35.4 s |

The runs used live OpenAI with recorded recall responses, not live NHTSA. Every
case respected the two-model/one-tool bounds, including clarification and identity
rejections. No unauthorized evidence or citations were observed.

- [Final M7 regression report](evidence/m7-quality-regression.json)
- [Final development report](evidence/m7-quality-development.json)
- [Case-by-case qualitative review](evidence/m7-quality-review.json)
- [All 22 attempts, hashes, usage, and observed failures](evidence/m7-quality-iterations.json)

Raw final reports retain their original `quality_review: pending` marker; the
linked review records the subsequent grading without rewriting captured output.
Reports include the uncommitted source fingerprint and original evaluation/corpus
hashes. Per-case raw traces remain in the ignored local run directories.

| Prompt version | Exposed M7 mechanical | Development mechanical |
| --- | ---: | ---: |
| m7-v3 | 22/24 (separate sandbox connection failure: 1/24) | Not run |
| m7-v4 | 24/24 | 15/16 |
| m7-v5 | 20/24 | 14/16 |
| m7-v6 | 21/24 | 16/16 |
| m7-v7 | 21/24 | 16/16 |
| m7-v8 | 23/24 | 15/16 |
| m7-v9 | 23/24 | 16/16 |
| m7-v10 | 24/24 | 16/16 |
| m7-v11 | 24/24 | 15/16 |
| m7-v12 | 24/24 | 16/16 |
| m7-v13 (final) | 24/24 | 16/16 |

All live development attempts are retained locally under ignored `runs/` folders.
The iteration summary preserves failed attempts as well as the final run;
this is iterative development on exposed questions, not best-of held-out scoring.
Notable intermediate failures included sentence-selection validation, omitted
referrals, overly broad status correction, shared/private deadline confusion,
and intermittent repair-completion routing. Manual review of m7-v12 also caught
an unrelated warranty referral and an unsupported exception-approval paraphrase
despite perfect mechanical scores. The final prompt tightens source relevance and
keeps free-form policy responses to two sentences; the final review checked both
corrections. The initial sandboxed attempt failed
provider connections and is not evidence about model quality.

## Reproduce

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .

# These call OpenAI using your local credentials and incur API usage.
# Recalls use recorded fixtures; these commands do not contact NHTSA.
.\.venv\Scripts\python.exe scripts/m7_quality_regression.py --live --env-file .env
.\.venv\Scripts\python.exe scripts/m7_quality_regression.py --live --env-file .env --split development
```

Each live invocation creates a new report and per-case traces. No expected labels
are supplied to the model. Reports mark `fresh_holdout: false`, and automatic
passes do not substitute for reading the answers. The script returns nonzero when
any mechanical case fails.

## Limits and remaining M7 work

Canonical quotations prevent fabricated quotation text; they do not prove that
the model selected every relevant sentence or correctly interpreted it in its
free-form introduction. The corpus sentence splitter and language guards are
conservative heuristics for this small demonstration, not universal language
understanding. Model behavior can vary between identical runs, even at temperature
zero. Longer answers trade brevity for explicit operational coverage.

Create and freeze a **new untouched holdout**, then obtain independent human review
before claiming an improved held-out quality score. The original M7 quality gate
is not retroactively passed. License selection, the hosted red-PR demonstration,
and the final video remain separate release work. These repairs do not establish
production readiness, live VIN status, or authentication of the selectable demo
identities.
