import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from packages.retrieval import Document, HybridIndex, build_index
from pipelines.documents.index import acquire_from_manifest, build_from_manifest

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
        "start_char": 11,
        "end_char": 69,
        "checksum": hashlib.sha256(documents()[0].text.encode()).hexdigest(),
    }
    citation = result.results[0]["citation"]
    assert (
        documents()[0].text[citation["start_char"] : citation["end_char"]]
        == result.results[0]["text"]
    )
    assert index.search("xylophone nebula quasar").status == "insufficient_evidence"


def test_hybrid_supports_exact_terms_and_semantic_paraphrase() -> None:
    index = build_index(documents())
    assert index.search("return to service").results[0]["citation"]["title"] == "FAA guide"
    assert (
        index.search("authorization for maintenance").results[0]["citation"]["title"] == "FAA guide"
    )


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


def test_manifest_verifies_checksum_and_rejects_corrupt_document(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Inspection\nApproved maintenance evidence.")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "sources": [
                    {
                        "approved": True,
                        "approved_by": "engineering-review",
                        "license": "US government work",
                        "path": "source.md",
                        "url": "https://www.faa.gov/example",
                        "title": "FAA example",
                        "version": "2026-01",
                        "sha256": digest,
                    }
                ],
            }
        )
    )
    first = build_from_manifest(manifest, tmp_path / "index.json")
    mtime = (tmp_path / "index.json").stat().st_mtime_ns
    assert build_from_manifest(manifest, tmp_path / "index.json").version == first.version
    assert (tmp_path / "index.json").stat().st_mtime_ns == mtime
    source.write_bytes(b"%PDF-1.7\x00broken")
    with pytest.raises(ValueError, match="checksum"):
        build_from_manifest(manifest, tmp_path / "index.json")


def test_acquisition_uses_existing_checksum_pinned_artifact(tmp_path: Path) -> None:
    source = tmp_path / "nasa.txt"
    source.write_text("NASA public technical report")
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "sources": [
                    {
                        "approved": True,
                        "approved_by": "engineering-review",
                        "license": "NASA STI",
                        "path": "nasa.txt",
                        "url": "https://ntrs.nasa.gov/example",
                        "title": "NASA example",
                        "version": "1.0",
                        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    }
                ],
            }
        )
    )
    assert acquire_from_manifest(manifest) == [source]


def test_checksum_valid_but_structurally_corrupt_pdf_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.7 structurally incomplete")
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "sources": [
                    {
                        "approved": True,
                        "approved_by": "engineering-review",
                        "license": "reviewed publisher terms",
                        "path": source.name,
                        "url": "https://www.faa.gov/broken.pdf",
                        "title": "Broken PDF",
                        "version": "1",
                        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="corrupt document"):
        build_from_manifest(manifest, tmp_path / "index.json")


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
