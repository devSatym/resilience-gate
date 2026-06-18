"""Integration-level contract for recovery semantics.

The same behavior is exercised against Compose by scripts/smoke-local.sh. This
in-process check protects the contract quickly in CI without opening a socket.
"""

from __future__ import annotations

import httpx
import pytest

from app.main import Settings, create_app


class RecoveringDatabase:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def fetchrow(self, query: str, *args: object) -> dict[str, str] | None:
        if query.startswith("SELECT"):
            return {"url": "https://example.test/recovery"}
        return None


class ToggleCache:
    def __init__(self) -> None:
        self.up = True

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        if not self.up:
            raise RuntimeError("redis down")

    async def get(self, code: str) -> str | None:
        if not self.up:
            from app.main import CacheUnavailable

            raise CacheUnavailable("redis down")
        return None

    async def set(self, code: str, url: str) -> None:
        if not self.up:
            from app.main import CacheUnavailable

            raise CacheUnavailable("redis down")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_outage_preserves_liveness_and_uses_database_fallback() -> None:
    cache = ToggleCache()
    app = create_app(
        Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=RecoveringDatabase(),  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://short.test",
        follow_redirects=False,
    ) as client:
        assert (await client.get("/ready")).status_code == 200
        cache.up = False
        assert (await client.get("/livez")).status_code == 200
        assert (await client.get("/ready")).status_code == 200
        redirected = await client.get("/recovery")

    assert redirected.status_code == 302
    assert redirected.headers["location"] == "https://example.test/recovery"
