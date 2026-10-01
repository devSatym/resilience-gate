#!/usr/bin/env bash
# Phase 04 — install the prerequisite controllers in a strict, pinned order.
# Credentials are created once as an existing Kargo API secret so re-runs never
# silently rotate access or expose sensitive values through Helm --set flags.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_config
# shellcheck source=versions.env
source "$SCRIPT_DIR/versions.env"

log_step "Phase 04 — pinned platform controllers"
require_env PROJECT_ID CERT_MANAGER_CHART_VERSION ARGOCD_CHART_VERSION ARGO_ROLLOUTS_CHART_VERSION EXTERNAL_SECRETS_CHART_VERSION KARGO_CHART_REF KARGO_CHART_VERSION HELM_TIMEOUT

if is_dry_run; then
  log_info "Dry run: target Kubernetes context is not queried"
else
  require_target_context
fi

run helm repo add jetstack https://charts.jetstack.io --force-update
run helm repo add argo https://argoproj.github.io/argo-helm --force-update
run helm repo add external-secrets https://charts.external-secrets.io --force-update
run helm repo update

run helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --version "$CERT_MANAGER_CHART_VERSION" \
  --set crds.enabled=true \
  --wait --timeout "$HELM_TIMEOUT"

run helm upgrade --install argocd argo/argo-cd \
  --namespace argocd --create-namespace \
  --version "$ARGOCD_CHART_VERSION" \
  --values "$SCRIPT_DIR/argocd-values.yaml" \
  --wait --timeout "$HELM_TIMEOUT"

run helm upgrade --install argo-rollouts argo/argo-rollouts \
  --namespace argo-rollouts --create-namespace \
  --version "$ARGO_ROLLOUTS_CHART_VERSION" \
  --wait --timeout "$HELM_TIMEOUT"

eso_gcp_service_account="external-secrets-sa@${PROJECT_ID}.iam.gserviceaccount.com"
run helm upgrade --install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace \
  --version "$EXTERNAL_SECRETS_CHART_VERSION" \
  --set serviceAccount.create=true \
  --set serviceAccount.name=external-secrets \
  --set-string "serviceAccount.annotations.iam\\.gke\\.io/gcp-service-account=$eso_gcp_service_account" \
  --wait --timeout "$HELM_TIMEOUT"

if ! is_dry_run; then
  eso_annotation=$(kubectl get serviceaccount external-secrets --namespace external-secrets -o jsonpath='{.metadata.annotations.iam\.gke\.io/gcp-service-account}')
  if [ "$eso_annotation" != "$eso_gcp_service_account" ]; then
    log_err "External Secrets Workload Identity annotation did not match the Terraform identity"
    exit 1
  fi
  log_ok "External Secrets Workload Identity annotation verified"
fi

kargo_secret_name="kargo-api-credentials"

# The API credential is intentionally created before Helm renders Kargo. Make
# its namespace first so a brand-new cluster does not fail on the first run.
if is_dry_run; then
  run kubectl create namespace kargo --dry-run=client -o yaml
  log_info "Dry run: would apply the Kargo namespace manifest"
else
  kubectl create namespace kargo --dry-run=client -o yaml | kubectl apply -f - >/dev/null
fi

create_kargo_api_secret() {
  if kubectl get secret "$kargo_secret_name" --namespace kargo >/dev/null 2>&1; then
    log_ok "Reusing existing Kargo API credential secret"
    return 0
  fi

  if [ ! -t 0 ] && [ -z "${KARGO_ADMIN_PASSWORD:-}" ]; then
    log_err "KARGO_ADMIN_PASSWORD must be supplied or entered on an interactive terminal for first Kargo install"
    return 1
  fi

  local admin_password="${KARGO_ADMIN_PASSWORD:-}"
  if [ -z "$admin_password" ]; then
    printf 'Set Kargo admin password: ' >&2
    IFS= read -r -s admin_password
    printf '\n' >&2
  fi
  if [ -z "$admin_password" ]; then
    log_err "Kargo admin password cannot be empty"
    return 1
  fi

  # The selected bcrypt hasher reads the password from stdin, avoiding an
  # argument-list disclosure. htpasswd is preferred; lib.sh supplies a
  # Python crypt fallback for portable operator workstations.
  local password_hash token_key encoded_hash encoded_key
  password_hash=$(printf '%s\n' "$admin_password" | bcrypt_password_hash)
  token_key="${KARGO_TOKEN_SIGNING_KEY:-$(openssl rand -base64 48 | tr -d '=+/' | cut -c1-48)}"
  unset admin_password
  if [ "${#password_hash}" -lt 50 ] || [ "${#token_key}" -lt 32 ]; then
    log_err "Generated Kargo credentials did not meet minimum length requirements"
    unset password_hash token_key
    return 1
  fi
  encoded_hash=$(printf '%s' "$password_hash" | base64 | tr -d '\n')
  encoded_key=$(printf '%s' "$token_key" | base64 | tr -d '\n')

  # Feed the Secret manifest on stdin. Sensitive values never appear in a
  # command argument, rendered file, or Helm release values.
  {
    printf '%s\n' 'apiVersion: v1'
    printf '%s\n' 'kind: Secret'
    printf '%s\n' 'metadata:'
    printf '%s\n' "  name: $kargo_secret_name"
    printf '%s\n' '  namespace: kargo'
    printf '%s\n' 'type: Opaque'
    printf '%s\n' 'data:'
    printf '%s\n' "  ADMIN_ACCOUNT_PASSWORD_HASH: $encoded_hash"
    printf '%s\n' "  ADMIN_ACCOUNT_TOKEN_SIGNING_KEY: $encoded_key"
  } | kubectl apply --namespace kargo -f - >/dev/null
  unset password_hash token_key encoded_hash encoded_key
  log_ok "Created persistent Kargo API credential secret"
}

if is_dry_run; then
  log_info "Dry run: would reuse or create Kargo API credentials without printing values"
else
  create_kargo_api_secret
fi

run helm upgrade --install kargo "$KARGO_CHART_REF" \
  --namespace kargo --create-namespace \
  --version "$KARGO_CHART_VERSION" \
  --set "api.secret.name=$kargo_secret_name" \
  --wait --timeout "$HELM_TIMEOUT"

# Kargo 1.3 uses the controller KSA's direct GKE Workload Identity principal
# to impersonate the project-specific GSA provisioned by Terraform. A legacy
# KSA-to-GSA annotation changes that principal and breaks GAR discovery.
if is_dry_run; then
  run kubectl annotate serviceaccount kargo-controller --namespace kargo iam.gke.io/gcp-service-account- --overwrite
else
  kubectl annotate serviceaccount kargo-controller --namespace kargo iam.gke.io/gcp-service-account- --overwrite >/dev/null
  kargo_annotation=$(kubectl get serviceaccount kargo-controller --namespace kargo -o jsonpath='{.metadata.annotations.iam\.gke\.io/gcp-service-account}')
  if [ -n "$kargo_annotation" ]; then
    log_err "Kargo controller must use its direct Workload Identity principal"
    exit 1
  fi
fi

log_ok "Phase 04 complete"
