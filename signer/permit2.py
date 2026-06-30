"""Pure Permit2 EIP-712 signing helpers.

This module deliberately has no FastAPI, Web3 provider, or environment
dependencies. Permit2 uses unordered bitmap nonces, so a signer can create a
new authorization without an RPC read on its request path.
"""

from __future__ import annotations

import secrets
from typing import Any

from eth_account.messages import encode_typed_data
from eth_account.signers.local import LocalAccount
from eth_utils import is_address, to_checksum_address


MAX_UINT256 = (1 << 256) - 1

# PermitWitnessTransferFrom extends Permit2's PermitTransferFrom with the
# x402 witness consumed by x402ExactPermit2Proxy. The field names and the
# omitted domain version are part of the signature preimage, so do not rename
# or reorder these declarations casually.
PERMIT2_TYPES: dict[str, list[dict[str, str]]] = {
    "PermitWitnessTransferFrom": [
        {"name": "permitted", "type": "TokenPermissions"},
        {"name": "spender", "type": "address"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
        {"name": "witness", "type": "Witness"},
    ],
    "TokenPermissions": [
        {"name": "token", "type": "address"},
        {"name": "amount", "type": "uint256"},
    ],
    "Witness": [
        {"name": "to", "type": "address"},
        {"name": "validAfter", "type": "uint256"},
    ],
}


def _uint256(value: int, field_name: str, *, allow_zero: bool = True) -> int:
    """Validate an integer for an EVM ``uint256`` field."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    minimum = 0 if allow_zero else 1
    if not minimum <= value <= MAX_UINT256:
        raise ValueError(f"{field_name} must fit in a uint256")
    return value


def normalize_address(value: str, field_name: str) -> str:
    """Return a checksummed EVM address or raise a concise configuration error."""

    if not isinstance(value, str) or not is_address(value):
        raise ValueError(f"{field_name} must be a 20-byte EVM address")
    return to_checksum_address(value)


def permit2_domain(chain_id: int, permit2_address: str) -> dict[str, Any]:
    """Build Permit2's EIP-712 domain.

    Permit2 intentionally omits the conventional ``version`` field. Adding one
    produces a signature that the Permit2 contract cannot recover.
    """

    return {
        "name": "Permit2",
        "chainId": _uint256(chain_id, "chain_id", allow_zero=False),
        "verifyingContract": normalize_address(permit2_address, "permit2_address"),
    }


def normalize_v(signature: bytes) -> bytes:
    """Normalize Ethereum's recovery byte to the canonical 27/28 encoding."""

    raw = bytes(signature)
    if len(raw) != 65:
        raise ValueError(f"signature must be 65 bytes, got {len(raw)}")
    recovery_id = raw[64]
    if recovery_id in (0, 1):
        return raw[:64] + bytes([recovery_id + 27])
    if recovery_id in (27, 28):
        return raw
    raise ValueError("signature recovery byte must be 0, 1, 27, or 28")


def build_permit_witness_transfer(
    *,
    chain_id: int,
    permit2_address: str,
    token: str,
    amount: int,
    spender: str,
    pay_to: str,
    deadline: int,
    valid_after: int = 0,
    nonce: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the exact EIP-712 domain and message signed for one payment."""

    domain = permit2_domain(chain_id, permit2_address)
    return domain, {
        "permitted": {
            "token": normalize_address(token, "token"),
            "amount": _uint256(amount, "amount", allow_zero=False),
        },
        "spender": normalize_address(spender, "spender"),
        "nonce": _uint256(nonce, "nonce"),
        "deadline": _uint256(deadline, "deadline", allow_zero=False),
        "witness": {
            "to": normalize_address(pay_to, "pay_to"),
            "validAfter": _uint256(valid_after, "valid_after"),
        },
    }


def sign_permit_witness_transfer(
    account: LocalAccount,
    *,
    chain_id: int,
    permit2_address: str,
    token: str,
    amount: int,
    spender: str,
    pay_to: str,
    deadline: int,
    valid_after: int = 0,
    nonce: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Sign one x402 ``PermitWitnessTransferFrom`` authorization.

    The returned authorization serializes integer fields as strings because it
    is placed in JSON inside the x402 payment header. The typed-data message
    itself retains integers, preserving the EIP-712 hash.
    """

    if nonce is None:
        nonce = secrets.randbits(256)
    domain, message = build_permit_witness_transfer(
        chain_id=chain_id,
        permit2_address=permit2_address,
        token=token,
        amount=amount,
        spender=spender,
        pay_to=pay_to,
        deadline=deadline,
        valid_after=valid_after,
        nonce=nonce,
    )
    signable = encode_typed_data(
        domain_data=domain,
        message_types=PERMIT2_TYPES,
        message_data=message,
    )
    signature = normalize_v(bytes(account.sign_message(signable).signature))
    return "0x" + signature.hex(), {
        "permitted": {
            "token": message["permitted"]["token"],
            "amount": str(message["permitted"]["amount"]),
        },
        "from": normalize_address(account.address, "account.address"),
        "spender": message["spender"],
        "nonce": str(message["nonce"]),
        "deadline": str(message["deadline"]),
        "witness": {
            "to": message["witness"]["to"],
            "validAfter": str(message["witness"]["validAfter"]),
        },
    }
