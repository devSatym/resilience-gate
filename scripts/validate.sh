#!/usr/bin/env bash
# Run deterministic checks that need neither cloud credentials nor a cluster.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

python_bin=${PYTHON:-python3}
"$python_bin" -m pytest "$@"

if command -v docker >/dev/null 2>&1; then
  docker compose config --quiet
fi
