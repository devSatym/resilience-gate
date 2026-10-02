#!/usr/bin/env bash
# Request an intended Kargo verification path for the owned testnet lab.
#
# Planning is the default and has no Kubernetes, Kargo, cloud, or testnet side
# effect. Execution never creates a Workflow, Job, or patched workload itself:
# it asks Kargo to run the Stage's reviewed verification contract. A zero exit
# status means only that Kargo accepted the request; collect and review the
# resulting AnalysisRun, Job, scorecards, and final status before claiming a
# pass.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly LIVE_REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly PLATFORM_DIR="$LIVE_REPO_ROOT/platform_setup_scripts"
readonly KARGO_PROJECT="resilience-gate"

mode="plan"
scenario=""
promotion_freight=""
config_file="${CONFIG_FILE:-$PLATFORM_DIR/config.env}"
acknowledged_lab=false
acknowledged_staging_promotion=false
acknowledged_prod_promotion=false

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/validate-live.sh --plan --scenario SCENARIO [--promotion-freight NAME]
  ./scripts/validate-live.sh --execute --acknowledge-owned-testnet-lab \
    --scenario SCENARIO --config PATH [--promotion-freight NAME \
    [--acknowledge-staging-promotion|--acknowledge-prod-promotion]]

Scenarios:
  baseline            Reverify development's normal service-health contract.
  chaos-gate          Reverify staging's immutable chaos-gate contract.
  regression-blocked  Promote a named, pipeline-produced candidate to staging;
                      it must be explicitly acknowledged and is never patched
                      directly by this script.
  recovery            Reverify staging through the same complete gate after a
                      separately recorded failed or blocked run.
  prod-smoke          Reverify the production-like testnet health contract.

Options:
  --plan                        Print the intended Kargo action (default).
  --execute                     Request the action after all safety checks.
  --scenario NAME               One scenario from the list above (required).
  --promotion-freight NAME      Kargo Freight name for a named promotion.
  --acknowledge-owned-testnet-lab
                                Required for every --execute request.
  --acknowledge-staging-promotion
                                Required for a named staging promotion.
  --acknowledge-prod-promotion
                                Required for a named production-like promotion.
  --config PATH                 Ignored local platform configuration for the
                                exact expected Kubernetes context.
  -h, --help                    Show this help.

This runner intentionally does not create a manual AnalysisRun, Chaos Mesh
Workflow, load Job, or deployment patch. A pipeline candidate must travel
through Kargo's Stage contract so the digest-pinned gate is the verifier.
USAGE
}

die() {
  printf 'live validation: %s\n' "$*" >&2
  exit 2
}

need_value() {
  [[ $# -ge 2 && -n "${2:-}" ]] || die "$1 requires a value"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan)
      mode="plan"
      shift
      ;;
    --execute)
      mode="execute"
      shift
      ;;
    --scenario)
      need_value "$@"
      scenario="$2"
      shift 2
      ;;
    --promotion-freight)
      need_value "$@"
      promotion_freight="$2"
      shift 2
      ;;
    --config)
      need_value "$@"
      config_file="$2"
      shift 2
      ;;
    --acknowledge-owned-testnet-lab)
      acknowledged_lab=true
      shift
      ;;
    --acknowledge-staging-promotion)
      acknowledged_staging_promotion=true
      shift
      ;;
    --acknowledge-prod-promotion)
      acknowledged_prod_promotion=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1 (use --help)"
      ;;
  esac
done

case "$scenario" in
  baseline|chaos-gate|regression-blocked|recovery|prod-smoke) ;;
  "") die "--scenario is required" ;;
  *) die "unsupported scenario: $scenario" ;;
esac

if [[ -n "$promotion_freight" ]]; then
  [[ "$promotion_freight" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] \
    && (( ${#promotion_freight} <= 63 )) \
    || die "--promotion-freight must be a lowercase DNS label of at most 63 characters"
  [[ "$scenario" == "chaos-gate" || "$scenario" == "regression-blocked" || "$scenario" == "recovery" || "$scenario" == "prod-smoke" ]] \
    || die "--promotion-freight is valid only for staging gate or prod-smoke scenarios"
fi

if [[ "$scenario" == "regression-blocked" && -z "$promotion_freight" ]]; then
  die "regression-blocked requires --promotion-freight; this runner will not patch a workload"
fi

stage_for_scenario() {
  case "$1" in
    baseline) printf 'dev' ;;
    chaos-gate|regression-blocked|recovery) printf 'staging' ;;
    prod-smoke) printf 'prod' ;;
  esac
}

namespace_for_scenario() {
  case "$1" in
    baseline) printf 'url-shortener-dev' ;;
    chaos-gate|regression-blocked|recovery) printf 'url-shortener-staging' ;;
    prod-smoke) printf 'url-shortener-prod' ;;
  esac
}

analysis_templates_for_scenario() {
  case "$1" in
    baseline) printf '%s\n' service-health ;;
    chaos-gate|regression-blocked|recovery) printf '%s\n' service-health chaos-gate ;;
    prod-smoke) printf '%s\n' prod-post-deploy-health ;;
  esac
}

stage="$(stage_for_scenario "$scenario")"
target_namespace="$(namespace_for_scenario "$scenario")"

print_command() {
  local -a command=("$@")
  printf '  '
  printf '%q ' "${command[@]}"
  printf '\n'
}

