#!/usr/bin/env bash
# Phase 03 — create a saved, reviewable Terraform plan and stop unless an
# operator explicitly approves it. Terraform always receives target values as
# explicit inputs; kubectl is switched and checked only after a successful apply.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_config

log_step "Phase 03 — Terraform"
require_env PROJECT_ID REGION ZONE CLUSTER_NAME TF_STATE_BUCKET GITHUB_REPO GAR_REPO

TF_DIR="$REPO_ROOT/gke_terraform"
TF_PLAN_FILE="$TF_DIR/.resilience-gate.tfplan"
if [ ! -d "$TF_DIR" ]; then
  log_err "Terraform directory not found: $TF_DIR"
  exit 1
fi

case "$TF_PLAN_FILE" in
  "$TF_DIR"/*) ;;
  *) log_err "Refusing an unsafe Terraform plan path"; exit 1 ;;
esac

cd "$TF_DIR"

# -reconfigure changes a stale backend without deleting .terraform by hand.
# The plan file stays inside gke_terraform and is ignored by Git.
run terraform init \
  -input=false \
  -reconfigure \
  "-backend-config=bucket=$TF_STATE_BUCKET" \
  -backend-config=prefix=resilience-gate/terraform

run terraform plan \
  -input=false \
  -lock-timeout=5m \
  "-var=project_id=$PROJECT_ID" \
  "-var=region=$REGION" \
  "-var=zone=$ZONE" \
  "-var=cluster_name=$CLUSTER_NAME" \
  "-var=registry_repository_id=$GAR_REPO" \
  "-var=github_repository=$GITHUB_REPO" \
  "-out=$TF_PLAN_FILE"

if is_dry_run; then
  log_ok "Phase 03 dry run complete; Terraform was not executed"
  exit 0
fi

if [ "${PLAN_ONLY:-false}" = true ]; then
  log_ok "PLAN_ONLY=true: saved plan was not applied"
  exit 0
fi

auto_approve="${TF_AUTO_APPROVE:-false}"
if [ "$auto_approve" != true ] && [ "$auto_approve" != false ]; then
  log_err "TF_AUTO_APPROVE must be true or false"
  exit 1
fi

if [ "$auto_approve" = true ]; then
  log_warn "TF_AUTO_APPROVE=true: applying the reviewed saved plan"
  confirmed=true
elif [ ! -t 0 ]; then
  # A CI pipe must never turn into consent. It leaves a reviewable plan and
  # succeeds so an operator can resume later with an interactive terminal.
  log_warn "No interactive terminal; leaving saved plan unapplied"
  exit 0
else
  printf '%s[CONFIRM]%s Apply this exact saved Terraform plan? [y/N] ' "$C_YELLOW" "$C_RESET" >&2
  IFS= read -r answer
  case "$answer" in
    y|Y|yes|YES) confirmed=true ;;
    *) confirmed=false ;;
  esac
fi

if [ "$confirmed" != true ]; then
  log_info "Terraform apply declined; saved plan remains unapplied"
  exit 0
fi

terraform apply -input=false "$TF_PLAN_FILE"

# get-credentials is scoped explicitly, then the exact generated context is
# asserted before any subsequent Helm or kubectl phase can proceed.
gcloud container clusters get-credentials "$CLUSTER_NAME" \
  "--zone=$ZONE" \
  "--project=$PROJECT_ID"
require_target_context

cd "$REPO_ROOT"
log_ok "Phase 03 complete"
