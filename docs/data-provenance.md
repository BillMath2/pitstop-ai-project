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
identities fail closed. Listing and M2 retrieval enforce this mapping. Search
filters before tokenization, indexing, scoring, or snippets; a future model must
receive only that authorized evidence.

These are simulated identities selected by the person running a local CLI.
The repository's synthetic files remain readable on disk. This demonstrates
application authorization behavior, not login, tenant isolation, or production
security. The local application and manifest are trusted; questions, retrieved
text, model output, and future API responses are untrusted.

## Public recall data

M3 captured three public NHTSA year/make/model responses for the existing
development cases. `data/recalls/v1/manifest.json` records source URLs, query
fields, UTC capture times, HTTP metadata, and exact response-byte fingerprints.
The local capture date was 2026-09-26 (2026-09-27 UTC). Six synthetic fixtures
cover empty, malformed, HTTP failure, timeout, and network-error responses.
Synthetic data has no claimed capture time. Recorded fixtures are always labeled
as offline replay; raw bytes are preserved with Git attributes. Reference:
[NHTSA datasets and APIs](https://www.nhtsa.gov/nhtsa-datasets-and-apis).

## Evaluation fixtures

The 40 cases in `evals/` are newly authored synthetic questions and expected
behaviors. They are frozen against the M1 corpus, with 16 development cases and
24 held-out cases in separate files. The M1 recall cases specify example vehicle
fields and routing expectations; they remain unchanged. M3 adds independently
versioned response/error fixtures under `data/recalls/`, not held-out answers.
These do not establish individual eligibility or repair status.
See [the fixture contract](../evals/README.md) for isolation and scoring rules.

## Results and licenses

M2 has development-only retrieval metrics; M3 has live tool smoke verification
and offline response-contract checks. There are no agent-answer-quality or
held-out evaluation results. These engineering checks are not evidence of model
answer quality.
Dependency versions and license references are recorded in `m0-decisions.md`.
Choose a license for the new project before public release; installing an
open-source dependency does not choose a license for the application itself.
