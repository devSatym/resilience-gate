"""Hermetic contracts for live verification and evidence collection safety."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_RUNNER = REPO_ROOT / "scripts" / "validate-live.sh"
COLLECTOR = REPO_ROOT / "scripts" / "collect-evidence.sh"
EVIDENCE_UTILITY = REPO_ROOT / "scripts" / "evidence_utils.py"
SCHEMA = REPO_ROOT / "schemas" / "run-metadata.schema.json"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "regressions"
EXPECTED_CONTEXT = "gke_resilience-gate-123_us-central1-a_resilience-gate"


def write_executable(path: Path, contents: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + contents + "\n", encoding="utf-8")
    path.chmod(0o755)


def write_config(tmp_path: Path) -> Path:
    config = tmp_path / "config.env"
    config.write_text(
        "\n".join(
            (
                'PROJECT_ID="resilience-gate-123"',
                'GITHUB_REPO="example/resilience-gate"',
                'REGION="us-central1"',
                'ZONE="us-central1-a"',
                'CLUSTER_NAME="resilience-gate"',
                'GAR_REPO="resilience-gate"',
                'TF_STATE_BUCKET="resilience-gate-123-tf-state"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def scorecard_line(experiment: str) -> str:
    return json.dumps(
        {
            "schema_version": "resilience-gate.scorecard/v1",
            "experiment": experiment,
            "verdict": "pass",
            "generated_at": "2026-10-01T12:00:00Z",
            "release": {
                "revision": "abcdef0",
                "image_digest": "sha256:" + "a" * 64,
                "run_id": "gate-run-1",
            },
            "window": None,
            "checks": [
                {
                    "id": "check",
                    "name": "check",
                    "verdict": "pass",
                    "observed": 1,
                    "operator": ">=",
                    "threshold": 1,
                    "unit": "count",
                    "expression": "up",
                    "query_kind": "instant",
                    "sample_count": 1,
                    "reason": None,
                    "evidence_error": None,
                }
            ],
        },
        separators=(",", ":"),
    )


def fake_environment(
    tmp_path: Path,
    *,
    fail_gate_exec: bool = False,
    log_scorecards: tuple[str, ...] | None = None,
) -> tuple[dict[str, str], Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    all_scorecards = (
        "postgres-pod-failure",
        "redis-pod-failure",
        "signer-pod-failure",
    )
    selected_scorecards = all_scorecards if log_scorecards is None else log_scorecards
    scorecard_logs = "\n".join(
        f"printf '%s\\n' '[pod/gate-pod-1/chaos-gate] {scorecard_line(experiment)}'"
        for experiment in selected_scorecards
    )
    scorecard_exec = "\n".join(
        "\n".join(
            (
                f'if [[ "$args" == *"{experiment}.json"* ]]; then',
                f"  printf '%s\\n' '{scorecard_line(experiment)}'",
                "  exit 0",
                "fi",
            )
        )
        for experiment in all_scorecards
    )
    write_executable(
        bin_dir / "kubectl",
        f"""
printf 'kubectl %s\\n' "$*" >> {calls}
args="$*"
if [[ "$args" == *"config current-context"* ]]; then echo {EXPECTED_CONTEXT}; exit 0; fi
if [[ "$args" == *"get namespace url-shortener-staging"* ]]; then exit 0; fi
if [[ "$args" == *"get namespace url-shortener-dev"* ]]; then exit 0; fi
if [[ "$args" == *"get namespace url-shortener-prod"* ]]; then exit 0; fi
if [[ "$args" == *"get stage staging -o yaml"* ]]; then
  printf 'apiVersion: kargo.akuity.io/v1alpha1\\nkind: Stage\\nmetadata:\\n  name: staging\\n'
  exit 0
fi
if [[ "$args" == *"get stage dev -o yaml"* ]]; then
  printf 'apiVersion: kargo.akuity.io/v1alpha1\\nkind: Stage\\nmetadata:\\n  name: dev\\n'
  exit 0
