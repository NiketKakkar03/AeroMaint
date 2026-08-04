# System design boundaries

The detailed component map and feature flows live in
[`system-architecture-and-feature-flow.md`](./system-architecture-and-feature-flow.md). This document
records the platform boundaries that implementation must preserve.

## Public boundary

The versioned capture-session manifest, HTTP API, and SDKs are the only supported seams between
ingestion, storage, applications, and intelligence services. Persistence models and local paths are
private implementation details.

## Storage boundary

PostgreSQL owns searchable metadata and mutable workflow state: sessions, stream descriptors,
imports, annotations, jobs, permissions, approvals, and append-only audit records. The local
filesystem owns large immutable artifacts for the initial release: media, Arrow data, indexes,
calibration payloads, exports, and model files. Database rows store content-addressed artifact
identifiers, integrity digests, media types, sizes, and relative logical keys—not absolute paths.

Artifact publication is atomic: write and verify under a temporary key, publish immutable content,
then commit its manifest pointer. MinIO or another object store may replace the filesystem only when
multi-host or lifecycle requirements justify it; the artifact repository interface must keep that
change invisible to API consumers.

## Runtime boundary

The project remains a modular monolith with independently runnable viewer, API, and worker processes.
Modules may be extracted only after measured deployment or scaling needs appear. Optional ML,
retrieval, and agent services consume the same public contracts and cannot become prerequisites for
capture review.

## Decision index

- [ADR 0001](./adr/0001-initial-architecture.md): platform stack and modular monorepo.
- [ADR 0002](./adr/0002-time-representation.md): signed nanosecond representation.
- [ADR 0003](./adr/0003-source-adapters.md): canonical adapter interface.
- [ADR 0004](./adr/0004-browser-media-path.md): HTML fallback and WebCodecs enhancement.
- [ADR 0005](./adr/0005-arrow-transport.md): Arrow sensor windows.
- [ADR 0006](./adr/0006-sdk-versioning.md): SDK compatibility policy.
