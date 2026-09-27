"""Execute and deliberately break reports without accessing real held-out cases or services."""

import json
import shutil
from pathlib import Path

import pytest

from dealer_evidence_agent.cli import main
from dealer_evidence_agent.corpus import load_corpus
from dealer_evidence_agent.evaluation import DEFAULT_REPLIES, evaluate_agent
from dealer_evidence_agent.evaluations import EvaluationError, load_evaluations
from dealer_evidence_agent.model_client import ModelClient, RecordingClient


@pytest.fixture
def inputs(tmp_path):
    for name in ("manifest.json", "development.jsonl"):
        shutil.copyfile(Path("evals") / name, tmp_path / name)
    return load_corpus(Path("data/manifest.json")), tmp_path / "manifest.json"


def evaluate(inputs, tmp_path, **kwargs):
    return evaluate_agent(*inputs, mode="scripted", runs_dir=tmp_path / "runs", **kwargs)


def test_offline_report_executes_all_cases_and_keeps_semantics_ungraded(inputs, tmp_path):
    report = evaluate(inputs, tmp_path)
    assert report["case_count"] == report["automatic_passes"] == 16
    assert report["semantic_pass_rate"] is None and report["manual_review_pending"] == 16
    assert report["metrics"]["arguments"] == {"passed": 3, "total": 3}
    assert report["metrics"]["permissions"] == {"passed": 16, "total": 16}
    assert report["metrics"]["recall_outcome"] == {"passed": 3, "total": 3}
    assert report["cases"][-1]["model_calls"] == report["cases"][-1]["tool_calls"] == 0
    assert len(list((tmp_path / "runs").glob("*.jsonl"))) == 16
    assert report["cases"][0]["providers"] == ["recording_fake"]
    assert "NOT model quality" in report["limitations"]
    assert len(report["cases_sha256"]) == len(report["code"]["source_sha256"]) == 64


@pytest.mark.parametrize("fault", ["route", "arguments", "disposition", "citation"])
def test_bad_outputs_are_failures_not_omitted_cases(inputs, tmp_path, fault):
    scripts = json.loads(DEFAULT_REPLIES.read_text())
    case_id = "dev_011" if fault in ("route", "arguments") else "dev_001"
    replies = scripts["cases"][case_id]
    if fault == "route":
        replies[0] = {"decision": {"action": "search_policies", "arguments": {"query": "loaner"}}}
    elif fault == "arguments":
        replies[0]["decision"]["arguments"]["year"] = 2021
    elif fault == "disposition":
        replies[1] = {"status": "insufficient_evidence", "text": "Cannot answer", "citations": []}
    else:
        replies[1]["citations"][0]["id"] = "manager_goodwill_review"
    path = tmp_path / "replies.json"
    path.write_text(json.dumps(scripts))
    report = evaluate(inputs, tmp_path, replies_path=path)
    assert report["case_count"] == 16 and report["automatic_passes"] == 15
    failed = next(r for r in report["cases"] if r["case_id"] == case_id)
    assert not failed["automatic_pass"]
    if fault == "citation":
        assert failed["error_code"] == "invalid_citation"


@pytest.mark.parametrize(
    "fixture,status",
    [
        ("synthetic-empty", "no_records"),
        ("synthetic-timeout", "error"),
        ("synthetic-malformed", "error"),
        ("synthetic-unavailable", "error"),
    ],
)
def test_expected_service_failures_never_become_zero_results(inputs, tmp_path, fixture, status):
    report = evaluate(inputs, tmp_path, fixture_overrides={"dev_011": fixture})
    row = next(r for r in report["cases"] if r["case_id"] == "dev_011")
    assert row["automatic_pass"] and row["answer"]["status"] == status
    assert row["actual_fixture_id"] == fixture
    assert row["model_calls"] == row["tool_calls"] == 1


def test_unexpected_provider_errors_count_against_full_denominator(inputs, tmp_path):
    def fail(**kwargs):
        raise TimeoutError("synthetic provider timeout")

    report = evaluate(inputs, tmp_path, model_factory=lambda _: ModelClient(fail))
    assert report["case_count"] == 16 and report["automatic_passes"] == 1
    assert all(r["answer"]["status"] == "error" for r in report["cases"])
    assert all(r["model_calls"] <= 1 for r in report["cases"])


def test_expected_labels_are_not_sent_to_the_provider(inputs, tmp_path):
    scripts = json.loads(DEFAULT_REPLIES.read_text())
    clients = {}

    def factory(case_id):
        replies = [
            {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(r)}}]}
            for r in scripts["cases"][case_id]
        ]
        clients[case_id] = RecordingClient(replies)
        return ModelClient(clients[case_id])

    evaluate(inputs, tmp_path, model_factory=factory)
    for case in load_evaluations(inputs[1], inputs[0]):
        for body in clients[case["case_id"]].bodies:
            payload = json.loads(body["messages"][-1]["content"])
            assert "expected" not in payload and "required_facts" not in payload
            for forbidden in case["expected"]["forbidden_document_ids"]:
                assert forbidden not in json.dumps(body)
            if "evidence" not in payload:
                assert not any(d.doc_id in json.dumps(payload) for d in inputs[0])
    assert not clients["dev_016"].bodies


def test_report_detects_retrieval_breach_even_when_context_guard_blocks_it(
    inputs, tmp_path, monkeypatch
):
    from dealer_evidence_agent import evaluation
    from dealer_evidence_agent.retrieval import PolicySearch

    monkeypatch.setattr(
        evaluation,
        "PolicySearch",
        lambda documents, identity: PolicySearch(documents, identity="manager_demo"),
    )
    report = evaluate(inputs, tmp_path)
    denied = next(r for r in report["cases"] if r["case_id"] == "dev_007")
    assert not denied["checks"]["permissions"] and not denied["automatic_pass"]
    assert denied["error_code"] == "context_rejected"
    assert denied["supplied_policy_ids"] == [] and denied["model_calls"] == 1


def test_script_mismatch_fails_before_any_model_or_trace(inputs, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"provenance":"synthetic_scripted_not_model_quality","cases":{}}')
    with pytest.raises(EvaluationError, match="no live fallback"):
        evaluate(inputs, tmp_path, replies_path=path)
    assert not (tmp_path / "runs").exists()


def test_cli_reports_and_exit_status(inputs, tmp_path, capsys):
    report_path = tmp_path / "retrieval.json"
    assert (
        main(
            [
                "evaluate",
                "--mode",
                "retrieval",
                "--eval-manifest",
                str(inputs[1]),
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text())
    assert report["top_k"] == 4 and report["hit_at_k"] == {"passed": 6, "total": 6}
    assert report["all_sources_at_k"] == {"passed": 6, "total": 6}
    assert "No routing" in capsys.readouterr().out
    assert main(["evaluate", "--mode", "scripted", "--replies", str(tmp_path / "missing")]) == 1
