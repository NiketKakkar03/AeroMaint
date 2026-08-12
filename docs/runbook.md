# Local release runbook

This runbook operates AeroMaint on Docker Desktop for supported Apple Silicon and Intel Macs.
All commands run from the repository root. Docker Desktop 4.40+, Compose v2, `curl`, `openssl`,
Python 3.11, `uv`, Node 22, and pnpm 11 are expected for the complete validation suite.

## Quick start

```sh
make bootstrap
make demo
```

`bootstrap` validates Compose and generates `.env.local-release` with mode `0600`. The file and
all backups are ignored by Git. `demo` builds only the core profile, runs migrations, waits for
readiness, and inserts one tiny synthetic fixture reference. It never downloads ML models or large
media. Open the viewer at <http://localhost:5173>, the API at <http://localhost:8000/docs>, and
metrics at <http://localhost:8000/metrics>.

Never reuse local defaults outside a developer machine. For shared environments, provide unique
`POSTGRES_PASSWORD`, `AEROMAINT_JWT_SECRET`, and `GRAFANA_ADMIN_PASSWORD` through a secret manager;
do not put secrets in Compose, shell history, images, source control, or backup filenames. Rotate a
possibly exposed local secret by stopping the stack, deleting `.env.local-release`, and rerunning
`make bootstrap`.

## Profiles and budgets

Profiles include their required PostgreSQL, migration, API, and viewer services. Limits below are
Compose container ceilings; host overhead and build cache require additional disk.

| Profile | Extra service | Suggested Docker RAM | Working disk | Command |
|---|---|---:|---:|---|
| `core` | none | 4 GB | 4 GB | `make up-core` |
| `media` | bounded fixture media worker | 6 GB | 8 GB | `make up-media` |
| `ml` | deterministic RUL service, no model download | 6 GB | 8 GB | `make up-ml` |
| `ai` | retrieval/tool service, no LLM weights | 6 GB | 8 GB | `make up-ai` |
| `observe` | Prometheus and Grafana | 6 GB | 10 GB | `make up-observe` |
| `full` | all services | 10 GB | 16 GB | `make up-full` |

Ports can be overridden with `API_PORT`, `VIEWER_PORT`, `MEDIA_PORT`, `ML_PORT`, `AI_PORT`,
`PROMETHEUS_PORT`, and `GRAFANA_PORT`. PostgreSQL is intentionally network-internal. Run `make down`
after any profile.

## Lifecycle commands

- `make seed` idempotently inserts the minimal demonstration row.
- `make ci` validates Compose and runs release contract/API health tests without starting Docker.
- `make smoke PROFILE=core` checks readiness and metrics for a running profile.
- `make smoke-matrix` starts, checks, and stops all six profiles in sequence.
- `make backup TARGET=local OUTPUT=backups/rehearsal.dump` creates a PostgreSQL custom dump.
- `make restore TARGET=local INPUT=backups/rehearsal.dump` replaces matching objects and then
  checks API readiness.
- `make backup-restore-drill` seeds, backs up, restores, and verifies the seed row.
- `make failure-injection` stops PostgreSQL, verifies readiness fails, restarts it, and verifies
  recovery.
- `make reset TARGET=local CONFIRM=RESET` removes containers and all named local volumes.

Restore and reset reject any target except the literal `local`; reset additionally requires the
literal confirmation `RESET`. These guards prevent a mistyped environment variable or empty target
from selecting a remote database. A reset is irreversible unless a prior backup exists.

## Migrations and readiness

The one-shot `migrate` service owns schema upgrades and must complete before the API starts. The API
also retains idempotent startup migration behavior for direct development. `/health/live` reports
process liveness; `/health/ready` performs a PostgreSQL query when configured and returns a failure
if the dependency is unavailable. Migration `0003_exports` is included in the ordered release set.

Inspect migration state:

```sh
docker compose --env-file .env.local-release --profile core exec postgres \
  psql -U aeromaint -d aeromaint -c 'table schema_migrations'
```

## Logs, traces, metrics, and dashboards

API and profile workers emit one-line JSON events. Every API response has `X-Request-ID` and
`X-Trace-ID`; supplying those headers preserves upstream correlation, and the same values appear in
the request log. This local trace path is deliberately weightless: it provides trace correlation
without downloading a separate trace backend.

```sh
docker compose --env-file .env.local-release --profile full logs -f api ml-service ai-service
curl -H 'X-Trace-ID: drill-28' http://localhost:8000/health/ready
```

Prometheus is at <http://localhost:9090>. Grafana is at <http://localhost:3000> and provisions the
**AeroMaint Platform Overview** dashboard. The dashboard exposes readiness/scrape failures, request
count and latency, and model/tool build versions. API `/metrics` is intentionally dependency-free;
profile services expose `/metrics`, `/version`, `/health/live`, and `/health/ready`.

For a failure, first capture `docker compose ps`, correlated JSON logs, `/metrics`, and the relevant
trace ID. Check `migrate` logs before restarting the API. Do not reset volumes as an initial remedy.

## Clean-machine release rehearsal

1. Verify Docker has the profile budget and ports are free.
2. Run `make bootstrap && make demo && make smoke PROFILE=core`.
3. Run `make backup-restore-drill` and `make failure-injection`.
4. Run `make smoke-matrix` when network access for optional images is available.
5. Run `make check` for source tests and static analysis.
6. Save command output and `docker compose images`; run `make down`.
7. Only when the backup has been verified, run `make reset TARGET=local CONFIRM=RESET`.
