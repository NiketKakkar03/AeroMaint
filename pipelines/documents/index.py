"""Build a versioned local retrieval index from an approved-source manifest."""

from __future__ import annotations

import json
from pathlib import Path

from packages.retrieval import Document, HybridIndex, build_index


def build_from_manifest(manifest_path: Path, destination: Path) -> HybridIndex:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != "1.0.0" or not isinstance(manifest.get("sources"), list):
        raise ValueError("invalid approved-source manifest")
    documents: list[Document] = []
    for source in manifest["sources"]:
        if source.get("approved") is not True:
            raise ValueError(f"source is not approved: {source.get('title', '<unknown>')}")
        path = (manifest_path.parent / source["path"]).resolve()
        if manifest_path.parent.resolve() not in path.parents:
            raise ValueError("source path escapes manifest directory")
        documents.append(
            Document(
                source_url=source["url"],
                title=source["title"],
                version=source["version"],
                page=source.get("page"),
                text=path.read_text(),
            )
        )
    index = build_index(documents)
    index.write(destination)
    return index
