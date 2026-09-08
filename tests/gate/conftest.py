"""Hermetic helpers for the chaos-gate scorer tests.

These helpers construct validated in-memory Prometheus results. They never
start a socket or depend on a cluster, matching the scorer's injectable reader
boundary.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCORER_PATH = REPO_ROOT / "kubernetes" / "chaos-experiments" / "score_experiment.py"


@pytest.fixture(scope="session")
def scorer() -> ModuleType:
    """Load the standalone scorer module once under a stable test-local name."""

    module_name = "resilience_gate_chaos_scorer"
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, SCORER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class ScriptedReader:
    """Return query results in scorer evaluation order and record expressions."""

    def __init__(self, *, instant: Iterable[object] = (), range_: Iterable[object] = ()):
        self.instant = list(instant)
        self.range = list(range_)
        self.queries: list[tuple[str, str]] = []

    def query_instant(self, expression: str, at: datetime) -> object:
        self.queries.append(("instant", expression))
        assert self.instant, f"unexpected instant query: {expression}"
        return self.instant.pop(0)

    def query_range(
        self, expression: str, start: datetime, end: datetime, step_seconds: int = 15
    ) -> object:
        self.queries.append(("range", expression))
        assert self.range, f"unexpected range query: {expression}"
        return self.range.pop(0)


@pytest.fixture
def inject_at() -> datetime:
    return datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def instant_result(scorer: ModuleType, at: datetime, value: float) -> object:
    return scorer.QueryResult(
        kind="instant",
        expression="synthetic",
        series=(
            scorer.TimeSeries(
                labels={}, samples=(scorer.Sample(timestamp=at, value=value),)
            ),
        ),
    )


def range_result(
    scorer: ModuleType, window: object, values: tuple[float, ...]
) -> object:
    assert len(values) >= 3
    start = window.start
    end = window.end
    span = (end - start) / (len(values) - 1)
    samples = tuple(
        scorer.Sample(timestamp=start + span * index, value=value)
        for index, value in enumerate(values)
    )
    return scorer.QueryResult(
        kind="range",
        expression="synthetic",
        series=(scorer.TimeSeries(labels={}, samples=samples),),
    )

