from __future__ import annotations

import json
from pathlib import Path
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CHART = REPO_ROOT / "helm" / "observability"


def render_chart() -> list[dict]:
    result = subprocess.run(
        ("helm", "template", "observability", str(CHART), "--namespace", "monitoring"),
        capture_output=True,
        check=True,
        cwd=REPO_ROOT,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def dashboard_json(path: Path, key: str) -> dict:
    text = path.read_text(encoding="utf-8")
    block = text.split(f"  {key}: |\n", 1)[1]
    payload = "\n".join(line[4:] for line in block.splitlines() if line.startswith("    "))
    # Helm emits these Grafana legend placeholders verbatim; normalize them
    # only for JSON syntax validation in this source-level test.
    payload = payload.replace('{{ "{{handler}} {{method}}" }}', "{{handler}} {{method}}")
    payload = payload.replace('{{ "{{handler}}" }}', "{{handler}}")
    payload = payload.replace('{{ "{{dependency}}" }}', "{{dependency}}")
    return json.loads(payload)


def test_chart_lock_pins_supported_telemetry_components() -> None:
    lock = yaml.safe_load((CHART / "Chart.lock").read_text(encoding="utf-8"))
    versions = {item["name"]: item["version"] for item in lock["dependencies"]}
    assert versions == {
        "kube-prometheus-stack": "91.4.0",
        "loki": "7.3.0",
        "alloy": "1.12.1",
    }
    assert {
        archive.name
        for archive in (CHART / "charts").glob("*.tgz")
    } == {
        "kube-prometheus-stack-91.4.0.tgz",
        "loki-7.3.0.tgz",
        "alloy-1.12.1.tgz",
    }


def test_metrics_and_logs_have_explicit_bounded_configuration() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    prometheus = values["kube-prometheus-stack"]["prometheus"]["prometheusSpec"]
    assert prometheus["storageSpec"]["volumeClaimTemplate"]["spec"]["resources"]["requests"]["storage"] == "10Gi"
    assert prometheus["serviceMonitorSelector"] == {"matchLabels": {"release": "observability"}}
    assert values["loki"]["loki"]["limits_config"]["retention_period"] == "72h"
    assert values["loki"]["chunksCache"] == {"enabled": True, "allocatedMemory": 1024}
    assert "promtail" not in values

    alloy = (CHART / "templates" / "alloy-configmap.yaml").read_text(encoding="utf-8")
    assert 'loki.source.kubernetes "pods"' in alloy
    assert "loki.write \"default\"" in alloy
    assert 'cluster = {{ .Values.clusterName | quote }},' in alloy
    assert "hostPath:" not in alloy

    documents = render_chart()
    chunks_cache = next(
        document
        for document in documents
        if document["kind"] == "StatefulSet"
        and document["metadata"]["name"] == "observability-loki-chunks-cache"
    )
    memcached = next(
        container
        for container in chunks_cache["spec"]["template"]["spec"]["containers"]
        if container["name"] == "memcached"
    )
    assert memcached["args"][0] == "-m 1024"
    assert memcached["resources"] == {
        "limits": {"memory": "1229Mi"},
        "requests": {"cpu": "500m", "memory": "1229Mi"},
    }


def test_service_monitors_and_dashboards_cover_the_application_contract() -> None:
    monitors = [
        document
        for document in render_chart()
        if document["kind"] == "ServiceMonitor"
        and document["metadata"]["name"].startswith("url-shortener-")
    ]
    assert {monitor["metadata"]["name"] for monitor in monitors} == {
        "url-shortener-url-shortener-dev",
        "url-shortener-url-shortener-staging",
        "url-shortener-url-shortener-prod",
    }
    for monitor in monitors:
        spec = monitor["spec"]
        assert spec["sampleLimit"] == 10000
        assert spec["labelLimit"] == 30
        assert spec["endpoints"][0]["path"] == "/metrics"
        assert "sampleLimit" not in spec["endpoints"][0]
        assert "labelLimit" not in spec["endpoints"][0]

    application = dashboard_json(CHART / "templates" / "dashboard-cm.yaml", "url-shortener.json")
    chaos = dashboard_json(CHART / "templates" / "chaos-demo-dashboard-cm.yaml", "chaos-demo.json")
    application_queries = json.dumps(application)
    chaos_queries = json.dumps(chaos)
    assert "payment_replay_attempts_total" in application_queries
    assert "payment_facilitator_duration_seconds_bucket" in application_queries
    assert "|!=" in chaos_queries


def test_gitops_bootstrap_orders_monitoring_before_its_secret() -> None:
    kustomization = yaml.safe_load((REPO_ROOT / "kubernetes/bootstrap/kustomization.yaml").read_text(encoding="utf-8"))
    assert "observability.yaml" in kustomization["resources"]
    assert "secrets/external-secrets-monitoring.yaml" in kustomization["resources"]
    external_secret = (REPO_ROOT / "kubernetes/bootstrap/secrets/external-secrets-monitoring.yaml").read_text(encoding="utf-8")
    assert 'argocd.argoproj.io/sync-wave: "3"' in external_secret
    assert "name: resilience-gate-secrets" in external_secret


def test_observability_retains_ssa_and_ignores_gke_deployment_status_field() -> None:
    manifests = (
        REPO_ROOT / "kubernetes/bootstrap/observability.yaml",
        REPO_ROOT / "platform_setup_scripts/templates/kubernetes/bootstrap/observability.yaml.tmpl",
    )
    for manifest in manifests:
        application = next(
            document
            for document in yaml.safe_load_all(manifest.read_text(encoding="utf-8"))
            if document and document["kind"] == "Application"
        )
        assert application["spec"]["syncPolicy"]["syncOptions"] == [
            "CreateNamespace=false",
            "ServerSideApply=true",
        ]
        assert application["spec"]["ignoreDifferences"] == [
            {
                "group": "apps",
                "kind": "Deployment",
                "jsonPointers": ["/status/terminatingReplicas"],
            }
        ]
