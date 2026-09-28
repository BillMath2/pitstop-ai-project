"""Strict output contracts and code-resolved evidence citations."""

import json
import re
from dataclasses import dataclass
from typing import Literal

Status = Literal[
    "answered", "insufficient_evidence", "needs_clarification", "unsupported", "no_records", "error"
]
INSUFFICIENT_MESSAGE = (
    "The supplied evidence does not answer this question. "
    "Suggested next step: ask the service desk to confirm the missing terms "
    "or request manager review. This is not an approval or a change of access."
)


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
        value = {"kind": self.citation.kind, "id": self.citation.id, "content": self.content}
        if self.citation.kind == "policy":
            value["policy_sentences"] = [
                {"index": i, "text": text} for i, text in enumerate(policy_sentences(self.content))
            ]
        return value


def policy_sentences(content: str) -> list[str]:
    """Stable source spans for this small Markdown corpus, not a general NLP parser.

    Model-selected indices resolve here, never to model-rewritten quotations.
    Headings are metadata; whitespace normalization retains sentence content.
    """
    body = " ".join(line for line in content.splitlines() if not line.lstrip().startswith("#"))
    sentences = []
    for part in re.split(r"(?<=[.!?])\s+", " ".join(body.split())):
        # Keep the qualifier after time abbreviations attached to its sentence.
        if sentences and re.search(r"\b[ap]\.m\.$", sentences[-1], re.I):
            sentences[-1] += " " + part
        else:
            sentences.append(part)
    return sentences


@dataclass(frozen=True)
class Answer:
    status: Status
    text: str
    citations: tuple[Citation, ...] = ()


def validate_answer(value: dict, evidence: tuple[Evidence, ...]) -> Answer:
    # Accept the original contract for recorded scripted fixtures; live calls
    # request the strict schema including policy_requirements.
    if set(value) not in (
        {"status", "text", "citations"},
        {"status", "text", "citations", "policy_requirements"},
    ):
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
    requirements = value.get("policy_requirements", [])
    if isinstance(requirements, dict):
        categories = ("records", "timing", "approvals_and_handling", "follow_up", "limits")
        if set(requirements) != set(categories) or any(
            not isinstance(requirements[c], list) or len(requirements[c]) > 3 for c in categories
        ):
            raise AgentError("invalid_policy_requirements")
        requirements = [item for category in categories for item in requirements[category]]
    if not isinstance(requirements, list) or len(requirements) > 15:
        raise AgentError("invalid_policy_requirements")
    policy_sources = {
        item.citation.id: item.content for item in evidence if item.citation.kind == "policy"
    }
    expanded = []
    for item in requirements:
        if isinstance(item, dict) and set(item) == {"id", "sentence_indices"}:
            doc_id, indices = item["id"], item["sentence_indices"]
            if (
                not isinstance(doc_id, str)
                or doc_id not in policy_sources
                or not isinstance(indices, list)
                or not 1 <= len(indices) <= 12
            ):
                raise AgentError("invalid_policy_requirements")
            sentences = policy_sentences(policy_sources[doc_id])
            if any(type(i) is not int or not 0 <= i < len(sentences) for i in indices):
                raise AgentError("invalid_policy_requirements")
            expanded.extend({"id": doc_id, "quote": sentences[i]} for i in indices)
        else:
            # Historical regression artifacts used verbatim quote strings.
            expanded.append(item)
    quoted = []
    quoted_ids = set()
    for item in expanded:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "quote"}
            or not isinstance(item["id"], str)
            or not isinstance(item["quote"], str)
            or not 1 <= len(item["quote"].strip()) <= 1600
            or item["id"] not in policy_sources
        ):
            raise AgentError("invalid_policy_requirements")
        quote = " ".join(item["quote"].split())
        source = " ".join(policy_sentences(policy_sources[item["id"]]))
        # Require complete sentence spans, not an arbitrary substring that can
        # silently drop a preceding negation. Source relevance remains reviewed.
        spans = list(re.finditer(re.escape(quote), source))
        if not any(
            (m.start() == 0 or source[: m.start()].rstrip().endswith((".", "!", "?")))
            and quote.endswith((".", "!", "?"))
            and (m.end() == len(source) or source[m.end()].isspace())
            for m in spans
        ):
            raise AgentError("invalid_policy_requirements")
        entry = f'- "{quote}" [{item["id"]}]'
        if entry not in quoted:
            quoted.append(entry)
        quoted_ids.add(item["id"])
        citation = allowed[("policy", item["id"])]
        if citation not in citations:
            citations.append(citation)
    status = value["status"]
    # An explicit admission that the requested term is absent must not be
    # labeled an answer merely because a related procedure was found. This
    # conservative consistency check does not infer truth from citation presence.
    if policy_sources and re.search(
        r"\b(?:not\s+(?:explicitly\s+)?(?:specified|stated|provided|defined)"
        r"|(?:polic(?:y|ies)|evidence)\s+(?:do|does)\s+not\s+"
        r"(?:explicitly\s+)?(?:specify|state|provide|establish|define))\b",
        policy_sentences(text)[0],
        re.I,
    ):
        status = "insufficient_evidence"
    if status == "insufficient_evidence":
        text = INSUFFICIENT_MESSAGE
        # Preserve explicit coordinator contact instructions from selected,
        # authorized sources even when the model selects only a scope limit.
        # Quote the original condition; do not invent a coordinator's authority.
        has_coordinator = False
        for citation in citations:
            if citation.kind != "policy":
                continue
            for sentence in policy_sentences(policy_sources[citation.id]):
                if re.search(r"\b(?:ask|send|contact|refer)\b.*\bcoordinator\b", sentence, re.I):
                    has_coordinator = True
                    entry = f'- "{sentence}" [{citation.id}]'
                    if entry not in quoted:
                        quoted.append(entry)
                    quoted_ids.add(citation.id)
        if has_coordinator:
            text += (
                " For confirmation, contact the coordinator identified "
                "in the source guidance below."
            )
        # Only verified source quotations survive an abstention; a valid
        # citation alone cannot authorize invented guidance or echo a guess.
        citations = [c for c in citations if c.kind == "policy" and c.id in quoted_ids]
    if quoted:
        text = (
            text.strip()
            + "\n\nRelevant policy requirements (source quotations):\n"
            + "\n".join(quoted)
        )
    if len(text) > 12_000:
        raise AgentError("invalid_answer")
    return Answer(status, text.strip(), tuple(citations))