fi
if [[ "$args" == *"get stage prod -o yaml"* ]]; then
  printf 'apiVersion: kargo.akuity.io/v1alpha1\\nkind: Stage\\nmetadata:\\n  name: prod\\n'
  exit 0
fi
if [[ "$args" == *"get analysistemplate chaos-gate -o yaml"* ]]; then
  printf 'apiVersion: argoproj.io/v1alpha1\\nkind: AnalysisTemplate\\nmetadata:\\n  name: chaos-gate\\n'
  exit 0
fi
if [[ "$args" == *"get analysistemplate service-health -o yaml"* ]]; then
  printf 'apiVersion: argoproj.io/v1alpha1\\nkind: AnalysisTemplate\\nmetadata:\\n  name: service-health\\n'
  exit 0
fi
if [[ "$args" == *"get deployment url-shortener-staging -o yaml"* ]]; then
  printf 'apiVersion: apps/v1\\nkind: Deployment\\nmetadata:\\n  name: url-shortener-staging\\n'
  exit 0
fi
if [[ "$args" == *"get deployment url-shortener-dev -o yaml"* ]]; then
  printf 'apiVersion: apps/v1\\nkind: Deployment\\nmetadata:\\n  name: url-shortener-dev\\n'
  exit 0
fi
if [[ "$args" == *"get deployment url-shortener-prod -o yaml"* ]]; then
  printf 'apiVersion: apps/v1\\nkind: Deployment\\nmetadata:\\n  name: url-shortener-prod\\n'
  exit 0
fi
if [[ "$args" == *"get deployment radius-signer -o yaml"* ]]; then
  printf 'apiVersion: apps/v1\\nkind: Deployment\\nmetadata:\\n  name: radius-signer\\n'
  exit 0
fi
if [[ "$args" == *"get cronjob loadgen -o yaml"* ]]; then
  printf 'apiVersion: batch/v1\\nkind: CronJob\\nmetadata:\\n  name: loadgen\\n'
  exit 0
fi
if [[ "$args" == *"get analysisrun analysis-run-1 -o yaml"* ]]; then
  printf 'apiVersion: argoproj.io/v1alpha1\\nkind: AnalysisRun\\nmetadata:\\n  name: analysis-run-1\\n'
  exit 0
fi
if [[ "$args" == *"get job gate-job-1 -o yaml"* ]]; then
  printf 'apiVersion: batch/v1\\nkind: Job\\nmetadata:\\n  name: gate-job-1\\n'
  exit 0
fi
if [[ "$args" == *"get pods -l job-name=gate-job-1"* ]]; then echo gate-pod-1; exit 0; fi
if [[ "$args" == *"get pod gate-pod-1 -o yaml"* ]]; then
  printf 'apiVersion: v1\\nkind: Pod\\nmetadata:\\n  name: gate-pod-1\\n'
  exit 0
fi
if [[ "$args" == *"logs pod/gate-pod-1"* ]]; then
{scorecard_logs}
  exit 0
fi
if [[ "$args" == *"exec gate-pod-1"* ]]; then
  if [[ "$FAIL_GATE_EXEC" == "1" ]]; then exit 1; fi
{scorecard_exec}
  exit 1
fi
if [[ "$args" == *"get stage staging"* ]]; then exit 0; fi
if [[ "$args" == *"get analysistemplate chaos-gate"* ]]; then exit 0; fi
if [[ "$args" == *"get analysistemplate service-health"* ]]; then exit 0; fi
if [[ "$args" == *"get freight candidate-1"* ]]; then exit 0; fi
exit 1
""",
    )
    write_executable(
        bin_dir / "kargo",
        f"""
