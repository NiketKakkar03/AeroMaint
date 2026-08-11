"""Canonical publication pipeline for ROS 2 MCAP sources."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from packages.source_adapters.mcap import ADAPTER_VERSION, MCAPAdapter, MCAPSource, Topic

from aeromaint_api.domain.manifest import CaptureSessionManifest

from .euroc import IngestionResult, PublicationError, _artifact, _canonical_json, _json_lines


def _stream_id(topic: Topic) -> str:
    preferred = {
        "/camera/left/image_raw": "camera-left",
        "/imu/data": "imu-main",
        "/localization/pose": "pose-ground-truth",
        "/maintenance/events": "maintenance-events",
    }
    return preferred.get(topic.name, topic.name.strip("/").replace("/", "-") or "root")


def _canonical_timestamp(source: MCAPSource, timestamp_ns: int) -> int:
    return timestamp_ns - source.source_epoch_ns


def _build(source: MCAPSource, source_uri: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    session_id = f"mcap-{source.source_sha256[:24]}"
    artifacts: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    streams: list[dict[str, Any]] = []

    for topic in source.topics:
        stream_id = _stream_id(topic)
        timestamps = [_canonical_timestamp(source, item.publish_time_ns) for item in topic.messages]
        record_rows = []
        frame_artifacts: list[str] = []
        for item, timestamp_ns in zip(topic.messages, timestamps, strict=True):
            value = dict(item.value)
            if topic.kind == "image":
                pixels = bytes.fromhex(str(value.pop("data")))
                frame, frame_content = _artifact(
                    pixels,
                    "application/octet-stream",
                    f"sessions/{session_id}/{stream_id}/frames/{timestamp_ns}.bin",
                )
                artifacts.append(frame)
                contents[frame["sha256"]] = frame_content
                frame_artifacts.append(frame["id"])
                value["artifact_id"] = frame["id"]
            record_rows.append(
                {
                    "timestamp_ns": str(timestamp_ns),
                    "source_publish_time_ns": str(item.publish_time_ns),
                    "source_log_time_ns": str(item.log_time_ns),
                    "sequence": item.sequence,
                    **value,
                }
            )
        metadata = {
            "source_topic": topic.name,
            "source_type": topic.type,
            "frame_ids": list(topic.frame_ids),
            "units": topic.units,
            "records": record_rows,
        }
        descriptor, content = _artifact(
            _canonical_json(metadata) if topic.kind == "image" else _json_lines(record_rows),
            "application/vnd.aeromaint.frame-index+json"
            if topic.kind == "image"
            else "application/x-ndjson",
            f"sessions/{session_id}/{stream_id}/"
            + ("index.json" if topic.kind == "image" else "records.ndjson"),
        )
        artifacts.append(descriptor)
        contents[descriptor["sha256"]] = content
        streams.append(
            {
                "id": stream_id,
                "kind": "video" if topic.kind == "image" else topic.kind,
                "clock_id": "ros",
                "start_ns": str(timestamps[0]),
                "end_ns": str(timestamps[-1]),
                "sample_count": len(timestamps),
                "schema_ref": {
                    "image": "aeromaint://schemas/video-frame-index/1.0.0",
                    "imu": "aeromaint://schemas/imu/1.0.0",
                    "pose": "aeromaint://schemas/pose/1.0.0",
                    "event": "aeromaint://schemas/event/1.0.0",
                }[topic.kind],
                "artifact_ids": [descriptor["id"], *frame_artifacts],
                "calibration_ids": [],
                "gaps": [],
            }
        )

    all_timestamps = [
        _canonical_timestamp(source, message.publish_time_ns)
        for topic in source.topics
        for message in topic.messages
    ]
    unique_artifacts = {artifact["id"]: artifact for artifact in artifacts}
    manifest = {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "display_name": f"ROS 2 MCAP {source.path.stem}",
        "start_ns": str(min(all_timestamps)),
        "end_ns": str(max(all_timestamps)),
        "session_clock_id": "ros",
        "clocks": [
            {
                "id": "ros",
                "source_epoch_ns": str(source.source_epoch_ns),
                "session_epoch_ns": "0",
                "rate_numerator": 1,
                "rate_denominator": 1,
            }
        ],
        "artifacts": list(unique_artifacts.values()),
        "calibrations": [],
        "streams": streams,
        "provenance": {
            "source_type": "ros2-mcap",
            "source_uri": source_uri,
            "source_sha256": source.source_sha256,
            "adapter": "aeromaint-mcap",
            "adapter_version": ADAPTER_VERSION,
            "source_metadata": {
                "profile": source.profile,
                "library": source.library,
                "topics": [
                    {
                        "name": topic.name,
                        "type": topic.type,
                        "frame_ids": list(topic.frame_ids),
                        "units": topic.units,
                    }
                    for topic in source.topics
                ],
                "unsupported_topics": list(source.unsupported),
            },
        },
    }
    CaptureSessionManifest.model_validate(manifest)
    return manifest, contents


def ingest_mcap(source_path: Path, output_root: Path, source_uri: str) -> IngestionResult:
    source = MCAPAdapter().read(source_path)
    manifest, contents = _build(source, source_uri)
    session_id = manifest["session_id"]
    final = output_root / session_id
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    if final.exists():
        existing = final / "manifest.json"
        if existing.is_file() and existing.read_bytes() == manifest_bytes:
            return IngestionResult(
                existing, session_id, source.source_sha256, len(contents), 0, True
            )
        raise PublicationError(f"existing session does not match deterministic output: {final}")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{session_id}-", dir=output_root))
    try:
        artifact_root = temporary / "artifacts"
        artifact_root.mkdir()
        for digest, content in sorted(contents.items()):
            (artifact_root / digest).write_bytes(content)
        (temporary / "manifest.json").write_bytes(manifest_bytes)
        temporary.rename(final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return IngestionResult(
        final / "manifest.json", session_id, source.source_sha256, len(contents), 0, False
    )
