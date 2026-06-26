from __future__ import annotations

import httpx
import pytest
from prometheus_client import generate_latest

from app.main import Settings, create_app
from app.payment import FacilitatorClient, PaymentRequirements, SettlementResult, SettlementStatus


class Database:
    def __init__(self) -> None:
        self.by_url: dict[str, str] = {}

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetchrow(self, query: str, *args: object) -> dict[str, str] | None:
        if query.lstrip().startswith("SELECT"):
            code = self.by_url.get(str(args[0]))
            return {"code": code} if code else None
        code, url = str(args[0]), str(args[1])
        if url in self.by_url:
            return None
        self.by_url[url] = code
        return {"code": code}


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
async def test_payment_challenges_and_successes_are_exported_as_metrics() -> None:
    async def settled(_: str) -> SettlementResult:
        return SettlementResult(
            SettlementStatus.SETTLED,
            "payment settled",
            transaction_hash="0x" + "a" * 64,
        )

    app = create_app(
        settings(),
        database=Database(),  # type: ignore[arg-type]
        code_generator=lambda: "metricpay",
        payment_processor=settled,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as client:
        assert (await client.post("/shorten", json={"url": "https://example.test/a"})).status_code == 402
        assert (
            await client.post(
                "/shorten",
                json={"url": "https://example.test/a"},
                headers={"PAYMENT-SIGNATURE": "eyJzaWduYXR1cmUiOiJ4In0="},
            )
        ).status_code == 201
        metrics = await client.get("/metrics")

    assert 'url_shortener_payment_outcomes_total{outcome="required"}' in metrics.text
    assert 'url_shortener_payment_outcomes_total{outcome="settled"}' in metrics.text


@pytest.mark.asyncio
async def test_facilitator_latency_and_outcome_metrics_are_exported() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/verify"
        return httpx.Response(200, json={"isValid": True})

    requirements = PaymentRequirements(
        scheme="exact",
        network="eip155:72344",
        amount="1000",
        asset="0x1111111111111111111111111111111111111111",
        pay_to="0x2222222222222222222222222222222222222222",
        max_timeout_seconds=300,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        facilitator = FacilitatorClient("https://facilitator.test", client)
        assert await facilitator.verify({"signature": "0xabc"}, requirements) == {"isValid": True}

    metrics = generate_latest().decode()
    assert 'url_shortener_facilitator_calls_total{endpoint="verify",outcome="success"}' in metrics
    assert 'url_shortener_facilitator_request_duration_seconds_count{endpoint="verify"}' in metrics
