"""Synthetic controls for signer outage recovery and app isolation."""

from __future__ import annotations


def test_signer_positive_control_requires_recovery_without_app_collateral_damage(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    reader = scripted_reader(
        instant=[
            instant_evidence(window.end, 0),  # application restarts
            instant_evidence(window.end, 0),  # app 5xx
            instant_evidence(window.end, 0),  # payment replays
        ],
        range_=[
            range_evidence(window, (1, 0, 1)),  # signer became unavailable
            range_evidence(window, (1, 0, 1)),  # signer became ready again
        ],
    )

    card = scorer.evaluate_experiment("signer-pod-failure", inject_at, 60, client=reader)

    assert card.verdict == "pass"
    assert [check.identifier for check in card.checks] == [
        "signer-outage-observed",
        "signer-recovered",
        "app-restarts",
        "app-5xx",
        "payment-replays",
    ]


def test_signer_gate_rejects_a_signer_that_never_recovers(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    reader = scripted_reader(
        instant=[
            instant_evidence(window.end, 0),
            instant_evidence(window.end, 0),
            instant_evidence(window.end, 0),
        ],
        range_=[
            range_evidence(window, (1, 0, 0)),
            range_evidence(window, (1, 0, 0)),
        ],
    )

    card = scorer.evaluate_experiment("signer-pod-failure", inject_at, 60, client=reader)

    recovery = next(check for check in card.checks if check.identifier == "signer-recovered")
    assert card.verdict == "fail"
    assert recovery.verdict == "fail"
    assert recovery.observed == 0


def test_signer_gate_rejects_app_isolation_regressions(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    window = scorer.make_window(inject_at, 60, 60)
    reader = scripted_reader(
        instant=[
            instant_evidence(window.end, 1),  # application restarted
            instant_evidence(window.end, 2),  # 5xx responses
            instant_evidence(window.end, 1),  # replay
        ],
        range_=[
            range_evidence(window, (1, 0, 1)),
            range_evidence(window, (1, 0, 1)),
        ],
    )

    card = scorer.evaluate_experiment("signer-pod-failure", inject_at, 60, client=reader)

    failures = {check.identifier for check in card.checks if check.verdict == "fail"}
    assert failures == {"app-restarts", "app-5xx", "payment-replays"}
