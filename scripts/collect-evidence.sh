#!/usr/bin/env bash
# Collect a small, sanitized evidence bundle from the owned testnet lab.
#
# The default plan does not read local configuration, create directories, or
# call Kubernetes. Collection is explicit, target-context guarded, and writes
# outside the repository by default. Raw kubectl output is streamed through the
# sanitizer; it is never first saved as an unreviewed artifact.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly COLLECT_REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
readonly PLATFORM_DIR="$COLLECT_REPO_ROOT/platform_setup_scripts"
readonly EVIDENCE_UTILITY="$SCRIPT_DIR/evidence_utils.py"
readonly METADATA_SCHEMA="$COLLECT_REPO_ROOT/schemas/run-metadata.schema.json"
readonly KARGO_PROJECT="resilience-gate"

mode="plan"
scenario=""
status=""
run_id=""
config_file="${CONFIG_FILE:-$PLATFORM_DIR/config.env}"
output_root="${EVIDENCE_OUTPUT_ROOT:-/tmp/resilience-gate-evidence}"
allow_repository_output=false
acknowledged_lab=false
analysis_run=""
gate_job=""
gate_pod=""
repository_revision="unavailable"
chart_revision="unavailable"
release_image_digest="unavailable"
gate_runner_image_digest="unavailable"
signer_image_digest="unavailable"
loadgen_image_digest="unavailable"
declare -a includes=()

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/collect-evidence.sh --plan --scenario NAME --status STATUS --run-id ID
  ./scripts/collect-evidence.sh --collect --acknowledge-owned-testnet-lab \
    --scenario NAME --status STATUS --run-id ID --config PATH [options]

Required options:
  --scenario baseline|chaos-gate|regression-blocked|recovery|prod-smoke
  --status pass|fail|blocked|unavailable
  --run-id ID                   Local evidence identifier; never reuse one.

Collection options:
  --analysis-run NAME           Exact Kargo-created AnalysisRun to capture.
  --gate-job NAME               Exact chaos-gate Job; its Pod is discovered.
  --gate-pod NAME               Exact chaos-gate Pod; captures logs/scorecards.
  --include ABSOLUTE_FILE       Add a sanitized local status/log extract (repeatable).
  --output-root ABSOLUTE_DIR    Defaults to /tmp/resilience-gate-evidence.
  --allow-repository-output     Required if output-root is inside this repository.
  --config PATH                 Ignored platform config used only for context guard.

Release identities (use `unavailable` only when no associated claim is made):
  --repository-revision SHA
  --chart-revision SHA
  --release-image-digest sha256:...
  --gate-runner-image-digest sha256:...
  --signer-image-digest sha256:...
  --loadgen-image-digest sha256:...

Modes:
  --plan                        Print the validated collection plan (default).
  --collect                     Read the guarded cluster and write sanitized evidence.
  --acknowledge-owned-testnet-lab
                                Required with --collect.
  -h, --help                    Show this help.

The collector never reads Kubernetes Secret values, shell environments, or raw
configuration. It does not start, delete, patch, or apply Kubernetes resources.
USAGE
}

die() {
  printf 'evidence collection: %s\n' "$*" >&2
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
    --collect)
      mode="collect"
      shift
      ;;
    --scenario|--status|--run-id|--config|--output-root|--analysis-run|--gate-job|--gate-pod|--repository-revision|--chart-revision|--release-image-digest|--gate-runner-image-digest|--signer-image-digest|--loadgen-image-digest|--include)
      need_value "$@"
      case "$1" in
        --scenario) scenario="$2" ;;
        --status) status="$2" ;;
        --run-id) run_id="$2" ;;
        --config) config_file="$2" ;;
        --output-root) output_root="$2" ;;
        --analysis-run) analysis_run="$2" ;;
        --gate-job) gate_job="$2" ;;
        --gate-pod) gate_pod="$2" ;;
        --repository-revision) repository_revision="$2" ;;
        --chart-revision) chart_revision="$2" ;;
        --release-image-digest) release_image_digest="$2" ;;
        --gate-runner-image-digest) gate_runner_image_digest="$2" ;;
        --signer-image-digest) signer_image_digest="$2" ;;
        --loadgen-image-digest) loadgen_image_digest="$2" ;;
        --include) includes+=("$2") ;;
      esac
      shift 2
      ;;
    --acknowledge-owned-testnet-lab)
      acknowledged_lab=true
      shift
      ;;
    --allow-repository-output)
      allow_repository_output=true
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
case "$status" in
  pass|fail|blocked|unavailable) ;;
  "") die "--status is required" ;;
  *) die "unsupported status: $status" ;;
