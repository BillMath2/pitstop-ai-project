"""CLI with explicit live recall access and offline policy/fixture commands."""

import argparse
import json
import sys
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from dealer_evidence_agent.corpus import CorpusError, corpus_fingerprint, load_corpus
from dealer_evidence_agent.evaluations import EvaluationError, load_evaluations
from dealer_evidence_agent.permissions import AuthorizationError, authorized_documents, resolve_role
from dealer_evidence_agent.recall_fixtures import (
    DEFAULT_FIXTURE_MANIFEST,
    RecallFixtureError,
    replay_recalls,
    validate_recall_fixtures,
)
from dealer_evidence_agent.recalls import (
    DEFAULT_LIMIT,
    RecallInputError,
    RecallLookup,
    RecallResult,
)
from dealer_evidence_agent.retrieval import (
    DEFAULT_TOP_K,
    PolicySearch,
    SearchError,
    validate_search,
)
from dealer_evidence_agent.retrieval_evaluation import evaluate_retrieval


def _print_recalls(result: RecallResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, allow_nan=False))
        return
    print(f"Recall lookup: {result.status} | source: {result.source}")
    print(f"Source URL: {result.source_url}")
    if result.observed_at is not None:
        print(f"Observed at: {result.observed_at}")
    if result.fixture_id is not None:
        print(f"Fixture: {result.fixture_id} (offline replay, not a current lookup)")
    if result.body_sha256 is not None:
        print(f"Response SHA-256: {result.body_sha256}")
    if result.error:
        print(result.error)
    elif result.status == "empty":
        print("No records were returned for this combination.")
    else:
        print(f"Showing {len(result.records)} of {result.total_count} campaign records.")
        if result.truncated:
            print("Results are truncated; this is not the complete response.")
        for record in result.records:
            print(f"\n{record.campaign_number} | {record.component}")
            print(f"Report received (source date): {record.report_received_date}")
            print(f"Summary: {record.summary}")
            print(f"Consequence: {record.consequence or 'Not supplied'}")
            print(f"Remedy: {record.remedy or 'Not supplied'}")
            print(
                f"Source flags: parkIt={record.park_it}, parkOutSide={record.park_outside}, "
                f"overTheAirUpdate={record.over_the_air_update}"
            )
    print(result.boundary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dealer-evidence",
        description="Dealer Evidence Agent: policy search and public recall evidence (M3).",
    )
    parser.add_argument("--version", action="version", version=version("dealer-evidence-agent"))
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-corpus", help="Validate policy metadata and files.")
    listing = commands.add_parser("list-policies", help="List policies visible to a demo identity.")
    listing.add_argument("--identity", required=True, help="tech_demo or manager_demo")
    recalls = commands.add_parser("lookup-recalls", help="Look up general NHTSA recall campaigns.")
    recalls.add_argument("--identity", required=True, help="tech_demo or manager_demo")
    recalls.add_argument("--make", required=True)
    recalls.add_argument("--model", required=True)
    recalls.add_argument("--year", required=True, type=int)
    recalls.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="Records: 1 to 10 (default 5)"
    )
    recalls.add_argument("--json", action="store_true")
    mode = recalls.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--live", action="store_true", help="Make one request to the public NHTSA API"
    )
    mode.add_argument("--fixture", help="Replay a recorded or synthetic fixture ID without network")
    recalls.add_argument("--fixture-manifest", type=Path, default=DEFAULT_FIXTURE_MANIFEST)
    recall_validation = commands.add_parser(
        "validate-recall-fixtures",
        help="Check recall fixture integrity and replay statuses offline.",
    )
    recall_validation.add_argument(
        "--fixture-manifest", type=Path, default=DEFAULT_FIXTURE_MANIFEST
    )
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
        if args.command == "lookup-recalls":
            resolve_role(args.identity)
            if args.live:
                result = RecallLookup(identity=args.identity).lookup_recalls(
                    args.make, args.model, args.year, limit=args.limit
                )
            else:
                result = replay_recalls(
                    args.fixture_manifest,
                    args.fixture,
                    identity=args.identity,
                    make=args.make,
                    model=args.model,
                    year=args.year,
                    limit=args.limit,
                )
            _print_recalls(result, args.json)
            return 0 if result.status in {"ok", "empty"} else 1
        if args.command == "validate-recall-fixtures":
            report = validate_recall_fixtures(args.fixture_manifest)
            print(json.dumps(report, indent=2))
            return 0
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
    except (
        AuthorizationError,
        EvaluationError,
        SearchError,
        RecallInputError,
        RecallFixtureError,
    ) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    shared = sum(document.visibility == "shared" for document in documents)
    print(
        f"Valid corpus: {len(documents)} documents "
        f"({shared} shared, {len(documents) - shared} manager_only)."
    )
    print(f"Corpus SHA-256: {corpus_fingerprint(documents)}")
    return 0
