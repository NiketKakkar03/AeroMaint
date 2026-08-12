#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"

token=$(PYTHONPATH=apps/data-api/src uv run python -c \
  'from aeromaint_api.security.auth import create_development_token; print(create_development_token(["viewer"], expires_in_seconds=900))')
export VITE_API_TOKEN="$token"
export AEROMAINT_EMPTY_STATE=true
# Ask Docker to allocate ephemeral host ports so this isolated smoke project can
# run alongside an existing local demo or other developer services.
export POSTGRES_PORT=0
export API_PORT=0
export VIEWER_PORT=0

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
api_port=$(compose port api 8000 | sed 's/.*://')
viewer_port=$(compose port viewer 5173 | sed 's/.*://')

test -n "$api_port"
test -n "$viewer_port"

curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 1 \
  "http://127.0.0.1:${api_port}/health/ready" >/dev/null
sessions=$(curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 1 \
  -H "Authorization: Bearer $token" "http://127.0.0.1:${api_port}/v1/sessions")
test "$sessions" = '{"items":[],"next_cursor":null}'
curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 1 \
  "http://127.0.0.1:${viewer_port}/" | grep -q '<div id="root"></div>'
printf 'empty-state API, viewer, and Compose smoke passed\n'
