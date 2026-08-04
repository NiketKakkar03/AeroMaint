from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

TimestampNs = Annotated[
    int,
    Field(ge=-(2**63), le=2**63 - 1),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]


class CaptureStream(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Literal["video", "imu", "pose", "event", "telemetry"]
    clock_id: str = Field(min_length=1)
    start_ns: TimestampNs
    end_ns: TimestampNs
    sample_count: int = Field(ge=0)


class CaptureSessionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    session_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    start_ns: TimestampNs
    end_ns: TimestampNs
    streams: list[CaptureStream]
