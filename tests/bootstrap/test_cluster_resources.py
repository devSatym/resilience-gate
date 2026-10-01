from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE = REPO_ROOT / "platform_setup_scripts" / "05-cluster-resources.sh"
PLATFORM_PHASE = REPO_ROOT / "platform_setup_scripts" / "04-platform.sh"
SENTINEL_DIGEST = "sha256:" + "0" * 64


def write_config(path: Path, signer_digest: str | None) -> None:
    values = [
        'PROJECT_ID="resilience-gate-123"',
        'GITHUB_REPO="example/resilience-gate"',
        'REGION="us-central1"',
        'ZONE="us-central1-a"',
        'CLUSTER_NAME="resilience-gate"',
        'GAR_REPO="resilience-gate"',
        'TF_STATE_BUCKET="resilience-gate-123-tf-state"',
    ]
    if signer_digest is not None:
        values.append(f'SIGNER_DIGEST="{signer_digest}"')
    path.write_text("\n".join(values) + "\n", encoding="utf-8")


def run_phase(path: Path, config: Path, **environment: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(path)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {"CONFIG_FILE": str(config)} | environment,
    )


def test_root_gitops_refuses_missing_or_unresolvable_signer_digest_before_cluster_access(tmp_path: Path) -> None:
    for signer_digest, expected in (
        (None, "SIGNER_DIGEST is required"),
        ("", "SIGNER_DIGEST is required"),
        (SENTINEL_DIGEST, "SIGNER_DIGEST is the unresolvable sentinel"),
        ("not-a-digest", "SIGNER_DIGEST must be a lowercase sha256 digest"),
    ):
        config = tmp_path / f"{signer_digest or 'missing'}.env"
        write_config(config, signer_digest)

        result = run_phase(PHASE, config)

        assert result.returncode != 0
        assert expected in result.stderr
        assert "Target Kubernetes context verified" not in result.stderr
        assert "Applying ClusterSecretStore" not in result.stderr


def test_nonmutating_dry_run_and_pre_gitops_platform_phase_do_not_require_a_signer_digest(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.env"
    write_config(config, None)

    root_gitops_dry_run = run_phase(PHASE, config, DRY_RUN="true")
    platform_dry_run = run_phase(PLATFORM_PHASE, config, DRY_RUN="true")

    # Phase 05's dry run cannot reconcile root-app; it reaches only the normal
    # rendered-manifest check. Phase 04 remains usable to provision controllers
    # before CI publishes the first signer artifact.
    assert root_gitops_dry_run.returncode != 0
    assert "rendered manifests are stale" in root_gitops_dry_run.stderr
    assert "SIGNER_DIGEST is required" not in root_gitops_dry_run.stderr
    assert platform_dry_run.returncode == 0, platform_dry_run.stderr


def test_root_gitops_guard_is_checked_before_rendering_or_apply() -> None:
    source = PHASE.read_text(encoding="utf-8")

    guard_call = 'if ! is_dry_run; then\n  require_deployable_signer_digest\nfi'
    assert source.index(guard_call) < source.index('render_config.py" --config "$CONFIG_FILE" --check')
    assert source.index(guard_call) < source.index('k8s_apply "$css_file"')
