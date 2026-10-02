"""Hermetic process-level tests for gate startup and concurrency boundaries."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = REPO_ROOT / "kubernetes" / "chaos-experiments" / "orchestrate.sh"


def executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def base_environment(tmp_path: Path, kubectl_body: str, **overrides: str) -> tuple[dict[str, str], Path]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "workflow.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n", encoding="utf-8")
    (scripts / "score_experiment.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (scripts / "annotate.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    calls = tmp_path / "kubectl.calls"
    kubectl = tmp_path / "kubectl"
    executable(
        kubectl,
        "#!/usr/bin/env bash\nset -u\nprintf '%s\\n' \"$*\" >> \"$CALLS\"\n" + kubectl_body,
    )
    env = os.environ | {
        "KUBECTL": str(kubectl),
        "CALLS": str(calls),
        "GATE_SCRIPTS_DIR": str(scripts),
        "WORKFLOW_FILE": str(scripts / "workflow.yaml"),
        "SCORECARD_DIR": str(tmp_path / "results"),
        "RUN_ID": "gate-test-2",
        "RELEASE_REVISION": "abc1234",
        "RELEASE_DIGEST": "sha256:" + "b" * 64,
        "POLL_INTERVAL_SECONDS": "1",
    }
    env.update(overrides)
    return env, calls


def run_orchestrator(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ORCHESTRATOR)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_unexpired_lease_blocks_concurrent_runs_before_any_fault_or_loadgen(tmp_path: Path) -> None:
    env, calls_path = base_environment(
        tmp_path,
        """
args="$*"
if [[ "$args" == *" create -f -"* ]]; then cat >/dev/null; exit 1; fi
if [[ "$args" == *"get lease chaos-gate-runner"*"resourceVersion"* ]]; then echo 7; exit 0; fi
if [[ "$args" == *"get lease chaos-gate-runner"*"holderIdentity"* ]]; then echo another-run; exit 0; fi
if [[ "$args" == *"get lease chaos-gate-runner"*"renewTime"* ]]; then echo 2999-01-01T00:00:00Z; exit 0; fi
if [[ "$args" == *"get lease chaos-gate-runner"*"leaseDurationSeconds"* ]]; then echo 720; exit 0; fi
exit 99
""",
    )

    result = run_orchestrator(env)

    assert result.returncode == 1
    assert "another gate run" in result.stderr
    calls = calls_path.read_text(encoding="utf-8")
    assert "get endpointslice" not in calls
    assert "create job" not in calls
    assert "workflow.yaml" not in calls


def test_no_ready_target_fails_before_workflow_or_loadgen_creation(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    env, calls_path = base_environment(
        tmp_path,
        f"""
args="$*"
if [[ "$args" == *" create -f -"* ]]; then cat >/dev/null; exit 0; fi
if [[ "$args" == *" get workflow -l resilience-gate.io/gate=chaos"* ]]; then exit 0; fi
if [[ "$args" == *" get endpointslice "* ]]; then exit 0; fi
if [[ "$args" == *" delete lease chaos-gate-runner "* ]]; then touch {state}/released; exit 0; fi
if [[ "$args" == *" get lease chaos-gate-runner "* ]]; then [[ -f {state}/released ]] && exit 1; exit 0; fi
exit 99
""",
    )

    result = run_orchestrator(env)

    assert result.returncode == 1
    assert "no ready endpoint" in result.stderr
    calls = calls_path.read_text(encoding="utf-8")
    assert "create job" not in calls
    assert "workflow.yaml" not in calls
    assert "delete lease chaos-gate-runner" in calls


def test_gate_lease_uses_kubernetes_microtime_timestamps(tmp_path: Path) -> None:
    """The API rejects seconds-only values for Lease MicroTime fields."""
    state = tmp_path / "state"
    state.mkdir()
    env, calls_path = base_environment(
        tmp_path,
        f"""
args="$*"
if [[ "$args" == *" create -f -"* ]]; then
  manifest="$(cat)"
  printf '%s\\n' "$manifest" | grep -Eq '^  acquireTime: [0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}\\.000000Z$' || exit 1
  printf '%s\\n' "$manifest" | grep -Eq '^  renewTime: [0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}\\.000000Z$' || exit 1
  exit 0
