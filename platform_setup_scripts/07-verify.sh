#!/usr/bin/env bash
# Post-bootstrap, read-only verification for the owned Resilience Gate testnet
# lab. This is intentionally not a bootstrap phase: it never applies, deletes,
# patches, promotes, starts load, or starts a chaos workflow.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_file="${CONFIG_FILE:-$SCRIPT_DIR/config.env}"
scope="all"

usage() {
  cat <<'EOF'
Usage: 07-verify.sh [--config PATH] [--scope platform|gitops|gate|all]

Run read-only checks against the exact Kubernetes context described by PATH.
This command is separate from bootstrap.sh and does not start a promotion,
paid load run, or chaos experiment.

Scopes:
  platform  controller namespaces and available controller Deployments
  gitops    GitOps, External Secrets, and Kargo registration contracts
  gate      bounded chaos-gate RBAC and its staging prerequisites
  all       run every read-only check (default)
EOF
}

require_value() {
  local option="$1"
  if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
    printf '[ERR ] %s requires a value\n' "$option" >&2
    exit 2
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --config)
      require_value "$@"
      config_file="$2"
      shift 2
      ;;
    --scope)
      require_value "$@"
      scope="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '[ERR ] Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$scope" in
  platform|gitops|gate|all) ;;
  *)
    printf '[ERR ] --scope must be platform, gitops, gate, or all\n' >&2
    exit 2
    ;;
esac

# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_config "$config_file"
require_env PROJECT_ID ZONE CLUSTER_NAME
require_command kubectl

log_step "Read-only Resilience Gate verification ($scope)"
require_target_context

failures=0

check() {
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    log_ok "$description"
  else
    log_err "$description"
    failures=$((failures + 1))
  fi
}

optional_check() {
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    log_ok "$description"
  else
    # Grafana annotations are deliberately non-fatal to the gate verdict, and
    # an unavailable optional integration must not be misreported as a failed
    # release verification.
    log_warn "$description (optional check unavailable)"
  fi
}

namespace_exists() {
  kubectl get namespace "$1"
}

cluster_resource_exists() {
  kubectl get "$1" "$2"
}

namespaced_resource_exists() {
  local namespace="$1" resource="$2" name="$3"
  kubectl --namespace "$namespace" get "$resource" "$name"
}

deployment_available() {
  local namespace="$1" name="$2" status
  status=$(kubectl --namespace "$namespace" get deployment "$name" \
    -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || true)
  printf '%s' "$status" | grep -Eq '(^|[[:space:]])True($|[[:space:]])'
}

application_synced_and_healthy() {
  local name="$1" sync health
  sync=$(kubectl --namespace argocd get application "$name" \
    -o jsonpath='{.status.sync.status}' 2>/dev/null || true)
  health=$(kubectl --namespace argocd get application "$name" \
    -o jsonpath='{.status.health.status}' 2>/dev/null || true)
  [ "$sync" = "Synced" ] && [ "$health" = "Healthy" ]
}

