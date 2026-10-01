"""Static contracts that keep direct Chaos Mesh faults inside staging."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGING_NAMESPACE = "url-shortener-staging"
BOOTSTRAP = REPO_ROOT / "kubernetes" / "bootstrap"
EXPERIMENTS = REPO_ROOT / "kubernetes" / "chaos-experiments"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def assert_bounded_staging_pod_failure(
    document: dict, *, name: str, labels: dict[str, str]
) -> None:
    assert document["apiVersion"] == "chaos-mesh.org/v1alpha1"
    assert document["kind"] == "PodChaos"
    assert document["metadata"] == {
        "name": name,
        "namespace": STAGING_NAMESPACE,
    }

    spec = document["spec"]
    assert spec["action"] == "pod-failure"
    assert spec["mode"] == "one"
    assert spec["duration"] == "60s"
    assert spec["selector"]["namespaces"] == [STAGING_NAMESPACE]
    assert spec["selector"]["labelSelectors"] == labels


def test_chaos_mesh_requires_an_explicit_staging_namespace_opt_in() -> None:
    application = load_yaml(BOOTSTRAP / "chaos-mesh.yaml")
    namespace = load_yaml(BOOTSTRAP / "chaos-mesh-ns-annotation.yaml")

    assert application["kind"] == "Application"
    assert application["metadata"]["namespace"] == "argocd"
    assert application["spec"]["destination"]["namespace"] == "chaos-mesh"
    assert application["spec"]["source"]["repoURL"] == "https://charts.chaos-mesh.org"
    assert application["spec"]["source"]["chart"] == "chaos-mesh"
    assert application["spec"]["source"]["targetRevision"] == "2.8.2"
    assert application["spec"]["syncPolicy"]["syncOptions"] == [
        "CreateNamespace=true",
        "ServerSideApply=true",
    ]
    assert application["spec"]["ignoreDifferences"] == [
        {
            "group": "apps",
            "kind": "Deployment",
            "jsonPointers": ["/status/terminatingReplicas"],
        }
    ]

    values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])
    assert values["enableProfiling"] is False
    assert values["controllerManager"]["enableFilterNamespace"] is True
    assert values["controllerManager"]["enabledControllers"] == ["podchaos", "workflow"]
    assert values["dashboard"]["create"] is False
    assert values["dnsServer"]["create"] is False
    assert namespace["metadata"]["name"] == STAGING_NAMESPACE
    assert namespace["metadata"]["annotations"]["chaos-mesh.org/inject"] == "enabled"


def test_postgresql_fault_is_bounded_to_the_staging_primary() -> None:
    assert_bounded_staging_pod_failure(
        load_yaml(EXPERIMENTS / "01-postgres-pod-failure.yaml"),
        name="postgres-pod-failure",
        labels={
            "app.kubernetes.io/name": "postgresql",
            "app.kubernetes.io/instance": STAGING_NAMESPACE,
            "app.kubernetes.io/component": "primary",
        },
    )


def test_redis_fault_is_bounded_to_the_staging_master() -> None:
    assert_bounded_staging_pod_failure(
        load_yaml(EXPERIMENTS / "03-redis-pod-failure.yaml"),
        name="redis-pod-failure",
        labels={
            "app.kubernetes.io/name": "redis",
            "app.kubernetes.io/instance": STAGING_NAMESPACE,
            "app.kubernetes.io/component": "master",
        },
    )


def test_signer_fault_is_bounded_to_the_staging_signer() -> None:
    assert_bounded_staging_pod_failure(
        load_yaml(EXPERIMENTS / "04-signer-pod-failure.yaml"),
        name="signer-pod-failure",
        labels={
            "app": "radius-signer",
            "app.kubernetes.io/name": "radius-signer",
            "app.kubernetes.io/component": "signer",
            "app.kubernetes.io/part-of": "resilience-gate",
        },
    )
