# Dealer Evidence Agent

A Python portfolio project for a fictional dealership: a bounded LangGraph agent
that will choose between permission-aware policy search and public NHTSA recall
lookup, then answer with evidence or explain what is missing.

**Current status: M2 permission-scoped retrieval.** The offline CLI searches the
24 fictional policies with BM25, enforcing demo permissions before indexing and
returning source excerpts with fingerprints. Corpus/fixture validation and a
development-only retrieval evaluation also work. Recall lookup, model routing,
request traces, and end-to-end answer evaluation are still planned.

## Quick start

Requires Python 3.12 and an initial network connection to install dependencies.
Run these commands from the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -c requirements.lock
.\.venv\Scripts\dealer-evidence.exe --help
.\.venv\Scripts\dealer-evidence.exe validate-corpus
.\.venv\Scripts\dealer-evidence.exe list-policies --identity tech_demo
.\.venv\Scripts\dealer-evidence.exe validate-evals
.\.venv\Scripts\dealer-evidence.exe search-policies "loaner return missing keys" --identity tech_demo
.\.venv\Scripts\dealer-evidence.exe eval-retrieval
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

If you use [uv](https://docs.astral.sh/uv/getting-started/installation/),
`uv sync --locked` installs Python 3.12 when needed and creates `.venv` with the
locked dependencies. Then use the same executable paths above, or
`uv run --locked dealer-evidence validate-corpus`.

No credentials or external service calls are needed for the current CLI or tests.
The default manifest is `data/manifest.json`, relative to the working directory;
use `validate-corpus --manifest PATH` to validate another corpus. Policy paths
are relative to the `corpus/` directory next to that manifest. The corpus stays
in the repository, rather than being embedded in the Python wheel. Evaluation
fixtures likewise stay in `evals/`. `validate-evals` checks only the development
set by default. An explicit `--include-held-out` validates both splits for
authoring/release integrity; it does not run an agent or measure answer quality.
See [M1 decisions](docs/m1-decisions.md) and the [fixture contract](evals/README.md).

## Policy search

```powershell
.\.venv\Scripts\dealer-evidence.exe search-policies "goodwill credit" --identity manager_demo --json
```

Search returns up to three authorized policies by default (`--top-k` accepts
1 through 5), with each excerpt limited to 480 characters. JSON output includes
document IDs, relative source paths, versions, text hashes, source line/character
offsets, raw BM25 scores, and the authorized corpus fingerprint. Character offsets
are zero-based and end-exclusive; line numbers are one-based and inclusive.

Results are evidence candidates, not generated answers. A lexical match does
not establish that a policy supports the requested fact, and a snippet may omit
an exception elsewhere in the document. `no_match` means no indexed term overlap,
not proof that a policy does not exist. Scores are not probabilities and are not
comparable across role scopes. Unknown identities and invalid arguments fail
with an error; a valid search without matches succeeds with an empty result.

`eval-retrieval` reads only the development fixtures and reports retrieval metrics
as JSON. The six policy-answer cases all retrieved their expected document at
rank 1 in the M2 baseline. Permission checks returned no restricted evidence.
These are development results, not held-out, answer-quality, or routing results.
See [M2 decisions and verification](docs/m2-decisions.md).

## Planned agent behavior

The model will select `search_policies(query)` or
`lookup_recalls(make, model, year)`, or request clarification. Code will validate
arguments, enforce permissions, and verify evidence and citations. Each request
will allow at most two logical model calls and one logical data-tool call.

The initial model choice is OpenAI `gpt-4.1-mini-2025-04-14`, with the OpenAI SDK
and strict function schemas. Its documented support is recorded in
[M0 decisions](docs/m0-decisions.md); live account access has not been tested.
`.env.example` lists future configuration placeholders. The current CLI does
not load `.env`, use API keys, or silently fall back to another model.

The completed demo will add JSONL traces at the model request boundary,
end-to-end evaluation execution, and a deliberately broken
authorization change that fails unchanged tests in CI. Those are later milestones.

## Demo boundaries

`tech_demo` maps to `technician` and `manager_demo` to `manager`. The access layer
and search/list commands expose 16 shared policies to technicians and all 24 to
managers. Unknown identities fail closed, including case or whitespace variants.
These are selectable local test identities, **not authentication**. Anyone with
the repository can read the fictional policies. Retrieval uses the authorized
document set before tokenization, indexing, scoring, or generating snippets.

Policies, amounts, and procedures are invented for this project. Future NHTSA
year/make/model results will describe general recall records, not VIN-specific
repair status or proof that a vehicle is safe. This is a new personal project,
written independently from public documentation and its own requirements.

See [data provenance](docs/data-provenance.md),
[the intended public file set](docs/public-files.md),
[M0 decisions and verification](docs/m0-decisions.md),
[M1 decisions and verification](docs/m1-decisions.md), and
[M2 decisions and verification](docs/m2-decisions.md).
