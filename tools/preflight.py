"""
Pre-flight check guard for signed orders against the V2 Exchange.
Runs simulation + local P&L concurrently within a 100ms budget.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Optional

from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

from tools.tx_simulator import SimResult, SIMULATE_TIMEOUT_S, _decode_revert_bytes

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

V2_EXCHANGE = "0xE111180000d2663C0091e4f400237545B87B996B"

# fillOrder(Order order, uint256 fillAmount, bytes sig) selector
FILL_ORDER_SELECTOR = "0x760a5cc0"


class Abort(Enum):
    NONE          = auto()
    REVERT        = auto()   # simulation returned a revert
    GHOST_ORDER   = auto()   # success but zero gas (Issue #338)
    TIMEOUT       = auto()   # RPC took > 100ms
    PNL_GATE      = auto()   # local P&L check failed
    TOKEN_MISSING = auto()   # token_id not in map


@dataclass(frozen=True)
class PreFlightResult:
    go:           bool
    abort_reason: Abort
    revert_msg:   Optional[str]
    gas_estimate: Optional[int]
    pnl_ok:       Optional[bool]
    elapsed_ms:   float
    token_id:     Optional[str] = None


# ── Shared provider (initialised once, reused across all checks) ─────────────

class _ProviderSingleton:
    """
    Holds a single AsyncWeb3 instance for the process lifetime.
    aiohttp reuses TCP connections across calls via its internal pool —
    no re-handshake overhead after the first request.
    """
    _w3: Optional[AsyncWeb3] = None

    @classmethod
    def get(cls, rpc_url: str) -> AsyncWeb3:
        if cls._w3 is None:
            cls._w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
            log.debug("Web3 provider initialised: %s", rpc_url)
        return cls._w3

    @classmethod
    def reset(cls) -> None:
        cls._w3 = None


def init_provider(rpc_url: str) -> None:
    """Call once at startup (or in a ProcessPoolExecutor initializer)."""
    _ProviderSingleton.get(rpc_url)


# ── Token resolution ─────────────────────────────────────────────────────────

async def _resolve_token_id(
    signed_order: dict[str, Any],
    fetch_token_id_map: Callable[[], Coroutine[Any, Any, dict[str, str]]],
) -> Optional[str]:
    token_map = await fetch_token_id_map()
    # signed_order must carry an 'asset_id' or 'condition_id' key
    key = signed_order.get("asset_id") or signed_order.get("condition_id")
    return token_map.get(key)


# ── Calldata builder ──────────────────────────────────────────────────────────

def _encode_fill_order(signed_order: dict[str, Any], token_id: str) -> str:
    """
    Minimal ABI encoding for fillOrder(order, fillAmount, sig).
    Replace with a full ABI encoder (eth_abi.encode) if your struct layout changes.
    """
    from eth_abi import encode

    order_tuple = (
        signed_order["maker"],
        signed_order["taker"],
        int(signed_order["makerAmount"]),
        int(signed_order["takerAmount"]),
        int(signed_order.get("expiration", 0)),
        int(signed_order.get("nonce", 0)),
        int(token_id),
        int(signed_order.get("feeRateBps", 0)),
        int(signed_order.get("side", 0)),
        int(signed_order.get("signatureType", 1)),  # POLY_PROXY = 1
    )
    fill_amount = int(signed_order.get("fillAmount", signed_order["makerAmount"]))
    sig_bytes   = bytes.fromhex(signed_order["signature"].lstrip("0x"))

    encoded = encode(
        ["(address,address,uint256,uint256,uint256,uint256,uint256,uint256,uint8,uint8)",
         "uint256",
         "bytes"],
        [order_tuple, fill_amount, sig_bytes],
    )
    return FILL_ORDER_SELECTOR + encoded.hex()


# ── Core guard ────────────────────────────────────────────────────────────────

async def pre_flight_check(
    signed_order: dict[str, Any],
    *,
    rpc_url: str,
    fetch_token_id_map: Callable[[], Coroutine[Any, Any, dict[str, str]]],
    pnl_check: Optional[Callable[[dict[str, Any]], Coroutine[Any, Any, bool]]] = None,
    sender: str = "0x0000000000000000000000000000000000000000",
    exchange: str = V2_EXCHANGE,
) -> PreFlightResult:
    """
    Run simulation + local P&L gate concurrently within SIMULATE_TIMEOUT_S.

    Args:
        signed_order:       Fully signed order dict (maker, sig, amounts, etc.)
        rpc_url:            RPC endpoint — provider is reused across calls.
        fetch_token_id_map: Async callable → {asset_id: token_id, ...}
        pnl_check:          Optional async callable → bool (True = P&L acceptable).
                            Runs concurrently with simulation; abort if False.
        sender:             msg.sender for eth_call (use EOA for realistic auth sim).
        exchange:           V2 Exchange contract address.

    Returns:
        PreFlightResult — check .go before submitting the order.
    """
    t0 = time.perf_counter()

    # ── 1. Resolve token_id ───────────────────────────────────────────────────
    token_id = await _resolve_token_id(signed_order, fetch_token_id_map)
    if token_id is None:
        return PreFlightResult(
            go=False, abort_reason=Abort.TOKEN_MISSING,
            revert_msg="token_id not found in map",
            gas_estimate=None, pnl_ok=None,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # ── 2. Encode calldata ────────────────────────────────────────────────────
    calldata = _encode_fill_order(signed_order, token_id)

    # ── 3. Build concurrent tasks ─────────────────────────────────────────────
    w3 = _ProviderSingleton.get(rpc_url)

    async def _simulate() -> SimResult:
        from tools.tx_simulator import simulate_transaction
        return await simulate_transaction(
            rpc_url=rpc_url,
            to=exchange,
            data=calldata,
            sender=sender,
        )

    tasks: list[Coroutine] = [_simulate()]
    if pnl_check is not None:
        tasks.append(pnl_check(signed_order))

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=SIMULATE_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        return PreFlightResult(
            go=False, abort_reason=Abort.TIMEOUT,
            revert_msg="RPC timeout",
            gas_estimate=None, pnl_ok=None,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            token_id=token_id,
        )

    sim_result: SimResult = results[0]
    pnl_ok: Optional[bool] = results[1] if pnl_check is not None else None

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # ── 4. P&L gate ───────────────────────────────────────────────────────────
    if pnl_ok is False:
        return PreFlightResult(
            go=False, abort_reason=Abort.PNL_GATE,
            revert_msg=None,
            gas_estimate=sim_result.gas_estimate if sim_result.success else None,
            pnl_ok=pnl_ok, elapsed_ms=elapsed_ms, token_id=token_id,
        )

    # ── 5. Revert gate ────────────────────────────────────────────────────────
    if not sim_result.success:
        log.warning(
            "pre_flight ABORT revert | token=%s | reason=%s | %.1fms",
            token_id, sim_result.revert_reason, elapsed_ms,
        )
        return PreFlightResult(
            go=False, abort_reason=Abort.REVERT,
            revert_msg=sim_result.revert_reason,
            gas_estimate=None, pnl_ok=pnl_ok,
            elapsed_ms=elapsed_ms, token_id=token_id,
        )

    # ── 6. Ghost-order filter (Issue #338) ────────────────────────────────────
    if sim_result.gas_estimate == 0:
        log.error(
            "pre_flight GHOST ORDER | token=%s | sig_type=%s | %.1fms — "
            "simulation succeeded with zero gas; order may not touch state. "
            "Possible V2 proxy auth mismatch (Issue #339).",
            token_id, signed_order.get("signatureType"), elapsed_ms,
        )
        return PreFlightResult(
            go=False, abort_reason=Abort.GHOST_ORDER,
            revert_msg="zero gas on success — ghost order detected",
            gas_estimate=0, pnl_ok=pnl_ok,
            elapsed_ms=elapsed_ms, token_id=token_id,
        )

    log.info(
        "pre_flight OK | token=%s | gas=%d | %.1fms",
        token_id, sim_result.gas_estimate, elapsed_ms,
    )
    return PreFlightResult(
        go=True, abort_reason=Abort.NONE,
        revert_msg=None,
        gas_estimate=sim_result.gas_estimate,
        pnl_ok=pnl_ok, elapsed_ms=elapsed_ms, token_id=token_id,
    )
