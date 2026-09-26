"""Exercise user-facing success and failure without services or credentials."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from dealer_evidence_agent.cli import main


def test_cli_help_without_credentials() -> None:
    env = {key: value for key, value in os.environ.items() if not key.endswith("API_KEY")}
    result = subprocess.run(
        [sys.executable, "-m", "dealer_evidence_agent", "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert "validate-corpus" in result.stdout


def test_validate_default_corpus(capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["validate-corpus"]) == 0
    output = capsys.readouterr().out
    assert "24 documents (16 shared, 8 manager_only)" in output
    assert "Corpus SHA-256:" in output


def test_missing_manifest_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture):
    assert main(["validate-corpus", "--manifest", str(tmp_path / "missing.json")]) == 1
    captured = capsys.readouterr()
    assert "Corpus validation failed" in captured.err
    assert "Valid corpus" not in captured.out


@pytest.mark.parametrize(("identity", "count"), [("tech_demo", 16), ("manager_demo", 24)])
def test_list_policies(identity: str, count: int, capsys, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["list-policies", "--identity", identity]) == 0
    output = capsys.readouterr().out
    assert len(output.splitlines()) == count
    if identity == "tech_demo":
        assert "manager_" not in output
        assert "goodwill" not in output.lower()


def test_unknown_identity_fails_before_loading_corpus(tmp_path, capsys):
    assert (
        main(["list-policies", "--identity", "admin", "--manifest", str(tmp_path / "missing.json")])
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Unknown demo identity" in captured.err
    assert "Corpus" not in captured.err


def test_validate_development_evaluations(capsys, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["validate-evals"]) == 0
    output = capsys.readouterr().out
    assert "16 cases (development only)" in output
    assert "no agent quality evaluation" in output


def test_missing_evaluation_manifest_is_an_error(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["validate-evals", "--eval-manifest", str(tmp_path / "missing.json")]) == 1
    assert "EvaluationError" in capsys.readouterr().err
