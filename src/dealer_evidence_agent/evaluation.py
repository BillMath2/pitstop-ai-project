"""Executed graph reports. Mechanical checks are separate from manual semantic grading."""

import hashlib
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from dealer_evidence_agent.corpus import corpus_fingerprint, text_fingerprint
from dealer_evidence_agent.evaluations import EvaluationError, load_evaluations
from dealer_evidence_agent.graph import request_metadata, run_agent
from dealer_evidence_agent.model_client import ModelClient, RecordingClient
from dealer_evidence_agent.permissions import AuthorizationError, resolve_role
from dealer_evidence_agent.prompts import PROMPT_VERSION
from dealer_evidence_agent.recall_fixtures import (
    DEFAULT_FIXTURE_MANIFEST,
    fixture_fingerprint,
    load_fixture_manifest,
    replay_recalls,
)
from dealer_evidence_agent.retrieval import PolicySearch
from dealer_evidence_agent.tracing import JsonlTrace, code_metadata, fingerprint, inspect_trace

DEFAULT_REPLIES = Path("evals/model_replies/development-scripted.json")
OUTCOMES = {
    "answer": "answered",
    "abstain": "insufficient_evidence",
    "clarify": "needs_clarification",
    "reject": "error",
    "lookup": "answered",
}


def _vehicle(args):
    return (
        " ".join(args["make"].casefold().split()),
        " ".join(args["model"].casefold().split()),
        args["year"],
    )


def load_scripted_replies(path: Path, cases: tuple[dict, ...]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            set(value) != {"provenance", "cases"}
            or value["provenance"] != "synthetic_scripted_not_model_quality"
            or set(value["cases"]) != {c["case_id"] for c in cases}
        ):
            raise ValueError("Bad script contract")
        for replies in value["cases"].values():
            if not isinstance(replies, list) or len(replies) > 2:
                raise ValueError("Bad reply count")
            if not all(isinstance(reply, dict) for reply in replies):
                raise ValueError("Bad scripted reply")
        return value
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise EvaluationError("Invalid scripted replies; no live fallback is allowed.") from exc


