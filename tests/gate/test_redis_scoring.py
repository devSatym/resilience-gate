"""Synthetic controls for Redis fallback latency and recovery scoring."""

from __future__ import annotations


def test_redis_positive_control_requires_fallback_latency_and_recovery(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    reader = scripted_reader(
        instant=[
            instant_evidence(window.end, 210),  # meaningful traffic
            instant_evidence(window.end, 48),  # cache misses/fallbacks
            instant_evidence(window.end, 0),  # app restarts
        ],
        range_=[
            range_evidence(window, (0.18, 0.54, 0.62)),  # redirect p95
            range_evidence(window, (1, 0, 1)),  # outage observed
            range_evidence(window, (1, 0, 1)),  # recovery observed
        ],
    )

    card = scorer.evaluate_experiment("redis-pod-failure", inject_at, 60, client=reader)

    assert card.verdict == "pass"
    assert all(check.verdict == "pass" for check in card.checks)
    assert any('handler="/{code}"' in expression for _, expression in reader.queries)


def test_redis_gate_rejects_slow_fallbacks(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    reader = scripted_reader(
        instant=[
            instant_evidence(window.end, 210),
            instant_evidence(window.end, 48),
            instant_evidence(window.end, 0),
        ],
        range_=[
            range_evidence(window, (0.4, 1.21, 1.3)),
            range_evidence(window, (1, 0, 1)),
            range_evidence(window, (1, 0, 1)),
        ],
    )

    card = scorer.evaluate_experiment("redis-pod-failure", inject_at, 60, client=reader)

    latency = next(check for check in card.checks if check.identifier == "redirect-latency")
    assert card.verdict == "fail"
    assert latency.observed == 1.3
    assert latency.verdict == "fail"


def test_redis_gate_rejects_a_missing_fallback_signal(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    reader = scripted_reader(
        instant=[
            instant_evidence(window.end, 210),
            instant_evidence(window.end, 0),  # no cache miss despite claimed outage
            instant_evidence(window.end, 0),
        ],
        range_=[
            range_evidence(window, (0.2, 0.3, 0.4)),
            range_evidence(window, (1, 0, 1)),
            range_evidence(window, (1, 0, 1)),
        ],
    )

    card = scorer.evaluate_experiment("redis-pod-failure", inject_at, 60, client=reader)

    fallback = next(check for check in card.checks if check.identifier == "redis-fallback-observed")
    assert fallback.verdict == "fail"
    assert fallback.reason == "threshold_not_met"


def test_redis_query_template_preserves_the_route_label_literal(scorer) -> None:
    check = scorer.REDIS_CHECKS[2]
    window = scorer.make_window("2026-10-01T12:00:00Z", 60, 60)

    expression = scorer.render_expression(
        check, namespace="url-shortener-staging", window=window
    )

    assert 'namespace="url-shortener-staging"' in expression
    assert 'handler="/{code}"' in expression
    assert "{namespace}" not in expression


def test_redis_outage_queries_use_the_exact_target_readiness_series(scorer) -> None:
    outage, recovery = scorer.REDIS_CHECKS[4:6]
    window = scorer.make_window("2026-10-01T12:00:00Z", 60, 60)

    for check in (outage, recovery):
        expression = scorer.render_expression(
            check, namespace="url-shortener-staging", window=window
        )
        assert "kube_pod_status_ready" in expression
        assert 'pod="url-shortener-staging-redis-master-0"' in expression
        assert "url_shortener_dependency_up" not in expression
