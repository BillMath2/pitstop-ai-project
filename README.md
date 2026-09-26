# Dealer Evidence Agent

A Python portfolio project for a fictional dealership: a bounded LangGraph agent
that will choose between permission-aware policy search and public NHTSA recall
lookup, then answer with evidence or explain what is missing.

**Current status: M1 corpus and evaluation fixtures.** The offline CLI validates
24 fictional policies and their fingerprints, lists policies by demo identity,
and validates a frozen 16/24 development/held-out case split. Search, recall
lookup, model routing, request traces, and evaluation execution are still planned.

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

The completed demo will include role-scoped BM25 retrieval, JSONL traces at the
model request boundary, evaluation execution, and a deliberately broken
authorization change that fails unchanged tests in CI. Those are later milestones.

## Demo boundaries

`tech_demo` maps to `technician` and `manager_demo` to `manager`. The access layer
and `list-policies` expose 16 shared policies to technicians and all 24 to
managers. Unknown identities fail closed, including case or whitespace variants.
These are selectable local test identities, **not authentication**. Anyone with
the repository can read the fictional policies. M2 retrieval must use the
authorized document set before building an index or generating snippets.

Policies, amounts, and procedures are invented for this project. Future NHTSA
year/make/model results will describe general recall records, not VIN-specific
repair status or proof that a vehicle is safe. This is a new personal project,
written independently from public documentation and its own requirements.

See [data provenance](docs/data-provenance.md),
[the intended public file set](docs/public-files.md), and
[M0 decisions and verification](docs/m0-decisions.md), and
[M1 decisions and verification](docs/m1-decisions.md).
