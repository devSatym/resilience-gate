#!/usr/bin/env bash
# Safe orchestrator for the reviewed bootstrap phases. It stops at phase 06:
# registration of GitOps/Kargo configuration never triggers a promotion, paid
# load run, or chaos experiment on its own.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: bootstrap.sh [--phase N | --from N --to N] [--source-project ID]
                    [--source-account EMAIL] [--config PATH] [--dry-run]
                    [--render-config]

Completed phases:
  00  preflight              tools, credentials, target-project access
  01  APIs and state         required APIs and versioned state bucket
  02  secrets                Secret Manager values (interactive or streamed)
  03  Terraform              saved plan, explicit approval, target context
  04  controllers            pinned cert-manager, Argo, ESO, and Kargo
  05  root GitOps            secret store, repository credential, root app
  06  GitOps/Kargo config    ordered rendered-branch configuration only

`--render-config` writes public manifests and exits. Review and commit that
diff before running any mutating phase. Promotion, paid load generation, and
chaos verification remain explicitly deferred to their later contracts. After
phase 06, run 07-verify.sh separately for read-only status; it is not a
bootstrap phase.
EOF
}

phase_index() {
  case "$1" in
    0|00) printf '0' ;;
    1|01) printf '1' ;;
    2|02) printf '2' ;;
    3|03) printf '3' ;;
    4|04) printf '4' ;;
    5|05) printf '5' ;;
    6|06) printf '6' ;;
    *) return 1 ;;
  esac
}

phase_label() { printf '%02d' "$1"; }

phase_single=""
phase_from=""
phase_to=""
render_only=false
export SOURCE_PROJECT="${SOURCE_PROJECT:-}"
export SOURCE_ACCOUNT="${SOURCE_ACCOUNT:-}"
export DRY_RUN="${DRY_RUN:-false}"
CONFIG_FILE="${CONFIG_FILE:-$SCRIPT_DIR/config.env}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --phase|--from|--to|--source-project|--source-account|--config)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        printf '[ERR ] %s requires a value\n' "$1" >&2
        exit 2
      fi
      case "$1" in
        --phase) phase_single="$2" ;;
        --from) phase_from="$2" ;;
        --to) phase_to="$2" ;;
        --source-project) SOURCE_PROJECT="$2" ;;
        --source-account) SOURCE_ACCOUNT="$2" ;;
        --config) CONFIG_FILE="$2" ;;
      esac
      shift 2
      ;;
    --dry-run) DRY_RUN=true; shift ;;
    --render-config) render_only=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf '[ERR ] Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -n "$phase_single" ] && { [ -n "$phase_from" ] || [ -n "$phase_to" ]; }; then
  printf '[ERR ] --phase cannot be combined with --from or --to\n' >&2
  exit 2
fi

if [ -n "$phase_single" ]; then
  if ! start=$(phase_index "$phase_single"); then
    printf '[ERR ] phase must be between 00 and 06\n' >&2
    exit 2
  fi
  end="$start"
else
  start=0
  end=6
  if [ -n "$phase_from" ] && ! start=$(phase_index "$phase_from"); then
    printf '[ERR ] --from must be between 00 and 06\n' >&2
    exit 2
  fi
  if [ -n "$phase_to" ] && ! end=$(phase_index "$phase_to"); then
    printf '[ERR ] --to must be between 00 and 06\n' >&2
    exit 2
  fi
fi
if [ "$start" -gt "$end" ]; then
  printf '[ERR ] --from cannot be later than --to\n' >&2
  exit 2
fi

export CONFIG_FILE
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_config "$CONFIG_FILE"

if [ "$render_only" = true ]; then
  exec "$SCRIPT_DIR/render_config.py" --config "$CONFIG_FILE" --write
fi

# An ignored config.env alone is never sufficient for a cloud mutation. The
# matching public manifests must be rendered, reviewed, and present in Git.
"$SCRIPT_DIR/render_config.py" --config "$CONFIG_FILE" --check

phase_files=(
  "$SCRIPT_DIR/00-preflight.sh"
  "$SCRIPT_DIR/01-apis-and-bucket.sh"
  "$SCRIPT_DIR/02-secrets.sh"
  "$SCRIPT_DIR/03-terraform.sh"
  "$SCRIPT_DIR/04-platform.sh"
  "$SCRIPT_DIR/05-cluster-resources.sh"
  "$SCRIPT_DIR/06-gitops-and-kargo.sh"
)

log_step "Resilience Gate platform bootstrap"
log_info "Target project: $PROJECT_ID"
log_info "Target cluster: $CLUSTER_NAME ($ZONE)"
log_info "Selected phases: $(phase_label "$start") through $(phase_label "$end")"
if is_dry_run; then
  log_warn "Dry run enabled: mutating commands will only be printed"
fi

for ((index=start; index<=end; index++)); do
  "${phase_files[$index]}"
done

log_ok "Requested bootstrap phases completed"
