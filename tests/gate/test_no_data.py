"""Fail-closed controls for absent, stale, NaN, and sparse evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


FIXTURES = Path(__file__).with_name("fixtures")


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_absent_series_is_rejected_instead_of_scored_as_zero(scorer) -> None:
    with pytest.raises(scorer.MissingEvidenceError):
        scorer.parse_prometheus_result(
            fixture("absent.json"), expected_kind="range", expression="dependency_up"
        )


def test_nan_value_is_rejected_instead_of_dropped_from_aggregation(scorer) -> None:
    with pytest.raises(scorer.NonFiniteEvidenceError):
        scorer.parse_prometheus_result(
            fixture("nan.json"), expected_kind="instant", expression="p95_latency"
        )


def test_stale_and_insufficient_range_samples_are_rejected(scorer, inject_at) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    stale = scorer.parse_prometheus_result(
        fixture("stale.json"), expected_kind="range", expression="dependency_up"
    )
    sparse = scorer.parse_prometheus_result(
        fixture("insufficient.json"), expected_kind="range", expression="dependency_up"
    )

    with pytest.raises(scorer.StaleEvidenceError, match="ends before"):
        scorer.validate_range_coverage(stale, window)
    with pytest.raises(scorer.InsufficientEvidenceError, match="at least"):
        scorer.validate_range_coverage(sparse, window)


def test_stale_instant_sample_is_rejected(scorer, inject_at, instant_evidence) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    stale = instant_evidence(window.start, 0)

    with pytest.raises(scorer.StaleEvidenceError, match="stale"):
        scorer.validate_instant_freshness(stale, window.end)


def test_evaluation_records_bad_evidence_as_a_failed_check_and_continues(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence, stale_range_evidence
) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    reader = scripted_reader(
        instant=[
            instant_evidence(window.end, 180),
            instant_evidence(window.end, 0),
            instant_evidence(window.end, 0),
        ],
        range_=[
            stale_range_evidence(window, 1),
            range_evidence(window, (1, 0, 1)),
        ],
    )

    card = scorer.evaluate_experiment("postgres-pod-failure", inject_at, 60, client=reader)

    outage = next(check for check in card.checks if check.identifier == "postgres-outage-observed")
    recovery = next(check for check in card.checks if check.identifier == "postgres-recovered")
    assert card.verdict == "fail"
    assert outage.verdict == "fail"
    assert outage.observed is None
    assert outage.evidence_error == "stale_evidence"
    assert recovery.verdict == "pass", "a bad rule must not hide later evidence"
