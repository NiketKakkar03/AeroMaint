#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"

token=$(PYTHONPATH=apps/data-api/src uv run python -c \
  'from aeromaint_api.security.auth import create_development_token; print(create_development_token(["viewer"], expires_in_seconds=900))')
export VITE_API_TOKEN="$token"
export AEROMAINT_EMPTY_STATE=true
export POSTGRES_PORT=15432
export API_PORT=18000
export VIEWER_PORT=15173

compose() {
  docker compose --project-name aeromaint-release-smoke "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    compose --profile core logs --no-color || true
  fi
  compose --profile core down --volumes
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

compose --profile core up --build --wait --wait-timeout 180
curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 1 \
  http://127.0.0.1:18000/health/ready >/dev/null
sessions=$(curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 1 \
  -H "Authorization: Bearer $token" http://127.0.0.1:18000/v1/sessions)
test "$sessions" = '{"items":[],"next_cursor":null}'
curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 1 \
  http://127.0.0.1:15173/ | grep -q '<div id="root"></div>'
printf 'empty-state API, viewer, and Compose smoke passed\n'
