# ADR 0002: Nanosecond time representation

- Status: Accepted
- Date: 2026-08-03

Related specification: [project documentation](../../AeroMaint_AI_Project_Documentation.md), sections
8, 9, and 16.

## Context

AeroMaint aligns camera frames, sensor samples, annotations, and model outputs across long-running
capture sessions. JavaScript numbers cannot exactly represent every signed 64-bit integer, while
Python and PostgreSQL can. A lossy public representation would make frame selection and gap handling
nondeterministic.

## Decision

The authoritative time value is a signed 64-bit count of nanoseconds. JSON and OpenAPI represent it
as a base-10 string matching `^-?(0|[1-9][0-9]*)$`; TypeScript converts it to `bigint`; Python uses
`int`; PostgreSQL uses `bigint`. Public JSON field names use snake_case. Durations and timestamps are
never serialized as floating-point seconds.

Clock mappings use integer affine parameters and an explicit rounding rule. Floating-point time is
permitted only for bounded presentation calculations after subtracting a nearby integer origin.

## Alternatives considered

- JSON numbers were rejected because JavaScript loses precision above `2^53 - 1`.
- ISO 8601 strings were rejected for device-relative clocks and sub-microsecond arithmetic.
- Decimal seconds were rejected because scale and rounding become implicit.

## Consequences

`packages/contracts`, API schemas, SDKs, adapters, playback, storage, and exports must validate the
same range and string grammar. Boundary and cross-language golden tests are mandatory.

## Revisit triggers

Revisit if a supported transport natively preserves signed 64-bit integers end to end, or if the
platform must represent values outside the signed 64-bit range.
