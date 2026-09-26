# Intended public file set

Only newly authored application material belongs in the eventual public repo:

- `README.md`, `pyproject.toml`, `.python-version`, `.gitignore`, `.env.example`.
- Dependency locks: `uv.lock` and `requirements.lock`.
- `src/dealer_evidence_agent/`, `tests/`, and synthetic `data/`.
- Reviewed project documentation under `docs/`.
- Synthetic evaluation fixtures and their contract under `evals/`.
- Later: `.github/workflows/ci.yml`.

Never include `.env`, credentials, local runtimes, virtual environments,
generated `runs/`, raw debug output, or career/internal planning material.
`.gitignore` excludes these ordinary local files, and the source distribution
uses an explicit inclusion list. Neither mechanism removes previously tracked
files or substitutes for inspecting Git history and built artifacts.

Before staging or publishing, inspect `git status --short`, `git ls-files`, the
actual diff, and repository history. Stage only named, reviewed paths. Review
any future synthetic trace examples before adding them. No commit, remote
rename, push, package publication, or PR is part of M0.
