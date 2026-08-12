"""Acquire, validate, parse, and index an approved source manifest."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any, cast

from packages.retrieval import Document, HybridIndex, build_index


def _manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("corrupt approved-source manifest") from exc
    if payload.get("schema_version") != "1.0.0" or not isinstance(payload.get("sources"), list):
        raise ValueError("invalid approved-source manifest")
    return cast(dict[str, Any], payload)


def _source_path(manifest_path: Path, relative: str) -> Path:
    root = manifest_path.parent.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError("source path escapes manifest directory")
    return path


def _validate_source(source: dict[str, Any]) -> None:
    required = ("url", "title", "version", "sha256", "path", "license", "approved_by")
    if source.get("approved") is not True:
        raise ValueError(f"source is not approved: {source.get('title', '<unknown>')}")
    if any(not isinstance(source.get(key), str) or not source[key].strip() for key in required):
        raise ValueError("approved source is missing version, checksum, or licensing metadata")
    if not source["url"].startswith("https://") or not re.fullmatch(
        r"[0-9a-f]{64}", source["sha256"]
    ):
        raise ValueError("approved source requires HTTPS and a SHA-256 checksum")


def acquire_from_manifest(manifest_path: Path, *, timeout_seconds: float = 30) -> list[Path]:
    """Download missing approved artifacts and verify every byte before publication."""
    acquired: list[Path] = []
    for source in _manifest(manifest_path)["sources"]:
        _validate_source(source)
        path = _source_path(manifest_path, source["path"])
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".part")
            try:
                with urllib.request.urlopen(source["url"], timeout=timeout_seconds) as response:  # noqa: S310
                    temporary.write_bytes(response.read())
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != source["sha256"]:
                    raise ValueError(f"checksum mismatch: {source['title']}")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"checksum mismatch: {source['title']}")
        acquired.append(path)
    return acquired


def _parse(path: Path) -> list[tuple[int | None, str]]:
    pages: list[tuple[int | None, str]]
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError

            try:
                reader = PdfReader(path)
                if reader.is_encrypted or not reader.pages:
                    raise ValueError("corrupt or encrypted document")
                pages = [
                    (number, page.extract_text() or "")
                    for number, page in enumerate(reader.pages, 1)
                ]
            except PdfReadError as exc:
                raise ValueError("invalid PDF structure") from exc
        except (OSError, ValueError) as exc:
            raise ValueError(f"corrupt document: {path.name}") from exc
    else:
        try:
            pages = [(None, path.read_text(encoding="utf-8"))]
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"corrupt document: {path.name}") from exc
    if (
        not pages
        or any("\x00" in text for _, text in pages)
        or not any(text.strip() for _, text in pages)
    ):
        raise ValueError(f"corrupt document: {path.name}")
    return pages


def build_from_manifest(manifest_path: Path, destination: Path) -> HybridIndex:
    manifest = _manifest(manifest_path)
    documents: list[Document] = []
    for source in manifest["sources"]:
        _validate_source(source)
        path = _source_path(manifest_path, source["path"])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"checksum mismatch or missing source: {source['title']}")
        for parsed_page, text in _parse(path):
            documents.append(
                Document(
                    source["url"],
                    source["title"],
                    source["version"],
                    text,
                    source.get("page", parsed_page),
                    source["sha256"],
                )
            )
    index = build_index(documents)
    index.write(destination)
    return index
