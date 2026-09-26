# Dealer Evidence Agent

A Python portfolio project for a fictional dealership: a bounded LangGraph agent
that will choose between permission-aware policy search and public NHTSA recall
lookup, then answer with evidence or explain what is missing.

**Current status: M0 scaffold.** Package installation, CLI help, and validation of
two fictional starter policies work. Search, recall lookup, model routing,
request traces, and evaluations are planned; they are not implemented yet.

## Quick start

Requires Python 3.12 and an initial network connection to install dependencies.
Run these commands from the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -c requirements.lock
.\.venv\Scripts\dealer-evidence.exe --help
.\.venv\Scripts\dealer-evidence.exe validate-corpus
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
in the repository, rather than being embedded in the Python wheel.

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
model request boundary, offline evaluation fixtures, and a deliberately broken
authorization change that fails unchanged tests in CI. Those are later milestones.

## Demo boundaries

`tech_demo` will map to `technician` and `manager_demo` to `manager`. Shared
policies will be available to both; manager-only policies only to managers.
These are selectable local test identities, **not authentication**. Anyone with
the repository can read the fictional policies. M0 validates visibility labels;
it does not yet implement role-based retrieval.

Policies, amounts, and procedures are invented for this project. Future NHTSA
year/make/model results will describe general recall records, not VIN-specific
repair status or proof that a vehicle is safe. This is a new personal project,
written independently from public documentation and its own requirements.

See [data provenance](docs/data-provenance.md),
[the intended public file set](docs/public-files.md), and
[M0 decisions and verification](docs/m0-decisions.md).
