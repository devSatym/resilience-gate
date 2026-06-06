from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from app.main import Settings, create_app


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


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    database = MemoryDatabase()
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=database,  # type: ignore[arg-type]
        code_generator=iter(["firstcode", "secondcode"]).__next__,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as async_client:
        yield async_client


@pytest.mark.asyncio
async def test_creates_a_short_url(client: httpx.AsyncClient) -> None:
    response = await client.post("/shorten", json={"url": "https://example.test/article"})

    assert response.status_code == 201
    assert response.json() == {
        "code": "firstcode",
        "short_url": "https://short.test/firstcode",
        "original_url": "https://example.test/article",
    }


@pytest.mark.asyncio
async def test_reuses_existing_url_without_consuming_another_code(client: httpx.AsyncClient) -> None:
    first = await client.post("/shorten", json={"url": "https://example.test/article"})
    second = await client.post("/shorten", json={"url": "https://example.test/article"})

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["code"] == "firstcode"
