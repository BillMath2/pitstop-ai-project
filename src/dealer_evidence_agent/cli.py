"""Offline entry point; only implemented commands are advertised."""

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from dealer_evidence_agent.corpus import CorpusError, corpus_fingerprint, load_corpus
from dealer_evidence_agent.evaluations import EvaluationError, load_evaluations
from dealer_evidence_agent.permissions import AuthorizationError, authorized_documents, resolve_role


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dealer-evidence",
        description="Dealer Evidence Agent: offline corpus, permissions, and fixtures (M1).",
    )
    parser.add_argument("--version", action="version", version=version("dealer-evidence-agent"))
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-corpus", help="Validate policy metadata and files.")
    listing = commands.add_parser("list-policies", help="List policies visible to a demo identity.")
    listing.add_argument("--identity", required=True, help="tech_demo or manager_demo")
    evaluations = commands.add_parser(
        "validate-evals", help="Validate offline evaluation fixtures."
    )
    evaluations.add_argument("--eval-manifest", type=Path, default=Path("evals/manifest.json"))
    evaluations.add_argument(
        "--include-held-out",
        action="store_true",
        help="Explicit authoring/release check of both splits; never use for tuning.",
    )
    for command in (validate, listing, evaluations):
        command.add_argument(
            "--manifest",
            type=Path,
            default=Path("data/manifest.json"),
            help="Corpus manifest (default: data/manifest.json, relative to working directory).",
        )
    args = parser.parse_args(argv)
    try:
        if args.command == "list-policies":
            resolve_role(args.identity)
        documents = load_corpus(args.manifest)
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
    except (AuthorizationError, EvaluationError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    shared = sum(document.visibility == "shared" for document in documents)
    print(
        f"Valid corpus: {len(documents)} documents "
        f"({shared} shared, {len(documents) - shared} manager_only)."
    )
    print(f"Corpus SHA-256: {corpus_fingerprint(documents)}")
    return 0