printf 'kargo %s\\n' "$*" >> {calls}
exit 0
""",
    )
    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAIL_GATE_EXEC": "1" if fail_gate_exec else "0",
    }
    return env, calls, write_config(tmp_path)


def run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)


def test_live_plan_has_no_cluster_side_effect() -> None:
    result = run(["bash", str(LIVE_RUNNER), "--plan", "--scenario", "chaos-gate"])

    assert result.returncode == 0, result.stderr
    assert "no cluster, Kargo, cloud, or testnet call" in result.stdout
    assert "kargo verify stage staging --project resilience-gate" in result.stdout


def test_baseline_plan_uses_the_development_stage_and_namespace() -> None:
    result = run(["bash", str(LIVE_RUNNER), "--plan", "--scenario", "baseline"])

    assert result.returncode == 0, result.stderr
    assert "Stage: dev" in result.stdout
    assert "target namespace: url-shortener-dev" in result.stdout


def test_live_execution_requires_explicit_lab_acknowledgement_before_loading_config(tmp_path: Path) -> None:
    env, calls, config = fake_environment(tmp_path)

    result = run(
        ["bash", str(LIVE_RUNNER), "--execute", "--scenario", "chaos-gate", "--config", str(config)],
        env=env,
    )

    assert result.returncode == 2
    assert "acknowledge-owned-testnet-lab" in result.stderr
    assert not calls.exists()


def test_live_execution_uses_kargo_stage_verification_not_a_direct_chaos_run(tmp_path: Path) -> None:
    env, calls, config = fake_environment(tmp_path)

    result = run(
        [
            "bash",
            str(LIVE_RUNNER),
            "--execute",
            "--acknowledge-owned-testnet-lab",
            "--scenario",
            "chaos-gate",
            "--config",
            str(config),
        ],
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "not a passing verification verdict" in result.stdout
    recorded = calls.read_text(encoding="utf-8")
    assert "kargo verify stage staging --project resilience-gate" in recorded
    assert "kubectl create" not in recorded
    assert "kubectl apply" not in recorded
    assert "kubectl delete" not in recorded


def test_named_staging_promotion_needs_a_second_acknowledgement(tmp_path: Path) -> None:
    env, calls, config = fake_environment(tmp_path)
    command = [
        "bash",
        str(LIVE_RUNNER),
        "--execute",
        "--acknowledge-owned-testnet-lab",
        "--scenario",
        "regression-blocked",
        "--promotion-freight",
        "candidate-1",
        "--config",
        str(config),
    ]

    denied = run(command, env=env)
    assert denied.returncode == 2
    assert "acknowledge-staging-promotion" in denied.stderr
    assert not calls.exists()

    accepted = run(command + ["--acknowledge-staging-promotion"], env=env)
    assert accepted.returncode == 0, accepted.stderr
    assert "kargo promote --project resilience-gate --freight candidate-1 --stage staging" in calls.read_text(
        encoding="utf-8"
    )


def test_collector_writes_sanitized_bundle_and_release_metadata(tmp_path: Path) -> None:
    env, _calls, config = fake_environment(tmp_path)
    output_root = tmp_path / "evidence-output"
    digest = "sha256:" + "a" * 64
    result = run(
        [
            "bash",
            str(COLLECTOR),
            "--collect",
            "--acknowledge-owned-testnet-lab",
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--scenario",
            "chaos-gate",
            "--status",
            "pass",
            "--run-id",
            "gate-evidence-1",
            "--analysis-run",
            "analysis-run-1",
            "--gate-job",
            "gate-job-1",
            "--repository-revision",
            "abcdef0",
            "--chart-revision",
            "abcdef0",
            "--release-image-digest",
            digest,
            "--gate-runner-image-digest",
            digest,
            "--signer-image-digest",
            digest,
            "--loadgen-image-digest",
            digest,
            "--include",
            str(FIXTURES / "sanitization-input.txt"),
        ],
        env=env,
    )

    assert result.returncode == 0, result.stderr
    bundle = output_root / "chaos-gate" / "gate-evidence-1"
    metadata_path = bundle / "run-metadata.json"
    assert metadata_path.is_file()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["status"] == "pass"
    assert metadata["namespace"] == "url-shortener-staging"
    assert metadata["gate_runner_image_digest"] == digest
    assert set(metadata["evidence"]["redactions"]) >= {"authorization-headers", "wallet-keys"}
    supplemental = (bundle / "supplemental" / "sanitization-input.txt").read_text(encoding="utf-8")
    assert "should-not-be-retained" not in supplemental
    assert "normal-status=healthy" in supplemental
    validation = run(
        [
            os.environ.get("PYTHON", "python3"),
            str(EVIDENCE_UTILITY),
            "validate",
            "--schema",
            str(SCHEMA),
            "--metadata",
            str(metadata_path),
        ],
        env=env,
    )
    assert validation.returncode == 0, validation.stderr


def test_collector_recovers_completed_gate_scorecards_from_sanitized_logs(tmp_path: Path) -> None:
    env, calls, config = fake_environment(tmp_path, fail_gate_exec=True)
    output_root = tmp_path / "evidence-output"
    digest = "sha256:" + "a" * 64
    result = run(
        [
            "bash",
            str(COLLECTOR),
            "--collect",
            "--acknowledge-owned-testnet-lab",
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--scenario",
            "chaos-gate",
            "--status",
            "pass",
            "--run-id",
            "gate-log-fallback-1",
            "--analysis-run",
            "analysis-run-1",
            "--gate-job",
            "gate-job-1",
            "--repository-revision",
            "abcdef0",
            "--chart-revision",
            "abcdef0",
            "--release-image-digest",
            digest,
            "--gate-runner-image-digest",
            digest,
            "--signer-image-digest",
            digest,
            "--loadgen-image-digest",
            digest,
        ],
        env=env,
    )

    assert result.returncode == 0, result.stderr
    bundle = output_root / "chaos-gate" / "gate-log-fallback-1"
    for experiment in (
        "postgres-pod-failure",
        "redis-pod-failure",
        "signer-pod-failure",
    ):
        scorecard = json.loads((bundle / "scorecards" / f"{experiment}.json").read_text(encoding="utf-8"))
        assert scorecard["experiment"] == experiment
        assert scorecard["verdict"] == "pass"
    recorded = calls.read_text(encoding="utf-8")
    assert "kubectl -n resilience-gate exec gate-pod-1" in recorded
    assert "kubectl -n resilience-gate logs pod/gate-pod-1 --all-containers=true --prefix=true" in recorded


def test_collector_refuses_missing_completed_gate_scorecard(tmp_path: Path) -> None:
    env, _calls, config = fake_environment(
        tmp_path,
        fail_gate_exec=True,
        log_scorecards=("postgres-pod-failure", "redis-pod-failure"),
    )
    output_root = tmp_path / "evidence-output"
    digest = "sha256:" + "a" * 64
    run_id = "gate-log-fallback-missing"
    result = run(
        [
            "bash",
            str(COLLECTOR),
            "--collect",
            "--acknowledge-owned-testnet-lab",
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--scenario",
            "chaos-gate",
            "--status",
            "pass",
            "--run-id",
            run_id,
            "--analysis-run",
            "analysis-run-1",
            "--gate-job",
            "gate-job-1",
            "--repository-revision",
            "abcdef0",
            "--chart-revision",
            "abcdef0",
            "--release-image-digest",
            digest,
            "--gate-runner-image-digest",
            digest,
            "--signer-image-digest",
            digest,
            "--loadgen-image-digest",
            digest,
        ],
        env=env,
    )

    assert result.returncode == 2
    assert "could not recover scorecard signer-pod-failure" in result.stderr
    assert not (output_root / "chaos-gate" / run_id).exists()
    assert not list(output_root.glob(".collect-*"))


def test_scorecard_extractor_accepts_prefixed_logs_and_rejects_ambiguous_matches(tmp_path: Path) -> None:
    source = tmp_path / "gate.log"
    output = tmp_path / "scorecard.json"
    prefix = "[pod/gate-pod-1/chaos-gate] "
    source.write_text(prefix + scorecard_line("postgres-pod-failure") + "\n", encoding="utf-8")

    command = [
        os.environ.get("PYTHON", "python3"),
        str(EVIDENCE_UTILITY),
        "extract-scorecard",
        "--input",
        str(source),
        "--experiment",
        "postgres-pod-failure",
        "--output",
        str(output),
    ]
    accepted = run(command)
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["experiment"] == "postgres-pod-failure"

    source.write_text(
        "\n".join((prefix + scorecard_line("postgres-pod-failure"), prefix + scorecard_line("postgres-pod-failure")))
        + "\n",
        encoding="utf-8",
    )
    ambiguous = run(command)
    assert ambiguous.returncode == 2
    assert "found 2" in ambiguous.stderr


def test_collector_maps_baseline_evidence_to_development_without_gate_artifacts(tmp_path: Path) -> None:
    env, calls, config = fake_environment(tmp_path)
    output_root = tmp_path / "evidence-output"
    result = run(
        [
            "bash",
            str(COLLECTOR),
            "--collect",
            "--acknowledge-owned-testnet-lab",
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--scenario",
            "baseline",
            "--status",
            "blocked",
            "--run-id",
            "baseline-evidence-1",
        ],
        env=env,
    )

    assert result.returncode == 0, result.stderr
    metadata = json.loads(
        (output_root / "baseline" / "baseline-evidence-1" / "run-metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["namespace"] == "url-shortener-dev"
    assert "kubectl -n resilience-gate get stage dev -o yaml" in calls.read_text(encoding="utf-8")
    assert "url-shortener-staging" not in calls.read_text(encoding="utf-8")


def test_sanitizer_redacts_an_entire_kubernetes_secret_document(tmp_path: Path) -> None:
    output = tmp_path / "sanitized.yaml"
    report = tmp_path / "report.txt"
    result = run(
        [
            os.environ.get("PYTHON", "python3"),
            str(EVIDENCE_UTILITY),
            "sanitize",
            "--input",
            str(FIXTURES / "secret-input.yaml"),
            "--output",
            str(output),
            "--report",
            str(report),
        ]
    )

    assert result.returncode == 0, result.stderr
    sanitized = output.read_text(encoding="utf-8")
    assert "must-not-be-evidence" not in sanitized
    assert "dG9rZW4=" not in sanitized
    assert "should-not-be-retained" not in sanitized
    assert "Kubernetes Secret document" in sanitized
    assert "secret-data" in report.read_text(encoding="utf-8")


def test_metadata_validation_rejects_a_namespace_that_does_not_match_the_scenario(tmp_path: Path) -> None:
    output = tmp_path / "metadata.json"
    digest = "sha256:" + "a" * 64
    result = run(
        [
            os.environ.get("PYTHON", "python3"),
            str(EVIDENCE_UTILITY),
            "write-metadata",
            "--output",
            str(output),
            "--run-id",
            "baseline-wrong-namespace",
            "--scenario",
            "baseline",
            "--status",
            "blocked",
            "--collected-at",
            "2026-10-01T00:00:00Z",
            "--repository-revision",
            "abcdef0",
            "--chart-revision",
            "abcdef0",
            "--release-image-digest",
            digest,
            "--gate-runner-image-digest",
            "unavailable",
            "--signer-image-digest",
            "unavailable",
            "--loadgen-image-digest",
            "unavailable",
            "--namespace",
            "url-shortener-staging",
            "--cluster-context",
            EXPECTED_CONTEXT,
            "--file",
            "stage/dev.yaml",
            "--redaction",
            "none",
        ]
    )

    assert result.returncode == 2
    assert "url-shortener-dev" in result.stderr


def test_metadata_validation_rejects_an_out_of_scope_namespace() -> None:
    result = run(
        [
            os.environ.get("PYTHON", "python3"),
            str(EVIDENCE_UTILITY),
            "validate",
            "--schema",
            str(SCHEMA),
            "--metadata",
            str(FIXTURES / "invalid-run-metadata.json"),
        ]
    )

    assert result.returncode == 2
    assert "namespace" in result.stderr
