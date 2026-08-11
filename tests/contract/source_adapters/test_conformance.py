from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from packages.source_adapters.mcap import MCAPAdapter, MCAPValidationError
from pipelines.ingestion import IngestionResult, ingest_euroc, ingest_mcap
from scripts.generate_mcap_fixture import build_mcap

from aeromaint_api.domain.manifest import CaptureSessionManifest

EUROC = Path("tests/media-fixtures/euroc-mini")
MCAP = Path("tests/media-fixtures/mcap-mini/ros2-mini.mcap")
Ingest = Callable[[Path, Path, str], IngestionResult]
MANIFEST_KEYS = {
    "artifacts",
    "calibrations",
    "clocks",
    "display_name",
    "end_ns",
    "provenance",
    "schema_version",
    "session_clock_id",
    "session_id",
    "start_ns",
    "streams",
}
STREAM_KEYS = {
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


def _manifest(result: IngestionResult) -> dict[str, Any]:
    return json.loads(result.manifest_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("adapter", "fixture", "uri"),
    [(ingest_euroc, EUROC, "fixture://euroc-mini"), (ingest_mcap, MCAP, "fixture://mcap-mini")],
    ids=("euroc", "mcap"),
)
def test_adapters_publish_one_canonical_consumer_contract(
    tmp_path: Path, adapter: Ingest, fixture: Path, uri: str
) -> None:
    manifest = _manifest(adapter(fixture, tmp_path / "sessions", uri))
    validated = CaptureSessionManifest.model_validate(manifest)
    assert set(manifest) == MANIFEST_KEYS
    assert all(set(stream) == STREAM_KEYS for stream in manifest["streams"])
    assert validated.schema_version == "1.0.0"
    assert {stream.kind for stream in validated.streams} >= {"video", "imu", "pose"}
    assert all(stream.schema_ref.startswith("aeromaint://schemas/") for stream in validated.streams)


def test_mcap_preserves_ros_evidence_without_changing_public_contract(tmp_path: Path) -> None:
    result = ingest_mcap(MCAP, tmp_path / "sessions", "fixture://mcap-mini")
    manifest = _manifest(result)
    metadata = manifest["provenance"]["source_metadata"]
    assert manifest["clocks"] == [
        {
            "id": "ros",
            "source_epoch_ns": "1700000000000000000",
            "session_epoch_ns": "0",
            "rate_numerator": 1,
            "rate_denominator": 1,
        }
    ]
    assert [(topic["name"], topic["type"]) for topic in metadata["topics"]] == [
        ("/camera/left/image_raw", "sensor_msgs/msg/Image"),
        ("/imu/data", "sensor_msgs/msg/Imu"),
        ("/localization/pose", "geometry_msgs/msg/PoseStamped"),
        ("/maintenance/events", "aeromaint_msgs/msg/Event"),
    ]
    assert metadata["topics"][0]["frame_ids"] == ["camera_left_optical"]
    assert metadata["topics"][1]["units"] == {
        "angular_velocity": "rad/s",
        "linear_acceleration": "m/s^2",
    }
    assert metadata["unsupported_topics"][0]["topic"] == "/debug/text"
    assert "unsupported ROS 2 schema" in metadata["unsupported_topics"][0]["diagnostic"]

    contracts = Path("packages/contracts/src/index.ts").read_text(encoding="utf-8")
    viewer_sdk = Path("apps/viewer/src/lib/sdk.ts").read_text(encoding="utf-8")
    public_sdk = Path("packages/capture-sdk-ts/src/index.ts").read_text(encoding="utf-8")
    assert "mcap" not in (contracts + viewer_sdk + public_sdk).lower()
    assert "source_metadata" not in contracts


def test_unsupported_only_mcap_has_actionable_diagnostic(tmp_path: Path) -> None:
    source = tmp_path / "unsupported.mcap"
    source.write_bytes(build_mcap(supported=False))
    with pytest.raises(
        MCAPValidationError,
        match=r"unsupported ROS 2 schema 'std_msgs/msg/String'.*topic '/debug/text'.*supported:",
    ):
        MCAPAdapter().read(source)


def test_mcap_fixture_checksums_are_complete_and_valid() -> None:
    root = MCAP.parent
    entries = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        entries[name] = digest
    assert set(entries) == {"README.md", "ros2-mini.mcap"}
    for name, expected in entries.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected


def test_mcap_golden_manifest_is_stable(tmp_path: Path) -> None:
    actual = _manifest(ingest_mcap(MCAP, tmp_path / "sessions", "fixture://mcap-mini"))
    expected = json.loads(
        Path("tests/contract/source_adapters/fixtures/mcap-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert actual == expected
