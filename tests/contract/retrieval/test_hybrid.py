import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from packages.retrieval import Document, HybridIndex, build_index
from pipelines.documents.index import build_from_manifest

from aeromaint_api.main import app


def documents() -> list[Document]:
    return [
        Document(
            "https://ntrs.nasa.gov/a",
            "NASA guide",
            "v1",
            "# Bearings\nBearing vibration trends can support condition monitoring.",
            7,
        ),
        Document(
            "https://www.faa.gov/b",
            "FAA guide",
            "2025",
            "# Approval\nReturn to service requires authorized maintenance approval.",
            11,
        ),
    ]


def test_hybrid_search_preserves_citation_and_can_abstain() -> None:
    index = build_index(documents())
    result = index.search("bearing vibration")
    assert result.status == "ok"
    assert result.results[0]["citation"] == {
        "chunk_id": result.results[0]["citation"]["chunk_id"],
        "source_url": "https://ntrs.nasa.gov/a",
        "title": "NASA guide",
        "version": "v1",
        "page": 7,
        "section": "Bearings",
    }
    assert index.search("xylophone nebula quasar").status == "insufficient_evidence"


def test_versioned_index_is_deterministic_and_corruption_is_rejected(tmp_path: Path) -> None:
    first = build_index(documents())
    second = build_index(list(reversed(documents())))
    assert first.version == second.version
    target = tmp_path / "index.json"
    first.write(target)
    before = target.read_bytes()
    second.write(target)
    assert target.read_bytes() == before
    target.write_text('{"chunks": "broken"}')
    with pytest.raises(ValueError, match="corrupt"):
        HybridIndex.read(target)


def test_manifest_rejects_unapproved_source(tmp_path: Path) -> None:
    (tmp_path / "source.md").write_text("# Test\nEvidence")
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "sources": [
                    {
                        "approved": False,
                        "path": "source.md",
                        "url": "https://example.test/doc",
                        "title": "Unreviewed",
                        "version": "1",
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="not approved"):
        build_from_manifest(manifest, tmp_path / "index.json")


def test_document_search_api_returns_versioned_citations() -> None:
    response = TestClient(app).get("/v1/documents/search", params={"q": "turbofan degradation"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["index_version"]
    assert body["results"][0]["citation"]["source_url"].startswith("https://ntrs.nasa.gov/")
