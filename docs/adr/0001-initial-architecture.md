# ADR 0001: Initial platform architecture

- Status: Accepted
- Date: 2026-08-03

## Context

AeroMaint needs a media-heavy TypeScript client, stable developer contracts, Python data/ML workflows, and a reproducible local runtime. It must remain practical on a single Mac before any scaling-oriented decomposition.

## Decision

Use a modular monorepo with:

- pnpm workspaces and Turborepo for TypeScript packages and applications;
- React with Vite for the synchronized viewer;
- Python 3.11, uv, and FastAPI for the data API and background jobs;
- PostgreSQL with pgvector for metadata, workflow state, full-text retrieval, and embeddings;
- a local filesystem artifact store first, with object storage introduced only when its semantics are required;
- Docker Compose profiles for reproducible local services.

All authoritative timestamps cross platform boundaries as signed 64-bit nanoseconds encoded as decimal strings in JSON and `bigint` in TypeScript. Consumers depend on versioned contracts rather than persistence models.

Detailed follow-up decisions are indexed in [`../system_design.md`](../system_design.md).

## Consequences

The repository has two toolchains, so a single `make check` command owns the combined quality gate. Deployable processes remain separable without introducing independently versioned microservices prematurely.
