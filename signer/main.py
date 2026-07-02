"""Private-key boundary for testnet x402 Permit2 authorizations.

Only the boot-time allowance bootstrap touches an RPC provider. Signing a
payment is a local EIP-712 operation with a cryptographically random Permit2
bitmap nonce, so a transient RPC outage cannot turn an API request into a
hidden on-chain action.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from eth_account import Account
from eth_account.signers.local import LocalAccount
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from web3 import HTTPProvider, Web3

try:  # Supports both ``uvicorn main:app`` in the image and package imports in tests.
    from .permit2 import MAX_UINT256, normalize_address, sign_permit_witness_transfer
except ImportError:  # pragma: no cover - exercised by the container entrypoint.
    from permit2 import MAX_UINT256, normalize_address, sign_permit_witness_transfer


logger = logging.getLogger("resilience_gate.signer")

DEFAULT_CHAIN_ID = 72344
DEFAULT_TOKEN_ADDRESS = "0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb"
DEFAULT_PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
DEFAULT_X402_PROXY_ADDRESS = "0x402085c248EeA27D92E8b30b2C58ed07f9E20001"

# Minimal ABI for the one-time Permit2 allowance bootstrap and cached wallet
# telemetry. No payment transfer or nonce RPC methods belong in this signer.
ERC20_ABI = [
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "allowance",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "approve",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]


# Per-wallet labels are deliberately bounded by the three configured signer
# slots. Never add request-provided values to these metrics.
SIGN_OUTCOMES = Counter(
    "signer_sign_total",
    "Terminal outcomes of Permit2 signing requests.",
    ["outcome", "wallet_index"],
)
SIGN_DURATION = Histogram(
    "signer_sign_duration_seconds",
    "Local Permit2 signing time, excluding all RPC work.",
    ["outcome"],
    buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1),
)
APPROVAL_OUTCOMES = Counter(
    "signer_permit2_approval_total",
    "One-time Permit2 approval bootstrap outcomes.",
    ["outcome", "wallet_index"],
)
APPROVAL_GAS_USED = Gauge(
    "signer_permit2_approval_gas_used",
    "Gas used by a successful one-time Permit2 approval transaction.",
    ["wallet_index"],
)
WALLET_SBC_BALANCE = Gauge(
    "signer_wallet_sbc_balance_units",
    "Cached raw SBC balance observed during signer bootstrap.",
    ["wallet_index", "address"],
)
WALLET_PERMIT2_ALLOWANCE = Gauge(
    "signer_wallet_permit2_allowance_units",
    "Cached raw SBC allowance granted to Permit2 during bootstrap.",
    ["wallet_index", "address"],
)
SIGNER_READY = Gauge(
    "signer_ready",
    "Whether at least one configured wallet completed Permit2 bootstrap.",
)


def _read_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _read_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _normalize_private_key(value: str) -> str:
    """Normalize a key for eth-account without ever logging its value."""

    key = value.strip()
    if not key:
        raise ValueError("wallet key is empty")
    return key if key.startswith("0x") else f"0x{key}"


@dataclass(frozen=True)
class SignerSettings:
    """Validated configuration owned by the signer process, not callers."""

    rpc_url: str = ""
    chain_id: int = DEFAULT_CHAIN_ID
    network_caip2: str = f"eip155:{DEFAULT_CHAIN_ID}"
    service_wallet_address: str = ""
    token_address: str = DEFAULT_TOKEN_ADDRESS
    permit2_address: str = DEFAULT_PERMIT2_ADDRESS
    x402_proxy_address: str = DEFAULT_X402_PROXY_ADDRESS
    wallet_private_keys: tuple[str, ...] = field(default_factory=tuple, repr=False)
    default_amount: int = 1000
    deadline_seconds: int = 300
    max_deadline_seconds: int = 300
    rpc_timeout_seconds: float = 10.0
    approval_timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "SignerSettings":
        keys: list[str] = []
        saw_empty_slot = False
        for index in range(1, 4):
            key = os.getenv(f"WALLET_KEY_{index}", "").strip()
            if not key:
                saw_empty_slot = True
                continue
            if saw_empty_slot:
                raise ValueError("wallet keys must be configured in contiguous WALLET_KEY_1..3 slots")
            keys.append(_normalize_private_key(key))

        chain_id = _read_int("CHAIN_ID", DEFAULT_CHAIN_ID)
        return cls(
            rpc_url=os.getenv("RPC_URL", "").strip(),
            chain_id=chain_id,
            network_caip2=os.getenv("NETWORK_CAIP2", f"eip155:{chain_id}").strip(),
            service_wallet_address=os.getenv("SERVICE_WALLET_ADDRESS", "").strip(),
            token_address=os.getenv("SBC_CONTRACT_ADDRESS", DEFAULT_TOKEN_ADDRESS).strip(),
            permit2_address=os.getenv("PERMIT2_CONTRACT_ADDRESS", DEFAULT_PERMIT2_ADDRESS).strip(),
            x402_proxy_address=os.getenv("X402_PROXY_ADDRESS", DEFAULT_X402_PROXY_ADDRESS).strip(),
            wallet_private_keys=tuple(keys),
            default_amount=_read_int("SBC_AMOUNT", 1000),
            deadline_seconds=_read_int("DEADLINE_SECONDS", 300),
            max_deadline_seconds=_read_int("MAX_DEADLINE_SECONDS", 300),
            rpc_timeout_seconds=_read_float("RPC_TIMEOUT_SECONDS", 10.0),
            approval_timeout_seconds=_read_float("APPROVAL_TX_TIMEOUT_SECONDS", 60.0),
        )

    def validated(self) -> "SignerSettings":
        """Return normalized settings, rejecting unsafe or incomplete config."""

        if not self.rpc_url:
            raise ValueError("RPC_URL is required")
        if self.chain_id <= 0:
            raise ValueError("CHAIN_ID must be positive")
        if self.network_caip2 != f"eip155:{self.chain_id}":
            raise ValueError("NETWORK_CAIP2 must match CHAIN_ID")
        if not self.wallet_private_keys:
            raise ValueError("at least WALLET_KEY_1 is required")
        if self.default_amount <= 0:
            raise ValueError("SBC_AMOUNT must be positive")
        if self.deadline_seconds <= 0 or self.max_deadline_seconds <= 0:
            raise ValueError("deadline values must be positive")
        if self.deadline_seconds > self.max_deadline_seconds:
            raise ValueError("DEADLINE_SECONDS may not exceed MAX_DEADLINE_SECONDS")
        if self.rpc_timeout_seconds <= 0 or self.approval_timeout_seconds <= 0:
            raise ValueError("RPC timeouts must be positive")

        # Constructing each account validates its key syntax without exposing
        # the private material in a log or exception response.
        for key in self.wallet_private_keys:
            try:
                Account.from_key(_normalize_private_key(key))
            except ValueError as exc:
                raise ValueError("a configured wallet key is invalid") from exc

        return replace(
            self,
            service_wallet_address=normalize_address(
                self.service_wallet_address, "SERVICE_WALLET_ADDRESS"
            ),
            token_address=normalize_address(self.token_address, "SBC_CONTRACT_ADDRESS"),
            permit2_address=normalize_address(self.permit2_address, "PERMIT2_CONTRACT_ADDRESS"),
            x402_proxy_address=normalize_address(self.x402_proxy_address, "X402_PROXY_ADDRESS"),
            wallet_private_keys=tuple(
                _normalize_private_key(key) for key in self.wallet_private_keys
            ),
        )


@dataclass
class WalletSlot:
    """One configured payer wallet; private account material is never repr'd."""

    index: int
    address: str
    account: LocalAccount = field(repr=False)
    bootstrapped: bool = False
    sbc_balance: int | None = None
    permit2_allowance: int | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class ApprovalReceipt:
    """The small receipt shape the bootstrap service needs from an RPC client."""

    succeeded: bool
    transaction_hash: str = ""
    gas_used: int = 0


