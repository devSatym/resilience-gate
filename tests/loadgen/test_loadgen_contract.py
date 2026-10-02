"""Offline contract checks for the k6 x402/redirect scenario.

These tests intentionally parse and syntax-check the script only. They never
start k6, HTTP, a signer, a facilitator, or a Radius testnet connection.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "kubernetes" / "jobs" / "scripts" / "loadgen.js"


def test_loadgen_script_is_valid_module_syntax() -> None:
    node = shutil.which("node")
    assert node, "node is required to syntax-check the k6 module"

    # `--check` parses stdin as an ES module but does not resolve k6 imports or
    # execute setup/default, so this cannot open a socket.
    result = subprocess.run(
        (node, "--input-type=module", "--check"),
        input=SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_loadgen_requires_explicit_endpoints_and_testnet_terms() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "const BASE_URL = environment('BASE_URL');" in source
    assert "const SIGNER_URL = environment('SIGNER_URL');" in source
    assert "TESTNET_NETWORK = 'eip155:72344'" in source
    assert "NETWORK_CAIP2 must remain the owned testnet" in source
    assert "validateConfiguration();" in source
    assert "before the first HTTP request" in source
    assert "url-shortener-staging.url-shortener-staging" not in source
    assert "facilitator.testnet" not in source
    assert "mainnet" not in source.lower()


def test_loadgen_matches_the_current_app_and_signer_contracts() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    # The application has separate process and dependency endpoints. The
    # signer has a process liveness endpoint and readiness/wallet telemetry.
    assert "${appUrl}/livez" in source
    assert "${appUrl}/ready" in source
    assert "${signerUrl}/livez" in source
    assert "${signerUrl}/health" in source
    assert "${signerUrl}/wallets" in source
    assert "${signerUrl}/sign-permit2" in source

    # 201 is the application's settlement-and-persistence contract. It does
    # not return an invented client-facing settlement header.
    assert "PAYMENT-RESPONSE" not in source
    assert "PAYMENT-REQUIRED" in source
    assert "Unsigned /shorten precheck did not return x402 challenge" in source
    assert "paymentSettledRate.add(created);" in source
    assert "x402Version: 2" in source
    assert "assetTransferMethod: 'permit2'" in source
    assert "PAYMENT-SIGNATURE" in source


def test_loadgen_records_separate_redirect_and_end_to_end_outcomes() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "redirect_ok_rate" in source
    assert "independent_redirect_ok_rate" in source
    assert "end_to_end_success_rate" in source
    assert "end_to_end_duration_ms" in source
    assert "redirects: 0" in source
    assert "example.invalid" in source
    assert "export function independentRedirectProbe()" in source


def test_paid_traffic_marker_is_fixed_and_requires_a_successful_end_to_end_flow() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    payment_flow = source.split("export function paymentFlow()", 1)[1].split(
        "export function independentRedirectProbe()", 1
    )[0]

    assert "PAID_TRAFFIC_READY_MARKER = 'RESILIENCE_GATE_PAID_TRAFFIC_READY v1'" in source
    assert "TRAFFIC_MODE === 'paid' && PAYMENT_ENABLED && created && redirected" in payment_flow
    assert "console.log(PAID_TRAFFIC_READY_MARKER);" in payment_flow
    assert "paidTrafficReadyReported = true;" in payment_flow
    marker_section = payment_flow.split("PAID_TRAFFIC_READY_MARKER", 1)[1]
    assert "paymentSignature" not in marker_section
    assert "signerBody" not in marker_section


def test_loadgen_emits_a_sanitized_machine_readable_summary_marker() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    summary = source.split("export function handleSummary(data)", 1)[1]

    assert "RESILIENCE_GATE_K6_SUMMARY " in source
    assert "schema_version: 'resilience-gate.loadgen-summary/v1'" in summary
    assert "'/results/summary.json': serialized" in summary
    assert "stdout: `${SUMMARY_MARKER}${serialized}\\n`" in summary
    assert "data.options" not in summary
    assert "BASE_URL" not in summary
    assert "SIGNER_URL" not in summary
    assert "PAYMENT-SIGNATURE" not in summary
