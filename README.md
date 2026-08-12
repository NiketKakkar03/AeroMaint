# AeroMaint Studio

AeroMaint Studio is a local-first multimodal aerospace data platform for synchronized media and sensor review, developer SDKs, predictive-maintenance experiments, and evidence-grounded engineering decision support.

> Educational decision-support prototype only. It is not approved for aircraft maintenance or vehicle control.

## Portfolio release

Start with the [two-to-three-minute viewer/SDK demo](docs/demo/README.md), then use the
[release evidence index](evals/reports/README.md) to distinguish measured results from unrun or
fixture-only gates. Safety boundaries are summarized in [limitations](docs/limitations.md), the
[threat model](docs/threat_model.md), and the [model card](docs/model_card.md).

```bash
make portfolio-demo # prints the viewer/API-first portfolio walkthrough
make release-check # checks local links, evidence references, and release metadata
```

## Initial stack

- **Web:** React 19, TypeScript (strict), Vite, TanStack Query
- **Platform contracts:** framework-independent TypeScript packages using nanosecond `bigint` timestamps
- **API and workers:** Python 3.11, FastAPI, Pydantic, structured logging
- **Data:** PostgreSQL 16 with pgvector; local filesystem artifacts for the MVP
- **Tooling:** pnpm workspaces, Turborepo, uv, ESLint, Prettier, Ruff, mypy, Vitest, Pytest
- **Local runtime:** Docker Compose with optional profiles as the system grows

The architecture starts as a modular monolith. The viewer, SDKs, ML services, and future copilot will depend on public contracts rather than storage internals.

## Prerequisites

- Node.js 22.13+
- pnpm 11+
- Python 3.11 and uv
- Docker Desktop or another Compose-compatible local runtime

## Bootstrap

```bash
make bootstrap
make demo
```

This generates ignored local credentials, validates Compose, starts the minimal core profile, runs
migrations, and seeds a tiny synthetic fixture. It does not download model weights or large media.
See the [local release runbook](./docs/runbook.md) for profiles, resource budgets, observability,
backup/restore, reset safeguards, and release drills.

For host-based development, install dependencies and run checks explicitly:

```bash
pnpm install
uv sync --python 3.11
make check
```

Run the frontend and API in separate terminals:

```bash
pnpm --filter @aeromaint/viewer dev
uv run uvicorn aeromaint_api.main:app --app-dir apps/data-api/src --reload
```

Or start the containerized core profile:

```bash
make up-core
```

- Viewer: <http://localhost:5173>
- API documentation: <http://localhost:8000/docs>
- API readiness: <http://localhost:8000/health/ready>

## Repository layout

```text
apps/viewer          React viewer and developer surface
apps/data-api        Versioned FastAPI data API
apps/worker          Background ingestion and media jobs
packages/contracts   Canonical cross-client data contracts
packages/playback-core  Framework-independent timeline logic
docs/adr             Architectural decision records
infrastructure       Local deployment configuration
```

The current system map is in [docs/architecture.md](docs/architecture.md). Historical private design
notes are intentionally not required by the reviewer path.

## Phase 0 fixture vertical slice

The API exposes one deterministic in-memory fixture while persistence and real ingestion are built:

```bash
curl http://localhost:8000/v1/sessions/fixture-session-001/manifest
```

The `@aeromaint/capture-sdk` package consumes this endpoint and converts decimal-string nanosecond
timestamps to `bigint`. Run `make check` to execute the Python endpoint, OpenAPI, contract, and SDK
tests together.