class ApprovalClient(Protocol):
    """Synchronous boot-only RPC contract; fakes make startup hermetic."""

    def verify_chain(self, expected_chain_id: int) -> None: ...

    def balance_of(self, address: str) -> int: ...

    def allowance(self, owner: str, spender: str) -> int: ...

    def approve(
        self, wallet: WalletSlot, spender: str, chain_id: int, timeout_seconds: float
    ) -> ApprovalReceipt: ...


class Web3ApprovalClient:
    """Concrete boot-only RPC adapter.

    The provider is created without opening a connection. ``verify_chain`` and
    the methods that follow are invoked only from the lifespan bootstrap.
    """

    def __init__(self, settings: SignerSettings):
        self._settings = settings
        self._web3 = Web3(
            HTTPProvider(
                settings.rpc_url,
                request_kwargs={"timeout": settings.rpc_timeout_seconds},
            )
        )
        self._token = self._web3.eth.contract(address=settings.token_address, abi=ERC20_ABI)

    def verify_chain(self, expected_chain_id: int) -> None:
        if not self._web3.is_connected():
            raise RuntimeError("RPC endpoint is unavailable")
        observed_chain_id = self._web3.eth.chain_id
        if observed_chain_id != expected_chain_id:
            raise RuntimeError(
                f"RPC chain ID mismatch: expected {expected_chain_id}, got {observed_chain_id}"
            )

    def balance_of(self, address: str) -> int:
        return int(self._token.functions.balanceOf(address).call())

    def allowance(self, owner: str, spender: str) -> int:
        return int(self._token.functions.allowance(owner, spender).call())

    def approve(
        self, wallet: WalletSlot, spender: str, chain_id: int, timeout_seconds: float
    ) -> ApprovalReceipt:
        approval = self._token.functions.approve(spender, MAX_UINT256)
        try:
            gas_limit = int(approval.estimate_gas({"from": wallet.address}) * 1.5)
        except Exception as exc:
            # Radius's token contract has nonstandard approval work. A bounded
            # fallback keeps boot operational if estimateGas is unavailable.
            logger.warning("approval gas estimate failed for wallet %s: %s", wallet.index, exc)
            gas_limit = 250_000
        transaction = approval.build_transaction(
            {
                "from": wallet.address,
                "chainId": chain_id,
                "nonce": self._web3.eth.get_transaction_count(wallet.address, "pending"),
                "gas": gas_limit,
                "gasPrice": self._web3.eth.gas_price,
            }
        )
        signed = wallet.account.sign_transaction(transaction)
        transaction_hash = self._web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._web3.eth.wait_for_transaction_receipt(
            transaction_hash, timeout=timeout_seconds
        )
        return ApprovalReceipt(
            succeeded=int(receipt["status"]) == 1,
            transaction_hash=transaction_hash.hex(),
            gas_used=int(receipt.get("gasUsed", 0)),
        )


