from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "platform_setup_scripts" / "bootstrap.sh"


def test_bootstrap_help_exposes_only_completed_safe_phases() -> None:
    result = subprocess.run(["bash", str(BOOTSTRAP), "--help"], check=False, capture_output=True, text=True)
    assert result.returncode == 0
    assert "00  preflight" in result.stdout
    assert "05  root GitOps" in result.stdout
    assert "06  gitops-and-kargo" not in result.stdout


def test_bootstrap_rejects_future_or_invalid_phase_before_loading_config() -> None:
    result = subprocess.run(["bash", str(BOOTSTRAP), "--phase", "6"], check=False, capture_output=True, text=True)
    assert result.returncode == 2
    assert "between 00 and 05" in result.stderr