resource_ready() {
  local namespace="$1" resource="$2" name="$3" status
  status=$(kubectl --namespace "$namespace" get "$resource" "$name" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
  printf '%s' "$status" | grep -Eq '(^|[[:space:]])True($|[[:space:]])'
}

cluster_resource_ready() {
  local resource="$1" name="$2" status
  status=$(kubectl get "$resource" "$name" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
  printf '%s' "$status" | grep -Eq '(^|[[:space:]])True($|[[:space:]])'
}

verify_platform() {
  log_info "Checking controller registration and availability"
  check "Namespace/cert-manager exists" namespace_exists cert-manager
  check "Deployment/cert-manager is Available" deployment_available cert-manager cert-manager
  check "Namespace/argocd exists" namespace_exists argocd
  check "Deployment/argocd-server is Available" deployment_available argocd argocd-server
  check "Namespace/argo-rollouts exists" namespace_exists argo-rollouts
  check "Deployment/argo-rollouts is Available" deployment_available argo-rollouts argo-rollouts
  check "Namespace/external-secrets exists" namespace_exists external-secrets
  check "Deployment/external-secrets is Available" deployment_available external-secrets external-secrets
  check "Namespace/kargo exists" namespace_exists kargo
  check "Deployment/kargo-controller is Available" deployment_available kargo kargo-controller
}

verify_gitops() {
  log_info "Checking GitOps, External Secrets, and Kargo contracts"
  check "ClusterSecretStore/resilience-gate-secrets is Ready" \
    cluster_resource_ready clustersecretstore resilience-gate-secrets
  check "ExternalSecret/argocd-repository is Ready" \
    resource_ready argocd externalsecret argocd-repository
  check "Application/root-app exists" namespaced_resource_exists argocd application root-app
  check "Application/root-app is Synced and Healthy" application_synced_and_healthy root-app
  check "Application/observability exists" namespaced_resource_exists argocd application observability
  check "Application/observability is Synced and Healthy" application_synced_and_healthy observability
  check "Application/chaos-mesh exists" namespaced_resource_exists argocd application chaos-mesh
  check "Application/chaos-mesh is Synced and Healthy" application_synced_and_healthy chaos-mesh
  check "Application/chaos-jobs exists" namespaced_resource_exists argocd application chaos-jobs
  check "Application/chaos-jobs is Synced and Healthy" application_synced_and_healthy chaos-jobs
  check "Application/chaos-gate exists" namespaced_resource_exists argocd application chaos-gate
  check "Application/chaos-gate is Synced and Healthy" application_synced_and_healthy chaos-gate
  check "ApplicationSet/resilience-gate exists" namespaced_resource_exists argocd applicationset resilience-gate
  check "Namespace/url-shortener-dev exists" namespace_exists url-shortener-dev
  check "Namespace/url-shortener-staging exists" namespace_exists url-shortener-staging
  check "Namespace/url-shortener-prod exists" namespace_exists url-shortener-prod
  check "Kargo Project/resilience-gate exists" cluster_resource_exists project resilience-gate
  check "Kargo Warehouse/resilience-gate exists" \
    namespaced_resource_exists resilience-gate warehouse resilience-gate
  check "Kargo Stage/dev exists" namespaced_resource_exists resilience-gate stage dev
  check "Kargo Stage/staging exists" namespaced_resource_exists resilience-gate stage staging
  check "Kargo Stage/prod exists" namespaced_resource_exists resilience-gate stage prod
  check "AnalysisTemplate/service-health exists" \
    namespaced_resource_exists resilience-gate analysistemplate service-health
  check "AnalysisTemplate/chaos-gate exists" \
    namespaced_resource_exists resilience-gate analysistemplate chaos-gate
  check "AnalysisTemplate/prod-post-deploy-health exists" \
    namespaced_resource_exists resilience-gate analysistemplate prod-post-deploy-health
}

verify_gate() {
  log_info "Checking bounded chaos-gate prerequisites"
  check "Namespace/resilience-gate exists" namespace_exists resilience-gate
  check "ServiceAccount/chaos-gate exists" \
    namespaced_resource_exists resilience-gate serviceaccount chaos-gate
  check "Role/chaos-gate-lock exists" namespaced_resource_exists resilience-gate role chaos-gate-lock
  check "RoleBinding/chaos-gate-lock exists" \
    namespaced_resource_exists resilience-gate rolebinding chaos-gate-lock
  check "Role/chaos-gate-runner exists" \
    namespaced_resource_exists url-shortener-staging role chaos-gate-runner
  check "RoleBinding/chaos-gate-runner exists" \
    namespaced_resource_exists url-shortener-staging rolebinding chaos-gate-runner
  check "CronJob/loadgen exists and remains registered" \
    namespaced_resource_exists url-shortener-staging cronjob loadgen
  check "Deployment/radius-signer is Available" \
    deployment_available url-shortener-staging radius-signer
  optional_check "ExternalSecret/grafana-annotation is Ready" \
    resource_ready resilience-gate externalsecret grafana-annotation
}

case "$scope" in
  platform)
    verify_platform
    ;;
  gitops)
    verify_gitops
    ;;
  gate)
    verify_gate
    ;;
  all)
    verify_platform
    verify_gitops
    verify_gate
    ;;
esac

if [ "$failures" -gt 0 ]; then
  log_err "Read-only verification found $failures required check(s) that need attention"
  exit 1
fi

log_ok "Read-only verification checks passed; no promotion, load run, chaos workflow, or release verdict was created"
