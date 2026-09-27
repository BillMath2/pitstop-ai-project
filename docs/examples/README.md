# Reviewed synthetic trace example

`e79271e8fcfc412eabfbb634c06c8b49.jsonl` is an actual local run of
`scripts/m5_trace_example.py`, generated 2026-09-27. The provider is explicitly
`recording_fake`; its responses are scripted. No live model or NHTSA service was
called. Missing token-usage fields are intentional.

It demonstrates a technician policy request: routing has no evidence, four
authorized shared policies enter the answer request, and the answer cites
`shared_loaner_return`. Source hashes were checked against the corpus. Review
confirmed no manager-only IDs, raw questions, policy prose, credentials,
authorization headers, or raw model messages. The actual timings and dirty-code
metadata are preserved; they are not performance or live answer-quality evidence.

Inspect from the repository root:

```powershell
.\.venv\Scripts\dealer-evidence.exe trace --runs-dir docs/examples --run-id e79271e8fcfc412eabfbb634c06c8b49
```

Regeneration creates a new ignored file under `runs/`. Review any replacement
before copying it here. IDs, timestamps, timings, source state, and revision can
change; do not rewrite an old example to claim it came from newer code.
