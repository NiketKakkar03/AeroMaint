"""Deterministic reader for the EuRoC MAV directory convention."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

ADAPTER_VERSION = "1.0.0"
I64_MIN = -(2**63)
I64_MAX = 2**63 - 1
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class SourceValidationError(ValueError):
    """The source cannot be safely interpreted as EuRoC."""


@dataclass(frozen=True)
class CameraRecord:
    timestamp_ns: int
    filename: str
    path: Path
    status: str
    sha256: str | None


@dataclass(frozen=True)
class NumericRecord:
    timestamp_ns: int
    values: tuple[str, ...]


@dataclass(frozen=True)
class EuRoCSource:
    root: Path
    source_sha256: str
    cameras: dict[str, tuple[CameraRecord, ...]]
    imu: tuple[NumericRecord, ...]
    pose: tuple[NumericRecord, ...]
    calibration: dict[str, str]
    rates_hz: dict[str, int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        size = path.stat().st_size
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: str, path: Path, row_number: int) -> int:
    if not re.fullmatch(r"-?(0|[1-9][0-9]*)", value):
        raise SourceValidationError(f"{path}:{row_number}: timestamp is not a canonical integer")
    parsed = int(value)
    if parsed < I64_MIN or parsed > I64_MAX:
        raise SourceValidationError(
            f"{path}:{row_number}: timestamp is outside signed 64-bit range"
        )
    return parsed


def _rows(path: Path, minimum_columns: int) -> list[tuple[int, tuple[str, ...]]]:
    records: list[tuple[int, tuple[str, ...]]] = []
    with path.open(encoding="utf-8", newline="") as source:
        for row_number, row in enumerate(csv.reader(source), start=1):
            if not row or row[0].lstrip().startswith("#"):
                continue
            values = tuple(value.strip() for value in row)
            if len(values) < minimum_columns or any(value == "" for value in values):
                raise SourceValidationError(f"{path}:{row_number}: malformed CSV record")
            timestamp = _timestamp(values[0], path, row_number)
            if records and timestamp <= records[-1][0]:
                raise SourceValidationError(
                    f"{path}:{row_number}: timestamps must be strictly increasing"
                )
            records.append((timestamp, values[1:]))
    if not records:
        raise SourceValidationError(f"{path}: contains no records")
    return records


def _valid_image(path: Path) -> bool:
    try:
        prefix = path.read_bytes()[:8]
    except OSError:
        return False
    return prefix.startswith(PNG_SIGNATURE) or prefix.startswith((b"P2\n", b"P5\n"))


def _rate(sensor_yaml: str, sensor: str) -> int:
    match = re.search(r"(?m)^rate_hz:\s*([1-9][0-9]*)\s*$", sensor_yaml)
    if match is None:
        raise SourceValidationError(f"{sensor}/sensor.yaml: missing positive integer rate_hz")
    return int(match.group(1))


class EuRoCAdapter:
    """Recognize and parse EuRoC data without publishing storage artifacts."""

    required = ("cam0", "cam1", "imu0")

    def read(self, source: Path) -> EuRoCSource:
        root = source / "mav0" if (source / "mav0").is_dir() else source
        if not root.is_dir():
            raise SourceValidationError(f"source directory does not exist: {source}")
        missing = [name for name in self.required if not (root / name).is_dir()]
        pose_name = next(
            (name for name in ("state_groundtruth_estimate0", "vicon0") if (root / name).is_dir()),
            None,
        )
        if missing or pose_name is None:
            details = ", ".join([*missing, *([] if pose_name else ["pose source"])])
            raise SourceValidationError(f"malformed EuRoC layout; missing: {details}")

        calibration: dict[str, str] = {}
        rates: dict[str, int] = {}
        for sensor in self.required:
            yaml_path = root / sensor / "sensor.yaml"
            if not yaml_path.is_file():
                raise SourceValidationError(f"missing calibration: {yaml_path}")
            text = yaml_path.read_text(encoding="utf-8")
            calibration[sensor] = text
            rates[sensor] = _rate(text, sensor)

        cameras: dict[str, tuple[CameraRecord, ...]] = {}
        for sensor in ("cam0", "cam1"):
            csv_path = root / sensor / "data.csv"
            if not csv_path.is_file():
                raise SourceValidationError(f"missing camera index: {csv_path}")
            camera_records: list[CameraRecord] = []
            for timestamp, values in _rows(csv_path, 2):
                filename = values[0]
                if Path(filename).name != filename:
                    raise SourceValidationError(f"{csv_path}: unsafe image filename {filename}")
                image = root / sensor / "data" / filename
                if not image.is_file():
                    status, digest = "missing", None
                elif not _valid_image(image):
                    status, digest = "corrupt", _sha256(image)
                else:
                    status, digest = "valid", _sha256(image)
                camera_records.append(CameraRecord(timestamp, filename, image, status, digest))
            cameras[sensor] = tuple(camera_records)

        imu_path = root / "imu0" / "data.csv"
        pose_path = root / pose_name / "data.csv"
        if not imu_path.is_file() or not pose_path.is_file():
            raise SourceValidationError("missing IMU or pose CSV")
        imu = tuple(NumericRecord(timestamp, values) for timestamp, values in _rows(imu_path, 7))
        pose = tuple(NumericRecord(timestamp, values) for timestamp, values in _rows(pose_path, 8))
        return EuRoCSource(
            root=root,
            source_sha256=_source_digest(root),
            cameras=cameras,
            imu=imu,
            pose=pose,
            calibration=calibration,
            rates_hz=rates,
        )
