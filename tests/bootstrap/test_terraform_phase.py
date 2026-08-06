from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_PHASE = REPO_ROOT / "platform_setup_scripts" / "03-terraform.sh"


def test_noninteractive_terraform_never_applies(tmp_path: Path) -> None:
    config = tmp_path / "config.env"
    config.write_text(
        '\n'.join(
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
    tools = tmp_path / "bin"
    tools.mkdir()
    calls = tmp_path / "terraform.calls"
    terraform = tools / "terraform"
    terraform.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{calls}"\n', encoding="utf-8")
    terraform.chmod(0o755)

    result = subprocess.run(
        ["bash", str(TERRAFORM_PHASE)],
        check=False,
        capture_output=True,
        text=True,
        input="",
        env=os.environ | {"CONFIG_FILE": str(config), "PATH": f"{tools}:/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    recorded = calls.read_text(encoding="utf-8")
    assert "init" in recorded
    assert "plan" in recorded
    assert "apply" not in recorded
    assert "No interactive terminal" in result.stderr


def test_terraform_phase_uses_saved_plan_and_exact_context_guard() -> None:
    source = TERRAFORM_PHASE.read_text(encoding="utf-8")
    assert "-reconfigure" in source
    assert "github_repository=$GITHUB_REPO" in source
    assert "registry_repository_id=$GAR_REPO" in source
    assert "require_target_context" in source
    assert "rm -rf" not in source
