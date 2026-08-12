# Model card: AeroMaint FD001 RUL baseline

## Status and safety

**Research prototype; not trained or promoted in this release.** The repository implements a
deterministic CPU gradient-boosted-stump pipeline for NASA C-MAPSS FD001. No approved FD001 source or
generated model is committed, and this release makes no held-out accuracy claim. Never use output for
maintenance, airworthiness, or safety decisions.

## Intended use

Pipeline testing, reproducibility experiments, and UI/API integration with model tracks. Out of
scope: real-engine prognostics, fleet comparison, maintenance scheduling, or autonomous action.

## Training and evaluation design

- Engine IDs, never individual rows, are deterministically split into train/validation/test.
- Imputation and standardization state is fit on training engines only.
- Selection requires validation RMSE better than both declared cycle baselines.
- Reports include RMSE, asymmetric NASA score, per-engine and RUL-horizon slices, interval coverage,
  training-range OOD rate, runtime, and dataset/feature/code/model versions.
- Inference abstains for fewer than three observations, missing/non-finite features, and values
  outside training feature ranges.

The generated `evaluation.json`, `experiment.json`, `model.json`, and `MODEL_CARD.md` are immutable
experiment artifacts. Reproduce them with the checksum-gated workflow in the
[dataset card](dataset_card.md) and `make cmapss-train`.

## Limitations

FD001 is simulated, has one operating condition and fault mode, and cannot establish performance on
real engines. Training-range checks do not detect every distribution shift. Symmetric residual
intervals are not conditionally calibrated safety bounds. Additive stump contributions are not
causal explanations. Subgroup/fairness analysis is not meaningful until a representative deployment
population and protected operational contexts are defined.

## Release evidence

| Gate                                                      | Status                      | Evidence                                                   |
| --------------------------------------------------------- | --------------------------- | ---------------------------------------------------------- |
| Unit-level prediction, abstention, metrics, serialization | exercised by release checks | [`tests/ml/test_rul.py`](../tests/ml/test_rul.py)          |
| Approved FD001 preparation and training                   | `not_run`                   | No approved source available in repository                 |
| Held-out FD001 metrics                                    | `not_run`                   | Generated only after a successful approved training run    |
| External/operational validation                           | `not_run`                   | No representative operational dataset or approval protocol |
