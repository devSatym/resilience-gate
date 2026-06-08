from __future__ import annotations

import httpx
import pytest

from app.main import CacheUnavailable, Settings, create_app


class RedirectDatabase:
    def __init__(self) -> None:
        self.lookups = 0

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetchrow(self, query: str, *args: object) -> dict[str, str] | None:
        self.lookups += 1
        return {"url": "https://example.test/from-database"}


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_reads = False

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get(self, code: str) -> str | None:
        if self.fail_reads:
            raise CacheUnavailable("simulated outage")
        return self.values.get(code)

    async def set(self, code: str, url: str) -> None:
        self.values[code] = url


@pytest.mark.asyncio
async def test_redirect_populates_cache_and_subsequent_lookup_skips_database() -> None:
    database = RedirectDatabase()
    cache = MemoryCache()
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=database,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://short.test",
        follow_redirects=False,
    ) as client:
        first = await client.get("/cached")
        second = await client.get("/cached")

    assert first.headers["location"] == "https://example.test/from-database"
    assert second.headers["location"] == "https://example.test/from-database"
    assert database.lookups == 1


@pytest.mark.asyncio
async def test_cache_outage_falls_back_to_database() -> None:
    database = RedirectDatabase()
    cache = MemoryCache()
    cache.fail_reads = True
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=database,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://short.test",
        follow_redirects=False,
    ) as client:
        response = await client.get("/cache-down")

    assert response.status_code == 302
    assert database.lookups == 1
