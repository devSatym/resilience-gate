"""Contracts for parsing Prometheus query evidence without a live endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


def range_payload(*, values: list[list[object]]) -> dict[str, object]:
    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [{"metric": {"namespace": "url-shortener-staging"}, "values": values}],
        },
    }


def instant_payload(*, value: list[object]) -> dict[str, object]:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {"namespace": "url-shortener-staging"}, "value": value}],
        },
    }


def test_range_response_is_normalized_to_finite_utc_samples(scorer) -> None:
    result = scorer.parse_prometheus_result(
        range_payload(values=[[1790856000, "0"], [1790856015, "1"]]),
        expected_kind="range",
        expression="up",
    )

    assert result.kind == "range"
    assert result.series[0].labels == {"namespace": "url-shortener-staging"}
    assert [sample.value for sample in result.series[0].samples] == [0.0, 1.0]
    assert result.series[0].samples[0].timestamp == datetime(
        2026, 10, 1, 12, 0, tzinfo=timezone.utc
    )


def test_instant_response_requires_the_expected_prometheus_result_type(scorer) -> None:
    with pytest.raises(scorer.QueryResponseError, match="expected Prometheus vector"):
        scorer.parse_prometheus_result(
            range_payload(values=[[1790856000, "1"]]),
            expected_kind="instant",
            expression="up",
        )


def test_empty_vector_is_missing_evidence_not_zero(scorer) -> None:
    payload = {"status": "success", "data": {"resultType": "vector", "result": []}}

    with pytest.raises(scorer.MissingEvidenceError):
        scorer.parse_prometheus_result(payload, expected_kind="instant", expression="up")


def test_malformed_response_and_prometheus_error_are_rejected(scorer) -> None:
    with pytest.raises(scorer.QueryResponseError, match="query failed"):
        scorer.parse_prometheus_result(
            {"status": "error", "errorType": "bad_data", "error": "invalid query"},
            expected_kind="instant",
            expression="bad(",
        )

    with pytest.raises(scorer.QueryResponseError, match="must be a \\[timestamp, value\\] pair"):
        scorer.parse_prometheus_result(
            instant_payload(value=[1790856000]), expected_kind="instant", expression="up"
        )


def test_window_requires_explicit_utc_time_and_positive_duration(scorer) -> None:
    window = scorer.make_window("2026-10-01T12:00:00Z", 60, 40)
    assert scorer.format_utc_timestamp(window.start) == "2026-10-01T11:59:40Z"
    assert scorer.format_utc_timestamp(window.end) == "2026-10-01T12:01:40Z"

    with pytest.raises(scorer.EvidenceError, match="ending in Z"):
        scorer.make_window("2026-10-01T12:00:00+05:30", 60, 40)
    with pytest.raises(scorer.EvidenceError, match="positive"):
        scorer.make_window("2026-10-01T12:00:00Z", 0, 40)

