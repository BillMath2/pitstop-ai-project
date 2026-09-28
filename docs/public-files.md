# Intended public file set

Only newly authored application material belongs in the eventual public repo:

- `README.md`, `pyproject.toml`, `.python-version`, `.gitignore`, `.gitattributes`, `.env.example`.
- Dependency locks: `uv.lock` and `requirements.lock`.
- `src/dealer_evidence_agent/`, `tests/`, and synthetic policies under `data/`.
- Public NHTSA response captures and labeled synthetic fixtures under `data/recalls/`.
- Reviewed project documentation under `docs/`.
- Explicitly reviewed synthetic trace examples under `docs/examples/`, labeled with provenance.
- Synthetic evaluation fixtures and their contract under `evals/`.
- Reviewed development smoke scripts under `scripts/` (their generated output stays ignored).
- `.github/workflows/ci.yml` for offline checks.
- Reviewed regression patch and reproduction record under `docs/`; never a broken production tree.
- Labeled synthetic model replies under `evals/model_replies/`; never presented as model quality.
- Reviewed M7 reports, freezes, qualitative grading, and scoped audit under `docs/evidence/`.
- Separately labeled exposed-case quality regression reports and iteration summaries;
  these do not replace the original held-out evaluation.
- The offline `docs/demo.html` replay and instructions; not a completed video.

Never include `.env`, credentials, local runtimes, virtual environments,
generated `runs/`, raw debug output, or career/internal planning material.
`.gitignore` excludes these ordinary local files, and the source distribution
uses an explicit inclusion list. Neither mechanism removes previously tracked
files or substitutes for inspecting Git history and built artifacts.

Before staging or publishing, inspect `git status --short`, `git ls-files`, the
actual diff, and repository history. Stage only named, reviewed paths. Review
any future synthetic trace examples before adding them. No commit, remote
rename, push, package publication, or PR is part of M0.
