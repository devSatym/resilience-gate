#!/usr/bin/env bash
# Phase 01 — enable only the APIs this platform needs and create a dedicated,
# versioned Terraform state bucket. It refuses to reuse a bucket from another
# project, which prevents an accidental cross-project state takeover.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_config

log_step "Phase 01 — APIs and Terraform state"
require_env PROJECT_ID REGION TF_STATE_BUCKET

if ! [[ "$TF_STATE_BUCKET" =~ ^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$ ]]; then
  log_err "TF_STATE_BUCKET is not a valid GCS bucket name"
  exit 1
fi

apis=(
  serviceusage.googleapis.com
  compute.googleapis.com
  container.googleapis.com
  artifactregistry.googleapis.com
  secretmanager.googleapis.com
  iam.googleapis.com
  iamcredentials.googleapis.com
  sts.googleapis.com
  cloudresourcemanager.googleapis.com
  logging.googleapis.com
  monitoring.googleapis.com
)
bucket_uri="gs://${TF_STATE_BUCKET}"

if is_dry_run; then
  log_info "Dry run: no API, bucket, or policy mutation will occur"
  run gcloud services enable "${apis[@]}" "--project=$PROJECT_ID"
  run gcloud storage buckets describe "$bucket_uri" "--project=$PROJECT_ID"
  run gcloud storage buckets create "$bucket_uri" "--project=$PROJECT_ID" "--location=$REGION" --uniform-bucket-level-access
  run gcloud storage buckets update "$bucket_uri" "--project=$PROJECT_ID" --versioning --public-access-prevention
  exit 0
fi

target_project_number=$(gcloud projects describe "$PROJECT_ID" --project="$PROJECT_ID" --format='value(projectNumber)')
if [ -z "$target_project_number" ]; then
  log_err "Unable to determine project number for '$PROJECT_ID'"
  exit 1
fi
if [ -n "${PROJECT_NUMBER:-}" ] && [ "$PROJECT_NUMBER" != "$target_project_number" ]; then
  log_err "Configured PROJECT_NUMBER does not match '$PROJECT_ID'"
  exit 1
fi

log_info "Enabling required APIs in target project"
gcloud services enable "${apis[@]}" "--project=$PROJECT_ID"

if gcloud storage buckets describe "$bucket_uri" "--project=$PROJECT_ID" >/dev/null 2>&1; then
  owner_project_number=$(gcloud storage buckets describe "$bucket_uri" --format='value(projectNumber)')
  if [ "$owner_project_number" != "$target_project_number" ]; then
    log_err "State bucket '$bucket_uri' belongs to project number '$owner_project_number', not '$target_project_number'"
    exit 1
  fi
  log_ok "Terraform state bucket already exists in the target project"
else
  log_info "Creating dedicated Terraform state bucket '$bucket_uri'"
  gcloud storage buckets create "$bucket_uri" \
    "--project=$PROJECT_ID" \
    "--location=$REGION" \
    --uniform-bucket-level-access
fi

# Both settings are idempotent. Versioning gives Terraform recoverable history;
# public-access prevention makes accidental exposure impossible at bucket scope.
gcloud storage buckets update "$bucket_uri" \
  "--project=$PROJECT_ID" \
  --versioning \
  --public-access-prevention

log_ok "Phase 01 complete: target APIs enabled and state bucket protected"
