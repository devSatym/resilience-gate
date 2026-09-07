"""Workflow contracts for ordered fault and recovery observation windows."""

from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / "kubernetes" / "chaos-experiments" / "workflow.yaml"
STAGING_NAMESPACE = "url-shortener-staging"
FAULTS = ("postgres", "redis", "signer")
SELECTOR_LABELS = {
    "postgres": {
        "app.kubernetes.io/name": "postgresql",
        "app.kubernetes.io/instance": STAGING_NAMESPACE,
        "app.kubernetes.io/component": "primary",
    },
    "redis": {
        "app.kubernetes.io/name": "redis",
        "app.kubernetes.io/instance": STAGING_NAMESPACE,
        "app.kubernetes.io/component": "master",
    },
    "signer": {
        "app": "radius-signer",
        "app.kubernetes.io/name": "radius-signer",
        "app.kubernetes.io/component": "signer",
        "app.kubernetes.io/part-of": "resilience-gate",
    },
}


def load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def seconds(duration: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)s", duration)
    assert match, f"workflow deadline must be a positive seconds duration, got {duration!r}"
    return int(match.group(1))


def test_workflow_has_explicit_baseline_fault_and_recovery_phases() -> None:
    workflow = load_workflow()

    assert workflow["apiVersion"] == "chaos-mesh.org/v1alpha1"
    assert workflow["kind"] == "Workflow"
    assert workflow["metadata"]["namespace"] == STAGING_NAMESPACE
    assert workflow["metadata"]["generateName"] == "chaos-gate-"
    assert workflow["spec"]["entry"] == "gate-serial"

    templates = {template["name"]: template for template in workflow["spec"]["templates"]}
    serial = templates["gate-serial"]
    assert serial["templateType"] == "Serial"
    assert serial["children"] == [
        "baseline",
        "postgres",
        "postgres-recovery",
        "redis",
        "redis-recovery",
        "signer",
        "signer-recovery",
    ]
    assert templates["baseline"]["templateType"] == "Suspend"

    for fault in FAULTS:
        assert templates[fault]["templateType"] == "PodChaos"
        assert templates[f"{fault}-recovery"]["templateType"] == "Suspend"
        assert seconds(templates[f"{fault}-recovery"]["deadline"]) > 0


def test_workflow_fault_windows_are_bounded_and_scoped_to_staging() -> None:
    workflow = load_workflow()
    templates = {template["name"]: template for template in workflow["spec"]["templates"]}

    for fault in FAULTS:
        template = templates[fault]
        assert seconds(template["deadline"]) == 60
        chaos = template["podChaos"]
        assert "duration" not in chaos
        assert chaos["action"] == "pod-failure"
        assert chaos["mode"] == "one"
        assert chaos["selector"]["namespaces"] == [STAGING_NAMESPACE]
        assert chaos["selector"]["labelSelectors"] == SELECTOR_LABELS[fault]


def test_workflow_deadline_covers_all_declared_child_windows() -> None:
    workflow = load_workflow()
    templates = {template["name"]: template for template in workflow["spec"]["templates"]}
    serial = templates[workflow["spec"]["entry"]]

    child_total = sum(seconds(templates[name]["deadline"]) for name in serial["children"])
    assert seconds(serial["deadline"]) >= child_total
