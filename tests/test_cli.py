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
    assert "2 documents (1 shared, 1 manager_only)" in capsys.readouterr().out


def test_missing_manifest_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture):
    assert main(["validate-corpus", "--manifest", str(tmp_path / "missing.json")]) == 1
    captured = capsys.readouterr()
    assert "Corpus validation failed" in captured.err
    assert "Valid corpus" not in captured.out
