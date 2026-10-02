#!/usr/bin/env bash
# Create one explicitly approved, bounded load-generation Job.
#
# This script deliberately defaults to --plan and makes no kubectl or network
# call until an operator passes --execute. Its default staging scenario sends
# paid traffic on the owned Radius testnet. The separate baseline scenario is
# bounded, unpaid GET traffic to development and is never part of pytest or CI.

set -euo pipefail

readonly NAMESPACE="url-shortener-staging"
readonly CRONJOB="loadgen"
readonly MAX_VUS=3
readonly MAX_DURATION_SECONDS=600
readonly DEV_NAMESPACE="url-shortener-dev"
readonly DEV_DEPLOYMENT="url-shortener-dev"
readonly DEV_BASE_URL="http://url-shortener-dev.url-shortener-dev.svc.cluster.local"
readonly BASELINE_MAX_DURATION_SECONDS=90
readonly BASELINE_MAX_ARRIVAL_RATE=60
readonly BASELINE_ACTIVE_DEADLINE_SECONDS=150
readonly BASELINE_MAX_WAIT_SECONDS=180

mode="plan"
scenario="staging"
profile="arrival-rate"
duration="10m"
vus="3"
arrival_rate="60"
arrival_time_unit="1m"
sleep_seconds="1"
wait_timeout="15m"
artifact_dir="${LOADGEN_ARTIFACT_DIR:-/tmp/resilience-gate-loadgen}"
duration_set=false
vus_set=false
arrival_rate_set=false
arrival_time_unit_set=false
wait_timeout_set=false
baseline_job_needs_cleanup=false
baseline_cleanup_at=""
job_name=""
pod_name=""
baseline_requested_at=""
baseline_observation_started_at=""
baseline_observation_ended_at=""

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/run-loadgen.sh --plan [options]
  ./scripts/run-loadgen.sh --execute [options]

Options:
  --scenario staging|baseline       Paid staging load (default), or the bounded
                                    unpaid development baseline.
  --profile closed-loop|arrival-rate   Load profile (default: arrival-rate)
  --duration <seconds|minutes>         1s through 10m (default: 10m)
  --vus 1..3                           One bounded signer wallet per VU (default: 3)
  --arrival-rate 1..600                Iterations per time unit (default: 60)
  --arrival-time-unit <seconds|minutes>
                                       Arrival-rate unit, up to 60m (default: 1m)
  --sleep-seconds <positive number>    Closed-loop pause (default: 1)
  --wait-timeout <Go duration>         Completion wait timeout (default: 15m)
  --artifact-dir <absolute path>       Result destination (default: /tmp/resilience-gate-loadgen)
  --plan                               Print the validated run; do not contact a cluster (default)
  --execute                            Create the one-off Job and copy its summary JSON
  -h, --help                           Show this help

`--execute` is an explicit acknowledgement that the default scenario sends
paid traffic only to the owned Radius testnet. `--scenario baseline` instead
uses the same suspended staging source CronJob to make at most 90 seconds of
one-VU unpaid GET / traffic to development. It never calls the signer or a
payment endpoint. Both scenarios require the suspended `loadgen` CronJob.
USAGE
}

die() {
  printf 'loadgen runner: %s\n' "$*" >&2
  exit 2
}

