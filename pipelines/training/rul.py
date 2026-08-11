"""Reproducible training and engine-isolated evaluation for FD001 RUL."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq  # type: ignore[import-untyped]
from packages.models.rul import MODEL_FORMAT_VERSION, RulModel, Stump

CODE_VERSION = "aeromaint.issue-23/v1"


@dataclass(frozen=True)
class Metrics:
    rmse: float
    nasa_score: float
    count: int


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1)]


def metrics(actual: list[float], predicted: list[float]) -> Metrics:
    if not actual or len(actual) != len(predicted):
        raise ValueError("actual and predicted values must be non-empty and aligned")
    errors = [guess - truth for truth, guess in zip(actual, predicted, strict=True)]
    rmse = math.sqrt(math.fsum(error * error for error in errors) / len(errors))
    score = math.fsum(
        math.exp(error / 10.0) - 1.0 if error >= 0 else math.exp(-error / 13.0) - 1.0
        for error in errors
    )
    return Metrics(rmse, score, len(errors))


def _linear_cycle(train: list[dict[str, Any]]) -> Callable[[dict[str, Any]], float]:
    xs, ys = [float(row["cycle"]) for row in train], [float(row["rul"]) for row in train]
    mean_x, mean_y = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    denominator = math.fsum((value - mean_x) ** 2 for value in xs)
    slope = (
        math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / denominator
    )
    return lambda row: mean_y + slope * (float(row["cycle"]) - mean_x)


def _candidates(values: list[float], bins: int = 16) -> tuple[float, ...]:
    unique = sorted(set(values))
    if len(unique) < 2:
        return ()
    indexes = sorted(
        {
            max(0, min(len(unique) - 2, round(index * (len(unique) - 1) / bins)))
            for index in range(1, bins)
        }
    )
    return tuple((unique[index] + unique[index + 1]) / 2.0 for index in indexes)


def train_model(
    train: list[dict[str, Any]],
    validation: list[dict[str, Any]],
    *,
    features: tuple[str, ...],
    versions: dict[str, str],
    rul_cap: float,
    rounds: int = 64,
    learning_rate: float = 0.08,
    minimum_history: int = 3,
) -> RulModel:
    if not train or not validation or not features:
        raise ValueError("training, validation, and features are required")
    target = [float(row["rul"]) for row in train]
    initial = math.fsum(target) / len(target)
    predictions = [initial] * len(train)
    stumps: list[Stump] = []
    thresholds = {
        feature: _candidates([float(row[feature]) for row in train]) for feature in features
    }
    for _ in range(rounds):
        residuals = [truth - guess for truth, guess in zip(target, predictions, strict=True)]
        best: tuple[float, str, float, float, float] | None = None
        for feature in features:
            for threshold in thresholds[feature]:
                left = [i for i, row in enumerate(train) if float(row[feature]) <= threshold]
                if not left or len(left) == len(train):
                    continue
                left_set = set(left)
                right = [i for i in range(len(train)) if i not in left_set]
                lv = math.fsum(residuals[i] for i in left) / len(left)
                rv = math.fsum(residuals[i] for i in right) / len(right)
                loss = math.fsum(
                    (residuals[i] - (lv if i in left_set else rv)) ** 2 for i in range(len(train))
                )
                candidate = (loss, feature, threshold, lv, rv)
                if best is None or candidate < best:
                    best = candidate
        if best is None:
            break
        _, feature, threshold, left_value, right_value = best
        stump = Stump(feature, threshold, left_value, right_value)
        stumps.append(stump)
        predictions = [
            guess + learning_rate * stump.value(row)
            for guess, row in zip(predictions, train, strict=True)
        ]
    ranges = {
        feature: (
            min(float(row[feature]) for row in train),
            max(float(row[feature]) for row in train),
        )
        for feature in features
    }
    model = RulModel(
        features,
        initial,
        learning_rate,
        tuple(stumps),
        0.0,
        ranges,
        rul_cap,
        minimum_history,
        versions,
    )
    residuals = []
    for row in validation:
        result = model.predict([row] * minimum_history)
        if result.status == "ok" and result.rul is not None:
            residuals.append(abs(float(row["rul"]) - result.rul))
    if not residuals:
        raise ValueError("validation contains no in-distribution rows for interval calibration")
    return replace(model, interval_radius=_quantile(residuals, 0.9))


def evaluate(
    rows: list[dict[str, Any]], predictor: Callable[[dict[str, Any]], float]
) -> dict[str, Any]:
    actual = [float(row["rul"]) for row in rows]
    predicted = [min(125.0, max(0.0, predictor(row))) for row in rows]
    overall = metrics(actual, predicted)
    horizons = {}
    for label, low, high in (("0-30", 0, 30), ("31-60", 31, 60), ("61-125", 61, 125)):
        indexes = [i for i, value in enumerate(actual) if low <= value <= high]
        horizons[label] = (
            metrics([actual[i] for i in indexes], [predicted[i] for i in indexes]).__dict__
            if indexes
            else None
        )
    engines = {}
    for engine_id in sorted({int(row["engine_id"]) for row in rows}):
        indexes = [i for i, row in enumerate(rows) if int(row["engine_id"]) == engine_id]
        engines[str(engine_id)] = metrics(
            [actual[i] for i in indexes], [predicted[i] for i in indexes]
        ).__dict__
    return {"overall": overall.__dict__, "per_horizon": horizons, "per_engine": engines}


def model_diagnostics(model: RulModel, rows: list[dict[str, Any]]) -> dict[str, Any]:
    covered = 0
    ood_rows = 0
    attribution = {feature: 0.0 for feature in model.features}
    for row in rows:
        estimate, contributions = model.estimate(row)
        lower = max(0.0, estimate - model.interval_radius)
        upper = min(model.rul_cap, estimate + model.interval_radius)
        covered += lower <= float(row["rul"]) <= upper
        ood_rows += any(
            not model.feature_ranges[feature][0]
            <= float(row[feature])
            <= model.feature_ranges[feature][1]
            for feature in model.features
        )
        for feature, value in contributions.items():
            attribution[feature] += abs(value)
    count = len(rows)
    return {
        "interval": {
            "nominal": 0.9,
            "empirical_coverage": covered / count,
            "mean_width": math.fsum(
                min(model.rul_cap, model.estimate(row)[0] + model.interval_radius)
                - max(0.0, model.estimate(row)[0] - model.interval_radius)
                for row in rows
            )
            / count,
        },
        "ood": {"rows": ood_rows, "rate": ood_rows / count},
        "mean_absolute_attribution": {
            feature: value / count for feature, value in attribution.items()
        },
    }


def train_experiment(dataset: Path, output: Path) -> dict[str, Any]:
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    rows = {
        name: pq.read_table(dataset / f"{name}.parquet").to_pylist()
        for name in ("train", "validation", "test")
    }
    excluded = {"engine_id", "cycle", "split", "rul"}
    features = ("cycle", *(key for key in rows["train"][0] if key not in excluded))
    versions = {
        "model": MODEL_FORMAT_VERSION,
        "features": manifest["feature_version"],
        "dataset": manifest["data_version"],
        "code": CODE_VERSION,
    }
    model = train_model(
        rows["train"],
        rows["validation"],
        features=features,
        versions=versions,
        rul_cap=float(manifest["rul_cap"]),
    )
    linear = _linear_cycle(rows["train"])

    def persistence(row: dict[str, Any]) -> float:
        return float(manifest["rul_cap"]) - float(row["cycle"])

    def model_predict(row: dict[str, Any]) -> float:
        return model.estimate(row)[0]

    report: dict[str, Any] = {
        "schema_version": "aeromaint.rul-evaluation/v1",
        "versions": versions,
        "runtime": {
            "python": platform.python_version(),
            "implementation": sys.implementation.name,
            "device": "cpu",
        },
        "validation": {
            "selected": evaluate(rows["validation"], model_predict),
            "diagnostics": model_diagnostics(model, rows["validation"]),
            "baselines": {
                "persistence": evaluate(rows["validation"], persistence),
                "cycle_linear": evaluate(rows["validation"], linear),
            },
        },
        "test": {
            "selected": evaluate(rows["test"], model_predict),
            "diagnostics": model_diagnostics(model, rows["test"]),
            "baselines": {
                "persistence": evaluate(rows["test"], persistence),
                "cycle_linear": evaluate(rows["test"], linear),
            },
        },
        "selection_rule": (
            "lowest validation RMSE; selected model must beat both declared baselines"
        ),
    }
    selected_rmse = report["validation"]["selected"]["overall"]["rmse"]
    baseline_rmse = min(
        item["overall"]["rmse"] for item in report["validation"]["baselines"].values()
    )
    if selected_rmse >= baseline_rmse:
        raise RuntimeError(
            f"model rejected: validation RMSE {selected_rmse:.4f} does not beat "
            f"baseline {baseline_rmse:.4f}"
        )
    output.mkdir(parents=True, exist_ok=False)
    model.save(output / "model.json")
    canonical = json.dumps(report, sort_keys=True, indent=2) + "\n"
    (output / "evaluation.json").write_text(canonical, encoding="utf-8")
    experiment = {
        "versions": versions,
        "model_sha256": hashlib.sha256((output / "model.json").read_bytes()).hexdigest(),
        "evaluation_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
    }
    (output / "experiment.json").write_text(
        json.dumps(experiment, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output / "MODEL_CARD.md").write_text(_model_card(report), encoding="utf-8")
    return report


def _model_card(report: dict[str, Any]) -> str:
    selected = report["test"]["selected"]["overall"]
    versions = json.dumps(report["versions"], sort_keys=True, indent=2)
    return "\n".join(
        (
            "# AeroMaint FD001 RUL model card",
            "",
            "Deterministic CPU gradient-boosted decision stumps trained on engine-isolated "
            "FD001 features.",
            "",
            "## Intended use",
            "",
            "Research and pipeline testing only. This simulated-data model must not support "
            "maintenance, airworthiness, or safety decisions. It abstains on insufficient "
            "history, missing/non-finite input, and features outside training ranges.",
            "",
            "## Evaluation",
            "",
            f"Held-out engine test RMSE: {selected['rmse']:.6f}; NASA score: "
            f"{selected['nasa_score']:.6f}; rows: {selected['count']}. Full per-engine, horizon, "
            "and baseline diagnostics are in `evaluation.json`. Intervals are symmetric "
            "90th-percentile absolute validation residual intervals clipped to the RUL range; "
            "they are not safety guarantees. Attribution is the exact additive stump "
            "contribution by feature, not a causal explanation.",
            "",
            "## Versions",
            "",
            f"```json\n{versions}\n```",
            "",
            "## Limitations",
            "",
            "FD001 has one simulated operating condition and fault mode. Training-range OOD is "
            "intentionally conservative and does not prove in-distribution inputs are safe. "
            "Accuracy, interval coverage, and subgroup behavior require validation on "
            "representative operational data.",
            "",
        )
    )
