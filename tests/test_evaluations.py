"""Check schema/integrity with development and synthetic fixtures only."""

import json
import shutil
from pathlib import Path

import pytest

from dealer_evidence_agent.corpus import load_corpus, text_fingerprint
from dealer_evidence_agent.evaluations import EvaluationError, load_evaluations

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixtures(tmp_path):
    for name in ("manifest.json", "development.jsonl"):
        shutil.copyfile(ROOT / "evals" / name, tmp_path / name)
    return tmp_path / "manifest.json", load_corpus(ROOT / "data/manifest.json")


def rewrite_cases(path, cases, split="development"):
    text = "".join(json.dumps(case) + "\n" for case in cases)
    (path.parent / f"{split}.jsonl").write_text(text, encoding="utf-8")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["splits"][split]["sha256"] = text_fingerprint(text)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_default_never_opens_held_out(fixtures):
    path, documents = fixtures
    assert not (path.parent / "held_out.jsonl").exists()
    assert len(load_evaluations(path, documents)) == 16
    with pytest.raises(EvaluationError, match="held_out"):
        load_evaluations(path, documents, include_held_out=True)


def test_development_category_coverage(fixtures):
    cases = load_evaluations(*fixtures)
    assert {case["category"] for case in cases} == {
        "policy",
        "permission",
        "missing_evidence",
        "recall",
        "clarification",
        "unknown_identity",
    }
    assert {case["identity"] for case in cases} >= {"tech_demo", "manager_demo"}


def test_split_tamper_is_detected(fixtures):
    path, documents = fixtures
    with (path.parent / "development.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(EvaluationError, match="fixture fingerprint"):
        load_evaluations(path, documents)


def test_corpus_drift_is_detected(fixtures):
    path, documents = fixtures
    with pytest.raises(EvaluationError, match="corpus fingerprint"):
        load_evaluations(path, documents[:-1])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_ids", ["manager_goodwill_review"]),
        ("document_ids", ["missing_id"]),
        ("route", "lookup_recalls"),
        ("required_facts", []),
        ("forbidden_claims", "none"),
        ("tool_arguments", {"identity": "manager_demo"}),
    ],
)
def test_rejects_invalid_expectations(fixtures, field, value):
    path, documents = fixtures
    cases = list(load_evaluations(path, documents))
    cases[0]["expected"][field] = value
    rewrite_cases(path, cases)
    with pytest.raises(EvaluationError):
        load_evaluations(path, documents)


@pytest.mark.parametrize("change", ["duplicate", "split", "identity", "count", "recall_year"])
def test_rejects_inconsistent_cases(fixtures, change):
    path, documents = fixtures
    cases = list(load_evaluations(path, documents))
    if change == "duplicate":
        cases[1] = cases[0]
    elif change == "split":
        cases[0]["split"] = "held_out"
    elif change == "identity":
        cases[0]["identity"] = "admin"
    elif change == "count":
        cases.pop()
    else:
        recall = next(case for case in cases if case["category"] == "recall")
        recall["expected"]["tool_arguments"]["year"] = True
    rewrite_cases(path, cases)
    with pytest.raises(EvaluationError):
        load_evaluations(path, documents)


def test_explicit_full_validation_with_synthetic_held_out(fixtures):
    path, documents = fixtures
    template = load_evaluations(path, documents)[0]
    synthetic = [
        dict(
            template,
            case_id=f"held_{index:03d}",
            split="held_out",
            query=f"Synthetic schema test {index}",
        )
        for index in range(24)
    ]
    rewrite_cases(path, synthetic, "held_out")
    assert len(load_evaluations(path, documents, include_held_out=True)) == 40
    synthetic[0]["query"] = template["query"]
    rewrite_cases(path, synthetic, "held_out")
    with pytest.raises(EvaluationError, match="Duplicate"):
        load_evaluations(path, documents, include_held_out=True)


def test_explicit_split_opens_only_selected_synthetic_file(fixtures):
    path, documents = fixtures
    template = load_evaluations(path, documents)[0]
    synthetic = [
        dict(template, case_id=f"held_{i:03d}", split="held_out", query=f"Synthetic split test {i}")
        for i in range(24)
    ]
    rewrite_cases(path, synthetic, "held_out")
    (path.parent / "development.jsonl").unlink()
    assert len(load_evaluations(path, documents, split="held_out")) == 24
    with pytest.raises(EvaluationError, match="Select one split"):
        load_evaluations(path, documents, split="held_out", include_held_out=True)
