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

import httpx


class PaymentHeaderError(ValueError):
    """A client-supplied x402 header was not valid base64 JSON."""


class FacilitatorUnavailable(RuntimeError):
    """The facilitator could not be contacted or returned an HTTP failure."""


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


class FacilitatorClient:
    """Small injected HTTP client for x402 `/verify` and `/settle` calls."""

    def __init__(self, base_url: str, client: httpx.AsyncClient, timeout_seconds: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def _post(
        self,
        endpoint: str,
        payment_payload: dict[str, Any],
        requirements: PaymentRequirements,
    ) -> dict[str, Any]:
        body = {
            "x402Version": 2,
            "paymentPayload": payment_payload,
            "paymentRequirements": requirements.as_dict(),
        }
        try:
            response = await self.client.post(
                f"{self.base_url}{endpoint}", json=body, timeout=self.timeout_seconds
            )
            response.raise_for_status()
            parsed = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise FacilitatorUnavailable(f"facilitator {endpoint} unavailable") from exc
        if not isinstance(parsed, dict):
            raise FacilitatorUnavailable(f"facilitator {endpoint} returned a non-object response")
        return parsed

    async def verify(
        self, payment_payload: dict[str, Any], requirements: PaymentRequirements
    ) -> dict[str, Any]:
        return await self._post("/verify", payment_payload, requirements)

    async def settle(
        self, payment_payload: dict[str, Any], requirements: PaymentRequirements
    ) -> dict[str, Any]:
        return await self._post("/settle", payment_payload, requirements)
