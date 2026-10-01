#!/usr/bin/env bash
# Run one bounded, release-linked chaos verification. This program is the
# gate's only mutating client: every created object has a run identifier and
# cleanup deletes and verifies only those exact objects. It deliberately fails
# closed on a missing target, an occupied Lease, incomplete workflow, missing
# score input, or cleanup uncertainty.

set -uo pipefail

readonly TARGET_NAMESPACE="${TARGET_NAMESPACE:-url-shortener-staging}"
readonly CONTROL_NAMESPACE="${CONTROL_NAMESPACE:-resilience-gate}"
readonly TARGET_SERVICE="${TARGET_SERVICE:-url-shortener-staging}"
readonly LOADGEN_CRONJOB="${LOADGEN_CRONJOB:-loadgen}"
readonly KUBECTL="${KUBECTL:-kubectl}"
readonly SLEEP_BIN="${SLEEP_BIN:-sleep}"
readonly TIMEOUT_BIN="${TIMEOUT_BIN:-timeout}"
readonly GATE_SCRIPTS_DIR="${GATE_SCRIPTS_DIR:-/opt/chaos-gate}"
readonly WORKFLOW_FILE="${WORKFLOW_FILE:-${GATE_SCRIPTS_DIR}/workflow.yaml}"
readonly SCORECARD_DIR="${SCORECARD_DIR:-/results}"
readonly PROM_URL="${PROM_URL:-}"

# The workflow itself is capped at 660 seconds: 90 seconds baseline, three
# 60-second faults, and 120/60/60 second recovery windows. The runner may use
# a shorter timeout in an offline test, but never a longer one. The enclosing
# Kargo Job and Lease must also cover loadgen start, fail-closed scoring,
# non-fatal annotation, and verified cleanup; otherwise an active deadline
# could kill the process before it removes its exact fault objects.
readonly WORKFLOW_TIMEOUT_SECONDS="${WORKFLOW_TIMEOUT_SECONDS:-660}"
readonly LOADGEN_STARTUP_TIMEOUT_SECONDS="${LOADGEN_STARTUP_TIMEOUT_SECONDS:-75}"
readonly POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-5}"
readonly SCORER_TIMEOUT_SECONDS="${SCORER_TIMEOUT_SECONDS:-105}"
readonly ANNOTATION_TIMEOUT_SECONDS="${ANNOTATION_TIMEOUT_SECONDS:-15}"
readonly CLEANUP_TIMEOUT_SECONDS="${CLEANUP_TIMEOUT_SECONDS:-120}"
readonly GATE_JOB_DEADLINE_SECONDS="${GATE_JOB_DEADLINE_SECONDS:-1320}"
readonly LOCK_DURATION_SECONDS="${LOCK_DURATION_SECONDS:-1470}"
readonly LOCK_NAME="${LOCK_NAME:-chaos-gate-runner}"
readonly GATE_SELECTOR="resilience-gate.io/gate=chaos"

readonly MAX_LOADGEN_STARTUP_SECONDS=90
readonly MAX_WORKFLOW_SECONDS=660
readonly PROMETHEUS_REQUEST_TIMEOUT_SECONDS=15
readonly MAX_PROMETHEUS_QUERIES_PER_EXPERIMENT=6
readonly EXPERIMENT_COUNT=3
readonly MIN_SCORER_TIMEOUT_SECONDS=$((
  PROMETHEUS_REQUEST_TIMEOUT_SECONDS * MAX_PROMETHEUS_QUERIES_PER_EXPERIMENT
))
readonly MAX_SCORING_SECONDS=$((EXPERIMENT_COUNT * SCORER_TIMEOUT_SECONDS))
readonly GATE_JOB_SAFETY_BUFFER_SECONDS=60
readonly LOCK_POST_JOB_BUFFER_SECONDS=150
readonly MIN_GATE_JOB_BUDGET_SECONDS=$((
  MAX_LOADGEN_STARTUP_SECONDS + MAX_WORKFLOW_SECONDS + MAX_SCORING_SECONDS +
  ANNOTATION_TIMEOUT_SECONDS + CLEANUP_TIMEOUT_SECONDS + GATE_JOB_SAFETY_BUFFER_SECONDS
))