@dataclass(frozen=True)
class BootstrapSummary:
    ready_wallets: int
    total_wallets: int
    attempted_wallets: int


class SignerUnavailable(RuntimeError):
    """Raised when no bootstrapped wallet can safely sign a request."""


class SignerService:
    """Owns wallet state and guarantees that the hot path never calls RPC."""

    def __init__(
        self,
        settings: SignerSettings,
        *,
        approval_client: ApprovalClient | None = None,
        approval_client_factory: Callable[[SignerSettings], ApprovalClient] = Web3ApprovalClient,
    ):
        self._lock = threading.Lock()
        self._approval_client = approval_client
        self._approval_client_factory = approval_client_factory
        self.configuration_error: str | None = None
        self.settings: SignerSettings | None = None
        self.wallets: list[WalletSlot] = []
        self._state = "unconfigured"
        try:
            self.settings = settings.validated()
            self.wallets = [
                WalletSlot(
                    index=index,
                    address=normalize_address(Account.from_key(key).address, "wallet address"),
                    account=Account.from_key(key),
                )
                for index, key in enumerate(self.settings.wallet_private_keys)
            ]
            self._state = "pending"
        except ValueError as exc:
            # The full detail is safe configuration context, but never include
            # raw key material. Route responses can expose it to operators.
            self.configuration_error = str(exc)
            logger.error("signer configuration is invalid: %s", self.configuration_error)

    @property
    def ready(self) -> bool:
        return self._state == "ready"

    @property
    def state(self) -> str:
        return self._state

    def _record_wallet_metrics(self, slot: WalletSlot) -> None:
        labels = {"wallet_index": str(slot.index), "address": slot.address}
        if slot.sbc_balance is not None:
            WALLET_SBC_BALANCE.labels(**labels).set(slot.sbc_balance)
        if slot.permit2_allowance is not None:
            WALLET_PERMIT2_ALLOWANCE.labels(**labels).set(slot.permit2_allowance)

    def _summary(self, attempted_wallets: int = 0) -> BootstrapSummary:
        return BootstrapSummary(
            ready_wallets=sum(slot.bootstrapped for slot in self.wallets),
            total_wallets=len(self.wallets),
            attempted_wallets=attempted_wallets,
        )

    def _set_state_from_wallets(self) -> None:
        if self.configuration_error:
            self._state = "unconfigured"
        elif any(slot.bootstrapped for slot in self.wallets):
            self._state = "ready"
        else:
            self._state = "degraded"
        SIGNER_READY.set(1 if self.ready else 0)

    def bootstrap(self) -> BootstrapSummary:
        """Idempotently grant Permit2 allowance to unready configured wallets.

        A partial boot is usable: successfully approved wallets keep serving,
        while failed slots remain unavailable until a later bootstrap/restart.
        """

        with self._lock:
            if self.configuration_error or self.settings is None:
                self._set_state_from_wallets()
                return self._summary()

            pending = [slot for slot in self.wallets if not slot.bootstrapped]
            if not pending:
                self._set_state_from_wallets()
                return self._summary()

            client = self._approval_client
            if client is None:
                client = self._approval_client_factory(self.settings)
                self._approval_client = client

            try:
                client.verify_chain(self.settings.chain_id)
            except Exception:
                logger.exception("signer bootstrap could not verify the configured RPC chain")
                for slot in pending:
                    slot.last_error = "RPC chain verification failed"
                    APPROVAL_OUTCOMES.labels(
                        outcome="approve_failed", wallet_index=str(slot.index)
                    ).inc()
                self._set_state_from_wallets()
                return self._summary(attempted_wallets=len(pending))

            for slot in pending:
                wallet_index = str(slot.index)
                try:
                    slot.sbc_balance = client.balance_of(slot.address)
                    slot.permit2_allowance = client.allowance(
                        slot.address, self.settings.permit2_address
                    )
                    self._record_wallet_metrics(slot)

                    if slot.permit2_allowance >= self.settings.default_amount:
                        slot.bootstrapped = True
                        slot.last_error = None
                        APPROVAL_OUTCOMES.labels(
                            outcome="already_approved", wallet_index=wallet_index
                        ).inc()
                        continue

                    receipt = client.approve(
                        slot,
                        self.settings.permit2_address,
                        self.settings.chain_id,
                        self.settings.approval_timeout_seconds,
                    )
                    if not receipt.succeeded:
                        raise RuntimeError("approval transaction reverted")
                    slot.permit2_allowance = MAX_UINT256
                    slot.bootstrapped = True
                    slot.last_error = None
                    APPROVAL_GAS_USED.labels(wallet_index=wallet_index).set(receipt.gas_used)
                    WALLET_PERMIT2_ALLOWANCE.labels(
                        wallet_index=wallet_index, address=slot.address
                    ).set(slot.permit2_allowance)
                    APPROVAL_OUTCOMES.labels(
                        outcome="approved", wallet_index=wallet_index
                    ).inc()
                    logger.info(
                        "Permit2 approval completed for wallet index=%s tx=%s",
                        slot.index,
                        receipt.transaction_hash,
                    )
                except Exception:
                    slot.last_error = "Permit2 approval bootstrap failed"
                    APPROVAL_OUTCOMES.labels(
                        outcome="approve_failed", wallet_index=wallet_index
                    ).inc()
                    logger.exception("Permit2 bootstrap failed for wallet index=%s", slot.index)

            self._set_state_from_wallets()
            return self._summary(attempted_wallets=len(pending))

    def health_payload(self) -> dict[str, Any]:
        settings = self.settings
        return {
            "status": "ready" if self.ready else "not_ready",
            "state": self.state,
            "chain_id": settings.chain_id if settings else None,
            "network": settings.network_caip2 if settings else None,
            "wallet_count": len(self.wallets),
            "wallets_bootstrapped": sum(slot.bootstrapped for slot in self.wallets),
            "service_wallet": settings.service_wallet_address if settings else None,
            "token_contract": settings.token_address if settings else None,
            "permit2_contract": settings.permit2_address if settings else None,
            "x402_proxy": settings.x402_proxy_address if settings else None,
            "reason": self.configuration_error,
        }

    def wallets_payload(self) -> dict[str, Any]:
        settings = self.settings
        return {
            "chain_id": settings.chain_id if settings else None,
            "network": settings.network_caip2 if settings else None,
            "wallet_count": len(self.wallets),
            "wallets": [
                {
                    "wallet_index": slot.index,
                    "address": slot.address,
                    "sbc_balance": slot.sbc_balance,
                    "permit2_allowance": slot.permit2_allowance,
                    "bootstrapped": slot.bootstrapped,
                }
                for slot in self.wallets
            ],
        }

    def sign(
        self, *, wallet_index: int, amount: int | None, deadline_seconds: int | None
    ) -> tuple[str, dict[str, Any]]:
        """Create a locally signed authorization, with no request-time RPC."""

        if not self.ready or self.settings is None:
            raise SignerUnavailable("no bootstrapped wallet is available")
        if wallet_index < 0 or wallet_index >= len(self.wallets):
            raise IndexError("wallet index is out of range")
        slot = self.wallets[wallet_index]
        if not slot.bootstrapped:
            raise SignerUnavailable("selected wallet is not bootstrapped")

        requested_amount = self.settings.default_amount if amount is None else amount
        if requested_amount != self.settings.default_amount:
            raise ValueError("amount must equal the configured payment amount")
        requested_deadline = (
            self.settings.deadline_seconds if deadline_seconds is None else deadline_seconds
        )
        if not 1 <= requested_deadline <= self.settings.max_deadline_seconds:
            raise ValueError("deadline_seconds exceeds the configured signing window")

        return sign_permit_witness_transfer(
            slot.account,
            chain_id=self.settings.chain_id,
            permit2_address=self.settings.permit2_address,
            token=self.settings.token_address,
            amount=requested_amount,
            spender=self.settings.x402_proxy_address,
            pay_to=self.settings.service_wallet_address,
            deadline=int(time.time()) + requested_deadline,
        )


