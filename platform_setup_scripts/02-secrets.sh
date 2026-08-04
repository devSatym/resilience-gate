#!/usr/bin/env bash
# Phase 02 — create or deliberately rotate named Secret Manager values. Values
# are read from a terminal or streamed source-to-destination; no value, temp
# file, or command-line argument is persisted by this script.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_config

log_step "Phase 02 — Secret Manager"
require_env PROJECT_ID

if ! declare -p SECRETS >/dev/null 2>&1 || [ "${#SECRETS[@]}" -eq 0 ]; then
  log_err "SECRETS must be a non-empty Bash array in config.env"
  exit 1
fi

declare -A seen_names=()
for secret_name in "${SECRETS[@]}"; do
  if ! [[ "$secret_name" =~ ^[A-Za-z][A-Za-z0-9_-]{0,254}$ ]]; then
    log_err "Invalid Secret Manager name in SECRETS: $secret_name"
    exit 1
  fi
  if [ -n "${seen_names[$secret_name]:-}" ]; then
    log_err "Duplicate secret name in SECRETS: $secret_name"
    exit 1
  fi
  seen_names[$secret_name]=1
done

rotation_requested="${ROTATE_SECRETS:-false}"
if [ "$rotation_requested" != true ] && [ "$rotation_requested" != false ]; then
  log_err "ROTATE_SECRETS must be true or false"
  exit 1
fi

if is_dry_run; then
  log_info "Dry run: no secret values will be requested, read, or written"
  for secret_name in "${SECRETS[@]}"; do
    log_info "Would ensure Secret Manager secret exists: $secret_name"
  done
  exit 0
fi

sha256_stream() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  else
    shasum -a 256 | awk '{print $1}'
  fi
}

create_or_rotate_from_stdin() {
  local name="$1"
  if secret_exists "$name" "$PROJECT_ID"; then
    if [ "$rotation_requested" != true ]; then
      log_info "Secret '$name' already exists; preserving it (set ROTATE_SECRETS=true to add a version)"
      cat >/dev/null
      return 0
    fi
    gcloud secrets versions add "$name" --project="$PROJECT_ID" --data-file=- >/dev/null
  else
    gcloud secrets create "$name" --project="$PROJECT_ID" --replication-policy=automatic --data-file=- >/dev/null
  fi
}

if [ -n "${SOURCE_PROJECT:-}" ]; then
  log_info "Migration mode: streaming named secrets from source project to target project"
  source_account_args=()
  if [ -n "${SOURCE_ACCOUNT:-}" ]; then
    source_account_args+=("--account=$SOURCE_ACCOUNT")
  fi

  for secret_name in "${SECRETS[@]}"; do
    if ! secret_exists "$secret_name" "$SOURCE_PROJECT" "${SOURCE_ACCOUNT:-}"; then
      log_err "Source secret is missing: $secret_name"
      exit 1
    fi

    if secret_exists "$secret_name" "$PROJECT_ID" && [ "$rotation_requested" != true ]; then
      log_info "Target secret '$secret_name' exists; preserving it (set ROTATE_SECRETS=true to copy a new version)"
      continue
    fi

    log_info "Copying '$secret_name' through a pipe (value is never written to disk)"
    gcloud secrets versions access latest \
      --secret="$secret_name" \
      "--project=$SOURCE_PROJECT" \
      "${source_account_args[@]}" \
      | create_or_rotate_from_stdin "$secret_name"

    source_hash=$(gcloud secrets versions access latest \
      --secret="$secret_name" \
      "--project=$SOURCE_PROJECT" \
      "${source_account_args[@]}" \
      | sha256_stream)
    target_hash=$(gcloud secrets versions access latest \
      --secret="$secret_name" \
      "--project=$PROJECT_ID" \
      | sha256_stream)
    if [ "$source_hash" != "$target_hash" ]; then
      log_err "Integrity verification failed for '$secret_name'"
      exit 1
    fi
    log_ok "Copied and integrity-verified '$secret_name'"
  done
else
  if [ ! -t 0 ]; then
    log_err "Fresh secret creation requires an interactive terminal; use SOURCE_PROJECT for noninteractive migration"
    exit 1
  fi

  log_info "Fresh setup mode: values are prompted silently and never echoed"
  for secret_name in "${SECRETS[@]}"; do
    if secret_exists "$secret_name" "$PROJECT_ID" && [ "$rotation_requested" != true ]; then
      log_info "Secret '$secret_name' already exists; preserving it"
      continue
    fi

    printf "Enter value for secret '%s': " "$secret_name" >&2
    IFS= read -r -s secret_value
    printf '\n' >&2
    if [ -z "$secret_value" ]; then
      log_err "Refusing to create an empty secret: $secret_name"
      exit 1
    fi
    printf '%s' "$secret_value" | create_or_rotate_from_stdin "$secret_name"
    unset secret_value
    log_ok "Stored '$secret_name'"
  done
fi

log_ok "Phase 02 complete"
