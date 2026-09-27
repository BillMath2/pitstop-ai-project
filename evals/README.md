# Frozen M1 evaluation fixtures

These are synthetic inputs and expected behaviors, not recorded agent results.
The manifest binds them to the exact corpus content and metadata fingerprint.
All policy facts are fictional. Recall cases here assert routing/argument behavior
only. M3 response/error fixtures live separately under `data/recalls/v1/`; they do
not change this frozen split or provide final agent-answer quality scores.

## Split discipline

- `development.jsonl`: 16 cases for M2 retrieval and later prompt development.
- `held_out.jsonl`: 24 cases reserved for final evaluation after decisions freeze.
- `manifest.json`: schema version, corpus fingerprint, split paths/counts/hashes.

Default validation opens only the development file. Normal unit tests must not
read real held-out questions or expected answers. To perform an explicit
authoring/release integrity check, use:

```powershell
.\.venv\Scripts\dealer-evidence.exe validate-evals --include-held-out
```

This checks fixture structure and integrity, not answer quality. No model or
data-tool calls occur. Do not use held-out cases or results to adjust retrieval,
prompts, thresholds, or expected answers to match observed behavior. If a holdout
is used for tuning, label it as development and author a new untouched holdout
before reporting final quality. Record deliberate corpus/fixture revisions as a
new baseline; do not silently update hashes to make validation pass.

The authoring process necessarily saw all cases; M1 has no ranking or prompts
to optimize. Future development should open only the development file. Because
the repository is public demo material, separation is procedural, not secrecy.

## Case schema and future scoring

Each JSONL line has `case_id`, `split`, `category`, `identity`, `query`, and
`expected`. Identity is request context; words inside the query cannot override it.
The `expected` object contains:

| Field | Meaning |
| --- | --- |
| `route` | `search_policies`, `lookup_recalls`, or `none` before clarification/rejection |
| `outcome` | `answer`, `abstain`, `lookup`, `clarify`, or `reject` |
| `document_ids` | Required supporting policy documents for a policy answer |
| `forbidden_document_ids` | Restricted evidence that must not reach results, snippets, context, or citations |
| `required_facts` | Semantic assertions the response/action must satisfy; not exact string matching |
| `forbidden_claims` | Claims or behaviors that cause failure even if required facts appear |
| `tool_arguments` | Exact recall make/model/year; empty for other categories |

For policy cases, the required documents must support the response; additional
authorized, relevant citations are allowed. For abstentions, empty document IDs
mean there is no required answering evidence, not a ban on citing an authorized
policy that explains a limitation. Permission denials must not confirm private
facts guessed in a question or leak them through paraphrases or encodings.

The M6 runner keeps expected labels out of model instructions and retrieval inputs,
verify route/outcome and citations, and assess the semantic assertions separately.
Measure unauthorized evidence in intermediate retrieval/model context as well
as the final answer. Unknown identities must be rejected before either a model
or data-tool call. `none` means no data tool is appropriate for clarification;
it does not forbid a model from asking the clarification question.

Recall `lookup` cases stop at routing and arguments in M1. M3 supplies separately
versioned response fixtures and error/empty-result checks; M4 must verify answers
against those responses before reporting end-to-end recall quality. No recall
result, VIN eligibility, repair completion, or safety conclusion may be invented.

Report development and held-out metrics separately, with corpus and case hashes,
and distinguish structural fixture validation from executed evaluation results.

## M2 retrieval evaluation

`dealer-evidence eval-retrieval` runs development-only retrieval checks. It has
no held-out option. Six policy cases contribute to mean document recall@k and
mean reciprocal rank@k; all policy, permission, and missing-evidence searches
are checked for unauthorized and explicitly forbidden document hits. The unknown
identity case checks rejection. The three recall and two clarification cases are
skipped by that runner because it measures policy retrieval only. M3 tests
validate the three development recall argument sets against recorded fixtures.
M6 adds a separate executed graph runner, described below.

Expected IDs are used only after search to score results; they are never query
inputs. Missing-evidence and permission cases may return authorized lexical
matches, so this runner does not score their final abstention behavior. Nor does
document recall establish that a bounded excerpt includes every required fact.
Intermediate authorization isolation is covered by separate unit tests.
The JSON report records the corpus hash, development-file hash, retrieval
version, k, per-case results, and aggregate metrics.

## M6 executed reports

`dealer-evidence evaluate --mode retrieval` defaults to k=4 and development.
`--mode scripted` uses the explicitly synthetic provider replies under
`model_replies/`, executes the graph with recorded recalls, and checks observed
routes, arguments, dispositions, evidence, citations, call bounds, and traces.
This is contract execution coverage, not a model-quality score. Scripted
replies are separate from the immutable expected-label files and are never
substituted into a live-model run.

`--mode live-model` explicitly calls the pinned model with fixture-only recalls.
Both modes leave semantic grading pending against `required_facts` and
`forbidden_claims`. Unknown-identity and unexpected-error cases remain in the
denominator. `--split held_out` is an explicit M7 operation; neither CI nor
normal tests open the real held-out file. Synthetic unit-test splits verify
the selection mechanism. Reports under ignored `runs/` are administrator
artifacts; review before sharing. See [M6 decisions](../docs/m6-decisions.md).
