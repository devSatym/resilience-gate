"""Hermetic contracts for the chart's local and External Secrets paths."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHART = REPOSITORY_ROOT / "helm" / "url-shortener"


def render(environment: str, *extra_values: str) -> list[dict]:
    """Render an environment without a cluster or a secret-manager account."""

    command = [
        "helm",
        "template",
        f"url-shortener-{environment}",
        str(CHART),
        "--namespace",
        f"url-shortener-{environment}",
    ]
    if environment != "local":
        command.extend(("--values", str(CHART / f"values-{environment}.yaml")))
    command.extend(extra_values)
    result = subprocess.run(command, capture_output=True, check=True, text=True)
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def resource(documents: list[dict], kind: str, name: str) -> dict:
    return next(
        document
        for document in documents
        if document["kind"] == kind and document["metadata"]["name"] == name
    )


@pytest.mark.parametrize("environment", ("dev", "staging", "prod"))
def test_environment_uses_external_secret_for_all_runtime_credentials(
    environment: str,
) -> None:
    documents = render(environment)
    credentials_name = f"url-shortener-{environment}-credentials"
    external_secret = resource(
        documents,
        "ExternalSecret",
        f"url-shortener-{environment}-external-secret",
    )

    assert external_secret["spec"]["target"]["name"] == credentials_name
    assert external_secret["spec"]["target"]["creationPolicy"] == "Owner"
    template_data = external_secret["spec"]["target"]["template"]["data"]
    assert set(template_data) == {
        "DATABASE_URL",
        "REDIS_URL",
        "SERVICE_WALLET_ADDRESS",
        "password",
        "postgres-password",
        "redis-password",
    }
    assert template_data["DATABASE_URL"] == "{{ .database_url }}"
    assert template_data["REDIS_URL"] == "{{ .redis_url }}"

    remote_keys = {
        entry["secretKey"]: entry["remoteRef"]["key"]
        for entry in external_secret["spec"]["data"]
    }
    assert set(remote_keys) == {
        "database_url",
        "database_password",
        "redis_url",
        "redis_password",
        "service_wallet_address",
    }
    assert all(key.startswith(f"resilience-gate-{environment}-") for key in remote_keys.values())
    assert all("/" not in key for key in remote_keys.values())

    deployment = resource(documents, "Deployment", f"url-shortener-{environment}")
    env_from = deployment["spec"]["template"]["spec"]["containers"][0]["envFrom"]
    assert env_from[1]["secretRef"]["name"] == credentials_name

    # Both dependency charts consume the same generated Secret, so the app
    # cannot drift from PostgreSQL or Redis credentials.
    postgres = resource(documents, "StatefulSet", f"url-shortener-{environment}-postgresql")
    redis = resource(documents, "StatefulSet", f"url-shortener-{environment}-redis-master")
    assert credentials_name in yaml.safe_dump(postgres)
    assert credentials_name in yaml.safe_dump(redis)
    assert not any(
        document["kind"] == "Secret"
        and document["metadata"]["name"] == credentials_name
        for document in documents
    )


def test_local_render_keeps_connection_strings_in_a_secret() -> None:
    documents = render(
        "local",
        "--set",
        "postgresql.auth.password=database:password with space",
        "--set",
        "redis.auth.password=redis:password with space",
    )
    credentials = resource(documents, "Secret", "url-shortener-local-credentials")
    rendered_values = credentials["stringData"]

    assert rendered_values["DATABASE_URL"].startswith("postgresql://urlshortener:")
    assert "database%3Apassword%20with%20space" in rendered_values["DATABASE_URL"]
    assert "redis%3Apassword%20with%20space" in rendered_values["REDIS_URL"]
    assert rendered_values["password"] == "database:password with space"
    assert rendered_values["redis-password"] == "redis:password with space"

    config = resource(documents, "ConfigMap", "url-shortener-local-config")
    assert "DATABASE_URL" not in config["data"]
    assert "REDIS_URL" not in config["data"]


def test_chart_rejects_a_dependency_secret_that_can_drift_from_the_app() -> None:
    result = subprocess.run(
        (
            "helm",
            "template",
            "url-shortener-dev",
            str(CHART),
            "--namespace",
            "url-shortener-dev",
            "--values",
            str(CHART / "values-dev.yaml"),
            "--set",
            "redis.auth.existingSecret=other-secret",
        ),
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "redis.auth.existingSecret must equal the ExternalSecret target name" in result.stderr
