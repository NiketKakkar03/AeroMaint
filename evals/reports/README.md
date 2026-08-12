# Release evidence index

This directory is the claim ledger for the portfolio candidate. Machine-readable status lives in
[`evidence.json`](evidence.json). A claim is publishable only when it names a retained report,
reproduction command, data scope, and environment. `fixture_only` is intentionally weaker than
representative evaluation; `not_run` is a gap, never a pass.

| Area                     | Status       | Honest conclusion                                              | Evidence/environment                                                                                           |
| ------------------------ | ------------ | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Viewer playback          | measured     | Declared browser budgets passed on one 20-minute synthetic run | [`viewer-20min.json`](../../tests/browser-performance/reports/viewer-20min.json), environment embedded         |
| Sensor rendering         | measured     | Declared browser budgets passed for 2 × 100k synthetic tracks  | [`sensor-rendering.json`](../../tests/browser-performance/reports/sensor-rendering.json), environment embedded |
| Retrieval                | fixture only | 2/2 smoke titles relevant in top five                          | [`evals/rag/report.md`](../rag/report.md); deterministic local fixture                                         |
| Release/reviewer path    | measured     | See command-by-command outcomes and timing                     | [`clean-checkout.md`](clean-checkout.md)                                                                       |
| RUL model quality        | not run      | No approved source/model, so no accuracy claim                 | [model card](../../docs/model_card.md)                                                                         |
| API load/resources       | not run      | Functional coverage is not a load benchmark                    | Gap retained in `evidence.json`                                                                                |
| Agent quality/safety     | not run      | MCP contract coverage is not agent evaluation                  | Gap retained in `evidence.json`                                                                                |
| Export latency/resources | not run      | Functional export tests only                                   | Gap retained in `evidence.json`                                                                                |

The viewer report's `performance.memory` values are browser-exposed JavaScript heap observations, not
whole-system RSS. Zero observed growth must not be generalized beyond that run. The synthetic media
path does not establish hardware decoder throughput or real-dataset behavior.
