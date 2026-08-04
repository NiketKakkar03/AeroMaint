# ADR 0003: Canonical source-adapter boundary

- Status: Accepted
- Date: 2026-08-03

Related specification: [project documentation](../../AeroMaint_AI_Project_Documentation.md), sections
8, 9, and 23.

## Context

EuRoC, ROS 2/MCAP, telemetry datasets, and future capture systems expose different layouts and clock
semantics. Allowing those details into the API or viewer would couple every consumer to every source.

## Decision

A source adapter performs detection, structural validation, metadata extraction, and ordered record
iteration. It emits a source-neutral draft manifest and canonical records; a shared publication
pipeline owns clock normalization, gap detection, artifact creation, validation, and atomic publish.

Adapters must be deterministic for a source digest plus adapter version. Source-specific metadata is
retained only under namespaced provenance. They must report missing or corrupt evidence explicitly
and never interpolate it silently.

## Alternatives considered

- Source-specific APIs were rejected because they duplicate synchronization and client logic.
- A single ingestion parser was rejected because format concerns would become entangled.
- Letting adapters write database rows directly was rejected because it bypasses validation and
  atomic publication.

## Consequences

`packages/source-adapters`, `pipelines/ingestion`, and `apps/worker` share conformance fixtures.
Downstream services consume only the published manifest and artifacts.

## Revisit triggers

Revisit if streaming live ingestion requires incremental publication, while retaining the same
validated public contract.
