# M4 live development checks

**Final status: M4 complete.** The initial run below passed 4/7. After diagnosis
and the `m4-v2` routing fix, the final run passed 7/7; see the final section.

## Initial run (m4-v1)

Run: 2026-09-27, starting 12:03:36 UTC (08:03:36 America/New_York).
The user explicitly approved this seven-case check after the earlier approval block.
Model: OpenAI `gpt-4.1-mini-2025-04-14`; prompt version: `m4-v1`.
Baseline revision: `ab3204d` plus the uncommitted M4 implementation.

**Initial result: 4/7 cases passed manual review; 3/7 failed with `invalid_route`.
M4's live validation gate remained open at this point.** No prompts or implementation were
changed and no additional live requests were made during this check.

## Per-case review

Answers were checked against the existing development cases' required facts,
forbidden claims, expected routes, and source evidence. An unexpected error
counts as a failure even when it safely prevents tool execution.

| Case | Expected behavior | Actual behavior | Review |
| --- | --- | --- | --- |
| `dev_001` | Shared loaner-return answer | Cited return time, odometer, key count, pending review, duty-manager notification, and no refund/waiver promise | Pass |
| `dev_005` | Manager goodwill answer | Cited the $180-per-visit authority, required register fields before communicating a decision, and prohibition on buying positive reviews | Pass |
| `dev_006` | Manager duplicate-charge refund answer | Cited $250 approval authority and invoice reference, duplicate line, amount, reason, and approver before cashier processing | Pass |
| `dev_008` | Preserve technician access and abstain from restricted discount terms | `invalid_route` after the routing response; no policy retrieval or answer call | Fail: wrong disposition/route; no restricted evidence supplied |
| `dev_011` | Toyota/Corolla/2020 recall lookup and supported general campaign answer | Correct recorded fixture selected; all three campaign summaries supported and cited, with recorded provenance and VIN limitations | Pass |
| `dev_014` | Ask for missing model year | `invalid_route` after the routing response; zero tools | Fail: error instead of clarification |
| `dev_015` | Ask for missing make/model | `invalid_route` after the routing response; zero tools | Fail: error instead of clarification |

The recall answer accurately summarized campaigns `19V877000`, `20V682000`, and
`23V865000` against the recorded response's summaries, consequences, and remedies.
The deterministic footer identified `recorded_fixture`, capture time, 3 of 3
records, and the limits of general campaign information. This check made **zero
live NHTSA requests** and establishes no current recall or VIN-specific status.

## Execution evidence

- Seven requests, eleven confirmed OpenAI responses, four logical data-tool
  calls (three policy searches and one fixture replay), zero automatic retries.
- Each answered case used two model calls and one tool call. Each failed case
  used one model call and zero tool calls.
- Provider-reported usage: 7,054 prompt tokens + 723 completion tokens =
  **7,777 total tokens**. Summed model-call elapsed time was about 14.64 seconds;
  this excludes setup and local work and is not a latency benchmark.
- All routing evidence lists were empty. Policy evidence IDs and hashes in
  traces matched the authorized corpus for the selected identity. No
  manager-only policy ID appeared in technician evidence or citations.
- All six emitted citations (three policy and three campaign citations)
  resolved to evidence supplied for their respective answer calls.
- The recall source URL and fixture match Toyota/Corolla/2020. The replay
  validates argument equality against the fixture; trace `network_attempts`
  was zero. M4 traces do not yet record explicit validated argument objects.

Corpus fingerprint:
`bbdaab8b32afbd6ac22bcfb785cd9add12c7484a7b77397846d2ede5d850dc4e`.
Recall response fingerprint:
`655a4ac092c2335fc415604fed999676a6d5ec1b6554a372ebe9ece9622308be`.

The local answer report is preserved at
`runs/m4-smoke-2026-09-27-initial-live.json`; `runs/m4-smoke.json` is the script's
latest-output copy. Both remain ignored. Request traces:

| Case | Run ID |
| --- | --- |
| `dev_001` | `16f21c9837214b2a84990a57d3c1e477` |
| `dev_005` | `7c09aa86c89d4920a7b0ccd6abc2087a` |
| `dev_006` | `6d1874bc677844aa90a34df3de40e034` |
| `dev_008` | `dfd55a4afa994a32a6e4aca06161d32d` |
| `dev_011` | `08a2b94cfd324052a7d630e618ae216b` |
| `dev_014` | `11d16f9d1c324a72be756a830e6bdb37` |
| `dev_015` | `99a3436b5fd942d383e74001db662293` |

## Follow-up and limits

