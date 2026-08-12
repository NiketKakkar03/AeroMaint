#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

printf '%s\n' \
  'AeroMaint Studio — educational, non-operational decision-support prototype' \
  'Demo: synchronized viewer first, then the same public SDK/API contract.' \
  '' \
  '1. Open docs/demo/README.md and follow the 2:30 storyboard.' \
  '2. Viewer: http://127.0.0.1:5173' \
  '3. API contract: http://127.0.0.1:8000/docs' \
  '4. SDK/API manifest:' \
  '   curl http://127.0.0.1:8000/v1/sessions/fixture-session-001/manifest' \
  '5. Evidence: evals/reports/README.md' \
  ''

if [ "${AEROMAINT_DEMO_LAUNCH:-0}" != "1" ]; then
  printf '%s\n' 'Dry walkthrough complete. Set AEROMAINT_DEMO_LAUNCH=1 to launch local services.'
  exit 0
fi

LOG_DIR=$(mktemp -d "${TMPDIR:-/tmp}/aeromaint-demo.XXXXXX")
API_PID=
VIEWER_PID=
cleanup() {
  [ -z "$VIEWER_PID" ] || kill "$VIEWER_PID" 2>/dev/null || true
  [ -z "$API_PID" ] || kill "$API_PID" 2>/dev/null || true
  printf '\nLogs retained at %s\n' "$LOG_DIR"
}
trap cleanup EXIT INT TERM

PYTHONPATH=apps/data-api/src uv run uvicorn aeromaint_api.main:app --host 127.0.0.1 --port 8000 >"$LOG_DIR/api.log" 2>&1 &
API_PID=$!
pnpm --filter @aeromaint/viewer dev --host 127.0.0.1 --port 5173 >"$LOG_DIR/viewer.log" 2>&1 &
VIEWER_PID=$!
printf '%s\n' 'Services launched. Press Ctrl-C after the walkthrough.'
wait "$API_PID" "$VIEWER_PID"
