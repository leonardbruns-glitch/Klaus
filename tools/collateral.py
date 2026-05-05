"""
Collateral allowance check + auto-approval for pUSD before V2 fill orders.

Thread-safety: all state is asyncio-local (single event loop assumed).
The module-level _ApprovalGuard serialises concurrent approval attempts so
that two simultaneous order_update events never broadcast competing approve()
transactions or corrupt the nonce chain.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from web3 import AsyncWeb3
from web3.types import TxReceipt

from tools.preflight import V2_EXCHANGE, _ProviderSingleton

log = logging.getLogger(__name__)

# ── Addresses ────────────────────────────────────────────────────────────────

PUSD_ADDRESS = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
UINT256_MAX  = (1 << 256) - 1

_ERC20_ABI = [
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner",   "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount",  "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

# Revert strings that signal the token requires a reset-to-zero before re-approve
_RESET_REQUIRED_PATTERNS = (
    "approve from non-zero to non-zero",
    "allowance to set",
    "non-zero allowance",
)


# ── Result types ──────────────────────────────────────────────────────────────

class CollateralStatus(Enum):
    SUFFICIENT       = auto()  # allowance already covers the order
    APPROVED         = auto()  # approval mined (await_receipt=True path)
    APPROVAL_SENT    = auto()  # approval broadcast; fill must use nonce_for_fill
    APPROVAL_PENDING = auto()  # another coroutine already sent an approval;
                               # fill must use pending_nonce + 1
    FAILED           = auto()  # unrecoverable error


@dataclass(frozen=True)
class CollateralResult:
    status:         CollateralStatus
    allowance_wei:  int
    required_wei:   int
    approval_tx:    Optional[str]  # tx hash of the approval that was sent/pending
    nonce_for_fill: Optional[int]  # caller MUST use this when status is APPROVAL_SENT
                                   # or APPROVAL_PENDING; None = use next pending nonce
    error:          Optional[str]


# ── In-flight approval guard ──────────────────────────────────────────────────

class _ApprovalGuard:
    """
    Serialises approval broadcasts for a single (owner, spender) pair.

    Problem it solves:
        asyncio.create_task fires two handlers concurrently. Both see
        allowance < required. Without a lock, both call get_transaction_count
        and get nonce N. Both broadcast approve(spender, X) at nonce N.
        The second tx replaces the first in the mempool (same nonce, higher
        fee wins) — or both fail — and the fill at nonce N+1 hits insufficient
        allowance either way.

    Solution:
        The first coroutine acquires the lock and broadcasts.  While it holds
        the lock it stores (tx_hash, nonce) in _pending.  The second coroutine
        acquires the lock after the first releases it, re-reads allowance
        (now reflects the in-flight or mined approval), and returns
        APPROVAL_PENDING with fill_nonce = pending_nonce + 1 — no second
        broadcast needed.
    """
    _lock:    asyncio.Lock
    _pending: Optional[tuple[str, int]]  # (tx_hash, nonce) while unmined

    def __init__(self) -> None:
        self._lock    = asyncio.Lock()
        self._pending = None

    @property
    def pending(self) -> Optional[tuple[str, int]]:
        return self._pending

    def set_pending(self, tx_hash: str, nonce: int) -> None:
        self._pending = (tx_hash, nonce)

    def clear_pending(self) -> None:
        self._pending = None

    def acquire(self):
        return self._lock.acquire()

    def release(self) -> None:
        self._lock.release()


# One guard per (owner, spender) pair — keyed at module level.
_guards: dict[tuple[str, str], _ApprovalGuard] = {}


def _get_guard(owner: str, spender: str) -> _ApprovalGuard:
    key = (owner.lower(), spender.lower())
    if key not in _guards:
        _guards[key] = _ApprovalGuard()
    return _guards[key]


# ── Low-level approve helper ──────────────────────────────────────────────────

async def _broadcast_approve(
    w3:             AsyncWeb3,
    token:          any,
    owner_addr:     str,
    spender_addr:   str,
    approve_amount: int,
    nonce:          int,
    tip_wei:        int,
    max_fee_wei:    int,
    private_key:    str,
) -> str:
    """Build, sign, and send a single approve() tx. Returns tx hash hex."""
    txn = await token.functions.approve(
        spender_addr, approve_amount
    ).build_transaction({
        "from":                 owner_addr,
        "nonce":                nonce,
        "maxPriorityFeePerGas": tip_wei,
        "maxFeePerGas":         max_fee_wei,
        "chainId":              await w3.eth.chain_id,
    })
    signed = w3.eth.account.sign_transaction(txn, private_key)
    tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


async def _approve_with_reset_guard(
    w3:             AsyncWeb3,
    token:          any,
    owner_addr:     str,
    spender_addr:   str,
    approve_amount: int,
    current_allowance: int,
    nonce:          int,
    tip_wei:        int,
    max_fee_wei:    int,
    private_key:    str,
) -> tuple[str, int]:
    """
    Approve approve_amount, handling the reset-to-zero pattern.

    Some tokens (OpenZeppelin ≤4.x, SNX-family) revert if you call
    approve(spender, X) while allowance > 0. Detect this from the revert
    string and insert approve(spender, 0) → approve(spender, X).

    Returns (tx_hash, final_nonce) — final_nonce is the nonce of the
    approve(amount) tx (nonce+1 if a reset was needed, nonce otherwise).
    """
    reset_needed = False

    if current_allowance > 0 and approve_amount != UINT256_MAX:
        # Speculatively detect by checking whether the token reverts on
        # a simulated approve without spending gas.
        try:
            result = await token.functions.approve(
                spender_addr, approve_amount
            ).call({"from": owner_addr})
            if result is False:
                reset_needed = True
        except Exception as exc:
            err = str(exc).lower()
            if any(p in err for p in _RESET_REQUIRED_PATTERNS):
                reset_needed = True

    if reset_needed:
        log.info(
            "approve reset-to-zero required | current=%d | sending approve(0) first",
            current_allowance,
        )
        await _broadcast_approve(
            w3, token, owner_addr, spender_addr,
            0, nonce, tip_wei, max_fee_wei, private_key,
        )
        # The fill will use nonce+2, so the guard caller must account for this.
        # We return the *second* tx (the real approval) and its nonce.
        final_nonce  = nonce + 1
        approve_hash = await _broadcast_approve(
            w3, token, owner_addr, spender_addr,
            approve_amount, final_nonce, tip_wei, max_fee_wei, private_key,
        )
        return approve_hash, final_nonce

    approve_hash = await _broadcast_approve(
        w3, token, owner_addr, spender_addr,
        approve_amount, nonce, tip_wei, max_fee_wei, private_key,
    )
    return approve_hash, nonce


# ── Core coroutine ────────────────────────────────────────────────────────────

async def check_and_approve_collateral(
    signed_order: dict,
    *,
    rpc_url:          str,
    owner:            str,
    collateral:       str   = PUSD_ADDRESS,
    spender:          str   = V2_EXCHANGE,
    priority_gwei:    int   = 100,
    approve_infinite: bool  = True,
    await_receipt:    bool  = True,
    receipt_timeout_s: float = 30.0,
) -> CollateralResult:
    """
    Check pUSD allowance and auto-approve if insufficient.

    Concurrent safety: if two coroutines enter simultaneously and both see
    insufficient allowance, only one broadcasts an approval. The second
    returns APPROVAL_PENDING with nonce_for_fill derived from the first
    approval's nonce — no duplicate broadcast, no nonce collision.

    Args:
        signed_order:      Must contain 'makerAmount' (wei int or str).
        rpc_url:           RPC endpoint — shares the singleton provider.
        owner:             EOA holding the collateral.
        collateral:        Token contract address.
        spender:           Address to approve (V2 Exchange).
        priority_gwei:     EIP-1559 maxPriorityFeePerGas (≥100 for Polygon).
        approve_infinite:  True  → approve UINT256_MAX (recommended; one-time cost).
                           False → approve exact makerAmount (re-approve each order).
        await_receipt:     True  → block until mined; fill uses normal nonce.
                           False → return immediately; fill MUST use nonce_for_fill.
        receipt_timeout_s: Max seconds to wait for mining confirmation.

    Private key:
        Read from TRADING_EOA_PRIVATE_KEY env var. Never passed as argument.
    """
    private_key = os.environ.get("TRADING_EOA_PRIVATE_KEY")
    if not private_key:
        raise EnvironmentError("TRADING_EOA_PRIVATE_KEY not set")

    w3           = _ProviderSingleton.get(rpc_url)
    owner_addr   = AsyncWeb3.to_checksum_address(owner)
    spender_addr = AsyncWeb3.to_checksum_address(spender)
    token_addr   = AsyncWeb3.to_checksum_address(collateral)
    token        = w3.eth.contract(address=token_addr, abi=_ERC20_ABI)
    required_wei = int(signed_order["makerAmount"])
    guard        = _get_guard(owner_addr, spender_addr)

    # ── 1. Fast path: read allowance without the lock ─────────────────────────
    try:
        current_allowance: int = await token.functions.allowance(
            owner_addr, spender_addr
        ).call()
    except Exception as exc:
        return CollateralResult(
            status=CollateralStatus.FAILED,
            allowance_wei=0, required_wei=required_wei,
            approval_tx=None, nonce_for_fill=None,
            error=f"allowance() call failed: {exc}",
        )

    if current_allowance >= required_wei:
        log.debug("collateral OK | allowance=%d required=%d", current_allowance, required_wei)
        return CollateralResult(
            status=CollateralStatus.SUFFICIENT,
            allowance_wei=current_allowance, required_wei=required_wei,
            approval_tx=None, nonce_for_fill=None, error=None,
        )

    # ── 2. Acquire the guard lock before touching nonces or broadcasting ───────
    await guard.acquire()
    try:
        # Re-read allowance inside the lock — a concurrent coroutine may have
        # already broadcast an approval that raised the allowance.
        try:
            current_allowance = await token.functions.allowance(
                owner_addr, spender_addr
            ).call()
        except Exception as exc:
            return CollateralResult(
                status=CollateralStatus.FAILED,
                allowance_wei=0, required_wei=required_wei,
                approval_tx=None, nonce_for_fill=None,
                error=f"allowance() re-check failed: {exc}",
            )

        if current_allowance >= required_wei:
            # A concurrent approval that was pending is now mined.
            guard.clear_pending()
            log.debug(
                "collateral OK after lock (concurrent approval landed) | allowance=%d",
                current_allowance,
            )
            return CollateralResult(
                status=CollateralStatus.SUFFICIENT,
                allowance_wei=current_allowance, required_wei=required_wei,
                approval_tx=None, nonce_for_fill=None, error=None,
            )

        # A prior broadcast is still in-flight (unmined).
        if guard.pending:
            pending_tx, pending_nonce = guard.pending
            fill_nonce = pending_nonce + 1
            log.info(
                "approval already in-flight | tx=%s | fill will use nonce=%d",
                pending_tx, fill_nonce,
            )
            return CollateralResult(
                status=CollateralStatus.APPROVAL_PENDING,
                allowance_wei=current_allowance, required_wei=required_wei,
                approval_tx=pending_tx, nonce_for_fill=fill_nonce, error=None,
            )

        # ── 3. No pending approval — we are the broadcaster ───────────────────
        log.warning(
            "collateral insufficient | allowance=%d required=%d | broadcasting approval",
            current_allowance, required_wei,
        )

        approve_amount = UINT256_MAX if approve_infinite else required_wei

        try:
            nonce       = await w3.eth.get_transaction_count(owner_addr, "pending")
            base_fee    = (await w3.eth.get_block("latest"))["baseFeePerGas"]
            tip_wei     = AsyncWeb3.to_wei(priority_gwei, "gwei")
            max_fee_wei = (2 * base_fee) + tip_wei

            tx_hash_hex, approve_nonce = await _approve_with_reset_guard(
                w3, token, owner_addr, spender_addr,
                approve_amount, current_allowance,
                nonce, tip_wei, max_fee_wei, private_key,
            )

            log.info(
                "approval broadcast | tx=%s | amount=%s | nonce=%d | tip=%d gwei",
                tx_hash_hex,
                "∞" if approve_infinite else str(approve_amount),
                approve_nonce, priority_gwei,
            )

            guard.set_pending(tx_hash_hex, approve_nonce)

        except Exception as exc:
            return CollateralResult(
                status=CollateralStatus.FAILED,
                allowance_wei=current_allowance, required_wei=required_wei,
                approval_tx=None, nonce_for_fill=None,
                error=f"approval broadcast failed: {exc}",
            )

    finally:
        guard.release()

    # ── 4a. Await receipt ─────────────────────────────────────────────────────
    if await_receipt:
        try:
            receipt: TxReceipt = await asyncio.wait_for(
                w3.eth.wait_for_transaction_receipt(tx_hash),
                timeout=receipt_timeout_s,
            )
        except asyncio.TimeoutError:
            return CollateralResult(
                status=CollateralStatus.FAILED,
                allowance_wei=current_allowance, required_wei=required_wei,
                approval_tx=tx_hash_hex, nonce_for_fill=None,
                error=f"approval not mined within {receipt_timeout_s}s",
            )

        if receipt["status"] != 1:
            guard.clear_pending()
            return CollateralResult(
                status=CollateralStatus.FAILED,
                allowance_wei=current_allowance, required_wei=required_wei,
                approval_tx=tx_hash_hex, nonce_for_fill=None,
                error="approval transaction reverted on-chain",
            )

        guard.clear_pending()
        log.info("approval mined | tx=%s | block=%d", tx_hash_hex, receipt["blockNumber"])
        return CollateralResult(
            status=CollateralStatus.APPROVED,
            allowance_wei=approve_amount, required_wei=required_wei,
            approval_tx=tx_hash_hex, nonce_for_fill=None, error=None,
        )

    # ── 4b. Fire-and-forget (nonce-chained) ───────────────────────────────────
    # guard.pending stays set until a subsequent check sees the mined allowance.
    return CollateralResult(
        status=CollateralStatus.APPROVAL_SENT,
        allowance_wei=current_allowance, required_wei=required_wei,
        approval_tx=tx_hash_hex,
        nonce_for_fill=approve_nonce + 1,
        error=None,
    )
