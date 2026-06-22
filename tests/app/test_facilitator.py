from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.payment import (
    FacilitatorClient,
    PaymentRequirements,
    SettlementStatus,
    validate_settle_response,
    validate_verify_response,
)


@pytest.fixture
def requirements() -> PaymentRequirements:
    return PaymentRequirements(
        scheme="exact",
        network="eip155:72344",
        amount="1000",
        asset="0x1111111111111111111111111111111111111111",
        pay_to="0x2222222222222222222222222222222222222222",
        max_timeout_seconds=300,
    )


@pytest.mark.asyncio
@respx.mock
async def test_verify_and_settle_send_the_same_signed_payload(
    requirements: PaymentRequirements,
) -> None:
    verify = respx.post("https://facilitator.test/verify").respond(200, json={"isValid": True})
    settle = respx.post("https://facilitator.test/settle").respond(
        200, json={"success": True, "transaction": "0x" + "a" * 64}
    )
    payload = {"signature": "0xabc", "authorization": {"nonce": "1"}}

    async with httpx.AsyncClient() as http_client:
        facilitator = FacilitatorClient("https://facilitator.test", http_client)
        assert await facilitator.verify(payload, requirements) == {"isValid": True}
        assert (await facilitator.settle(payload, requirements))["success"] is True

    assert verify.called and settle.called
    verify_body = json.loads(verify.calls[0].request.content)
    settle_body = json.loads(settle.calls[0].request.content)
    assert verify_body["paymentPayload"] == payload
    assert settle_body["paymentRequirements"]["network"] == "eip155:72344"


def test_invalid_or_incomplete_upstream_responses_cannot_be_treated_as_success() -> None:
    assert validate_verify_response({"isValid": "yes"}).status == SettlementStatus.INVALID_RESPONSE
    assert validate_verify_response(
        {"isValid": False, "invalidReason": "bad signature"}
    ).status == SettlementStatus.SIGNATURE_INVALID
    assert validate_verify_response(
        {"isValid": False, "invalidReason": "bad signature", "payer": "bad"}
    ).status == SettlementStatus.INVALID_RESPONSE
    assert validate_settle_response({"success": True, "transaction": "0xnot-a-hash"}).status == (
        SettlementStatus.INVALID_RESPONSE
    )
    assert validate_settle_response({"success": False, "errorMessage": "denied"}).status == (
        SettlementStatus.SETTLE_REJECTED
    )
