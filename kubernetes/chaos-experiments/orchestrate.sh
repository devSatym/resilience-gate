#!/usr/bin/env bash
# C086 snapshot: run one release-linked staging fault sequence and score it.
# C087 hardens this baseline with a Lease, deadline bounds, and verified cleanup;
# C088 adds a non-fatal Grafana annotation after the verdict is decided.
set -uo pipefail

readonly TARGET_NAMESPACE="${TARGET_NAMESPACE:-url-shortener-staging}"
readonly TARGET_SERVICE="${TARGET_SERVICE:-url-shortener-staging}"
readonly LOADGEN_CRONJOB="${LOADGEN_CRONJOB:-loadgen}"
readonly KUBECTL="${KUBECTL:-kubectl}"
readonly SLEEP_BIN="${SLEEP_BIN:-sleep}"
readonly GATE_SCRIPTS_DIR="${GATE_SCRIPTS_DIR:-/opt/chaos-gate}"
readonly WORKFLOW_FILE="${WORKFLOW_FILE:-${GATE_SCRIPTS_DIR}/workflow.yaml}"
readonly SCORECARD_DIR="${SCORECARD_DIR:-/results}"
readonly PROM_URL="${PROM_URL:-}"
readonly WORKFLOW_TIMEOUT_SECONDS="${WORKFLOW_TIMEOUT_SECONDS:-660}"
readonly LOADGEN_STARTUP_TIMEOUT_SECONDS="${LOADGEN_STARTUP_TIMEOUT_SECONDS:-75}"
readonly POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-5}"
readonly RELEASE_REVISION="${RELEASE_REVISION:-}"
readonly RELEASE_DIGEST="${RELEASE_DIGEST:-}"
readonly RUN_ID="${RUN_ID:-gate-$(date -u +%s)-$$}"
readonly -a EXPERIMENTS=(postgres redis signer)

WORKFLOW_NAME=""
LOADGEN_JOB=""
declare -A INJECTED_AT=()

log() { printf '%s\n' "$*" >&2; }
fail() { log "!! $*"; return 1; }
now_epoch() { date -u +%s; }

