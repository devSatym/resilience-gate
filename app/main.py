"""The local URL-shortener API.

This module intentionally starts small: configuration and request validation
are kept independent from persistence so each layer can be tested without a
running database or cache.
"""

from __future__ import annotations

import os
import secrets
import string
import asyncio
from dataclasses import dataclass
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import asyncpg
import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, field_validator
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator

from app.payment import (
    FacilitatorClient,
    PaymentRequirements,
    SettlementResult,
    SettlementStatus,
    encode_header,
    payment_required_descriptor,
    settle_payment,
)


CACHE_HITS = Counter("url_shortener_cache_hits_total", "Redis cache hits")
CACHE_MISSES = Counter(
    "url_shortener_cache_misses_total", "Redis misses or unavailable cache fallbacks"
)
URLS_CREATED = Counter("url_shortener_urls_created_total", "New short URLs created")
PAYMENT_OUTCOMES = Counter(
    "url_shortener_payment_outcomes_total",
    "Payment decisions grouped by their fail-closed outcome.",
    ["outcome"],
)
PAYMENT_REPLAYS = Counter(
    "url_shortener_payment_replays_total",
    "Settlement transactions rejected because they were already used.",
)
DEPENDENCY_UP = Gauge(
    "url_shortener_dependency_up",
    "Whether a backing dependency was reachable at the most recent health check.",
    ["dependency"],
)


