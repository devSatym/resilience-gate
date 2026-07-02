"""ASGI coverage for signer health, cached wallet state, and local signing."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pytest
from asgi_lifespan import LifespanManager
from eth_account import Account
from eth_account.messages import encode_typed_data

from signer.main import ApprovalReceipt, SignerSettings, create_app
from signer.permit2 import PERMIT2_TYPES, build_permit_witness_transfer


TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
MERCHANT = "0xbD5fdCde255Abb883cB0C3137037cAef28ed10ac"


@dataclass
class CachedApprovalClient:
    """A no-network double that records every boot-time RPC-like operation."""

    verify_calls: int = 0
    balance_calls: int = 0
    allowance_calls: int = 0
    approval_calls: int = 0
    allowances: dict[str, int] = field(default_factory=dict)

    def verify_chain(self, expected_chain_id: int) -> None:
        self.verify_calls += 1
        assert expected_chain_id == 72344

    def balance_of(self, address: str) -> int:
        self.balance_calls += 1
        return 42_000

    def allowance(self, owner: str, spender: str) -> int:
        self.allowance_calls += 1
        return self.allowances.get(owner, 0)

    def approve(self, wallet, spender: str, chain_id: int, timeout_seconds: float) -> ApprovalReceipt:
        self.approval_calls += 1
        self.allowances[wallet.address] = 2**256 - 1
        return ApprovalReceipt(succeeded=True, transaction_hash="0xapproval", gas_used=123)


def settings() -> SignerSettings:
    return SignerSettings(
        rpc_url="http://127.0.0.1:1",
        service_wallet_address=MERCHANT,
        wallet_private_keys=(TEST_KEY,),
    )


@pytest.mark.asyncio
async def test_health_wallets_and_metrics_use_boot_cached_values() -> None:
    rpc = CachedApprovalClient()
    application = create_app(settings(), approval_client=rpc)

    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json() == {
                "status": "ready",
                "state": "ready",
                "chain_id": 72344,
                "network": "eip155:72344",
                "wallet_count": 1,
                "wallets_bootstrapped": 1,
                "service_wallet": MERCHANT,
                "token_contract": "0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb",
                "permit2_contract": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
                "x402_proxy": "0x402085c248EeA27D92E8b30b2C58ed07f9E20001",
                "reason": None,
            }

            rpc_calls_after_boot = (rpc.balance_calls, rpc.allowance_calls, rpc.approval_calls)
            wallets = await client.get("/wallets")
            assert wallets.status_code == 200
            assert wallets.json()["wallets"] == [
                {
                    "wallet_index": 0,
                    "address": Account.from_key(TEST_KEY).address,
                    "sbc_balance": 42_000,
                    "permit2_allowance": 2**256 - 1,
                    "bootstrapped": True,
                }
            ]
            assert (rpc.balance_calls, rpc.allowance_calls, rpc.approval_calls) == rpc_calls_after_boot

            metrics = await client.get("/metrics")
            assert metrics.status_code == 200
            assert "signer_wallet_sbc_balance_units" in metrics.text
            assert "signer_wallet_permit2_allowance_units" in metrics.text
            assert "signer_permit2_approval_total" in metrics.text


@pytest.mark.asyncio
async def test_sign_endpoint_returns_recoverable_authorization_without_rpc() -> None:
    rpc = CachedApprovalClient()
    application = create_app(settings(), approval_client=rpc)

    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            rpc_calls_after_boot = (rpc.verify_calls, rpc.balance_calls, rpc.allowance_calls)
            response = await client.post("/sign-permit2", json={"wallet_index": 0, "amount": 1000})
            assert response.status_code == 200
            payload = response.json()
            authorization = payload["permit2Authorization"]

            domain, message = build_permit_witness_transfer(
                chain_id=72344,
                permit2_address="0x000000000022D473030F116dDEE9F6B43aC78BA3",
                token="0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb",
                amount=1000,
                spender="0x402085c248EeA27D92E8b30b2C58ed07f9E20001",
                pay_to=MERCHANT,
                deadline=int(authorization["deadline"]),
                valid_after=int(authorization["witness"]["validAfter"]),
                nonce=int(authorization["nonce"]),
            )
            recovered = Account.recover_message(
                encode_typed_data(
                    domain_data=domain,
                    message_types=PERMIT2_TYPES,
                    message_data=message,
                ),
                signature=payload["signature"],
            )
            assert recovered == Account.from_key(TEST_KEY).address
            assert authorization["from"] == recovered
            assert authorization["witness"]["to"] == MERCHANT
            assert (rpc.verify_calls, rpc.balance_calls, rpc.allowance_calls) == rpc_calls_after_boot


@pytest.mark.asyncio
async def test_sign_endpoint_rejects_out_of_range_and_non_contract_terms() -> None:
    application = create_app(settings(), approval_client=CachedApprovalClient())

    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (await client.post("/sign-permit2", json={"wallet_index": 1})).status_code == 400
            assert (
                await client.post("/sign-permit2", json={"wallet_index": 0, "amount": 999})
            ).status_code == 400
            assert (
                await client.post(
                    "/sign-permit2", json={"wallet_index": 0, "deadline_seconds": 301}
                )
            ).status_code == 400


@pytest.mark.asyncio
async def test_unconfigured_signer_is_live_but_not_ready_or_signing() -> None:
    application = create_app(SignerSettings())

    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (await client.get("/livez")).status_code == 200
            health = await client.get("/health")
            assert health.status_code == 503
            assert health.json()["reason"] == "RPC_URL is required"
            assert (await client.get("/wallets")).status_code == 503
            assert (await client.post("/sign-permit2", json={"wallet_index": 0})).status_code == 503
