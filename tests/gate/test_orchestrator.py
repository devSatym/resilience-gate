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


def test_loadgen_startup_timeout_cleans_the_new_run_without_scoring(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    env, calls_path = base_environment(
        tmp_path,
        f"""
args="$*"
if [[ "$args" == *" create -f -"* ]]; then cat >/dev/null; exit 0; fi
if [[ "$args" == *" get workflow -l resilience-gate.io/gate=chaos"* ]]; then exit 0; fi
if [[ "$args" == *" get endpointslice "* ]]; then echo 10.0.0.9; exit 0; fi
if [[ "$args" == *" create -f "*"workflow.yaml"* ]]; then echo chaos-gate-run-timeout; exit 0; fi
if [[ "$args" == *" label workflow "* || "$args" == *" label job "* ]]; then exit 0; fi
if [[ "$args" == *" create job --from=cronjob/loadgen "* ]]; then exit 0; fi
if [[ "$args" == *" get job loadgen-gate-test-2 "* ]]; then
  [[ -f {state}/job-deleted ]] && exit 1
  echo '0 0'; exit 0
fi
if [[ "$args" == *" delete workflow chaos-gate-run-timeout "* ]]; then touch {state}/workflow-deleted; exit 0; fi
if [[ "$args" == *" get workflow chaos-gate-run-timeout "* ]]; then [[ -f {state}/workflow-deleted ]] && exit 1; exit 99; fi
if [[ "$args" == *" delete podchaos "* || "$args" == *" get podchaos "* ]]; then exit 0; fi
if [[ "$args" == *" delete job loadgen-gate-test-2 "* ]]; then touch {state}/job-deleted; exit 0; fi
if [[ "$args" == *" delete lease chaos-gate-runner "* ]]; then touch {state}/released; exit 0; fi
if [[ "$args" == *" get lease chaos-gate-runner "* ]]; then [[ -f {state}/released ]] && exit 1; exit 0; fi
exit 99
""",
        LOADGEN_STARTUP_TIMEOUT_SECONDS="1",
        SLEEP_BIN="/bin/true",
    )

    result = run_orchestrator(env)

    assert result.returncode == 1
    assert "loadgen did not start within 1s" in result.stderr
    calls = calls_path.read_text(encoding="utf-8")
    assert "delete workflow chaos-gate-run-timeout" in calls
    assert "delete job loadgen-gate-test-2" in calls
    assert "get workflownode" not in calls
