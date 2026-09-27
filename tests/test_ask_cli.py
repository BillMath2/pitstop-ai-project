"""The ask CLI stays offline under a recording provider and safe configuration failures."""

import json

from dealer_evidence_agent.cli import main
from dealer_evidence_agent.model_client import ModelClient, RecordingClient


def test_ask_json_with_fake_provider(tmp_path, monkeypatch, capsys):
    client = RecordingClient(
        [
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "decision": {
                                        "action": "needs_clarification",
                                        "reason": "missing_vehicle",
                                    }
                                }
                            )
                        },
                    }
                ]
            }
        ]
    )
    monkeypatch.setattr(ModelClient, "from_environment", lambda path: ModelClient(client))
    code = main(
        [
            "ask",
            "Any recalls for a Honda Civic?",
            "--identity",
            "tech_demo",
            "--runs-dir",
            str(tmp_path),
            "--json",
        ]
    )
    value = json.loads(capsys.readouterr().out)
    assert code == 0 and value["status"] == "needs_clarification"
    assert value["tool_calls"] == 0 and value["model_calls"] == 1
    assert (tmp_path / f"{value['run_id']}.jsonl").exists()


def test_unknown_identity_precedes_provider_setup(tmp_path, monkeypatch, capsys):
    def unexpected(path):
        raise AssertionError("Must not create provider")

    monkeypatch.setattr(ModelClient, "from_environment", unexpected)
    assert main(["ask", "test", "--identity", "guest_demo", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_missing_credentials_are_safe_json(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert (
        main(["ask", "loaner", "--identity", "tech_demo", "--json", "--runs-dir", str(tmp_path)])
        == 1
    )
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "error" and "missing_api_key" in value["text"]


def test_invalid_corpus_before_provider_setup(tmp_path, monkeypatch, capsys):
    def unexpected(path):
        raise AssertionError("Must not create provider")

    monkeypatch.setattr(ModelClient, "from_environment", unexpected)
    assert (
        main(
            [
                "ask",
                "loaner",
                "--identity",
                "tech_demo",
                "--json",
                "--manifest",
                str(tmp_path / "missing"),
            ]
        )
        == 1
    )
    assert "CorpusError" in json.loads(capsys.readouterr().out)["text"]
