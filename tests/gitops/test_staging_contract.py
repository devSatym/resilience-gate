"""Offline contracts for the staging promotion boundary."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGING_PATH = REPO_ROOT / "kubernetes" / "kargo" / "stage-staging.yaml"
PROJECT_CONFIG_PATH = REPO_ROOT / "kubernetes" / "kargo" / "projectconfig.yaml"


def load(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def stage_policy(project_config: dict[str, object], stage: str) -> bool:
    policies = project_config["spec"]["promotionPolicies"]
    matching = [
        policy
        for policy in policies
        if policy["stageSelector"] == {"name": stage}
    ]
    assert len(matching) == 1
    return matching[0]["autoPromotionEnabled"]


def test_staging_accepts_only_development_freight_and_requires_manual_promotion() -> None:
    stage = load(STAGING_PATH)
    project_config = load(PROJECT_CONFIG_PATH)

    assert stage["metadata"]["name"] == "staging"
    assert stage["metadata"]["namespace"] == "resilience-gate"
    request = stage["spec"]["requestedFreight"]
    assert request == [
        {
            "origin": {"kind": "Warehouse", "name": "resilience-gate"},
            "sources": {"stages": ["dev"]},
        }
    ]
    assert stage_policy(project_config, "staging") is False


def test_staging_renders_the_freight_digest_and_verifies_only_service_health_for_now() -> None:
    stage = load(STAGING_PATH)
    template = stage["spec"]["promotionTemplate"]["spec"]
    steps = template["steps"]
    yaml_update = next(step for step in steps if step["uses"] == "yaml-update")
    updates = yaml_update["config"]["updates"]

    assert {update["key"]: update["value"] for update in updates} == {
        "image.repository": "${{ vars.imageRepo }}",
        "image.digest": "${{ imageFrom(vars.imageRepo).Digest }}",
    }
    assert stage["spec"]["verification"] == {
        "analysisTemplates": [{"name": "service-health"}],
        "args": [
            {
                "name": "service-url",
                "value": "http://url-shortener-${{ ctx.stage }}.url-shortener-${{ ctx.stage }}.svc.cluster.local",
            }
        ],
    }

    contents = STAGING_PATH.read_text(encoding="utf-8")
    assert "sources:\n        direct:" not in contents
    assert "image.tag" not in contents
    assert "chaos-gate" not in contents
    assert "mainnet" not in contents
