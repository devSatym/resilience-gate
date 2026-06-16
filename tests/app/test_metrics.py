from __future__ import annotations

import httpx
import pytest

from app.main import Settings, create_app


class Database:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def fetchrow(self, query: str, *args: object) -> dict[str, str] | None:
        return {"url": "https://example.test/from-database"}


class Cache:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get(self, code: str) -> str | None:
        return "https://example.test/from-cache"

    async def set(self, code: str, url: str) -> None:
        return None


@pytest.mark.asyncio
async def test_metrics_expose_cache_and_dependency_telemetry() -> None:
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=Database(),  # type: ignore[arg-type]
        cache=Cache(),  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://short.test",
        follow_redirects=False,
    ) as client:
        assert (await client.get("/ready")).status_code == 200
        assert (await client.get("/cached")).status_code == 302
        metrics = await client.get("/metrics")

    assert metrics.status_code == 200
    assert "url_shortener_cache_hits_total" in metrics.text
    assert 'url_shortener_dependency_up{dependency="postgres"} 1.0' in metrics.text
    assert 'url_shortener_dependency_up{dependency="redis"} 1.0' in metrics.text
