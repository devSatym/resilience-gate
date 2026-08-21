"""Offline checks for the explicit-only manual loadgen runner."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "scripts" / "run-loadgen.sh"
RUNBOOK = REPOSITORY_ROOT / "docs" / "runbooks" / "load-testing.md"


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


def test_runner_requires_an_explicit_execute_boundary() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert 'mode="plan"' in source
    assert '[[ "$mode" == "execute" ]] || exit 0' in source
    assert "kubectl -n" in source
    assert "CronJob/$CRONJOB must be suspended" in source
    assert "--server-side --field-manager=resilience-gate-loadgen" in source
    assert "summary.json" in source


def test_runbook_marks_execution_as_testnet_only_and_explicit() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")
    assert "eip155:72344" in source
    assert "--plan" in source
    assert "--execute" in source
    assert "ordinary test" in source
    assert "pull-request validation" in source
    assert "never add wallet keys" in source.lower()
