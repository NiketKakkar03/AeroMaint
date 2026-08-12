# Limitations and safety classification

> **NON-OPERATIONAL / EDUCATIONAL PROTOTYPE.** AeroMaint is not approved for aircraft maintenance,
> airworthiness, dispatch, return-to-service, flight control, or any other safety-critical decision.
> A qualified human must independently verify source evidence and retain decision authority.

## What the evidence supports

- Deterministic fixture tests support API, SDK, clock, adapter, export, retrieval, and model-contract
  behavior on the cases named in the test suite.
- The retained Chromium reports support bounded viewer behavior only on the recorded synthetic
  fixtures and environment; see [the evidence index](../evals/reports/README.md).
- The RUL implementation has unit/contract coverage, but there is no committed approved FD001
  training run. There is therefore no release-level RUL accuracy claim.
- Retrieval reaches 2/2 top-five title relevance on its tiny deterministic smoke corpus. This is not
  evidence of broad NASA/FAA retrieval, answer correctness, or agent reliability.

## Known product boundaries

| Area       | Current boundary                                    | Required before broader use                                                         |
| ---------- | --------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Media      | Synthetic/mini fixtures; browser-side metrics       | Representative hardware, codecs, long real sequences, failure injection             |
| Data       | Local files and development persistence             | Validated provenance, retention, encryption, backup/restore, access review          |
| ML         | FD001 research pipeline and abstention rules        | Approved data, external validation, calibration, drift monitoring, model governance |
| RAG/agent  | Local deterministic retrieval and bounded MCP tools | Approved corpus evaluation, adversarial testing, human-factors validation           |
| Security   | Development JWT and local deployment assumptions    | Managed OIDC, TLS, secret rotation, durable audit/idempotency, penetration testing  |
| Operations | Developer-run Compose and scripts                   | SLOs, incident response exercises, disaster recovery, supported deployment          |

Measurements that are missing are marked `not_run` in
[`evals/reports/evidence.json`](../evals/reports/evidence.json); absence is never interpreted as a pass.
