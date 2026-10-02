#!/usr/bin/env python3
"""Fail-closed Prometheus scoring for one bounded development baseline.

This is intentionally separate from the staging chaos scorecard.  It reuses
the chaos scorer's strict Prometheus response parsing, sample freshness, range
coverage, and check-result semantics, but records a baseline's explicit start
and end instead of manufacturing a fault-injection window.

The command accepts only non-secret release identity and telemetry inputs.  It
never prints the Prometheus URL, request headers, or raw Prometheus response.
Every malformed, missing, non-finite, or stale observation yields a structured
``fail`` result rather than a pass or an implicit zero.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence
from urllib.parse import urlparse


SCRIPT_ROOT = Path(__file__).resolve().parent
CHAOS_SCORER_PATH = SCRIPT_ROOT.parent / "kubernetes" / "chaos-experiments" / "score_experiment.py"

SCHEMA_VERSION = "resilience-gate.baseline-scorecard/v1"
MIN_BASELINE_SECONDS = 60
# The runner caps k6 traffic at 90 seconds and the temporary Job at 150
# seconds. Keep the scorecard window within that exact Job bound so an
# arbitrary multi-minute Prometheus interval cannot be relabelled a baseline.
MAX_BASELINE_OBSERVATION_SECONDS = 150
MIN_ROOT_GET_REQUESTS = 20
MAX_ROOT_GET_P95_SECONDS = 1.0
_NAMESPACE_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{7,64}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _load_chaos_scorer() -> ModuleType:
    """Load the shared strict Prometheus implementation without a package shim."""

    module_name = "resilience_gate_shared_chaos_scorer"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, CHAOS_SCORER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load shared scorer from {CHAOS_SCORER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


chaos = _load_chaos_scorer()


@dataclass(frozen=True)
class BaselineWindow:
    """An exact, bounded observation window supplied by the baseline run."""

    started_at: datetime
    ended_at: datetime

    @property
    def start(self) -> datetime:
        return self.started_at

    @property
    def end(self) -> datetime:
        return self.ended_at

    @property
    def seconds(self) -> int:
        return int((self.ended_at - self.started_at).total_seconds())

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": chaos.format_utc_timestamp(self.started_at),
            "ended_at": chaos.format_utc_timestamp(self.ended_at),
            "duration_seconds": self.seconds,
        }


@dataclass(frozen=True)
class BaselineScorecard:
    """A scorecard-shaped, release-linked baseline result.

    The field names for ``verdict``, ``release``, and ``checks`` intentionally
    match the chaos scorecard.  The separate schema/version makes it impossible
    to present a baseline as one of the three Chaos Mesh experiment scorecards.
    """

    window: BaselineWindow | None
    checks: tuple[Any, ...]
    release: Any
    generated_at: datetime

    @property
    def verdict(self) -> str:
        return "pass" if all(check.verdict == "pass" for check in self.checks) else "fail"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "scenario": "baseline",
            "verdict": self.verdict,
            "generated_at": chaos.format_utc_timestamp(self.generated_at),
            "release": self.release.as_dict(),
            "window": None if self.window is None else self.window.as_dict(),
            "checks": [check.as_dict() for check in self.checks],
        }


BASELINE_CHECKS = (
    chaos.CheckDefinition(
        identifier="root-get-traffic",
        name="meaningful GET / traffic flowed during the baseline",
        expression=(
            'sum(increase(http_requests_total{{namespace="{namespace}", '
            'handler="/", method="GET"}}[{window}s]))'
        ),
        query_kind="instant",
        aggregation="value",
        operator=">",
        threshold=MIN_ROOT_GET_REQUESTS,
        unit="requests",
    ),
    chaos.CheckDefinition(
        identifier="application-5xx",
        name="the application returned no 5xx responses during the baseline",
        expression=(
            'sum(increase(http_requests_total{{namespace="{namespace}", '
            'status=~"5.."}}[{window}s])) or vector(0)'
        ),
        query_kind="instant",
        aggregation="value",
        operator="<",
        threshold=0.5,
        unit="responses",
    ),
    chaos.CheckDefinition(
        identifier="root-get-p95-latency",
        name="GET / p95 latency over the final one-minute traffic interval stayed below the baseline bound",
        expression=(
            'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket'
            '{{namespace="{namespace}", handler="/", method="GET"}}[1m])) by (le))'
        ),
        # The baseline begins from an idle service. The first point of a
        # range-vector rate can therefore be NaN before a full one-minute
        # traffic interval exists. Evaluate one fresh scalar at the completed
        # window end instead; it covers the final 60 seconds of the bounded
        # run and still fails closed on missing, stale, or non-finite data.
        query_kind="instant",
        aggregation="value",
        operator="<",
        threshold=MAX_ROOT_GET_P95_SECONDS,
        unit="seconds",
    ),
    chaos.CheckDefinition(
        identifier="postgres-ready",
        name="the PostgreSQL primary remained ready throughout the baseline",
        expression=(
            'min(kube_pod_status_ready{{namespace="{namespace}", condition="true", '
            'pod=~"url-shortener-[a-z0-9-]+-postgresql-0"}})'
        ),
        query_kind="range",
        aggregation="min",
        operator="==",
        threshold=1,
        unit="state",
    ),
    chaos.CheckDefinition(
        identifier="redis-ready",
        name="the Redis primary remained ready throughout the baseline",
        expression=(
            'min(kube_pod_status_ready{{namespace="{namespace}", condition="true", '
            'pod=~"url-shortener-[a-z0-9-]+-redis-master-0"}})'
        ),
        query_kind="range",
        aggregation="min",
        operator="==",
        threshold=1,
        unit="state",
    ),
)


def make_baseline_window(started_at: str | datetime, ended_at: str | datetime) -> BaselineWindow:
    """Parse an explicit UTC baseline window without widening either endpoint."""

    start = chaos.parse_utc_timestamp(started_at) if isinstance(started_at, str) else started_at
    end = chaos.parse_utc_timestamp(ended_at) if isinstance(ended_at, str) else ended_at
    if not isinstance(start, datetime) or start.tzinfo is None:
        raise chaos.EvidenceError("started_at must be a timezone-aware datetime")
    if not isinstance(end, datetime) or end.tzinfo is None:
        raise chaos.EvidenceError("ended_at must be a timezone-aware datetime")
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    duration = (end - start).total_seconds()
    if duration <= 0:
        raise chaos.EvidenceError("ended_at must be after started_at")
    if not duration.is_integer():
        raise chaos.EvidenceError("baseline duration must be an exact number of seconds")
    if duration < MIN_BASELINE_SECONDS:
        raise chaos.EvidenceError(
            f"baseline duration must be at least {MIN_BASELINE_SECONDS} seconds"
        )
    if duration > MAX_BASELINE_OBSERVATION_SECONDS:
        raise chaos.EvidenceError(
            "baseline duration must be no more than "
            f"{MAX_BASELINE_OBSERVATION_SECONDS} seconds"
        )
    return BaselineWindow(started_at=start, ended_at=end)


def _validate_namespace(namespace: str) -> None:
    if not _NAMESPACE_RE.fullmatch(namespace):
        raise chaos.EvidenceError("namespace must be a lowercase DNS label")


def _safe_release_identity(
    *, source_revision: str | None, release_digest: str | None, run_id: str | None
) -> Any:
    """Never echo unvalidated caller text into the public scorecard."""

    return chaos.ReleaseIdentity(
        revision=source_revision if source_revision and _SOURCE_REVISION_RE.fullmatch(source_revision) else None,
        image_digest=release_digest if release_digest and _DIGEST_RE.fullmatch(release_digest) else None,
        run_id=run_id if run_id and _RUN_ID_RE.fullmatch(run_id) else None,
    )


def _validate_identity(*, source_revision: str, release_digest: str, run_id: str) -> Any:
    release = _safe_release_identity(
        source_revision=source_revision,
        release_digest=release_digest,
        run_id=run_id,
    )
    if release.revision is None:
        raise chaos.EvidenceError("source revision must be a lowercase Git SHA of 7 to 64 characters")
    if release.validation_error():
        raise chaos.EvidenceError(release.validation_error())
    return release


def _invalid_invocation_scorecard(release: Any, error: Exception) -> BaselineScorecard:
    check = chaos.CheckResult(
        identifier="baseline-invocation",
        name="the baseline scorer received a complete bounded invocation",
        verdict="fail",
        observed=None,
        operator="==",
        threshold=1,
        unit="metadata",
        expression="baseline invocation validation",
        query_kind="instant",
        sample_count=0,
        reason=str(error),
        evidence_error=error.code if isinstance(error, chaos.EvidenceError) else "unexpected_error",
    )
    return BaselineScorecard(
        window=None,
        checks=(check, chaos._release_identity_check(release)),
        release=release,
        generated_at=datetime.now(timezone.utc),
    )


def evaluate_baseline(
    *,
    client: Any,
    namespace: str,
    source_revision: str,
    release_digest: str,
    run_id: str,
    started_at: str | datetime,
    ended_at: str | datetime,
    generated_at: datetime | None = None,
) -> BaselineScorecard:
    """Evaluate every baseline rule, retaining all failures for review."""

    _validate_namespace(namespace)
    window = make_baseline_window(started_at, ended_at)
    release = _validate_identity(
        source_revision=source_revision,
        release_digest=release_digest,
        run_id=run_id,
    )
    checks = tuple(
        chaos.evaluate_check(check, client=client, namespace=namespace, window=window)
        for check in BASELINE_CHECKS
    ) + (chaos._release_identity_check(release),)
    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise chaos.EvidenceError("generated_at must include a timezone")
    return BaselineScorecard(
        window=window,
        checks=checks,
        release=release,
        generated_at=timestamp.astimezone(timezone.utc),
    )


def validate_baseline_scorecard_shape(payload: Any) -> None:
    """Keep baseline output scorecard-shaped without changing chaos schemas."""

    if not isinstance(payload, dict):
        raise chaos.EvidenceError("baseline scorecard must be an object")
    required = {
        "schema_version",
        "scenario",
        "verdict",
        "generated_at",
        "release",
        "window",
        "checks",
    }
    if set(payload) != required:
        raise chaos.EvidenceError("baseline scorecard has an invalid field set")
    if payload["schema_version"] != SCHEMA_VERSION or payload["scenario"] != "baseline":
        raise chaos.EvidenceError("baseline scorecard has an unsupported schema or scenario")
    if payload["verdict"] not in {"pass", "fail"}:
        raise chaos.EvidenceError("baseline scorecard has an invalid verdict")
    if not isinstance(payload["release"], dict) or set(payload["release"]) != {
        "revision",
        "image_digest",
        "run_id",
    }:
        raise chaos.EvidenceError("baseline scorecard has an invalid release identity")
    if payload["window"] is not None:
        if not isinstance(payload["window"], dict) or set(payload["window"]) != {
            "started_at",
            "ended_at",
            "duration_seconds",
        }:
            raise chaos.EvidenceError("baseline scorecard has an invalid window")
    checks = payload["checks"]
    if not isinstance(checks, list) or not checks:
        raise chaos.EvidenceError("baseline scorecard must contain checks")
    for check in checks:
        if not isinstance(check, dict) or check.get("verdict") not in {"pass", "fail"}:
            raise chaos.EvidenceError("baseline scorecard has an invalid check")


def _validate_prometheus_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise chaos.EvidenceError("Prometheus URL must be a credential-free absolute HTTP(S) URL")
    return value.rstrip("/")


def _write_scorecard(path: Path, payload: dict[str, Any]) -> None:
    if path.is_symlink():
        raise chaos.EvidenceError("scorecard output path must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="bounded baseline run identifier")
    parser.add_argument("--namespace", required=True, help="target Kubernetes namespace")
    parser.add_argument("--source-revision", required=True, help="source/Freight Git SHA")
    parser.add_argument("--release-digest", required=True, help="immutable application sha256 digest")
    parser.add_argument("--started-at", required=True, help="RFC3339 UTC baseline start")
    parser.add_argument("--ended-at", required=True, help="RFC3339 UTC baseline end")
    parser.add_argument("--prom", required=True, help="credential-free Prometheus HTTP(S) URL")
    parser.add_argument("--output", type=Path, help="optional JSON scorecard destination")
    args = parser.parse_args(argv)

    safe_release = _safe_release_identity(
        source_revision=args.source_revision,
        release_digest=args.release_digest,
        run_id=args.run_id,
    )
    try:
        client = chaos.PrometheusHTTPClient(_validate_prometheus_url(args.prom))
        card = evaluate_baseline(
            client=client,
            namespace=args.namespace,
            source_revision=args.source_revision,
            release_digest=args.release_digest,
            run_id=args.run_id,
            started_at=args.started_at,
            ended_at=args.ended_at,
        )
    except Exception as exc:
        card = _invalid_invocation_scorecard(safe_release, exc)

    payload = card.as_dict()
    validate_baseline_scorecard_shape(payload)
    if args.output:
        _write_scorecard(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if card.verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
