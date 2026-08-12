import hashlib
import json
from pathlib import Path

from scripts.build_release import build


def test_release_manifest_has_versions_and_verified_checksums(tmp_path: Path) -> None:
    manifest = build(tmp_path)
    assert manifest["schema_version"] == "1.0.0"
    assert len(manifest["source_commit"]) == 40
    assert manifest["components"]["typescript_sdk"] == "1.0.0"
    for artifact in manifest["artifacts"]:
        body = (tmp_path / artifact["name"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == artifact["sha256"]
    checksums = (tmp_path / "SHA256SUMS").read_text()
    assert "release-manifest.json" in checksums
    assert json.loads((tmp_path / "release-manifest.json").read_text()) == manifest