def score_case(
    case,
    result,
    requests,
    events,
    retrieved_ids,
    recall_result,
    documents,
    expected_recall_status="ok",
) -> dict:
    """Score observed actions/evidence only after execution; labels never enter the model."""
    expected = case["expected"]
    try:
        role = resolve_role(case["identity"])
    except AuthorizationError:
        role = None
    allowed = {
        d.doc_id: d
        for d in documents
        if (d.visibility == "shared" and role is not None)
        or (d.visibility == "manager_only" and role == "manager")
    }
    forbidden = set(expected["forbidden_document_ids"])
    selected = [e for e in events if e["event"] == "route_selected"]
    actual_route = next(
        (e["action"] for e in selected if e["action"] in ("search_policies", "lookup_recalls")),
        "none",
    )
    actual_args = next((e.get("arguments") for e in selected if e["action"] == actual_route), None)
    arguments_ok = None
    if expected["route"] == "lookup_recalls":
        arguments_ok = actual_route == "lookup_recalls" and _vehicle(actual_args) == _vehicle(
            expected["tool_arguments"]
        )
    evidence = [
        e
        for body in requests
        for e in json.loads(body["messages"][-1]["content"]).get("evidence", [])
    ]
    supplied_policy = {e["id"] for e in evidence if e["kind"] == "policy"}
    citation_policy = {c.id for c in result.answer.citations if c.kind == "policy"}
    all_policy = set(retrieved_ids) | supplied_policy | citation_policy
    permissions_ok = all_policy <= allowed.keys() and not all_policy & forbidden
    content_ok = all(
        e["id"] in allowed and e["content"] == allowed[e["id"]].text
        for e in evidence
        if e["kind"] == "policy"
    )
    permitted_citations = {
        ("policy", e["id"], allowed[e["id"]].path)
        for e in evidence
        if e["kind"] == "policy" and e["id"] in allowed
    }
    recall_content_ok = True
    recall_items = [e for e in evidence if e["kind"].startswith("recall_")]
    if recall_items:
        recall_content_ok = recall_result is not None and recall_result.status == "ok"
        if recall_content_ok:
            campaigns = {r.campaign_number: asdict(r) for r in recall_result.records}
            for item in recall_items:
                content = json.loads(item["content"])
                if item["kind"] == "recall_campaign":
                    recall_content_ok &= content == campaigns.get(item["id"])
                elif item["kind"] == "recall_response":
                    recall_content_ok &= (
                        item["id"] == recall_result.body_sha256
                        and content.get("query") == asdict(recall_result.query)
                        and content.get("source") == recall_result.source
                        and content.get("fixture_id") == recall_result.fixture_id
                        and content.get("total_count") == recall_result.total_count
                        and content.get("returned_count") == len(recall_result.records)
                        and content.get("truncated") == recall_result.truncated
                        and content.get("observed_at") == recall_result.observed_at
                        and content.get("boundary") == recall_result.boundary
                    )
                else:
                    recall_content_ok = False
    if recall_result is not None and recall_result.status in ("ok", "empty"):
        permitted_citations.add(
            ("recall_response", recall_result.body_sha256, recall_result.source_url)
        )
        permitted_citations.update(
            ("recall_campaign", r.campaign_number, recall_result.source_url)
            for r in recall_result.records
        )
    citations_ok = all(
        (c.kind, c.id, c.source) in permitted_citations for c in result.answer.citations
    )
    citations_ok &= result.answer.status != "answered" or bool(result.answer.citations)
    boundary = [e for e in events if e["event"] == "model_request"]
    trace_ok = len(boundary) == len(requests)
    for event, body in zip(boundary, requests, strict=False):
        payload = json.loads(body["messages"][-1]["content"])
        supplied = [
            {
                "kind": e["kind"],
                "id": e["id"],
                "content_sha256": hashlib.sha256(e["content"].encode()).hexdigest(),
            }
            for e in payload.get("evidence", [])
        ]
        trace_ok &= event["request_sha256"] == fingerprint(body) and event["evidence"] == supplied
        if event["stage"] == "route":
            trace_ok &= not supplied
    disposition = OUTCOMES[expected["outcome"]]
    if expected["outcome"] == "lookup":
        disposition = (
            "answered"
            if expected_recall_status == "ok"
            else ("no_records" if expected_recall_status == "empty" else "error")
        )
    disposition_ok = result.answer.status == disposition
    if expected["outcome"] == "reject":
        disposition_ok &= result.error_code == "invalid_identity"
    elif disposition == "error":
        disposition_ok &= result.error_code == "recall_service_error"
    checks = {
        "route": actual_route == expected["route"],
        "arguments": arguments_ok,
        "disposition": bool(disposition_ok),
        "permissions": bool(permissions_ok),
        "canonical_policy_content": content_ok,
        "recall_evidence": bool(recall_content_ok),
        "citations": bool(citations_ok),
        "required_policy_evidence": set(expected["document_ids"])
        <= supplied_policy & citation_policy,
        "boundary_trace": bool(trace_ok),
        "call_bounds": result.model_calls <= 2 and result.tool_calls <= 1,
        "no_tools_for_terminal": (result.tool_calls == 0 if expected["route"] == "none" else True),
        "unknown_identity_preflight": (
            result.model_calls == result.tool_calls == 0
            if expected["outcome"] == "reject"
            else None
        ),
        "recorded_recall_only": recall_result.network_attempts == 0 if recall_result else True,
        "recall_outcome": (
            recall_result is not None and recall_result.status == expected_recall_status
            if expected["route"] == "lookup_recalls"
            else None
        ),
    }
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "identity": case["identity"],
        "question": case["query"],
        "route": actual_route,
        "arguments": actual_args,
        "answer": asdict(result.answer),
        "error_code": result.error_code,
        "retrieved_ids": retrieved_ids,
        "supplied_policy_ids": sorted(supplied_policy),
        "model_calls": result.model_calls,
        "tool_calls": result.tool_calls,
        "models": sorted({b["model"] for b in requests}),
        "providers": sorted({e["provider"] for e in boundary}),
        "checks": checks,
        "automatic_pass": all(v for v in checks.values() if v is not None),
        "manual_review": {
            "status": "pending",
            "required_facts": expected["required_facts"],
            "forbidden_claims": expected["forbidden_claims"],
        },
    }


