from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class SessionSummary:
    id: str
    start_ns: int
    end_ns: int
    display_name: str | None = None
    stream_count: int | None = None
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class StreamSummary:
    id: str
    kind: str
    start_ns: int
    end_ns: int
    schema_ref: str | None = None


@dataclass(frozen=True, slots=True)
class SensorSample:
    timestamp_ns: int
    values: dict[str, object]


@dataclass(frozen=True, slots=True)
class SensorWindow:
    session_id: str
    stream_id: str
    start_ns: int
    end_ns: int
    samples: tuple[SensorSample, ...]
    schema_ref: str | None
    next_cursor: str | None
    downsampled: bool
