"""Static contracts for the portable Kargo Freight sources.

These tests deliberately parse manifests only; no registry, Git provider, or
Kubernetes cluster is contacted during ordinary CI.
"""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE_TEMPLATE_PATH = (
    REPO_ROOT / "platform_setup_scripts" / "templates" / "kubernetes" / "kargo" / "warehouse.yaml.tmpl"
)


def warehouse() -> dict[str, object]:
    # The generated manifest contains the selected public project identity;
    # this portable contract deliberately checks the source template.
    return yaml.safe_load(WAREHOUSE_TEMPLATE_PATH.read_text(encoding="utf-8"))


def test_warehouse_combines_chart_revision_and_digest_backed_image_freight() -> None:
    manifest = warehouse()

    assert manifest["apiVersion"] == "kargo.akuity.io/v1alpha1"
    assert manifest["kind"] == "Warehouse"
    assert manifest["metadata"]["name"] == "resilience-gate"
    assert manifest["metadata"]["namespace"] == "resilience-gate"

    subscriptions = manifest["spec"]["subscriptions"]
    assert len(subscriptions) == 2
    image = subscriptions[0]["image"]
    git = subscriptions[1]["git"]

    assert image["repoURL"] == "{{REGION}}-docker.pkg.dev/{{PROJECT_ID}}/{{GAR_REPO}}/url-shortener"
    assert image["imageSelectionStrategy"] == "NewestBuild"
    assert image["allowTagsRegexes"] == ["^sha-[a-f0-9]{7,40}$"]
    assert image["ignoreTagsRegexes"] == ["^(latest|buildcache|pr-[0-9]+)$"]
    assert "allowTags" not in image

    assert git == {
        "repoURL": "{{GITHUB_REPOSITORY_URL}}",
        "branch": "main",
        "includePaths": ["helm/url-shortener"],
    }


def test_warehouse_has_no_committed_identity_or_mutable_deployment_reference() -> None:
    contents = WAREHOUSE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "github.com/" not in contents
    assert "amoghjay" not in contents
    assert "ajprojectplatform" not in contents
    assert ":latest" not in contents
    assert "{{GITHUB_REPOSITORY_URL}}" in contents
