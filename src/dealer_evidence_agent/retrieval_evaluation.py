"""Development-only retrieval metrics; no routing, answer, or held-out evaluation."""

from pathlib import Path

from dealer_evidence_agent.corpus import PolicyDocument, corpus_fingerprint, text_fingerprint
from dealer_evidence_agent.evaluations import load_evaluations
from dealer_evidence_agent.permissions import AuthorizationError, can_access, resolve_role
from dealer_evidence_agent.retrieval import (
    DEFAULT_TOP_K,
    RETRIEVAL_VERSION,
    PolicySearch,
    validate_search,
)


def evaluate_retrieval(
    documents: tuple[PolicyDocument, ...],
    eval_manifest: Path,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    validate_search("evaluation", top_k)
    cases = load_evaluations(eval_manifest, documents)
    by_id = {doc.doc_id: doc for doc in documents}
    rows = []
    policy_recalls = []
    reciprocal_ranks = []
    unauthorized_count = 0
    forbidden_count = 0
    rejection_count = 0
    # This administrator report includes corpus metadata. It is not a model tool.
    for case in cases:
        category = case["category"]
        if category not in {"policy", "permission", "missing_evidence", "unknown_identity"}:
            continue
        if category == "unknown_identity":
            try:
                PolicySearch(documents, identity=case["identity"])
            except AuthorizationError:
                rejection_count += 1
                rows.append({"case_id": case["case_id"], "category": category, "rejected": True})
            else:
                rows.append({"case_id": case["case_id"], "category": category, "rejected": False})
            continue
        result = PolicySearch(documents, identity=case["identity"]).search_policies(
            case["query"], top_k=top_k
        )
        ids = [hit.doc_id for hit in result.hits]
        expected = set(case["expected"]["document_ids"])
        forbidden = set(case["expected"]["forbidden_document_ids"]) & set(ids)
        role = resolve_role(case["identity"])
        unauthorized = [doc_id for doc_id in ids if not can_access(role, by_id[doc_id].visibility)]
        unauthorized_count += len(unauthorized)
        forbidden_count += len(forbidden)
        row = {
            "case_id": case["case_id"],
            "category": category,
            "status": result.status,
            "retrieved_ids": ids,
            "unauthorized_count": len(unauthorized),
            "forbidden_count": len(forbidden),
        }
        if category == "policy":
            recall = len(expected & set(ids)) / len(expected)
            reciprocal = next(
                (1 / rank for rank, doc_id in enumerate(ids, 1) if doc_id in expected), 0
            )
            policy_recalls.append(recall)
            reciprocal_ranks.append(reciprocal)
            row.update(recall_at_k=recall, reciprocal_rank_at_k=reciprocal)
        rows.append(row)
    return {
        "split": "development",
        "retrieval_version": RETRIEVAL_VERSION,
        "top_k": top_k,
        "corpus_sha256": corpus_fingerprint(documents),
        "development_sha256": text_fingerprint(
            (eval_manifest.parent / "development.jsonl").read_text(encoding="utf-8")
        ),
        "policy_cases": len(policy_recalls),
        "mean_recall_at_k": sum(policy_recalls) / len(policy_recalls) if policy_recalls else None,
        "mean_reciprocal_rank_at_k": (
            sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else None
        ),
        "unauthorized_hits": unauthorized_count,
        "forbidden_hits": forbidden_count,
        "unknown_identities_rejected": rejection_count,
        "skipped_cases": len(cases) - len(rows),
        "cases": rows,
        "limitations": (
            "Retrieval only. Lexical matches do not establish answerability. "
            "No routing, factual-answer, abstention, recall API, or held-out quality was measured."
        ),
    }
