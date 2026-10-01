#!/usr/bin/env bash
# Phase 06 — register reviewed GitOps, Kargo, and complete chaos-gate
# configuration. Registration never creates a Promotion, paid load Job, or
# Chaos Mesh Workflow: only a later manually requested staging promotion can
# cause Kargo's AnalysisRun to start the bounded gate.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_config

log_step "Phase 06 — ordered GitOps and Kargo configuration"
require_env PROJECT_ID

if is_dry_run; then
  log_info "Dry run: target Kubernetes context is not queried"
else
  require_target_context
fi

# The renderer keeps every public repository/registry identifier reviewable.
# It fails closed if a manifest still has placeholders or a local config has
# changed without its generated diff being reviewed.
"$SCRIPTS_DIR/render_config.py" --config "$CONFIG_FILE" --check

declare -A manifests=(
  [project]="$REPO_ROOT/kubernetes/kargo/project.yaml"
  [credentials]="$REPO_ROOT/kubernetes/kargo/credentials-git.yaml"
  [project_config]="$REPO_ROOT/kubernetes/kargo/projectconfig.yaml"
  [analysis]="$REPO_ROOT/kubernetes/kargo/analysistemplate.yaml"
  [chaos_gate]="$REPO_ROOT/kubernetes/bootstrap/chaos-gate.yaml"
  [workload_namespaces]="$REPO_ROOT/kubernetes/bootstrap/workload-namespaces.yaml"
  [app_project]="$REPO_ROOT/kubernetes/apps/appproject.yaml"
  [app_set]="$REPO_ROOT/kubernetes/apps/applicationset.yaml"
  [dev]="$REPO_ROOT/kubernetes/kargo/stage-dev.yaml"
  [staging]="$REPO_ROOT/kubernetes/kargo/stage-staging.yaml"
  [prod]="$REPO_ROOT/kubernetes/kargo/stage-prod.yaml"
  [warehouse]="$REPO_ROOT/kubernetes/kargo/warehouse.yaml"
)

for name in "${!manifests[@]}"; do
  if [ ! -f "${manifests[$name]}" ]; then
    log_err "Required GitOps manifest is missing: ${manifests[$name]}"
    exit 1
  fi
done

# A Kargo Project owns its own namespace, so it must be registered before the
# namespaced ProjectConfig, credential, Warehouse, and Stages.
log_info "Applying Kargo Project"
k8s_apply "${manifests[project]}"
if ! is_dry_run; then
  wait_for "Kargo Project namespace" \
    "kubectl get namespace resilience-gate >/dev/null" \
    120
fi

log_info "Applying Kargo Git credential ExternalSecret"
k8s_apply "${manifests[credentials]}"
if ! is_dry_run; then
  wait_for "Kargo Git credential" \
    "kubectl get secret kargo-git-credentials --namespace resilience-gate >/dev/null" \
    120
fi

log_info "Applying Kargo policy, health analyses, and stage contracts"
k8s_apply "${manifests[project_config]}"
k8s_apply "${manifests[analysis]}"
k8s_apply "${manifests[dev]}"
k8s_apply "${manifests[staging]}"
k8s_apply "${manifests[prod]}"

# The ApplicationSet is deliberately not allowed to create namespaces. Ensure
# its dev and prod destinations exist before it registers Applications. The
# staging namespace is already bootstrap-owned by chaos-mesh-ns-annotation.
log_info "Applying bootstrap-owned workload namespaces"
k8s_apply "${manifests[workload_namespaces]}"

# ApplicationSet must exist before a future Kargo argocd-update step can find
# the generated Applications. Registration—not health—is all this phase
# verifies because env/* rendered branches are created by later Freight.
log_info "Applying scoped Argo CD project and ApplicationSet"
k8s_apply "${manifests[app_project]}"
k8s_apply "${manifests[app_set]}"
if ! is_dry_run; then
  wait_for "rendered dev Application registration" \
    "kubectl get application resilience-gate-dev --namespace argocd >/dev/null" \
    120
fi

# Register the immutable gate Application before the Warehouse can discover
# Freight. This only reconciles its RBAC/ExternalSecret configuration; it does
# not create an AnalysisRun, a fault, or a paid load Job.
log_info "Applying immutable chaos-gate configuration"
k8s_apply "${manifests[chaos_gate]}"
if ! is_dry_run; then
  wait_for "chaos-gate Application registration" \
    "kubectl get application chaos-gate --namespace argocd >/dev/null" \
    120
fi

# Warehouse polling comes last. It is the only resource in this phase that can
# discover Freight; the manually promoted staging Stage now references the
# complete gate, so Freight cannot become verified without its Job verdict.
log_info "Applying Kargo Warehouse after destinations are registered"
k8s_apply "${manifests[warehouse]}"

log_ok "Phase 06 complete: configuration registered; no promotion or chaos run was started"
