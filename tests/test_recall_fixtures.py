"""Recorded provenance, synthetic error cases, and offline replay isolation."""

import json
import shutil
from pathlib import Path

import httpx
import pytest

from dealer_evidence_agent.corpus import load_corpus
from dealer_evidence_agent.evaluations import load_evaluations
from dealer_evidence_agent.permissions import AuthorizationError
from dealer_evidence_agent.recall_fixtures import (
    RecallFixtureError,
    fixture_fingerprint,
    replay_recalls,
    validate_recall_fixtures,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/recalls/v1/manifest.json"


def replay(fixture_id="toyota-corolla-2020", path=MANIFEST, **kwargs):
    return replay_recalls(
        path, fixture_id, identity="tech_demo", make="Toyota", model="Corolla", year=2020, **kwargs
    )


def test_full_fixture_set_is_valid_and_offline(monkeypatch):
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: pytest.fail("Replay attempted network"))
    report = validate_recall_fixtures(MANIFEST)
    assert report["fixtures"] == 9 and report["recorded"] == 3 and report["synthetic"] == 6
    result = replay()
    assert result.source == "recorded_fixture" and result.network_attempts == 0
    assert result.observed_at.endswith("+00:00") and result.total_count == 3


@pytest.mark.parametrize(
    ("fixture_id", "status"),
    [
        ("synthetic-empty", "empty"),
        ("synthetic-malformed", "invalid_response"),
        ("synthetic-rate-limit", "http_error"),
        ("synthetic-unavailable", "http_error"),
        ("synthetic-timeout", "timeout"),
        ("synthetic-network", "network_error"),
    ],
)
def test_synthetic_provenance_never_looks_live(fixture_id, status):
    result = replay(fixture_id)
    assert result.status == status and result.source == "synthetic_fixture"
    assert result.observed_at is None and result.network_attempts == 0
    assert result.total_count == (0 if status == "empty" else None)


def test_development_recall_arguments_have_recorded_responses():
    documents = load_corpus(ROOT / "data/manifest.json")
    cases = load_evaluations(ROOT / "evals/manifest.json", documents)
    count = 0
    for case in cases:
        if case["category"] != "recall":
            continue
        args = case["expected"]["tool_arguments"]
        fixture_id = f"{args['make'].lower()}-{args['model'].lower()}-{args['year']}"
        result = replay_recalls(MANIFEST, fixture_id, identity=case["identity"], **args)
        assert result.status == "ok" and result.source == "recorded_fixture"
        assert result.total_count >= len(result.records) > 0
        count += 1
    assert count == 3


def test_wrong_vehicle_and_unknown_fixture_do_not_fallback():
    with pytest.raises(RecallFixtureError, match="vehicle"):
        replay_recalls(
            MANIFEST,
            "toyota-corolla-2020",
            identity="tech_demo",
            make="Toyota",
            model="Camry",
            year=2020,
        )
    with pytest.raises(RecallFixtureError, match="Unknown"):
        replay("missing-fixture")


def test_unknown_identity_rejected_before_fixture_io(tmp_path):
    with pytest.raises(AuthorizationError):
        replay_recalls(
            tmp_path / "missing.json",
            "toyota-corolla-2020",
            identity="admin",
            make="Toyota",
            model="Corolla",
            year=2020,
        )


@pytest.fixture
def copied(tmp_path):
    shutil.copytree(MANIFEST.parent, tmp_path / "fixtures")
    return tmp_path / "fixtures/manifest.json"


def test_body_tampering_fails_closed(copied):
    with (copied.parent / "toyota-corolla-2020.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(RecallFixtureError, match="fingerprint"):
        replay(path=copied)


def test_metadata_tampering_fails_closed(copied):
    data = json.loads(copied.read_text())
    data["fixtures"][0]["captured_at"] = "2000-01-01T00:00:00+00:00"
    copied.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RecallFixtureError, match="fingerprint"):
        replay(path=copied)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("body_path", "../outside.json"),
        ("body_path", "C:/outside.json"),
        ("source_url", "https://example.invalid"),
        ("captured_at", None),
        ("captured_at", "2026-09-26T00:00:00"),
        ("kind", "live"),
        ("http_status", True),
        ("expected_status", "pretend_ok"),
        ("body_sha256", "bad"),
    ],
)
def test_invalid_fixture_provenance_even_with_new_hash(copied, field, value):
    data = json.loads(copied.read_text())
    data["fixtures"][0][field] = value
    data["fixtures_sha256"] = fixture_fingerprint(data["fixtures"])
    copied.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RecallFixtureError):
        replay(path=copied)
