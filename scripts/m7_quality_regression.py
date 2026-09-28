"""Explicit live regression on exposed cases; never fresh held-out validation.

Uses recorded recall responses only. No live NHTSA requests. Outputs and per-case
traces are saved in a new ignored directory; original M7 evidence is untouched.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from dealer_evidence_agent.corpus import load_corpus
from dealer_evidence_agent.evaluation import evaluate_agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--split", choices=("development", "held_out"), default="held_out")
    args = parser.parse_args()
    output = Path("runs") / f"m7-quality-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    output.mkdir(parents=True, exist_ok=False)
    report = evaluate_agent(
        load_corpus(Path("data/manifest.json")),
        Path("evals/manifest.json"),
        mode="live-model",
        split=args.split,
        runs_dir=output / "traces",
        env_file=args.env_file,
        fixture_manifest=Path(
            "data/recalls/v2/manifest.json"
            if args.split == "held_out"
            else "data/recalls/v1/manifest.json"
        ),
    )
    report["evaluation_kind"] = "exposed_case_regression_not_fresh_holdout"
    report["fresh_holdout"] = False
    report["quality_review"] = "pending; mechanical passes are not semantic quality"
    destination = output / "report.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "report": str(destination),
                "automatic_passes": report["automatic_passes"],
                "case_count": report["case_count"],
                "fresh_holdout": False,
            }
        )
    )
    return int(report["automatic_passes"] != report["case_count"])


if __name__ == "__main__":
    raise SystemExit(main())
