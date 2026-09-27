"""Explicit live-model DEVELOPMENT smoke; recall data is always labeled fixture replay.

Run from the repository root with Python 3.12. This is not held-out evaluation.
Outputs stay under ignored runs/. No credentials or raw provider messages are saved.
"""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from dealer_evidence_agent.corpus import corpus_fingerprint, load_corpus
from dealer_evidence_agent.graph import run_agent
from dealer_evidence_agent.model_client import ModelClient
from dealer_evidence_agent.prompts import PROMPT_VERSION
from dealer_evidence_agent.recall_fixtures import DEFAULT_FIXTURE_MANIFEST, replay_recalls
from dealer_evidence_agent.tracing import JsonlTrace

CASES = {"dev_001", "dev_005", "dev_006", "dev_008", "dev_011", "dev_014", "dev_015"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    documents = load_corpus(Path("data/manifest.json"))
    rows = [json.loads(line) for line in Path("evals/development.jsonl").read_text().splitlines()]
    client = ModelClient.from_environment(args.env_file)
    stamp = datetime.now(UTC)
    archive = Path("runs") / f"m4-smoke-{stamp.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    report = {
        "mode": "live_model_development_smoke",
        "model": client.model,
        "prompt_version": PROMPT_VERSION,
        "started_at": stamp.isoformat(),
        "corpus_sha256": corpus_fingerprint(documents),
        "cases": [],
    }
    try:
        for case in rows:
            if case["case_id"] not in CASES:
                continue
            identity = case["identity"]

            def lookup(identity=identity, **arguments):
                return replay_recalls(
                    DEFAULT_FIXTURE_MANIFEST,
                    "toyota-corolla-2020",
                    identity=identity,
                    **arguments,
                )

            trace = JsonlTrace(Path("runs"))
            try:
                result = run_agent(
                    case["query"],
                    identity=identity,
                    documents=documents,
                    model=client,
                    trace=trace,
                    recall_lookup=lookup,
                )
            finally:
                trace.close()
            record = {"case_id": case["case_id"], "run_id": trace.run_id, **asdict(result)}
            # Source text is already available in the corpus/fixtures; avoid duplicating it.
            record.pop("evidence")
            report["cases"].append(record)
            print(json.dumps(record), flush=True)
            if result.error_code == "provider_error":
                break
    finally:
        client.close()
        output = Path("runs") / "m4-smoke.json"
        output.parent.mkdir(exist_ok=True)
        serialized = json.dumps(report, indent=2)
        with archive.open("x", encoding="utf-8") as file:
            file.write(serialized)
        output.write_text(serialized, encoding="utf-8")
    return 1 if any(row["answer"]["status"] == "error" for row in report["cases"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
