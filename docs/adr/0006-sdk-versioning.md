# ADR 0006: SDK semantic versioning and compatibility

- Status: Accepted
- Date: 2026-08-03

Related specification: [project documentation](../../AeroMaint_AI_Project_Documentation.md), sections
16 and 23.

## Context

The viewer and external clients must evolve independently from storage and server implementation.
Manifest versions, HTTP behavior, and packaged SDK APIs need an explicit compatibility policy.

## Decision

Public SDKs use semantic versioning. Removing or changing a public method, error code, wire field, or
accepted value requires a major release. Additive optional fields and methods are minor releases;
compatible fixes are patches. The `/v1` HTTP namespace and manifest `schema_version` evolve
independently but publish a tested compatibility matrix.

SDKs reject unsupported major manifest versions with typed errors and tolerate unknown additive
fields. They expose domain contracts rather than generated persistence models. Consumer-driven tests
run against a live API, and packed-package tests run outside the monorepo.

## Alternatives considered

- Lockstep server and SDK versions were rejected because deployments and clients update separately.
- Silent best-effort parsing was rejected because it can misinterpret engineering evidence.
- Exposing raw OpenAPI output directly was rejected as the only public API because it lacks domain
  conversions such as `bigint` timestamps.

## Consequences

`packages/capture-sdk-ts`, the future Python SDK, API, contracts, examples, and release automation
must maintain compatibility fixtures and migration notes.

## Revisit triggers

Revisit when supporting a second API major version or when generated clients can preserve all domain
semantics without a handwritten layer.
