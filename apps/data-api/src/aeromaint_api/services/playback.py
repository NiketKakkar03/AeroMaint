import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar

from aeromaint_api.domain.clock import IndexedFrame, frame_at_or_before, nearest_frame
from aeromaint_api.domain.fixtures import FIXTURE_MANIFEST, FIXTURE_SESSION_ID
from aeromaint_api.domain.manifest import CaptureSessionManifest, CaptureStream, StreamGap


@dataclass(frozen=True)
class SessionRecord:
    manifest: CaptureSessionManifest
    created_at: str


@dataclass(frozen=True)
class Sample:
    timestamp_ns: int
    values: dict[str, int | float | str | bool | None]


class SessionRepository(Protocol):
    def sessions(self) -> Sequence[SessionRecord]: ...
    def session(self, session_id: str) -> SessionRecord | None: ...
    def samples(self, session_id: str, stream_id: str) -> Sequence[Sample]: ...
    def frames(self, session_id: str, stream_id: str) -> Sequence[IndexedFrame]: ...


def encode_cursor(offset: int) -> str:
    payload = json.dumps({"offset": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded))
        offset = value["offset"]
        if not isinstance(offset, int) or offset < 0:
            raise ValueError
        return offset
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid cursor") from error


T = TypeVar("T")


def page(values: Sequence[T], cursor: str | None, limit: int) -> tuple[list[T], str | None]:
    offset = decode_cursor(cursor)
    if offset > len(values):
        raise ValueError("invalid cursor")
    items = list(values[offset : offset + limit])
    next_offset = offset + len(items)
    return items, encode_cursor(next_offset) if next_offset < len(values) else None


def select_frame(
    frames: Sequence[IndexedFrame],
    requested_ns: int,
    gaps: Sequence[StreamGap],
    mode: Literal["at_or_before", "nearest"],
) -> IndexedFrame | None:
    if mode == "nearest":
        return nearest_frame(frames, requested_ns, gaps)
    return frame_at_or_before(frames, requested_ns, gaps)


class InMemorySessionRepository:
    """Deterministic adapter used until the database repository is wired in."""

    def __init__(self) -> None:
        base = FIXTURE_MANIFEST.start_ns
        self._sessions = [SessionRecord(FIXTURE_MANIFEST, "2026-01-01T00:00:00Z")]
        self._frames = {
            (FIXTURE_SESSION_ID, "camera-left"): [
                IndexedFrame(0, base, True),
                IndexedFrame(1, base + 50_000_000, False),
                IndexedFrame(2, base + 100_000_000, False),
                IndexedFrame(3, base + 150_000_000, False),
                IndexedFrame(4, base + 200_000_000, True),
            ]
        }
        self._samples = {
            (FIXTURE_SESSION_ID, "imu-main"): [
                Sample(base + offset, {"ax": index / 10, "ay": 0.0, "az": 9.81})
                for index, offset in enumerate(range(0, 200_000_001, 5_000_000))
            ]
        }

    def sessions(self) -> Sequence[SessionRecord]:
        return self._sessions

    def session(self, session_id: str) -> SessionRecord | None:
        return next(
            (item for item in self._sessions if item.manifest.session_id == session_id), None
        )

    def samples(self, session_id: str, stream_id: str) -> Sequence[Sample]:
        return self._samples.get((session_id, stream_id), ())

    def frames(self, session_id: str, stream_id: str) -> Sequence[IndexedFrame]:
        return self._frames.get((session_id, stream_id), ())


def stream_for(record: SessionRecord, stream_id: str) -> CaptureStream | None:
    return next((stream for stream in record.manifest.streams if stream.id == stream_id), None)


def frame_dict(frame: IndexedFrame) -> dict[str, Any]:
    return {
        "frame_number": frame.frame_number,
        "presentation_ns": str(frame.presentation_ns),
        "keyframe": frame.keyframe,
    }
