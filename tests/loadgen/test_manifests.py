"""Rendered, cluster-free contracts for staging signer and loadgen resources."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
JOBS = REPOSITORY_ROOT / "kubernetes" / "jobs"
DIGEST = re.compile(r"@sha256:[a-f0-9]{64}$")


def render() -> list[dict]:
    """Run Kustomize locally; this reads manifests and contacts no cluster."""

    result = subprocess.run(
        ("kubectl", "kustomize", str(JOBS)),
        capture_output=True,
        check=True,
        cwd=REPOSITORY_ROOT,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def resource(documents: list[dict], kind: str, name: str) -> dict:
    return next(
        document
        for document in documents
        if document["kind"] == kind and document["metadata"]["name"] == name
    )


def test_signer_uses_its_own_secret_boundary_and_safe_probes() -> None:
    documents = render()
    deployment = resource(documents, "Deployment", "radius-signer")
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]

    assert container["image"] == (
        "{{REGION}}-docker.pkg.dev/{{PROJECT_ID}}/{{GAR_REPO}}/"
        "radius-signer@{{SIGNER_DIGEST}}"
    )
    assert ":latest" not in container["image"]
    assert "ajprojectplatform" not in container["image"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["enableServiceLinks"] is False
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert container["envFrom"] == [{"secretRef": {"name": "resilience-gate-signer-credentials"}}]
    assert container["startupProbe"]["httpGet"]["path"] == "/livez"
    assert container["livenessProbe"]["httpGet"]["path"] == "/livez"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]

    service_monitor = resource(documents, "ServiceMonitor", "radius-signer")
    endpoint = service_monitor["spec"]["endpoints"][0]
    assert endpoint["port"] == "http"
    assert endpoint["path"] == "/metrics"
    assert service_monitor["metadata"]["labels"]["release"] == "observability"


def test_external_secret_contract_never_gives_loadgen_payer_keys() -> None:
    signer = yaml.safe_load((JOBS / "external-secret-signer.yaml").read_text())
    loadgen = yaml.safe_load((JOBS / "external-secret-loadgen.yaml").read_text())

    assert signer["spec"]["secretStoreRef"]["name"] == "resilience-gate-secrets"
    assert signer["spec"]["target"]["name"] == "resilience-gate-signer-credentials"
    assert {item["secretKey"] for item in signer["spec"]["data"]} == {
        "RPC_URL",
        "SERVICE_WALLET_ADDRESS",
        "WALLET_KEY_1",
        "WALLET_KEY_2",
        "WALLET_KEY_3",
    }

    assert loadgen["spec"]["secretStoreRef"]["name"] == "resilience-gate-secrets"
    assert loadgen["spec"]["target"]["name"] == "resilience-gate-loadgen-credentials"
    assert [item["secretKey"] for item in loadgen["spec"]["data"]] == ["SERVICE_WALLET_ADDRESS"]
    assert "WALLET_KEY" not in (JOBS / "external-secret-loadgen.yaml").read_text()

    for external_secret in (signer, loadgen):
        assert all(
            item["remoteRef"]["key"].startswith("resilience-gate-staging-")
            for item in external_secret["spec"]["data"]
        )
        assert all("/" not in item["remoteRef"]["key"] for item in external_secret["spec"]["data"])


def test_suspended_loadgen_is_digest_pinned_and_exports_a_summary() -> None:
    documents = render()
    cronjob = resource(documents, "CronJob", "loadgen")
    pod = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = pod["containers"][0]

    assert cronjob["spec"]["suspend"] is True
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    job_spec = cronjob["spec"]["jobTemplate"]["spec"]
    assert job_spec["activeDeadlineSeconds"] == 780
    assert job_spec["ttlSecondsAfterFinished"] == 86400
    assert container["image"].startswith("grafana/k6@sha256:")
    assert DIGEST.search(container["image"])
    assert ":latest" not in container["image"]
    assert "--summary-export=/results/summary.json" in container["args"]
    assert container["envFrom"] == [{"secretRef": {"name": "resilience-gate-loadgen-credentials"}}]
    assert "K6_NO_USAGE_REPORT" in {item["name"] for item in container["env"]}
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsUser"] == 12345
    assert {mount["mountPath"] for mount in container["volumeMounts"]} >= {
        "/scripts",
        "/results",
        "/tmp",
    }

    config_map = next(
        document
        for document in documents
        if document["kind"] == "ConfigMap"
        and document["metadata"]["name"].startswith("k6-loadgen-script-")
    )
    config_map_name = config_map["metadata"]["name"]
    volume = next(volume for volume in pod["volumes"] if volume["name"] == "k6-script")
    assert volume["configMap"]["name"] == config_map_name


def test_jobs_kustomization_contains_no_mutable_legacy_identity() -> None:
    source = "\n".join(path.read_text() for path in JOBS.rglob("*.yaml"))
    assert "ajprojectplatform" not in source
    assert "k8s-chaos-demo" not in source
    assert ":latest" not in source
    assert "disableNameSuffixHash: true" not in (JOBS / "kustomization.yaml").read_text()
