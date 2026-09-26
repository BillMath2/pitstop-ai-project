# M0: name and scaffold

Implementation date: 2026-09-26. Scope: an installable Python package, offline
CLI, validated starter corpus, and decisions needed for the later agent.

## Name

| Surface | Selected name |
| --- | --- |
| Display | Dealer Evidence Agent |
| Intended repository | `BillMath2/dealer-evidence-agent` |
| Distribution | `dealer-evidence-agent` |
| Python import | `dealer_evidence_agent` |
| Command | `dealer-evidence` |

Checks on 2026-09-26: the unauthenticated GitHub repository API returned 404 for
the intended owner/name; PyPI's normalized-name JSON endpoint returned 404; a
GitHub repository-name search returned zero matches. Exact-name web search
identified no obvious competing dealership project. These are checks of public
listings, not a reservation or trademark clearance. Recheck at publication.

- [GitHub owner/name lookup](https://api.github.com/repos/BillMath2/dealer-evidence-agent)
- [PyPI normalized-name lookup](https://pypi.org/pypi/dealer-evidence-agent/json)
- [GitHub name search](https://github.com/search?q=dealer-evidence-agent&type=repositories)

The existing working directory and remote still use `pitstop-ai-project`.
No rename or publication was performed. The distinct public name avoids the
existing [Pitstop garage-management example](https://github.com/EdwinVW/pitstop).

## Provider decision

Use the OpenAI Python SDK with `gpt-4.1-mini-2025-04-14` as the initial fixed
model. It is a small, non-reasoning baseline for the narrow routing and answer
tasks; this selection makes no claim that it outperforms other models. Use the
Responses API with strict function schemas for tool selection and structured
output for final answers in M4. Do not silently change provider/model.

The [official model page](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
documents support for Responses, function calling, structured outputs, and this
snapshot. The [function-calling guide](https://developers.openai.com/api/docs/guides/function-calling)
documents strict schemas and disabling parallel tool calls. Documentation
support and an SDK import were verified at M0; account access, billing, and live
model behavior were not tested. M4 must verify actual calls before reporting
routing quality. No paid model calls were made during M0.

Only `OPENAI_API_KEY` and `OPENAI_MODEL` belong in this application's future
provider configuration. `.env.example` contains placeholders; the existing
`.env` is unchanged and ignored. Current commands do not read configuration or
initialize a model client.

## Runtime and dependencies

Python 3.12 is the initial supported runtime. This workstation had Python 3.11;
a project-local uv download installed CPython 3.12.14 under ignored `.tools/`
and created `.venv/`. No global Python replacement was needed. uv 0.12.19 was
used to resolve dependencies. See [uv installation](https://docs.astral.sh/uv/getting-started/installation/).

| Dependency | Verified version | License |
| --- | --- | --- |
| LangGraph | 1.2.12 | MIT |
| OpenAI Python SDK | 3.19.2 | Apache-2.0 |
| HTTPX | 0.28.1 | BSD-3-Clause |
| rank-bm25 | 0.2.2 | Apache-2.0 |
| pytest | 9.1.1 | MIT |
| Ruff | 0.16.9 | MIT |
| Hatchling (build) | 1.32.4 | MIT |

License identifiers were checked against installed package metadata.
Dependencies retain their own licenses; review transitive license notices when
distributing artifacts. Project licensing remains a release decision.

Direct dependencies and the build backend are pinned in `pyproject.toml`.
`uv.lock` records transitive versions and artifact hashes. `requirements.lock`
exports runtime/development constraints for pip, excluding this editable project
and omitting hashes so it can be used with `pip install -e ".[dev]" -c ...`.
Prefer `uv sync --locked` for the fully resolved installation. Regenerate the
pip constraints with `uv export --locked --no-emit-project --no-hashes --output-file requirements.lock`.

LangGraph brings supporting LangChain packages transitively. No separate
LangChain agent framework or second provider SDK was added. The graph itself
belongs to M4; importing `StateGraph` is the M0 dependency check. Reference:
[LangGraph installation](https://docs.langchain.com/oss/python/langgraph/install).

## Verification

The M0 exit checks are package installation, CLI help, LangGraph import, and
validation of the two starter documents. Offline tests cover malformed
metadata, duplicate IDs/files, path containment, invalid visibility, missing
files, encoding errors, and CLI failure reporting. M0 validation is not the
role-based retrieval authorization promised for later milestones.

Results on 2026-09-26:

- Editable installation and a separate fresh wheel installation succeeded.
- `dealer-evidence --help`, `--version`, and `validate-corpus` succeeded.
- Both starter policies validated: one shared and one manager-only.
- LangGraph `StateGraph` and OpenAI SDK imports succeeded.
- pytest: **25 passed, 1 skipped**. The skipped symlink-escape test requires
  Windows permission to create symlinks. It remains in the suite for environments
  that support them; this workstation did not verify that case end to end.
- Ruff lint and formatting checks passed. Dependency compatibility passed.
- Wheel and source distribution built successfully. Their file lists excluded
  `.env`, planning material, local environments, caches, and generated traces.
- Git tracked files/history contained only the original README before this work.
  The M0 files were subsequently committed as `ce12c61` (`builing M0`). No
  publication or remote changes were part of M0 implementation.

The initial offline fresh-environment install needed another dependency fetch;
installation with network access then succeeded. Offline tests require no
service calls once dependencies are installed.

## Next milestone

M1: complete the 24-policy corpus, add corpus fingerprints and the two-role
permission matrix, and author the 40 evaluation cases with a 16/24 split.
Do not tune retrieval or prompts against the held-out cases.
