# M1: corpus, permissions, and evaluation fixtures

Implementation date: 2026-09-26. Scope: 24 fictional policies, reproducible
fingerprints, a two-role access layer, and 40 frozen evaluation cases.

## Corpus and permission matrix

The two M0 starter documents retain their IDs, versions, and content. M1 adds
22 policies covering service intake, estimates, communication, transportation,
records, complaints, warranty/recall boundaries, and manager approvals.
All limits and procedures are invented. They are not repair or safety guidance.

| Identity | Role | Shared policies | Manager-only policies | Total visible |
| --- | --- | --- | --- | --- |
| `tech_demo` | `technician` | 16 | 0 | 16 |
| `manager_demo` | `manager` | 16 | 8 | 24 |
| Any other value | None | 0 | 0 | 0 |

`permissions.py` owns the fixed, immutable identity/visibility mappings.
`authorized_documents()` rejects unknown identities even for an empty corpus.
Identity matching is exact; claims in question text or policy text cannot grant
a role. `list-policies --identity ...` resolves identity before loading documents
and prints only authorized IDs and titles. The corpus loader is a trusted
administrative operation, not a public retrieval API.

M2 must construct its retrieval index from `authorized_documents()` before
scoring, producing snippets, or passing context to a model. Filtering only final
results is insufficient. Direct filesystem access remains outside this demo's
authorization boundary; these identities are not authentication.

## Fingerprint contract

`data/manifest.json` uses schema version 2; version 1 manifests are intentionally
rejected because they have no integrity fields. Each entry carries a lowercase
SHA-256 of its UTF-8 text after CRLF and CR become LF. All other whitespace and
Unicode characters remain significant. This makes ordinary Windows/Git newline
conversion portable without hiding substantive edits.

The corpus hash is SHA-256 of canonical JSON: document records sorted by
`doc_id`, keys sorted, compact separators, and `ensure_ascii=False`. Each record
contains ID, title, relative path, visibility, version, and text hash. Thus a
permission-label change invalidates the corpus hash as well as a content change.
Manifest entry order has no effect. `corpus_fingerprint()` defines this contract.

The evaluation manifest pins the corpus hash and each split's normalized-text
hash. These are reproducibility checks, not signatures: someone who can edit
files can replace their hashes too. The repository and manifests are trusted.

To revise a policy deliberately, review its version and metadata, recompute the
entry hash with `text_fingerprint()`, and recompute the corpus hash from the
updated `PolicyDocument` records. Re-author/review affected fixture expectations
and record a new evaluation baseline before updating their manifest hashes.
Validation never silently regenerates hashes or accepts a changed baseline.

## Evaluation boundary

Cases are authored before retrieval or prompt implementation. The split is
fixed, with no runtime shuffle. It is a small handcrafted, stratified demo set,
not a statistically representative sample or proof of generalization.

| Category | Development | Held out |
| --- | --- | --- |
| Policy answers | 6 | 10 |
| Permission denials (including injection attempts) | 2 | 4 |
| Missing evidence | 2 | 3 |
| Complete recall lookup requests | 3 | 3 |
| Requests needing clarification | 2 | 3 |
| Unknown identity rejection | 1 | 1 |
| **Total** | **16** | **24** |

`validate-evals` loads only development cases by default. Regular tests use
development and temporary synthetic cases, never the real held-out file.
`--include-held-out` is an explicit structural authoring/release check, which
checks counts, schemas, permissions, unique cases, evidence IDs, and hashes.
It prints no case questions, expected answers, or model scores.

Do not tune ranking, prompts, or thresholds against held-out questions or
results. Full structural validation during M1 authoring is not model evaluation.
The next milestone is M2: implement permission-scoped BM25 retrieval using the
development split. See [the fixture contract](../evals/README.md) for future
runner requirements and how to handle an exposed or revised holdout.

## Verification

- Corpus validation: 24 documents, 16 shared and 8 manager-only.
- Role listings: 16 for `tech_demo`, 24 for `manager_demo`; unknown identities
  rejected before corpus loading.
- Both fixture splits pass the explicit authoring integrity check: 40 cases.
- Offline tests: **71 passed, 1 skipped**. The skipped symlink-escape test still
  requires Windows symlink creation permission. Fingerprint drift, metadata
  drift, role filtering, default holdout isolation, and invalid fixtures are tested.
- Ruff lint and formatting passed; the existing dependency lock is current and
  installed dependencies are compatible.
- Wheel and source distribution built offline. Archive inspection confirmed all
  24 policies and four evaluation files in the source distribution, both new
  Python modules in the wheel, and no credentials, local runtimes, or caches.

No agent, retrieval, recall service, or model-quality evaluation runs in M1.
