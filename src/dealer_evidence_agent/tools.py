"""Deterministic dispatch arguments and an independent policy context guard."""

import json
import re
from dataclasses import asdict

from dealer_evidence_agent.answers import AgentError, Citation, Evidence
from dealer_evidence_agent.corpus import PolicyDocument
from dealer_evidence_agent.permissions import resolve_role
from dealer_evidence_agent.recalls import RecallInputError, RecallResult, validate_query
from dealer_evidence_agent.retrieval import PolicyHit, SearchError, validate_search

MAX_EVIDENCE_CHARS = 40_000


def routing_question(question: str) -> str:
    """Separate a narrow recall-scope follow-up from the tool-selection question.

    Only a complete, terminal repair-completion question is removed. The full
    question still drives ambiguity guards and answer composition. No vehicle
    fields are extracted or supplied here, and unrecognized wording is retained.
    """
    if not re.search(r"\brecalls?\b", question, re.I) or mixed_request(question):
        return question
    return re.sub(
        r"(?:,?\s+and\s+|[.;?]\s*)"
        r"(?:tell me (?:if|whether) (?:that|this|it) (?:proves|establishes|confirms)"
        r"|does (?:that|this|it) (?:prove|establish|confirm))"
        r"\s+(?:that\s+)?(?:my|the)\s+repairs?\s+"
        r"(?:was|were|has been|have been)\s+completed[.?]?\s*$",
        "",
        question,
        flags=re.I,
    )


def validate_arguments(name: str, arguments: dict) -> dict:
    if name == "search_policies" and set(arguments) == {"query"}:
        try:
            validate_search(arguments["query"], 4)
        except SearchError as exc:
            raise AgentError("invalid_tool_arguments") from exc
        return arguments
    if name == "lookup_recalls" and set(arguments) == {"make", "model", "year"}:
        try:
            return asdict(validate_query(**arguments))
        except RecallInputError as exc:
            raise AgentError("invalid_tool_arguments") from exc
    raise AgentError("invalid_tool_arguments")


def vehicle_is_explicit(question: str, arguments: dict) -> bool:
    """Conservative lexical guard, not a universal natural-language ambiguity detector."""
    normalized = " ".join(question.casefold().split())
    years = re.findall(r"(?<!\w)(?:19|20|21)\d{2}(?!\w)", normalized)
    if set(years) != {str(arguments["year"])}:
        return False
    # A negated inference is a scope caveat, not a negated vehicle selection.
    # Remove only that negation token, retaining the rest of the question so
    # alternatives (including ones following the caveat) still fail closed.
    selection_text = re.sub(
        r"\b(do|does|should|must) not (?=(?:infer|assume|conclude|prove|establish|mean)\b)",
        r"\1 ",
        normalized,
    )
    if re.search(r"\b(or|either|versus|vs|maybe|possibly|not|instead)\b", selection_text):
        return False
    if re.search(r"\band\b(?!\s+(?:tell me|explain|does that|whether)\b)", normalized):
        return False
    for key in ("make", "model"):
        if not re.search(r"(?<!\w)" + re.escape(arguments[key].casefold()) + r"(?!\w)", normalized):
            return False
    # A slash is accepted only if it belongs to the explicit vehicle label.
    residual = normalized.replace(arguments["model"].casefold(), "")
    return "/" not in residual


def mixed_request(question: str) -> bool:
    return bool(
        re.search(
            r"\b(?:recalls? for|recall records|recall campaigns|(?:check|look up|lookup|find)"
            r"\b.{0,40}\brecalls?)\b",
            question,
            re.I,
        )
        and re.search(
            r"\b(policy|policies|loaner|goodwill|discount|shuttle|refund|appointment)\b",
            question,
            re.I,
        )
    )


def restricted_policy_request(question: str, identity: str) -> bool:
    """Conservative abstention for explicitly requested private policy terms.

    Query text can narrow an answer, never grant a different role. This does not
    infer that a restricted policy exists or expose any restricted metadata.
    """
    return resolve_role(identity) == "technician" and bool(
        re.search(r"\b(?:private|confidential|manager[-_ ]only)\b", question, re.I)
        and re.search(
            r"\b(?:limits?|deadlines?|caps?|thresholds?|procedures?|terms|rules|rates?)\b",
            question,
            re.I,
        )
    )


def policy_evidence(
    hits: tuple[PolicyHit, ...], documents: tuple[PolicyDocument, ...], identity: str
) -> tuple[Evidence, ...]:
    role = resolve_role(identity)
    by_id = {doc.doc_id: doc for doc in documents}
    seen = set()
    evidence = []
    if len(hits) > 4:
        raise AgentError("context_rejected")
    for hit in hits:
        doc = by_id.get(hit.doc_id)
        # Deliberately independent of the retrieval permission predicate/helper.
        if (
            doc is None
            or hit.doc_id in seen
            or doc.visibility not in ("shared", "manager_only")
            or (role != "manager" and doc.visibility != "shared")
        ):
            raise AgentError("context_rejected")
        if (hit.path, hit.version, hit.sha256, hit.title) != (
            doc.path,
            doc.version,
            doc.sha256,
            doc.title,
        ):
            raise AgentError("context_rejected")
        seen.add(hit.doc_id)
        # Supply canonical full text, never trust retriever-generated snippets as content.
        evidence.append(Evidence(Citation("policy", doc.doc_id, doc.path), doc.text))
    return bound_evidence(tuple(evidence))


def bound_evidence(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    if sum(len(item.content) for item in evidence) > MAX_EVIDENCE_CHARS:
        raise AgentError("evidence_too_large")
    return evidence


def recall_evidence(result: RecallResult) -> tuple[Evidence, ...]:
    if result.body_sha256 is None:
        raise AgentError("invalid_recall_evidence")
    metadata = {
        "query": asdict(result.query),
        "source": result.source,
        "observed_at": result.observed_at,
        "fixture_id": result.fixture_id,
        "total_count": result.total_count,
        "returned_count": len(result.records),
        "truncated": result.truncated,
        "boundary": result.boundary,
    }
    evidence = [
        Evidence(
            Citation("recall_response", result.body_sha256, result.source_url),
            json.dumps(metadata, ensure_ascii=False),
        )
    ]
    evidence.extend(
        Evidence(
            Citation("recall_campaign", record.campaign_number, result.source_url),
            json.dumps(asdict(record), ensure_ascii=False),
        )
        for record in result.records
    )
    return bound_evidence(tuple(evidence))
