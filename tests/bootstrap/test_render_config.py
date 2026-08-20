from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "platform_setup_scripts" / "render_config.py"
TEMPLATES = REPO_ROOT / "platform_setup_scripts" / "templates"


def write_config(path: Path, **overrides: str) -> None:
    values = {
        "PROJECT_ID": "resilience-gate-123",
        "GITHUB_REPO": "example/resilience-gate",
        "REGION": "us-central1",
        "ZONE": "us-central1-a",
        "CLUSTER_NAME": "resilience-gate",
        "GAR_REPO": "resilience-gate",
        "TF_STATE_BUCKET": "",
    }
    values.update(overrides)
    path.write_text("\n".join(f'{key}="{value}"' for key, value in values.items()) + "\n", encoding="utf-8")


def invoke(config: Path, output_root: Path, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(RENDERER),
            "--config",
            str(config),
            "--template-root",
            str(TEMPLATES),
            "--output-root",
            str(output_root),
            mode,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_renderer_writes_and_checks_only_public_configuration(tmp_path: Path) -> None:
    config = tmp_path / "config.env"
    write_config(config)

    assert invoke(config, tmp_path, "--write").returncode == 0
    checked = invoke(config, tmp_path, "--check")
    assert checked.returncode == 0, checked.stderr

    root_app = (tmp_path / "kubernetes/argocd/root-app.yaml").read_text(encoding="utf-8")
    store = (tmp_path / "kubernetes/bootstrap/secrets/cluster-secret-store.yaml").read_text(encoding="utf-8")
    external_secret = (tmp_path / "kubernetes/bootstrap/secrets/external-secrets-argocd.yaml").read_text(encoding="utf-8")
    chaos_jobs = (tmp_path / "kubernetes/bootstrap/chaos-jobs.yaml").read_text(encoding="utf-8")

    assert "https://github.com/example/resilience-gate.git" in root_app
    assert "resilience-gate-123" in store
    assert "github_pat" in external_secret
    assert "https://github.com/example/resilience-gate.git" in chaos_jobs
    assert "{{PROJECT_ID}}" not in store


def test_renderer_rejects_incomplete_or_stale_config(tmp_path: Path) -> None:
    config = tmp_path / "config.env"
    write_config(config, GITHUB_REPO="")
    result = invoke(config, tmp_path, "--write")
    assert result.returncode == 2
    assert "GITHUB_REPO is required" in result.stderr

    write_config(config)
    assert invoke(config, tmp_path, "--write").returncode == 0
    (tmp_path / "kubernetes/argocd/root-app.yaml").write_text("stale\n", encoding="utf-8")
    result = invoke(config, tmp_path, "--check")
    assert result.returncode == 2
    assert "rendered manifests are stale" in result.stderr