need_option_value() {
  [[ $# -ge 2 ]] || die "$1 requires a value"
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
      need_option_value "$@"
      scenario="$2"
      shift 2
      ;;
    --profile)
      need_option_value "$@"
      profile="$2"
      shift 2
      ;;
    --duration)
      need_option_value "$@"
      duration="$2"
      duration_set=true
      shift 2
      ;;
    --vus)
      need_option_value "$@"
      vus="$2"
      vus_set=true
      shift 2
      ;;
    --arrival-rate)
      need_option_value "$@"
      arrival_rate="$2"
      arrival_rate_set=true
      shift 2
      ;;
    --arrival-time-unit)
      need_option_value "$@"
      arrival_time_unit="$2"
      arrival_time_unit_set=true
      shift 2
      ;;
    --sleep-seconds)
      need_option_value "$@"
      sleep_seconds="$2"
      shift 2
      ;;
    --wait-timeout)
      need_option_value "$@"
      wait_timeout="$2"
      wait_timeout_set=true
      shift 2
      ;;
    --artifact-dir)
      need_option_value "$@"
      artifact_dir="$2"
      shift 2
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
  staging)
    target_namespace="$NAMESPACE"
    target_deployment="url-shortener-staging"
    target_base_url=""
    traffic_mode="paid"
    ;;
  baseline)
    target_namespace="$DEV_NAMESPACE"
    target_deployment="$DEV_DEPLOYMENT"
    target_base_url="$DEV_BASE_URL"
    traffic_mode="unpaid-baseline"
    [[ "$duration_set" == true ]] || duration="90s"
    [[ "$vus_set" == true ]] || vus="1"
    [[ "$arrival_rate_set" == true ]] || arrival_rate="30"
    [[ "$arrival_time_unit_set" == true ]] || arrival_time_unit="1m"
    [[ "$wait_timeout_set" == true ]] || wait_timeout="3m"
    ;;
  *) die "--scenario must be staging or baseline" ;;
esac

