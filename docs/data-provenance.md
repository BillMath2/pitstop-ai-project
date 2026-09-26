# Data provenance and identity limits

## Starter corpus

The two Markdown policies in `data/corpus/` were newly authored for this personal
project on 2026-09-26. Cedar Junction Motors is fictional. Procedures, contacts,
and the $180 goodwill amount are invented, not statements about any employer,
manufacturer, or real dealership. No internal source code, transcripts, policy
documents, fixtures, or results were used as implementation templates.

The manifest assigns stable IDs, versions, paths, and one of two visibility
labels. Paths are relative to its adjacent `corpus/` directory. M0 checks the
complete manifest and reads UTF-8 files before reporting success. M1 will add
the remaining 22 documents, corpus fingerprints, and permission enforcement.

## Identity boundary

The planned fixed mapping is `tech_demo` -> `technician` and
`manager_demo` -> `manager`. Technicians may retrieve `shared` policies;
managers may retrieve both `shared` and `manager_only` policies. Unknown
identities will fail closed. M0 does not yet implement this mapping.

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

## Results and licenses

There are no agent-quality or held-out evaluation results at M0. Installation
and offline validation are engineering checks, not evidence of model quality.
Dependency versions and license references are recorded in `m0-decisions.md`.
Choose a license for the new project before public release; installing an
open-source dependency does not choose a license for the application itself.
