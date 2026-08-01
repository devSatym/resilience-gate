#!/usr/bin/env bash
# Shared library for platform_setup_scripts. Every phase loads local config
# independently so a Bash array such as SECRETS is never lost between process
# boundaries. All cloud and Kubernetes calls must use the helpers here.

set -euo pipefail

# Colors only when stderr is a TTY
if [ -t 2 ]; then
  C_RESET=$'\033[0m' C_GREEN=$'\033[32m' C_YELLOW=$'\033[33m' C_RED=$'\033[31m' C_BLUE=$'\033[34m' C_DIM=$'\033[2m'
else
  C_RESET= C_GREEN= C_YELLOW= C_RED= C_BLUE= C_DIM=
fi

DRY_RUN="${DRY_RUN:-false}"

log_info()  { printf '%s[INFO]%s  %s\n' "$C_BLUE"   "$C_RESET" "$*" >&2; }
log_ok()    { printf '%s[ OK ]%s  %s\n' "$C_GREEN"  "$C_RESET" "$*" >&2; }
log_warn()  { printf '%s[WARN]%s  %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
log_err()   { printf '%s[ERR ]%s  %s\n' "$C_RED"    "$C_RESET" "$*" >&2; }
log_step()  { printf '\n%s──▶ %s%s\n'   "$C_BLUE"   "$*"        "$C_RESET" >&2; }

is_dry_run() { [ "${DRY_RUN:-false}" = "true" ]; }

run() {
  if is_dry_run; then
    printf '%s$' "$C_DIM" >&2
    printf ' %q' "$@" >&2
    printf '%s\n' "$C_RESET" >&2
    return 0
  fi
  "$@"
}

require_env() {
  for v in "$@"; do
    if [ -z "${!v:-}" ]; then
      log_err "Required env var \$$v is not set"
      exit 1
    fi
  done
}

require_command() {
  local command
  for command in "$@"; do
    if ! command -v "$command" >/dev/null 2>&1; then
      log_err "Required command is not installed: $command"
      return 1
    fi
  done
}

load_config() {
  local config_file="${1:-${CONFIG_FILE:-$SCRIPTS_DIR/config.env}}"
  if [ ! -f "$config_file" ]; then
    log_err "Configuration file not found: $config_file"
    log_err "Copy platform_setup_scripts/config.env.example to config.env first."
    return 1
  fi

  # This is an operator-controlled Bash configuration file. It is intentionally
  # ignored and is sourced only on the local machine running bootstrap.
  # shellcheck disable=SC1090
  source "$config_file"

  : "${PROJECT_ID:=}"
  : "${GITHUB_REPO:=}"
  : "${REGION:=us-central1}"
  : "${ZONE:=${REGION}-a}"
  : "${CLUSTER_NAME:=resilience-gate}"
  : "${GAR_REPO:=resilience-gate}"
  : "${TF_STATE_BUCKET:=${PROJECT_ID:+${PROJECT_ID}-tf-state}}"

  CONFIG_FILE="$config_file"
  export CONFIG_FILE PROJECT_ID GITHUB_REPO PROJECT_NUMBER REGION ZONE CLUSTER_NAME GAR_REPO TF_STATE_BUCKET
}

gcloud_active() {
  local account project
  account=$(gcloud config get-value account 2>/dev/null)
  project=$(gcloud config get-value project 2>/dev/null)
  log_info "gcloud account: ${account:-<unset>}"
  log_info "gcloud project: ${project:-<unset>}"
  if [ "$project" != "$PROJECT_ID" ]; then
    log_warn "gcloud project ($project) != PROJECT_ID ($PROJECT_ID). Will pass --project=$PROJECT_ID explicitly."
  fi
}

expected_kube_context() {
  require_env PROJECT_ID ZONE CLUSTER_NAME
  printf 'gke_%s_%s_%s' "$PROJECT_ID" "$ZONE" "$CLUSTER_NAME"
}

require_target_context() {
  local expected actual
  expected=$(expected_kube_context)
  actual=$(kubectl config current-context 2>/dev/null || true)
  if [ "$actual" != "$expected" ]; then
    log_err "Refusing to operate on Kubernetes context '${actual:-<unset>}'"
    log_err "Expected target context: $expected"
    return 1
  fi
  log_ok "Target Kubernetes context verified: $actual"
}

secret_exists() {
  # secret_exists <secret-name> <project-id> [account-flag]
  local name="$1" project="$2" account="${3:-}"
  local args=(gcloud secrets describe "$name" "--project=$project")
  if [ -n "$account" ]; then
    args+=("--account=$account")
  fi
  "${args[@]}" >/dev/null 2>&1
}

k8s_apply() {
  # Apply a manifest. Respects DRY_RUN.
  if [ "$DRY_RUN" = "true" ]; then
    printf '%s$ kubectl apply -f %s%s\n' "$C_DIM" "$*" "$C_RESET" >&2
  else
    kubectl apply -f "$@"
  fi
}

wait_for() {
  # wait_for "<description>" "<command that exits 0 when ready>" [timeout-seconds]
  local desc="$1" check="$2" timeout="${3:-180}"
  local elapsed=0
  log_info "Waiting for: $desc (timeout ${timeout}s)"
  while ! eval "$check" >/dev/null 2>&1; do
    if [ "$elapsed" -ge "$timeout" ]; then
      log_err "Timed out after ${timeout}s waiting for: $desc"
      return 1
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  log_ok "Ready: $desc (took ${elapsed}s)"
}

# Detect repo root (assumes lib.sh lives in <repo>/platform_setup_scripts/)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/platform_setup_scripts"
