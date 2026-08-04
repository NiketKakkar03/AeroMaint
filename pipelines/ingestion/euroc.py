"""Canonical, content-addressed publication pipeline for EuRoC sources."""

from __future__ import annotations

import hashlib
import itertools
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.source_adapters.euroc import ADAPTER_VERSION, EuRoCAdapter, EuRoCSource

from aeromaint_api.domain.manifest import CaptureSessionManifest


class PublicationError(RuntimeError):
    """Canonical artifact publication could not complete atomically."""


@dataclass(frozen=True)
class IngestionResult:
    manifest_path: Path
    session_id: str
    source_sha256: str
    artifact_count: int
    gap_count: int
    reused: bool


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _json_lines(records: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_json(record) for record in records)


def _artifact(content: bytes, media_type: str, logical_key: str) -> tuple[dict[str, Any], bytes]:
    digest = hashlib.sha256(content).hexdigest()
    return (
        {
            "id": f"sha256-{digest}",
            "media_type": media_type,
            "logical_key": logical_key,
            "size_bytes": len(content),
            "sha256": digest,
        },
        content,
    )


def _period_ns(rate_hz: int) -> int:
    return 1_000_000_000 // rate_hz


def _gaps(timestamps: list[int], rate_hz: int) -> list[dict[str, str]]:
    period = _period_ns(rate_hz)
    gaps: list[dict[str, str]] = []
    for previous, current in itertools.pairwise(timestamps):
        if current - previous > period + period // 2:
            gaps.append(
                {
                    "start_ns": str(previous + period),
                    "end_ns": str(current),
                    "reason": "missing",
                }
            )
    return gaps


def _camera_gaps(source: EuRoCSource, sensor: str) -> list[dict[str, str]]:
    records = source.cameras[sensor]
    result = _gaps([record.timestamp_ns for record in records], source.rates_hz[sensor])
    period = _period_ns(source.rates_hz[sensor])
    for record in records:
        if record.status != "valid":
            result.append(
                {
                    "start_ns": str(record.timestamp_ns),
                    "end_ns": str(min(record.timestamp_ns + period, records[-1].timestamp_ns)),
                    "reason": record.status,
                }
            )
    result.sort(key=lambda gap: (int(gap["start_ns"]), int(gap["end_ns"])))
    merged: list[dict[str, str]] = []
    for gap in result:
        if merged and int(gap["start_ns"]) < int(merged[-1]["end_ns"]):
            if gap["reason"] == merged[-1]["reason"]:
                merged[-1]["end_ns"] = str(max(int(merged[-1]["end_ns"]), int(gap["end_ns"])))
                continue
            gap["start_ns"] = merged[-1]["end_ns"]
        merged.append(gap)
    return merged


def _stream(
    stream_id: str,
    kind: str,
    timestamps: list[int],
    artifact_ids: list[str],
    schema_ref: str,
    calibration_ids: list[str],
    gaps: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "id": stream_id,
        "kind": kind,
        "clock_id": "session",
        "start_ns": str(timestamps[0]),
        "end_ns": str(timestamps[-1]),
        "sample_count": len(timestamps),
        "schema_ref": schema_ref,
        "artifact_ids": artifact_ids,
        "calibration_ids": calibration_ids,
        "gaps": gaps,
    }


