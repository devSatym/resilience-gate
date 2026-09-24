from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "platform_setup_scripts" / "bootstrap.sh"


def test_bootstrap_help_exposes_completed_safe_phases_but_not_post_bootstrap_verification() -> None:
    result = subprocess.run(["bash", str(BOOTSTRAP), "--help"], check=False, capture_output=True, text=True)
    assert result.returncode == 0
    assert "00  preflight" in result.stdout
    assert "05  root GitOps" in result.stdout
    assert "06  GitOps/Kargo config" in result.stdout
    assert "07  " not in result.stdout


def test_bootstrap_accepts_completed_phase_six_but_rejects_phase_seven_before_loading_config(tmp_path: Path) -> None:
    missing_config = tmp_path / "missing-config.env"
    accepted = subprocess.run(
        ["bash", str(BOOTSTRAP), "--phase", "6", "--config", str(missing_config)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert accepted.returncode != 2
    assert "between 00 and 06" not in accepted.stderr
    assert "Configuration file not found" in accepted.stderr

    result = subprocess.run(
        ["bash", str(BOOTSTRAP), "--phase", "7", "--config", str(missing_config)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "between 00 and 06" in result.stderr