readonly RELEASE_REVISION="${RELEASE_REVISION:-}"
readonly RELEASE_DIGEST="${RELEASE_DIGEST:-}"
readonly RUN_ID="${RUN_ID:-gate-$(date -u +%s)-$$}"

readonly -a EXPERIMENTS=(postgres redis signer)

WORKFLOW_NAME=""
LOADGEN_JOB=""
SCORER_RUN_ID=""
LOCK_HELD=0
CLEANUP_DEADLINE_EPOCH=0
declare -a FAILED_EXPERIMENTS=()
declare -A INJECTED_AT=()

log() {
  printf '%s\n' "$*" >&2
}

fail() {
  log "!! $*"
  return 1
}

is_positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

now_epoch() {
  date -u +%s
}

validate_settings() {
  local value
  for value in "$WORKFLOW_TIMEOUT_SECONDS" "$LOADGEN_STARTUP_TIMEOUT_SECONDS" \
    "$POLL_INTERVAL_SECONDS" "$SCORER_TIMEOUT_SECONDS" \
    "$ANNOTATION_TIMEOUT_SECONDS" "$CLEANUP_TIMEOUT_SECONDS" \
    "$GATE_JOB_DEADLINE_SECONDS" "$LOCK_DURATION_SECONDS"; do
    is_positive_integer "$value" || fail "timeout values must be positive integers" || return 1
  done
  (( WORKFLOW_TIMEOUT_SECONDS <= MAX_WORKFLOW_SECONDS )) || {
    fail "WORKFLOW_TIMEOUT_SECONDS cannot exceed the 660 second workflow deadline"
    return 1
  }
  (( LOADGEN_STARTUP_TIMEOUT_SECONDS <= MAX_LOADGEN_STARTUP_SECONDS )) || {
    fail "LOADGEN_STARTUP_TIMEOUT_SECONDS cannot exceed the baseline window"
    return 1
  }
  (( SCORER_TIMEOUT_SECONDS >= MIN_SCORER_TIMEOUT_SECONDS )) || {
    fail "SCORER_TIMEOUT_SECONDS must cover six 15-second Prometheus calls"
    return 1
  }
  (( GATE_JOB_DEADLINE_SECONDS >= MIN_GATE_JOB_BUDGET_SECONDS )) || {
    fail "GATE_JOB_DEADLINE_SECONDS cannot cover startup, workflow, scoring, annotation, and cleanup"
    return 1
  }
  (( LOCK_DURATION_SECONDS >= GATE_JOB_DEADLINE_SECONDS + LOCK_POST_JOB_BUFFER_SECONDS )) || {
    fail "LOCK_DURATION_SECONDS must outlast the complete gate Job and post-job cleanup buffer"
    return 1
  }
  command -v "$TIMEOUT_BIN" >/dev/null 2>&1 || {
    fail "TIMEOUT_BIN is required to bound scoring and cleanup"
    return 1
  }
  [[ "$RUN_ID" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] \
    && (( ${#RUN_ID} <= 50 )) || {
      fail "RUN_ID must be a lowercase DNS label of at most 50 characters"
      return 1
    }
  [[ -n "$RELEASE_REVISION" && ${#RELEASE_REVISION} -le 256 && "$RELEASE_REVISION" != *$'\n'* ]] || {
    fail "RELEASE_REVISION must be a non-empty single-line source identifier"
    return 1
  }
  [[ "$RELEASE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || {
    fail "RELEASE_DIGEST must be the immutable application digest under verification"
    return 1
  }
  [[ -r "$WORKFLOW_FILE" ]] || {
    fail "workflow file is not readable: $WORKFLOW_FILE"
    return 1
  }
}

lease_document() {
  local resource_version="${1:-}"
  local observed_at
  # coordination.k8s.io/v1 Lease timestamps are MicroTime values. Kubernetes
  # validates them strictly, so retain an explicit six-digit fractional part
  # instead of emitting RFC3339 seconds-only timestamps.
  observed_at=$(date -u +%Y-%m-%dT%H:%M:%S.000000Z)
  cat <<EOF
apiVersion: coordination.k8s.io/v1
kind: Lease
metadata:
  name: ${LOCK_NAME}
  namespace: ${CONTROL_NAMESPACE}
${resource_version:+  resourceVersion: ${resource_version}}
spec:
  holderIdentity: ${RUN_ID}
  leaseDurationSeconds: ${LOCK_DURATION_SECONDS}
  acquireTime: ${observed_at}
  renewTime: ${observed_at}
EOF
}

lease_is_expired() {
  local observed_at="$1"
  local duration="$2"
  python3 - "$observed_at" "$duration" <<'PY'
from datetime import datetime, timedelta, timezone
import sys

try:
    observed = datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    duration = int(sys.argv[2])
    if duration <= 0:
        raise ValueError("duration must be positive")
except (ValueError, IndexError):
    raise SystemExit(2)

raise SystemExit(0 if datetime.now(timezone.utc) >= observed + timedelta(seconds=duration) else 1)
PY
}

acquire_lock() {
  # `create` is atomic. A concurrent runner cannot overwrite an existing
  # holder; only an expired Lease may be replaced, and then only with its
  # observed resourceVersion (optimistic concurrency).
  if lease_document | "$KUBECTL" -n "$CONTROL_NAMESPACE" create -f - >/dev/null 2>&1; then
    LOCK_HELD=1
    log ">> acquired gate Lease $LOCK_NAME for $RUN_ID"
    return 0
  fi

  local resource_version holder renew duration
  resource_version=$("$KUBECTL" -n "$CONTROL_NAMESPACE" get lease "$LOCK_NAME" \
    -o jsonpath='{.metadata.resourceVersion}' 2>/dev/null) || {
      fail "could not inspect existing gate Lease after an unsuccessful create"
      return 1
    }
  holder=$("$KUBECTL" -n "$CONTROL_NAMESPACE" get lease "$LOCK_NAME" \
    -o jsonpath='{.spec.holderIdentity}' 2>/dev/null) || return 1
  renew=$("$KUBECTL" -n "$CONTROL_NAMESPACE" get lease "$LOCK_NAME" \
    -o jsonpath='{.spec.renewTime}' 2>/dev/null) || return 1
  duration=$("$KUBECTL" -n "$CONTROL_NAMESPACE" get lease "$LOCK_NAME" \
    -o jsonpath='{.spec.leaseDurationSeconds}' 2>/dev/null) || return 1

  [[ -n "$resource_version" && -n "$holder" && -n "$renew" ]] || {
    fail "existing gate Lease is incomplete; refusing an unsafe takeover"
    return 1
  }
  if ! lease_is_expired "$renew" "$duration"; then
    fail "another gate run ($holder) still holds Lease $LOCK_NAME"
    return 1
  fi
  if lease_document "$resource_version" | "$KUBECTL" -n "$CONTROL_NAMESPACE" replace -f - >/dev/null; then
    LOCK_HELD=1
    log ">> took over expired gate Lease $LOCK_NAME from $holder"
    return 0
  fi
  fail "expired gate Lease changed while taking over; retry after its holder finishes"
}

cleanup_kubectl() {
  local remaining_seconds
  remaining_seconds=$((CLEANUP_DEADLINE_EPOCH - $(now_epoch)))
  (( remaining_seconds > 0 )) || {
    log "!! cleanup deadline (${CLEANUP_TIMEOUT_SECONDS}s) expired before verified cleanup completed"
    return 1
  }
  "$TIMEOUT_BIN" --foreground "${remaining_seconds}s" "$KUBECTL" "$@"
}

verify_absent() {
  local namespace="$1" kind="$2" name="$3"
  if cleanup_kubectl -n "$namespace" get "$kind" "$name" >/dev/null 2>&1; then
    log "!! cleanup verification: $kind/$name still exists in $namespace"
    return 1
  fi
  return 0
}

cleanup() {
  local cleanup_failed=0 leftovers
  CLEANUP_DEADLINE_EPOCH=$(( $(now_epoch) + CLEANUP_TIMEOUT_SECONDS ))
  log ">> verified cleanup deadline: ${CLEANUP_TIMEOUT_SECONDS}s"

  # Delete exact objects we created. Never sweep a selector from a different
  # run: an unrecognised object is evidence worth blocking on, not deleting.
  if [[ -n "$WORKFLOW_NAME" ]]; then
    log ">> cleaning workflow $WORKFLOW_NAME"
    cleanup_kubectl -n "$TARGET_NAMESPACE" delete workflow "$WORKFLOW_NAME" \
      --ignore-not-found --wait=true >/dev/null 2>&1 || cleanup_failed=1
    cleanup_kubectl -n "$TARGET_NAMESPACE" delete podchaos \
      -l "chaos-mesh.org/workflow=$WORKFLOW_NAME" --ignore-not-found --wait=true \
      >/dev/null 2>&1 || cleanup_failed=1
    verify_absent "$TARGET_NAMESPACE" workflow "$WORKFLOW_NAME" || cleanup_failed=1
    leftovers=$(cleanup_kubectl -n "$TARGET_NAMESPACE" get podchaos \
      -l "chaos-mesh.org/workflow=$WORKFLOW_NAME" -o name 2>/dev/null) || cleanup_failed=1
    [[ -z "${leftovers:-}" ]] || {
      log "!! cleanup verification: workflow-owned PodChaos still exists: $leftovers"
      cleanup_failed=1
    }
  fi

  if [[ -n "$LOADGEN_JOB" ]]; then
    log ">> cleaning loadgen Job $LOADGEN_JOB"
    cleanup_kubectl -n "$TARGET_NAMESPACE" delete job "$LOADGEN_JOB" \
      --ignore-not-found --wait=true >/dev/null 2>&1 || cleanup_failed=1
    verify_absent "$TARGET_NAMESPACE" job "$LOADGEN_JOB" || cleanup_failed=1
  fi

  if (( LOCK_HELD )); then
    cleanup_kubectl -n "$CONTROL_NAMESPACE" delete lease "$LOCK_NAME" \
      --ignore-not-found --wait=true >/dev/null 2>&1 || cleanup_failed=1
    verify_absent "$CONTROL_NAMESPACE" lease "$LOCK_NAME" || cleanup_failed=1
    LOCK_HELD=0
  fi

  return "$cleanup_failed"
}

on_exit() {
  local exit_code=$?
  trap - EXIT INT TERM
  if ! cleanup; then
    # A passing score with unverified cleanup is not a safe promotion verdict.
    exit_code=1
  fi
  exit "$exit_code"
}

trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ensure_no_other_gate_run() {
  local existing
  existing=$("$KUBECTL" -n "$TARGET_NAMESPACE" get workflow \
    -l "$GATE_SELECTOR" -o name 2>/dev/null) || {
      fail "could not list existing gate workflows"
      return 1
    }
  [[ -z "$existing" ]] || {
    fail "an earlier gate workflow still exists; inspect it before another fault run"
    return 1
  }
}

ensure_target_ready() {
  local endpoints
  endpoints=$("$KUBECTL" -n "$TARGET_NAMESPACE" get endpointslice \
    -l "kubernetes.io/service-name=$TARGET_SERVICE" \
    -o jsonpath='{range .items[*].endpoints[?(@.conditions.ready==true)]}{.addresses[0]}{"\\n"}{end}' \
    2>/dev/null) || {
      fail "could not inspect EndpointSlices for target Service $TARGET_SERVICE"
      return 1
    }
  [[ -n "${endpoints//[[:space:]]/}" ]] || {
    fail "target Service $TARGET_SERVICE has no ready endpoint; refusing to inject a vacuous fault"
    return 1
  }
}

create_workflow() {
  WORKFLOW_NAME=$("$KUBECTL" -n "$TARGET_NAMESPACE" create -f "$WORKFLOW_FILE" \
    -o jsonpath='{.metadata.name}') || {
      fail "could not create bounded Chaos Mesh workflow"
      return 1
    }
  [[ -n "$WORKFLOW_NAME" ]] || {
    fail "Chaos Mesh workflow create returned no name"
    return 1
  }
  "$KUBECTL" -n "$TARGET_NAMESPACE" label workflow "$WORKFLOW_NAME" \
    "resilience-gate.io/run-id=$RUN_ID" --overwrite >/dev/null || {
      fail "could not label gate workflow with its run identifier"
      return 1
    }
  # The Chaos Mesh generated name is the durable run identity visible in the
  # cluster, scorecards, and later evidence collection.
  SCORER_RUN_ID="$WORKFLOW_NAME"
  log ">> created bounded workflow $WORKFLOW_NAME"
}

create_loadgen() {
  LOADGEN_JOB="loadgen-$RUN_ID"
  "$KUBECTL" -n "$TARGET_NAMESPACE" create job --from="cronjob/$LOADGEN_CRONJOB" \
    "$LOADGEN_JOB" >/dev/null || {
      fail "could not create run-scoped loadgen Job"
      return 1
    }
  "$KUBECTL" -n "$TARGET_NAMESPACE" label job "$LOADGEN_JOB" \
    "resilience-gate.io/run-id=$RUN_ID" --overwrite >/dev/null || {
      fail "could not label loadgen Job with its run identifier"
      return 1
    }
  log ">> created loadgen Job $LOADGEN_JOB"
}

wait_for_loadgen_start() {
  local deadline status active failed
  deadline=$(( $(now_epoch) + LOADGEN_STARTUP_TIMEOUT_SECONDS ))
  while :; do
    status=$("$KUBECTL" -n "$TARGET_NAMESPACE" get job "$LOADGEN_JOB" \
      -o jsonpath='{.status.active}{" "}{.status.failed}' 2>/dev/null || true)
    read -r active failed <<<"${status:-0 0}"
    [[ "${active:-0}" =~ ^[1-9][0-9]*$ ]] && return 0
    if [[ "${failed:-0}" =~ ^[1-9][0-9]*$ ]]; then
      fail "loadgen Job failed before producing traffic"
      return 1
    fi
    if (( $(now_epoch) >= deadline )); then
      fail "loadgen did not start within ${LOADGEN_STARTUP_TIMEOUT_SECONDS}s"
      return 1
    fi
    "$SLEEP_BIN" "$POLL_INTERVAL_SECONDS"
  done
}

wait_for_workflow() {
  local deadline conditions
  deadline=$(( $(now_epoch) + WORKFLOW_TIMEOUT_SECONDS ))
  while :; do
    # Chaos Mesh removes WorkflowNodes and their child PodChaos resources as
    # the Workflow reaches a terminal state. Preserve each actual Apply event
    # while the Workflow is still running, so scorecards retain fault evidence.
    collect_injection_times || return 1
    conditions=$("$KUBECTL" -n "$TARGET_NAMESPACE" get workflow "$WORKFLOW_NAME" \
      -o jsonpath='{range .status.conditions[*]}{.type}={.status}{" "}{end}' \
      2>/dev/null || true)
    [[ "$conditions" == *"Accomplished=True"* ]] && return 0
    if [[ "$conditions" == *"Failed=True"* ]]; then
      fail "workflow reported failure before all recovery windows completed"
      return 1
    fi
    if (( $(now_epoch) >= deadline )); then
      fail "workflow did not complete within ${WORKFLOW_TIMEOUT_SECONDS}s"
      return 1
    fi
    "$SLEEP_BIN" "$POLL_INTERVAL_SECONDS"
  done
}

collect_injection_times() {
  local rows template_name api_group kind chaos_name
  local event_rows event_type event_operation event_at
  rows=$("$KUBECTL" -n "$TARGET_NAMESPACE" get workflownode \
    -l "chaos-mesh.org/workflow=$WORKFLOW_NAME" \
    -o jsonpath='{range .items[*]}{.spec.templateName}{"\t"}{.status.chaosResource.apiGroup}{"\t"}{.status.chaosResource.kind}{"\t"}{.status.chaosResource.name}{"\n"}{end}' \
    2>/dev/null) || {
      fail "could not retrieve workflow node chaos references"
      return 1
    }
  while IFS=$'\t' read -r template_name api_group kind chaos_name; do
    case "$template_name" in
      postgres|redis|signer) ;;
      *) continue ;;
    esac
    [[ "$api_group" == "chaos-mesh.org" && "$kind" == "PodChaos" && -n "$chaos_name" ]] || continue

    # A WorkflowNode's startTime is when its controller rendered the node,
    # not proof that Chaos Mesh changed a target. Score only from the earliest
    # successful Apply event on its exact typed child resource.
    event_rows=$("$KUBECTL" -n "$TARGET_NAMESPACE" get podchaos "$chaos_name" \
      -o jsonpath='{range .status.experiment.containerRecords[*]}{range .events[*]}{.type}{"\t"}{.operation}{"\t"}{.timestamp}{"\n"}{end}{end}' \
      2>/dev/null) || continue
    while IFS=$'\t' read -r event_type event_operation event_at; do
      [[ "$event_type" == "Succeeded" && "$event_operation" == "Apply" && -n "$event_at" ]] || continue
      if [[ -z "${INJECTED_AT[$template_name]:-}" || "$event_at" < "${INJECTED_AT[$template_name]}" ]]; then
        INJECTED_AT["$template_name"]="$event_at"
      fi
    done <<<"$event_rows"
  done <<<"$rows"
}

score_experiments() {
  local experiment scorer_name inject_at scorecard_path
  local score_failed=0
  mkdir -p "$SCORECARD_DIR" || return 1
  for experiment in "${EXPERIMENTS[@]}"; do
    scorer_name="${experiment}-pod-failure"
    inject_at="${INJECTED_AT[$experiment]:-}"
    if [[ -z "$inject_at" ]]; then
      log "!! workflow did not expose a successful Apply timestamp for $experiment"
      FAILED_EXPERIMENTS+=("$experiment")
      score_failed=1
      continue
    fi
    scorecard_path="$SCORECARD_DIR/$scorer_name.json"
    log ">> scoring $scorer_name from injection time $inject_at"
    local -a command=(
      python3 "$GATE_SCRIPTS_DIR/score_experiment.py" "$scorer_name"
      --inject-at "$inject_at"
      --duration 60
      --namespace "$TARGET_NAMESPACE"
      --release-revision "$RELEASE_REVISION"
      --release-digest "$RELEASE_DIGEST"
      --run-id "${SCORER_RUN_ID:-$RUN_ID}"
      --scorecard-path "$scorecard_path"
    )
    [[ -n "$PROM_URL" ]] && command+=(--prom "$PROM_URL")
    if ! "$TIMEOUT_BIN" --foreground "${SCORER_TIMEOUT_SECONDS}s" "${command[@]}"; then
      log "!! scorer $scorer_name exceeded its ${SCORER_TIMEOUT_SECONDS}s bound or returned a failure"
      FAILED_EXPERIMENTS+=("$experiment")
      score_failed=1
    fi
  done
  return "$score_failed"
}

annotate_verdict() {
  local verdict failed_csv workflow_start workflow_end
  verdict="$1"
  failed_csv=$(IFS=,; printf '%s' "${FAILED_EXPERIMENTS[*]}")
  workflow_start=$("$KUBECTL" -n "$TARGET_NAMESPACE" get workflow "$WORKFLOW_NAME" \
    -o jsonpath='{.status.startTime}' 2>/dev/null || true)
  workflow_end=$("$KUBECTL" -n "$TARGET_NAMESPACE" get workflow "$WORKFLOW_NAME" \
    -o jsonpath='{.status.endTime}' 2>/dev/null || true)
  # Annotation is diagnostic only. `annotate.py` self-skips when Grafana
  # credentials are unavailable and no annotation error can flip this verdict.
  # C086/C087 runner images do not yet carry the optional helper; that absence
  # is deliberately harmless until C088 adds it to the reviewed image.
  if [[ ! -r "$GATE_SCRIPTS_DIR/annotate.py" ]]; then
    log ">> Grafana annotation helper is unavailable; skipping non-fatally"
    return 0
  fi
  "$TIMEOUT_BIN" --foreground "${ANNOTATION_TIMEOUT_SECONDS}s" \
    python3 "$GATE_SCRIPTS_DIR/annotate.py" --verdict "$verdict" \
      --failed "$failed_csv" --start "$workflow_start" --end "$workflow_end" \
      --workflow "$WORKFLOW_NAME" || log "!! Grafana annotation failed non-fatally"
}

main() {
  local gate_failed=0
  validate_settings || return 1
  acquire_lock || return 1
  ensure_no_other_gate_run || return 1
  ensure_target_ready || return 1
  create_workflow || return 1
  create_loadgen || return 1
  wait_for_loadgen_start || return 1

  if ! wait_for_workflow; then
    FAILED_EXPERIMENTS+=("workflow")
    gate_failed=1
  fi
  collect_injection_times || gate_failed=1
  score_experiments || gate_failed=1

  if (( gate_failed )); then
    annotate_verdict fail
    log ">> GATE VERDICT: FAIL"
    return 1
  fi
  annotate_verdict pass
  log ">> GATE VERDICT: PASS"
  return 0
}

main "$@"
