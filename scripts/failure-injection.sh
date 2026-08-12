#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose --project-directory "$root" --env-file "$root/.env.local-release" --profile core)
"$root/scripts/local-release" demo
"${compose[@]}" stop postgres
if curl -fsS "http://localhost:${API_PORT:-8000}/health/ready" >/dev/null 2>&1; then
  echo "readiness unexpectedly passed without PostgreSQL" >&2; exit 1
fi
"${compose[@]}" start postgres
for _ in {1..30}; do
  curl -fsS "http://localhost:${API_PORT:-8000}/health/ready" >/dev/null && break
  sleep 1
done
"$root/scripts/local-release" smoke --profile core
echo "failure injection passed"
