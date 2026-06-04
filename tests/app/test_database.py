from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app import main


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, query: str) -> None:
        self.executed.append(query)

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        return {"query": query, "args": args}


class Acquire:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, *args: object) -> None:
        return None


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.closed = False

    def acquire(self) -> Acquire:
        return Acquire(self.connection)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_database_initializes_schema_and_delegates_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FakePool()

    async def create_pool(*args: object, **kwargs: object) -> FakePool:
        assert args == ("postgresql://test",)
        assert kwargs["min_size"] == 1
        return pool

    monkeypatch.setattr(main.asyncpg, "create_pool", create_pool)
    database = main.Database("postgresql://test")

    await database.connect()
    assert pool.connection.executed == [main.SCHEMA_SQL]
    assert await database.fetchrow("SELECT $1", "value") == {
        "query": "SELECT $1",
        "args": ("value",),
    }

    await database.close()
    assert pool.closed is True


@pytest.mark.asyncio
async def test_database_rejects_queries_before_connection() -> None:
    database = main.Database("postgresql://test")
    with pytest.raises(main.DatabaseUnavailable, match="not ready"):
        await database.fetchrow("SELECT 1")
