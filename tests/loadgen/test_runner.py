"""Offline checks for the explicit-only manual loadgen runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "scripts" / "run-loadgen.sh"
RUNBOOK = REPOSITORY_ROOT / "docs" / "runbooks" / "load-testing.md"
LOADGEN_SCRIPT = REPOSITORY_ROOT / "kubernetes" / "jobs" / "scripts" / "loadgen.js"


def runner(*arguments: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if environment:
        env.update(environment)
    return subprocess.run(
        ("bash", str(RUNNER), *arguments),
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        env=env,
        text=True,
    )


def test_runner_shell_is_valid() -> None:
    result = subprocess.run(("bash", "-n", str(RUNNER)), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_default_plan_never_invokes_kubectl(tmp_path: Path) -> None:
    fake_kubectl = tmp_path / "kubectl"
    fake_kubectl.write_text("#!/usr/bin/env bash\necho kubectl-was-called >&2\nexit 99\n")
    fake_kubectl.chmod(0o755)
    result = runner(environment={"PATH": f"{tmp_path}:{os.environ['PATH']}"})

    assert result.returncode == 0, result.stderr
    assert "no cluster call has been made" in result.stdout
    assert "kubectl-was-called" not in result.stderr


def test_baseline_plan_is_bounded_unpaid_traffic_to_development(tmp_path: Path) -> None:
    fake_kubectl = tmp_path / "kubectl"
    fake_kubectl.write_text("#!/usr/bin/env bash\necho kubectl-was-called >&2\nexit 99\n")
    fake_kubectl.chmod(0o755)

    result = runner("--scenario", "baseline", environment={"PATH": f"{tmp_path}:{os.environ['PATH']}"})

    assert result.returncode == 0, result.stderr
    assert "scenario:          baseline" in result.stdout
    assert "source namespace:  url-shortener-staging" in result.stdout
    assert "target namespace:  url-shortener-dev" in result.stdout
    assert "duration:          90s" in result.stdout
    assert "virtual users:     1" in result.stdout
    assert "traffic mode:      unpaid-baseline (GET / only; no signer or payment calls)" in result.stdout
    assert "kubectl-was-called" not in result.stderr


def test_invalid_runner_inputs_fail_before_cluster_access(tmp_path: Path) -> None:
    fake_kubectl = tmp_path / "kubectl"
    fake_kubectl.write_text("#!/usr/bin/env bash\necho kubectl-was-called >&2\nexit 99\n")
    fake_kubectl.chmod(0o755)
    result = runner(
        "--execute",
        "--profile",
        "unbounded",
        environment={"PATH": f"{tmp_path}:{os.environ['PATH']}"},
    )

    assert result.returncode == 2
    assert "closed-loop or arrival-rate" in result.stderr
    assert "kubectl-was-called" not in result.stderr


def test_baseline_bounds_fail_before_cluster_access(tmp_path: Path) -> None:
    fake_kubectl = tmp_path / "kubectl"
    fake_kubectl.write_text("#!/usr/bin/env bash\necho kubectl-was-called >&2\nexit 99\n")
    fake_kubectl.chmod(0o755)

    duration = runner(
        "--execute",
        "--scenario",
        "baseline",
        "--duration",
        "91s",
        environment={"PATH": f"{tmp_path}:{os.environ['PATH']}"},
    )
    vus = runner(
        "--execute",
        "--scenario",
        "baseline",
        "--vus",
        "2",
        environment={"PATH": f"{tmp_path}:{os.environ['PATH']}"},
    )

    assert duration.returncode == 2
    assert "duration must be at most 90s" in duration.stderr
    assert vus.returncode == 2
    assert "requires exactly one virtual user" in vus.stderr
    assert "kubectl-was-called" not in duration.stderr
    assert "kubectl-was-called" not in vus.stderr


def test_baseline_execution_recovers_safe_artifacts_and_exactly_cleans_its_job(tmp_path: Path) -> None:
    fake_kubectl = tmp_path / "kubectl"
    calls = tmp_path / "kubectl-calls.log"
    fake_kubectl.write_text(
        """#!/usr/bin/env bash
set -eu
printf 'kubectl %s\\n' "$*" >> "$KUBECTL_CALLS"
args="$*"
if [[ "$args" == "config current-context" ]]; then
  printf 'gke_test_project_zone_cluster\\n'
  exit 0
fi
if [[ "$args" == *"get cronjob loadgen -o jsonpath={.spec.suspend}"* ]]; then
  printf 'true'
  exit 0
fi
if [[ "$args" == *"get job baseline-manual-"* ]]; then
  exit 1
fi
if [[ "$args" == *"wait --for=condition=available deployment/url-shortener-dev"* ]]; then
  exit 0
fi
if [[ "$args" == *"wait --for=condition=complete job/baseline-manual-"* ]]; then
  exit 0
fi
if [[ "$args" == *"create job baseline-manual-"* ]]; then
  printf 'apiVersion: batch/v1\\nkind: Job\\nmetadata:\\n  name: baseline\\n'
  exit 0
fi
if [[ "$args" == *"set env --local -f - -o yaml"* ]]; then
  cat
  exit 0
