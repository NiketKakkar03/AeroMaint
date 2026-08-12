# ADR 0005: Apache Arrow sensor-window transport

- Status: Accepted
- Date: 2026-08-03

Related specification: [current architecture](../architecture.md), sections
16 and 21.

## Context

Dense IMU, pose, and telemetry windows are expensive to transfer and parse as JSON. Their schemas
must preserve integer timestamps, units, nullability, provenance, and downsampling information.

## Decision

Serve bounded sensor windows as Arrow IPC streams. Each schema includes a signed 64-bit `timestamp_ns`
column, stable field names, units metadata, nullability, source stream identity, schema version, and
downsampling metadata. JSON remains available for small control documents such as manifests and
errors, not dense samples.

Requests always specify a bounded time window and optional documented resolution. Implementations
stream record batches so memory scales with the requested window rather than the entire session.

## Alternatives considered

- JSON arrays were rejected for size, parsing cost, and integer ambiguity.
- Protobuf was rejected for the browser analytics and columnar use case.
- Returning whole-session files was rejected because it defeats bounded access.

## Consequences

`packages/arrow-streams`, API range services, SDKs, workers, and timeline renderers share versioned
Arrow schemas and round-trip tests.

## Revisit triggers

Revisit if browser Arrow support or workload measurements show another format materially improves
interoperability or resource usage.
