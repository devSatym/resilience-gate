from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SECRETS_SCRIPT = REPO_ROOT / "platform_setup_scripts" / "02-secrets.sh"
CONFIG_EXAMPLE = REPO_ROOT / "platform_setup_scripts" / "config.env.example"
CHART = REPO_ROOT / "helm" / "url-shortener"


def configured_secret_names() -> set[str]:
    match = re.search(
        r"^SECRETS=\(\n(?P<names>.*?)^\)",
        CONFIG_EXAMPLE.read_text(encoding="utf-8"),
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, "config.env.example must declare SECRETS as a Bash array"
    return {
        line.strip()
        for line in match.group("names").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def external_secret_remote_keys(path: Path) -> set[str]:
    return {
        item["remoteRef"]["key"]
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if document and document.get("kind") == "ExternalSecret"
        for item in document["spec"]["data"]
    }


def chart_remote_keys(path: Path) -> set[str]:
    values = yaml.safe_load(path.read_text(encoding="utf-8"))
    return set(values["externalSecrets"]["remoteRefs"].values())


def test_dry_run_never_prompts_or_calls_gcloud(tmp_path: Path) -> None:
    config = tmp_path / "config.env"
    config.write_text(
        '\n'.join(
            (
                'PROJECT_ID="resilience-gate-123"',
                'GITHUB_REPO="example/resilience-gate"',
                'SECRETS=(database-password github-pat)',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(SECRETS_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        input="",
        env=os.environ | {"CONFIG_FILE": str(config), "DRY_RUN": "true", "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert "no secret values will be requested" in result.stderr
    assert "Enter value" not in result.stderr
    assert "database-password" in result.stderr


def test_secret_script_requires_explicit_rotation() -> None:
    source = SECRETS_SCRIPT.read_text(encoding="utf-8")
    assert "ROTATE_SECRETS=true" in source
    assert "--data-file=-" in source
    assert "never written to disk" in source


def test_configured_flat_secret_manager_ids_cover_every_workload_reference() -> None:
    configured = configured_secret_names()
    expected = {
        "resilience-gate-github-pat",
        "resilience-gate-grafana-admin-password",
        "resilience-gate-shared-url-shortener-database-url",
        "resilience-gate-shared-url-shortener-database-password",
        "resilience-gate-shared-url-shortener-redis-url",
        "resilience-gate-shared-url-shortener-redis-password",
        "resilience-gate-shared-service-wallet-address-testnet",
        "resilience-gate-dev-url-shortener-database-url",
        "resilience-gate-dev-url-shortener-database-password",
        "resilience-gate-dev-url-shortener-redis-url",
        "resilience-gate-dev-url-shortener-redis-password",
        "resilience-gate-dev-service-wallet-address-testnet",
        "resilience-gate-staging-url-shortener-database-url",
        "resilience-gate-staging-url-shortener-database-password",
        "resilience-gate-staging-url-shortener-redis-url",
        "resilience-gate-staging-url-shortener-redis-password",
        "resilience-gate-staging-service-wallet-address-testnet",
        "resilience-gate-staging-signer-rpc-url-testnet",
        "resilience-gate-staging-loadgen-wallet-key-1-testnet",
        "resilience-gate-staging-loadgen-wallet-key-2-testnet",
        "resilience-gate-staging-loadgen-wallet-key-3-testnet",
        "resilience-gate-prod-url-shortener-database-url",
        "resilience-gate-prod-url-shortener-database-password",
        "resilience-gate-prod-url-shortener-redis-url",
        "resilience-gate-prod-url-shortener-redis-password",
        "resilience-gate-prod-service-wallet-address-testnet",
    }
    remote_keys = set().union(
        *(chart_remote_keys(CHART / f"values-{environment}.yaml") for environment in ("dev", "staging", "prod")),
        chart_remote_keys(CHART / "values.yaml"),
        external_secret_remote_keys(REPO_ROOT / "kubernetes" / "jobs" / "external-secret-signer.yaml"),
        external_secret_remote_keys(REPO_ROOT / "kubernetes" / "jobs" / "external-secret-loadgen.yaml"),
        external_secret_remote_keys(
            REPO_ROOT / "kubernetes" / "bootstrap" / "secrets" / "external-secrets-argocd.yaml"
        ),
        external_secret_remote_keys(
            REPO_ROOT / "kubernetes" / "bootstrap" / "secrets" / "external-secrets-monitoring.yaml"
        ),
        external_secret_remote_keys(
            REPO_ROOT / "kubernetes" / "chaos-experiments" / "external-secret-grafana.yaml"
        ),
        external_secret_remote_keys(REPO_ROOT / "kubernetes" / "kargo" / "credentials-git.yaml"),
    )

    assert configured == expected
    assert remote_keys == expected
    assert all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,254}", name) for name in configured)
    assert all("/" not in name for name in configured)
