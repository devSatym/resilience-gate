#!/usr/bin/env bash
# Phase 00 — prove the operator can safely target this project before any
# mutating phase is allowed to run. A cluster-context assertion is optional for
# first bootstrap and mandatory when resuming at a Kubernetes phase.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_config

require_cluster_context=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --require-cluster-context) require_cluster_context=true; shift ;;
    -h|--help)
      printf '%s\n' "Usage: $0 [--require-cluster-context]"
      exit 0
      ;;
    *)
      log_err "Unknown preflight option: $1"
      exit 2
      ;;
  esac
done

log_step "Phase 00 — preflight"
require_env PROJECT_ID GITHUB_REPO REGION ZONE CLUSTER_NAME

# Tool installation instructions are deliberately generic; no package manager
# is assumed because bootstrap must work from Linux and macOS workstations.
required_tools=(gcloud kubectl helm terraform python3 openssl base64)
missing=0
for tool in "${required_tools[@]}"; do
  if command -v "$tool" >/dev/null 2>&1; then
    log_ok "$tool present"
  else
    log_err "$tool is required but not installed"
    missing=1
  fi
done
[ "$missing" -eq 0 ] || { log_err "Install the missing tools and retry."; exit 1; }

if bcrypt_password_hasher_available; then
  if command -v htpasswd >/dev/null 2>&1; then
    log_ok "htpasswd bcrypt hasher present"
  else
    log_ok "Python bcrypt-capable crypt fallback present"
  fi
else
  log_err "A bcrypt password hasher is required (install htpasswd or use Python with bcrypt-capable crypt)"
  exit 1
fi

if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then
  log_err "A SHA-256 utility (sha256sum or shasum) is required for secret migration verification"
  exit 1
fi

account=$(gcloud config get-value account 2>/dev/null || true)
if [ -z "$account" ] || [ "$account" = "(unset)" ]; then
  log_err "No active gcloud account. Run: gcloud auth login"
  exit 1
fi
log_ok "Active gcloud account detected"

if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  log_err "Application Default Credentials are unavailable. Run: gcloud auth application-default login"
  exit 1
fi
log_ok "Application Default Credentials configured"

if ! project_number=$(gcloud projects describe "$PROJECT_ID" --project="$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null); then
  log_err "Cannot access target project '$PROJECT_ID' with the active credentials"
  exit 1
fi
if [ -z "$project_number" ]; then
  log_err "Target project '$PROJECT_ID' did not return a project number"
  exit 1
fi
if [ -n "${PROJECT_NUMBER:-}" ] && [ "$PROJECT_NUMBER" != "$project_number" ]; then
  log_err "Configured PROJECT_NUMBER does not match target project '$PROJECT_ID'"
  exit 1
fi
PROJECT_NUMBER="$project_number"
export PROJECT_NUMBER
log_ok "Target project access verified"

if [ -n "${SOURCE_PROJECT:-}" ]; then
  source_args=("--project=$SOURCE_PROJECT")
  if [ -n "${SOURCE_ACCOUNT:-}" ]; then
    source_args+=("--account=$SOURCE_ACCOUNT")
  fi
  if ! gcloud projects describe "$SOURCE_PROJECT" "${source_args[@]}" >/dev/null 2>&1; then
    log_err "Cannot access migration source project '$SOURCE_PROJECT'"
    exit 1
  fi
  log_ok "Migration source project access verified"
fi

if [ "$require_cluster_context" = true ]; then
  require_target_context
else
  log_info "Cluster context check deferred until Terraform creates or selects the target cluster"
fi

log_ok "Phase 00 complete"
