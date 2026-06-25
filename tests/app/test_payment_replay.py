from __future__ import annotations

import httpx
import pytest

from app.main import Settings, create_app
from app.payment import SettlementResult, SettlementStatus, encode_header


class SettlementDatabase:
    def __init__(self) -> None:
        self.by_url: dict[str, str] = {}
        self.by_code: dict[str, str] = {}
        self.by_transaction: dict[str, str] = {}

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetchrow(self, query: str, *args: object) -> dict[str, str] | None:
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT code FROM urls WHERE url"):
            code = self.by_url.get(str(args[0]))
            return {"code": code} if code else None
        if normalized.startswith("SELECT code FROM urls WHERE settlement_tx_hash"):
            code = self.by_transaction.get(str(args[0]))
            return {"code": code} if code else None

        code, url, transaction = str(args[0]), str(args[1]), str(args[2])
        if code in self.by_code or url in self.by_url or transaction in self.by_transaction:
            return None
        self.by_code[code] = url
        self.by_url[url] = code
        self.by_transaction[transaction] = code
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
async def test_a_settlement_transaction_cannot_create_two_urls() -> None:
    transaction_hash = "0x" + "a" * 64

    async def settled(_: str) -> SettlementResult:
        return SettlementResult(
            SettlementStatus.SETTLED,
            "payment settled",
            transaction_hash=transaction_hash,
            payer="0x" + "b" * 40,
        )

    app = create_app(
        payment_settings(),
        database=SettlementDatabase(),  # type: ignore[arg-type]
        code_generator=iter(["firstpaid", "secondpay"]).__next__,
        payment_processor=settled,
    )
    headers = {"PAYMENT-SIGNATURE": encode_header({"signature": "0xabc"})}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as client:
        first = await client.post(
            "/shorten", json={"url": "https://example.test/one"}, headers=headers
        )
        replay = await client.post(
            "/shorten", json={"url": "https://example.test/two"}, headers=headers
        )

    assert first.status_code == 201
    assert replay.status_code == 409
    assert replay.json()["detail"] == "payment settlement has already been used"