def evaluate_agent(
    documents,
    eval_manifest: Path,
    *,
    mode: str,
    runs_dir: Path,
    split: str = "development",
    env_file: Path | None = None,
    replies_path: Path = DEFAULT_REPLIES,
    fixture_manifest: Path = DEFAULT_FIXTURE_MANIFEST,
    model_factory=None,
    fixture_overrides: dict | None = None,
) -> dict:
    if mode not in ("scripted", "live-model"):
        raise EvaluationError("Unknown model evaluation mode.")
    cases = load_evaluations(eval_manifest, documents, split=split)
    fixtures = load_fixture_manifest(fixture_manifest)
    by_fixture = {f["fixture_id"]: f for f in fixtures}
    recorded = {_vehicle(f["query"]): f for f in fixtures if f["kind"] == "recorded"}
    overrides = fixture_overrides or {}
    if set(overrides) - {c["case_id"] for c in cases} or any(
        f not in by_fixture for f in overrides.values()
    ):
        raise EvaluationError("Invalid explicit recall fixture override.")
    # Preflight expected fixtures before spending tokens; none are supplied to the router.
    expected_fixtures = {}
    for case in cases:
        if case["expected"]["route"] == "lookup_recalls":
            fixture = (
                by_fixture[overrides[case["case_id"]]]
                if case["case_id"] in overrides
                else recorded.get(_vehicle(case["expected"]["tool_arguments"]))
            )
            if fixture is None or _vehicle(fixture["query"]) != _vehicle(
                case["expected"]["tool_arguments"]
            ):
                raise EvaluationError(
                    "A matching recall fixture is required before model evaluation."
                )
            expected_fixtures[case["case_id"]] = fixture
    scripts = load_scripted_replies(replies_path, cases) if mode == "scripted" else None
    rows = []
    started = time.monotonic()
    metadata = code_metadata()
    usage = {}
    for case in cases:
        case_started = time.monotonic()
        trace = JsonlTrace(runs_dir)
        trace.emit("request_started", **request_metadata())
        owner = None
        requests, retrieved, recall_results = [], [], []
        identity, case_id = case["identity"], case["case_id"]
        fixture = expected_fixtures.get(case_id)

        class SearchProbe:
            def search_policies(self, query, *, identity=identity, retrieved=retrieved, **kwargs):
                found = PolicySearch(documents, identity=identity).search_policies(query, **kwargs)
                retrieved.extend(h.doc_id for h in found.hits)
                return found

        def lookup(*, case_id=case_id, identity=identity, recall_results=recall_results, **args):
            # Select by actual arguments, with only trusted operator-selected overrides.
            selected = (
                by_fixture[overrides[case_id]]
                if case_id in overrides
                else recorded.get(_vehicle(args))
            )
            if selected is None:
                raise EvaluationError("No recorded fixture for the selected vehicle.")
            result = replay_recalls(
                fixture_manifest, selected["fixture_id"], identity=identity, **args
            )
            recall_results.append(result)
            return result

        try:
            if model_factory is not None:
                owner = model_factory(case_id)
            elif scripts is not None:
                replies = [
                    {
                        "choices": [
                            {"finish_reason": "stop", "message": {"content": json.dumps(reply)}}
                        ]
                    }
                    for reply in scripts["cases"][case_id]
                ]
                owner = ModelClient(RecordingClient(replies))
            else:
                owner = ModelClient.from_environment(env_file)
            if identity in ("tech_demo", "manager_demo"):
                trace.emit(
                    "request_validated",
                    identity=identity,
                    corpus_sha256=corpus_fingerprint(documents),
                )
            result = run_agent(
                case["query"],
                identity=identity,
                documents=documents,
                model=owner.with_recording(requests),
                trace=trace,
                search=SearchProbe(),
                recall_lookup=lookup,
                finalize_trace=False,
            )
            owner.close()
            owner = None
            counts = {"model_calls": result.model_calls, "tool_calls": result.tool_calls}
            if result.error_code:
                trace.emit("request_failed", error=result.error_code, **counts)
            else:
                trace.emit(
                    "request_finished",
                    status=result.answer.status,
                    citation_ids=[c.id for c in result.answer.citations],
                    **counts,
                )
        except Exception as exc:
            trace.emit("request_failed", error="evaluation_setup_failed")
            raise EvaluationError(
                "Evaluation setup or persistence failed; run not complete."
            ) from exc
        finally:
            if owner is not None:
                owner.close()
            trace.close()
        observed = inspect_trace(runs_dir, trace.run_id)
        row = score_case(
            case,
            result,
            requests,
            observed["events"],
            retrieved,
            recall_results[0] if recall_results else None,
            documents,
            fixture["expected_status"] if fixture else "ok",
        )
        row.update(
            run_id=trace.run_id,
            expected_fixture_id=fixture["fixture_id"] if fixture else None,
            actual_fixture_id=recall_results[0].fixture_id if recall_results else None,
            recall_status=recall_results[0].status if recall_results else None,
            elapsed_seconds=time.monotonic() - case_started,
            usage=observed["usage"],
        )
        rows.append(row)
        for key, count in observed["usage"].items():
            usage[key] = usage.get(key, 0) + count
    metrics = {
        key: {
            "passed": sum(r["checks"][key] is True for r in rows),
            "total": sum(r["checks"][key] is not None for r in rows),
        }
        for key in rows[0]["checks"]
    }
    return {
        "report_version": 1,
        "mode": mode,
        "split": split,
        "generated_at": datetime.now(UTC).isoformat(),
        "code": metadata,
        "prompt_version": PROMPT_VERSION,
        "corpus_sha256": corpus_fingerprint(documents),
        "cases_sha256": text_fingerprint(
            (eval_manifest.parent / f"{split}.jsonl").read_text(encoding="utf-8")
        ),
        "fixtures_sha256": fixture_fingerprint(list(fixtures)),
        "scripted_replies_sha256": fingerprint(scripts) if scripts else None,
        "recall_source": "fixtures",
        "elapsed_seconds": time.monotonic() - started,
        "usage": usage,
        "automatic_passes": sum(r["automatic_pass"] for r in rows),
        "case_count": len(rows),
        "metrics": metrics,
        "semantic_pass_rate": None,
        "manual_review_pending": len(rows),
        "cases": rows,
        "limitations": "Mechanical checks only; manually grade facts and prohibited claims. "
        + (
            "Scripted replies measure contract execution, NOT model quality."
            if scripts
            else "Live model outputs are nondeterministic; recall responses are recorded."
        ),
    }