if [[ -n "$promotion_freight" ]]; then
  action=(kargo promote --project "$KARGO_PROJECT" --freight "$promotion_freight" --stage "$stage")
else
  # Keep the dry-run contract stable regardless of which local tools happen to
  # be installed. The annotation fallback below expresses this same reviewed
  # Kargo reverify request when a compatible CLI is unavailable.
  action=(kargo verify stage "$stage" --project "$KARGO_PROJECT")
fi

if [[ "$mode" == "plan" ]]; then
  printf 'Live validation plan (no cluster, Kargo, cloud, or testnet call has been made):\n'
  printf '  scenario: %s\n' "$scenario"
  printf '  Kargo project: %s\n' "$KARGO_PROJECT"
  printf '  Stage: %s\n' "$stage"
  printf '  target namespace: %s\n' "$target_namespace"
  if [[ -n "$promotion_freight" ]]; then
    printf '  Freight: %s (a real %s promotion would be requested)\n' "$promotion_freight" "$stage"
  else
    printf "%s\n" "  Action: reverify the Stage's current Freight"
  fi
  print_command "${action[@]}"
  if [[ -z "$promotion_freight" ]] && ! command -v kargo >/dev/null 2>&1; then
    printf '%s\n' "  Execute fallback without a compatible Kargo CLI: annotate the Stage with its latest verification ID"
  fi
  cat <<'NOTICE'

Review the actual Freight identities and the rendered application before using
--execute. A successful CLI request is not a passing verification verdict;
collect the exact AnalysisRun and scorecards with scripts/collect-evidence.sh.
NOTICE
  exit 0
fi

[[ "$acknowledged_lab" == true ]] \
  || die "--execute requires --acknowledge-owned-testnet-lab"
if [[ -n "$promotion_freight" ]]; then
  if [[ "$scenario" == "prod-smoke" ]]; then
    [[ "$acknowledged_prod_promotion" == true ]] \
      || die "a production-like promotion also requires --acknowledge-prod-promotion"
  else
    [[ "$acknowledged_staging_promotion" == true ]] \
      || die "a staging promotion also requires --acknowledge-staging-promotion"
  fi
fi
[[ -f "$config_file" ]] || die "configuration file not found: $config_file"

# shellcheck source=../platform_setup_scripts/lib.sh
source "$PLATFORM_DIR/lib.sh"
load_config "$config_file"
require_env PROJECT_ID ZONE CLUSTER_NAME
require_command kubectl
if [[ -n "$promotion_freight" ]]; then
  require_command kargo || die "a named promotion requires a compatible Kargo CLI"
fi
require_target_context

# Establish that both the target namespace and the reviewed Kargo contract are
# present before making the one explicit Kargo API request. These checks are
# read-only and no command output carrying credentials is printed by this tool.
kubectl get namespace "$target_namespace" >/dev/null \
  || die "target namespace $target_namespace is not present"
kubectl -n "$KARGO_PROJECT" get stage "$stage" >/dev/null \
  || die "Kargo Stage/$stage is not present in project $KARGO_PROJECT"
while IFS= read -r analysis_template; do
  kubectl -n "$KARGO_PROJECT" get analysistemplate "$analysis_template" >/dev/null \
    || die "AnalysisTemplate/$analysis_template is not present for $scenario"
done < <(analysis_templates_for_scenario "$scenario")
if [[ -n "$promotion_freight" ]]; then
  kubectl -n "$KARGO_PROJECT" get freight "$promotion_freight" >/dev/null \
    || die "Freight/$promotion_freight is not present in project $KARGO_PROJECT"
  if [[ "$scenario" == "prod-smoke" ]]; then
    verified_in_staging="$(kubectl -n "$KARGO_PROJECT" get freight "$promotion_freight" \
      -o jsonpath='{.status.verifiedIn.staging.verifiedAt}')"
    [[ -n "$verified_in_staging" ]] \
      || die "Freight/$promotion_freight has not been verified in Stage/staging"
  fi
fi

if [[ -z "$promotion_freight" ]] && ! command -v kargo >/dev/null 2>&1; then
  # Resolve the exact previous verification only after every read-only safety
  # check. Plan mode never queries a cluster merely to produce its preview.
  prior_verification_id="$(kubectl -n "$KARGO_PROJECT" get stage "$stage" \
    -o jsonpath='{.status.freightHistory[0].verificationHistory[0].id}')"
  [[ -n "$prior_verification_id" ]] \
    || die "Stage/$stage has no prior verification ID for a reverify request"
  action=(
    kubectl -n "$KARGO_PROJECT" annotate "stage.kargo.akuity.io/$stage"
    "kargo.akuity.io/reverify=$prior_verification_id" --overwrite
  )
fi

printf 'Requesting the reviewed Kargo verification path:\n'
print_command "${action[@]}"
if ! "${action[@]}"; then
  printf 'live validation: Kargo rejected or could not start the request; no pass claim was made.\n' >&2
  exit 1
fi

cat <<'NOTICE'
Kargo accepted the request. This is not a passing verification verdict. Wait
for the associated AnalysisRun and applicable gate artifacts to finish, then
collect sanitized evidence with scripts/collect-evidence.sh and review its
status and scorecards where the scenario uses the chaos gate.
NOTICE
