# Dealer Evidence Agent

A Python portfolio project for a fictional dealership: a bounded LangGraph agent
that chooses between permission-aware policy search and public NHTSA recall
lookup, then answers with evidence or explains what is missing.

**Current status: M5 complete; M6 evaluation and CI are next.** The `ask` CLI
runs a bounded LangGraph route/tool/answer flow with permission-scoped policy
search, public NHTSA recall lookup, typed citations, and model-boundary trace hooks.
Offline validation passes 317 tests (one existing skip), and all seven cases in
M4's final live OpenAI development smoke pass manual review. The initial routing
failures and their fix are preserved in [live results](docs/m4-live-development.md) and
[M4 decisions and remaining work](docs/m4-decisions.md).

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
.\.venv\Scripts\dealer-evidence.exe validate-recall-fixtures
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

If you use [uv](https://docs.astral.sh/uv/getting-started/installation/),
`uv sync --locked` installs Python 3.12 when needed and creates `.venv` with the
locked dependencies. Then use the same executable paths above, or
`uv run --locked dealer-evidence validate-corpus`.

No credentials are needed for the quick-start commands. Tests, policy search,
and fixture replay run offline. `lookup-recalls --live` calls NHTSA; `ask` calls
OpenAI and, when the model selects recall lookup, calls NHTSA live.
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

## Recall lookup

Replay a captured response without a network connection:

```powershell
.\.venv\Scripts\dealer-evidence.exe lookup-recalls --identity tech_demo --make Toyota --model Corolla --year 2020 --fixture toyota-corolla-2020
```

Make one public request to NHTSA:

```powershell
.\.venv\Scripts\dealer-evidence.exe lookup-recalls --identity tech_demo --make Toyota --model Corolla --year 2020 --live --json
```

Choose `--live` or `--fixture ID` explicitly. Both demo identities can use this
public tool; unknown identities fail before network or fixture access. Up to five
records are displayed by default (`--limit` accepts 1..10). The response states
the full count and whether output is truncated, plus source URL, observation
time, and response fingerprint. Fixture replay is labeled `recorded_fixture` or
`synthetic_fixture`; it never falls back to a live call.

An empty result is distinct from timeout, HTTP, network, oversized, or malformed
response errors. Neither a campaign nor an empty result establishes a particular
VIN's eligibility, repair completion, or safety. Recorded responses describe the
capture time, not current recall status. Source text is evidence, not instructions.
See [M3 decisions](docs/m3-decisions.md) and [recall fixture provenance](data/recalls/README.md).

## Ask a question (live model)

Set `OPENAI_API_KEY` in the process environment, or explicitly load your local
`.env` file. The CLI does not load `.env` automatically. Environment variables
take precedence over values in the specified file. Keep the pinned model in
`.env.example`; a different model setting produces an error rather than a fallback.

```powershell
.\.venv\Scripts\dealer-evidence.exe ask "What should I record for a loaner return?" --identity tech_demo --env-file .env
.\.venv\Scripts\dealer-evidence.exe ask "What is the goodwill approval maximum?" --identity manager_demo --env-file .env --show-evidence
.\.venv\Scripts\dealer-evidence.exe ask "Look up general recalls for a 2020 Toyota Corolla." --identity tech_demo --env-file .env --json
.\.venv\Scripts\dealer-evidence.exe ask "Any recalls for my Honda Civic?" --identity tech_demo --env-file .env
```

The model returns one structured decision selecting `search_policies(query)` or
`lookup_recalls(make, model, year)`, or a clarification/unsupported disposition.
Code validates arguments and identity,
then independently rechecks policy permissions before supplying up to four full
documents. The existing direct search command retains its default of three excerpts.
Answer citations resolve only to supplied evidence. Citation membership does not
prove factual support; that requires manual answer evaluation.

Each request allows at most two logical model calls and one logical data-tool
call, with zero automatic retries and a six-step graph limit. Missing vehicle
values and recognized ambiguity prevent recall execution. Mixed requests ask the
user to choose one task. Clarification is terminal: resubmit a complete question.
No evidence, successful empty recall results, provider failures, and invalid
citations remain distinct outcomes. See M4 decisions for conservative language
checks, timing limits, and remaining live validation.

The initial model choice is OpenAI `gpt-4.1-mini-2025-04-14`, with the OpenAI SDK
and strict structured-output schemas. Its documented support is recorded in
[M0 decisions](docs/m0-decisions.md). Live account access is now verified. The
final seven-case development check produced four supported answers, one appropriate
abstention, and two clarifications. It is not held-out validation or a general
answer-quality estimate.

`ask` writes versioned, ignored `runs/<run_id>.jsonl` files beginning before
request setup. They contain ordered graph events, code/configuration fingerprints,
tool provenance, and evidence IDs/content hashes derived from the final SDK request. Routine traces
omit message bodies, questions, credentials, and upstream error text. `--show-evidence`
explicitly displays authorized source content in CLI output. The seven-case
development smoke in `scripts/m4_smoke.py` uses the live model with labeled,
recorded NHTSA evidence; it never opens held-out cases or calls NHTSA live.

Inspect a request without provider access:

```powershell
.\.venv\Scripts\dealer-evidence.exe trace --run-id <run-id>
.\.venv\Scripts\dealer-evidence.exe trace --run-id <run-id> --json
.\.venv\Scripts\dealer-evidence.exe trace --runs-dir docs/examples --run-id e79271e8fcfc412eabfbb634c06c8b49
```

The last command opens a reviewed **offline scripted example**, not live model
quality evidence. The inspector identifies incomplete traces and unconfirmed
attempts; it rejects malformed/versionless files. Policy-query text is redacted
with an argument fingerprint; validated recall fields remain readable. Writes
are flushed and synced before execution continues; trace failures return errors.
See [M5 decisions and limits](docs/m5-decisions.md). End-to-end evaluation and
the production-code regression/CI demo remain later work.

## Demo boundaries

`tech_demo` maps to `technician` and `manager_demo` to `manager`. The access layer
and search/list commands expose 16 shared policies to technicians and all 24 to
managers. Unknown identities fail closed, including case or whitespace variants.
These are selectable local test identities, **not authentication**. Anyone with
the repository can read the fictional policies. Retrieval uses the authorized
document set before tokenization, indexing, scoring, or generating snippets.

Policies, amounts, and procedures are invented for this project. NHTSA
year/make/model results describe general recall records, not VIN-specific
repair status or proof that a vehicle is safe. This is a new personal project,
written independently from public documentation and its own requirements.

See [data provenance](docs/data-provenance.md),
[the intended public file set](docs/public-files.md),
[M0 decisions and verification](docs/m0-decisions.md),
[M1 decisions and verification](docs/m1-decisions.md),
[M2 decisions and verification](docs/m2-decisions.md), and
[M3 decisions and verification](docs/m3-decisions.md), and
[M4 decisions and verification](docs/m4-decisions.md), and
[M5 decisions and verification](docs/m5-decisions.md).
