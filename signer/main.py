"""Boot-time wallet configuration for the testnet Permit2 signer.

This module keeps the only RPC work—checking and granting the one-time token
allowance—behind a small synchronous adapter. It can therefore be exercised
with fakes without a provider, wallet secret, or network access.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Protocol

from eth_account import Account
from eth_account.signers.local import LocalAccount
from fastapi import FastAPI
from web3 import HTTPProvider, Web3

try:  # Supports package imports in tests and ``uvicorn main:app`` later.
    from .permit2 import MAX_UINT256, normalize_address
except ImportError:  # pragma: no cover - exercised by the container entrypoint.
    from permit2 import MAX_UINT256, normalize_address


logger = logging.getLogger("resilience_gate.signer")

DEFAULT_CHAIN_ID = 72344
DEFAULT_TOKEN_ADDRESS = "0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb"
DEFAULT_PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
DEFAULT_X402_PROXY_ADDRESS = "0x402085c248EeA27D92E8b30b2C58ed07f9E20001"

# Minimal ABI for the one-time Permit2 allowance bootstrap. No payment
# transfer or nonce RPC method belongs in this component.
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
        # private material in a log or exception response.
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

    Creating the provider does not open a connection. ``verify_chain`` and the
    methods that follow run only during application startup.
    """

    def __init__(self, settings: SignerSettings):
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


class SignerService:
    """Owns wallet bootstrap state and exposes no request-time RPC method."""

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
            # Detail is safe configuration context and never includes raw keys.
            self.configuration_error = str(exc)
            logger.error("signer configuration is invalid: %s", self.configuration_error)

    @property
    def ready(self) -> bool:
        return self._state == "ready"

    @property
    def state(self) -> str:
        return self._state

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

    def bootstrap(self) -> BootstrapSummary:
        """Idempotently grant Permit2 allowance to unready configured wallets.

        A partial boot remains usable: successfully approved wallets retain
        their state while failed slots can be retried after an operator fixes
        the RPC or funding condition.
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
                self._set_state_from_wallets()
                return self._summary(attempted_wallets=len(pending))

            for slot in pending:
                try:
                    slot.sbc_balance = client.balance_of(slot.address)
                    slot.permit2_allowance = client.allowance(
                        slot.address, self.settings.permit2_address
                    )
                    if slot.permit2_allowance >= self.settings.default_amount:
                        slot.bootstrapped = True
                        slot.last_error = None
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
                    logger.info(
                        "Permit2 approval completed for wallet index=%s tx=%s",
                        slot.index,
                        receipt.transaction_hash,
                    )
                except Exception:
                    slot.last_error = "Permit2 approval bootstrap failed"
                    logger.exception("Permit2 bootstrap failed for wallet index=%s", slot.index)

            self._set_state_from_wallets()
            return self._summary(attempted_wallets=len(pending))


def create_app(
    settings: SignerSettings | None = None,
    *,
    approval_client: ApprovalClient | None = None,
    approval_client_factory: Callable[[SignerSettings], ApprovalClient] = Web3ApprovalClient,
) -> FastAPI:
    """Create a shell whose lifespan performs the injected, bounded bootstrap.

    HTTP health and signing routes are added with telemetry in the next change;
    keeping the lifecycle constructor here makes startup behavior testable now.
    """

    service = SignerService(
        settings or SignerSettings.from_env(),
        approval_client=approval_client,
        approval_client_factory=approval_client_factory,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await asyncio.to_thread(service.bootstrap)
        yield

    application = FastAPI(
        title="Resilience Gate Permit2 Signer",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.signer_service = service
    return application


# Importing the module is credential- and network-free. The only provider work
# happens during ASGI startup after configuration has been validated.
app = create_app()
