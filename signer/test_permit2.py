"""Unit tests for pure Permit2 signing helpers; they never contact an RPC."""

from __future__ import annotations

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

from signer.permit2 import (
    MAX_UINT256,
    PERMIT2_TYPES,
    build_permit_witness_transfer,
    normalize_v,
    permit2_domain,
    sign_permit_witness_transfer,
)


# Deterministic Anvil account #0. It is public test data and must never hold
# real funds.
TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
CHAIN_ID = 72344
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
SBC = "0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb"
X402_PROXY = "0x402085c248EeA27D92E8b30b2C58ed07f9E20001"
MERCHANT = "0xbD5fdCde255Abb883cB0C3137037cAef28ed10ac"


def test_permit2_domain_omits_version() -> None:
    domain = permit2_domain(CHAIN_ID, PERMIT2)
    assert set(domain) == {"name", "chainId", "verifyingContract"}
    assert "version" not in domain


@pytest.mark.parametrize("input_v, expected_v", [(0, 27), (1, 28), (27, 27), (28, 28)])
def test_normalize_v_accepts_only_ethereum_recovery_values(
    input_v: int, expected_v: int
) -> None:
    assert normalize_v(bytes(64) + bytes([input_v]))[64] == expected_v


@pytest.mark.parametrize("signature", [b"\x00" * 64, bytes(64) + bytes([2])])
def test_normalize_v_rejects_invalid_signatures(signature: bytes) -> None:
    with pytest.raises(ValueError):
        normalize_v(signature)


def test_signature_recovers_to_signer_and_binds_all_payment_terms() -> None:
    account = Account.from_key(TEST_KEY)
    signature, authorization = sign_permit_witness_transfer(
        account,
        chain_id=CHAIN_ID,
        permit2_address=PERMIT2,
        token=SBC,
        amount=1000,
        spender=X402_PROXY,
        pay_to=MERCHANT,
        deadline=1_780_000_000,
        nonce=0xDEADBEEF,
    )

    domain, message = build_permit_witness_transfer(
        chain_id=CHAIN_ID,
        permit2_address=PERMIT2,
        token=SBC,
        amount=1000,
        spender=X402_PROXY,
        pay_to=MERCHANT,
        deadline=1_780_000_000,
        nonce=0xDEADBEEF,
    )
    signable = encode_typed_data(
        domain_data=domain,
        message_types=PERMIT2_TYPES,
        message_data=message,
    )
    assert Account.recover_message(signable, signature=signature) == account.address
    assert authorization == {
        "permitted": {"token": message["permitted"]["token"], "amount": "1000"},
        "from": account.address,
        "spender": message["spender"],
        "nonce": str(0xDEADBEEF),
        "deadline": "1780000000",
        "witness": {"to": message["witness"]["to"], "validAfter": "0"},
    }


def test_unsupplied_nonce_uses_a_256_bit_random_value(monkeypatch: pytest.MonkeyPatch) -> None:
    account = Account.from_key(TEST_KEY)
    monkeypatch.setattr("signer.permit2.secrets.randbits", lambda bits: MAX_UINT256)
    _, authorization = sign_permit_witness_transfer(
        account,
        chain_id=CHAIN_ID,
        permit2_address=PERMIT2,
        token=SBC,
        amount=1,
        spender=X402_PROXY,
        pay_to=MERCHANT,
        deadline=1,
    )
    assert authorization["nonce"] == str(MAX_UINT256)


@pytest.mark.parametrize(
    ("field", "value"),
    [("amount", 0), ("amount", MAX_UINT256 + 1), ("deadline", 0), ("nonce", -1)],
)
def test_typed_data_rejects_invalid_uint256_values(field: str, value: int) -> None:
    fields = {
        "chain_id": CHAIN_ID,
        "permit2_address": PERMIT2,
        "token": SBC,
        "amount": 1,
        "spender": X402_PROXY,
        "pay_to": MERCHANT,
        "deadline": 1,
        "nonce": 0,
    }
    fields[field] = value
    with pytest.raises(ValueError):
        build_permit_witness_transfer(**fields)
