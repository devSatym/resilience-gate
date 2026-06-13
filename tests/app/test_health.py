from __future__ import annotations

import httpx
import pytest

from app.main import Settings, create_app


class ExplodingDependency:
    async def connect(self) -> None:
        raise AssertionError("liveness must not connect dependencies")

    async def close(self) -> None:
        return None

    async def fetchrow(self, *args: object) -> None:
        raise AssertionError("liveness must not query dependencies")


@pytest.mark.asyncio
async def test_liveness_is_process_only() -> None:
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=ExplodingDependency(),  # type: ignore[arg-type]
        cache=ExplodingDependency(),  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as client:
        response = await client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


class ReadinessDatabase:
    def __init__(self) -> None:
        self.up = True

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        if not self.up:
            raise RuntimeError("postgres down")


class ReadinessCache:
    def __init__(self) -> None:
        self.up = True

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        if not self.up:
            raise RuntimeError("redis down")


@pytest.mark.asyncio
async def test_readiness_requires_cache_only_until_first_success() -> None:
    database = ReadinessDatabase()
    cache = ReadinessCache()
    cache.up = False
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=database,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as client:
        assert (await client.get("/ready")).status_code == 503
        cache.up = True
        assert (await client.get("/ready")).status_code == 200
        cache.up = False
        assert (await client.get("/ready")).status_code == 200
        database.up = False
        assert (await client.get("/ready")).status_code == 503