fi
if [[ "$args" == *" get workflow -l resilience-gate.io/gate=chaos"* ]]; then exit 0; fi
if [[ "$args" == *" get endpointslice "* ]]; then exit 0; fi
if [[ "$args" == *" delete lease chaos-gate-runner "* ]]; then touch {state}/released; exit 0; fi
if [[ "$args" == *" get lease chaos-gate-runner "* ]]; then [[ -f {state}/released ]] && exit 1; exit 0; fi
exit 99
""",
    )

    result = run_orchestrator(env)

    assert result.returncode == 1
    assert "no ready endpoint" in result.stderr
    assert "could not inspect existing gate Lease" not in result.stderr
    calls = calls_path.read_text(encoding="utf-8")
    assert "create -f -" in calls
    assert "get endpointslice" in calls


def loadgen_preflight_environment(
    tmp_path: Path, *, job_status: str, log_output: str = "k6 is still warming up"
) -> tuple[dict[str, str], Path]:
    """Simulate a run whose loadgen cannot prove paid end-to-end traffic."""
    state = tmp_path / "state"
    state.mkdir()
    env, calls_path = base_environment(
        tmp_path,
        f"""
args="$*"
if [[ "$args" == *" create -f -"* ]]; then cat >/dev/null; exit 0; fi
if [[ "$args" == *" get workflow -l resilience-gate.io/gate=chaos"* ]]; then exit 0; fi
if [[ "$args" == *" get endpointslice "* ]]; then echo 10.0.0.9; exit 0; fi
if [[ "$args" == *" create job --from=cronjob/loadgen "* ]]; then exit 0; fi
if [[ "$args" == *" label job "* ]]; then exit 0; fi
if [[ "$args" == *" get job loadgen-gate-test-2 "* ]]; then
  [[ -f {state}/job-deleted ]] && exit 1
  echo '{job_status}'; exit 0
fi
if [[ "$args" == *" logs job/loadgen-gate-test-2 "* ]]; then
  printf '%s\\n' '{log_output}'; exit 0
fi
if [[ "$args" == *" create -f "*"workflow.yaml"* ]]; then touch {state}/workflow-created; exit 0; fi
if [[ "$args" == *" delete workflow "* || "$args" == *" delete podchaos "* ]]; then touch {state}/workflow-deleted; exit 0; fi
if [[ "$args" == *" delete job loadgen-gate-test-2 "* ]]; then touch {state}/job-deleted; exit 0; fi
if [[ "$args" == *" delete lease chaos-gate-runner "* ]]; then touch {state}/released; exit 0; fi
if [[ "$args" == *" get lease chaos-gate-runner "* ]]; then [[ -f {state}/released ]] && exit 1; exit 0; fi
exit 99
""",
        LOADGEN_STARTUP_TIMEOUT_SECONDS="1",
        SLEEP_BIN="/bin/true",
    )
    return env, calls_path


def assert_no_chaos_workflow_was_touched(calls: str) -> None:
    assert "workflow.yaml" not in calls
    assert "delete workflow " not in calls
    assert "delete podchaos " not in calls


def test_loadgen_startup_probes_recompute_remaining_time_before_each_api_or_log_call() -> None:
    source = ORCHESTRATOR.read_text(encoding="utf-8")
    helper_start = source.index("loadgen_startup_probe_timeout()")
    helper_end = source.index("\n}\n\nwait_for_loadgen_traffic", helper_start)
    helper = source[helper_start:helper_end]
    wait_start = source.index("wait_for_loadgen_traffic()")
    wait_end = source.index("\n}\n\nensure_loadgen_remains_active", wait_start)
    wait = source[wait_start:wait_end]

    assert "remaining_seconds=$(( deadline - $(now_epoch) ))" in helper
    # Initial status, exact-Job log, and post-marker status each receive a
    # freshly recomputed bounded allowance rather than a stale 5-second one.
    assert wait.count('probe_timeout=$(loadgen_startup_probe_timeout "$deadline")') == 3


def test_active_loadgen_without_paid_marker_cleans_the_new_run_without_scoring(tmp_path: Path) -> None:
    env, calls_path = loadgen_preflight_environment(tmp_path, job_status="1 0 0")

    result = run_orchestrator(env)

    assert result.returncode == 1
    assert "loadgen did not prove paid traffic within 1s" in result.stderr
    calls = calls_path.read_text(encoding="utf-8")
    assert "logs job/loadgen-gate-test-2" in calls
    assert_no_chaos_workflow_was_touched(calls)
    assert "delete job loadgen-gate-test-2" in calls
    assert "get workflownode" not in calls


def test_completed_loadgen_before_paid_marker_never_creates_or_deletes_a_workflow(tmp_path: Path) -> None:
    env, calls_path = loadgen_preflight_environment(tmp_path, job_status="0 1 0")

    result = run_orchestrator(env)

    assert result.returncode == 1
    assert "loadgen Job completed before proving paid traffic" in result.stderr
    calls = calls_path.read_text(encoding="utf-8")
    assert "logs job/loadgen-gate-test-2" not in calls
    assert_no_chaos_workflow_was_touched(calls)
    assert "delete job loadgen-gate-test-2" in calls


def test_failed_loadgen_before_paid_marker_never_creates_or_deletes_a_workflow(tmp_path: Path) -> None:
    env, calls_path = loadgen_preflight_environment(tmp_path, job_status="0 0 1")

    result = run_orchestrator(env)

    assert result.returncode == 1
    assert "loadgen Job failed before proving paid traffic" in result.stderr
    calls = calls_path.read_text(encoding="utf-8")
    assert "logs job/loadgen-gate-test-2" not in calls
    assert_no_chaos_workflow_was_touched(calls)
    assert "delete job loadgen-gate-test-2" in calls


def test_terminal_loadgen_failure_during_workflow_fails_closed_and_cleans_its_workflow(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    env, calls_path = base_environment(
        tmp_path,
        f"""
