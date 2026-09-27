"""Strict output contracts and code-resolved evidence citations."""

import json
from dataclasses import dataclass
from typing import Literal

Status = Literal[
    "answered", "insufficient_evidence", "needs_clarification", "unsupported", "no_records", "error"
]


class AgentError(ValueError):
    """A safe, fixed error code; never include upstream or restricted content."""


def parse_json(text: str, *, max_chars: int = 24_000) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("Nonfinite JSON")

    try:
        if not isinstance(text, str) or len(text) > max_chars:
            raise ValueError("Invalid size")
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
        if not isinstance(value, dict):
            raise ValueError("Expected object")
        return value
    except (ValueError, TypeError, RecursionError) as exc:
        raise AgentError("invalid_model_output") from exc


@dataclass(frozen=True)
class Citation:
    kind: Literal["policy", "recall_campaign", "recall_response"]
    id: str
    source: str


@dataclass(frozen=True)
class Evidence:
    citation: Citation
    content: str

    def payload(self) -> dict:
        return {"kind": self.citation.kind, "id": self.citation.id, "content": self.content}


@dataclass(frozen=True)
class Answer:
    status: Status
    text: str
    citations: tuple[Citation, ...] = ()


def validate_answer(value: dict, evidence: tuple[Evidence, ...]) -> Answer:
    if set(value) != {"status", "text", "citations"}:
        raise AgentError("invalid_answer")
    if value["status"] not in ("answered", "insufficient_evidence"):
        raise AgentError("invalid_answer")
    text, refs = value["text"], value["citations"]
    if not isinstance(text, str) or not text.strip() or len(text) > 6000:
        raise AgentError("invalid_answer")
    if not isinstance(refs, list) or len(refs) > len(evidence):
        raise AgentError("invalid_citation")
    allowed = {(item.citation.kind, item.citation.id): item.citation for item in evidence}
    citations = []
    for ref in refs:
        if (
            not isinstance(ref, dict)
            or set(ref) != {"kind", "id"}
            or not all(isinstance(v, str) for v in ref.values())
        ):
            raise AgentError("invalid_citation")
        citation = allowed.get((ref["kind"], ref["id"]))
        if citation is None or citation in citations:
            raise AgentError("invalid_citation")
        citations.append(citation)
    if value["status"] == "answered" and not citations:
        raise AgentError("missing_citation")
    if value["status"] == "insufficient_evidence":
        # A model abstention cannot smuggle unsupported facts into a factual answer.
        return Answer(
            "insufficient_evidence", "The supplied evidence does not answer this question."
        )
    return Answer("answered", text.strip(), tuple(citations))
