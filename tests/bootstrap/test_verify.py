"""Hermetic safety contracts for the read-only platform verifier."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY = REPO_ROOT / "platform_setup_scripts" / "07-verify.sh"
EXPECTED_CONTEXT = "gke_resilience-gate-123_us-central1-a_resilience-gate"


def write_executable(path: Path, source: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + source + "\n", encoding="utf-8")
    path.chmod(0o755)


def write_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                'PROJECT_ID="resilience-gate-123"',
                'GITHUB_REPO="example/resilience-gate"',
                'REGION="us-central1"',
                'ZONE="us-central1-a"',
                'CLUSTER_NAME="resilience-gate"',
                'GAR_REPO="resilience-gate"',
                'TF_STATE_BUCKET="resilience-gate-123-tf-state"',
            )
        )
        + "\n",
        encoding="utf-8",
    )


def run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)


def test_verifier_help_is_local_and_lists_narrow_scopes(tmp_path: Path) -> None:
    calls = tmp_path / "kubectl.calls"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_executable(bin_dir / "kubectl", f'printf "%s\\n" "$*" >> "{calls}"')
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}

    result = run(["bash", str(VERIFY), "--help"], env=env)

    assert result.returncode == 0, result.stderr
    assert "--scope" in result.stdout
    for scope in ("platform", "gitops", "gate", "all"):
        assert scope in result.stdout
    assert not calls.exists(), "help must not inspect a cluster"


def test_verifier_refuses_wrong_context_before_any_resource_read(tmp_path: Path) -> None:
    calls = tmp_path / "kubectl.calls"
    config = tmp_path / "config.env"
    write_config(config)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_executable(
        bin_dir / "kubectl",
        f'''
printf '%s\\n' "$*" >> "{calls}"
if [[ "$*" == "config current-context" ]]; then
  printf '%s\\n' gke_other-project_us-central1-a_other-cluster
  exit 0
fi
exit 91
''',
    )
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}

    result = run(["bash", str(VERIFY), "--config", str(config), "--scope", "all"], env=env)

    assert result.returncode != 0
    assert "Expected target context" in result.stderr
    recorded = calls.read_text(encoding="utf-8")
    assert "config current-context" in recorded
    assert " get " not in f" {recorded} "
    assert " apply " not in f" {recorded} "
    assert " delete " not in f" {recorded} "


def test_gate_scope_successfully_uses_only_context_and_get_calls(tmp_path: Path) -> None:
    calls = tmp_path / "kubectl.calls"
    config = tmp_path / "config.env"
    write_config(config)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_executable(
        bin_dir / "kubectl",
        f'''
printf '%s\\n' "$*" >> "{calls}"
if [[ "$*" == "config current-context" ]]; then
  printf '%s\\n' {EXPECTED_CONTEXT}
elif [[ "$*" == *jsonpath* ]]; then
  printf 'True'
fi
''',
    )
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}

    result = run(["bash", str(VERIFY), "--config", str(config), "--scope", "gate"], env=env)

    assert result.returncode == 0, result.stderr
    recorded_calls = [line for line in calls.read_text(encoding="utf-8").splitlines() if line]
    assert any("config current-context" in call for call in recorded_calls)
    assert any(" get " in f" {call} " for call in recorded_calls)
    for call in recorded_calls:
        assert "config current-context" in call or " get " in f" {call} "
        for forbidden in (" apply ", " create ", " delete ", " patch ", " promote "):
            assert forbidden not in f" {call} "


def test_verifier_shell_and_source_contract_are_read_only() -> None:
    syntax = subprocess.run(["bash", "-n", str(VERIFY)], capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr

    source = VERIFY.read_text(encoding="utf-8")
    assert "require_target_context" in source
    assert "--scope" in source
    for forbidden in (
        "kubectl apply",
        "kubectl create",
        "kubectl delete",
        "kubectl patch",
        "kubectl replace",
        "kubectl edit",
        "kubectl exec",
        "kubectl cp",
        "kubectl port-forward",
        "kargo promote",
        "kargo verify",
    ):
        assert forbidden not in source
