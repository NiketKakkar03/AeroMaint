# ADR 0007: PostgreSQL persistence boundaries

- Status: Accepted
- Date: 2026-08-10

## Decision

PostgreSQL stores session manifests, queryable stream metadata, import workflow state,
annotations, and append-only audit events. Artifact rows contain only immutable logical keys,
content digests, media types, and sizes; media bytes remain in the artifact store.

Repository protocols separate domain consumers from psycopg. Import idempotency is enforced by a
unique database constraint and an atomic `INSERT ... ON CONFLICT`, so it remains correct across API
processes. Migrations are ordered, transactional SQL resources and the API can apply them during
startup. Audit immutability is enforced in PostgreSQL, not merely by repository convention.
