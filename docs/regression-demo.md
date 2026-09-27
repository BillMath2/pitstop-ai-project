# Reproducible production authorization regression

Verified locally on Windows/Python 3.12.14, 2026-09-27. This is local test
evidence, not a hosted CI result. The mutation was never applied to the main
working copy and was not committed, pushed, or merged.

## Passing base and actual mutation

Passing revision: `6ec238d88e11b96955db62c63f950a744bdca8da` (M5).
The unchanged full suite passed **317 tests, one Windows skip**, in 28.73 s,
in a detached worktree. The imported permission module was verified to be
inside that worktree, not the main editable installation.

The [patch](authorization-regression.patch) changes exactly one production
predicate in `authorized_documents`:

```diff
-    return tuple(doc for doc in documents if can_access(role, doc.visibility))
+    return tuple(doc for doc in documents if can_access(role, "shared"))
```

Both known roles can access `shared`, so every document now enters their index.
Unknown identities still fail. Tests, corpus/fixtures, the independent context
guard, and CI were unchanged. Patch SHA-256:
`3febae494f5d2477ca0296beb2c0cfe234db56903c967b8a944ce199d6038eac`.

## Observed failure

The unchanged test
`tests/test_retrieval.py::test_role_claim_in_query_does_not_change_bound_identity`
failed at line 86:

```text
assert all(hit.doc_id.startswith("shared_") for hit in result.hits)
E assert False
```

Actual technician search returned, in order:
`manager_goodwill_review`, `manager_access_review`, `manager_discount_review`,
`shared_complaint_intake`, `manager_refund_review`.

The same full pytest command then produced **26 failed, 291 passed, one skip**
in 28.72 s. The additional failures reflect permission leakage and graph paths
stopping earlier at the independent context guard. This was an assertion
failure, not an import, syntax, infrastructure, or lint failure. Ruff on the
mutated module passed. Separately, the unchanged
`tests/test_graph.py::test_faulty_retriever_cannot_leak_restricted_ids_or_content`
passed and confirmed the independent guard still blocks restricted model input.

Local raw logs remain in ignored `runs/m6-base-pytest.txt`,
`runs/m6-mutation-red.txt`, `runs/m6-mutation-full.txt`,
`runs/m6-mutation-guard.txt`, `runs/m6-mutation-lint.txt`, and
`runs/m6-mutation-ids.json`. This reviewed record is the portable artifact.

## Reproduce locally

From the repository root in PowerShell, with dependencies already installed:

```powershell
$repo = (Get-Location).Path
$demo = Join-Path $repo 'runs/m6-authorization-regression'
$python = Join-Path $repo '.venv/Scripts/python.exe'
$patch = Join-Path $repo 'docs/authorization-regression.patch'
$base = '6ec238d88e11b96955db62c63f950a744bdca8da'
git worktree add --detach $demo $base
if ($LASTEXITCODE -ne 0) { throw 'Worktree creation failed' }
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $demo 'src'
Push-Location $demo
try {
    & $python -c 'import dealer_evidence_agent.permissions as p; print(p.__file__)'
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw 'Baseline must pass before mutation' }
    git apply --check $patch
    if ($LASTEXITCODE -ne 0) { throw 'Patch preflight failed' }
    git apply $patch
    if ($LASTEXITCODE -ne 0) { throw 'Patch failed' }
    git diff --stat
    & $python -m pytest tests/test_retrieval.py::test_role_claim_in_query_does_not_change_bound_identity -vv
    # Inspect the expected authorization assertion above; exit must be 1.
    & $python -m pytest
    & $python -m pytest tests/test_graph.py::test_faulty_retriever_cannot_leak_restricted_ids_or_content
    & $python -m ruff check src/dealer_evidence_agent/permissions.py
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
```

Keep the red pytest command ordinary: no `xfail`, `continue-on-error`, fabricated
test, or CI wrapper that accepts its failure. This historic M5 base predates
the new M6 workflow. At publication time, first commit and verify M6 on the
intended passing base, then repeat the same patch/tests on that revision and
record both hosted URLs and exact base/head revisions. Do not claim the M5
worktree ran a workflow it did not contain.

## Cleanup and publication boundary

```powershell
git -C $demo apply --reverse --check $patch
if ($LASTEXITCODE -ne 0) { throw 'Inspect changes before cleanup' }
git -C $demo apply --reverse $patch
if ($LASTEXITCODE -ne 0) { throw 'Reverse patch failed' }
$status = git -C $demo status --porcelain
if ($LASTEXITCODE -ne 0 -or $status) { throw 'Worktree must be clean' }
git worktree remove $demo
git worktree list
```

During this verification, Git unregistered the restored clean worktree but
left files behind with a Windows “Directory not empty” error. The remaining
temporary directory was removed with PowerShell `Remove-Item -LiteralPath`
after verifying its absolute path was exactly the intended workspace `runs/`
directory and its `.git` marker was gone. Only the main worktree now remains;
the main production predicate is unchanged and the broken worktree is gone.

A later, explicitly authorized demonstration PR must be clearly labeled,
show the real passing-base/red-PR CI links, and close without merging. No
runtime bypass option is introduced by this milestone.
