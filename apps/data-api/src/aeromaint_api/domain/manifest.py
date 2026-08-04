from collections.abc import Sequence
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

TimestampNs = Annotated[
    int,
    Field(ge=-(2**63), le=2**63 - 1),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Identified(Protocol):
    id: str


class TimeRange(ContractModel):
    start_ns: TimestampNs
    end_ns: TimestampNs

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end_ns < self.start_ns:
            raise ValueError("end_ns must be greater than or equal to start_ns")
        return self


class ClockDefinition(ContractModel):
    id: str = Field(min_length=1)
    source_epoch_ns: TimestampNs
    session_epoch_ns: TimestampNs
    rate_numerator: int = Field(ge=1)
    rate_denominator: int = Field(ge=1)


class ArtifactDescriptor(ContractModel):
    id: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    logical_key: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: Sha256


class CalibrationReference(ContractModel):
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)


class StreamGap(TimeRange):
    reason: Literal["missing", "corrupt", "clock_discontinuity"]


class CaptureStream(TimeRange):
    id: str = Field(min_length=1)
    kind: Literal["video", "imu", "pose", "event", "telemetry"]
    clock_id: str = Field(min_length=1)
    sample_count: int = Field(ge=0)
    schema_ref: str = Field(min_length=1)
    artifact_ids: list[str]
    calibration_ids: list[str]
    gaps: list[StreamGap]

    @model_validator(mode="after")
    def validate_gaps(self) -> Self:
        previous_end: int | None = None
        for gap in self.gaps:
            if gap.start_ns < self.start_ns or gap.end_ns > self.end_ns:
                raise ValueError("gap range must be contained by the stream range")
            if previous_end is not None and gap.start_ns < previous_end:
                raise ValueError("gaps must be ordered and non-overlapping")
            previous_end = gap.end_ns
        return self


class ManifestProvenance(ContractModel):
    source_type: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    source_sha256: Sha256
    adapter: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)


class CaptureSessionManifest(TimeRange):
    schema_version: Literal["1.0.0"]
    session_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    session_clock_id: str = Field(min_length=1)
    clocks: list[ClockDefinition]
    artifacts: list[ArtifactDescriptor]
    calibrations: list[CalibrationReference]
    streams: list[CaptureStream]
    provenance: ManifestProvenance

    @staticmethod
    def _unique_ids(values: Sequence[Identified], collection: str) -> set[str]:
        ids = {value.id for value in values}
        if len(ids) != len(values):
            raise ValueError(f"{collection} contains duplicate ids")
        return ids

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        clock_ids = self._unique_ids(self.clocks, "clocks")
        artifact_ids = self._unique_ids(self.artifacts, "artifacts")
        calibration_ids = self._unique_ids(self.calibrations, "calibrations")
        self._unique_ids(self.streams, "streams")

        if self.session_clock_id not in clock_ids:
            raise ValueError("session_clock_id references an unknown clock")
        for calibration in self.calibrations:
            if calibration.artifact_id not in artifact_ids:
                raise ValueError("calibration references an unknown artifact")
        for stream in self.streams:
            if stream.start_ns < self.start_ns or stream.end_ns > self.end_ns:
                raise ValueError("stream range must be contained by the session range")
            if stream.clock_id not in clock_ids:
                raise ValueError("stream references an unknown clock")
            if not set(stream.artifact_ids) <= artifact_ids:
                raise ValueError("stream references an unknown artifact")
            if not set(stream.calibration_ids) <= calibration_ids:
                raise ValueError("stream references an unknown calibration")
        return self
