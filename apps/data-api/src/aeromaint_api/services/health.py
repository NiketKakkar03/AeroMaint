"""Deterministic, dependency-free health inference and versioned artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

VERSIONS = {
    "model": "rul-linear-1",
    "features": "health-core-1",
    "data": "capture-v1",
    "code": "health-service-1",
}
SCHEMA_VERSION = "1.0.0"


def infer_track(
    engine_id: str, session_id: str, observations: list[dict[str, Any]]
) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    history: dict[str, list[float]] = {}
    for index, observation in enumerate(observations):
        features = {key: float(value) for key, value in observation.get("features", {}).items()}
        status = "ok"
        reason: str | None = None
        ood: list[str] = []
        if index < 2:
            status, reason = "insufficient_history", "requires at least 3 observations"
        else:
            for name, value in features.items():
                prior = history.get(name, [])
                if not math.isfinite(value) or abs(value) > 1_000_000:
                    ood.append(name)
                elif len(prior) >= 2:
                    mean = sum(prior) / len(prior)
                    spread = max(
                        0.01, math.sqrt(sum((item - mean) ** 2 for item in prior) / len(prior))
                    )
                    if abs(value - mean) > 8 * spread:
                        ood.append(name)
            if ood:
                status, reason = "ood", "out-of-distribution features"
        z_scores: list[float] = []
        for name, value in features.items():
            prior = history.get(name, [])
            if len(prior) >= 2:
                mean = sum(prior) / len(prior)
                spread = max(
                    0.01, math.sqrt(sum((item - mean) ** 2 for item in prior) / len(prior))
                )
                z_scores.append(abs(value - mean) / spread)
            history.setdefault(name, []).append(value)
        score = max(z_scores, default=0.0) if status == "ok" else None
        severity = (
            "critical"
            if score is not None and score >= 6
            else "warning"
            if score is not None and score >= 3
            else "none"
        )
        cycle = float(observation.get("cycle", index + 1))
        degradation = sum(max(0.0, abs(value)) for value in features.values()) / max(
            1, len(features)
        )
        rul = max(0.0, 200.0 - cycle - degradation * 0.1) if status == "ok" else None
        radius = max(5.0, 0.12 * rul) if rul is not None else None
        points.append(
            {
                "timestamp_ns": str(observation["timestamp_ns"]),
                "status": status,
                "rul": rul,
                "rul_unit": "cycles",
                "interval": [max(0.0, rul - radius), rul + radius]
                if rul is not None and radius is not None
                else None,
                "horizon": 30,
                "horizon_unit": "cycles",
                "anomaly_score": score,
                "anomaly_severity": severity,
                "reason": reason,
                "ood_features": ood,
                "attribution": [
                    {
                        "feature": name,
                        "contribution": -abs(value) * 0.1 / max(1, len(features)),
                        "unit": "cycles",
                    }
                    for name, value in sorted(features.items())
                ]
                if status == "ok"
                else [],
            }
        )
    identity = json.dumps(
        {
            "engine": engine_id,
            "session": session_id,
            "observations": observations,
            "versions": VERSIONS,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"prediction-{hashlib.sha256(identity.encode()).hexdigest()[:16]}",
        "engine_id": engine_id,
        "session_id": session_id,
        "created_at": "2026-08-11T00:00:00Z",
        "versions": VERSIONS,
        "points": points,
    }


def demo_track(engine_id: str, session_id: str) -> dict[str, Any]:
    offset = sum(engine_id.encode()) % 9
    observations = [
        {
            "timestamp_ns": str(1_000_000_000 * cycle),
            "cycle": cycle,
            "features": {
                "vibration": 1.0 + offset / 20 + cycle * 0.03,
                "temperature": 70 + offset + cycle * 0.4,
            },
        }
        for cycle in range(1, 9)
    ]
    return infer_track(engine_id, session_id, observations)


def engine_summary(track: dict[str, Any]) -> dict[str, Any]:
    latest = track["points"][-1]
    return {
        "engine_id": track["engine_id"],
        "session_id": track["session_id"],
        "status": latest["status"],
        "rul": latest["rul"],
        "rul_unit": latest["rul_unit"],
        "interval": latest["interval"],
        "anomaly_score": latest["anomaly_score"],
        "anomaly_severity": latest["anomaly_severity"],
        "artifact_id": track["artifact_id"],
        "versions": track["versions"],
    }
