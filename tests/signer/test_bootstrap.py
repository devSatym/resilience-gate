"""Hermetic coverage for Permit2 approval bootstrap behavior."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from asgi_lifespan import LifespanManager

from signer.main import (
    MAX_UINT256,
    ApprovalReceipt,
    SignerService,
    SignerSettings,
    create_app,
)


TEST_KEY_1 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_KEY_2 = "0x59c6995e998f97a5a0044976f0945389dc9e86dae88c7a8410ca61b306b2f24d"
MERCHANT = "0xbD5fdCde255Abb883cB0C3137037cAef28ed10ac"


@dataclass
class FakeApprovalClient:
    """In-memory RPC double; tests prove startup does not need a provider."""

    allowances: dict[str, int] = field(default_factory=dict)
    balances: dict[str, int] = field(default_factory=dict)
    rejected_approvals: set[str] = field(default_factory=set)
    reject_chain: bool = False
    verify_calls: int = 0
    balance_calls: int = 0
    allowance_calls: int = 0
    approvals: list[str] = field(default_factory=list)

    def verify_chain(self, expected_chain_id: int) -> None:
        self.verify_calls += 1
        assert expected_chain_id == 72344
        if self.reject_chain:
            raise RuntimeError("offline test RPC")

    def balance_of(self, address: str) -> int:
        self.balance_calls += 1
        return self.balances.get(address, 50_000)

    def allowance(self, owner: str, spender: str) -> int:
        self.allowance_calls += 1
        return self.allowances.get(owner, 0)

    def approve(self, wallet, spender: str, chain_id: int, timeout_seconds: float) -> ApprovalReceipt:
        assert chain_id == 72344
        assert timeout_seconds > 0
        self.approvals.append(wallet.address)
        if wallet.address in self.rejected_approvals:
            return ApprovalReceipt(succeeded=False)
        self.allowances[wallet.address] = MAX_UINT256
        return ApprovalReceipt(succeeded=True, transaction_hash="0xapproval", gas_used=123_456)


def signer_settings(*keys: str) -> SignerSettings:
    return SignerSettings(
        rpc_url="http://127.0.0.1:1",
        service_wallet_address=MERCHANT,
        wallet_private_keys=tuple(keys),
    )


def test_bootstrap_approves_only_wallets_below_working_threshold() -> None:
    service = SignerService(signer_settings(TEST_KEY_1, TEST_KEY_2))
    already_approved, needs_approval = (slot.address for slot in service.wallets)
    client = FakeApprovalClient(allowances={already_approved: 1000})
    service = SignerService(
        signer_settings(TEST_KEY_1, TEST_KEY_2), approval_client=client
    )

    summary = service.bootstrap()

    assert summary.ready_wallets == 2
    assert summary.total_wallets == 2
    assert summary.attempted_wallets == 2
    assert client.approvals == [needs_approval]
    assert all(slot.bootstrapped for slot in service.wallets)
    assert service.ready


def test_bootstrap_is_idempotent_after_a_successful_run() -> None:
    client = FakeApprovalClient()
    service = SignerService(signer_settings(TEST_KEY_1), approval_client=client)

    service.bootstrap()
    first_approvals = list(client.approvals)
    first_verify_calls = client.verify_calls
    second = service.bootstrap()

    assert first_approvals
    assert client.approvals == first_approvals
    assert client.verify_calls == first_verify_calls
    assert second.attempted_wallets == 0


def test_partial_boot_keeps_successful_wallet_available() -> None:
    initial = SignerService(signer_settings(TEST_KEY_1, TEST_KEY_2))
    rejected_address = initial.wallets[1].address
    client = FakeApprovalClient(rejected_approvals={rejected_address})
    service = SignerService(
        signer_settings(TEST_KEY_1, TEST_KEY_2), approval_client=client
    )

    summary = service.bootstrap()

    assert summary.ready_wallets == 1
    assert service.ready
    assert service.wallets[0].bootstrapped is True
    assert service.wallets[1].bootstrapped is False
    assert service.wallets[1].last_error == "Permit2 approval bootstrap failed"


def test_failed_chain_verification_never_attempts_an_approval() -> None:
    client = FakeApprovalClient(reject_chain=True)
    service = SignerService(signer_settings(TEST_KEY_1), approval_client=client)

    summary = service.bootstrap()

    assert summary.ready_wallets == 0
    assert service.state == "degraded"
    assert client.approvals == []


def test_missing_configuration_does_not_open_an_rpc_connection() -> None:
    service = SignerService(SignerSettings())

    summary = service.bootstrap()

    assert summary.total_wallets == 0
    assert service.state == "unconfigured"
    assert service.configuration_error == "RPC_URL is required"


@pytest.mark.asyncio
async def test_lifespan_bootstraps_only_the_injected_client() -> None:
    client = FakeApprovalClient()
    application = create_app(signer_settings(TEST_KEY_1), approval_client=client)

    async with LifespanManager(application):
        assert application.state.signer_service.ready
        assert client.verify_calls == 1
        assert len(client.approvals) == 1
