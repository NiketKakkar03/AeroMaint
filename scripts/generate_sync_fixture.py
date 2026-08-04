#!/usr/bin/env python3
"""Generate the deterministic, project-owned synchronization contract fixture."""

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "media-fixtures" / "synthetic-session"
BASE_NS = 9_007_199_254_740_993


def artifact(identifier: str, logical_key: str, payload: bytes) -> dict[str, Any]:
    return {
        "id": identifier,
        "media_type": "application/vnd.aeromaint.frame-index+json",
        "logical_key": logical_key,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def frame_index(offset_ns: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "frames": [
            {
                "frame_number": index,
                "presentation_ns": str(BASE_NS + offset_ns + index * 50_000_000),
                "keyframe": index in {0, 4},
            }
            for index in range(5)
        ],
    }


def build_fixture() -> dict[str, bytes]:
    left = json_bytes(frame_index(0))
    right = json_bytes(frame_index(10_000_000))
    imu = b"timestamp_ns,ax,ay,az\n9007199254740993,0.0,0.0,9.81\n"
    pose = b"timestamp_ns,x,y,z\n9007199254740993,0.0,0.0,0.0\n"
    events = b"timestamp_ns,label\n9007199354740993,known-event\n"
    calibration = json_bytes({"baseline_m": 0.11, "model": "pinhole"})

    artifacts = [
        artifact("left-index", "camera-left/index.json", left),
        artifact("right-index", "camera-right/index.json", right),
        {**artifact("imu-samples", "imu/samples.csv", imu), "media_type": "text/csv"},
        {**artifact("pose-samples", "pose/samples.csv", pose), "media_type": "text/csv"},
        {**artifact("events", "events/events.csv", events), "media_type": "text/csv"},
        {
            **artifact("stereo-calibration", "calibration/stereo.json", calibration),
            "media_type": "application/json",
        },
    ]
    manifest = {
        "schema_version": "1.0.0",
        "session_id": "synthetic-sync-v1",
        "display_name": "Deterministic synchronization fixture",
        "start_ns": str(BASE_NS),
        "end_ns": str(BASE_NS + 210_000_000),
        "session_clock_id": "session",
        "clocks": [
            {
                "id": "session",
                "source_epoch_ns": "0",
                "session_epoch_ns": "0",
                "rate_numerator": 1,
                "rate_denominator": 1,
            },
            {
                "id": "right-device",
                "source_epoch_ns": "500000000",
                "session_epoch_ns": str(BASE_NS + 10_000_000),
                "rate_numerator": 1_000_001,
                "rate_denominator": 1_000_000,
            },
        ],
        "artifacts": artifacts,
        "calibrations": [
            {
                "id": "stereo-rig",
                "kind": "stereo_camera",
                "artifact_id": "stereo-calibration",
            }
        ],
        "streams": [
            {
                "id": "camera-left",
                "kind": "video",
                "clock_id": "session",
                "start_ns": str(BASE_NS),
                "end_ns": str(BASE_NS + 200_000_000),
                "sample_count": 5,
                "schema_ref": "aeromaint://schemas/video-frame-index/1.0.0",
                "artifact_ids": ["left-index"],
                "calibration_ids": ["stereo-rig"],
                "gaps": [
                    {
                        "start_ns": str(BASE_NS + 120_000_000),
                        "end_ns": str(BASE_NS + 140_000_000),
                        "reason": "missing",
                    }
                ],
            },
            {
                "id": "camera-right",
                "kind": "video",
                "clock_id": "right-device",
                "start_ns": str(BASE_NS + 10_000_000),
                "end_ns": str(BASE_NS + 210_000_000),
                "sample_count": 5,
                "schema_ref": "aeromaint://schemas/video-frame-index/1.0.0",
                "artifact_ids": ["right-index"],
                "calibration_ids": ["stereo-rig"],
                "gaps": [],
            },
            *[
                {
                    "id": stream_id,
                    "kind": kind,
                    "clock_id": "session",
                    "start_ns": str(BASE_NS),
                    "end_ns": str(BASE_NS + 200_000_000),
                    "sample_count": 1,
                    "schema_ref": f"aeromaint://schemas/{kind}/1.0.0",
                    "artifact_ids": [artifact_id],
                    "calibration_ids": [],
                    "gaps": [],
                }
                for stream_id, kind, artifact_id in [
                    ("imu-main", "imu", "imu-samples"),
                    ("pose-ground-truth", "pose", "pose-samples"),
                    ("events", "event", "events"),
                ]
            ],
        ],
        "provenance": {
            "source_type": "synthetic",
            "source_uri": "aeromaint://fixtures/synthetic-sync-v1",
            "source_sha256": hashlib.sha256(left + right + imu + pose + events).hexdigest(),
            "adapter": "generate_sync_fixture.py",
            "adapter_version": "1.0.0",
        },
    }
    expectations = {
        "base_ns": str(BASE_NS),
        "clock_mappings": [
            {
                "clock_id": "right-device",
                "source_ns": "500000000",
                "expected_session_ns": str(BASE_NS + 10_000_000),
            },
            {
                "clock_id": "right-device",
                "source_ns": "600000000",
                "expected_session_ns": str(BASE_NS + 110_000_100),
            },
            {
                "clock_id": "right-device",
                "source_ns": "499999999",
                "expected_session_ns": str(BASE_NS + 9_999_998),
            },
        ],
        "frame_queries": [
            {"offset_ns": "0", "at_or_before": 0, "nearest": 0},
            {"offset_ns": "25000000", "at_or_before": 0, "nearest": 0},
            {"offset_ns": "76000000", "at_or_before": 1, "nearest": 2},
            {"offset_ns": "130000000", "at_or_before": None, "nearest": None},
            {"offset_ns": "160000000", "at_or_before": 3, "nearest": 3},
        ],
    }
    return {
        "camera-left-index.json": left,
        "camera-right-index.json": right,
        "imu.csv": imu,
        "pose.csv": pose,
        "events.csv": events,
        "stereo-calibration.json": calibration,
        "manifest.json": json_bytes(manifest),
        "expectations.json": json_bytes(expectations),
    }


def write_fixture() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = build_fixture()
    for name, payload in files.items():
        (OUTPUT / name).write_bytes(payload)
    checksums = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
        for name, payload in sorted(files.items())
    )
    (OUTPUT / "SHA256SUMS").write_text(checksums)


if __name__ == "__main__":
    write_fixture()
