"""Acyclic route -> execute -> compose graph; identity is immutable closure context."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from dealer_evidence_agent.answers import AgentError, Answer, Evidence, parse_json, validate_answer
from dealer_evidence_agent.corpus import PolicyDocument, corpus_fingerprint
from dealer_evidence_agent.model_client import ModelClient
from dealer_evidence_agent.permissions import AuthorizationError, resolve_role
from dealer_evidence_agent.prompts import (
    ANSWER_PROMPT,
    ANSWER_SCHEMA,
    ROUTE_PROMPT,
    ROUTE_SCHEMA,
    response_format,
)
from dealer_evidence_agent.recalls import BOUNDARY, REQUEST_BUDGET_SECONDS, RecallLookup
from dealer_evidence_agent.retrieval import PolicySearch, SearchError, validate_search
from dealer_evidence_agent.tools import (
    mixed_request,
    policy_evidence,
    recall_evidence,
    validate_arguments,
    vehicle_is_explicit,
)
from dealer_evidence_agent.tracing import Trace

REQUEST_SECONDS = 65.0
GRAPH_STEP_LIMIT = 6
TERMINALS = {
    "missing_vehicle": "Please supply one vehicle's make, model, and four-digit model year.",
    "ambiguous_request": "Please specify one unambiguous task and one vehicle make/model/year.",
    "mixed_request": "Please choose a policy question or a recall lookup, then resubmit it.",
    "out_of_scope": "Supported tasks are dealership policy questions and general recall lookups.",
}


class AgentState(TypedDict, total=False):
    action: str
    arguments: dict
    evidence: tuple[Evidence, ...]
    answer: Answer
    recall_note: str


@dataclass(frozen=True)
class AgentResult:
    answer: Answer
    model_calls: int
    tool_calls: int
    evidence: tuple[Evidence, ...]
    error_code: str | None = None


def run_agent(
    question: str,
    *,
    identity: str,
    documents: tuple[PolicyDocument, ...],
    model: ModelClient,
    trace: Trace,
    search: PolicySearch | None = None,
    recall_lookup: Callable | None = None,
) -> AgentResult:
    """Injected tools are trusted test dependencies, never choices exposed to the model."""
    started = time.monotonic()
    deadline = started + REQUEST_SECONDS
    counts = {"model": 0, "tool": 0}

    def check_time() -> None:
        if time.monotonic() >= deadline:
            raise AgentError("request_deadline_exceeded")

    def complete(stage: str, body: dict) -> dict:
        check_time()
        if counts["model"] >= 2:
            raise AgentError("model_call_limit")
        counts["model"] += 1
        return model.complete(body, stage=stage, deadline=deadline, trace=trace)

    def route(state: AgentState) -> AgentState:
        def reject(reason: str):
            # Fixed structural codes only: no model prose, arguments, or source IDs.
            trace.emit("route_rejected", reason=reason)
            raise AgentError("invalid_route")

        message = complete(
            "route",
            {
                "messages": [
                    {"role": "system", "content": ROUTE_PROMPT},
                    {"role": "user", "content": json.dumps({"question": question})},
                ],
                "response_format": response_format("route", ROUTE_SCHEMA),
            },
        )
        if message.get("tool_calls") or message.get("function_call"):
            reject("unexpected_provider_tool_call")
        value = parse_json(message.get("content"))
        if set(value) != {"decision"} or not isinstance(value["decision"], dict):
            reject("invalid_decision_envelope")
        decision = value["decision"]
        action = decision.get("action")
        if action in ("search_policies", "lookup_recalls"):
            if set(decision) != {"action", "arguments"} or not isinstance(
                decision["arguments"], dict
            ):
                reject("invalid_tool_decision")
            arguments = validate_arguments(action, decision["arguments"])
            if mixed_request(question):
                return terminal("needs_clarification", "mixed_request")
            if action == "lookup_recalls" and not vehicle_is_explicit(question, arguments):
                return terminal("needs_clarification", "missing_vehicle")
            # Policy query text is deliberately not logged: it can echo raw user text.
            trace.emit("route_selected", action=action)
            return {"action": action, "arguments": arguments}
        if set(decision) != {"action", "reason"}:
            reject("invalid_terminal_decision")
        reason = decision["reason"]
        if not isinstance(reason, str) or reason not in TERMINALS:
            reject("invalid_terminal_reason")
        if action == "unsupported" and reason == "out_of_scope":
            return terminal(action, reason)
        if action == "needs_clarification" and reason != "out_of_scope":
            return terminal(action, reason)
        reject("invalid_terminal_action")

    def terminal(status: str, reason: str) -> AgentState:
        trace.emit("route_selected", action=status, reason=reason)
        return {"answer": Answer(status, TERMINALS[reason])}

    def execute(state: AgentState) -> AgentState:
        check_time()
        if counts["tool"] >= 1:
            raise AgentError("tool_call_limit")
        action, args = state["action"], state["arguments"]
        if action == "lookup_recalls" and deadline - time.monotonic() < REQUEST_BUDGET_SECONDS:
            raise AgentError("request_deadline_exceeded")
        counts["tool"] += 1
        if action == "search_policies":
            engine = search if search is not None else PolicySearch(documents, identity=identity)
            found = engine.search_policies(args["query"], top_k=4)
            evidence = policy_evidence(found.hits, documents, identity)
            trace.emit(
                "tool_completed",
                action=action,
                status=found.status,
                evidence_ids=[e.citation.id for e in evidence],
            )
            if not evidence:
                return {
                    "answer": Answer("insufficient_evidence", "No matching authorized evidence.")
                }
            return {"evidence": evidence}
        lookup = recall_lookup or RecallLookup(identity=identity).lookup_recalls
        result = lookup(**args)
        check_time()
        trace.emit(
            "tool_completed",
            action=action,
            status=result.status,
            source=result.source,
            source_url=result.source_url,
            body_sha256=result.body_sha256,
            total_count=result.total_count,
            returned_count=len(result.records),
            fixture_id=result.fixture_id,
            network_attempts=result.network_attempts,
        )
        if result.status not in ("ok", "empty"):
            raise AgentError("recall_service_error")
        evidence = recall_evidence(result)
        observed = result.observed_at or "synthetic, no capture time"
        note = (
            f"Source: {result.source}; observed: {observed}. "
            f"Showing {len(result.records)} of {result.total_count} returned campaign records. "
            + ("Results are truncated. " if result.truncated else "")
            + BOUNDARY
        )
        if result.status == "empty":
            return {
                "evidence": evidence,
                "answer": Answer(
                    "no_records",
                    "No records were returned for this combination. " + note,
                    (evidence[0].citation,),
                ),
            }
        return {"evidence": evidence, "recall_note": note}

    def compose(state: AgentState) -> AgentState:
        message = complete(
            "answer",
            {
                "messages": [
                    {"role": "system", "content": ANSWER_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "evidence": [item.payload() for item in state["evidence"]],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                "response_format": response_format("answer", ANSWER_SCHEMA),
            },
        )
        if message.get("tool_calls"):
            raise AgentError("invalid_answer")
        answer = validate_answer(parse_json(message.get("content")), state["evidence"])
        if state.get("recall_note"):
            answer = Answer(
                answer.status, answer.text + "\n\n" + state["recall_note"], answer.citations
            )
        return {"answer": answer}

    try:
        trace.emit("request_started")
        try:
            resolve_role(identity)
            validate_search(question, 4)
        except AuthorizationError as exc:
            raise AgentError("invalid_identity") from exc
        except SearchError as exc:
            raise AgentError("invalid_question") from exc
        trace.emit(
            "request_validated", identity=identity, corpus_sha256=corpus_fingerprint(documents)
        )
        builder = StateGraph(AgentState)
        builder.add_node("route", route)
        builder.add_node("execute", execute)
        builder.add_node("compose", compose)
        builder.add_edge(START, "route")
        builder.add_conditional_edges("route", lambda s: END if "answer" in s else "execute")
        builder.add_conditional_edges("execute", lambda s: END if "answer" in s else "compose")
        builder.add_edge("compose", END)
        state = builder.compile().invoke({}, {"recursion_limit": GRAPH_STEP_LIMIT})
        check_time()
        answer = state["answer"]
        trace.emit(
            "request_finished",
            status=answer.status,
            model_calls=counts["model"],
            tool_calls=counts["tool"],
            citation_ids=[c.id for c in answer.citations],
            elapsed_seconds=time.monotonic() - started,
        )
        return AgentResult(answer, counts["model"], counts["tool"], state.get("evidence", ()))
    except Exception as exc:
        code = str(exc) if isinstance(exc, AgentError) else "internal_error"
        try:
            trace.emit(
                "request_failed", error=code, model_calls=counts["model"], tool_calls=counts["tool"]
            )
        except Exception:
            code = "trace_write_failed"
        return AgentResult(
            Answer("error", f"Request failed: {code}."), counts["model"], counts["tool"], (), code
        )
