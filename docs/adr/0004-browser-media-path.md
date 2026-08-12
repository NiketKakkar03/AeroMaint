# ADR 0004: Browser media path with progressive enhancement

- Status: Accepted
- Date: 2026-08-03

Related specification: [current architecture](../architecture.md), sections
16, 17, and 21.

## Context

The viewer must synchronize stereo media with nanosecond sensor data on common browsers. WebCodecs
offers precise control but is not universally available and adds demuxing and worker complexity.

## Decision

Ship an HTML media-element path first, coordinated by the framework-independent playback state
machine. Use indexed presentation timestamps and measured drift rather than treating an element's
clock as authoritative. Add worker-based demuxing and WebCodecs as a capability-detected optimization;
retain the HTML path as the supported fallback.

Media artifacts are immutable and addressable through authenticated HTTP range requests. The API
exposes frame indexes and presentation timestamps without leaking filesystem paths.

## Alternatives considered

- WebCodecs-only playback was rejected for compatibility and implementation risk.
- Independent media-element clocks were rejected because stereo streams would drift.
- Server-rendered frames were rejected as the default due to latency and resource cost.

## Consequences

`apps/viewer`, `packages/playback-core`, future media workers, ingestion, and range delivery must
share frame-index semantics and instrument drift, seek latency, and fallback selection.

## Revisit triggers

Revisit when measured HTML fallback performance misses declared budgets or browser support changes.
