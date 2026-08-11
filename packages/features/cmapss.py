"""Leakage-safe C-MAPSS feature preprocessing."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from packages.telemetry.cmapss import SENSOR_COLUMNS, SETTING_COLUMNS

INPUT_COLUMNS = (*SETTING_COLUMNS, *SENSOR_COLUMNS)
TRANSFORM_VERSION = "aeromaint.cmapss-standardize/v1"


@dataclass(frozen=True)
class TransformedData:
    rows: tuple[dict[str, int | float | str], ...]
    checksum: str


@dataclass(frozen=True)
class CmapssPreprocessor:
    medians: dict[str, float]
    means: dict[str, float]
    scales: dict[str, float]
    active_features: tuple[str, ...]
    constant_features: tuple[str, ...]
    fit_engine_ids: tuple[int, ...]
    missing_policy: str = "median"
    constant_policy: str = "drop"
    version: str = TRANSFORM_VERSION

    @classmethod
    def fit(cls, rows: list[dict[str, Any]]) -> CmapssPreprocessor:
        if not rows:
            raise ValueError("training rows are required to fit preprocessing")
        medians: dict[str, float] = {}
        means: dict[str, float] = {}
        scales: dict[str, float] = {}
        constants: list[str] = []
        active: list[str] = []
        for column in INPUT_COLUMNS:
            observed = sorted(float(row[column]) for row in rows if row.get(column) is not None)
            if not observed:
                raise ValueError(f"feature {column} is entirely missing in training data")
            middle = len(observed) // 2
            median = (
                observed[middle]
                if len(observed) % 2
                else (observed[middle - 1] + observed[middle]) / 2
            )
            filled = [float(row[column]) if row.get(column) is not None else median for row in rows]
            mean = math.fsum(filled) / len(filled)
            variance = math.fsum((value - mean) ** 2 for value in filled) / len(filled)
            medians[column], means[column] = median, mean
            if variance <= 1e-24:
                constants.append(column)
            else:
                active.append(column)
                scales[column] = math.sqrt(variance)
        return cls(
            medians,
            means,
            scales,
            tuple(active),
            tuple(constants),
            tuple(sorted({int(row["engine_id"]) for row in rows})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "missing_policy": self.missing_policy,
            "constant_policy": self.constant_policy,
            "fit_engine_ids": list(self.fit_engine_ids),
            "active_features": list(self.active_features),
            "constant_features": list(self.constant_features),
            "medians": self.medians,
            "means": self.means,
            "scales": self.scales,
        }

    def transform(self, rows: list[dict[str, Any]], split: str, rul_cap: int) -> TransformedData:
        output: list[dict[str, int | float | str]] = []
        maximum_cycles: dict[int, int] = {}
        for row in rows:
            engine_id = int(row["engine_id"])
            maximum_cycles[engine_id] = max(maximum_cycles.get(engine_id, 0), int(row["cycle"]))
        for row in rows:
            engine_id, cycle = int(row["engine_id"]), int(row["cycle"])
            transformed: dict[str, int | float | str] = {
                "engine_id": engine_id,
                "cycle": cycle,
                "split": split,
                "rul": min(rul_cap, maximum_cycles[engine_id] - cycle),
            }
            for column in self.active_features:
                value = row.get(column)
                filled = self.medians[column] if value is None else float(value)
                transformed[column] = (filled - self.means[column]) / self.scales[column]
            output.append(transformed)
        canonical = json.dumps(
            output, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        return TransformedData(tuple(output), hashlib.sha256(canonical).hexdigest())
