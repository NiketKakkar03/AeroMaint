# Current architecture and evidence flow

Status reflects the source at this release candidate, not the historical roadmap.

```mermaid
flowchart LR
  S["Synthetic / EuRoC-like / MCAP fixtures"] --> A["Validated source adapters"]
  A --> C["Canonical manifest + nanosecond clock"]
  C --> API["FastAPI /v1 boundary"]
  API --> TS["TypeScript SDK"]
  API --> PY["Python SDK"]
  TS --> V["Synchronized React viewer"]
  PY --> ML["FD001 RUL research pipeline"]
  API --> MCP["Bounded MCP tools"]
  D["Approved local documents"] --> R["Deterministic hybrid retrieval"]
  R --> MCP
  V --> E["Annotations and aligned exports"]
  ML --> API
  API --> AUDIT["Authorization audit boundary"]
```

The canonical manifest is the hinge: adapters preserve source provenance and clocks; the API exposes
versioned contracts; SDKs preserve nanosecond identity; the viewer, ML, and tool layers consume public
interfaces rather than database internals. Human approval is deliberately outside MCP.

## Trust and evidence boundaries

```mermaid
flowchart TB
  U["Untrusted imported data and documents"] --> VAL["Parsing, schema, path and checksum validation"]
  VAL --> CORE["Local trusted computing boundary"]
  CORE --> OUT["Reports, exports, model tracks, retrieved passages"]
  OUT --> HUMAN{"Qualified human review"}
  HUMAN -->|"prototype evidence only"| DEC["External decision process"]
```

See [threat model](threat_model.md), [limitations](limitations.md), and the
[evidence index](../evals/reports/README.md). A rendered architecture SVG is in
[`docs/demo/architecture.svg`](demo/architecture.svg).
