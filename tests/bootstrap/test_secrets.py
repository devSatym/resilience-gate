from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SECRETS_SCRIPT = REPO_ROOT / "platform_setup_scripts" / "02-secrets.sh"


def test_dry_run_never_prompts_or_calls_gcloud(tmp_path: Path) -> None:
    config = tmp_path / "config.env"
    config.write_text(
        '\n'.join(
            (
                'PROJECT_ID="resilience-gate-123"',
                'GITHUB_REPO="example/resilience-gate"',
                'SECRETS=(database-password github-pat)',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(SECRETS_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        input="",
        env=os.environ | {"CONFIG_FILE": str(config), "DRY_RUN": "true", "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert "no secret values will be requested" in result.stderr
    assert "Enter value" not in result.stderr
    assert "database-password" in result.stderr


def test_secret_script_requires_explicit_rotation() -> None:
    source = SECRETS_SCRIPT.read_text(encoding="utf-8")
    assert "ROTATE_SECRETS=true" in source
    assert "--data-file=-" in source
    assert "never written to disk" in source
