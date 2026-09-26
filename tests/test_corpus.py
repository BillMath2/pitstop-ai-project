"""Offline checks of the manifest boundary used by the starter CLI."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from dealer_evidence_agent.corpus import (
    CorpusError,
    corpus_fingerprint,
    load_corpus,
    text_fingerprint,
)


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, dict]:
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "policy.md").write_text("# A fictional policy\nDemo text.", encoding="utf-8")
    manifest = {
        "schema_version": 2,
        "documents": [
            {
                "doc_id": "shared_example",
                "title": "Example",
                "path": "policy.md",
                "visibility": "shared",
                "version": "1.0",
                "sha256": text_fingerprint("# A fictional policy\nDemo text."),
            }
        ],
    }
    return tmp_path / "manifest.json", manifest


def write_manifest(path: Path, manifest: dict) -> None:
    records = sorted(manifest["documents"], key=lambda entry: entry["doc_id"])
    manifest["corpus_sha256"] = text_fingerprint(
        json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_complete_corpus() -> None:
    documents = load_corpus(Path(__file__).resolve().parents[1] / "data/manifest.json")
    assert len(documents) == 24
    assert sum(doc.visibility == "shared" for doc in documents) == 16
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


def test_content_change_invalidates_manifest(corpus: tuple[Path, dict]) -> None:
    path, manifest = corpus
    write_manifest(path, manifest)
    (path.parent / "corpus/policy.md").write_text("A changed limit.", encoding="utf-8")
    with pytest.raises(CorpusError, match="policy fingerprint"):
        load_corpus(path)


def test_visibility_change_invalidates_manifest(corpus: tuple[Path, dict]) -> None:
    path, manifest = corpus
    write_manifest(path, manifest)
    manifest["documents"][0]["visibility"] = "manager_only"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CorpusError, match="Corpus fingerprint"):
        load_corpus(path)


def test_line_endings_are_portable(corpus: tuple[Path, dict]) -> None:
    path, manifest = corpus
    write_manifest(path, manifest)
    before = load_corpus(path)
    (path.parent / "corpus/policy.md").write_bytes(b"# A fictional policy\r\nDemo text.")
    assert corpus_fingerprint(load_corpus(path)) == corpus_fingerprint(before)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("doc_id", "new_id"),
        ("title", "New title"),
        ("path", "new.md"),
        ("visibility", "manager_only"),
        ("version", "2.0"),
        ("text", "Changed text"),
    ],
)
def test_fingerprint_binds_metadata_and_text(corpus: tuple[Path, dict], field: str, value: str):
    path, manifest = corpus
    write_manifest(path, manifest)
    documents = load_corpus(path)
    changed = (replace(documents[0], **{field: value}),)
    assert corpus_fingerprint(changed) != corpus_fingerprint(documents)


def test_fingerprint_is_independent_of_manifest_order() -> None:
    documents = load_corpus(Path(__file__).resolve().parents[1] / "data/manifest.json")
    assert corpus_fingerprint(documents) == corpus_fingerprint(tuple(reversed(documents)))
