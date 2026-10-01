"""Offline contracts for the deferred production-like testnet Stage."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_PATH = REPO_ROOT / "kubernetes" / "kargo" / "stage-prod.yaml"
PROJECT_PATH = REPO_ROOT / "kubernetes" / "kargo" / "project.yaml"
ANALYSIS_PATH = REPO_ROOT / "kubernetes" / "kargo" / "analysistemplate.yaml"


def load(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_prod_can_only_receive_staging_freight_and_stays_manually_promoted() -> None:
    stage = load(PROD_PATH)
    project = load(PROJECT_PATH)

    assert stage["metadata"]["name"] == "prod"
    assert stage["metadata"]["namespace"] == "resilience-gate"
    assert stage["metadata"]["annotations"]["resilience-gate.io/activation"] == "deferred-until-c089"
    assert stage["spec"]["requestedFreight"] == [
        {
            "origin": {"kind": "Warehouse", "name": "resilience-gate"},
            "sources": {"stages": ["staging"]},
        }
    ]
    policies = project["spec"]["promotionPolicies"]
    prod_policy = [policy for policy in policies if policy["stage"] == "prod"]
    assert prod_policy == [{"stage": "prod", "autoPromotionEnabled": False}]


def test_prod_requires_post_deploy_health_without_premature_chaos_gate() -> None:
    stage = load(PROD_PATH)
    templates = list(yaml.safe_load_all(ANALYSIS_PATH.read_text(encoding="utf-8")))
    post_deploy = next(template for template in templates if template["metadata"]["name"] == "prod-post-deploy-health")

    assert stage["spec"]["verification"]["analysisTemplates"] == [
        {"name": "prod-post-deploy-health"}
    ]
    assert stage["spec"]["verification"]["args"] == [
        {
            "name": "service-url",
            "value": "http://url-shortener-${{ ctx.stage }}.url-shortener-${{ ctx.stage }}.svc.cluster.local",
        }
    ]
    assert [metric["name"] for metric in post_deploy["spec"]["metrics"]] == ["readiness", "liveness"]
    assert all(metric["failureLimit"] == 0 for metric in post_deploy["spec"]["metrics"])

    contents = PROD_PATH.read_text(encoding="utf-8")
    assert "sources:\n        direct:" not in contents
    assert "image.tag" not in contents
    assert "chaos-gate" not in contents
    assert "mainnet" not in contents
