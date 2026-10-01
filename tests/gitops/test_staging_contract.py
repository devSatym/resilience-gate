"""Offline contracts for the staging promotion boundary."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGING_PATH = REPO_ROOT / "kubernetes" / "kargo" / "stage-staging.yaml"
STAGING_TEMPLATE_PATH = (
    REPO_ROOT / "platform_setup_scripts" / "templates" / "kubernetes" / "kargo" / "stage-staging.yaml.tmpl"
)
ANALYSIS_TEMPLATE_PATH = (
    REPO_ROOT / "platform_setup_scripts" / "templates" / "kubernetes" / "kargo" / "analysistemplate.yaml.tmpl"
)
PROJECT_PATH = REPO_ROOT / "kubernetes" / "kargo" / "project.yaml"


def load(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def stage_policy(project: dict[str, object], stage: str) -> bool:
    policies = project["spec"]["promotionPolicies"]
    matching = [
        policy
        for policy in policies
        if policy["stage"] == stage
    ]
    assert len(matching) == 1
    return matching[0]["autoPromotionEnabled"]


def test_staging_accepts_only_development_freight_and_requires_manual_promotion() -> None:
    stage = load(STAGING_PATH)
    project = load(PROJECT_PATH)

    assert stage["metadata"]["name"] == "staging"
    assert stage["metadata"]["namespace"] == "resilience-gate"
    request = stage["spec"]["requestedFreight"]
    assert request == [
        {
            "origin": {"kind": "Warehouse", "name": "resilience-gate"},
            "sources": {"stages": ["dev"]},
        }
    ]
    assert stage_policy(project, "staging") is False


def test_staging_renders_the_freight_digest_and_requires_the_immutable_chaos_gate() -> None:
    # Public rendered manifests deliberately contain the selected deployment
    # identity. The portable contract belongs to the source template instead.
    stage = load(STAGING_TEMPLATE_PATH)
    template = stage["spec"]["promotionTemplate"]["spec"]
    steps = template["steps"]
    yaml_update = next(step for step in steps if step["uses"] == "yaml-update")
    updates = yaml_update["config"]["updates"]

    assert {update["key"]: update["value"] for update in updates} == {
        "image.repository": "${{ vars.imageRepo }}",
        "image.digest": "${{ imageFrom(vars.imageRepo).Digest }}",
    }
    assert stage["spec"]["verification"] == {
        "analysisTemplates": [{"name": "service-health"}, {"name": "chaos-gate"}],
        "args": [
            {
                "name": "service-url",
                "value": "http://url-shortener-${{ ctx.stage }}.url-shortener-${{ ctx.stage }}.svc.cluster.local",
            },
            {
                "name": "release-revision",
                "value": "${{ commitFrom(\"{{GITHUB_REPOSITORY_URL}}\").ID }}",
            },
            {
                "name": "release-digest",
                "value": "${{ imageFrom(\"{{REGION}}-docker.pkg.dev/{{PROJECT_ID}}/{{GAR_REPO}}/url-shortener\").Digest }}",
            },
        ],
    }

    contents = STAGING_TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "sources:\n        direct:" not in contents
    assert "image.tag" not in contents
    assert "mainnet" not in contents


def test_chaos_gate_job_uses_a_digest_and_cannot_change_its_scripts_at_runtime() -> None:
    templates = list(yaml.safe_load_all(ANALYSIS_TEMPLATE_PATH.read_text(encoding="utf-8")))
    gate = next(template for template in templates if template["metadata"]["name"] == "chaos-gate")
    metric = gate["spec"]["metrics"][0]
    job = metric["provider"]["job"]["spec"]
    pod = job["template"]["spec"]
    container = pod["containers"][0]

    assert metric["name"] == "chaos-verdict"
    assert metric["count"] == 1
    assert metric["failureLimit"] == 0
    assert job["backoffLimit"] == 0
    assert job["activeDeadlineSeconds"] == 1320
    assert pod["serviceAccountName"] == "chaos-gate"
    assert pod["restartPolicy"] == "Never"
    assert pod["terminationGracePeriodSeconds"] == 120
    grafana_password = next(
        env for env in container["env"] if env["name"] == "GRAFANA_PASSWORD"
    )
    assert grafana_password["valueFrom"]["secretKeyRef"] == {
        "name": "grafana-annotation",
        "key": "password",
        "optional": True,
    }
    assert container["image"].endswith("/gate-runner@{{GATE_RUNNER_DIGEST}}")
    assert "configMap" not in yaml.safe_dump(job)


def test_rendered_templates_use_freight_identities_without_unsupported_stage_vars() -> None:
    template_root = REPO_ROOT / "platform_setup_scripts" / "templates" / "kubernetes" / "kargo"
    stage_template = (template_root / "stage-staging.yaml.tmpl").read_text(encoding="utf-8")
    analysis_template = (template_root / "analysistemplate.yaml.tmpl").read_text(encoding="utf-8")

    assert "spec:\n  vars:" not in stage_template
    assert 'commitFrom("{{GITHUB_REPOSITORY_URL}}").ID' in stage_template
    assert 'imageFrom("{{REGION}}-docker.pkg.dev/{{PROJECT_ID}}/{{GAR_REPO}}/url-shortener").Digest' in stage_template
    assert "activeDeadlineSeconds: 1320" in analysis_template
    assert "terminationGracePeriodSeconds: 120" in analysis_template
    assert "optional: true" in analysis_template


def test_complete_gate_resources_are_reachable_before_warehouse_discovery() -> None:
    bootstrap_root = REPO_ROOT / "kubernetes" / "bootstrap"
    kustomization = load(bootstrap_root / "kustomization.yaml")
    gate_application = load(bootstrap_root / "chaos-gate.yaml")
    annotation_secret = load(
        REPO_ROOT / "kubernetes" / "chaos-experiments" / "external-secret-grafana.yaml"
    )
    bootstrap_script = (
        REPO_ROOT / "platform_setup_scripts" / "06-gitops-and-kargo.sh"
    ).read_text(encoding="utf-8")

    assert {
        "chaos-mesh-ns-annotation.yaml",
        "chaos-mesh.yaml",
        "chaos-gate.yaml",
    } <= set(kustomization["resources"])
    assert gate_application["spec"]["source"]["path"] == "kubernetes/chaos-experiments"
    assert gate_application["spec"]["destination"]["namespace"] == "resilience-gate"
    assert annotation_secret["spec"]["secretStoreRef"] == {
        "name": "resilience-gate-secrets",
        "kind": "ClusterSecretStore",
    }
    assert annotation_secret["spec"]["target"] == {
        "name": "grafana-annotation",
        "creationPolicy": "Owner",
        "deletionPolicy": "Retain",
        "template": {
            "engineVersion": "v2",
            "mergePolicy": "Replace",
            "data": {"password": "{{ .password }}"},
        },
    }
    assert annotation_secret["spec"]["data"] == [
        {
            "secretKey": "password",
            "remoteRef": {
                "key": "resilience-gate-grafana-admin-password",
                "conversionStrategy": "Default",
                "decodingStrategy": "None",
                "metadataPolicy": "None",
            },
        }
    ]
    assert bootstrap_script.index('k8s_apply "${manifests[chaos_gate]}"') < bootstrap_script.index(
        'k8s_apply "${manifests[warehouse]}"'
    )
