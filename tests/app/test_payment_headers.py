from __future__ import annotations

import pytest

from app.payment import (
    PaymentHeaderError,
    PaymentRequirements,
    decode_header,
    encode_header,
    payment_required_descriptor,
)


def test_header_codecs_round_trip_an_object_deterministically() -> None:
    payload = {"x402Version": 2, "payload": {"signature": "0xabc"}}

    assert decode_header(encode_header(payload)) == payload


@pytest.mark.parametrize("value", ["not-base64", "W10=", "bnVsbA==", "e30=!"])
def test_header_codec_rejects_non_object_or_malformed_values(value: str) -> None:
    with pytest.raises(PaymentHeaderError):
        decode_header(value)


def test_payment_required_descriptor_declares_permit2_terms() -> None:
    requirements = PaymentRequirements(
        scheme="exact",
        network="eip155:72344",
        amount="1000",
        asset="0x1111111111111111111111111111111111111111",
        pay_to="0x2222222222222222222222222222222222222222",
        max_timeout_seconds=300,
    )

    descriptor = payment_required_descriptor("https://short.test/shorten", requirements)

    assert descriptor["x402Version"] == 2
    assert descriptor["accepts"][0]["extra"]["assetTransferMethod"] == "permit2"
    assert descriptor["accepts"][0]["payTo"] == requirements.pay_to