duration_seconds() {
  local value="$1"
  [[ "$value" =~ ^([1-9][0-9]*)(s|m)$ ]] || return 1
  local amount="${BASH_REMATCH[1]}"
  local unit="${BASH_REMATCH[2]}"
  # Bound before arithmetic so an untrusted oversized shell integer cannot
  # wrap around and evade the duration cap below.
  [[ ${#amount} -le 5 ]] || return 1
  if [[ "$unit" == "m" ]]; then
    printf '%s\n' "$((amount * 60))"
  else
    printf '%s\n' "$amount"
  fi
}

wait_timeout_seconds() {
  local value="$1"
  [[ "$value" =~ ^([1-9][0-9]*)(s|m|h)$ ]] || return 1
  local amount="${BASH_REMATCH[1]}"
  local unit="${BASH_REMATCH[2]}"
  [[ ${#amount} -le 5 ]] || return 1
  case "$unit" in
    s) printf '%s\n' "$amount" ;;
    m) printf '%s\n' "$((amount * 60))" ;;
    h) printf '%s\n' "$((amount * 3600))" ;;
  esac
}

validate_positive_integer() {
  local name="$1"
  local value="$2"
  local maximum="$3"
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "$name must be a positive integer"
  local maximum_digits=${#maximum}
  if (( ${#value} > maximum_digits )) \
    || { (( ${#value} == maximum_digits )) && [[ "$value" > "$maximum" ]]; }; then
    die "$name must be no more than $maximum"
  fi
}

case "$profile" in
  closed-loop|arrival-rate) ;;
  *) die "--profile must be closed-loop or arrival-rate" ;;
esac

duration_seconds_value="$(duration_seconds "$duration")" || die "--duration must use s or m"
(( duration_seconds_value <= MAX_DURATION_SECONDS )) || die "--duration must be at most 10m"

arrival_time_unit_seconds="$(duration_seconds "$arrival_time_unit")" || die "--arrival-time-unit must use s or m"
(( arrival_time_unit_seconds <= 3600 )) || die "--arrival-time-unit must be at most 60m"

validate_positive_integer "--vus" "$vus" "$MAX_VUS"
validate_positive_integer "--arrival-rate" "$arrival_rate" 600
[[ "$sleep_seconds" =~ ^[0-9]+([.][0-9]+)?$ ]] || die "--sleep-seconds must be a positive number"
[[ "$sleep_seconds" != "0" && "$sleep_seconds" != "0.0" && "$sleep_seconds" != "0.00" ]] || die "--sleep-seconds must be greater than zero"
[[ "$wait_timeout" =~ ^[1-9][0-9]*(s|m|h)$ ]] || die "--wait-timeout must use s, m, or h"
[[ "$artifact_dir" = /* ]] || die "--artifact-dir must be an absolute path"

if [[ "$scenario" == "baseline" ]]; then
  [[ "$profile" == "arrival-rate" ]] \
    || die "--scenario baseline requires --profile arrival-rate"
  (( duration_seconds_value <= BASELINE_MAX_DURATION_SECONDS )) \
    || die "--scenario baseline duration must be at most ${BASELINE_MAX_DURATION_SECONDS}s"
  [[ "$vus" == "1" ]] || die "--scenario baseline requires exactly one virtual user"
  [[ "$arrival_time_unit" == "1m" ]] \
    || die "--scenario baseline requires --arrival-time-unit 1m"
  (( arrival_rate <= BASELINE_MAX_ARRIVAL_RATE )) \
    || die "--scenario baseline arrival rate must be at most ${BASELINE_MAX_ARRIVAL_RATE} per minute"
  wait_timeout_seconds_value="$(wait_timeout_seconds "$wait_timeout")" \
    || die "--scenario baseline --wait-timeout must use s, m, or h"
  (( wait_timeout_seconds_value <= BASELINE_MAX_WAIT_SECONDS )) \
    || die "--scenario baseline --wait-timeout must be at most ${BASELINE_MAX_WAIT_SECONDS}s"
fi

print_plan() {
  cat <<PLAN
Load-generation plan (no cluster call has been made):
  scenario:          $scenario
  source namespace:  $NAMESPACE
  source CronJob:    $CRONJOB (must remain suspended)
  target namespace:  $target_namespace
  target deployment: $target_deployment
  profile:           $profile
  duration:          $duration
  virtual users:     $vus
  arrival rate:      $arrival_rate per $arrival_time_unit
  result directory:  $artifact_dir

PLAN
  if [[ "$scenario" == "baseline" ]]; then
    cat <<BASELINE_NOTICE
  target URL:        $target_base_url
  traffic mode:      $traffic_mode (GET / only; no signer or payment calls)

The generated Job reuses the source CronJob's digest-pinned k6 image but
overrides its target and traffic mode. It is capped at 90 seconds and one VU;
its Job deadline is capped at ${BASELINE_ACTIVE_DEADLINE_SECONDS} seconds, and its
exact Job is deleted only after the local summary is copied.
BASELINE_NOTICE
  else
    cat <<STAGING_NOTICE

The generated Job uses the CronJob's digest-pinned k6 image, explicit
testnet-only configuration, signer/app readiness prechecks, and a JSON summary.
Run again with --execute only after reviewing the owned staging environment.
STAGING_NOTICE
  fi
}

cleanup_baseline_job() {
  [[ "$scenario" == "baseline" && "$baseline_job_needs_cleanup" == true ]] || return 0

  if ! kubectl -n "$NAMESPACE" delete job "$job_name" --ignore-not-found --wait=true >/dev/null; then
    printf 'loadgen runner: could not delete baseline Job/%s\n' "$job_name" >&2
    return 1
  fi
  if kubectl -n "$NAMESPACE" get job "$job_name" >/dev/null 2>&1; then
    printf 'loadgen runner: baseline Job/%s still exists after exact cleanup\n' "$job_name" >&2
    return 1
  fi

  baseline_job_needs_cleanup=false
  baseline_cleanup_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

cleanup_baseline_on_exit() {
  local exit_status=$?
  trap - EXIT
  if [[ "$scenario" == "baseline" && "$baseline_job_needs_cleanup" == true ]]; then
    if ! cleanup_baseline_job; then
      printf 'loadgen runner: baseline cleanup could not be verified\n' >&2
      if (( exit_status == 0 )); then
        exit_status=1
      fi
    fi
  fi
  exit "$exit_status"
}

write_baseline_record() {
  local record_path="$artifact_dir/$job_name-run.json"
  python3 - "$record_path" "$job_name" "$pod_name" "$baseline_requested_at" \
    "$baseline_observation_started_at" "$baseline_observation_ended_at" \
    "$baseline_cleanup_at" "$(basename "$summary_path")" \
    "$duration_seconds_value" "$BASELINE_ACTIVE_DEADLINE_SECONDS" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

(
    output,
    job_name,
    pod_name,
    requested_at,
    observation_started_at,
    observation_ended_at,
    cleanup_at,
    summary_file,
    configured_duration_seconds,
    active_deadline_seconds,
) = sys.argv[1:]

record = {
    "schema_version": "resilience-gate.baseline-run/v1",
    "scenario": "baseline",
    "source": {
        "namespace": "url-shortener-staging",
        "cronjob": "loadgen",
        "job": job_name,
        "pod": pod_name,
    },
    "target": {
        "namespace": "url-shortener-dev",
        "deployment": "url-shortener-dev",
        "base_url": "http://url-shortener-dev.url-shortener-dev.svc.cluster.local",
        "traffic": "unpaid GET / only",
    },
    "requested_at": requested_at,
    "observation": {
        "started_at": observation_started_at,
        "ended_at": observation_ended_at,
        "configured_duration_seconds": int(configured_duration_seconds),
        "job_active_deadline_seconds": int(active_deadline_seconds),
    },
    "summary_file": summary_file,
    "cleanup": {
        "strategy": "exact-job-delete",
        "completed_at": cleanup_at,
        "verified_absent": True,
    },
}
Path(output).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  printf 'Baseline run and cleanup record copied to %s\n' "$record_path"
}

print_plan
[[ "$mode" == "execute" ]] || exit 0

command -v kubectl >/dev/null 2>&1 || die "kubectl is required for --execute"
if [[ "$scenario" == "baseline" ]]; then
  command -v python3 >/dev/null 2>&1 || die "python3 is required to write the baseline run record"
fi
context="$(kubectl config current-context 2>/dev/null || true)"
[[ -n "$context" ]] || die "kubectl has no current context"

if [[ "$scenario" == "baseline" ]]; then
  printf 'Executing bounded unpaid baseline against Kubernetes context %q (source %q, target %q).\n' \
    "$context" "$NAMESPACE" "$target_namespace"
else
  printf 'Executing testnet load run against Kubernetes context %q in %q.\n' "$context" "$NAMESPACE"
fi

# Prechecks are intentionally explicit and occur before the one-off Job is
# created. They do not create testnet payments themselves.
[[ "$(kubectl -n "$NAMESPACE" get cronjob "$CRONJOB" -o jsonpath='{.spec.suspend}')" == "true" ]] \
  || die "CronJob/$CRONJOB must be suspended before a manual run"
kubectl -n "$target_namespace" wait --for=condition=available "deployment/$target_deployment" --timeout=120s
if [[ "$scenario" == "staging" ]]; then
  kubectl -n "$NAMESPACE" wait --for=condition=available deployment/radius-signer --timeout=240s
  kubectl -n "$NAMESPACE" wait --for=condition=Ready externalsecret/resilience-gate-signer --timeout=120s
  kubectl -n "$NAMESPACE" wait --for=condition=Ready externalsecret/resilience-gate-loadgen --timeout=120s
fi

run_stamp="$(date -u +%Y%m%d%H%M%S)"
if [[ "$scenario" == "baseline" ]]; then
  job_name="baseline-manual-$run_stamp"
  baseline_requested_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if kubectl -n "$NAMESPACE" get job "$job_name" >/dev/null 2>&1; then
    die "refusing to reuse existing baseline Job/$job_name"
  fi
  trap cleanup_baseline_on_exit EXIT
else
  job_name="loadgen-manual-$run_stamp"
fi

# Generate locally, inject only validated non-secret controls, then apply the
# new Job. `--from=cronjob` carries the signed image and secret contract.
if [[ "$scenario" == "baseline" ]]; then
  baseline_job_needs_cleanup=true
  kubectl -n "$NAMESPACE" create job "$job_name" --from="cronjob/$CRONJOB" --dry-run=client -o yaml \
    | kubectl -n "$NAMESPACE" set env --local -f - -o yaml \
        "BASE_URL=$target_base_url" \
        "PAYMENT_ENABLED=false" \
        "TRAFFIC_MODE=$traffic_mode" \
        "LOAD_PROFILE=$profile" \
        "DURATION=$duration" \
        "VUS=$vus" \
        "ARRIVAL_RATE=$arrival_rate" \
        "ARRIVAL_TIME_UNIT=$arrival_time_unit" \
        "SLEEP_SECONDS=$sleep_seconds" \
    | kubectl -n "$NAMESPACE" patch --local -f - --type=merge \
        -p "{\"spec\":{\"activeDeadlineSeconds\":$BASELINE_ACTIVE_DEADLINE_SECONDS}}" -o yaml \
    | kubectl -n "$NAMESPACE" apply --server-side --field-manager=resilience-gate-loadgen -f -
else
  kubectl -n "$NAMESPACE" create job "$job_name" --from="cronjob/$CRONJOB" --dry-run=client -o yaml \
    | kubectl -n "$NAMESPACE" set env --local -f - -o yaml \
        "LOAD_PROFILE=$profile" \
        "DURATION=$duration" \
        "VUS=$vus" \
        "ARRIVAL_RATE=$arrival_rate" \
        "ARRIVAL_TIME_UNIT=$arrival_time_unit" \
        "SLEEP_SECONDS=$sleep_seconds" \
    | kubectl -n "$NAMESPACE" apply --server-side --field-manager=resilience-gate-loadgen -f -
fi

if ! kubectl -n "$NAMESPACE" wait --for=condition=complete "job/$job_name" --timeout="$wait_timeout"; then
  kubectl -n "$NAMESPACE" logs "job/$job_name" --all-containers=true --tail=200 || true
  if [[ "$scenario" == "baseline" ]]; then
    die "Job/$job_name did not complete; exact cleanup is being attempted"
  fi
  die "Job/$job_name did not complete; inspect it before attempting another paid run"
fi

pod_name="$(kubectl -n "$NAMESPACE" get pod -l "job-name=$job_name" -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$pod_name" ]] || die "could not locate the completed pod for Job/$job_name"
if [[ "$scenario" == "baseline" ]]; then
  pod_timestamps="$(kubectl -n "$NAMESPACE" get pod "$pod_name" -o json | python3 -c '
import json
import sys

pod = json.load(sys.stdin)
status = pod.get("status", {})
started_at = status.get("startTime")
finished_at = next(
    (
        item.get("state", {}).get("terminated", {}).get("finishedAt")
        for item in status.get("containerStatuses", [])
        if item.get("name") == "k6"
    ),
    None,
)
if not isinstance(started_at, str) or not isinstance(finished_at, str):
    raise SystemExit("completed baseline Pod is missing start or k6 finish time")
print(f"{started_at}\t{finished_at}")
')"
  IFS=$'\t' read -r baseline_observation_started_at baseline_observation_ended_at <<< "$pod_timestamps"
  [[ -n "$baseline_observation_started_at" && -n "$baseline_observation_ended_at" ]] \
    || die "could not bind the baseline observation window to completed Pod/$pod_name"
fi
mkdir -p "$artifact_dir"
summary_path="$artifact_dir/$job_name-summary.json"
kubectl -n "$NAMESPACE" cp -c k6 "$pod_name:/results/summary.json" "$summary_path"
if [[ "$scenario" == "baseline" ]]; then
  cleanup_baseline_job || die "could not verify exact cleanup for Job/$job_name"
  write_baseline_record
fi
printf 'Load-generation summary copied to %s\n' "$summary_path"
