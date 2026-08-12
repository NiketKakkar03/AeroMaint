#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup="$(mktemp "${TMPDIR:-/tmp}/aeromaint-drill.XXXXXX.dump")"
trap 'rm -f "$backup"' EXIT
"$root/scripts/local-release" demo
"$root/scripts/local-release" backup --target local --output "$backup"
"$root/scripts/local-release" restore --target local --input "$backup"
docker compose --project-directory "$root" --env-file "$root/.env.local-release" --profile core \
  exec -T postgres psql -U aeromaint -d aeromaint -Atc \
  "SELECT id FROM local_demo_sessions WHERE id='synthetic-session'" | grep -qx synthetic-session
echo "backup/restore drill passed"
