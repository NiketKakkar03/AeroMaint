#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
stage=$(mktemp -d "${TMPDIR:-/tmp}/aeromaint-python-consumer.XXXXXX")
trap 'rm -rf "$stage"' EXIT HUP INT TERM

python3 "$root/packages/capture-sdk-python/build_artifacts.py" "$stage/dist"
UV_CACHE_DIR="$stage/uv-cache" uv venv --python python3 --no-project "$stage/venv"
wheel=$(find "$stage/dist" -name '*.whl' -type f)
UV_CACHE_DIR="$stage/uv-cache" uv pip install --python "$stage/venv/bin/python" --no-index --no-deps "$wheel"
"$stage/venv/bin/python" "$root/tests/contract/sdk-python/installed-smoke.py"
UV_CACHE_DIR="$stage/uv-cache" uv pip show --python "$stage/venv/bin/python" --files aeromaint-capture-sdk
tar -tzf "$stage/dist"/*.tar.gz | grep 'aeromaint_capture/py.typed'
printf 'clean packed Python consumer passed: %s\n' "$stage"
