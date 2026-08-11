"""Dependency-free deterministic remaining-useful-life inference."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODEL_FORMAT_VERSION = "aeromaint.rul-gbstumps/v1"


@dataclass(frozen=True)
class Stump:
    feature: str
    threshold: float
    left: float
    right: float

    def value(self, row: dict[str, Any]) -> float:
        return self.left if float(row[self.feature]) <= self.threshold else self.right


@dataclass(frozen=True)
class RulPrediction:
    status: str
    rul: float | None
    interval: tuple[float, float] | None
    attribution: dict[str, float]
    ood_features: tuple[str, ...]
    reason: str | None = None


@dataclass(frozen=True)
class RulModel:
    features: tuple[str, ...]
    initial: float
    learning_rate: float
    stumps: tuple[Stump, ...]
    interval_radius: float
    feature_ranges: dict[str, tuple[float, float]]
    rul_cap: float
    minimum_history: int
    versions: dict[str, str]
    format_version: str = MODEL_FORMAT_VERSION

    def estimate(self, row: dict[str, Any]) -> tuple[float, dict[str, float]]:
        """Return the numeric estimate used for offline evaluation, without safety gating."""
        attribution = {feature: 0.0 for feature in self.features}
        value = self.initial
        for stump in self.stumps:
            contribution = self.learning_rate * stump.value(row)
            value += contribution
            attribution[stump.feature] += contribution
        return min(self.rul_cap, max(0.0, value)), {
            key: result for key, result in attribution.items() if result != 0.0
        }

    def predict(self, history: list[dict[str, Any]]) -> RulPrediction:
        if len(history) < self.minimum_history:
            return RulPrediction(
                "abstain",
                None,
                None,
                {},
                (),
                f"requires at least {self.minimum_history} observations; received {len(history)}",
            )
        row = history[-1]
        missing = tuple(feature for feature in self.features if feature not in row)
        if missing:
            return RulPrediction("abstain", None, None, {}, missing, "required features missing")
        non_finite = tuple(
            feature for feature in self.features if not math.isfinite(float(row[feature]))
        )
        if non_finite:
            return RulPrediction("abstain", None, None, {}, non_finite, "non-finite features")
        ood = tuple(
            feature
            for feature in self.features
            if not self.feature_ranges[feature][0]
            <= float(row[feature])
            <= self.feature_ranges[feature][1]
        )
        if ood:
            return RulPrediction("abstain", None, None, {}, ood, "out-of-distribution features")
        value, attribution = self.estimate(row)
        radius = self.interval_radius
        return RulPrediction(
            "ok",
            value,
            (max(0.0, value - radius), min(self.rul_cap, value + radius)),
            attribution,
            (),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "features": list(self.features),
            "initial": self.initial,
            "learning_rate": self.learning_rate,
            "stumps": [stump.__dict__ for stump in self.stumps],
            "interval_radius": self.interval_radius,
            "feature_ranges": {key: list(value) for key, value in self.feature_ranges.items()},
            "rul_cap": self.rul_cap,
            "minimum_history": self.minimum_history,
            "versions": self.versions,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RulModel:
        if payload.get("format_version") != MODEL_FORMAT_VERSION:
            raise ValueError("unsupported RUL model format")
        return cls(
            tuple(payload["features"]),
            float(payload["initial"]),
            float(payload["learning_rate"]),
            tuple(Stump(**item) for item in payload["stumps"]),
            float(payload["interval_radius"]),
            {
                key: (float(value[0]), float(value[1]))
                for key, value in payload["feature_ranges"].items()
            },
            float(payload["rul_cap"]),
            int(payload["minimum_history"]),
            dict(payload["versions"]),
        )

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> RulModel:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