fi
if [[ "$args" == *"apply --server-side --field-manager=resilience-gate-loadgen -f -"* ]]; then
  cat >/dev/null
  exit 0
fi
if [[ "$args" == *"get pod -l job-name=baseline-manual-"* ]]; then
  printf 'baseline-pod\\n'
  exit 0
fi
if [[ "$args" == *"get pod baseline-pod -o json"* ]]; then
  printf '%s\n' '{"status":{"startTime":"2026-10-02T00:00:00Z","containerStatuses":[{"name":"k6","state":{"terminated":{"finishedAt":"2026-10-02T00:01:30Z"}}}]}}'
  exit 0
fi
if [[ "$args" == *"logs pod/baseline-pod -c k6 --tail=200"* ]]; then
  printf '%s\\n' 'RESILIENCE_GATE_K6_SUMMARY {"schema_version":"resilience-gate.loadgen-summary/v1","traffic_mode":"unpaid-baseline","metrics":{"http_reqs":{"type":"counter","values":{"count":45},"thresholds":{}}}}'
  exit 0
fi
if [[ "$args" == *"delete job baseline-manual-"* ]]; then
  exit 0
fi
if [[ "$args" == *"patch --local -f - --type=merge"* ]]; then
  cat
  exit 0
fi
printf 'unexpected kubectl call: %s\\n' "$args" >&2
exit 99
""",
        encoding="utf-8",
    )
    fake_kubectl.chmod(0o755)
    artifact_dir = tmp_path / "artifacts"

    result = runner(
        "--execute",
        "--scenario",
        "baseline",
        "--artifact-dir",
        str(artifact_dir),
        environment={
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "KUBECTL_CALLS": str(calls),
        },
    )

    assert result.returncode == 0, result.stderr
    summaries = list(artifact_dir.glob("baseline-manual-*-summary.json"))
    records = list(artifact_dir.glob("baseline-manual-*-run.json"))
    assert len(summaries) == 1
    assert len(records) == 1
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary == {
        "schema_version": "resilience-gate.loadgen-summary/v1",
        "traffic_mode": "unpaid-baseline",
        "metrics": {
            "http_reqs": {
                "type": "counter",
                "values": {"count": 45},
                "thresholds": {},
            }
        },
    }
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["scenario"] == "baseline"
    assert record["source"]["namespace"] == "url-shortener-staging"
    assert record["target"]["namespace"] == "url-shortener-dev"
    assert record["target"]["traffic"] == "unpaid GET / only"
    assert record["summary_capture"] == "pod-log-sentinel"
    assert record["observation"] == {
        "started_at": "2026-10-02T00:00:00Z",
        "ended_at": "2026-10-02T00:01:30Z",
        "configured_duration_seconds": 90,
        "job_active_deadline_seconds": 150,
    }
    assert record["cleanup"]["strategy"] == "exact-job-delete"
    assert record["cleanup"]["verified_absent"] is True

    recorded = calls.read_text(encoding="utf-8")
    assert "-n url-shortener-dev wait --for=condition=available deployment/url-shortener-dev" in recorded
    assert "BASE_URL=http://url-shortener-dev.url-shortener-dev.svc.cluster.local" in recorded
    assert "PAYMENT_ENABLED=false" in recorded
    assert "TRAFFIC_MODE=unpaid-baseline" in recorded
    assert '\"activeDeadlineSeconds\":150' in recorded
    assert "logs pod/baseline-pod -c k6 --tail=200" in recorded
    assert " cp -c k6 " not in recorded
    assert "radius-signer" not in recorded
    assert "externalsecret" not in recorded
    assert "delete job baseline-manual-" in recorded
    cleanup_delete = recorded.index("delete job baseline-manual-")
    assert "get job baseline-manual-" in recorded[cleanup_delete:]


def test_runner_requires_an_explicit_execute_boundary() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert 'mode="plan"' in source
    assert '[[ "$mode" == "execute" ]] || exit 0' in source
    assert "kubectl -n" in source
    assert "CronJob/$CRONJOB must be suspended" in source
    assert "--server-side --field-manager=resilience-gate-loadgen" in source
    assert "summary.json" in source


def test_baseline_mode_is_get_only_and_rejects_payment_enabled() -> None:
    source = LOADGEN_SCRIPT.read_text(encoding="utf-8")
    baseline_flow = source.split("export function baselineFlow()", 1)[1].split(
        "export function paymentFlow()", 1
    )[0]

    assert "TRAFFIC_MODE = environment('TRAFFIC_MODE', 'paid')" in source
    assert "PAYMENT_ENABLED must be false for unpaid-baseline traffic" in source
    assert "BASE_URL must be ${DEV_BASELINE_URL} for unpaid-baseline traffic" in source
    assert "http.get(`${appUrl}/`" in baseline_flow
    assert "http.post" not in baseline_flow
    assert "/shorten" not in baseline_flow
    assert "baseline_get_success_rate" in source
    assert "baseline_5xx_rate" in source


def test_runbook_marks_execution_as_testnet_only_and_explicit() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")
    assert "eip155:72344" in source
    assert "--plan" in source
    assert "--execute" in source
    assert "ordinary test" in source
    assert "pull-request validation" in source
    assert "never add wallet keys" in source.lower()
