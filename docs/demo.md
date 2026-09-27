# Demo recording kit — 110 seconds

Open [demo.html](demo.html) locally and press **Play 110 seconds**. Pause and Reset
are available. This replays reviewed captured outputs with no external assets
or API calls. It is a prepared recording surface, not a captured video or a new
live execution. Browser automation was unavailable, so visual playback and
screen capture still require operator review. Rebuild offline:

```powershell
.\.venv\Scripts\python.exe scripts/m7_prepare_demo.py
```

| Time | Scene | Narration point |
| --- | --- | --- |
| 0–10 s | Bounded agent | Fictional policies, public data, two tools, hard call limits |
| 10–27 s | Supported policy answer | Contact correction uses both required cited sources |
| 27–43 s | Technician | Goodwill question cannot be answered from authorized evidence |
| 43–59 s | Manager | Same question now has access to the invented $180 source |
| 59–80 s | Live recall | Real OpenAI/NHTSA trace; general records, not VIN/safety status; missing fields clarify |
| 80–98 s | Production regression | One-line mutation, unchanged local red test, independent guard green |
| 98–110 s | Limits | Retrieval 10/10; mechanical 20/24; strict qualitative 14/24; targets unmet |

Suggested narration:

> This bounded LangGraph agent works with fictional dealership policies and
> public recall records. It allows one tool call and at most two model calls.
> Correcting contact information needs both record-amendment and contact-check
> policies, and the answer cites both. The same goodwill question then produces
> different evidence for two fixed identities. The technician receives an
> abstention; the manager can see the invented approval limit. Question text
> cannot grant that access.
>
> The recall scene is a real OpenAI and NHTSA execution with one HTTP attempt.
> These are general campaign records, not VIN eligibility, repair completion,
> or safety conclusions. Missing fields stop the lookup. For the regression,
> one production predicate was weakened in an isolated worktree. An unchanged
> test fails because restricted records enter technician retrieval, while the
> independent context guard still passes.
>
> The first held-out results have limits. Retrieval found every required source,
> but only twenty of twenty-four cases passed mechanical checks, and strict
> qualitative review passed fourteen. These failures remain visible. This is
> a constrained demonstration, not a production-ready assistant.

The current regression scene is **local red evidence**. Before the final public
recording, obtain authorization for the clearly labeled regression PR, show
actual hosted passing/red checks, and close without merging. Follow
[the mutation/cleanup procedure](regression-demo.md). The known
[hosted passing base is 5df166d](https://github.com/BillMath2/pitstop-ai-project/actions/runs/36325212649).
Do not imply that a red PR exists or uncommitted M7 artifacts have hosted checks.

An uncut walkthrough can use `ask` and `trace` with their printed run IDs.
New live calls incur usage and are new observations; they must not replace the
first held-out result. Role captures are development demonstrations, excluded
from held-out scores. Keep `.env`, secret-bearing terminals, and local checkpoint
objects out of the recording.

Remaining: address unmet gates or agree to a limited demonstration scope; choose
a license; review grading and playback; capture video; authorize the hosted red PR.
No completed video or PR is claimed by this kit.
