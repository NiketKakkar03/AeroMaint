from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from packages.source_adapters.euroc import EuRoCAdapter, SourceValidationError
from pipelines.ingestion import ingest_euroc

from aeromaint_api.domain.manifest import CaptureSessionManifest

FIXTURE = Path("tests/media-fixtures/euroc-mini")


def copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "source"
    shutil.copytree(FIXTURE, target)
    return target


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stream(manifest: dict[str, Any], stream_id: str) -> dict[str, Any]:
    return next(item for item in manifest["streams"] if item["id"] == stream_id)


def test_adapter_rejects_malformed_layout(tmp_path: Path) -> None:
    source = copy_fixture(tmp_path)
    shutil.rmtree(source / "mav0" / "cam1")
    with pytest.raises(SourceValidationError, match="missing: cam1"):
        EuRoCAdapter().read(source)


def test_adapter_rejects_malformed_and_out_of_order_csv(tmp_path: Path) -> None:
    source = copy_fixture(tmp_path)
    csv_path = source / "mav0" / "imu0" / "data.csv"
    csv_path.write_text(
        "# timestamp\n9007199254740994,0,0,0,0,0,0\n9007199254740993,0,0,0,0,0,0\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceValidationError, match="strictly increasing"):
        EuRoCAdapter().read(source)

    csv_path.write_text("9007199254740993,0,0\n", encoding="utf-8")
    with pytest.raises(SourceValidationError, match="malformed CSV"):
        EuRoCAdapter().read(source)


def test_missing_and_corrupt_frames_are_declared_as_gaps(tmp_path: Path) -> None:
    source = copy_fixture(tmp_path)
    missing = source / "mav0" / "cam0" / "data" / "9007199304740993.pgm"
    missing.unlink()
    corrupt = source / "mav0" / "cam1" / "data" / "9007199304740993.pgm"
    corrupt.write_bytes(b"not an image")

    result = ingest_euroc(source, tmp_path / "output", "fixture://missing-corrupt")
    manifest = load_manifest(result.manifest_path)
    left_reasons = {gap["reason"] for gap in stream(manifest, "camera-left")["gaps"]}
    right_reasons = {gap["reason"] for gap in stream(manifest, "camera-right")["gaps"]}
    assert "missing" in left_reasons
    assert "corrupt" in right_reasons


def test_exact_nanoseconds_gaps_and_canonical_manifest(tmp_path: Path) -> None:
    result = ingest_euroc(FIXTURE, tmp_path / "output", "fixture://euroc-mini")
    manifest = load_manifest(result.manifest_path)
    validated = CaptureSessionManifest.model_validate(manifest)

    assert manifest["start_ns"] == "9007199254740993"
    assert validated.start_ns == 9_007_199_254_740_993
    assert stream(manifest, "camera-left")["gaps"] == [
        {
            "end_ns": "9007199404740993",
            "reason": "missing",
            "start_ns": "9007199354740993",
        }
    ]
    assert stream(manifest, "imu-main")["gaps"] == [
        {
            "end_ns": "9007199404740993",
            "reason": "missing",
            "start_ns": "9007199269740993",
        }
    ]
    assert set(stream(manifest, "camera-left")) == {
        "artifact_ids",
        "calibration_ids",
        "clock_id",
        "end_ns",
        "gaps",
        "id",
        "kind",
        "sample_count",
        "schema_ref",
        "start_ns",
    }


def test_artifact_identifiers_are_content_addressed_and_reruns_idempotent(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    first = ingest_euroc(FIXTURE, output, "fixture://euroc-mini")
    first_bytes = first.manifest_path.read_bytes()
    second = ingest_euroc(FIXTURE, output, "fixture://euroc-mini")
    assert not first.reused
    assert second.reused
    assert first.session_id == second.session_id
    assert first.manifest_path == second.manifest_path
    assert second.manifest_path.read_bytes() == first_bytes

    manifest = load_manifest(first.manifest_path)
    for artifact in manifest["artifacts"]:
        artifact_path = first.manifest_path.parent / "artifacts" / artifact["sha256"]
        content = artifact_path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
        assert artifact["id"] == f"sha256-{artifact['sha256']}"


def test_duplicate_frame_content_reuses_one_artifact_descriptor(tmp_path: Path) -> None:
    source = copy_fixture(tmp_path)
    first = source / "mav0" / "cam0" / "data" / "9007199254740993.pgm"
    duplicate = source / "mav0" / "cam0" / "data" / "9007199304740993.pgm"
    duplicate.write_bytes(first.read_bytes())

    result = ingest_euroc(source, tmp_path / "output", "fixture://duplicate-frame")
    manifest = load_manifest(result.manifest_path)
    artifact_ids = [artifact["id"] for artifact in manifest["artifacts"]]
    assert len(artifact_ids) == len(set(artifact_ids))
    CaptureSessionManifest.model_validate(manifest)


def test_golden_manifest_is_structurally_stable(tmp_path: Path) -> None:
    result = ingest_euroc(FIXTURE, tmp_path / "output", "fixture://euroc-mini")
    expected = load_manifest(Path("tests/integration/euroc/fixtures/manifest.json"))
    assert load_manifest(result.manifest_path) == expected
