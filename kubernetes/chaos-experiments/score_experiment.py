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


# C084 — release-linked scorecard contract ---------------------------------

@dataclass(frozen=True)
class ReleaseIdentity:
    """Immutable identity required to make a scorecard useful to promotion."""

    revision: str | None = None
    image_digest: str | None = None
    run_id: str | None = None

    def validation_error(self) -> str | None:
        if not self.revision or not self.revision.strip():
            return "release revision is required"
        if not self.image_digest or not _DIGEST_RE.fullmatch(self.image_digest):
            return "release image digest must be a lowercase sha256 digest"
        if not self.run_id or not _RUN_ID_RE.fullmatch(self.run_id):
            return "run id is required and must be a bounded safe identifier"
        return None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "revision": self.revision,
            "image_digest": self.image_digest,
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class Scorecard:
    """Portable result with enough provenance to approve or reject one release."""

    experiment: str
    window: ExperimentWindow | None
    checks: tuple[CheckResult, ...]
    release: ReleaseIdentity
    generated_at: datetime

    @property
    def verdict(self) -> Literal["pass", "fail"]:
        return "pass" if all(check.verdict == "pass" for check in self.checks) else "fail"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "experiment": self.experiment,
            "verdict": self.verdict,
            "generated_at": format_utc_timestamp(self.generated_at),
            "release": self.release.as_dict(),
            "window": (
                None
                if self.window is None
                else {
                    "inject_at": format_utc_timestamp(self.window.inject_at),
                    "start": format_utc_timestamp(self.window.start),
                    "end": format_utc_timestamp(self.window.end),
                    "duration_seconds": self.window.duration_seconds,
                    "settle_seconds": self.window.settle_seconds,
                }
            ),
            "checks": [check.as_dict() for check in self.checks],
        }


def _release_identity_check(release: ReleaseIdentity) -> CheckResult:
    error = release.validation_error()
    return CheckResult(
        identifier="release-identity",
        name="scorecard is linked to an immutable release and a bounded run id",
        verdict="fail" if error else "pass",
        observed=None,
        operator="==",
        threshold=1,
        unit="metadata",
        expression="release identity validation",
        query_kind="instant",
        sample_count=0,
        reason=error,
        evidence_error="invalid_release_identity" if error else None,
    )


def evaluate_experiment(
    experiment: str,
    inject_at: str | datetime,
    duration_seconds: int,
    *,
    client: PrometheusReader,
    namespace: str = DEFAULT_NAMESPACE,
    release: ReleaseIdentity | None = None,
    require_release_identity: bool = False,
    generated_at: datetime | None = None,
) -> Scorecard:
    """Evaluate all checks, retaining every failure instead of short-circuiting.

    ``require_release_identity`` is false for unit-level scorer controls and
    true for the CLI gate. A real promotion verdict therefore cannot pass
    without an immutable digest, revision, and run identifier.
    """

    definition = EXPERIMENTS.get(experiment)
    if definition is None:
        raise EvidenceError(f"unknown experiment: {experiment}")
    window = make_window(inject_at, duration_seconds, definition.settle_seconds)
    results = tuple(
        evaluate_check(check, client=client, namespace=namespace, window=window)
        for check in definition.checks
    )
    identity = release or ReleaseIdentity()
    if require_release_identity:
        results = results + (_release_identity_check(identity),)
    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise EvidenceError("generated_at must include a timezone")
    return Scorecard(
        experiment=definition.identifier,
        window=window,
        checks=results,
        release=identity,
        generated_at=timestamp.astimezone(timezone.utc),
    )


def score(
    experiment: str,
    inject_at: str | datetime,
    duration: int,
    *,
    client: PrometheusReader | None = None,
    namespace: str = DEFAULT_NAMESPACE,
) -> bool:
    """Compatibility helper: return an evidence-only pass/fail boolean.

    The command-line gate uses :func:`evaluate_experiment` with release
    identity required; this helper intentionally remains useful for synthetic
    scorer tests without manufacturing release metadata.
    """

    reader = client or PrometheusHTTPClient(PROM)
    card = evaluate_experiment(
        experiment,
        inject_at,
        duration,
        client=reader,
        namespace=namespace,
        require_release_identity=False,
    )
    return card.verdict == "pass"


