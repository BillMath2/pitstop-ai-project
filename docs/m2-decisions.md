# M2: permission-scoped BM25 retrieval

Implementation date: 2026-09-26. Scope: deterministic offline policy search,
bounded source excerpts, and development-only retrieval metrics. M1 was committed
as `2d80f8e` before this work. Its corpus, fixtures, and fingerprints are unchanged.

## Search contract

`PolicySearch(documents, identity=...)` binds a validated corpus snapshot to the
trusted request identity. Its `search_policies(query, top_k=3)` method accepts
only query text and a bounded result count; query content cannot change roles.
Future tool binding must obtain identity from request context, not model output.

The constructor calls `authorized_documents()` before retaining, tokenizing,
fingerprinting, or indexing records. Thus a technician index contains exactly the
16 shared policies; manager indexes contain all 24. Unknown identities fail before
index creation, and the CLI also rejects them before reading the corpus. The
corpus loader remains a trusted administrative operation over the full corpus.

Each instance owns its authorized document tuple and index. There is no cross-role
cache or broader-index fallback. Create a new instance for a changed identity or
corpus. A technician's returned scope fingerprint includes only visible records;
private text/metadata changes cannot affect that fingerprint or search scores.
This enforces the demo application boundary, not filesystem protection or login.

## Ranking and excerpt choices

- `rank-bm25==0.2.2`, `BM25Okapi`, k1=1.5, b=0.75, epsilon=0.25.
- Tokenize title plus full Markdown text into case-folded Unicode words/numbers;
  drop a fixed small English stopword list. Keep amounts and negations. No
  stemming, synonym expansion, learned reranking, or per-case special handling.
- Deduplicate query terms. Rank documents with at least one remaining query-term
  overlap; break score ties by document ID. Sorting the index by ID also makes
  manifest order irrelevant.
- Default k=3, allowed range 1..5. Queries must be nonblank strings of at most
  1,000 characters; invalid input is an error. Punctuation-only, stopword-only,
  absent-term, and empty-scope searches return `no_match` without fabricated hits.
- Keep legitimate overlapping documents even when BM25 gives zero or negative
  scores, which can occur in small authorized scopes. Do not use a score-sign
  filter, probability interpretation, or cross-role score comparison.
- Choose one contiguous excerpt per hit, at most 480 characters, from a paragraph
  window covering the most distinct query terms. Break ties by earliest source
  offset. Long paragraphs use windows near matches. Excerpts are exact slices,
  with no generated text or hidden expansion; windows can clip a sentence.

Each hit includes ID, title, relative path, version, normalized-text SHA-256,
score, excerpt, zero-based end-exclusive character offsets, and one-based
inclusive source lines. The response includes `matches`/`no_match`, the retrieval
version `bm25-okapi-v1`, and an authorized-scope fingerprint. Offsets refer to the
UTF-8 source text read with normalized newlines, consistent with M1 hashing.

An excerpt may omit relevant conditions elsewhere in a policy. Neither a high
BM25 score nor document recall proves answerability or complete factual coverage.
Future answer verification must handle insufficient evidence and must not claim
approval, recall status, or safety from these search results alone.

## Commands

```powershell
.\.venv\Scripts\dealer-evidence.exe search-policies "loaner return keys" --identity tech_demo
.\.venv\Scripts\dealer-evidence.exe search-policies "goodwill credit" --identity manager_demo --json
.\.venv\Scripts\dealer-evidence.exe eval-retrieval
```

Both commands support `--manifest PATH` and `--top-k 1..5`; the evaluator also
accepts `--eval-manifest PATH`. The evaluator is a local administrative report,
not a model tool. It validates and reads development cases only, and has no
held-out option. No credentials, network, model, or recall service are needed.

## Development baseline

The baseline uses the library defaults above, without ranking changes after
seeing development results. Expected IDs are consulted after retrieval only.

| Measurement at k=3 | Result |
| --- | --- |
| Policy-answer cases | 6 |
| Mean document recall@3 | 1.0 |
| Mean reciprocal rank@3 | 1.0 |
| Unauthorized returned hits across 10 searches | 0 |
| Explicitly forbidden returned hits | 0 |
| Unknown identities rejected | 1 of 1 |
| Recall/clarification cases skipped | 5 |

Both missing-evidence cases returned lexical matches. This is recorded as search
behavior, not a successful answer or abstention. Permission cases likewise test
absence of restricted evidence, not final refusal wording. No routing, factual
answer, excerpt completeness, recall API, or held-out quality was measured.

Corpus SHA-256:
`bbdaab8b32afbd6ac22bcfb785cd9add12c7484a7b77397846d2ede5d850dc4e`

Development-file SHA-256:
`cf4369bd8bb2637c3d4c5a425e08121293d31746f188f79b979a1a0f1096d6fb`

## Verification

- Offline suite: **106 passed, 1 skipped**. The existing symlink-escape check
  still requires Windows symlink creation permission.
- Tests instrument tokenization and BM25 construction to reject restricted
  content; changing/adding private policies cannot change technician scores or
  fingerprints. Alternating roles cannot reuse a broader index.
- Tests cover query role-injection attempts, unknown identities before indexing,
  exact bounded excerpts and source offsets, long-paragraph matches, deterministic
  ties, empty scopes, zero/negative scores, argument limits, and CLI JSON/errors.
- Development evaluation succeeds when the real held-out file is absent. No
  held-out questions or expected answers were read or scored during M2.
- Ruff lint, formatting, and diff whitespace checks pass. Corpus and development
  fixture fingerprints still validate. The wheel builds offline and contains the
  new retrieval modules without credentials, local caches, corpus, or fixtures.

Next is M3: public NHTSA recall lookup and versioned response/error fixtures.
