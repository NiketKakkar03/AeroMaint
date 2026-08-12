# Portfolio release notes

## AeroMaint Studio 0.1.0 portfolio candidate

This release candidate packages the implemented local-first viewer, public SDK contracts, ingestion
adapters, deterministic RUL research pipeline, evidence-grounded retrieval, and bounded MCP tools for
review. It is a recruiter-facing engineering artifact, not an operational aviation product.

### Reviewer path

1. Read [limitations](limitations.md) (one minute).
2. Run the [viewer/SDK-first demo](demo/README.md) (two to three minutes after bootstrap).
3. Inspect the [evidence index](../evals/reports/README.md) and retained reports.
4. Review the [architecture](architecture.md), [threat model](threat_model.md), dataset/model cards,
   and [runbook](runbook.md).
5. Run `make release-check`; use `make check` for the full source gate.

### Evidence-backed highlights

- A retained 20-minute synthetic Chromium viewer run passed its declared seek, dropped-frame, drift,
  and browser heap-growth budgets on the environment recorded in the JSON report.
- TypeScript and Python SDKs preserve nanosecond timestamps without lossy JavaScript conversion and
  have packed-artifact smoke paths.
- EuRoC-like and MCAP mini fixtures exercise a shared canonical adapter contract.
- Retrieval has citation-preserving deterministic smoke coverage, explicitly limited to two queries.

### Not included

No QLoRA, DPO, quantization, production model, operational dataset, hosted deployment, or broad agent
quality claim is included. API load/resource, export end-to-end latency, full-corpus RAG, and clean
room setup on non-macOS hosts remain documented gaps.

Archive provenance is produced only from a clean commit by `make release-archive`; see the
[runbook](runbook.md).
