# Data provenance and identity limits

## Synthetic corpus

The 24 Markdown policies in `data/corpus/` were newly authored for this personal
project on 2026-09-26. Cedar Junction Motors is fictional. Procedures, contacts,
and the $180 goodwill amount are invented, not statements about any employer,
manufacturer, or real dealership. No internal source code, transcripts, policy
documents, fixtures, or results were used as implementation templates.

The manifest assigns stable IDs, versions, paths, and one of two visibility
labels: 16 shared and 8 manager-only. Paths are relative to its adjacent `corpus/`
directory. The version 2 manifest binds each policy to a SHA-256 text fingerprint
and the complete corpus to a metadata/content fingerprint. M1 validates these
before reporting success and implements an identity-scoped access layer.

## Identity boundary

The implemented fixed mapping is `tech_demo` -> `technician` and
`manager_demo` -> `manager`. Technicians may retrieve `shared` policies;
managers may retrieve both `shared` and `manager_only` policies. Unknown
identities fail closed. Listing enforces this mapping now; future retrieval must
filter documents before indexing, scoring, snippets, or model context.

These are simulated identities selected by the person running a local CLI.
The repository's synthetic files remain readable on disk. This demonstrates
application authorization behavior, not login, tenant isolation, or production
security. The local application and manifest are trusted; questions, retrieved
text, model output, and future API responses are untrusted.

## Future recall data

No NHTSA responses have been collected yet. M3 will capture public recall
responses with source URLs, query fields, UTC capture times, and fingerprints.
Synthetic error fixtures will be labeled separately. Recorded fixtures will
never be presented as live results. Reference:
[NHTSA datasets and APIs](https://www.nhtsa.gov/nhtsa-datasets-and-apis).

## Evaluation fixtures

The 40 cases in `evals/` are newly authored synthetic questions and expected
behaviors. They are frozen against the M1 corpus, with 16 development cases and
24 held-out cases in separate files. Recall queries use example vehicle fields
but assert no real campaigns, recall counts, eligibility, or repair status.
M1 validates routing expectations and fixture integrity, not API responses.
See [the fixture contract](../evals/README.md) for isolation and scoring rules.

## Results and licenses

There are no agent-quality or held-out evaluation results at M1. Installation
and offline validation are engineering checks, not evidence of model quality.
Dependency versions and license references are recorded in `m0-decisions.md`.
Choose a license for the new project before public release; installing an
open-source dependency does not choose a license for the application itself.
