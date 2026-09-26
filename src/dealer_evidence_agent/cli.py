"""Offline entry point; only implemented commands are advertised."""

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from dealer_evidence_agent.corpus import CorpusError, load_corpus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dealer-evidence",
        description="Dealer Evidence Agent: validate the fictional starter corpus (M0).",
    )
    parser.add_argument("--version", action="version", version=version("dealer-evidence-agent"))
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-corpus", help="Validate policy metadata and files.")
    validate.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/manifest.json"),
        help="Manifest path (default: data/manifest.json, relative to the working directory).",
    )
    args = parser.parse_args(argv)
    try:
        documents = load_corpus(args.manifest)
    except CorpusError as exc:
        print(f"Corpus validation failed: {exc}", file=sys.stderr)
        return 1
    shared = sum(document.visibility == "shared" for document in documents)
    print(
        f"Valid corpus: {len(documents)} documents "
        f"({shared} shared, {len(documents) - shared} manager_only)."
    )
    return 0
