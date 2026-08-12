#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SOURCE_COMMIT=$(git -C "$ROOT" rev-parse HEAD)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/aeromaint-release-rehearsal.XXXXXX")
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

git -C "$ROOT" archive "$SOURCE_COMMIT" | tar -x -C "$WORK"
START=$(date +%s)
(
  cd "$WORK"
  pnpm install --frozen-lockfile
  uv sync --frozen --python 3.11
  make release-check
  pnpm check
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy apps/data-api/src apps/worker/src packages pipelines
  uv run pytest
)
END=$(date +%s)
printf 'source_commit=%s\nelapsed_seconds=%s\n' "$SOURCE_COMMIT" "$((END - START))"
