"""The local URL-shortener API.

This module intentionally starts small: configuration and request validation
are kept independent from persistence so each layer can be tested without a
running database or cache.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import asyncpg
from fastapi import FastAPI
from pydantic import BaseModel, field_validator


@dataclass(frozen=True)
class Settings:
    """Runtime settings that are safe to read in local development."""

    base_url: str
    code_length: int
    database_url: str
    redis_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        base_url = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
        code_length = int(os.getenv("CODE_LENGTH", "8"))
        if code_length < 4 or code_length > 16:
            raise ValueError("CODE_LENGTH must be between 4 and 16")
        return cls(
            base_url=base_url,
            code_length=code_length,
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://urlshortener:password@localhost:5432/urlshortener",
            ),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        )


def validate_destination_url(value: str) -> str:
    """Return a normalised public HTTP(S) destination or raise ``ValueError``."""

    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an absolute http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("url must not contain user credentials")
    return url


class ShortenRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_destination_url(value)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS urls (
    code VARCHAR(16) PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class DatabaseUnavailable(RuntimeError):
    """Raised when a route is used before the database is ready."""


class Database:
    """Small asyncpg boundary that owns schema setup and pool lifecycle."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self.pool is not None:
            return
        pool = await asyncpg.create_pool(
            self.url,
            min_size=1,
            max_size=5,
            command_timeout=5,
        )
        async with pool.acquire() as connection:
            await connection.execute(SCHEMA_SQL)
        self.pool = pool

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise DatabaseUnavailable("database is not ready")
        return self.pool

    async def fetchrow(self, query: str, *args: object) -> asyncpg.Record | None:
        async with self._pool().acquire() as connection:
            return await connection.fetchrow(query, *args)


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
) -> FastAPI:
    """Build the ASGI application without connecting to infrastructure."""

    configured = settings or Settings.from_env()
    store = database or Database(configured.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await store.connect()
        try:
            yield
        finally:
            await store.close()

    application = FastAPI(
        title="Resilience Gate URL Shortener",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = configured
    application.state.database = store

    @application.get("/")
    async def index() -> dict[str, str]:
        return {"service": "url-shortener", "status": "configured"}

    return application


app = create_app()
