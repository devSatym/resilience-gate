#!/usr/bin/env bash
# Create one explicitly approved, bounded staging load-generation Job.
#
# This script deliberately defaults to --plan and makes no kubectl or network
# call until an operator passes --execute. An executed run sends paid traffic
# on the owned Radius testnet, so it is never part of pytest or CI.

set -euo pipefail

readonly NAMESPACE="url-shortener-staging"
readonly CRONJOB="loadgen"
readonly MAX_VUS=3
readonly MAX_DURATION_SECONDS=600

mode="plan"
profile="arrival-rate"
duration="10m"
vus="3"
arrival_rate="60"
arrival_time_unit="1m"
sleep_seconds="1"
wait_timeout="15m"
artifact_dir="${LOADGEN_ARTIFACT_DIR:-/tmp/resilience-gate-loadgen}"

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/run-loadgen.sh --plan [options]
  ./scripts/run-loadgen.sh --execute [options]

Options:
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

`--execute` is an explicit acknowledgement that this sends paid traffic only
to the owned Radius testnet. It refuses any namespace other than
url-shortener-staging and requires the suspended `loadgen` CronJob.
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
    --profile)
      need_option_value "$@"
      profile="$2"
      shift 2
      ;;
    --duration)
      need_option_value "$@"
      duration="$2"
      shift 2
      ;;
    --vus)
      need_option_value "$@"
      vus="$2"
      shift 2
      ;;
    --arrival-rate)
      need_option_value "$@"
      arrival_rate="$2"
      shift 2
      ;;
    --arrival-time-unit)
      need_option_value "$@"
      arrival_time_unit="$2"
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

print_plan() {
  cat <<PLAN
Load-generation plan (no cluster call has been made):
  namespace:         $NAMESPACE
  source CronJob:    $CRONJOB (must remain suspended)
  profile:           $profile
  duration:          $duration
  virtual users:     $vus (max $MAX_VUS signer wallets)
  arrival rate:      $arrival_rate per $arrival_time_unit
  result directory:  $artifact_dir

The generated Job uses the CronJob's digest-pinned k6 image, explicit
testnet-only configuration, signer/app readiness prechecks, and a JSON summary.
Run again with --execute only after reviewing the owned staging environment.
PLAN
}

print_plan
[[ "$mode" == "execute" ]] || exit 0

command -v kubectl >/dev/null 2>&1 || die "kubectl is required for --execute"
context="$(kubectl config current-context 2>/dev/null || true)"
[[ -n "$context" ]] || die "kubectl has no current context"

printf 'Executing testnet load run against Kubernetes context %q in %q.\n' "$context" "$NAMESPACE"

# Prechecks are intentionally explicit and occur before the one-off Job is
# created. They do not create testnet payments themselves.
[[ "$(kubectl -n "$NAMESPACE" get cronjob "$CRONJOB" -o jsonpath='{.spec.suspend}')" == "true" ]] \
  || die "CronJob/$CRONJOB must be suspended before a manual run"
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/url-shortener-staging --timeout=120s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/radius-signer --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=Ready externalsecret/resilience-gate-signer --timeout=120s
kubectl -n "$NAMESPACE" wait --for=condition=Ready externalsecret/resilience-gate-loadgen --timeout=120s

run_stamp="$(date -u +%Y%m%d%H%M%S)"
job_name="loadgen-manual-$run_stamp"

# Generate locally, inject only validated non-secret controls, then apply the
# new Job. `--from=cronjob` carries the signed image and secret contract.
kubectl -n "$NAMESPACE" create job "$job_name" --from="cronjob/$CRONJOB" --dry-run=client -o yaml \
  | kubectl -n "$NAMESPACE" set env --local -f - -o yaml \
      "LOAD_PROFILE=$profile" \
      "DURATION=$duration" \
      "VUS=$vus" \
      "ARRIVAL_RATE=$arrival_rate" \
      "ARRIVAL_TIME_UNIT=$arrival_time_unit" \
      "SLEEP_SECONDS=$sleep_seconds" \
  | kubectl -n "$NAMESPACE" apply --server-side --field-manager=resilience-gate-loadgen -f -

if ! kubectl -n "$NAMESPACE" wait --for=condition=complete "job/$job_name" --timeout="$wait_timeout"; then
  kubectl -n "$NAMESPACE" logs "job/$job_name" --all-containers=true --tail=200 || true
  die "Job/$job_name did not complete; inspect it before attempting another paid run"
fi

pod_name="$(kubectl -n "$NAMESPACE" get pod -l "job-name=$job_name" -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$pod_name" ]] || die "could not locate the completed pod for Job/$job_name"
mkdir -p "$artifact_dir"
summary_path="$artifact_dir/$job_name-summary.json"
kubectl -n "$NAMESPACE" cp -c k6 "$pod_name:/results/summary.json" "$summary_path"
printf 'Load-generation summary copied to %s\n' "$summary_path"
