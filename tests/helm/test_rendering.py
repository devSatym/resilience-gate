"""Offline rendering contracts for the Resilience Gate application chart."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHART = REPOSITORY_ROOT / "helm" / "url-shortener"
ENVIRONMENTS = ("dev", "staging", "prod")
DIGEST_PATTERN = re.compile(r"@sha256:[a-f0-9]{64}$")
EXPECTED_REPLICAS = {"dev": 1, "staging": 2, "prod": 3}
EXPECTED_MIN_AVAILABLE = {"staging": 1, "prod": 2}


def helm(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("helm", *arguments),
        capture_output=True,
        check=check,
        cwd=REPOSITORY_ROOT,
        text=True,
    )


def render(environment: str, *extra_values: str) -> list[dict]:
    result = helm(
        "template",
        f"url-shortener-{environment}",
        str(CHART),
        "--namespace",
        f"url-shortener-{environment}",
        "--values",
        str(CHART / f"values-{environment}.yaml"),
        *extra_values,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def resource(documents: list[dict], kind: str, name: str) -> dict:
    return next(
        document
        for document in documents
        if document["kind"] == kind and document["metadata"]["name"] == name
    )


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_environment_render_is_immutable_hardened_and_testnet_only(
    environment: str,
) -> None:
    documents = render(environment)
    deployment = resource(documents, "Deployment", f"url-shortener-{environment}")
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]

    assert deployment["spec"]["replicas"] == EXPECTED_REPLICAS[environment]
    assert DIGEST_PATTERN.search(container["image"])
    assert ":latest" not in container["image"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["enableServiceLinks"] is False
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
        "readOnlyRootFilesystem": True,
        "runAsNonRoot": True,
    }
    assert container["livenessProbe"]["httpGet"]["path"] == "/livez"
    assert container["readinessProbe"]["httpGet"]["path"] == "/ready"
    assert container["startupProbe"]["httpGet"]["path"] == "/ready"

    config = resource(documents, "ConfigMap", f"url-shortener-{environment}-config")
    assert config["data"]["NETWORK_CAIP2"] == "eip155:72344"
    assert "testnet" in config["data"]["FACILITATOR_URL"]
    assert "mainnet" not in yaml.safe_dump(config).lower()
    assert "DATABASE_URL" not in config["data"]
    assert "REDIS_URL" not in config["data"]

    service = resource(documents, "Service", f"url-shortener-{environment}")
    assert service["spec"]["ports"][0]["targetPort"] == "http"

    has_pdb = any(
        document["kind"] == "PodDisruptionBudget"
        and document["metadata"]["name"] == f"url-shortener-{environment}"
        for document in documents
    )
    assert has_pdb is (environment != "dev")
    if environment == "dev":
        assert "topologySpreadConstraints" not in pod
        assert "affinity" not in pod
    else:
        assert pod["topologySpreadConstraints"][0]["topologyKey"] == "kubernetes.io/hostname"
        assert pod["affinity"]["podAntiAffinity"]
        pdb = resource(documents, "PodDisruptionBudget", f"url-shortener-{environment}")
        assert pdb["spec"]["minAvailable"] == EXPECTED_MIN_AVAILABLE[environment]

    service_account = resource(documents, "ServiceAccount", f"url-shortener-{environment}")
    assert service_account["automountServiceAccountToken"] is False


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_environment_values_are_testnet_only(environment: str) -> None:
    values = yaml.safe_load((CHART / f"values-{environment}.yaml").read_text())
    payments = values["payments"]
    assert payments["enabled"] is True
    assert payments["testnetOnly"] is True
    assert payments["network"] == "eip155:72344"
    assert "testnet" in payments["facilitatorUrl"]
    assert "mainnet" not in (CHART / f"values-{environment}.yaml").read_text().lower()


def test_chart_rejects_a_mutable_image_reference() -> None:
    result = helm(
        "template",
        "url-shortener-dev",
        str(CHART),
        "--namespace",
        "url-shortener-dev",
        "--values",
        str(CHART / "values-dev.yaml"),
        "--set",
        "image.digest=sha-candidate",
        check=False,
    )

    assert result.returncode != 0
    assert "mutable image tags are not supported" in result.stderr


def test_chart_rejects_non_testnet_payment_configuration() -> None:
    result = helm(
        "template",
        "url-shortener-dev",
        str(CHART),
        "--namespace",
        "url-shortener-dev",
        "--values",
        str(CHART / "values-dev.yaml"),
        "--set",
        "payments.testnetOnly=false",
        check=False,
    )

    assert result.returncode != 0
    assert "payments.testnetOnly must remain true" in result.stderr


def test_chart_rejects_an_unapproved_payment_network() -> None:
    result = helm(
        "template",
        "url-shortener-dev",
        str(CHART),
        "--namespace",
        "url-shortener-dev",
        "--values",
        str(CHART / "values-dev.yaml"),
        "--set",
        "payments.network=eip155:723487",
        check=False,
    )

    assert result.returncode != 0
    assert "payments.network is not in payments.allowedNetworks" in result.stderr


def test_chart_dependencies_are_pinned_and_vendored() -> None:
    result = helm("dependency", "list", str(CHART))

    assert "redis" in result.stdout
    assert "postgresql" in result.stdout
    assert result.stdout.count("ok") == 2
    assert (CHART / "Chart.lock").is_file()
    assert (CHART / "charts" / "redis-25.3.5.tgz").is_file()
    assert (CHART / "charts" / "postgresql-18.5.7.tgz").is_file()


def test_fragile_staging_overlay_changes_existing_chart_values() -> None:
    documents = render(
        "staging",
        "--values",
        str(CHART / "values-staging-fragile.yaml"),
    )
    deployment = resource(documents, "Deployment", "url-shortener-staging")
    config = resource(documents, "ConfigMap", "url-shortener-staging-config")

    assert deployment["spec"]["replicas"] == 1
    assert "affinity" not in deployment["spec"]["template"]["spec"]
    assert config["data"]["FACILITATOR_TIMEOUT_SECONDS"] == "2"
    assert not any(
        document["kind"] == "PodDisruptionBudget"
        and document["metadata"]["name"] == "url-shortener-staging"
        for document in documents
    )
    assert not any(document["kind"] == "PersistentVolumeClaim" for document in documents)
