"""Offline contracts for ordered, non-activating GitOps bootstrap."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "platform_setup_scripts" / "bootstrap.sh"
GITOPS_PHASE = REPO_ROOT / "platform_setup_scripts" / "06-gitops-and-kargo.sh"
RENDERER = REPO_ROOT / "platform_setup_scripts" / "render_config.py"
PROMOTION_CONTRACT = REPO_ROOT / "docs" / "design" / "promotion-contract.md"


def test_bootstrap_exposes_the_reviewed_non_activating_gitops_phase() -> None:
    result = subprocess.run(("bash", str(BOOTSTRAP), "--help"), capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "06  GitOps/Kargo config" in result.stdout
    assert "Promotion, paid load generation, and\nchaos verification" in result.stdout


def test_gitops_phase_orders_destinations_before_warehouse_and_does_not_activate_work() -> None:
    source = GITOPS_PHASE.read_text(encoding="utf-8")

    assert 'render_config.py" --config "$CONFIG_FILE" --check' in source
    assert "require_target_context" in source
    assert source.index('k8s_apply "${manifests[project]}"') < source.index('k8s_apply "${manifests[credentials]}"')
    assert source.index('k8s_apply "${manifests[app_set]}"') < source.index('k8s_apply "${manifests[warehouse]}"')
    assert "kargo promote" not in source
    assert "kubectl patch" not in source
    assert "kubectl create job" not in source
    assert "run-loadgen" not in source


def test_all_tokenized_promotion_resources_are_reviewed_renderer_outputs() -> None:
    source = RENDERER.read_text(encoding="utf-8")
    expected = {
        "kubernetes/kargo/credentials-git.yaml",
        "kubernetes/kargo/warehouse.yaml",
        "kubernetes/kargo/stage-dev.yaml",
        "kubernetes/kargo/stage-staging.yaml",
        "kubernetes/kargo/stage-prod.yaml",
        "kubernetes/apps/appproject.yaml",
        "kubernetes/apps/applicationset.yaml",
    }
    for path in expected:
        assert f'Path("{path}")' in source
        template = REPO_ROOT / "platform_setup_scripts" / "templates" / path
        assert template.with_suffix(template.suffix + ".tmpl").is_file()


def test_promotion_contract_names_the_deferred_gate_boundary() -> None:
    source = " ".join(PROMOTION_CONTRACT.read_text(encoding="utf-8").lower().split())
    assert "testnet" in source
    assert "does not invoke a kargo promotion" in source
    assert "does not" in source and "declare a gate passed" in source
