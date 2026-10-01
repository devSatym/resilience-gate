from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "platform_setup_scripts" / "04-platform.sh"
VERSIONS = REPO_ROOT / "platform_setup_scripts" / "versions.env"


def test_platform_versions_are_explicit_and_nonempty() -> None:
    values = {}
    for line in VERSIONS.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    expected = {
        "CERT_MANAGER_CHART_VERSION",
        "ARGOCD_CHART_VERSION",
        "ARGO_ROLLOUTS_CHART_VERSION",
        "EXTERNAL_SECRETS_CHART_VERSION",
        "KARGO_CHART_REF",
        "KARGO_CHART_VERSION",
    }
    assert expected <= values.keys()
    assert all(values[key] for key in expected)


def test_platform_uses_persistent_secret_and_workload_identities() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'api.secret.name=$kargo_secret_name' in source
    assert "ADMIN_ACCOUNT_PASSWORD_HASH" in source
    assert "kubectl create namespace kargo --dry-run=client -o yaml" in source
    assert "iam.gke.io/gcp-service-account=$kargo_gcp_service_account" in source
    assert "api.adminAccount.passwordHash" not in source
    assert "api.adminAccount.tokenSigningKey" not in source


def test_platform_uses_the_portable_stdin_only_bcrypt_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    library = (REPO_ROOT / "platform_setup_scripts" / "lib.sh").read_text(encoding="utf-8")

    assert 'printf \'%s\\n\' "$admin_password" | bcrypt_password_hash' in source
    assert "bcrypt_password_hasher_available" in library
    assert "htpasswd -niBC 12 ''" in library
    assert "crypt.METHOD_BLOWFISH" in library


def test_platform_shell_is_valid() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
