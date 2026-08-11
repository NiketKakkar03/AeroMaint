from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from packages.models.rul import RulModel
from pipelines.training.rul import evaluate, metrics, model_diagnostics, train_model


def _rows(engine: int, offset: float = 0.0) -> list[dict[str, float | int]]:
    return [
        {
            "engine_id": engine,
            "cycle": cycle,
            "sensor": offset + cycle / 10.0,
            "rul": 20.0 - 2.0 * cycle + (1.0 if cycle % 2 else 0.0),
        }
        for cycle in range(1, 10)
    ]


def _model() -> RulModel:
    return train_model(
        _rows(1) + _rows(2, 0.02),
        _rows(3, 0.01),
        features=("cycle", "sensor"),
        versions={"model": "test", "features": "f1", "dataset": "d1", "code": "c1"},
        rul_cap=20,
        rounds=24,
        minimum_history=3,
    )


def test_prediction_interval_attribution_and_golden_round_trip(tmp_path: Path) -> None:
    model = _model()
    history = _rows(4, 0.01)[:5]
    prediction = model.predict(history)
    assert prediction.status == "ok"
    assert prediction.rul == pytest.approx(10.975765968677461)
    assert prediction.interval == pytest.approx((7.737926376663099, 14.213605560691823))
    assert prediction.rul == pytest.approx(model.initial + sum(prediction.attribution.values()))

    path = tmp_path / "model.json"
    model.save(path)
    restored = RulModel.load(path)
    assert restored.predict(history) == prediction
    assert json.loads(path.read_text(encoding="utf-8"))["versions"]["dataset"] == "d1"


def test_abstains_for_insufficient_invalid_and_ood_history() -> None:
    model = _model()
    assert model.predict(_rows(4)[:2]).status == "abstain"
    missing = _rows(4)[:3]
    del missing[-1]["sensor"]
    assert model.predict(missing).reason == "required features missing"
    invalid = _rows(4)[:3]
    invalid[-1]["sensor"] = math.nan
    assert model.predict(invalid).reason == "non-finite features"
    ood = _rows(4)[:3]
    ood[-1]["sensor"] = 100.0
    result = model.predict(ood)
    assert result.reason == "out-of-distribution features"
    assert result.ood_features == ("sensor",)


def test_metrics_nasa_asymmetry_and_diagnostics() -> None:
    early = metrics([10.0], [5.0])
    late = metrics([10.0], [15.0])
    assert late.nasa_score > early.nasa_score
    report = evaluate(_rows(5), lambda row: float(row["rul"]) + 1.0)
    assert report["overall"]["rmse"] == 1.0
    assert set(report["per_engine"]) == {"5"}
    assert report["per_horizon"]["0-30"] is not None
    diagnostics = model_diagnostics(_model(), _rows(5, 0.01))
    assert 0.0 <= diagnostics["interval"]["empirical_coverage"] <= 1.0
    assert diagnostics["interval"]["mean_width"] > 0.0
    assert diagnostics["ood"]["rows"] == 0
    assert set(diagnostics["mean_absolute_attribution"]) == {"cycle", "sensor"}


def test_selected_model_beats_declared_cycle_baselines_on_held_out_engine() -> None:
    train = _rows(1) + _rows(2, 0.02)
    held_out = _rows(3, 0.01)
    model = train_model(
        train,
        held_out,
        features=("cycle", "sensor"),
        versions={"model": "m", "features": "f", "dataset": "d", "code": "c"},
        rul_cap=20,
        rounds=24,
    )
    guesses = [model.predict([row] * 3).rul for row in held_out]
    selected = metrics([float(row["rul"]) for row in held_out], [float(value) for value in guesses])
    persistence = metrics(
        [float(row["rul"]) for row in held_out],
        [20.0 - float(row["cycle"]) for row in held_out],
    )
    constant = metrics(
        [float(row["rul"]) for row in held_out],
        [sum(float(row["rul"]) for row in train) / len(train)] * len(held_out),
    )
    assert selected.rmse < min(persistence.rmse, constant.rmse)
