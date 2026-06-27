"""Hermetic end-to-end contract for the application/facilitator boundary."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager

from app.main import Settings, create_app
from app.payment import decode_header, encode_header


class Database:
    def __init__(self) -> None:
        self.by_url: dict[str, str] = {}
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
        self.by_url[url] = code
        self.by_transaction[transaction] = code
        return {"code": code}


class Cache:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None


def settings() -> Settings:
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
@respx.mock
async def test_application_and_facilitator_share_server_owned_payment_terms() -> None:
    verify = respx.post("https://facilitator.test/verify").respond(200, json={"isValid": True})
    settle = respx.post("https://facilitator.test/settle").respond(
        200, json={"success": True, "transaction": "0x" + "a" * 64}
    )
    app = create_app(
        settings(),
        database=Database(),  # type: ignore[arg-type]
        cache=Cache(),  # type: ignore[arg-type]
        code_generator=lambda: "contract",
    )

    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://short.test"
        ) as client:
            challenge = await client.post(
                "/shorten", json={"url": "https://example.test/contract"}
            )
            assert challenge.status_code == 402
            terms = decode_header(challenge.headers["PAYMENT-REQUIRED"])["accepts"][0]

            created = await client.post(
                "/shorten",
                json={"url": "https://example.test/contract"},
                headers={"PAYMENT-SIGNATURE": encode_header({"signature": "0xabc"})},
            )

    assert created.status_code == 201
    assert verify.called and settle.called
    verify_body = json.loads(verify.calls[0].request.content)
    settle_body = json.loads(settle.calls[0].request.content)
    assert verify_body["paymentRequirements"] == terms
    assert settle_body["paymentRequirements"] == terms
    assert verify_body["paymentPayload"] == settle_body["paymentPayload"]
