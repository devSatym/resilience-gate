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

if [[ -d gke_terraform ]]; then
  command -v terraform >/dev/null 2>&1 || {
    echo "terraform is required to validate gke_terraform" >&2
    exit 1
  }
  terraform -chdir=gke_terraform fmt -check -recursive
  terraform -chdir=gke_terraform init -backend=false -input=false >/dev/null
  terraform -chdir=gke_terraform validate
fi

# Check committed shell entrypoints without accidentally treating a developer's
# ignored local configuration as a CI input.
while IFS= read -r -d '' shell_script; do
  bash -n "$shell_script"
done < <(git ls-files -z -- '*.sh')

# Render only Kustomizations that are actually committed. This keeps a local
# worktree with future or experimental manifests from changing CI behavior.
mapfile -d '' -t kustomizations < <(git ls-files -z -- 'kubernetes/**/kustomization.yaml')
if (( ${#kustomizations[@]} > 0 )); then
  command -v kubectl >/dev/null 2>&1 || {
    echo "kubectl is required to validate committed Kustomizations" >&2
    exit 1
  }
  for kustomization in "${kustomizations[@]}"; do
    kubectl kustomize "$(dirname "$kustomization")" >/dev/null
  done
fi

"$python_bin" -m pytest "$@"

if [[ -f signer/test_permit2.py ]]; then
  "$python_bin" -m pytest signer/test_permit2.py
fi

if command -v docker >/dev/null 2>&1; then
  docker compose config --quiet
fi
