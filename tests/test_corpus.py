"""Offline checks of the manifest boundary used by the starter CLI."""

import json
from pathlib import Path

import pytest

from dealer_evidence_agent.corpus import CorpusError, load_corpus


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, dict]:
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "policy.md").write_text("# A fictional policy\nDemo text.", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "documents": [
            {
                "doc_id": "shared_example",
                "title": "Example",
                "path": "policy.md",
                "visibility": "shared",
                "version": "1.0",
            }
        ],
    }
    return tmp_path / "manifest.json", manifest


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_starter_corpus() -> None:
    documents = load_corpus(Path(__file__).resolve().parents[1] / "data/manifest.json")
    assert len(documents) == 2
    assert {document.visibility for document in documents} == {"shared", "manager_only"}
    assert all("fictional" in document.text for document in documents)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("visibility", "public"),
        ("visibility", None),
        ("doc_id", ""),
        ("doc_id", "spaces are invalid"),
        ("version", 1),
        ("title", "   "),
        ("path", "../outside.md"),
        ("path", "/absolute.md"),
        ("path", "C:/outside.md"),
        ("path", "..\\outside.md"),
        ("path", "policy.md:stream.md"),
        ("path", "missing.md"),
    ],
)
def test_rejects_invalid_entry(corpus: tuple[Path, dict], field: str, value: object) -> None:
    path, manifest = corpus
    manifest["documents"][0][field] = value
    write_manifest(path, manifest)
    with pytest.raises(CorpusError):
        load_corpus(path)


@pytest.mark.parametrize("reuse_id", [True, False])
def test_rejects_duplicate_ids_or_files(corpus: tuple[Path, dict], reuse_id: bool) -> None:
    path, manifest = corpus
    duplicate = dict(manifest["documents"][0])
    if not reuse_id:
        duplicate["doc_id"] = "another_id"
    manifest["documents"].append(duplicate)
    write_manifest(path, manifest)
    with pytest.raises(CorpusError, match="duplicate|reuses"):
        load_corpus(path)


@pytest.mark.parametrize(
    "body", ["", " ", "{broken", "[]", '{"schema_version":true,"documents":[]}']
)
def test_rejects_invalid_manifest(tmp_path: Path, body: str) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(CorpusError):
        load_corpus(path)


@pytest.mark.parametrize("body", [b"  ", b"\xff\xfe"])
def test_rejects_empty_or_invalid_utf8_policy(corpus: tuple[Path, dict], body: bytes) -> None:
    path, manifest = corpus
    write_manifest(path, manifest)
    (path.parent / "corpus/policy.md").write_bytes(body)
    with pytest.raises(CorpusError):
        load_corpus(path)


def test_rejects_symlink_escape(corpus: tuple[Path, dict]) -> None:
    path, manifest = corpus
    outside = path.parent / "outside.md"
    outside.write_text("Outside corpus.", encoding="utf-8")
    link = path.parent / "corpus/link.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires OS support/permission.")
    manifest["documents"][0]["path"] = "link.md"
    write_manifest(path, manifest)
    with pytest.raises(CorpusError, match="within corpus"):
        load_corpus(path)
