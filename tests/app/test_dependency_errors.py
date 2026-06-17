from __future__ import annotations

import httpx
import pytest

from app.main import CacheUnavailable, DatabaseUnavailable, Settings, create_app


class FailingDatabase:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def fetchrow(self, query: str, *args: object) -> None:
        raise DatabaseUnavailable("simulated database outage")


class UnavailableCache:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get(self, code: str) -> None:
        raise CacheUnavailable("simulated cache outage")

    async def set(self, code: str, url: str) -> None:
        raise CacheUnavailable("simulated cache outage")


@pytest.mark.asyncio
async def test_database_failures_are_consistent_for_create_and_redirect() -> None:
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=FailingDatabase(),  # type: ignore[arg-type]
        cache=UnavailableCache(),  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as client:
        create = await client.post("/shorten", json={"url": "https://example.test"})
        redirect = await client.get("/missing")

    assert create.status_code == 503
    assert redirect.status_code == 503
    assert create.json()["detail"] == redirect.json()["detail"] == "database unavailable"
