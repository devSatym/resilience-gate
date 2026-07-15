#!/usr/bin/env bash
# Run deterministic checks that need neither cloud credentials nor a cluster.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

python_bin=${PYTHON:-python3}

if [[ -d helm/url-shortener ]]; then
  command -v helm >/dev/null 2>&1 || {
    echo "helm is required to validate helm/url-shortener" >&2
    exit 1
  }
  helm dependency list helm/url-shortener
  for environment in dev staging prod; do
    values="helm/url-shortener/values-${environment}.yaml"
    helm lint helm/url-shortener --strict --values "$values"
    helm template "url-shortener-${environment}" helm/url-shortener \
      --namespace "url-shortener-${environment}" --values "$values" >/dev/null
  done
fi

"$python_bin" -m pytest "$@"

if command -v docker >/dev/null 2>&1; then
  docker compose config --quiet
fi