esac
[[ "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$ ]] \
  || die "--run-id must contain only letters, digits, dot, underscore, or dash"

valid_resource_name() {
  [[ "$1" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] && (( ${#1} <= 253 ))
}
for name in "$analysis_run" "$gate_job" "$gate_pod"; do
  [[ -z "$name" ]] || valid_resource_name "$name" \
    || die "resource names must be lowercase DNS names"
done

case "$scenario" in
  baseline)
    target_stage="dev"
    target_namespace="url-shortener-dev"
    analysis_templates=(service-health)
    uses_chaos_gate=false
    ;;
  chaos-gate|regression-blocked|recovery)
    target_stage="staging"
    target_namespace="url-shortener-staging"
    analysis_templates=(service-health chaos-gate)
    uses_chaos_gate=true
    ;;
  prod-smoke)
    target_stage="prod"
    target_namespace="url-shortener-prod"
    analysis_templates=(prod-post-deploy-health)
    uses_chaos_gate=false
    ;;
esac

if [[ "$uses_chaos_gate" != true && ( -n "$gate_job" || -n "$gate_pod" ) ]]; then
  die "--gate-job and --gate-pod are valid only for staging chaos scenarios"
fi

if [[ "$status" == "pass" ]]; then
  for value in "$repository_revision" "$chart_revision" "$release_image_digest"; do
    [[ "$value" != "unavailable" ]] \
      || die "a pass evidence record must identify source, chart, and application image"
  done
  if [[ "$uses_chaos_gate" == true ]]; then
    for value in "$gate_runner_image_digest" "$signer_image_digest" "$loadgen_image_digest"; do
      [[ "$value" != "unavailable" ]] \
        || die "a passing chaos record must identify gate-runner, signer, and load-generator images"
    done
  fi
  [[ -n "$analysis_run" ]] || die "a pass evidence record requires --analysis-run"
  if [[ "$uses_chaos_gate" == true ]]; then
    [[ -n "$gate_job" || -n "$gate_pod" ]] \
      || die "a passing chaos record requires --gate-job or --gate-pod"
  fi
fi

if [[ "$mode" == "plan" ]]; then
  printf 'Evidence collection plan (no directory, cluster, Kargo, cloud, or testnet call has been made):\n'
  printf '  scenario/status: %s / %s\n' "$scenario" "$status"
  printf '  run ID: %s\n' "$run_id"
  printf '  target stage/namespace: %s / %s\n' "$target_stage" "$target_namespace"
  printf '  output root: %s\n' "$output_root"
  [[ -z "$analysis_run" ]] || printf '  AnalysisRun: %s\n' "$analysis_run"
  [[ -z "$gate_job" ]] || printf '  gate Job: %s\n' "$gate_job"
  [[ -z "$gate_pod" ]] || printf '  gate Pod: %s\n' "$gate_pod"
  printf '  supplemental local files: %s\n' "${#includes[@]}"
  cat <<'NOTICE'

--collect requires the explicit owned-testnet acknowledgement, an exact
configured Kubernetes context, and a fresh scenario/run-ID directory. The
result is an evidence bundle, not proof that the supplied status is true.
NOTICE
  exit 0
fi

[[ "$acknowledged_lab" == true ]] \
  || die "--collect requires --acknowledge-owned-testnet-lab"
[[ -x "$EVIDENCE_UTILITY" ]] || die "evidence utility is not executable: $EVIDENCE_UTILITY"
[[ -f "$METADATA_SCHEMA" ]] || die "run metadata schema is missing: $METADATA_SCHEMA"
[[ -f "$config_file" ]] || die "configuration file not found: $config_file"
[[ "$output_root" = /* ]] || die "--output-root must be an absolute path"

# shellcheck source=../platform_setup_scripts/lib.sh
source "$PLATFORM_DIR/lib.sh"
load_config "$config_file"
require_env PROJECT_ID ZONE CLUSTER_NAME
require_command kubectl python3
require_target_context

mkdir -p "$output_root"
output_root="$(cd "$output_root" && pwd -P)"
case "$output_root" in
  "$COLLECT_REPO_ROOT"|"$COLLECT_REPO_ROOT"/*)
    [[ "$allow_repository_output" == true ]] \
      || die "refusing repository output without --allow-repository-output"
    ;;
esac

readonly final_directory="$output_root/$scenario/$run_id"
[[ ! -e "$final_directory" ]] \
  || die "refusing to overwrite existing evidence directory: $final_directory"
mkdir -p "$(dirname "$final_directory")"
temporary_directory="$(mktemp -d "$output_root/.collect-${run_id}.XXXXXX")"

cleanup_temporary_directory() {
  if [[ -n "${temporary_directory:-}" && -d "$temporary_directory" ]]; then
    case "$temporary_directory" in
      "$output_root"/.collect-*) rm -rf -- "$temporary_directory" ;;
    esac
  fi
}
trap cleanup_temporary_directory EXIT INT TERM

declare -a evidence_files=()
declare -a redaction_categories=()

add_redactions() {
  local report="$1" category
  while IFS= read -r category; do
    [[ -n "$category" && "$category" != "none" ]] && redaction_categories+=("$category")
  done < "$report"
  # A report containing only `none` is normal. Do not let the final false
  # predicate become this helper's return status under `set -e`.
  return 0
}

capture_command() {
  local relative_path="$1"
  shift
  local destination="$temporary_directory/$relative_path"
  local report="$temporary_directory/.redaction-${#evidence_files[@]}.txt"
  mkdir -p "$(dirname "$destination")"
  if "$@" 2>&1 | python3 "$EVIDENCE_UTILITY" sanitize \
    --input - --output "$destination" --report "$report"; then
    add_redactions "$report"
    evidence_files+=("$relative_path")
    return 0
  fi
  return 1
}

capture_file() {
  local relative_path="$1" source_path="$2"
  local destination="$temporary_directory/$relative_path"
  local report="$temporary_directory/.redaction-${#evidence_files[@]}.txt"
  mkdir -p "$(dirname "$destination")"
  python3 "$EVIDENCE_UTILITY" sanitize \
    --input "$source_path" --output "$destination" --report "$report"
  add_redactions "$report"
  evidence_files+=("$relative_path")
}

required_capture() {
  local description="$1" relative_path="$2"
  shift 2
  capture_command "$relative_path" "$@" \
    || die "could not collect $description; no evidence bundle was written"
}

# These are intentionally narrow read-only queries. They provide the release
# and runtime context without asking Kubernetes for any Secret object or data.
kubectl get namespace "$target_namespace" >/dev/null \
  || die "target namespace $target_namespace is not present"
required_capture "Stage/$target_stage" "stage/${target_stage}.yaml" \
  kubectl -n "$KARGO_PROJECT" get stage "$target_stage" -o yaml
required_capture "application deployment" "workload/application-deployment.yaml" \
  kubectl -n "$target_namespace" get deployment "url-shortener-${target_stage}" -o yaml
for analysis_template in "${analysis_templates[@]}"; do
  if [[ "$analysis_template" == "chaos-gate" ]]; then
    analysis_path="gate/analysis-template.yaml"
  else
    analysis_path="analysis/${analysis_template}.yaml"
  fi
  required_capture "AnalysisTemplate/$analysis_template" "$analysis_path" \
    kubectl -n "$KARGO_PROJECT" get analysistemplate "$analysis_template" -o yaml
done

if [[ "$uses_chaos_gate" == true ]]; then
  required_capture "staging signer deployment" "workload/signer-deployment.yaml" \
    kubectl -n "$target_namespace" get deployment radius-signer -o yaml
  required_capture "suspended load generator" "workload/loadgen-cronjob.yaml" \
    kubectl -n "$target_namespace" get cronjob loadgen -o yaml
fi

if [[ -n "$analysis_run" ]]; then
  required_capture "AnalysisRun/$analysis_run" "analysis/analysisrun-${analysis_run}.yaml" \
    kubectl -n "$KARGO_PROJECT" get analysisrun "$analysis_run" -o yaml
fi

if [[ -n "$gate_job" ]]; then
  required_capture "Job/$gate_job" "gate/job-${gate_job}.yaml" \
    kubectl -n "$KARGO_PROJECT" get job "$gate_job" -o yaml
  if [[ -z "$gate_pod" ]]; then
    gate_pod="$(kubectl -n "$KARGO_PROJECT" get pods -l "job-name=$gate_job" \
      --sort-by=.metadata.creationTimestamp \
      -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null || true)"
    [[ -n "$gate_pod" ]] \
      || die "could not find a Pod for Job/$gate_job; do not claim scorecard evidence without it"
  fi
fi

if [[ -n "$gate_pod" ]]; then
  required_capture "Pod/$gate_pod" "gate/pod-${gate_pod}.yaml" \
    kubectl -n "$KARGO_PROJECT" get pod "$gate_pod" -o yaml
  gate_log_path="$temporary_directory/gate/pod-${gate_pod}.log"
  required_capture "logs for Pod/$gate_pod" "gate/pod-${gate_pod}.log" \
    kubectl -n "$KARGO_PROJECT" logs "pod/$gate_pod" --all-containers=true --prefix=true --tail=500
  if [[ "$status" == "pass" ]]; then
    for scorecard in postgres-pod-failure redis-pod-failure signer-pod-failure; do
      scorecard_path="scorecards/${scorecard}.json"
      if capture_command "$scorecard_path" \
        kubectl -n "$KARGO_PROJECT" exec "$gate_pod" -c chaos-gate -- \
          cat "/results/${scorecard}.json"; then
        continue
      fi

      # A completed Job cannot serve kubectl exec, but score_experiment.py emits
      # each scorecard to the retained container log.  The log above has already
      # passed through the sanitizer, so this fallback never writes raw output.
      python3 "$EVIDENCE_UTILITY" extract-scorecard \
        --input "$gate_log_path" \
        --experiment "$scorecard" \
        --output "$temporary_directory/$scorecard_path" \
        || die "could not recover scorecard $scorecard from sanitized gate logs"
      evidence_files+=("$scorecard_path")
    done
  fi
fi

declare -A supplemental_names=()
for source_path in "${includes[@]}"; do
  [[ "$source_path" = /* ]] || die "--include must be an absolute path"
  [[ -f "$source_path" && ! -L "$source_path" ]] \
    || die "--include must name a regular, non-symlink file: $source_path"
  basename="$(basename "$source_path")"
  [[ "$basename" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || die "--include basename is not safe for evidence: $basename"
  [[ -z "${supplemental_names[$basename]:-}" ]] \
    || die "duplicate --include basename: $basename"
  supplemental_names["$basename"]=1
  capture_file "supplemental/$basename" "$source_path"
done

if (( ${#redaction_categories[@]} == 0 )); then
  redaction_categories=(none)
else
  mapfile -t redaction_categories < <(printf '%s\n' "${redaction_categories[@]}" | sort -u)
fi

metadata_arguments=(
  write-metadata
  --output "$temporary_directory/run-metadata.json"
  --run-id "$run_id"
  --scenario "$scenario"
  --status "$status"
  --collected-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  --repository-revision "$repository_revision"
  --chart-revision "$chart_revision"
  --release-image-digest "$release_image_digest"
  --gate-runner-image-digest "$gate_runner_image_digest"
  --signer-image-digest "$signer_image_digest"
  --loadgen-image-digest "$loadgen_image_digest"
  --namespace "$target_namespace"
  --cluster-context "$(kubectl config current-context)"
)
for file in "${evidence_files[@]}"; do
  metadata_arguments+=(--file "$file")
done
for category in "${redaction_categories[@]}"; do
  metadata_arguments+=(--redaction "$category")
done
python3 "$EVIDENCE_UTILITY" "${metadata_arguments[@]}"
python3 "$EVIDENCE_UTILITY" validate \
  --schema "$METADATA_SCHEMA" --metadata "$temporary_directory/run-metadata.json"

mv "$temporary_directory" "$final_directory"
temporary_directory=""
trap - EXIT INT TERM
printf 'Sanitized evidence written to %s\n' "$final_directory"
printf 'Review its metadata and artifacts before committing any selected files to docs/evidence/.\n'