validate_settings() {
  [[ -r "$WORKFLOW_FILE" ]] || fail "workflow file is not readable: $WORKFLOW_FILE" || return 1
  [[ -n "$RELEASE_REVISION" && "$RELEASE_REVISION" != *$'\n'* ]] || fail "RELEASE_REVISION is required" || return 1
  [[ "$RELEASE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "RELEASE_DIGEST must be immutable" || return 1
  [[ "$RUN_ID" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || fail "RUN_ID must be a lowercase DNS label" || return 1
}

best_effort_cleanup() {
  [[ -n "$WORKFLOW_NAME" ]] && "$KUBECTL" -n "$TARGET_NAMESPACE" delete workflow "$WORKFLOW_NAME" --ignore-not-found --wait=true >/dev/null 2>&1 || true
  [[ -n "$LOADGEN_JOB" ]] && "$KUBECTL" -n "$TARGET_NAMESPACE" delete job "$LOADGEN_JOB" --ignore-not-found --wait=true >/dev/null 2>&1 || true
}
trap best_effort_cleanup EXIT INT TERM

ensure_target_ready() {
  local endpoints
  endpoints=$("$KUBECTL" -n "$TARGET_NAMESPACE" get endpointslice -l "kubernetes.io/service-name=$TARGET_SERVICE" -o jsonpath='{range .items[*].endpoints[?(@.conditions.ready==true)]}{.addresses[0]}{"\\n"}{end}' 2>/dev/null) || return 1
  [[ -n "${endpoints//[[:space:]]/}" ]] || fail "target Service $TARGET_SERVICE has no ready endpoint" || return 1
}

create_workflow() {
  WORKFLOW_NAME=$("$KUBECTL" -n "$TARGET_NAMESPACE" create -f "$WORKFLOW_FILE" -o jsonpath='{.metadata.name}') || return 1
  [[ -n "$WORKFLOW_NAME" ]] || fail "workflow create returned no name" || return 1
  "$KUBECTL" -n "$TARGET_NAMESPACE" label workflow "$WORKFLOW_NAME" "resilience-gate.io/run-id=$RUN_ID" --overwrite >/dev/null
}

create_loadgen() {
  LOADGEN_JOB="loadgen-$RUN_ID"
  "$KUBECTL" -n "$TARGET_NAMESPACE" create job --from="cronjob/$LOADGEN_CRONJOB" "$LOADGEN_JOB" >/dev/null || return 1
  "$KUBECTL" -n "$TARGET_NAMESPACE" label job "$LOADGEN_JOB" "resilience-gate.io/run-id=$RUN_ID" --overwrite >/dev/null
}

wait_for_loadgen_start() {
  local deadline status active failed
  deadline=$(( $(now_epoch) + LOADGEN_STARTUP_TIMEOUT_SECONDS ))
  while :; do
    status=$("$KUBECTL" -n "$TARGET_NAMESPACE" get job "$LOADGEN_JOB" -o jsonpath='{.status.active}{" "}{.status.failed}' 2>/dev/null || true)
    read -r active failed <<<"${status:-0 0}"
    [[ "${active:-0}" =~ ^[1-9][0-9]*$ ]] && return 0
    [[ "${failed:-0}" =~ ^[1-9][0-9]*$ ]] && return 1
    (( $(now_epoch) < deadline )) || return 1
    "$SLEEP_BIN" "$POLL_INTERVAL_SECONDS"
  done
}

wait_for_workflow() {
  local deadline conditions
  deadline=$(( $(now_epoch) + WORKFLOW_TIMEOUT_SECONDS ))
  while :; do
    conditions=$("$KUBECTL" -n "$TARGET_NAMESPACE" get workflow "$WORKFLOW_NAME" -o jsonpath='{range .status.conditions[*]}{.type}={.status}{" "}{end}' 2>/dev/null || true)
    [[ "$conditions" == *"Accomplished=True"* ]] && return 0
    [[ "$conditions" == *"Failed=True"* ]] && return 1
    (( $(now_epoch) < deadline )) || return 1
    "$SLEEP_BIN" "$POLL_INTERVAL_SECONDS"
  done
}

collect_injection_times() {
  local rows template_name inject_at
  rows=$("$KUBECTL" -n "$TARGET_NAMESPACE" get workflownode -l "chaos-mesh.org/workflow=$WORKFLOW_NAME" -o jsonpath='{range .items[*]}{.spec.templateName}{"\\t"}{.spec.startTime}{"\\n"}{end}' 2>/dev/null) || return 1
  while IFS=$'\t' read -r template_name inject_at; do
    [[ -n "$template_name" && -n "$inject_at" ]] && INJECTED_AT["$template_name"]="$inject_at"
  done <<<"$rows"
}

score_experiments() {
  local experiment name inject_at path result=0
  mkdir -p "$SCORECARD_DIR" || return 1
  for experiment in "${EXPERIMENTS[@]}"; do
    name="${experiment}-pod-failure"
    inject_at="${INJECTED_AT[$experiment]:-}"
    [[ -n "$inject_at" ]] || { log "!! missing injection time for $experiment"; result=1; continue; }
    path="$SCORECARD_DIR/$name.json"
    local -a command=(python3 "$GATE_SCRIPTS_DIR/score_experiment.py" "$name" --inject-at "$inject_at" --duration 60 --namespace "$TARGET_NAMESPACE" --release-revision "$RELEASE_REVISION" --release-digest "$RELEASE_DIGEST" --run-id "$WORKFLOW_NAME" --scorecard-path "$path")
    [[ -n "$PROM_URL" ]] && command+=(--prom "$PROM_URL")
    "${command[@]}" || result=1
  done
  return "$result"
}

main() {
  validate_settings || return 1
  ensure_target_ready || return 1
  create_workflow || return 1
  create_loadgen || return 1
  wait_for_loadgen_start || { fail "loadgen did not start in the baseline window"; return 1; }
  wait_for_workflow || { fail "workflow did not finish"; return 1; }
  collect_injection_times || return 1
  score_experiments
}

main "$@"
