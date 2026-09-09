"""Synthetic controls for PostgreSQL-fault traffic and recovery scoring."""

from __future__ import annotations


def postgres_reader(scorer, inject_at, scripted_reader, instant_evidence, range_evidence):
    window = scorer.make_window(inject_at, 60, scorer.EXPERIMENTS["postgres-pod-failure"].settle_seconds)
    return scripted_reader(
        instant=[
            instant_evidence(window.end, 180),  # meaningful traffic
            instant_evidence(window.end, 0),  # app restarts
            instant_evidence(window.end, 0),  # unhandled 500s
        ],
        range_=[
            range_evidence(window, (1, 0, 1)),  # fault landed
            range_evidence(window, (1, 0, 1)),  # recovered
        ],
    )


def test_postgresql_positive_control_requires_traffic_outage_and_recovery(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    reader = postgres_reader(
        scorer, inject_at, scripted_reader, instant_evidence, range_evidence
    )

    card = scorer.evaluate_experiment(
        "postgres-pod-failure",  # real CLI-compatible identifier
        inject_at,
        60,
        client=reader,
    )

    assert card.verdict == "pass"
    assert {check.identifier for check in card.checks} == {
        "meaningful-traffic",
        "app-restarts",
        "postgres-outage-observed",
        "postgres-recovered",
        "postgres-clean-degradation",
    }
    assert all(check.verdict == "pass" for check in card.checks)
    assert any("[120s]" in expression for _, expression in reader.queries)


def test_postgresql_gate_rejects_a_fault_that_never_landed(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    reader = scripted_reader(
        instant=[
            instant_evidence(window.end, 180),
            instant_evidence(window.end, 0),
            instant_evidence(window.end, 0),
        ],
        range_=[
            range_evidence(window, (1, 1, 1)),  # dependency never fell
            range_evidence(window, (1, 1, 1)),
        ],
    )

    card = scorer.evaluate_experiment(
        "postgres-pod-failure", inject_at, 60, client=reader
    )

    failure = next(check for check in card.checks if check.identifier == "postgres-outage-observed")
    assert card.verdict == "fail"
    assert failure.verdict == "fail"
    assert failure.observed == 1
    assert failure.reason == "threshold_not_met"


def test_postgresql_gate_rejects_recovery_that_does_not_complete(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    reader = scripted_reader(
        instant=[
            instant_evidence(window.end, 180),
            instant_evidence(window.end, 0),
            instant_evidence(window.end, 0),
        ],
        range_=[
            range_evidence(window, (1, 0, 0)),
            range_evidence(window, (1, 0, 0)),  # last value remains unavailable
        ],
    )

    card = scorer.evaluate_experiment(
        "postgres-pod-failure", inject_at, 60, client=reader
    )

    recovery = next(check for check in card.checks if check.identifier == "postgres-recovered")
    assert recovery.verdict == "fail"
    assert recovery.observed == 0