args="$*"
if [[ "$args" == *" create -f -"* ]]; then cat >/dev/null; exit 0; fi
if [[ "$args" == *" get workflow -l resilience-gate.io/gate=chaos"* ]]; then exit 0; fi
if [[ "$args" == *" get endpointslice "* ]]; then echo 10.0.0.9; exit 0; fi
if [[ "$args" == *" create job --from=cronjob/loadgen "* ]]; then exit 0; fi
if [[ "$args" == *" label job "* || "$args" == *" label workflow "* ]]; then exit 0; fi
if [[ "$args" == *" get job loadgen-gate-test-2 "* ]]; then
  [[ -f {state}/job-deleted ]] && exit 1
  [[ -f {state}/workflow-created ]] && echo '0 0 1' || echo '1 0 0'
  exit 0
fi
if [[ "$args" == *" logs job/loadgen-gate-test-2 "* ]]; then
  printf '%s\\n' 'RESILIENCE_GATE_PAID_TRAFFIC_READY v1'; exit 0
fi
if [[ "$args" == *" create -f "*"workflow.yaml"* ]]; then
  touch {state}/workflow-created; echo chaos-gate-run-monitor; exit 0
fi
if [[ "$args" == *" get workflownode "* ]]; then exit 0; fi
if [[ "$args" == *" get workflow chaos-gate-run-monitor "* ]]; then
  [[ -f {state}/workflow-deleted ]] && exit 1
  [[ "$args" == *"status.conditions"* ]] && echo 'Running=True'
  exit 0
fi
if [[ "$args" == *" delete workflow chaos-gate-run-monitor "* ]]; then touch {state}/workflow-deleted; exit 0; fi
if [[ "$args" == *" delete podchaos "* || "$args" == *" get podchaos "* ]]; then exit 0; fi
if [[ "$args" == *" delete job loadgen-gate-test-2 "* ]]; then touch {state}/job-deleted; exit 0; fi
if [[ "$args" == *" delete lease chaos-gate-runner "* ]]; then touch {state}/released; exit 0; fi
if [[ "$args" == *" get lease chaos-gate-runner "* ]]; then [[ -f {state}/released ]] && exit 1; exit 0; fi
exit 99
""",
    )

    result = run_orchestrator(env)

    assert result.returncode == 1
    assert "loadgen Job failed after paid traffic was verified" in result.stderr
    calls = calls_path.read_text(encoding="utf-8")
    assert calls.index("workflow.yaml") > calls.index("logs job/loadgen-gate-test-2")
    assert "delete workflow chaos-gate-run-monitor" in calls
    assert "delete job loadgen-gate-test-2" in calls


def terminal_workflow_success_environment(
    tmp_path: Path, *, terminal_job_status: str
) -> tuple[dict[str, str], Path, Path]:
    """Return a terminal Workflow whose loadgen dies at the final observation."""
    state = tmp_path / "state"
    state.mkdir()
    env, calls_path = base_environment(
        tmp_path,
        f"""
