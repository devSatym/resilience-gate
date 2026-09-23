"""Release-linked JSON scorecard controls using synthetic evidence only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


def valid_postgres_reader(scorer, inject_at, scripted_reader, instant_evidence, range_evidence):
    window = scorer.make_window(inject_at, 60, 60)
    return scripted_reader(
        instant=[
            instant_evidence(window.end, 180),
            instant_evidence(window.end, 0),
            instant_evidence(window.end, 0),
        ],
        range_=[
            range_evidence(window, (1, 0, 1)),
            range_evidence(window, (1, 0, 1)),
        ],
    )


def release(scorer):
    return scorer.ReleaseIdentity(
        revision="7f3f2bb",
        image_digest="sha256:" + "a" * 64,
        run_id="chaos-gate-20261001-001",
    )


def test_scorecard_carries_release_identity_window_and_each_check(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    card = scorer.evaluate_experiment(
        "postgres-pod-failure",
        inject_at,
        60,
        client=valid_postgres_reader(
            scorer, inject_at, scripted_reader, instant_evidence, range_evidence
        ),
        release=release(scorer),
        require_release_identity=True,
        generated_at=datetime(2026, 10, 1, 12, 5, tzinfo=timezone.utc),
    )

    payload = card.as_dict()
    scorer.validate_scorecard_shape(payload)

    assert card.verdict == "pass"
    assert payload["schema_version"] == "resilience-gate.scorecard/v1"
    assert payload["release"] == {
        "revision": "7f3f2bb",
        "image_digest": "sha256:" + "a" * 64,
        "run_id": "chaos-gate-20261001-001",
    }
    assert payload["window"]["inject_at"] == "2026-10-01T12:00:00Z"
    assert {item["id"] for item in payload["checks"]} >= {
        "postgres-outage-observed",
        "postgres-recovered",
        "release-identity",
    }


def test_release_identity_is_a_required_fail_closed_gate_check(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence
) -> None:
    card = scorer.evaluate_experiment(
        "postgres-pod-failure",
        inject_at,
        60,
        client=valid_postgres_reader(
            scorer, inject_at, scripted_reader, instant_evidence, range_evidence
        ),
        release=scorer.ReleaseIdentity(revision="7f3f2bb", image_digest="latest", run_id=" "),
        require_release_identity=True,
    )

    identity = next(check for check in card.checks if check.identifier == "release-identity")
    assert card.verdict == "fail"
    assert identity.verdict == "fail"
    assert identity.evidence_error == "invalid_release_identity"
    assert "digest" in identity.reason


def test_cli_labels_release_revision_as_the_source_freight_identity(scorer) -> None:
    source = Path(scorer.__file__).read_text(encoding="utf-8")

    assert "source/Freight revision bound to the evaluated release" in source
    assert "rendered Git revision for the evaluated release" not in source


def test_scorecard_writer_emits_deterministic_valid_json(
    scorer, inject_at, scripted_reader, instant_evidence, range_evidence, tmp_path
) -> None:
    card = scorer.evaluate_experiment(
        "postgres-pod-failure",
        inject_at,
        60,
        client=valid_postgres_reader(
            scorer, inject_at, scripted_reader, instant_evidence, range_evidence
        ),
        release=release(scorer),
        require_release_identity=True,
    )
    path = tmp_path / "nested" / "scorecard.json"

    scorer.write_scorecard(card, path)

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    scorer.validate_scorecard_shape(payload)
    assert payload["verdict"] == "pass"
    assert not (path.parent / "scorecard.json.tmp").exists()


def test_json_schema_describes_the_same_required_scorecard_contract() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "scorecard.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == "resilience-gate.scorecard/v1"
    assert set(schema["required"]) >= {
        "experiment",
        "verdict",
        "release",
        "window",
        "checks",
    }
    assert set(schema["properties"]["release"]["required"]) == {
        "revision",
        "image_digest",
        "run_id",
    }
    assert schema["properties"]["checks"]["minItems"] == 1


def test_shape_validator_rejects_a_scorecard_without_checks(scorer) -> None:
    with pytest.raises(scorer.EvidenceError, match="at least one check"):
        scorer.validate_scorecard_shape(
            {
                "schema_version": scorer.SCHEMA_VERSION,
                "experiment": "postgres-pod-failure",
                "verdict": "pass",
                "generated_at": "2026-10-01T12:00:00Z",
                "release": {},
                "window": None,
                "checks": [],
            }
        )
