"""Shared, hermetic test support for the FastAPI application.

Unit tests use an in-process ASGI transport and start with inert dependency
URLs.  They must mock Postgres, Redis, and facilitator behavior explicitly;
the default suite never needs Docker, cloud credentials, an RPC endpoint, or
internet access.  Tests that genuinely require locally started dependencies
must carry ``@pytest.mark.integration`` and are intentionally skipped by the
default pytest command.
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys
from collections.abc import AsyncIterator, Iterator
from types import ModuleType
from typing import Any

import httpx
import pytest


# Apply these before pytest imports any test modules: application settings are
# read at module-import time.  Invalid loopback endpoints fail fast if a test
# accidentally bypasses a mock, while an empty facilitator URL disables paid
# behavior until a payment test opts in and supplies its own mocked endpoint.
TEST_ENVIRONMENT = {
    "BASE_URL": "http://testserver",
    "CODE_LENGTH": "8",
    "DATABASE_URL": "postgresql://test:test@127.0.0.1:1/urlshortener_test",
    "REDIS_URL": "redis://127.0.0.1:1/15",
    "FACILITATOR_URL": "",
    "RPC_URL": "",
    "SERVICE_WALLET_ADDRESS": "",
    "WALLET_KEY_1": "",
    "WALLET_KEY_2": "",
    "WALLET_KEY_3": "",
}
os.environ.update(TEST_ENVIRONMENT)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Restore the hermetic defaults for every test.

    Individual tests can still use ``monkeypatch`` to exercise a configuration
    branch.  The next test gets the known-safe values again.
    """
    for name, value in TEST_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    yield


@pytest.fixture(autouse=True)
def block_network(request: pytest.FixtureRequest) -> Iterator[None]:
    """Disable sockets outside explicitly marked local integration tests."""
    if request.node.get_closest_marker("integration"):
        yield
        return

    # Resolve lazily so pytest-socket is needed only when pytest executes the
    # suite, not when a tool merely imports this conftest module.
    request.getfixturevalue("socket_disabled")
    yield


@pytest.fixture
def app_module() -> ModuleType:
    """Import the application only after the test environment is in place."""
    return importlib.import_module("app.main")


@pytest.fixture
async def api_client(app_module: ModuleType) -> AsyncIterator[httpx.AsyncClient]:
    """An async client that exercises routes without opening a TCP socket.

    ``ASGITransport`` intentionally does not drive the lifespan protocol.
    Tests that need startup behavior should patch its dependency constructors
    first, then use ``asgi_lifespan.LifespanManager`` explicitly.
    """
    transport = httpx.ASGITransport(app=app_module.app, raise_app_exceptions=True)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=TEST_ENVIRONMENT["BASE_URL"],
        follow_redirects=False,
    ) as client:
        yield client


async def _close_resource(resource: Any) -> None:
    """Close either a real async client/pool or a lightweight test double."""
    for method_name in ("aclose", "close"):
        method = getattr(resource, method_name, None)
        if callable(method):
            result = method()
            if inspect.isawaitable(result):
                await result
            return


async def _reset_application_state() -> None:
    """Prevent mutable module globals from leaking between route tests."""
    module = sys.modules.get("app.main")
    if module is None:
        return

    for attribute in ("db_pool", "redis_client", "http_client"):
        resource = getattr(module, attribute, None)
        if resource is not None:
            await _close_resource(resource)
            setattr(module, attribute, None)
    if hasattr(module, "_started"):
        module._started = False


@pytest.fixture(autouse=True)
async def reset_application_state() -> AsyncIterator[None]:
    """Give each test a clean app-global state without a real dependency."""
    await _reset_application_state()
    yield
    await _reset_application_state()
