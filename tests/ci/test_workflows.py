"""C085 static contracts for a credential-safe scorer image delivery path."""

from __future__ import annotations

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPOSITORY_ROOT / ".github" / "workflows"
DELIVERY_WORKFLOWS = (
    "build-push.yaml",
    "build-radius-signer.yaml",
    "build-gate-runner.yaml",
)


def workflow(name: str) -> tuple[dict, str]:
    raw = (WORKFLOWS / name).read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict)
    return parsed, raw


def checkout_steps(job: dict) -> list[dict]:
    return [
        step for step in job["steps"]
        if isinstance(step, dict) and step.get("uses") == "actions/checkout@v4"
    ]


def test_pull_request_validation_never_receives_publish_credentials() -> None:
    for name in DELIVERY_WORKFLOWS:
        parsed, raw = workflow(name)
        validate = parsed["jobs"]["validate"]
        publish = parsed["jobs"]["publish"]
        assert validate["permissions"] == {"contents": "read"}
        assert validate["permissions"].get("id-token") is None
        assert "github.event_name == 'push'" in publish["if"]
        assert "github.ref == 'refs/heads/main'" in publish["if"]
        assert publish["permissions"] == {"contents": "read", "id-token": "write"}
        assert "google-github-actions/auth@v2" not in str(validate)
        assert "contents: write" not in raw
        assert "git push" not in raw
        assert "ajprojectplatform" not in raw
        assert "amoghjay" not in raw


def test_delivery_waits_for_validation_and_records_a_verified_digest() -> None:
    for name in DELIVERY_WORKFLOWS:
        parsed, raw = workflow(name)
        publish = parsed["jobs"]["publish"]
        assert publish["needs"] == "validate"
        assert "push: true" in raw
        assert "sha-${{ github.sha }}" in raw
        assert ":latest" not in raw
        assert "cosign sign --yes" in raw
        assert "cosign verify" in raw
        assert "actions/upload-artifact@v4" in raw


def test_all_workflows_disable_checkout_credential_persistence() -> None:
    for name in (*DELIVERY_WORKFLOWS, "validate.yaml"):
        parsed, _ = workflow(name)
        for job in parsed["jobs"].values():
            steps = checkout_steps(job)
            assert steps, f"{name} has a job without an explicit checkout step"
            assert all(step.get("with", {}).get("persist-credentials") is False for step in steps)


def test_validation_workflow_is_credential_free_and_has_platform_tooling() -> None:
    parsed, raw = workflow("validate.yaml")
    assert "id-token: write" not in raw
    assert "google-github-actions/auth" not in raw
    assert "hashicorp/setup-terraform@v3" in raw
    assert "azure/setup-helm@v4" in raw
    assert "azure/setup-kubectl@v4" in raw
    assert parsed["permissions"] == {"contents": "read"}


def test_initial_gate_runner_packages_the_reviewed_scorer_without_mutable_tags() -> None:
    dockerfile = (REPOSITORY_ROOT / "docker" / "gate-runner" / "Dockerfile").read_text(encoding="utf-8")
    parsed, workflow_raw = workflow("build-gate-runner.yaml")
    assert "COPY kubernetes/chaos-experiments/score_experiment.py" in dockerfile
    assert "ENTRYPOINT [\"/opt/chaos-gate/score_experiment.py\"]" in dockerfile
    assert "orchestrate.sh" not in dockerfile
    assert "annotate.py" not in dockerfile
    assert "context: ." in workflow_raw
    assert "gate-runner" in workflow_raw
    assert ":v1" not in workflow_raw
    assert ":latest" not in workflow_raw
    build = next(step for step in parsed["jobs"]["publish"]["steps"] if step.get("id") == "build")
    upload = parsed["jobs"]["publish"]["steps"][-1]
    assert build["with"]["cache-from"].startswith("type=registry,")
    assert build["with"]["cache-to"].startswith("type=registry,")
    assert "cache-from" not in upload["with"]
    assert "cache-to" not in upload["with"]
