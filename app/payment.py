"""x402 value types and header codecs.

Network calls deliberately live elsewhere. Keeping the wire format pure makes
malformed client input testable without a wallet, facilitator, or RPC endpoint.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx


class PaymentHeaderError(ValueError):
    """A client-supplied x402 header was not valid base64 JSON."""


class FacilitatorUnavailable(RuntimeError):
    """The facilitator could not be contacted or returned an HTTP failure."""


class SettlementStatus(StrEnum):
    SETTLED = "settled"
    SIGNATURE_INVALID = "signature_invalid"
    VERIFY_REJECTED = "verify_rejected"
    SETTLE_REJECTED = "settle_rejected"
    INVALID_RESPONSE = "invalid_response"
    FACILITATOR_UNAVAILABLE = "facilitator_unavailable"


@dataclass(frozen=True)
class SettlementResult:
    status: SettlementStatus
    message: str
    transaction_hash: str = ""
    payer: str = ""


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


_TRANSACTION_HASH = re.compile(r"^0x[a-fA-F0-9]{64}$")
_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")


def validate_verify_response(response: dict[str, Any]) -> SettlementResult | None:
    """Return a terminal rejection for invalid `/verify` output, if any."""

    verdict = response.get("isValid")
    if verdict is True:
        return None
    if verdict is not False:
        return SettlementResult(
            SettlementStatus.INVALID_RESPONSE,
            "facilitator verify response has no boolean isValid field",
        )
    reason = response.get("invalidReason") or response.get("invalidMessage") or "verify rejected"
    if not isinstance(reason, str):
        return SettlementResult(
            SettlementStatus.INVALID_RESPONSE,
            "facilitator verify rejection reason is not text",
        )
    status = (
        SettlementStatus.SIGNATURE_INVALID
        if "signature" in reason.lower()
        else SettlementStatus.VERIFY_REJECTED
    )
    try:
        payer = _validated_payer(response.get("payer"))
    except ValueError as exc:
        return SettlementResult(SettlementStatus.INVALID_RESPONSE, str(exc))
    return SettlementResult(status, reason, payer=payer)


def _validated_payer(value: object) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not _ADDRESS.fullmatch(value):
        raise ValueError("facilitator payer must be a 20-byte hex address")
    return value


def validate_settle_response(response: dict[str, Any]) -> SettlementResult:
    """Validate a `/settle` result before it can be persisted or returned."""

    success = response.get("success")
    if success is not True:
        if success is False:
            reason = response.get("errorReason") or response.get("errorMessage") or "settle rejected"
            if isinstance(reason, str):
                return SettlementResult(SettlementStatus.SETTLE_REJECTED, reason)
        return SettlementResult(
            SettlementStatus.INVALID_RESPONSE,
            "facilitator settle response has no valid success field",
        )

    transaction = response.get("transaction")
    if not isinstance(transaction, str) or not _TRANSACTION_HASH.fullmatch(transaction):
        return SettlementResult(
            SettlementStatus.INVALID_RESPONSE,
            "facilitator settlement transaction is not a 32-byte hash",
        )
    try:
        payer = _validated_payer(response.get("payer"))
    except ValueError as exc:
        return SettlementResult(SettlementStatus.INVALID_RESPONSE, str(exc))
    return SettlementResult(SettlementStatus.SETTLED, "payment settled", transaction, payer)


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
