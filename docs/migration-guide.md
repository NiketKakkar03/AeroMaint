# Migration guide

## From the phase-7 foundation to the portfolio release

No HTTP, manifest, or SDK breaking change is introduced. Existing `/v1` clients continue to work.

1. Use `make release-check` as the documentation/evidence gate in addition to `make check`.
2. Replace links to the untracked historical project document with `docs/architecture.md`.
3. Treat `evals/reports/evidence.json` as the machine-readable claim inventory. `not_run` is a gap,
   not a failure silently promoted to success.
4. Produce distributable source archives with `make release-archive` from a clean committed tree.
   The command writes an archive, SHA-256 file, and manifest under `dist/release/`.
5. Continue to version SDK, HTTP API, manifest schema, dataset, feature, and model artifacts
   independently. Do not infer compatibility from the repository release label alone.

Rollback is source-only: check out the previous commit/tag and rebuild. Database down migrations are
development aids and require backup/restore rehearsal before any persistent deployment.
