"""Strict, checksum-gated support for the NASA C-MAPSS FD001 text format."""

from __future__ import annotations

import hashlib
import math
import shutil
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

SETTING_COLUMNS = tuple(f"setting_{index}" for index in range(1, 4))
SENSOR_COLUMNS = tuple(f"sensor_{index}" for index in range(1, 22))
CMAPSS_COLUMNS = ("engine_id", "cycle", *SETTING_COLUMNS, *SENSOR_COLUMNS)


class CmapssError(ValueError):
    """An FD001 source is malformed or cannot be verified."""


@dataclass(frozen=True)
class CmapssData:
    rows: tuple[dict[str, int | float | None], ...]
    source_path: Path
    source_sha256: str

    @property
    def engine_ids(self) -> tuple[int, ...]:
        return tuple(sorted({cast(int, row["engine_id"]) for row in self.rows}))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_digest(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise CmapssError("expected SHA-256 must contain exactly 64 hexadecimal characters")
    return normalized


def _safe_members(bundle: zipfile.ZipFile) -> Iterator[zipfile.ZipInfo]:
    for member in bundle.infolist():
        parts = Path(member.filename).parts
        if Path(member.filename).is_absolute() or ".." in parts:
            raise CmapssError(f"unsafe archive member: {member.filename}")
        yield member


def acquire_fd001(
    url: str,
    destination: Path,
    expected_sha256: str,
    *,
    opener: Callable[[str, str], object] = urllib.request.urlretrieve,
) -> Path:
    """Optionally acquire FD001, refusing untrusted or unsafe archives.

    No default URL or digest is embedded: callers must supply both from an approved
    acquisition record. Existing local input can be passed directly to ``parse_fd001``.
    """
    expected = _expected_digest(expected_sha256)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aeromaint-cmapss-") as temporary:
        archive = Path(temporary) / "cmapss.zip"
        opener(url, str(archive))
        actual = _sha256(archive)
        if actual != expected:
            raise CmapssError(f"SHA-256 mismatch: expected {expected}, got {actual}")
        with zipfile.ZipFile(archive) as bundle:
            candidates = [
                m for m in _safe_members(bundle) if Path(m.filename).name == "train_FD001.txt"
            ]
            if len(candidates) != 1:
                raise CmapssError("archive must contain exactly one train_FD001.txt")
            with bundle.open(candidates[0]) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
    return destination


def parse_fd001(path: Path) -> CmapssData:
    """Parse FD001 into typed rows and validate the trajectory schema."""
    path = Path(path)
    rows: list[dict[str, int | float | None]] = []
    last_cycle: dict[int, int] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        values = line.split()
        if not values:
            continue
        if len(values) != len(CMAPSS_COLUMNS):
            raise CmapssError(
                f"{path}:{line_number}: expected {len(CMAPSS_COLUMNS)} columns, got {len(values)}"
            )
        try:
            engine_value, cycle_value = float(values[0]), float(values[1])
            if not engine_value.is_integer() or not cycle_value.is_integer():
                raise ValueError
            engine_id, cycle = int(engine_value), int(cycle_value)
            numeric = [float(value) for value in values[2:]]
        except ValueError as error:
            raise CmapssError(f"{path}:{line_number}: non-numeric identifier or value") from error
        if engine_id < 1 or cycle < 1:
            raise CmapssError(f"{path}:{line_number}: engine and cycle must be positive")
        if last_cycle.get(engine_id, 0) >= cycle:
            raise CmapssError(f"{path}:{line_number}: cycles must increase within each engine")
        last_cycle[engine_id] = cycle
        converted: list[float | None] = [
            value if math.isfinite(value) else None for value in numeric
        ]
        rows.append(dict(zip(CMAPSS_COLUMNS, [engine_id, cycle, *converted], strict=True)))
    if not rows:
        raise CmapssError(f"{path}: contains no telemetry rows")
    return CmapssData(tuple(rows), path, _sha256(path))
