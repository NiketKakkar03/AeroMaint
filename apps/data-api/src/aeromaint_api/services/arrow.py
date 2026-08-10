from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import pyarrow as pa  # type: ignore[import-untyped]
from packages.arrow_streams import SensorField, SensorWindow, encode_sensor_window


@dataclass(frozen=True)
class SensorSource:
    stream_id: str
    source_uri: str
    source_sha256: str
    fields: tuple[SensorField, ...]


class SensorRepository(Protocol):
    def describe(self, session_id: str, stream_id: str) -> SensorSource | None: ...

    def iter_window(
        self, session_id: str, stream_id: str, start_ns: int, end_ns: int
    ) -> Iterable[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class ArrowResult:
    body: bytes
    mode: Literal["raw", "downsampled"]
    input_sample_count: int
    output_sample_count: int


def _evenly_spaced(
    rows: Iterable[Mapping[str, Any]], max_points: int
) -> tuple[Iterator[Mapping[str, Any]], int]:
    materialized = list(rows)
    count = len(materialized)
    if count <= max_points:
        return iter(materialized), count
    if max_points == 1:
        return iter(materialized[:1]), count
    indexes = {(index * (count - 1)) // (max_points - 1) for index in range(max_points)}
    return (row for index, row in enumerate(materialized) if index in indexes), count


def build_arrow_window(
    repository: SensorRepository,
    session_id: str,
    stream_id: str,
    start_ns: int,
    end_ns: int,
    *,
    max_points: int | None,
) -> ArrowResult | None:
    source = repository.describe(session_id, stream_id)
    if source is None:
        return None
    rows = repository.iter_window(session_id, stream_id, start_ns, end_ns)
    mode: Literal["raw", "downsampled"] = "raw"
    algorithm = "none"
    if max_points is None:
        selected = iter(rows)
        input_count = -1
    else:
        selected, input_count = _evenly_spaced(rows, max_points)
        mode = "downsampled"
        algorithm = "endpoint-preserving-even-spacing-v1"
    selected_rows = list(selected)
    if input_count < 0:
        input_count = len(selected_rows)
    body = encode_sensor_window(
        SensorWindow(
            stream_id=source.stream_id,
            source_uri=source.source_uri,
            source_sha256=source.source_sha256,
            fields=source.fields,
            rows=selected_rows,
            mode=mode,
            algorithm=algorithm,
            requested_max_points=max_points,
            input_sample_count=input_count,
        )
    )
    return ArrowResult(body, mode, input_count, len(selected_rows))


IMU_FIELDS = (
    SensorField("ax", pa.float64(), "m/s^2", nullable=True),
    SensorField("ay", pa.float64(), "m/s^2", nullable=True),
    SensorField("az", pa.float64(), "m/s^2", nullable=True),
)
