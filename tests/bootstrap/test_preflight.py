from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = REPO_ROOT / "platform_setup_scripts" / "00-preflight.sh"


def write_fake_tool(path: Path, name: str, body: str) -> None:
    tool = path / name
    tool.write_text("#!/usr/bin/env bash\nset -eu\n" + body + "\n", encoding="utf-8")
    tool.chmod(0o755)


def run_preflight(tmp_path: Path, context: str) -> subprocess.CompletedProcess[str]:
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
                'SECRETS=(database-password)',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    tools = tmp_path / "bin"
    tools.mkdir()
    write_fake_tool(
        tools,
        "gcloud",
        """
if [[ "$*" == "config get-value account" ]]; then echo operator@example.test; exit 0; fi
if [[ "$*" == "auth application-default print-access-token" ]]; then echo token; exit 0; fi
if [[ "$*" == projects\\ describe* ]]; then echo 123456789; exit 0; fi
exit 1
""",
    )
    write_fake_tool(tools, "kubectl", f'if [[ "$*" == "config current-context" ]]; then echo "{context}"; fi')
    for command in ("helm", "terraform", "openssl", "htpasswd", "base64"):
        write_fake_tool(tools, command, "exit 0")

    env = os.environ | {"CONFIG_FILE": str(config), "PATH": f"{tools}:{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(PREFLIGHT), "--require-cluster-context"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_preflight_accepts_the_exact_target_context(tmp_path: Path) -> None:
    result = run_preflight(tmp_path, "gke_resilience-gate-123_us-central1-a_resilience-gate")
    assert result.returncode == 0, result.stderr
    assert "Target Kubernetes context verified" in result.stderr


def test_preflight_refuses_a_different_cluster_context(tmp_path: Path) -> None:
    result = run_preflight(tmp_path, "gke_other-project_us-central1-a_other-cluster")
    assert result.returncode != 0
    assert "Expected target context" in result.stderr
