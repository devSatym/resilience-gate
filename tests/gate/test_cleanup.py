"""Offline contracts for exact, verified chaos-run cleanup."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = REPO_ROOT / "kubernetes" / "chaos-experiments" / "orchestrate.sh"
RBAC_PATH = REPO_ROOT / "kubernetes" / "chaos-experiments" / "chaos-gate-rbac.yaml"
WORKFLOW_PATH = REPO_ROOT / "kubernetes" / "chaos-experiments" / "workflow.yaml"


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def fake_gate_environment(
    tmp_path: Path, *, workflow_nodes_disappear_on_completion: bool = False
) -> dict[str, str]:
    """Create a hermetic API simulation where scoring fails after a full run."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "workflow.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n", encoding="utf-8")
    (scripts / "score_experiment.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
    (scripts / "annotate.py").write_text("raise SystemExit(0)\n", encoding="utf-8")

    state = tmp_path / "state"
    state.mkdir()
    calls = tmp_path / "kubectl.calls"
    kubectl = tmp_path / "kubectl"
    completion_marker = (
        f"touch {state}/workflow-completed;"
        if workflow_nodes_disappear_on_completion
        else ""
    )
    node_visibility_guard = (
        f"[[ -f {state}/workflow-completed ]] && exit 0;"
        if workflow_nodes_disappear_on_completion
        else ""
    )
    write_executable(
        kubectl,
        f"""#!/usr/bin/env bash
set -u
printf '%s\\n' "$*" >> {calls}
args="$*"
if [[ "$args" == *" create -f -"* ]]; then cat >/dev/null; exit 0; fi
if [[ "$args" == *" get workflow -l resilience-gate.io/gate=chaos"* ]]; then exit 0; fi
if [[ "$args" == *" get endpointslice "* ]]; then echo 10.0.0.8; exit 0; fi
if [[ "$args" == *" create -f "*"workflow.yaml"* ]]; then echo chaos-gate-run-1; exit 0; fi
if [[ "$args" == *" label workflow "* || "$args" == *" label job "* ]]; then exit 0; fi
if [[ "$args" == *" create job --from=cronjob/loadgen "* ]]; then exit 0; fi
if [[ "$args" == *" get job loadgen-gate-test-1 "* ]]; then
  [[ -f {state}/job-deleted ]] && exit 1
  echo '1 0'; exit 0
fi
if [[ "$args" == *" get workflow chaos-gate-run-1 "* ]]; then
  [[ -f {state}/workflow-deleted ]] && exit 1
  if [[ "$args" == *"status.conditions"* ]]; then {completion_marker} echo 'Accomplished=True'; fi
  if [[ "$args" == *"status.startTime"* ]]; then echo '2026-10-01T12:00:00Z'; fi
  if [[ "$args" == *"status.endTime"* ]]; then echo '2026-10-01T12:08:00Z'; fi
  exit 0
fi
if [[ "$args" == *" get workflownode "* ]]; then
  {node_visibility_guard}
  printf 'postgres\\t2026-10-01T12:01:30Z\\nredis\\t2026-10-01T12:04:30Z\\nsigner\\t2026-10-01T12:06:30Z\\n'
  exit 0
fi
if [[ "$args" == *" delete workflow chaos-gate-run-1 "* ]]; then touch {state}/workflow-deleted; exit 0; fi
if [[ "$args" == *" delete podchaos "* ]]; then exit 0; fi
if [[ "$args" == *" get podchaos "* ]]; then exit 0; fi
if [[ "$args" == *" delete job loadgen-gate-test-1 "* ]]; then touch {state}/job-deleted; exit 0; fi
if [[ "$args" == *" delete lease chaos-gate-runner "* ]]; then touch {state}/lease-deleted; exit 0; fi
if [[ "$args" == *" get lease chaos-gate-runner "* ]]; then
  [[ -f {state}/lease-deleted ]] && exit 1
  exit 1
fi
exit 0
""",
    )

    return os.environ | {
        "KUBECTL": str(kubectl),
        "GATE_SCRIPTS_DIR": str(scripts),
        "WORKFLOW_FILE": str(scripts / "workflow.yaml"),
        "SCORECARD_DIR": str(tmp_path / "results"),
        "RUN_ID": "gate-test-1",
        "RELEASE_REVISION": "abc1234",
        "RELEASE_DIGEST": "sha256:" + "a" * 64,
        "POLL_INTERVAL_SECONDS": "1",
    }


def test_failed_score_cleans_only_its_exact_objects_and_verifies_absence(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(ORCHESTRATOR)],
        env=fake_gate_environment(tmp_path),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    calls = (tmp_path / "kubectl.calls").read_text(encoding="utf-8")
    assert "delete workflow chaos-gate-run-1 --ignore-not-found --wait=true" in calls
    assert "delete podchaos -l chaos-mesh.org/workflow=chaos-gate-run-1" in calls
    assert "delete job loadgen-gate-test-1 --ignore-not-found --wait=true" in calls
    assert "delete lease chaos-gate-runner --ignore-not-found --wait=true" in calls
    assert "delete workflow -l" not in calls
    assert "delete job -l" not in calls


def test_pre_annotation_runner_still_preserves_the_gate_verdict(tmp_path: Path) -> None:
    env = fake_gate_environment(tmp_path)
    (tmp_path / "scripts" / "annotate.py").unlink()

    result = subprocess.run(
        ["bash", str(ORCHESTRATOR)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    # C088 merely makes annotations available; it cannot turn this score
    # failure into success or make an earlier runner unusable.
    assert result.returncode == 1
    assert "annotation helper is unavailable; skipping non-fatally" in result.stderr


def test_collects_workflow_node_timestamps_before_terminal_gc(tmp_path: Path) -> None:
    """Scorecards retain fault timestamps even after Chaos Mesh removes nodes."""
    result = subprocess.run(
        ["bash", str(ORCHESTRATOR)],
        env=fake_gate_environment(tmp_path, workflow_nodes_disappear_on_completion=True),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    # The fixture's scorer intentionally fails, but a missing timestamp must
    # not be the cause after the Workflow transitions to terminal.
    assert result.returncode == 1
    assert "workflow did not expose a start time" not in result.stderr
    calls = (tmp_path / "kubectl.calls").read_text(encoding="utf-8")
    assert calls.count("get workflownode") >= 2


def test_lock_and_target_permissions_match_the_orchestrator_contract() -> None:
    documents = list(yaml.safe_load_all(RBAC_PATH.read_text(encoding="utf-8")))
    roles = {document["metadata"]["name"]: document for document in documents if document["kind"] == "Role"}

    lock_rules = roles["chaos-gate-lock"]["rules"]
    assert lock_rules == [
        {
            "apiGroups": ["coordination.k8s.io"],
            "resources": ["leases"],
            "verbs": ["get", "create", "update", "delete"],
        }
    ]
    runner_rules = roles["chaos-gate-runner"]["rules"]
    assert any(
        rule["resources"] == ["endpointslices"]
        and rule["apiGroups"] == ["discovery.k8s.io"]
        and rule["verbs"] == ["get", "list"]
        for rule in runner_rules
    )
    assert any(
        rule["resources"] == ["workflows"] and "patch" in rule["verbs"]
        for rule in runner_rules
    )
    assert any(
        rule["resources"] == ["jobs"] and "patch" in rule["verbs"]
        for rule in runner_rules
    )


def test_cleanup_windows_keep_the_workflow_within_its_hard_deadline() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    templates = {template["name"]: template for template in workflow["spec"]["templates"]}

    assert templates["gate-serial"]["deadline"] == "660s"
    assert templates["postgres"]["deadline"] == "60s"
    assert templates["redis"]["deadline"] == "60s"
    assert templates["signer"]["deadline"] == "60s"
    assert templates["postgres-recovery"]["deadline"] == "120s"
    assert templates["redis-recovery"]["deadline"] == "60s"
    assert templates["signer-recovery"]["deadline"] == "60s"


def test_full_gate_budget_bounds_scoring_and_keeps_cleanup_ahead_of_lease_takeover() -> None:
    """The Job cannot be killed before exact-object cleanup can run."""
    source = ORCHESTRATOR.read_text(encoding="utf-8")
    analysis_path = REPO_ROOT / "kubernetes" / "kargo" / "analysistemplate.yaml"
    documents = list(yaml.safe_load_all(analysis_path.read_text(encoding="utf-8")))
    gate = next(document for document in documents if document["metadata"]["name"] == "chaos-gate")
    job = gate["spec"]["metrics"][0]["provider"]["job"]["spec"]
    pod = job["template"]["spec"]

    # One scorer can make at most six 15-second Prometheus requests. The
    # runner gives each of the three scorers 105 seconds, then reserves time
    # for non-fatal annotation and verified cleanup.
    startup = 90
    workflow = 660
    scorer_count = 3
    scorer_timeout = 105
    annotation = 15
    cleanup = 120
    reserve = 60
    expected_minimum = startup + workflow + scorer_count * scorer_timeout + annotation + cleanup + reserve

    assert expected_minimum == 1260
    assert job["activeDeadlineSeconds"] == 1320
    assert job["activeDeadlineSeconds"] >= expected_minimum
    assert pod["terminationGracePeriodSeconds"] >= cleanup
    # Lease expiry happens only after the Job deadline plus more than the
    # maximum graceful-cleanup window, preventing another run from taking over
    # during cleanup.
    assert 1470 > job["activeDeadlineSeconds"] + pod["terminationGracePeriodSeconds"]
    assert 'readonly SCORER_TIMEOUT_SECONDS="${SCORER_TIMEOUT_SECONDS:-105}"' in source
    assert 'readonly CLEANUP_TIMEOUT_SECONDS="${CLEANUP_TIMEOUT_SECONDS:-120}"' in source
    assert 'readonly GATE_JOB_DEADLINE_SECONDS="${GATE_JOB_DEADLINE_SECONDS:-1320}"' in source
    assert 'readonly LOCK_DURATION_SECONDS="${LOCK_DURATION_SECONDS:-1470}"' in source
    assert '"$TIMEOUT_BIN" --foreground "${SCORER_TIMEOUT_SECONDS}s"' in source
    assert "cleanup_kubectl()" in source


def test_undersized_gate_budget_fails_before_the_runner_acquires_a_lease(tmp_path: Path) -> None:
    env = fake_gate_environment(tmp_path) | {
        "GATE_JOB_DEADLINE_SECONDS": "1259",
    }

    result = subprocess.run(
        ["bash", str(ORCHESTRATOR)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert "cannot cover startup, workflow, scoring, annotation, and cleanup" in result.stderr
    assert not (tmp_path / "kubectl.calls").exists()
