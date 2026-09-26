"""Load a small, trusted manifest and reject invalid metadata before use.

This validates corpus structure, not user authorization. Role filtering and
content fingerprints are added in M1.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal, cast

Visibility = Literal["shared", "manager_only"]
_FIELDS = {"doc_id", "title", "path", "visibility", "version"}


class CorpusError(ValueError):
    """Corpus metadata or content cannot safely be used."""


@dataclass(frozen=True)
class PolicyDocument:
    doc_id: str
    title: str
    path: str
    visibility: Visibility
    version: str
    text: str


def _read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise CorpusError(f"Cannot read UTF-8 file: {path.name}") from exc


def load_corpus(manifest_path: Path) -> tuple[PolicyDocument, ...]:
    """Validate every entry and return documents only if the whole corpus is valid.

    Manifest paths use forward slashes, relative to the adjacent corpus directory.
    Resolved paths must remain inside that directory, including symlink targets.
    """
    try:
        manifest = json.loads(_read_utf8(manifest_path))
    except json.JSONDecodeError as exc:
        raise CorpusError("Manifest must contain valid JSON.") from exc
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "documents"}:
        raise CorpusError("Manifest must contain only schema_version and documents.")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise CorpusError("Unsupported manifest schema_version; expected integer 1.")
    entries = manifest["documents"]
    if not isinstance(entries, list) or not entries:
        raise CorpusError("Manifest documents must be a nonempty list.")

    root = (manifest_path.parent / "corpus").resolve()
    seen_ids: set[str] = set()
    seen_paths: set[Path] = set()
    documents: list[PolicyDocument] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or set(entry) != _FIELDS:
            raise CorpusError(f"Entry {index} must contain exactly {sorted(_FIELDS)}.")
        if any(not isinstance(value, str) or not value.strip() for value in entry.values()):
            raise CorpusError(f"Entry {index} fields must be nonempty strings.")
        doc_id = entry["doc_id"]
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", doc_id):
            raise CorpusError(f"Entry {index} has an invalid doc_id.")
        if doc_id in seen_ids:
            raise CorpusError(f"Entry {index} has a duplicate doc_id.")
        if entry["visibility"] not in {"shared", "manager_only"}:
            raise CorpusError(f"Entry {index} has an unknown visibility.")

        relative = entry["path"]
        parts = PurePosixPath(relative)
        if (
            "\\" in relative
            or ":" in relative
            or "\x00" in relative
            or parts.is_absolute()
            or PureWindowsPath(relative).drive
            or ".." in parts.parts
            or parts.suffix != ".md"
        ):
            raise CorpusError(f"Entry {index} requires a relative Markdown path within corpus/.")
        try:
            path = (root / relative).resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise CorpusError(f"Entry {index} policy path cannot be resolved.") from exc
        if not path.is_relative_to(root) or not path.is_file():
            raise CorpusError(f"Entry {index} policy must be a file within corpus/.")
        if path in seen_paths:
            raise CorpusError(f"Entry {index} reuses an existing policy file.")
        text = _read_utf8(path)
        if not text.strip():
            raise CorpusError(f"Entry {index} policy is empty.")
        documents.append(
            PolicyDocument(
                doc_id=doc_id,
                title=entry["title"],
                path=relative,
                visibility=cast(Visibility, entry["visibility"]),
                version=entry["version"],
                text=text,
            )
        )
        seen_ids.add(doc_id)
        seen_paths.add(path)
    return tuple(documents)
