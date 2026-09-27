# M4: bounded routing and grounded-answer implementation

Implementation date: 2026-09-27. Baseline: M3 commit `ab3204d`, initially clean.
The external development plan initially said M1 was next; repository commits and
`docs/m1-decisions.md` through `m3-decisions.md` established the actual baseline.
No saved M4 implementation was present when this session resumed.

**Status: M4 complete.** Offline validation passes 279 tests (one existing skip).
After correcting the routing contract, the seven-case live development check
passes 7/7. The initial 4/7 run and diagnosis remain in
[the live results](m4-live-development.md). M5 tracing is next.

## Completed scope

- Typed LangGraph route, execute, compose, and terminal paths.
- One OpenAI adapter and a recording fake operating at the same SDK call boundary.
- New versioned prompts and a strict decision schema containing the two tool
  argument schemas and terminal alternatives, plus a strict answer schema.
  Runtime validation remains independent of provider schema enforcement.
- Clarification, unsupported, no evidence, no records, and explicit error outcomes.
- Limits of two logical model calls, one logical tool call, and six graph steps.
- `ask`, optional authorized evidence display, typed/code-resolved citations,
  and trace hooks at the actual provider request boundary.
- Offline tests for routing, input ambiguity, authorization faults, malformed
  output, invalid citations, provider failures, and trace/body agreement.

## Request behavior

`ask "question" --identity tech_demo` validates identity, question, and the corpus
before creating a provider client. Graph identity lives in trusted closure
context; the model cannot set it through state or tool arguments. The routing
request contains a question, original system instructions, and one structured
decision schema. The schema contains mutually exclusive policy-tool, recall-tool,
clarification, and unsupported branches. It contains no corpus documents or
restricted titles. Code dispatches the selected real data tool.

One valid tool call executes. Parallel calls, unknown actions, extra arguments,
invalid values, malformed JSON, duplicate keys, truncated model output, and
refusals are errors. A terminal disposition needs no tool or second model call.
There is no model-driven retry or route loop. SDK retries and NHTSA retries are
both disabled (zero is within the plan's allowance of at most one retry).

Policy retrieval requests four hits, leaving the direct M2 search command's
three-excerpt default unchanged. A separate guard compares each hit with the
trusted corpus, independently checks visibility for the immutable identity, and
verifies metadata/content hashes. It supplies canonical full policy text, so
answers can account for exceptions omitted from search snippets. The guard does
not reuse the retrieval permission predicate. Faulty retrieval aborts before
generation or logging rejected IDs. The ordinary trace records only accepted IDs.

Recall arguments must pass the M3 vehicle validator and appear as whole labels
in the question. Missing explicit values, multiple years, alternatives,
negations, and recognized multiple-task forms block execution. These conservative
lexical checks can ask for clarification on otherwise valid phrasing; they are
not a complete semantic ambiguity detector. The router is also instructed to
clarify uncertain or mixed requests. A policy question about handling recalls
can still use policy search. No vehicle aliases or implicit years are inferred.

Normal `ask` recall execution uses the existing live NHTSA tool. Only trusted
test/development dependencies inject fixture replay; there is no fixture-mode
argument on `ask`. Recall context includes provenance, capture time, total and
supplied counts, and truncation status. A deterministic note repeats those limits
in the final response. Empty success becomes `no_records`, with a response
citation and no second model call; service failures remain `error`.

The evidence content budget is 40,000 characters. Oversized evidence fails
explicitly rather than silently cutting policy exceptions or recall text.
M3's independent response and record limits also remain enforced. The graph has
a 65-second elapsed budget, checks between stages and after responses, and passes
at most 25 seconds (or the remaining budget) to each provider attempt. Recall
execution requires at least its 15-second budget remaining. Like M3, these are
cooperative elapsed checks plus transport timeouts, not preemptive cancellation
of synchronous I/O; an operation may finish after the elapsed budget, at which
point the request returns an error.

Generated answers allow `answered` or `insufficient_evidence`. Every answered
result requires supplied typed citations. Code resolves policy paths and NHTSA
URLs; the model cannot create citation targets. Abstention uses fixed text, so
unsupported model prose is not displayed as a factual answer. Citation membership
does **not** establish semantic support or prevent all unsupported prose. Manual
live evaluation remains necessary; fake replies do not measure model quality.

## Provider and configuration

The pinned choice remains OpenAI `gpt-4.1-mini-2025-04-14`; no dependency or model
upgrade was made. The adapter uses Chat Completions with one strict JSON decision
output for routing and strict JSON for answers. Neither request offers native
SDK function calls. The router chooses a tool and arguments within its decision,
and deterministic code executes that tool after validation. An object wrapper
contains four disjoint `anyOf` branches; each has one action value and only its
corresponding arguments or reason. This follows the official structured-output
requirements for an object root and supported nested unions.
Temperature is zero and output is bounded at
1,800 completion tokens; incomplete outputs fail rather than being displayed.
The installed OpenAI 3.19.2 and LangGraph 1.2.12 interfaces were inspected.
Public references checked during implementation:

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)

