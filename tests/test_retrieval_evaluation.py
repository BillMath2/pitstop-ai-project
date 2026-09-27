"""Development baseline and isolation from real held-out fixtures."""

import shutil
from pathlib import Path

import pytest

from dealer_evidence_agent.corpus import load_corpus
from dealer_evidence_agent.retrieval import SearchError
from dealer_evidence_agent.retrieval_evaluation import evaluate_retrieval

ROOT = Path(__file__).resolve().parents[1]


def test_development_baseline_without_held_out_file(tmp_path):
    for name in ("manifest.json", "development.jsonl"):
        shutil.copyfile(ROOT / "evals" / name, tmp_path / name)
    documents = load_corpus(ROOT / "data/manifest.json")
    report = evaluate_retrieval(documents, tmp_path / "manifest.json")
    assert report["split"] == "development"
    assert report["policy_cases"] == 6
    assert report["mean_recall_at_k"] == 1.0
    assert report["mean_reciprocal_rank_at_k"] == 1.0
    assert report["unauthorized_hits"] == report["forbidden_hits"] == 0
    assert report["unknown_identities_rejected"] == 1
    assert report["skipped_cases"] == 5
    assert len(report["cases"]) == 11
    # Abstention is an answer-layer behavior, not an inference from lexical overlap.
    missing = [row for row in report["cases"] if row["category"] == "missing_evidence"]
    assert len(missing) == 2
    assert all("recall_at_k" not in row for row in missing)
    assert "No routing" in report["limitations"]


def test_invalid_evaluation_limit_is_rejected_before_fixture_io(tmp_path):
    with pytest.raises(SearchError):
        evaluate_retrieval((), tmp_path / "missing.json", top_k=True)
