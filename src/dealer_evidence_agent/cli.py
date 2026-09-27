"""Offline entry point; only implemented commands are advertised."""

import argparse
import json
import sys
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from dealer_evidence_agent.corpus import CorpusError, corpus_fingerprint, load_corpus
from dealer_evidence_agent.evaluations import EvaluationError, load_evaluations
from dealer_evidence_agent.permissions import AuthorizationError, authorized_documents, resolve_role
from dealer_evidence_agent.retrieval import (
    DEFAULT_TOP_K,
    PolicySearch,
    SearchError,
    validate_search,
)
from dealer_evidence_agent.retrieval_evaluation import evaluate_retrieval


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dealer-evidence",
        description="Dealer Evidence Agent: offline permission-scoped policy search (M2).",
    )
    parser.add_argument("--version", action="version", version=version("dealer-evidence-agent"))
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-corpus", help="Validate policy metadata and files.")
    listing = commands.add_parser("list-policies", help="List policies visible to a demo identity.")
    listing.add_argument("--identity", required=True, help="tech_demo or manager_demo")
    search = commands.add_parser("search-policies", help="Search authorized policies with BM25.")
    search.add_argument("query", help="Policy question (up to 1000 characters)")
    search.add_argument("--identity", required=True, help="tech_demo or manager_demo")
    search.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K, help="Results: 1 to 5 (default 3)"
    )
    search.add_argument("--json", action="store_true", help="Emit structured evidence as JSON")
    retrieval_eval = commands.add_parser(
        "eval-retrieval", help="Measure development-set retrieval only; never reads held-out cases."
    )
    retrieval_eval.add_argument("--eval-manifest", type=Path, default=Path("evals/manifest.json"))
    retrieval_eval.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    evaluations = commands.add_parser(
        "validate-evals", help="Validate offline evaluation fixtures."
    )
    evaluations.add_argument("--eval-manifest", type=Path, default=Path("evals/manifest.json"))
    evaluations.add_argument(
        "--include-held-out",
        action="store_true",
        help="Explicit authoring/release check of both splits; never use for tuning.",
    )
    for command in (validate, listing, evaluations, search, retrieval_eval):
        command.add_argument(
            "--manifest",
            type=Path,
            default=Path("data/manifest.json"),
            help="Corpus manifest (default: data/manifest.json, relative to working directory).",
        )
    args = parser.parse_args(argv)
    try:
        if args.command in {"list-policies", "search-policies"}:
            resolve_role(args.identity)
        if args.command == "search-policies":
            validate_search(args.query, args.top_k)
        if args.command == "eval-retrieval":
            validate_search("evaluation", args.top_k)
        documents = load_corpus(args.manifest)
        if args.command == "search-policies":
            result = PolicySearch(documents, identity=args.identity).search_policies(
                args.query, top_k=args.top_k
            )
            if args.json:
                print(json.dumps(asdict(result), ensure_ascii=False, indent=2, allow_nan=False))
            elif not result.hits:
                print("No matching authorized policies. Try different policy terms.")
            else:
                print("Policy search matches; excerpts are evidence candidates, not an answer.")
                for hit in result.hits:
                    print(f"\n{hit.doc_id} (v{hit.version}) | {hit.title} | BM25 {hit.score:.4f}")
                    print(
                        f"Source: {hit.path}:{hit.start_line}-{hit.end_line} "
                        f"| SHA-256: {hit.sha256}"
                    )
                    print(hit.snippet)
            return 0
        if args.command == "eval-retrieval":
            report = evaluate_retrieval(documents, args.eval_manifest, top_k=args.top_k)
            print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
            return 0
        if args.command == "list-policies":
            for document in authorized_documents(documents, args.identity):
                print(f"{document.doc_id}\t{document.title}")
            return 0
        if args.command == "validate-evals":
            cases = load_evaluations(
                args.eval_manifest, documents, include_held_out=args.include_held_out
            )
            scope = "development + held_out" if args.include_held_out else "development only"
            print(f"Valid evaluation fixtures: {len(cases)} cases ({scope}).")
            print("Structure and fingerprints checked; no agent quality evaluation performed.")
            return 0
    except CorpusError as exc:
        print(f"Corpus validation failed: {exc}", file=sys.stderr)
        return 1
    except (AuthorizationError, EvaluationError, SearchError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    shared = sum(document.visibility == "shared" for document in documents)
    print(
        f"Valid corpus: {len(documents)} documents "
        f"({shared} shared, {len(documents) - shared} manager_only)."
    )
    print(f"Corpus SHA-256: {corpus_fingerprint(documents)}")
    return 0
