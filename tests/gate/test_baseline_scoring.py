"""Hermetic contracts for the standalone development baseline scorer."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_SCORER = REPO_ROOT / "scripts" / "score-baseline.py"
REVISION = "abcdef0123456789abcdef0123456789abcdef01"
DIGEST = "sha256:" + "a" * 64
RUN_ID = "baseline-20261002"
NAMESPACE = "url-shortener-dev"


@pytest.fixture(scope="session")
def baseline_scorer() -> ModuleType:
    module_name = "resilience_gate_baseline_scorer"
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, BASELINE_SCORER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class ScriptedReader:
    def __init__(self, *, instant: list[object], range_: list[object]) -> None:
        self.instant = instant
        self.range = range_
        self.queries: list[tuple[str, str]] = []

    def query_instant(self, expression: str, at: datetime) -> object:
        self.queries.append(("instant", expression))
        assert self.instant, f"unexpected instant query: {expression}"
        result = self.instant.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def query_range(
        self, expression: str, start: datetime, end: datetime, step_seconds: int = 15
    ) -> object:
        self.queries.append(("range", expression))
        assert self.range, f"unexpected range query: {expression}"
        result = self.range.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def instant(baseline_scorer: ModuleType, at: datetime, value: float) -> object:
    return baseline_scorer.chaos.QueryResult(
        kind="instant",
        expression="synthetic",
        series=(
            baseline_scorer.chaos.TimeSeries(
                labels={}, samples=(baseline_scorer.chaos.Sample(timestamp=at, value=value),)
            ),
        ),
    )


def range_(baseline_scorer: ModuleType, window: object, values: tuple[float, ...]) -> object:
    start = window.start
    end = window.end
    span = (end - start) / (len(values) - 1)
    return baseline_scorer.chaos.QueryResult(
        kind="range",
        expression="synthetic",
        series=(
            baseline_scorer.chaos.TimeSeries(
                labels={},
                samples=tuple(
                    baseline_scorer.chaos.Sample(
                        timestamp=start + span * index, value=value
                    )
                    for index, value in enumerate(values)
                ),
            ),
        ),
    )


def evaluate_with_complete_evidence(baseline_scorer: ModuleType) -> tuple[object, ScriptedReader]:
    window = baseline_scorer.make_baseline_window(
        "2026-10-02T00:00:00Z", "2026-10-02T00:01:30Z"
    )
    reader = ScriptedReader(
        instant=[instant(baseline_scorer, window.end, 30), instant(baseline_scorer, window.end, 0)],
        range_=[
            range_(baseline_scorer, window, (0.08, 0.1, 0.12, 0.16, 0.2)),
            range_(baseline_scorer, window, (1, 1, 1, 1, 1)),
            range_(baseline_scorer, window, (1, 1, 1, 1, 1)),
        ],
    )
    card = baseline_scorer.evaluate_baseline(
        client=reader,
        namespace=NAMESPACE,
        source_revision=REVISION,
        release_digest=DIGEST,
        run_id=RUN_ID,
        started_at=window.start,
        ended_at=window.end,
        generated_at=datetime(2026, 10, 2, 0, 4, tzinfo=timezone.utc),
    )
    return card, reader


def test_complete_fresh_baseline_telemetry_passes(baseline_scorer: ModuleType) -> None:
    card, reader = evaluate_with_complete_evidence(baseline_scorer)

    payload = card.as_dict()
    baseline_scorer.validate_baseline_scorecard_shape(payload)
    assert payload["schema_version"] == "resilience-gate.baseline-scorecard/v1"
    assert payload["scenario"] == "baseline"
    assert payload["verdict"] == "pass"
    assert payload["release"] == {
        "revision": REVISION,
        "image_digest": DIGEST,
        "run_id": RUN_ID,
    }
    assert payload["window"] == {
        "started_at": "2026-10-02T00:00:00Z",
        "ended_at": "2026-10-02T00:01:30Z",
        "duration_seconds": 90,
    }
    assert [check["id"] for check in payload["checks"]] == [
        "root-get-traffic",
        "application-5xx",
        "root-get-p95-latency",
        "postgres-ready",
        "redis-ready",
        "release-identity",
    ]
    assert any('handler="/", method="GET"' in expression for _, expression in reader.queries)
    assert all(NAMESPACE in expression for _, expression in reader.queries)


def test_missing_and_stale_evidence_fail_closed(baseline_scorer: ModuleType) -> None:
    window = baseline_scorer.make_baseline_window(
        "2026-10-02T00:00:00Z", "2026-10-02T00:01:30Z"
    )
    missing = baseline_scorer.chaos.MissingEvidenceError("no matching traffic series")
    stale_samples = tuple(
        baseline_scorer.chaos.Sample(
            timestamp=window.start + timedelta(seconds=10 * index), value=0.1
        )
        for index in range(3)
    )
    stale = baseline_scorer.chaos.QueryResult(
        kind="range",
        expression="synthetic",
        series=(baseline_scorer.chaos.TimeSeries(labels={}, samples=stale_samples),),
    )
    reader = ScriptedReader(
        instant=[missing, instant(baseline_scorer, window.end, 0)],
        range_=[
            stale,
            range_(baseline_scorer, window, (1, 1, 1, 1, 1)),
            range_(baseline_scorer, window, (1, 1, 1, 1, 1)),
        ],
    )

    card = baseline_scorer.evaluate_baseline(
        client=reader,
        namespace=NAMESPACE,
        source_revision=REVISION,
        release_digest=DIGEST,
        run_id=RUN_ID,
        started_at=window.start,
        ended_at=window.end,
    )

    checks = {check.identifier: check for check in card.checks}
    assert card.verdict == "fail"
    assert checks["root-get-traffic"].evidence_error == "missing_evidence"
    assert checks["root-get-p95-latency"].evidence_error == "stale_evidence"


def test_window_and_identity_inputs_are_strict(baseline_scorer: ModuleType) -> None:
    with pytest.raises(baseline_scorer.chaos.EvidenceError, match="ending in Z"):
        baseline_scorer.make_baseline_window(
            "2026-10-02T00:00:00+05:30", "2026-10-02T00:03:00Z"
        )
    with pytest.raises(baseline_scorer.chaos.EvidenceError, match="at least"):
        baseline_scorer.make_baseline_window(
            "2026-10-02T00:00:00Z", "2026-10-02T00:00:30Z"
        )
    with pytest.raises(baseline_scorer.chaos.EvidenceError, match="no more than"):
        baseline_scorer.make_baseline_window(
            "2026-10-02T00:00:00Z", "2026-10-02T00:02:31Z"
        )
    with pytest.raises(baseline_scorer.chaos.EvidenceError, match="source revision"):
        baseline_scorer.evaluate_baseline(
            client=ScriptedReader(instant=[], range_=[]),
            namespace=NAMESPACE,
            source_revision="main",
            release_digest=DIGEST,
            run_id=RUN_ID,
            started_at="2026-10-02T00:00:00Z",
            ended_at="2026-10-02T00:01:30Z",
        )


def test_cli_returns_sanitized_failure_without_contacting_prometheus() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(BASELINE_SCORER),
            "--run-id",
            RUN_ID,
            "--namespace",
            NAMESPACE,
            "--source-revision",
            "not-a-sha",
            "--release-digest",
            DIGEST,
            "--started-at",
            "2026-10-02T00:00:00Z",
            "--ended-at",
            "2026-10-02T00:01:30Z",
            "--prom",
            "https://user:do-not-echo@example.test",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["verdict"] == "fail"
    assert payload["release"]["revision"] is None
    assert "do-not-echo" not in result.stdout
    assert payload["checks"][0]["evidence_error"] == "invalid_evidence"
