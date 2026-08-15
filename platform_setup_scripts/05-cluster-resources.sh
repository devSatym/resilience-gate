#!/usr/bin/env bash
# Phase 05 — establish the minimum GitOps trust chain in a known target
# context. ClusterSecretStore and the Argo CD repository credential are applied
# directly first, because Argo CD cannot read a private repository without them.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_config

log_step "Phase 05 — cluster resources and root GitOps application"
require_env PROJECT_ID

if is_dry_run; then
  log_info "Dry run: target Kubernetes context is not queried"
else
  require_target_context
fi

css_file="$REPO_ROOT/kubernetes/bootstrap/secrets/cluster-secret-store.yaml"
argocd_secret_file="$REPO_ROOT/kubernetes/bootstrap/secrets/external-secrets-argocd.yaml"
root_app_file="$REPO_ROOT/kubernetes/argocd/root-app.yaml"
for manifest in "$css_file" "$argocd_secret_file" "$root_app_file"; do
  if [ ! -f "$manifest" ]; then
    log_err "Required bootstrap manifest is missing: $manifest"
    exit 1
  fi
done

# A direct invocation is held to the same rendered-config contract as the
# orchestrator. It blocks accidental use of placeholder or stale target IDs.
"$SCRIPTS_DIR/render_config.py" --config "$CONFIG_FILE" --check

log_info "Applying ClusterSecretStore"
k8s_apply "$css_file"
if ! is_dry_run; then
  wait_for "ClusterSecretStore resilience-gate-secrets" \
    "kubectl get clustersecretstore resilience-gate-secrets -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}' | grep -qx True" \
    120
fi

log_info "Applying Argo CD repository ExternalSecret"
k8s_apply "$argocd_secret_file"
if ! is_dry_run; then
  wait_for "Argo CD repository credential" \
    "kubectl get secret repo-resilience-gate --namespace argocd -o jsonpath='{.metadata.labels.argocd\\.argoproj\\.io/secret-type}' | grep -qx repository" \
    120
fi

log_info "Applying root GitOps application"
k8s_apply "$root_app_file"
if ! is_dry_run; then
  wait_for "root-app registered by Argo CD" \
    "kubectl get application root-app --namespace argocd >/dev/null" \
    120
fi

# C060 appends observability resources to bootstrap/kustomization.yaml. Wait
# for their child Application only when that reviewed phase is present; C055
# stays useful on its own and never attempts future promotion resources.
if grep -qx -- '  - observability.yaml' "$REPO_ROOT/kubernetes/bootstrap/kustomization.yaml" 2>/dev/null; then
  if is_dry_run; then
    log_info "Dry run: would verify observability Application and Grafana ExternalSecret"
  else
    wait_for "observability Application registered by root-app" \
      "kubectl get application observability --namespace argocd >/dev/null" \
      180
    wait_for "Grafana credentials synced" \
      "kubectl get secret grafana-admin-secret --namespace monitoring >/dev/null" \
      180
  fi
fi

log_ok "Phase 05 complete"
