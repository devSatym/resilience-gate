#!/usr/bin/env python3
"""Fail-closed scoring for bounded chaos experiments.

The scorer deliberately treats telemetry as evidence rather than a best-effort
dashboard query. A missing series, malformed Prometheus response, non-finite
number, stale sample, or insufficient range coverage is a failed check. That
keeps a quiet Prometheus outage from being mistaken for a healthy release.

The module has no cloud or Kubernetes client. Its only optional I/O is the
Prometheus HTTP API used by the command-line entry point. Tests inject a
``PrometheusReader`` implementation with synthetic query results.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol, Sequence


# C079 — query and result contracts ----------------------------------------

PROM = "http://observability-kube-prometh-prometheus.monitoring.svc:9090"
DEFAULT_NAMESPACE = "url-shortener-staging"
DEFAULT_STEP_SECONDS = 15
DEFAULT_TIMEOUT_SECONDS = 15

# C083 tightens range validation with these explicit limits. They are kept
# here, rather than inferred from a query, so changes require a reviewed
# threshold change.
MIN_RANGE_SAMPLES = 3
MAX_SAMPLE_GAP_SECONDS = 75
MAX_SAMPLE_STALENESS_SECONDS = 60

SCHEMA_VERSION = "resilience-gate.scorecard/v1"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class EvidenceError(RuntimeError):
    """A telemetry contract failure that must fail the gate."""

    code = "invalid_evidence"


class QueryTransportError(EvidenceError):
    code = "query_transport_error"


class QueryResponseError(EvidenceError):
    code = "query_response_error"


class MissingEvidenceError(EvidenceError):
    code = "missing_evidence"


class NonFiniteEvidenceError(EvidenceError):
    code = "non_finite_evidence"


class StaleEvidenceError(EvidenceError):
    code = "stale_evidence"


class InsufficientEvidenceError(EvidenceError):
    code = "insufficient_evidence"


@dataclass(frozen=True)
class Sample:
    """One finite Prometheus sample, normalized to a UTC timestamp."""

    timestamp: datetime
    value: float


@dataclass(frozen=True)
class TimeSeries:
    """A non-empty sequence returned for one Prometheus label set."""

    labels: Mapping[str, str]
    samples: tuple[Sample, ...]


@dataclass(frozen=True)
class QueryResult:
    """A validated Prometheus vector or matrix result."""

    kind: Literal["instant", "range"]
    expression: str
    series: tuple[TimeSeries, ...]


@dataclass(frozen=True)
class ExperimentWindow:
    """The bounded observation window anchored to the actual fault start."""

    inject_at: datetime
    duration_seconds: int
    settle_seconds: int
    lead_seconds: int = 20

    @property
    def start(self) -> datetime:
        return self.inject_at - timedelta(seconds=self.lead_seconds)

    @property
    def end(self) -> datetime:
        return self.inject_at + timedelta(
            seconds=self.duration_seconds + self.settle_seconds
        )

    @property
    def seconds(self) -> int:
        """The fault-plus-settle duration used in counter lookbacks."""

        return self.duration_seconds + self.settle_seconds


class PrometheusReader(Protocol):
    """Small injectable boundary around Prometheus for hermetic scorer tests."""

    def query_range(
        self,
        expression: str,
        start: datetime,
        end: datetime,
        step_seconds: int = DEFAULT_STEP_SECONDS,
    ) -> QueryResult: ...

    def query_instant(self, expression: str, at: datetime) -> QueryResult: ...


def parse_utc_timestamp(value: str) -> datetime:
    """Accept an explicit RFC3339 UTC timestamp and reject ambiguous input."""

    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError("timestamp must be an RFC3339 UTC value ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"invalid RFC3339 timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise EvidenceError("timestamp must be UTC")
    return parsed.astimezone(timezone.utc)


def format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise EvidenceError("timestamp must include a timezone")
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def make_window(
    inject_at: str | datetime,
    duration_seconds: int,
    settle_seconds: int,
) -> ExperimentWindow:
    """Build a bounded window; invalid timing is never coerced to a default."""

    if not isinstance(duration_seconds, int) or isinstance(duration_seconds, bool):
        raise EvidenceError("duration must be an integer number of seconds")
    if duration_seconds <= 0:
        raise EvidenceError("duration must be positive")
    if not isinstance(settle_seconds, int) or isinstance(settle_seconds, bool):
        raise EvidenceError("settle duration must be an integer number of seconds")
    if settle_seconds < 0:
        raise EvidenceError("settle duration may not be negative")

    parsed = parse_utc_timestamp(inject_at) if isinstance(inject_at, str) else inject_at
    if not isinstance(parsed, datetime) or parsed.tzinfo is None:
        raise EvidenceError("inject_at must be a timezone-aware datetime")
    return ExperimentWindow(
        inject_at=parsed.astimezone(timezone.utc),
        duration_seconds=duration_seconds,
        settle_seconds=settle_seconds,
    )


def _as_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise QueryResponseError(f"{context} must be an object")
    return value


def _as_finite_float(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise QueryResponseError(f"{context} must be a numeric value")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise QueryResponseError(f"{context} is not numeric") from exc
    if not math.isfinite(number):
        raise NonFiniteEvidenceError(f"{context} must be finite")
    return number


def _parse_sample(raw: Any, context: str) -> Sample:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 2:
        raise QueryResponseError(f"{context} must be a [timestamp, value] pair")
    epoch_seconds = _as_finite_float(raw[0], f"{context} timestamp")
    if epoch_seconds <= 0:
        raise QueryResponseError(f"{context} timestamp must be after the Unix epoch")
    try:
        timestamp = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise QueryResponseError(f"{context} timestamp is outside the supported range") from exc
    return Sample(timestamp=timestamp, value=_as_finite_float(raw[1], f"{context} value"))


def parse_prometheus_result(
    payload: Any,
    *,
    expected_kind: Literal["instant", "range"],
    expression: str,
) -> QueryResult:
    """Validate a complete Prometheus API response before scoring it.

    A successful HTTP request is not enough. Prometheus can return a warning,
    empty vector, NaN quantile, or unexpected result type; each is unsafe to
    interpret as a zero or pass.
    """

    root = _as_mapping(payload, "Prometheus response")
    if root.get("status") != "success":
        error_type = root.get("errorType", "unknown")
        detail = root.get("error", "Prometheus did not return success")
        raise QueryResponseError(f"Prometheus query failed ({error_type}): {detail}")
    data = _as_mapping(root.get("data"), "Prometheus response data")
    expected_type = "vector" if expected_kind == "instant" else "matrix"
    if data.get("resultType") != expected_type:
        raise QueryResponseError(
            f"expected Prometheus {expected_type} result, got {data.get('resultType')!r}"
        )
    raw_result = data.get("result")
    if not isinstance(raw_result, list):
        raise QueryResponseError("Prometheus data.result must be an array")
    if not raw_result:
        raise MissingEvidenceError("Prometheus returned no matching time series")

    parsed_series: list[TimeSeries] = []
    for index, raw_series in enumerate(raw_result):
        series = _as_mapping(raw_series, f"Prometheus result[{index}]")
        raw_labels = series.get("metric", {})
        labels_object = _as_mapping(raw_labels, f"Prometheus result[{index}].metric")
        labels: dict[str, str] = {}
        for key, value in labels_object.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise QueryResponseError("Prometheus labels must be string pairs")
            labels[key] = value

        if expected_kind == "instant":
            samples = (_parse_sample(series.get("value"), f"result[{index}].value"),)
        else:
            raw_values = series.get("values")
            if not isinstance(raw_values, list) or not raw_values:
                raise MissingEvidenceError(
                    f"Prometheus range result[{index}] has no samples"
                )
            samples = tuple(
                _parse_sample(raw, f"result[{index}].values[{sample_index}]")
                for sample_index, raw in enumerate(raw_values)
            )
            for prior, current in zip(samples, samples[1:]):
                if current.timestamp <= prior.timestamp:
                    raise QueryResponseError(
                        f"Prometheus range result[{index}] timestamps must strictly increase"
                    )
        parsed_series.append(TimeSeries(labels=labels, samples=samples))

    return QueryResult(kind=expected_kind, expression=expression, series=tuple(parsed_series))


class PrometheusHTTPClient:
    """Strict stdlib Prometheus client; only this adapter performs network I/O."""

    def __init__(self, base_url: str, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise EvidenceError("Prometheus URL must be an absolute HTTP(S) URL")
        if timeout_seconds <= 0:
            raise EvidenceError("Prometheus timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, path: str, params: Mapping[str, str]) -> Any:
        url = self.base_url + path + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise QueryTransportError(f"Prometheus request failed: {exc}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QueryResponseError("Prometheus returned invalid JSON") from exc

    def query_range(
        self,
        expression: str,
        start: datetime,
        end: datetime,
        step_seconds: int = DEFAULT_STEP_SECONDS,
    ) -> QueryResult:
        if step_seconds <= 0:
            raise EvidenceError("Prometheus range step must be positive")
        payload = self._request(
            "/api/v1/query_range",
            {
                "query": expression,
                "start": format_utc_timestamp(start),
                "end": format_utc_timestamp(end),
                "step": f"{step_seconds}s",
            },
        )
        return parse_prometheus_result(payload, expected_kind="range", expression=expression)

    def query_instant(self, expression: str, at: datetime) -> QueryResult:
        payload = self._request(
            "/api/v1/query",
            {"query": expression, "time": format_utc_timestamp(at)},
        )
        return parse_prometheus_result(payload, expected_kind="instant", expression=expression)


@dataclass(frozen=True)
class CheckDefinition:
    """One explicit, auditable metric assertion for a chaos experiment."""

    identifier: str
    name: str
    expression: str
    query_kind: Literal["instant", "range"]
    aggregation: Literal["value", "min", "max", "avg", "last"]
    operator: Literal["<", "<=", ">", ">=", "=="]
    threshold: float
    unit: str


@dataclass(frozen=True)
class ExperimentDefinition:
    identifier: str
    settle_seconds: int
    checks: tuple[CheckDefinition, ...]


@dataclass(frozen=True)
class CheckResult:
    identifier: str
    name: str
    verdict: Literal["pass", "fail"]
    observed: float | None
    operator: str
    threshold: float
    unit: str
    expression: str
    query_kind: Literal["instant", "range"]
    sample_count: int
    reason: str | None = None
    evidence_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "name": self.name,
            "verdict": self.verdict,
            "observed": self.observed,
            "operator": self.operator,
            "threshold": self.threshold,
            "unit": self.unit,
            "expression": self.expression,
            "query_kind": self.query_kind,
            "sample_count": self.sample_count,
            "reason": self.reason,
            "evidence_error": self.evidence_error,
        }


_OPERATORS = {
    "<": lambda actual, expected: actual < expected,
    "<=": lambda actual, expected: actual <= expected,
    ">": lambda actual, expected: actual > expected,
    ">=": lambda actual, expected: actual >= expected,
    "==": lambda actual, expected: math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-9),
}


def render_expression(check: CheckDefinition, *, namespace: str, window: ExperimentWindow) -> str:
    """Render only reviewer-owned placeholders; label braces remain literal."""

    if not namespace or namespace.strip() != namespace:
        raise EvidenceError("namespace must be a non-empty, trimmed value")
    try:
        return check.expression.format(namespace=namespace, window=window.seconds)
    except (KeyError, ValueError) as exc:
        raise EvidenceError(f"invalid query template for {check.identifier}") from exc


def _all_samples(result: QueryResult) -> tuple[Sample, ...]:
    return tuple(sample for series in result.series for sample in series.samples)


def aggregate(result: QueryResult, aggregation: str) -> tuple[float, int]:
    """Aggregate finite validated samples; no empty result silently becomes zero."""

    samples = _all_samples(result)
    if not samples:
        raise MissingEvidenceError("Prometheus result contains no samples")
    values = [sample.value for sample in samples]
    if aggregation == "value":
        if len(samples) != 1:
            raise InsufficientEvidenceError(
                "scalar query must return exactly one sample after aggregation"
            )
        return values[0], 1
    if aggregation == "min":
        return min(values), len(values)
    if aggregation == "max":
        return max(values), len(values)
    if aggregation == "avg":
        return sum(values) / len(values), len(values)
    if aggregation == "last":
        latest = max(samples, key=lambda item: item.timestamp)
        return latest.value, len(values)
    raise EvidenceError(f"unsupported aggregation: {aggregation}")


def validate_range_coverage(result: QueryResult, window: ExperimentWindow) -> None:
    """Reject range series that could hide a telemetry outage or stale scrape."""

    if result.kind != "range":
        raise QueryResponseError("range coverage validation requires a range result")
    latest_allowed_start = window.start + timedelta(seconds=MAX_SAMPLE_STALENESS_SECONDS)
    earliest_allowed_end = window.end - timedelta(seconds=MAX_SAMPLE_STALENESS_SECONDS)
    for index, series in enumerate(result.series):
        samples = series.samples
        if len(samples) < MIN_RANGE_SAMPLES:
            raise InsufficientEvidenceError(
                f"range series {index} has {len(samples)} samples; need at least {MIN_RANGE_SAMPLES}"
            )
        if samples[0].timestamp > latest_allowed_start:
            raise StaleEvidenceError("range evidence starts too late for the observation window")
        if samples[-1].timestamp < earliest_allowed_end:
            raise StaleEvidenceError("range evidence ends before the observation window")
        for prior, current in zip(samples, samples[1:]):
            if current.timestamp - prior.timestamp > timedelta(seconds=MAX_SAMPLE_GAP_SECONDS):
                raise StaleEvidenceError("range evidence contains a scrape gap beyond the limit")


def validate_instant_freshness(result: QueryResult, evaluated_at: datetime) -> None:
    """Require an instant vector to be a fresh single scalar at query time."""

    if result.kind != "instant":
        raise QueryResponseError("instant freshness validation requires an instant result")
    samples = _all_samples(result)
    if len(samples) != 1:
        raise InsufficientEvidenceError("instant query must return exactly one sample")
    age = abs((evaluated_at - samples[0].timestamp).total_seconds())
    if age > MAX_SAMPLE_STALENESS_SECONDS:
        raise StaleEvidenceError(
            f"instant evidence is stale by {age:.0f}s; limit is {MAX_SAMPLE_STALENESS_SECONDS}s"
        )


def _check_result_from_error(
    check: CheckDefinition, expression: str, error: EvidenceError | Exception
) -> CheckResult:
    return CheckResult(
        identifier=check.identifier,
        name=check.name,
        verdict="fail",
        observed=None,
        operator=check.operator,
        threshold=check.threshold,
        unit=check.unit,
        expression=expression,
        query_kind=check.query_kind,
        sample_count=0,
        reason=str(error),
        evidence_error=error.code if isinstance(error, EvidenceError) else "unexpected_error",
    )


def evaluate_check(
    check: CheckDefinition,
    *,
    client: PrometheusReader,
    namespace: str,
    window: ExperimentWindow,
) -> CheckResult:
    """Evaluate one rule, converting every telemetry problem into a failed check."""

    expression = render_expression(check, namespace=namespace, window=window)
    try:
        if check.query_kind == "range":
            result = client.query_range(expression, window.start, window.end)
            if result.kind != "range":
                raise QueryResponseError("reader returned a non-range result for a range query")
            validate_range_coverage(result, window)
        else:
            result = client.query_instant(expression, window.end)
            if result.kind != "instant":
                raise QueryResponseError("reader returned a non-instant result for an instant query")
            validate_instant_freshness(result, window.end)
        observed, sample_count = aggregate(result, check.aggregation)
        passed = _OPERATORS[check.operator](observed, check.threshold)
        return CheckResult(
            identifier=check.identifier,
            name=check.name,
            verdict="pass" if passed else "fail",
            observed=observed,
            operator=check.operator,
            threshold=check.threshold,
            unit=check.unit,
            expression=expression,
            query_kind=check.query_kind,
            sample_count=sample_count,
            reason=None if passed else "threshold_not_met",
        )
    except Exception as exc:  # fail closed, including an adapter implementation bug
        return _check_result_from_error(check, expression, exc)


# C080 — PostgreSQL traffic and recovery rules -----------------------------

POSTGRES_CHECKS = (
    CheckDefinition(
        identifier="meaningful-traffic",
        name="meaningful non-probe traffic flowed during the PostgreSQL fault",
        expression=(
            'sum(increase(http_requests_total{{namespace="{namespace}", '
            'handler!~"/(livez|ready|metrics)"}}[{window}s]))'
        ),
        query_kind="instant",
        aggregation="value",
        operator=">",
        threshold=50,
        unit="requests",
    ),
    CheckDefinition(
        identifier="app-restarts",
        name="the application did not restart during PostgreSQL unavailability",
        expression=(
            'max(increase(kube_pod_container_status_restarts_total{{namespace="{namespace}", '
            'container="url-shortener"}}[{window}s])) or vector(0)'
        ),
        query_kind="instant",
        aggregation="value",
        operator="<",
        threshold=0.5,
        unit="restarts",
    ),
    CheckDefinition(
        identifier="postgres-outage-observed",
        name="the PostgreSQL dependency was observed unavailable",
        expression=(
            'min(url_shortener_dependency_up{{namespace="{namespace}", dependency="postgres"}})'
        ),
        query_kind="range",
        aggregation="min",
        operator="==",
        threshold=0,
        unit="state",
    ),
    CheckDefinition(
        identifier="postgres-recovered",
        name="the application observed PostgreSQL recovery before the window ended",
        expression=(
            'min(url_shortener_dependency_up{{namespace="{namespace}", dependency="postgres"}})'
        ),
        query_kind="range",
        aggregation="last",
        operator="==",
        threshold=1,
        unit="state",
    ),
    CheckDefinition(
        identifier="postgres-clean-degradation",
        name="PostgreSQL unavailability did not produce unhandled /shorten 500 responses",
        expression=(
            'sum(increase(http_requests_total{{namespace="{namespace}", handler="/shorten", '
            'status="500"}}[{window}s])) or vector(0)'
        ),
        query_kind="instant",
        aggregation="value",
        operator="<",
        threshold=0.5,
        unit="responses",
    ),
)


# C081 — Redis fallback latency and recovery rules -------------------------

REDIS_CHECKS = (
    CheckDefinition(
        identifier="meaningful-traffic",
        name="meaningful non-probe traffic flowed during the Redis fault",
        expression=(
            'sum(increase(http_requests_total{{namespace="{namespace}", '
            'handler!~"/(livez|ready|metrics)"}}[{window}s]))'
        ),
        query_kind="instant",
        aggregation="value",
        operator=">",
        threshold=50,
        unit="requests",
    ),
    CheckDefinition(
        identifier="redis-fallback-observed",
        name="the application exercised the Redis-miss fallback path",
        expression=(
            'sum(increase(url_shortener_cache_misses_total{{namespace="{namespace}"}}[{window}s]))'
        ),
        query_kind="instant",
        aggregation="value",
        operator=">",
        threshold=0,
        unit="fallbacks",
    ),
    CheckDefinition(
        identifier="redirect-latency",
        name="redirect p95 stayed below the degraded-mode latency bound",
        expression=(
            'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket'
            '{{namespace="{namespace}", handler="/{{code}}"}}[1m])) by (le))'
        ),
        query_kind="range",
        aggregation="max",
        operator="<",
        threshold=1.2,
        unit="seconds",
    ),
    CheckDefinition(
        identifier="app-restarts",
        name="the application did not restart during Redis unavailability",
        expression=(
            'max(increase(kube_pod_container_status_restarts_total{{namespace="{namespace}", '
            'container="url-shortener"}}[{window}s])) or vector(0)'
        ),
        query_kind="instant",
        aggregation="value",
        operator="<",
        threshold=0.5,
        unit="restarts",
    ),
    CheckDefinition(
        identifier="redis-outage-observed",
        name="the Redis dependency was observed unavailable",
        expression='min(url_shortener_dependency_up{{namespace="{namespace}", dependency="redis"}})',
        query_kind="range",
        aggregation="min",
        operator="==",
        threshold=0,
        unit="state",
    ),
    CheckDefinition(
        identifier="redis-recovered",
        name="the application observed Redis recovery before the window ended",
        expression='min(url_shortener_dependency_up{{namespace="{namespace}", dependency="redis"}})',
        query_kind="range",
        aggregation="last",
        operator="==",
        threshold=1,
        unit="state",
    ),
)


# C082 — signer recovery and application-isolation rules -------------------

SIGNER_CHECKS = (
    CheckDefinition(
        identifier="signer-outage-observed",
        name="the signer readiness metric was observed unavailable",
        expression='min(signer_ready{{namespace="{namespace}"}})',
        query_kind="range",
        aggregation="min",
        operator="==",
        threshold=0,
        unit="state",
    ),
    CheckDefinition(
        identifier="signer-recovered",
        name="the signer became ready again before the observation window ended",
        expression='min(signer_ready{{namespace="{namespace}"}})',
        query_kind="range",
        aggregation="last",
        operator="==",
        threshold=1,
        unit="state",
    ),
    CheckDefinition(
        identifier="app-restarts",
        name="the application did not restart while the signer was unavailable",
        expression=(
            'max(increase(kube_pod_container_status_restarts_total{{namespace="{namespace}", '
            'container="url-shortener"}}[{window}s])) or vector(0)'
        ),
        query_kind="instant",
        aggregation="value",
        operator="<",
        threshold=0.5,
        unit="restarts",
    ),
    CheckDefinition(
        identifier="app-5xx",
        name="the application did not return /shorten 5xx responses during signer recovery",
        expression=(
            'sum(increase(http_requests_total{{namespace="{namespace}", handler="/shorten", '
            'status=~"5.."}}[{window}s])) or vector(0)'
        ),
        query_kind="instant",
        aggregation="value",
        operator="<",
        threshold=0.5,
        unit="responses",
    ),
    CheckDefinition(
        identifier="payment-replays",
        name="the signer fault did not produce a reused-settlement replay",
        expression=(
            'sum(increase(url_shortener_payment_replays_total{{namespace="{namespace}"}}[{window}s])) '
            'or vector(0)'
        ),
        query_kind="instant",
        aggregation="value",
        operator="<",
        threshold=0.5,
        unit="replays",
    ),
)


EXPERIMENTS: Mapping[str, ExperimentDefinition] = {
    "postgres-pod-failure": ExperimentDefinition(
        identifier="postgres-pod-failure", settle_seconds=60, checks=POSTGRES_CHECKS
    ),
    "redis-pod-failure": ExperimentDefinition(
        identifier="redis-pod-failure", settle_seconds=60, checks=REDIS_CHECKS
    ),
    "signer-pod-failure": ExperimentDefinition(
        identifier="signer-pod-failure", settle_seconds=60, checks=SIGNER_CHECKS
    ),
}
