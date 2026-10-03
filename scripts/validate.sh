#!/usr/bin/env bash
# Run deterministic checks that need neither cloud credentials nor a cluster.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

python_bin=${PYTHON:-python3}

# Keep the published presentation tied to reviewed source and image bytes.
# This check is offline and never starts a browser, cluster, or paid run.
"$python_bin" scripts/validate-docs.py

if [[ -d helm/url-shortener || -d helm/observability ]]; then
  command -v helm >/dev/null 2>&1 || {
    echo "helm is required to validate committed Helm charts" >&2
    exit 1
  }
fi

if [[ -d helm/url-shortener ]]; then
  helm dependency list helm/url-shortener
  for environment in dev staging prod; do
    values="helm/url-shortener/values-${environment}.yaml"
    helm lint helm/url-shortener --strict --values "$values"
    helm template "url-shortener-${environment}" helm/url-shortener \
      --namespace "url-shortener-${environment}" --values "$values" >/dev/null
  done
fi

if [[ -d helm/observability ]]; then
  helm dependency list helm/observability
  helm lint helm/observability --strict
  helm template observability helm/observability --namespace monitoring >/dev/null
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

# The promotion gate is intentionally testable without a cluster. Check that
# its four baked inputs exist together before the gate-runner Docker build; no
# validation step starts a Job, contacts Prometheus, or invokes testnet APIs.
if [[ -f kubernetes/chaos-experiments/orchestrate.sh ]]; then
  for gate_input in \
    kubernetes/chaos-experiments/orchestrate.sh \
    kubernetes/chaos-experiments/score_experiment.py \
    kubernetes/chaos-experiments/annotate.py \
    kubernetes/chaos-experiments/workflow.yaml; do
    [[ -f "$gate_input" ]] || {
      echo "missing required chaos-gate input: $gate_input" >&2
      exit 1
    }
  done
  bash -n kubernetes/chaos-experiments/orchestrate.sh
fi

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