args="$*"
if [[ "$args" == *" create -f -"* ]]; then cat >/dev/null; exit 0; fi
if [[ "$args" == *" get workflow -l resilience-gate.io/gate=chaos"* ]]; then exit 0; fi
if [[ "$args" == *" get endpointslice "* ]]; then echo 10.0.0.9; exit 0; fi
if [[ "$args" == *" create job --from=cronjob/loadgen "* ]]; then exit 0; fi
if [[ "$args" == *" label job "* || "$args" == *" label workflow "* ]]; then exit 0; fi
if [[ "$args" == *" get job loadgen-gate-test-2 "* ]]; then
  [[ -f {state}/job-deleted ]] && exit 1
  [[ -f {state}/terminal-workflow-observed ]] && echo '{terminal_job_status}' || echo '1 0 0'
  exit 0
fi
if [[ "$args" == *" logs job/loadgen-gate-test-2 "* ]]; then
  printf '%s\\n' 'RESILIENCE_GATE_PAID_TRAFFIC_READY v1'; exit 0
fi
if [[ "$args" == *" create -f "*"workflow.yaml"* ]]; then
  echo chaos-gate-run-terminal; exit 0
fi
if [[ "$args" == *" get workflownode "* ]]; then exit 0; fi
if [[ "$args" == *" get workflow chaos-gate-run-terminal "* ]]; then
  [[ -f {state}/workflow-deleted ]] && exit 1
  if [[ "$args" == *"status.conditions"* ]]; then
    touch {state}/terminal-workflow-observed
    echo 'Accomplished=True'
  fi
  exit 0
fi
if [[ "$args" == *" delete workflow chaos-gate-run-terminal "* ]]; then touch {state}/workflow-deleted; exit 0; fi
if [[ "$args" == *" delete podchaos "* || "$args" == *" get podchaos "* ]]; then exit 0; fi
if [[ "$args" == *" delete job loadgen-gate-test-2 "* ]]; then touch {state}/job-deleted; exit 0; fi
if [[ "$args" == *" delete lease chaos-gate-runner "* ]]; then touch {state}/released; exit 0; fi
if [[ "$args" == *" get lease chaos-gate-runner "* ]]; then [[ -f {state}/released ]] && exit 1; exit 0; fi
exit 99
""",
    )
    return env, calls_path, state


def assert_terminal_workflow_loadgen_failure(
    tmp_path: Path, *, terminal_job_status: str, expected_error: str
) -> None:
    """Assert a terminal Workflow does not bypass the final Job observation."""
    env, calls_path, state = terminal_workflow_success_environment(
        tmp_path, terminal_job_status=terminal_job_status
    )

    result = run_orchestrator(env)

    assert result.returncode == 1
    assert expected_error in result.stderr
    assert (state / "terminal-workflow-observed").is_file()
    calls = calls_path.read_text(encoding="utf-8")
    assert "delete workflow chaos-gate-run-terminal" in calls
    assert "delete job loadgen-gate-test-2" in calls


def test_terminal_workflow_success_still_fails_if_loadgen_has_completed(tmp_path: Path) -> None:
    assert_terminal_workflow_loadgen_failure(
        tmp_path,
        terminal_job_status="0 1 0",
        expected_error="loadgen Job completed before the chaos workflow finished",
    )


def test_terminal_workflow_success_still_fails_if_loadgen_has_failed(tmp_path: Path) -> None:
    assert_terminal_workflow_loadgen_failure(
        tmp_path,
        terminal_job_status="0 0 1",
        expected_error="loadgen Job failed after paid traffic was verified",
    )
