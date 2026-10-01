from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CHART = REPO_ROOT / "helm" / "observability"


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
    assert "promtail" not in values

    alloy = (CHART / "templates" / "alloy-configmap.yaml").read_text(encoding="utf-8")
    assert 'loki.source.kubernetes "pods"' in alloy
    assert "loki.write \"default\"" in alloy
    assert "hostPath:" not in alloy


def test_service_monitors_and_dashboards_cover_the_application_contract() -> None:
    service_monitor = (CHART / "templates" / "servicemonitor.yaml").read_text(encoding="utf-8")
    assert "release: observability" in service_monitor
    assert "path: /metrics" in service_monitor
    assert "sampleLimit: 10000" in service_monitor

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
