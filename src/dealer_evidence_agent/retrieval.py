"""Deterministic BM25 over an identity's authorized policy snapshot only."""

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from dealer_evidence_agent.corpus import PolicyDocument, corpus_fingerprint
from dealer_evidence_agent.permissions import authorized_documents

RETRIEVAL_VERSION = "bm25-okapi-v1"
DEFAULT_TOP_K = 3
MAX_TOP_K = 5
MAX_QUERY_CHARS = 1000
MAX_SNIPPET_CHARS = 480
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_STOPWORDS = frozenset(
    "a an and are as at be been but by can could did do does for from had has have "
    "how i if in into is it its may me my of on or our should that the their them "
    "there these they this those to us was we were what when where which who will "
    "with would you your".split()
)


class SearchError(ValueError):
    """Invalid search input, distinct from a valid query without lexical matches."""


def tokenize(text: str) -> tuple[str, ...]:
    """Case-fold Unicode words/numbers; no stemming or corpus-specific synonyms."""
    return tuple(word for word in _WORDS.findall(text.casefold()) if word not in _STOPWORDS)


def validate_search(query: str, top_k: int) -> None:
    if not isinstance(query, str) or not query.strip():
        raise SearchError("Query must be a nonempty string.")
    if len(query) > MAX_QUERY_CHARS:
        raise SearchError(f"Query must be at most {MAX_QUERY_CHARS} characters.")
    if type(top_k) is not int or not 1 <= top_k <= MAX_TOP_K:
        raise SearchError(f"top_k must be an integer from 1 to {MAX_TOP_K}.")


@dataclass(frozen=True)
class PolicyHit:
    doc_id: str
    title: str
    path: str
    version: str
    sha256: str
    score: float
    snippet: str
    start_char: int
    end_char: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class SearchResult:
    status: str
    retrieval_version: str
    scope_sha256: str
    hits: tuple[PolicyHit, ...]


def _excerpt(text: str, query_terms: frozenset[str]) -> tuple[int, int]:
    """Choose a contiguous source window within a paragraph, preserving exact text."""
    windows: set[tuple[int, int]] = set()
    for paragraph in re.finditer(r"\S[\s\S]*?(?=\n[ \t]*\n|\Z)", text):
        start, end = paragraph.span()
        starts = {start}
        if end - start > MAX_SNIPPET_CHARS:
            for word in _WORDS.finditer(paragraph.group()):
                if word.group().casefold() in query_terms:
                    starts.add(
                        max(
                            start,
                            min(
                                start + word.start() - MAX_SNIPPET_CHARS // 3,
                                end - MAX_SNIPPET_CHARS,
                            ),
                        )
                    )
        windows.update((offset, min(offset + MAX_SNIPPET_CHARS, end)) for offset in starts)
    if not windows:
        return 0, min(len(text), MAX_SNIPPET_CHARS)
    return min(
        windows,
        key=lambda span: (
            -len(query_terms.intersection(tokenize(text[span[0] : span[1]]))),
            span[0],
            span[1],
        ),
    )


class PolicySearch:
    """Bound to a trusted request identity; queries cannot select or change roles.

    Only authorized documents are retained, tokenized, indexed, and excerpted.
    Construct a new instance when the corpus or identity changes. No shared cache
    or fallback to a broader index is used.
    """

    def __init__(self, documents: tuple[PolicyDocument, ...], *, identity: str):
        visible = authorized_documents(documents, identity)
        self._documents = tuple(sorted(visible, key=lambda doc: doc.doc_id))
        self.scope_sha256 = corpus_fingerprint(self._documents)
        tokens = [tokenize(f"{doc.title}\n{doc.text}") for doc in self._documents]
        self._terms = tuple(frozenset(words) for words in tokens)
        self._index = BM25Okapi(tokens, k1=1.5, b=0.75, epsilon=0.25) if any(tokens) else None

    def search_policies(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> SearchResult:
        validate_search(query, top_k)
        # Repeating a query term must not inflate its weight.
        terms = tuple(dict.fromkeys(tokenize(query)))
        query_terms = frozenset(terms)
        hits: list[PolicyHit] = []
        if terms and self._index is not None:
            scores = self._index.get_scores(terms)
            # Gate on lexical overlap, not score sign: Okapi scores can be zero
            # or negative for common terms in very small authorized corpora.
            candidates = [i for i, words in enumerate(self._terms) if words & query_terms]
            candidates.sort(key=lambda i: (-float(scores[i]), self._documents[i].doc_id))
            for index in candidates[:top_k]:
                doc = self._documents[index]
                start, end = _excerpt(doc.text, query_terms)
                hits.append(
                    PolicyHit(
                        doc_id=doc.doc_id,
                        title=doc.title,
                        path=doc.path,
                        version=doc.version,
                        sha256=doc.sha256,
                        score=float(scores[index]),
                        snippet=doc.text[start:end],
                        start_char=start,
                        end_char=end,
                        start_line=doc.text.count("\n", 0, start) + 1,
                        end_line=doc.text.count("\n", 0, max(start, end - 1)) + 1,
                    )
                )
        return SearchResult(
            status="matches" if hits else "no_match",
            retrieval_version=RETRIEVAL_VERSION,
            scope_sha256=self.scope_sha256,
            hits=tuple(hits),
        )
