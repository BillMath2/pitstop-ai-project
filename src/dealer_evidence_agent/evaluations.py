"""Offline fixture validation only; this is not an agent evaluation runner.

Default loading never opens held-out cases. Full validation is an explicit
authoring/release check and must not be used to tune retrieval or prompts.
"""

import json
from pathlib import Path

from dealer_evidence_agent.corpus import PolicyDocument, corpus_fingerprint, text_fingerprint
from dealer_evidence_agent.permissions import AuthorizationError, can_access, resolve_role


class EvaluationError(ValueError):
    """Evaluation fixtures are malformed or no longer match their frozen inputs."""


_CATEGORIES = {
    "policy": ("search_policies", "answer"),
    "permission": ("search_policies", "abstain"),
    "missing_evidence": ("search_policies", "abstain"),
    "recall": ("lookup_recalls", "lookup"),
    "clarification": ("none", "clarify"),
    "unknown_identity": ("none", "reject"),
}
_EXPECTED_FIELDS = {
    "route",
    "outcome",
    "document_ids",
    "forbidden_document_ids",
    "required_facts",
    "forbidden_claims",
    "tool_arguments",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise EvaluationError(f"Cannot read fixture: {path.name}") from exc


def _json(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvaluationError("Invalid fixture JSON.") from exc


def _strings(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and item.strip() for item in value)
        and len(value) == len(set(value))
    )


def _validate_case(case: object, split: str, documents: dict[str, PolicyDocument]) -> None:
    fields = {"case_id", "split", "category", "identity", "query", "expected"}
    if not isinstance(case, dict) or set(case) != fields:
        raise EvaluationError("Case fields do not match the fixture schema.")
    for field in fields - {"expected"}:
        if not isinstance(case[field], str) or not case[field].strip():
            raise EvaluationError(f"Case {field} must be a nonempty string.")
    prefix = "dev_" if split == "development" else "held_"
    if case["split"] != split or not case["case_id"].startswith(prefix):
        raise EvaluationError("Case split or ID prefix mismatch.")
    category = case["category"]
    if category not in _CATEGORIES:
        raise EvaluationError("Unknown case category.")
    expected = case["expected"]
    if not isinstance(expected, dict) or set(expected) != _EXPECTED_FIELDS:
        raise EvaluationError("Expected-result fields do not match the fixture schema.")
    if (expected["route"], expected["outcome"]) != _CATEGORIES[category]:
        raise EvaluationError("Route/outcome does not match category.")
    for field in ("document_ids", "forbidden_document_ids", "required_facts", "forbidden_claims"):
        if not _strings(expected[field]):
            raise EvaluationError(f"Expected {field} must be unique nonempty strings.")
    if not expected["required_facts"] or not expected["forbidden_claims"]:
        raise EvaluationError("Each case needs required facts and forbidden claims.")
    required = set(expected["document_ids"])
    forbidden = set(expected["forbidden_document_ids"])
    if not (required | forbidden) <= documents.keys() or required & forbidden:
        raise EvaluationError("Unknown or conflicting evidence document IDs.")
    try:
        role = resolve_role(case["identity"])
    except AuthorizationError:
        if category != "unknown_identity":
            raise EvaluationError("Unknown identity requires a rejection case.") from None
        role = None
    if role is not None and category == "unknown_identity":
        raise EvaluationError("Rejection case must use an unknown identity.")
    if any(not can_access(role, documents[doc_id].visibility) for doc_id in required):
        raise EvaluationError("Expected evidence is inaccessible to this identity.")
    if category == "policy" and not required:
        raise EvaluationError("Policy answers require evidence.")
    if category != "policy" and required:
        raise EvaluationError("Non-answer cases cannot require policy citations.")
    if category == "permission" and (
        not forbidden or any(can_access(role, documents[doc_id].visibility) for doc_id in forbidden)
    ):
        raise EvaluationError("Permission cases must identify inaccessible evidence.")
    arguments = expected["tool_arguments"]
    if category == "recall":
        if not isinstance(arguments, dict) or set(arguments) != {"make", "model", "year"}:
            raise EvaluationError("Recall arguments require make, model, and year.")
        if (
            any(
                not isinstance(arguments[key], str) or not arguments[key].strip()
                for key in ("make", "model")
            )
            or type(arguments["year"]) is not int
            or not 1900 <= arguments["year"] <= 2100
        ):
            raise EvaluationError("Invalid recall arguments.")
    elif arguments != {}:
        raise EvaluationError("Only recall fixtures specify exact tool arguments at M1.")


def load_evaluations(
    manifest_path: Path,
    documents: tuple[PolicyDocument, ...],
    *,
    include_held_out: bool = False,
    split: str | None = None,
) -> tuple[dict, ...]:
    if split not in (None, "development", "held_out") or (split and include_held_out):
        raise EvaluationError("Select one split or the explicit integrity check, not both.")
    manifest = _json(_read(manifest_path))
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "corpus_sha256",
        "splits",
    }:
        raise EvaluationError("Invalid evaluation manifest fields.")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise EvaluationError("Unsupported evaluation manifest version.")
    if manifest["corpus_sha256"] != corpus_fingerprint(documents):
        raise EvaluationError("Evaluation corpus fingerprint mismatch.")
    splits = manifest["splits"]
    if not isinstance(splits, dict) or set(splits) != {"development", "held_out"}:
        raise EvaluationError("Expected development and held_out splits.")
    selected = (
        (split,)
        if split
        else (("development", "held_out") if include_held_out else ("development",))
    )
    cases: list[dict] = []
    seen_ids: set[str] = set()
    seen_queries: set[tuple[str, str]] = set()
    by_id = {doc.doc_id: doc for doc in documents}
    for split in selected:
        record = splits[split]
        if not isinstance(record, dict) or set(record) != {"path", "count", "sha256"}:
            raise EvaluationError("Invalid split fields.")
        count = 16 if split == "development" else 24
        if record["path"] != f"{split}.jsonl" or type(record["count"]) is not int:
            raise EvaluationError("Invalid split path or count.")
        if record["count"] != count:
            raise EvaluationError("Expected a 16/24 development/held-out split.")
        text = _read(manifest_path.parent / record["path"])
        if text_fingerprint(text) != record["sha256"]:
            raise EvaluationError(f"{split} fixture fingerprint mismatch.")
        lines = text.splitlines()
        if len(lines) != count:
            raise EvaluationError("Split case count mismatch.")
        for line in lines:
            case = _json(line)
            _validate_case(case, split, by_id)
            query_key = (case["identity"], " ".join(case["query"].casefold().split()))
            if case["case_id"] in seen_ids or query_key in seen_queries:
                raise EvaluationError("Duplicate case ID or identity/query pair across fixtures.")
            seen_ids.add(case["case_id"])
            seen_queries.add(query_key)
            cases.append(case)
    return tuple(cases)