def _build(source: EuRoCSource, source_uri: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    session_id = f"euroc-{source.source_sha256[:24]}"
    artifacts: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}

    calibration_content = _canonical_json(
        {"format": "euroc-sensor-yaml", "sensors": source.calibration}
    )
    calibration, content = _artifact(
        calibration_content,
        "application/vnd.aeromaint.calibration+json",
        f"sessions/{session_id}/calibration/euroc.json",
    )
    artifacts.append(calibration)
    contents[calibration["sha256"]] = content

    streams: list[dict[str, Any]] = []
    for sensor, stream_id in (("cam0", "camera-left"), ("cam1", "camera-right")):
        records = source.cameras[sensor]
        frame_artifact_ids: dict[int, str] = {}
        for record in records:
            if record.status != "valid" or record.sha256 is None:
                continue
            frame_content = record.path.read_bytes()
            media_type = (
                "image/png" if record.path.suffix.lower() == ".png" else "image/x-portable-graymap"
            )
            frame, content = _artifact(
                frame_content,
                media_type,
                f"sessions/{session_id}/{stream_id}/frames/{record.timestamp_ns}{record.path.suffix.lower()}",
            )
            artifacts.append(frame)
            contents[frame["sha256"]] = content
            frame_artifact_ids[record.timestamp_ns] = frame["id"]
        index_content = _canonical_json(
            {
                "frames": [
                    {
                        "timestamp_ns": str(record.timestamp_ns),
                        "source_key": f"{sensor}/data/{record.filename}",
                        "source_sha256": record.sha256,
                        "artifact_id": frame_artifact_ids.get(record.timestamp_ns),
                        "status": record.status,
                    }
                    for record in records
                ]
            }
        )
        descriptor, content = _artifact(
            index_content,
            "application/vnd.aeromaint.frame-index+json",
            f"sessions/{session_id}/{stream_id}/index.json",
        )
        artifacts.append(descriptor)
        contents[descriptor["sha256"]] = content
        timestamps = [record.timestamp_ns for record in records]
        streams.append(
            _stream(
                stream_id,
                "video",
                timestamps,
                [descriptor["id"], *frame_artifact_ids.values()],
                "aeromaint://schemas/video-frame-index/1.0.0",
                ["stereo-rig"],
                _camera_gaps(source, sensor),
            )
        )

    for stream_id, kind, numeric_records, schema_ref, rate in (
        ("imu-main", "imu", source.imu, "aeromaint://schemas/imu/1.0.0", source.rates_hz["imu0"]),
        ("pose-ground-truth", "pose", source.pose, "aeromaint://schemas/pose/1.0.0", 0),
    ):
        payload = _json_lines(
            [
                {"timestamp_ns": str(record.timestamp_ns), "values": list(record.values)}
                for record in numeric_records
            ]
        )
        descriptor, content = _artifact(
            payload,
            "application/x-ndjson",
            f"sessions/{session_id}/{stream_id}/records.ndjson",
        )
        artifacts.append(descriptor)
        contents[descriptor["sha256"]] = content
        timestamps = [record.timestamp_ns for record in numeric_records]
        gaps = _gaps(timestamps, rate) if rate else []
        streams.append(
            _stream(stream_id, kind, timestamps, [descriptor["id"]], schema_ref, [], gaps)
        )

    all_timestamps = [
        *(record.timestamp_ns for records in source.cameras.values() for record in records),
        *(record.timestamp_ns for record in source.imu),
        *(record.timestamp_ns for record in source.pose),
    ]
    unique_artifacts: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        unique_artifacts.setdefault(artifact["id"], artifact)
    manifest = {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "display_name": f"EuRoC {source.root.parent.name or source.root.name}",
        "start_ns": str(min(all_timestamps)),
        "end_ns": str(max(all_timestamps)),
        "session_clock_id": "session",
        "clocks": [
            {
                "id": "session",
                "source_epoch_ns": "0",
                "session_epoch_ns": "0",
                "rate_numerator": 1,
                "rate_denominator": 1,
            }
        ],
        "artifacts": list(unique_artifacts.values()),
        "calibrations": [
            {"id": "stereo-rig", "kind": "stereo_camera", "artifact_id": calibration["id"]}
        ],
        "streams": streams,
        "provenance": {
            "source_type": "euroc-mav",
            "source_uri": source_uri,
            "source_sha256": source.source_sha256,
            "adapter": "aeromaint-euroc",
            "adapter_version": ADAPTER_VERSION,
            "source_metadata": {"layout": "mav0", "sensor_names": sorted(source.calibration)},
        },
    }
    CaptureSessionManifest.model_validate(manifest)
    return manifest, contents


def ingest_euroc(source_path: Path, output_root: Path, source_uri: str) -> IngestionResult:
    source = EuRoCAdapter().read(source_path)
    manifest, contents = _build(source, source_uri)
    session_id = manifest["session_id"]
    final = output_root / session_id
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    if final.exists():
        existing = final / "manifest.json"
        if existing.is_file() and existing.read_bytes() == manifest_bytes:
            return IngestionResult(
                existing,
                session_id,
                source.source_sha256,
                len(contents),
                sum(len(stream["gaps"]) for stream in manifest["streams"]),
                True,
            )
        raise PublicationError(f"existing session does not match deterministic output: {final}")

    output_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{session_id}-", dir=output_root))
    try:
        artifacts = temporary / "artifacts"
        artifacts.mkdir()
        for digest, content in sorted(contents.items()):
            (artifacts / digest).write_bytes(content)
        (temporary / "manifest.json").write_bytes(manifest_bytes)
        temporary.rename(final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return IngestionResult(
        final / "manifest.json",
        session_id,
        source.source_sha256,
        len(contents),
        sum(len(stream["gaps"]) for stream in manifest["streams"]),
        False,
    )
