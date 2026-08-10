from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from aeromaint_api.domain.fixtures import FIXTURE_SESSION_ID
from aeromaint_api.services.arrow import IMU_FIELDS, SensorSource

FIXTURE_MEDIA = b"frame-0000|frame-0001|frame-0002|frame-0003|frame-0004"
FIXTURE_MEDIA_ID = "camera-left-media"
FIXTURE_TOKEN = "fixture-local-token"  # noqa: S105 - non-secret deterministic test credential
BASE_NS = 9_007_199_254_740_993

SENSOR_ROWS: tuple[dict[str, Any], ...] = tuple(
    {
        "timestamp_ns": BASE_NS + index * 5_000_000,
        "ax": None if index == 3 else index / 10,
        "ay": index / 5,
        "az": 9.81,
    }
    for index in range(41)
)


class FixtureSensorRepository:
    def describe(self, session_id: str, stream_id: str) -> SensorSource | None:
        if session_id != FIXTURE_SESSION_ID or stream_id != "imu-main":
            return None
        return SensorSource(
            stream_id=stream_id,
            source_uri="aeromaint://fixtures/sync-v1/imu",
            source_sha256="a" * 64,
            fields=IMU_FIELDS,
        )

    def iter_window(
        self, session_id: str, stream_id: str, start_ns: int, end_ns: int
    ) -> Iterable[Mapping[str, Any]]:
        del session_id, stream_id
        return (row for row in SENSOR_ROWS if start_ns <= row["timestamp_ns"] <= end_ns)


@dataclass(frozen=True)
class MediaArtifact:
    media_type: str
    data: bytes


class FixtureMediaRepository:
    def get(self, session_id: str, artifact_id: str) -> MediaArtifact | None:
        if session_id != FIXTURE_SESSION_ID or artifact_id != FIXTURE_MEDIA_ID:
            return None
        return MediaArtifact("video/mp4", FIXTURE_MEDIA)


FRAME_INDEX = tuple(
    {
        "frame_number": index,
        "presentation_ns": BASE_NS + index * 50_000_000,
        "byte_offset": index * 11,
        "byte_length": 10 if index == 4 else 11,
        "keyframe": index in (0, 4),
    }
    for index in range(5)
)
