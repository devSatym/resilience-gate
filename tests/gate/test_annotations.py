"""Grafana annotations are useful evidence, never a promotion dependency."""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ANNOTATE_PATH = REPO_ROOT / "kubernetes" / "chaos-experiments" / "annotate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("resilience_gate_annotation", ANNOTATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_annotation_credentials_skips_without_a_network_request(monkeypatch, capsys) -> None:
    module = load_module()
    monkeypatch.delenv("GRAFANA_PASSWORD", raising=False)
    monkeypatch.delenv("GRAFANA_TOKEN", raising=False)

    def no_request(*_args, **_kwargs):
        raise AssertionError("annotation attempted a request without credentials")

    monkeypatch.setattr(module.urllib.request, "urlopen", no_request)

    assert module.main(["--verdict", "pass"]) == 0
    assert "skipping" in capsys.readouterr().out


def test_annotation_uses_a_release_window_and_never_exposes_the_password(monkeypatch) -> None:
    module = load_module()
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def record(request, *, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setenv("GRAFANA_URL", "http://grafana.test/")
    monkeypatch.setenv("GRAFANA_USER", "gate")
    monkeypatch.setenv("GRAFANA_PASSWORD", "do-not-log-me")
    monkeypatch.setattr(module.urllib.request, "urlopen", record)

    assert module.main(
        [
            "--verdict",
            "fail",
            "--failed",
            "redis",
            "--workflow",
            "chaos-gate-abc",
            "--start",
            "2026-10-01T12:00:00.123Z",
            "--end",
            "2026-10-01T12:00:01.456Z",
        ]
    ) == 0

    request, timeout = requests.pop()
    body = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://grafana.test/api/annotations"
    assert timeout == 10
    assert body == {
        "time": 1790856000123,
        "timeEnd": 1790856001456,
        "tags": ["chaos-gate", "verdict:fail"],
        "text": "chaos-gate FAIL — failed: redis (chaos-gate-abc)",
    }
    assert request.get_header("Authorization") == "Basic " + base64.b64encode(
        b"gate:do-not-log-me"
    ).decode()


def test_annotation_error_is_explicitly_non_fatal(monkeypatch, capsys) -> None:
    module = load_module()
    monkeypatch.setenv("GRAFANA_TOKEN", "short-lived-token")

    def unavailable(*_args, **_kwargs):
        raise OSError("offline test")

    monkeypatch.setattr(module.urllib.request, "urlopen", unavailable)

    assert module.main(["--verdict", "pass", "--workflow", "chaos-gate-abc"]) == 0
    output = capsys.readouterr().out
    assert "non-fatal" in output
    assert "short-lived-token" not in output