@dataclass(frozen=True)
class Settings:
    """Runtime settings that are safe to read in local development."""

    base_url: str
    code_length: int
    database_url: str
    redis_url: str
    redis_ttl_seconds: int = 3600
    dependency_timeout_seconds: float = 2.0
    facilitator_url: str = ""
    service_wallet: str = ""
    asset_contract: str = ""
    payment_amount: str = "1000"
    payment_network: str = "eip155:72344"
    payment_timeout_seconds: float = 10.0

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
            redis_ttl_seconds=int(os.getenv("REDIS_TTL_SECONDS", "3600")),
            dependency_timeout_seconds=float(
                os.getenv("DEPENDENCY_TIMEOUT_SECONDS", "2")
            ),
            facilitator_url=os.getenv("FACILITATOR_URL", "").strip().rstrip("/"),
            service_wallet=os.getenv("SERVICE_WALLET_ADDRESS", "").strip(),
            asset_contract=os.getenv("SBC_CONTRACT_ADDRESS", "").strip(),
            payment_amount=os.getenv("SHORTEN_FEE", "1000").strip(),
            payment_network=os.getenv("NETWORK_CAIP2", "eip155:72344").strip(),
            payment_timeout_seconds=float(os.getenv("FACILITATOR_TIMEOUT_SECONDS", "10")),
        )

    @property
    def payment_enabled(self) -> bool:
        return bool(self.facilitator_url and self.service_wallet and self.asset_contract)

    def payment_requirements(self) -> PaymentRequirements:
        if not self.payment_enabled:
            raise ValueError("payment configuration is incomplete")
        return PaymentRequirements(
            scheme="exact",
            network=self.payment_network,
            amount=self.payment_amount,
            asset=self.asset_contract,
            pay_to=self.service_wallet,
            max_timeout_seconds=300,
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

ALTER TABLE urls
    ADD COLUMN IF NOT EXISTS settlement_tx_hash VARCHAR(66),
    ADD COLUMN IF NOT EXISTS payer_address VARCHAR(42),
    ADD COLUMN IF NOT EXISTS settled_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS urls_settlement_tx_hash_unique
    ON urls (settlement_tx_hash)
    WHERE settlement_tx_hash IS NOT NULL;
"""


class DatabaseUnavailable(RuntimeError):
    """Raised when a route is used before the database is ready."""


class Database:
    """Small asyncpg boundary that owns schema setup and pool lifecycle."""

    def __init__(self, url: str, timeout_seconds: float = 2.0) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.pool: asyncpg.Pool | None = None
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> None:
        if self.pool is not None:
            return
        async with self._connect_lock:
            if self.pool is not None:
                return
            pool: asyncpg.Pool | None = None
            try:
                pool = await asyncio.wait_for(
                    asyncpg.create_pool(
                        self.url,
                        min_size=1,
                        max_size=5,
                        command_timeout=self.timeout_seconds,
                    ),
                    timeout=self.timeout_seconds,
                )
                async with pool.acquire() as connection:
                    await asyncio.wait_for(
                        connection.execute(SCHEMA_SQL), timeout=self.timeout_seconds
                    )
                self.pool = pool
            except Exception as exc:
                if pool is not None:
                    await pool.close()
                raise DatabaseUnavailable("database connection failed") from exc

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise DatabaseUnavailable("database is not ready")
        return self.pool

    async def fetchrow(self, query: str, *args: object) -> asyncpg.Record | None:
        try:
            async with self._pool().acquire() as connection:
                return await connection.fetchrow(query, *args)
        except (asyncpg.PostgresError, OSError, asyncio.TimeoutError) as exc:
            # Drop a poisoned pool so the next bounded readiness attempt builds
            # a fresh connection rather than repeating a known-bad one.
            await self.close()
            raise DatabaseUnavailable("database query failed") from exc

    async def ping(self) -> None:
        if self.pool is None:
            await self.connect()
        try:
            await asyncio.wait_for(self.fetchrow("SELECT 1"), timeout=self.timeout_seconds)
        except Exception as exc:
            await self.close()
            raise DatabaseUnavailable("database ping failed") from exc


class CacheUnavailable(RuntimeError):
    """Raised only at the cache boundary; callers fall back to Postgres."""


class Cache:
    """Bounded Redis cache that is never authoritative for URL resolution."""

    def __init__(self, url: str, ttl_seconds: int, timeout_seconds: float = 2.0) -> None:
        self.url = url
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.client: aioredis.Redis | None = None

    async def connect(self) -> None:
        try:
            client = aioredis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            await asyncio.wait_for(client.ping(), timeout=self.timeout_seconds)
            self.client = client
        except Exception:
            # Redis is an optimisation.  Keep the service usable through its
            # Postgres source of truth when the cache starts unavailable.
            self.client = None

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    def _client(self) -> aioredis.Redis:
        if self.client is None:
            raise CacheUnavailable("cache is not ready")
        return self.client

    async def get(self, code: str) -> str | None:
        try:
            return await self._client().get(f"url:{code}")
        except Exception as exc:
            raise CacheUnavailable("cache read failed") from exc

    async def ping(self) -> None:
        try:
            if self.client is None:
                await self.connect()
            await asyncio.wait_for(self._client().ping(), timeout=self.timeout_seconds)
        except Exception as exc:
            raise CacheUnavailable("cache ping failed") from exc

    async def set(self, code: str, url: str) -> None:
        try:
            await self._client().setex(f"url:{code}", self.ttl_seconds, url)
        except Exception as exc:
            raise CacheUnavailable("cache write failed") from exc


ALPHABET = string.ascii_letters + string.digits


def generate_code(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    cache: Cache | None = None,
    code_generator: Callable[[], str] | None = None,
    payment_processor: Callable[[str], Awaitable[SettlementResult]] | None = None,
) -> FastAPI:
    """Build the ASGI application without connecting to infrastructure."""

    configured = settings or Settings.from_env()
    store = database or Database(
        configured.database_url, configured.dependency_timeout_seconds
    )
    url_cache = cache or Cache(
        configured.redis_url,
        configured.redis_ttl_seconds,
        configured.dependency_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal payment_client
        try:
            await store.connect()
        except DatabaseUnavailable:
            # The process stays alive; /ready performs bounded reconnect
            # attempts and keeps it out of Service endpoints until recovery.
            pass
        await url_cache.connect()
        if configured.payment_enabled and payment_processor is None:
            payment_client = httpx.AsyncClient()
        try:
            yield
        finally:
            if payment_client is not None:
                await payment_client.aclose()
                payment_client = None
            await url_cache.close()
            await store.close()

    application = FastAPI(
        title="Resilience Gate URL Shortener",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = configured
    application.state.database = store
    application.state.cache = url_cache
    application.state.has_been_ready = False
    create_code = code_generator or (lambda: generate_code(configured.code_length))
    payment_client: httpx.AsyncClient | None = None

    async def process_payment(header_value: str) -> SettlementResult:
        if payment_processor is not None:
            return await payment_processor(header_value)
        if payment_client is None:
            return SettlementResult(
                SettlementStatus.FACILITATOR_UNAVAILABLE,
                "payment client is not initialised",
            )
        return await settle_payment(
            header_value,
            FacilitatorClient(
                configured.facilitator_url,
                payment_client,
                configured.payment_timeout_seconds,
            ),
            configured.payment_requirements(),
        )

    Instrumentator(
        excluded_handlers=["/livez", "/ready", "/metrics"],
        should_group_status_codes=False,
    ).instrument(application)

    @application.get("/")
    async def index() -> dict[str, str]:
        return {"service": "url-shortener", "status": "configured"}

    @application.get("/livez")
    async def livez() -> dict[str, str]:
        """Process-only liveness: dependency failures must never restart a pod."""

        return {"status": "alive"}

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @application.get("/ready")
    async def ready() -> dict[str, str]:
        """Readiness needs Postgres always and Redis only before first success."""

        try:
            await store.ping()
        except Exception as exc:
            # Keep the original dependency exception out of the response, but
            # never convert it into liveness failure or a 500.
            DEPENDENCY_UP.labels(dependency="postgres").set(0)
            raise HTTPException(status_code=503, detail="database not ready") from exc
        DEPENDENCY_UP.labels(dependency="postgres").set(1)

        if not application.state.has_been_ready:
            try:
                await url_cache.ping()
            except Exception as exc:
                DEPENDENCY_UP.labels(dependency="redis").set(0)
                raise HTTPException(status_code=503, detail="cache not ready") from exc
            DEPENDENCY_UP.labels(dependency="redis").set(1)
            application.state.has_been_ready = True

        return {"status": "ready"}

    @application.post("/shorten", status_code=201)
    async def shorten(
        body: ShortenRequest,
        request: Request,
        payment_signature: str | None = Header(default=None, alias="PAYMENT-SIGNATURE"),
    ):
        """Create one short code per destination URL, reusing an existing one."""

        payment_result: SettlementResult | None = None
        try:
            existing = await store.fetchrow(
                "SELECT code FROM urls WHERE url = $1", body.url
            )
            if existing is not None:
                return JSONResponse(
                    {
                        "code": existing["code"],
                        "short_url": f"{configured.base_url}/{existing['code']}",
                        "original_url": body.url,
                    },
                    status_code=200,
                )

            if configured.payment_enabled:
                if not payment_signature:
                    PAYMENT_OUTCOMES.labels(outcome="required").inc()
                    descriptor = payment_required_descriptor(
                        str(request.url), configured.payment_requirements()
                    )
                    return Response(
                        content="{}",
                        status_code=402,
                        media_type="application/json",
                        headers={"PAYMENT-REQUIRED": encode_header(descriptor)},
                    )
                payment_result = await process_payment(payment_signature)
                PAYMENT_OUTCOMES.labels(outcome=payment_result.status.value).inc()
                if payment_result.status == SettlementStatus.FACILITATOR_UNAVAILABLE:
                    raise HTTPException(status_code=503, detail="payment facilitator unavailable")
                if payment_result.status != SettlementStatus.SETTLED:
                    raise HTTPException(status_code=402, detail="payment was not accepted")

            # A collision is extremely unlikely, but each insertion is still
            # conflict-safe and the URL is re-read before returning failure.
            for _ in range(3):
                code = create_code()
                if payment_result is None:
                    created = await store.fetchrow(
                        """
                        INSERT INTO urls (code, url) VALUES ($1, $2)
                        ON CONFLICT DO NOTHING
                        RETURNING code
                        """,
                        code,
                        body.url,
                    )
                else:
                    created = await store.fetchrow(
                        """
                        INSERT INTO urls (
                            code, url, settlement_tx_hash, payer_address, settled_at
                        ) VALUES ($1, $2, $3, $4, NOW())
                        ON CONFLICT DO NOTHING
                        RETURNING code
                        """,
                        code,
                        body.url,
                        payment_result.transaction_hash,
                        payment_result.payer or None,
                    )
                if created is not None:
                    URLS_CREATED.inc()
                    return {
                        "code": created["code"],
                        "short_url": f"{configured.base_url}/{created['code']}",
                        "original_url": body.url,
                    }

                existing = await store.fetchrow(
                    "SELECT code FROM urls WHERE url = $1", body.url
                )
                if existing is not None:
                    return JSONResponse(
                        {
                            "code": existing["code"],
                            "short_url": f"{configured.base_url}/{existing['code']}",
                            "original_url": body.url,
                        },
                        status_code=200,
                    )

                if payment_result is not None:
                    replay = await store.fetchrow(
                        "SELECT code FROM urls WHERE settlement_tx_hash = $1",
                        payment_result.transaction_hash,
                    )
                    if replay is not None:
                        PAYMENT_REPLAYS.inc()
                        raise HTTPException(
                            status_code=409,
                            detail="payment settlement has already been used",
                        )
        except DatabaseUnavailable as exc:
            raise HTTPException(status_code=503, detail="database unavailable") from exc

        raise HTTPException(status_code=503, detail="could not allocate a short code")

    @application.get("/{code}")
    async def redirect(code: str) -> RedirectResponse:
        """Resolve a short code from Postgres and issue a temporary redirect."""

        try:
            cached_url = await url_cache.get(code)
            if cached_url:
                CACHE_HITS.inc()
                return RedirectResponse(url=cached_url, status_code=302)
            CACHE_MISSES.inc()
        except CacheUnavailable:
            CACHE_MISSES.inc()
            pass

        try:
            row = await store.fetchrow("SELECT url FROM urls WHERE code = $1", code)
        except DatabaseUnavailable as exc:
            raise HTTPException(status_code=503, detail="database unavailable") from exc
        if row is None:
            raise HTTPException(status_code=404, detail="short code not found")
        try:
            await url_cache.set(code, row["url"])
        except CacheUnavailable:
            pass
        return RedirectResponse(url=row["url"], status_code=302)

    return application


app = create_app()
