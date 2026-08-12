#!/bin/sh
set -eu

command -v pip-audit >/dev/null || { echo 'pip-audit is required' >&2; exit 2; }
command -v trivy >/dev/null || { echo 'trivy is required' >&2; exit 2; }

requirements=$(mktemp "${TMPDIR:-/tmp}/aeromaint-requirements.XXXXXX")
trap 'rm -f "$requirements"' EXIT HUP INT TERM

pnpm audit --audit-level high
uv export --frozen --no-dev --format requirements-txt --no-emit-project --no-hashes \
  --output-file "$requirements"
pip-audit --requirement "$requirements"
docker build --tag aeromaint-api:release -f apps/data-api/Dockerfile .
docker build --tag aeromaint-viewer:release -f apps/viewer/Dockerfile .
trivy image --exit-code 1 --ignore-unfixed --severity HIGH,CRITICAL aeromaint-api:release
trivy image --exit-code 1 --ignore-unfixed --severity HIGH,CRITICAL aeromaint-viewer:release
