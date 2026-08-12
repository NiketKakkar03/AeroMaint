#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for profile in core media ml ai observe full; do
  "$root/scripts/local-release" up --profile "$profile"
  "$root/scripts/local-release" smoke --profile "$profile"
  "$root/scripts/local-release" down
done
