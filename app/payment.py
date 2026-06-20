"""x402 value types and header codecs.

Network calls deliberately live elsewhere. Keeping the wire format pure makes
malformed client input testable without a wallet, facilitator, or RPC endpoint.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any


class PaymentHeaderError(ValueError):
    """A client-supplied x402 header was not valid base64 JSON."""


@dataclass(frozen=True)
class PaymentRequirements:
    scheme: str
    network: str
    amount: str
    asset: str
    pay_to: str
    max_timeout_seconds: int

    def as_dict(self, *, transfer_method: str = "permit2") -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "network": self.network,
            "amount": self.amount,
            "asset": self.asset,
            "payTo": self.pay_to,
            "maxTimeoutSeconds": self.max_timeout_seconds,
            "extra": {"assetTransferMethod": transfer_method},
        }


def encode_header(value: dict[str, Any]) -> str:
    """Return standard base64 JSON suitable for an x402 HTTP header."""

    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.b64encode(encoded).decode("ascii")


def decode_header(value: str) -> dict[str, Any]:
    """Decode a base64 JSON object and reject ambiguous client input."""

    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
        parsed = json.loads(decoded)
    except (UnicodeEncodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise PaymentHeaderError("header must be base64-encoded JSON") from exc
    if not isinstance(parsed, dict):
        raise PaymentHeaderError("header JSON must be an object")
    return parsed


def payment_required_descriptor(
    resource_url: str, requirements: PaymentRequirements
) -> dict[str, Any]:
    """Build the x402 v2 challenge sent with a 402 response."""

    return {
        "x402Version": 2,
        "error": "PAYMENT-SIGNATURE header is required",
        "resource": {
            "url": resource_url,
            "description": "Create a shortened URL",
            "mimeType": "application/json",
        },
        "accepts": [requirements.as_dict()],
    }
