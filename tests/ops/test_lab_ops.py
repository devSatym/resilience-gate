"""Hermetic contracts for guarded owned-testnet lifecycle commands."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAB_OPS = REPO_ROOT / "scripts" / "lab-ops.sh"
PROJECT_ID = "resilience-gate-123"


def write_executable(path: Path, source: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + source + "\n", encoding="utf-8")
    path.chmod(0o755)


def write_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                f'PROJECT_ID="{PROJECT_ID}"',
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


def environment_with_fake_terraform(tmp_path: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "terraform.calls"
    write_executable(
        bin_dir / "terraform",
        f'''
printf '%s\\n' "$*" >> "{calls}"
previous=''
for argument in "$@"; do
  if [[ "$previous" == '-out' ]]; then : > "$argument"; fi
  case "$argument" in -out=*) : > "${{argument#-out=}}" ;; esac
  previous="$argument"
done
printf 'fake Terraform output\\n'
''',
    )
    return os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}, calls


def run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)


def test_help_is_local_and_exposes_only_guarded_commands(tmp_path: Path) -> None:
    env, calls = environment_with_fake_terraform(tmp_path)

    result = run(["bash", str(LAB_OPS), "--help"], env=env)

    assert result.returncode == 0, result.stderr
    for command in ("status", "bootstrap-plan", "destroy-plan", "destroy"):
        assert command in result.stdout
    assert "--apply" in result.stdout
    assert "--confirm-project" in result.stdout
    assert "--acknowledge-owned-testnet-lab-destruction" in result.stdout
    assert not calls.exists(), "help must not contact Terraform"


def test_destroy_rejects_missing_acknowledgements_before_terraform(tmp_path: Path) -> None:
    env, calls = environment_with_fake_terraform(tmp_path)
    config = tmp_path / "config.env"
    write_config(config)

    result = run(["bash", str(LAB_OPS), "--config", str(config), "destroy"], env=env)

    assert result.returncode != 0
    assert "--apply" in result.stderr
    assert not calls.exists(), "an unconfirmed destroy must not create a plan or apply one"


def test_destroy_cannot_apply_without_an_interactive_project_retype(tmp_path: Path) -> None:
    env, calls = environment_with_fake_terraform(tmp_path)
    config = tmp_path / "config.env"
    write_config(config)
    command = [
        "bash",
        str(LAB_OPS),
        "--config",
        str(config),
        "destroy",
        "--apply",
        "--confirm-project",
        PROJECT_ID,
        "--acknowledge-owned-testnet-lab-destruction",
    ]

    result = run(command, env=env)

    assert result.returncode != 0
    assert "interactive" in result.stderr.lower() or "tty" in result.stderr.lower()
    if calls.exists():
        assert "apply" not in calls.read_text(encoding="utf-8")


def test_destroy_plan_makes_a_plan_without_applying_or_using_a_bare_destroy(tmp_path: Path) -> None:
    env, calls = environment_with_fake_terraform(tmp_path)
    config = tmp_path / "config.env"
    write_config(config)

    result = run(["bash", str(LAB_OPS), "--config", str(config), "destroy-plan"], env=env)

    assert result.returncode == 0, result.stderr
    recorded = calls.read_text(encoding="utf-8")
    invoked_words = [line.split() for line in recorded.splitlines() if line]
    assert any("plan" in words for words in invoked_words)
    assert "-destroy" in recorded
    assert not any("apply" in words for words in invoked_words)
    assert not any("destroy" in words for words in invoked_words)


def test_lifecycle_shell_uses_a_saved_destroy_plan_and_no_direct_cluster_deletion() -> None:
    syntax = subprocess.run(["bash", "-n", str(LAB_OPS)], capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr

    source = LAB_OPS.read_text(encoding="utf-8")
    assert "07-verify.sh" in source
    assert "plan -destroy" in source
    assert "-lock=true" in source
    assert "-lock-timeout=5m" in source
    assert "create_destroy_plan" in source
    assert 'terraform_in_target apply -input=false "$destroy_plan_file"' in source
    assert "terraform destroy" not in source
    assert "kubectl delete" not in source
    assert not re.search(r"(?m)^\s*(?:run\s+)?gcloud\s+", source)
