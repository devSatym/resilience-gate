from __future__ import annotations

import httpx
import pytest

from app.main import Settings, create_app
from app.payment import SettlementResult, SettlementStatus, decode_header, encode_header


class MemoryDatabase:
    def __init__(self) -> None:
        self.by_url: dict[str, str] = {}
        self.by_code: dict[str, str] = {}

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetchrow(self, query: str, *args: object) -> dict[str, str] | None:
        if query.lstrip().startswith("SELECT"):
            code = self.by_url.get(str(args[0]))
            return {"code": code} if code else None

        code, url = str(args[0]), str(args[1])
        if code in self.by_code or url in self.by_url:
            return None
        self.by_code[code] = url
        self.by_url[url] = code
        return {"code": code}


def payment_settings() -> Settings:
    return Settings(
        "https://short.test",
        8,
        "postgresql://ignored",
        "redis://ignored",
        facilitator_url="https://facilitator.test",
        service_wallet="0x2222222222222222222222222222222222222222",
        asset_contract="0x1111111111111111111111111111111111111111",
    )


@pytest.mark.asyncio
async def test_paid_url_creation_challenges_then_settles_a_valid_signature() -> None:
    calls: list[str] = []

    async def settled(header_value: str) -> SettlementResult:
        calls.append(header_value)
        return SettlementResult(
            SettlementStatus.SETTLED,
            "payment settled",
            transaction_hash="0x" + "a" * 64,
            payer="0x" + "b" * 40,
        )

    app = create_app(
        payment_settings(),
        database=MemoryDatabase(),  # type: ignore[arg-type]
        code_generator=lambda: "paidcode",
        payment_processor=settled,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as client:
        challenge = await client.post(
            "/shorten", json={"url": "https://example.test/paid"}
        )
        assert challenge.status_code == 402
        requirements = decode_header(challenge.headers["PAYMENT-REQUIRED"])
        assert requirements["accepts"][0]["extra"]["assetTransferMethod"] == "permit2"

        signature = encode_header({"signature": "0xsignature", "nonce": "1"})
        created = await client.post(
            "/shorten",
            json={"url": "https://example.test/paid"},
            headers={"PAYMENT-SIGNATURE": signature},
        )

    assert created.status_code == 201
    assert created.json()["code"] == "paidcode"
    assert calls == [signature]


@pytest.mark.asyncio
async def test_paid_url_creation_rejects_a_failed_payment() -> None:
    async def rejected(_: str) -> SettlementResult:
        return SettlementResult(SettlementStatus.SIGNATURE_INVALID, "bad signature")

    app = create_app(
        payment_settings(),
        database=MemoryDatabase(),  # type: ignore[arg-type]
        payment_processor=rejected,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as client:
        response = await client.post(
            "/shorten",
            json={"url": "https://example.test/rejected"},
            headers={"PAYMENT-SIGNATURE": encode_header({"signature": "invalid"})},
        )

    assert response.status_code == 402
    assert response.json()["detail"] == "payment was not accepted"