class SignRequest(BaseModel):
    wallet_index: int = Field(ge=0)
    amount: int | None = Field(default=None, gt=0)
    deadline_seconds: int | None = Field(default=None, gt=0)


def create_app(
    settings: SignerSettings | None = None,
    *,
    approval_client: ApprovalClient | None = None,
    approval_client_factory: Callable[[SignerSettings], ApprovalClient] = Web3ApprovalClient,
) -> FastAPI:
    """Build an ASGI app without contacting an RPC endpoint during import."""

    service = SignerService(
        settings or SignerSettings.from_env(),
        approval_client=approval_client,
        approval_client_factory=approval_client_factory,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # The adapter is synchronous because web3.py's HTTP provider is sync;
        # move it off the event loop but keep the bounded provider timeout.
        await asyncio.to_thread(service.bootstrap)
        yield

    application = FastAPI(
        title="Resilience Gate Permit2 Signer",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.signer_service = service

    @application.get("/livez")
    async def livez() -> dict[str, str]:
        return {"status": "alive"}

    @application.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(
            service.health_payload(), status_code=200 if service.ready else 503
        )

    @application.get("/wallets")
    async def wallets() -> JSONResponse:
        return JSONResponse(
            service.wallets_payload(), status_code=200 if service.ready else 503
        )

    @application.post("/sign-permit2")
    async def sign_permit2(request: SignRequest) -> dict[str, Any]:
        wallet_label = str(request.wallet_index)
        started = time.perf_counter()
        outcome = "signing_error"
        try:
            signature, authorization = service.sign(
                wallet_index=request.wallet_index,
                amount=request.amount,
                deadline_seconds=request.deadline_seconds,
            )
            outcome = "success"
            return {"signature": signature, "permit2Authorization": authorization}
        except IndexError as exc:
            outcome = "wallet_not_found"
            raise HTTPException(status_code=400, detail="wallet_index is out of range") from exc
        except ValueError as exc:
            outcome = "invalid_request"
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SignerUnavailable as exc:
            outcome = "not_bootstrapped"
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Permit2 signing failed for wallet index=%s", request.wallet_index)
            raise HTTPException(status_code=500, detail="Permit2 signing failed") from exc
        finally:
            SIGN_OUTCOMES.labels(outcome=outcome, wallet_index=wallet_label).inc()
            SIGN_DURATION.labels(outcome=outcome).observe(time.perf_counter() - started)

    Instrumentator(
        excluded_handlers=["/livez", "/health", "/wallets", "/metrics"],
        should_group_status_codes=False,
    ).instrument(application).expose(application, include_in_schema=False)
    return application


# Importing this module is safe in a credential-free test or PR environment:
# no socket is opened until the ASGI lifespan begins with valid configuration.
app = create_app()
