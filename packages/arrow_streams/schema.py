from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

import pyarrow as pa  # type: ignore[import-untyped]

SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class SensorField:
    name: str
    data_type: pa.DataType
    unit: str
    nullable: bool = True


@dataclass(frozen=True)
class SensorWindow:
    stream_id: str
    source_uri: str
    source_sha256: str
    fields: tuple[SensorField, ...]
    rows: Iterable[Mapping[str, Any]]
    mode: Literal["raw", "downsampled"] = "raw"
    algorithm: str = "none"
    requested_max_points: int | None = None
    input_sample_count: int | None = None


def _metadata(window: SensorWindow) -> dict[bytes, bytes]:
    values = {
        "aeromaint.schema_version": SCHEMA_VERSION,
        "aeromaint.stream_id": window.stream_id,
        "aeromaint.provenance.source_uri": window.source_uri,
        "aeromaint.provenance.source_sha256": window.source_sha256,
        "aeromaint.downsampling.mode": window.mode,
        "aeromaint.downsampling.algorithm": window.algorithm,
    }
    if window.requested_max_points is not None:
        values["aeromaint.downsampling.requested_max_points"] = str(window.requested_max_points)
    if window.input_sample_count is not None:
        values["aeromaint.downsampling.input_sample_count"] = str(window.input_sample_count)
    return {key.encode(): value.encode() for key, value in values.items()}


def encode_sensor_window(window: SensorWindow, *, batch_size: int = 4096) -> bytes:
    """Encode a bounded row iterable without materializing its enclosing session."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    fields = [
        pa.field("timestamp_ns", pa.int64(), nullable=False, metadata={b"unit": b"ns"}),
        *[
            pa.field(
                field.name,
                field.data_type,
                nullable=field.nullable,
                metadata={b"unit": field.unit.encode()},
            )
            for field in window.fields
        ],
    ]
    schema = pa.schema(fields, metadata=_metadata(window))
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        pending: list[Mapping[str, Any]] = []
        for row in window.rows:
            pending.append(row)
            if len(pending) == batch_size:
                writer.write_batch(pa.RecordBatch.from_pylist(pending, schema=schema))
                pending.clear()
        if pending:
            writer.write_batch(pa.RecordBatch.from_pylist(pending, schema=schema))
    return cast(bytes, sink.getvalue().to_pybytes())