`OPENAI_API_KEY` is required for `ask`. `.env` loading is explicit via
`--env-file .env`; only literal `OPENAI_API_KEY` and `OPENAI_MODEL` assignments are
recognized, with optional matching quotes, no interpolation or shell execution.
Process environment values take precedence. A model different from the pinned
choice is rejected, not silently substituted. The API base URL is fixed and
environment proxies/redirects are disabled. Errors omit raw SDK messages and keys.

## M4 trace hooks versus remaining M5 work

M4 supplies an in-memory recording sink plus minimal ignored JSONL files. The
adapter derives evidence IDs and exact content hashes from the final SDK body
immediately before invocation; the full canonical request is also hashed. Tests
compare these with a recording client and with JSON serialized by the real SDK
through an offline HTTP transport. Routing evidence is empty. Request attempts,
confirmed responses, reported usage, errors, and zero retries are distinguished.
Credentials, headers, question text, evidence bodies, and model prose are omitted.
Actual JSONL write failures abort success. Rejected route shapes emit fixed
structural reason codes, never model text. No application debug-message capture
mode exists; a local synthetic-only diagnostic script was used to reproduce
the initial routing failure, with credentials and headers excluded.

M5 still needs full audit metadata (code revision, explicit schema/configuration
fingerprints and permitted validated arguments), comprehensive setup/early-exit
lifecycle coverage, operator trace inspection, and a reviewed synthetic example.
The current setup-failure event can precede graph `request_started`; this is not
yet the complete M5 lifecycle contract. Ordinary JSONL hooks are not described
as a completed audit system or universal no-leak guarantee.

## Verification and live development checks

- Baseline: 192 passed, 1 skipped.
- M4: **279 passed, 1 skipped**, including 87 new graph/provider/CLI checks.
  The skip is the existing Windows symlink-permission check.
- Tests exercise both roles/routes, role impersonation, full-text permission
  rechecking, forged retrieval metadata, no evidence, empty recall results,
  failure statuses, terminal dispositions, output/citation errors, extra tool
  arguments, multiple calls, deadlines, context size, and trace failures. Twelve
  final regressions cover the reproduced contradictory live outputs and malformed
  or mixed decisions. The request test verifies there is only one routing channel.
- Offline SDK transport verifies the exact serialized request hash, returned
  usage, omitted secrets, and a single attempt on HTTP 503.
- Ruff lint/format checks, whitespace checks, dependency compatibility, locked
  dependency validation, and offline source/wheel builds passed. Build contents
  include the new modules and smoke script while excluding credentials, local
  runtimes/caches, generated runs, and private planning paths. Corpus,
  development-case, and all nine recall-fixture validation commands passed.
- The corpus, frozen development/held-out files, and recorded recall fixtures
  were not changed. Held-out cases were not opened or evaluated.

The prepared seven-case smoke selects `dev_001`, `dev_005`, `dev_006`, `dev_008`,
`dev_011`, `dev_014`, and `dev_015` from the development file only. It covers
shared/restricted policy questions, impersonation, a recall lookup, and missing
vehicle details. OpenAI runs live; recall lookup replays the recorded
Toyota/Corolla/2020 public response, explicitly labeled as such. Raw output stays
under ignored `runs/`; the smoke is not a held-out evaluation or grading system.

```powershell
.\.venv\Scripts\python.exe scripts/m4_smoke.py --env-file .env
```

The first attempted case returned `provider_error` before a confirmed response
or data-tool execution. The network-enabled retry was rejected by automatic
approval review because exporting repository evidence to OpenAI was considered
unapproved. No workaround or further live request followed that rejection.
The user subsequently approved the seven-case check. On 2026-09-27 it completed
with eleven confirmed OpenAI responses: four supported answers passed manual
review, while the role-impersonation case and both missing-vehicle cases failed
with `invalid_route` before tool execution. No live NHTSA requests occurred.
See [per-case grading, traces, usage, and follow-up](m4-live-development.md).
Diagnosis reproduced terminal JSON and a tool call in the same response,
including guessed values for missing vehicle fields. Prompt `m4-v2` replaces
the dual output contract with one mutually exclusive structured decision and
clarifies how to ignore role-change instructions while searching the policy topic.
Runtime guards still reject contradictory outputs and guessed vehicle arguments.
The final live rerun passed all seven cases: four cited answers, one authorized
search followed by abstention, and two clarifications with no data-tool calls.
Eleven model calls used 8,562 reported tokens, with no retries or live NHTSA calls.
This satisfies M4's small development-pass exit requirement; it does not satisfy
M7's held-out evaluation or live graph-to-NHTSA demonstration.

No commit, push, or publication was performed.
Elapsed session time was not instrumented, so no engineering-hour estimate is
claimed. **Next task:** complete M5 request-boundary tracing.
