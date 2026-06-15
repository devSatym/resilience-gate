from __future__ import annotations

import httpx
import pytest

from app import main


class RecoveringConnection:
    async def execute(self, query: str) -> None:
        return None

    async def fetchrow(self, query: str, *args: object) -> dict[str, int]:
        return {"ok": 1}


class Acquire:
    async def __aenter__(self) -> RecoveringConnection:
        return RecoveringConnection()

    async def __aexit__(self, *args: object) -> None:
        return None


class RecoveringPool:
    def acquire(self) -> Acquire:
        return Acquire()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_database_retries_after_a_bounded_failed_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def create_pool(*args: object, **kwargs: object) -> RecoveringPool:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("database unavailable")
        return RecoveringPool()

    monkeypatch.setattr(main.asyncpg, "create_pool", create_pool)
    database = main.Database("postgresql://ignored", timeout_seconds=0.1)

    with pytest.raises(main.DatabaseUnavailable):
        await database.ping()
    await database.ping()
    assert attempts == 2


class RecoveringDatabase:
    def __init__(self) -> None:
        self.calls = 0

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        self.calls += 1
        if self.calls == 1:
            raise main.DatabaseUnavailable("temporary outage")


class ReadyCache:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None


@pytest.mark.asyncio
async def test_readiness_recovers_without_liveness_restart() -> None:
    database = RecoveringDatabase()
    app = main.create_app(
        main.Settings("https://short.test", 8, "postgresql://ignored", "redis://ignored"),
        database=database,  # type: ignore[arg-type]
        cache=ReadyCache(),  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://short.test"
    ) as client:
        assert (await client.get("/ready")).status_code == 503
        assert (await client.get("/livez")).status_code == 200
        assert (await client.get("/ready")).status_code == 200