def validate_scorecard_shape(payload: Any) -> None:
    """Minimal dependency-free guard for scorecards emitted by this module."""

    root = _as_mapping(payload, "scorecard")
    required = {
        "schema_version",
        "experiment",
        "verdict",
        "generated_at",
        "release",
        "window",
        "checks",
    }
    missing = sorted(required.difference(root))
    if missing:
        raise EvidenceError(f"scorecard is missing required fields: {', '.join(missing)}")
    if root["schema_version"] != SCHEMA_VERSION:
        raise EvidenceError("scorecard schema version is unsupported")
    if root["verdict"] not in {"pass", "fail"}:
        raise EvidenceError("scorecard verdict must be pass or fail")
    _as_mapping(root["release"], "scorecard release")
    if root["window"] is not None:
        _as_mapping(root["window"], "scorecard window")
    if not isinstance(root["checks"], list) or not root["checks"]:
        raise EvidenceError("scorecard must contain at least one check")
    for index, check in enumerate(root["checks"]):
        item = _as_mapping(check, f"scorecard checks[{index}]")
        if item.get("verdict") not in {"pass", "fail"}:
            raise EvidenceError(f"scorecard checks[{index}] has an invalid verdict")


def write_scorecard(card: Scorecard, path: Path) -> None:
    """Write deterministic JSON only to an explicitly requested artifact path."""

    payload = card.as_dict()
    validate_scorecard_shape(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _invalid_invocation_card(
    *, experiment: str, release: ReleaseIdentity, error: Exception
) -> Scorecard:
    check = CheckResult(
        identifier="scorer-invocation",
        name="the scorer received a valid bounded experiment invocation",
        verdict="fail",
        observed=None,
        operator="==",
        threshold=1,
        unit="metadata",
        expression="scorer invocation validation",
        query_kind="instant",
        sample_count=0,
        reason=str(error),
        evidence_error=error.code if isinstance(error, EvidenceError) else "unexpected_error",
    )
    checks = (check, _release_identity_check(release))
    return Scorecard(
        experiment=experiment,
        window=None,
        checks=checks,
        release=release,
        generated_at=datetime.now(timezone.utc),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", choices=sorted(EXPERIMENTS))
    parser.add_argument("--inject-at", required=True, help="RFC3339 UTC fault start time")
    parser.add_argument("--duration", type=int, required=True, help="fault duration in seconds")
    parser.add_argument(
        "--prom",
        default=os.environ.get("PROM_URL", PROM),
        help="Prometheus base URL (default: PROM_URL or the in-cluster service)",
    )
    parser.add_argument(
        "--namespace",
        default=os.environ.get("CHAOS_NAMESPACE", DEFAULT_NAMESPACE),
        help="target workload namespace",
    )
    parser.add_argument(
        "--release-revision",
        default=os.environ.get("RELEASE_REVISION"),
        help="source/Freight revision bound to the evaluated release",
    )
    parser.add_argument(
        "--release-digest",
        default=os.environ.get("RELEASE_DIGEST"),
        help="immutable image digest for the evaluated release",
    )
    parser.add_argument(
        "--run-id",
        default=os.environ.get("CHAOS_RUN_ID"),
        help="bounded identifier for this isolated chaos run",
    )
    parser.add_argument(
        "--scorecard-path",
        type=Path,
        help="optional path for the structured JSON scorecard",
    )
    args = parser.parse_args(argv)

    release = ReleaseIdentity(
        revision=args.release_revision,
        image_digest=args.release_digest,
        run_id=args.run_id,
    )
    try:
        card = evaluate_experiment(
            args.experiment,
            args.inject_at,
            args.duration,
            client=PrometheusHTTPClient(args.prom),
            namespace=args.namespace,
            release=release,
            require_release_identity=True,
        )
    except Exception as exc:  # configuration/query setup failure must yield FAIL JSON
        card = _invalid_invocation_card(experiment=args.experiment, release=release, error=exc)

    payload = card.as_dict()
    validate_scorecard_shape(payload)
    if args.scorecard_path:
        write_scorecard(card, args.scorecard_path)
    print(json.dumps(payload, sort_keys=True))
    return 0 if card.verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
