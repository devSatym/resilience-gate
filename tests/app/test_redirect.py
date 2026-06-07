from __future__ import annotations

import httpx
import pytest

from app.main import Settings, create_app


class RedirectDatabase:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetchrow(self, query: str, *args: object) -> dict[str, str] | None:
        assert query == "SELECT url FROM urls WHERE code = $1"
        if args == ("known123",):
            return {"url": "https://example.test/destination"}
        return None


@pytest.mark.asyncio
async def test_redirects_known_short_code() -> None:
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=RedirectDatabase(),  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://short.test",
        follow_redirects=False,
    ) as client:
        response = await client.get("/known123")

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.test/destination"


@pytest.mark.asyncio
async def test_returns_not_found_for_unknown_code() -> None:
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=RedirectDatabase(),  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as client:
        response = await client.get("/missing")

    assert response.status_code == 404