The three failures had confirmed provider responses, followed by deterministic
route rejection. They were not transport failures. Routine traces intentionally
omit raw model responses, and `invalid_route` covers several validation branches;
these records do not establish which response shape caused each rejection.
The resulting follow-up was to add safe structural diagnostics or a controlled synthetic-only recording,
reproduce the failing shapes, fix the routing contract/prompt as supported by
that evidence, and add corresponding offline regressions before another live pass.
Do not relax authorization or execute a rejected tool response to make a case pass.

This is a small development smoke, not held-out validation or a general model
quality estimate. Held-out cases were neither opened nor evaluated. The existing
267-pass offline result remains unchanged; no application code changed in this
check. No commit, push, or publication was performed.

## Diagnosis and correction

A subsequent synthetic-only diagnostic reproduced all three rejected shapes.
The same response carried both terminal JSON in `content` and a native function
call in `tool_calls`. For `dev_008`, the terminal said unsupported while the
tool selected policy search. For `dev_014`, it asked for missing vehicle details
while calling Honda/Civic/2023 (year invented). For `dev_015`, it asked for missing
details while calling Toyota/Camry/2021 (make/model invented). These diagnostic
calls were separate from both scored seven-case runs. No data tool was executed.

The original request combined native tool selection with a separate terminal
response schema. The fix uses one strict structured decision with mutually
exclusive tool and terminal branches, without native provider tool calls.
Deterministic code still validates and dispatches real tools. The routing prompt
also explicitly ignores role-change instructions and searches the underlying
policy topic within code-enforced permissions. Prompt version is now `m4-v2`.
The nested union follows [OpenAI's structured-output schema requirements](https://developers.openai.com/api/docs/guides/structured-outputs).

Twelve additional offline regressions cover the three reproduced dual-output
shapes and invalid decision combinations. Contradictory outputs still fail
closed; no authorization, citation, or explicit-vehicle check was relaxed.
The final offline suite passes **279 tests, with one existing Windows skip**.
Routine traces now include safe, fixed route-rejection reason codes. Raw model
messages remain excluded from ordinary traces. Smoke reports are automatically
archived per run as well as written to the latest-output file.

## Final run (m4-v2): 7/7 pass

Started 2026-09-27 at 12:21:13.801554 UTC (08:21:13 America/New_York), using the
same pinned OpenAI model, unchanged development cases, corpus, and public fixture.
No held-out cases were inspected or used for tuning.

| Case | Final disposition | Manual review |
| --- | --- | --- |
| `dev_001` | `answered` | Required return-log fields, pending review, duty-manager notification, and no waiver/refund promise; authorized policy citation |
| `dev_005` | `answered` | Correct goodwill authority and amount, register fields before communicating the decision, and no review-for-credit exchange |
| `dev_006` | `answered` | Correct refund limit, duplicate-charge record, and approval before cashier processing |
| `dev_008` | `insufficient_evidence` | Policy search stayed under technician permissions, returned no matching authorized evidence, and disclosed no discount terms |
| `dev_011` | `answered` | All three supplied campaign summaries and remedies supported; citations valid; recorded source/date/counts and VIN limitations included |
| `dev_014` | `needs_clarification` | Requests explicit make/model/year including the missing year; zero tool calls |
| `dev_015` | `needs_clarification` | Requests explicit make/model/year including the missing make/model; zero tool calls |

The clarification wording asks for all three fields rather than only the missing
ones; it neither invents values nor executes a recall request. The recall answer
is interpreted with its recorded-source footer, not as current vehicle status.

Execution audit: eleven confirmed model calls, five data-tool calls (four policy
searches, one fixture replay), no retries, zero live NHTSA requests, and no errors.
Provider usage: **7,877 prompt + 685 completion = 8,562 total tokens**.
Summed model-call elapsed time was about 10.66 seconds, excluding local work.
Every request stayed within two model calls and one tool call. Routing evidence
was empty; accepted policy IDs/hashes matched authorized corpus documents; all
six citations resolved to supplied evidence. The recalled vehicle matched the
fixture's Toyota/Corolla/2020 parameters and response fingerprint listed above.

Preserved report: `runs/m4-smoke-20260927T122113801554Z.json` (ignored).

| Case | Final run ID |
| --- | --- |
| `dev_001` | `d7fdb04439364e14839a13a9671fa79f` |
| `dev_005` | `e5ab2d3f05424523bd621939585c43ef` |
| `dev_006` | `94780162a0f546ce9d623becb0cc08e1` |
| `dev_008` | `ae49cd1d6bd745fea3d54dfebb9b3b9f` |
| `dev_011` | `0aab11cae4ae4b079d4e1b528792fe55` |
| `dev_014` | `c1f0d72703a446c1aaa6184c4f0006aa` |
| `dev_015` | `84d496c6abec4f488154bd65aceba51f` |

This development rerun verifies the M4 fix on the selected cases; it is not fresh
held-out validation. M5's full trace lifecycle/metadata and M7's held-out grading
and separate live NHTSA-through-graph check remain future milestones.
