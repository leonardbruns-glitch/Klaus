"""
Experimental V2 branch — Polymarket CLOB order listener + pre-flight guard + on-chain fill.

Environment variables required:
    POLYGON_RPC_URL              — Polygon HTTP RPC (Alchemy / Infura / private node)
    TRADING_EOA_ADDRESS          — your EOA (0x...)
    TRADING_EOA_PRIVATE_KEY      — private key for signing fill + approval txs
    CLOB_API_KEY                 — Polymarket CLOB API key
    CLOB_API_SECRET              — Polymarket CLOB API secret
    CLOB_API_PASSPHRASE          — Polymarket CLOB API passphrase
    DRY_RUN                      — set to "true" to log without submitting (default: true)

Fill in CLOB_WS_URL and CLOB_REST_URL from the Polymarket CLOB API docs.
"""

import asyncio
import json
import logging
import logging.handlers
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp
from web3 import AsyncWeb3

from tools.collateral import (
    CollateralResult,
    CollateralStatus,
    check_and_approve_collateral,
)

# APPROVAL_PENDING means a concurrent coroutine already broadcast an approval;
# the fill must still use nonce_for_fill — same as APPROVAL_SENT.
_COLLATERAL_NEEDS_NONCE = {CollateralStatus.APPROVAL_SENT, CollateralStatus.APPROVAL_PENDING}
from tools.preflight import (
    Abort,
    PreFlightResult,
    V2_EXCHANGE,
    _ProviderSingleton,
    init_provider,
    pre_flight_check,
)

# ── Configuration ─────────────────────────────────────────────────────────────

RPC_URL      = os.environ["POLYGON_RPC_URL"]
EOA_ADDRESS  = os.environ["TRADING_EOA_ADDRESS"]
CLOB_API_KEY = os.environ.get("CLOB_API_KEY", "")

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

# Fill these from https://docs.polymarket.com — CLOB WebSocket + REST endpoints
CLOB_WS_URL   = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
CLOB_REST_URL = "https://clob.polymarket.com"

# Reconnect timing
WS_RECONNECT_DELAY_S = 5.0
WS_PING_INTERVAL_S   = 20.0


# ── Logging ───────────────────────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d UTC | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt.converter = time.gmtime

    file_handler = logging.handlers.RotatingFileHandler(
        "experimental_v2.log",
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    return logging.getLogger("experimental_v2")


log = _setup_logging()


# ── Token ID cache ────────────────────────────────────────────────────────────

_token_id_cache: dict[str, str] = {}
_token_cache_ts: float = 0.0
_TOKEN_CACHE_TTL_S = 300.0  # refresh every 5 minutes


async def fetch_token_id_map() -> dict[str, str]:
    """Fetch asset_id → token_id map from the CLOB markets endpoint with TTL cache."""
    global _token_id_cache, _token_cache_ts

    if _token_id_cache and (time.monotonic() - _token_cache_ts) < _TOKEN_CACHE_TTL_S:
        return _token_id_cache

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CLOB_REST_URL}/markets",
                headers={"Authorization": f"Bearer {CLOB_API_KEY}"},
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

        mapping: dict[str, str] = {}
        for market in data.get("data", []):
            for token in market.get("tokens", []):
                asset_id = token.get("asset_id") or market.get("condition_id")
                token_id = token.get("token_id")
                if asset_id and token_id:
                    mapping[asset_id] = token_id

        _token_id_cache = mapping
        _token_cache_ts = time.monotonic()
        log.debug("token map refreshed | %d entries", len(mapping))
        return mapping

    except Exception as exc:
        log.warning("token map fetch failed, using stale cache: %s", exc)
        return _token_id_cache


# ── P&L gate (stub — replace with your real check) ───────────────────────────

async def local_pnl_check(signed_order: dict[str, Any]) -> bool:
    """
    Return True if the order passes your local P&L / exposure rules.
    Runs concurrently with the simulation inside asyncio.gather.
    """
    maker_amount = int(signed_order.get("makerAmount", 0))
    return maker_amount > 0  # replace with real check


# ── On-chain fill submission ──────────────────────────────────────────────────

async def submit_fill_onchain(
    signed_order: dict[str, Any],
    token_id: str,
    explicit_nonce: Optional[int],
) -> str:
    """
    Encode and broadcast the fillOrder transaction directly to the V2 Exchange.
    Returns the tx hash.
    """
    from tools.preflight import _encode_fill_order, _ProviderSingleton, V2_EXCHANGE

    w3 = _ProviderSingleton.get(RPC_URL)
    private_key = os.environ["TRADING_EOA_PRIVATE_KEY"]
    owner_addr  = AsyncWeb3.to_checksum_address(EOA_ADDRESS)

    calldata   = _encode_fill_order(signed_order, token_id)
    base_fee   = (await w3.eth.get_block("latest"))["baseFeePerGas"]
    tip_wei    = AsyncWeb3.to_wei(100, "gwei")
    max_fee    = (2 * base_fee) + tip_wei

    nonce = explicit_nonce if explicit_nonce is not None else (
        await w3.eth.get_transaction_count(owner_addr, "pending")
    )

    tx = {
        "to":                  AsyncWeb3.to_checksum_address(V2_EXCHANGE),
        "from":                owner_addr,
        "data":                calldata,
        "value":               0,
        "nonce":               nonce,
        "maxPriorityFeePerGas": tip_wei,
        "maxFeePerGas":        max_fee,
        "chainId":             await w3.eth.chain_id,
    }
    tx["gas"] = await w3.eth.estimate_gas(tx)

    signed_txn = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash    = await w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    return tx_hash.hex()


# ── Order event handler ───────────────────────────────────────────────────────

async def handle_order_update(event: dict[str, Any]) -> None:
    """
    Process a single order_update event from the CLOB WebSocket.

    Expected event shape (adjust field names to match actual CLOB WS schema):
        {
            "type": "order_update",
            "order": {
                "maker":         "0x...",
                "taker":         "0x...",
                "makerAmount":   "1000000",
                "takerAmount":   "800000",
                "expiration":    "1234567890",
                "nonce":         "0",
                "asset_id":      "...",      # used for token_id resolution
                "feeRateBps":    "0",
                "side":          0,
                "signatureType": 1,          # POLY_PROXY
                "signature":     "0x..."
            }
        }
    """
    signed_order: dict[str, Any] = event.get("order", event)
    order_id = signed_order.get("id", "unknown")

    log.info("order_update received | id=%s | maker=%s", order_id, signed_order.get("maker"))

    # ── Run simulation, P&L gate, and collateral check concurrently ───────────
    try:
        preflight_coro = pre_flight_check(
            signed_order,
            rpc_url=RPC_URL,
            fetch_token_id_map=fetch_token_id_map,
            pnl_check=local_pnl_check,
            sender=EOA_ADDRESS,
        )
        collateral_coro = check_and_approve_collateral(
            signed_order,
            rpc_url=RPC_URL,
            owner=EOA_ADDRESS,
            await_receipt=False,  # nonce-chained; fill uses nonce_for_fill
        )

        preflight_result, collateral_result = await asyncio.gather(
            preflight_coro,
            collateral_coro,
            return_exceptions=True,
        )
    except Exception as exc:
        log.error("gather error | id=%s | %s", order_id, exc)
        return

    # ── Propagate any unexpected exceptions from gather ───────────────────────
    if isinstance(preflight_result, Exception):
        log.error("preflight raised | id=%s | %s", order_id, preflight_result)
        return
    if isinstance(collateral_result, Exception):
        log.error("collateral raised | id=%s | %s", order_id, collateral_result)
        return

    preflight: PreFlightResult    = preflight_result
    collateral: CollateralResult  = collateral_result

    # ── Preflight gates ───────────────────────────────────────────────────────
    if not preflight.go:
        if preflight.abort_reason == Abort.GHOST_ORDER:
            # Issue #338 — structured log for audit
            log.error(
                "GHOST_ORDER | id=%s | token=%s | gas=%s | sig_type=%s | %.1fms",
                order_id, preflight.token_id, preflight.gas_estimate,
                signed_order.get("signatureType"), preflight.elapsed_ms,
            )
        else:
            log.warning(
                "preflight ABORT | id=%s | reason=%s | msg=%s | %.1fms",
                order_id, preflight.abort_reason.name,
                preflight.revert_msg, preflight.elapsed_ms,
            )
        return

    if collateral.status == CollateralStatus.FAILED:
        log.error("collateral FAILED | id=%s | %s", order_id, collateral.error)
        return

    # ── Determine fill nonce ──────────────────────────────────────────────────
    # APPROVAL_SENT / APPROVAL_PENDING → use nonce_for_fill so the mempool
    # sequences approval → fill regardless of mining order.
    # SUFFICIENT / APPROVED → let eth_getTransactionCount decide.
    fill_nonce: Optional[int] = (
        collateral.nonce_for_fill
        if collateral.status in _COLLATERAL_NEEDS_NONCE
        else None
    )

    log.info(
        "pre-flight PASSED | id=%s | gas=%d | collateral=%s | nonce=%s | %.1fms",
        order_id, preflight.gas_estimate, collateral.status.name,
        fill_nonce, preflight.elapsed_ms,
    )

    # ── Submit ────────────────────────────────────────────────────────────────
    if DRY_RUN:
        log.info("DRY_RUN — fill suppressed | id=%s | nonce_would_be=%s", order_id, fill_nonce)
        return

    try:
        tx_hash = await submit_fill_onchain(
            signed_order,
            token_id=preflight.token_id,
            explicit_nonce=fill_nonce,
        )
        log.info("fill broadcast | id=%s | tx=%s", order_id, tx_hash)
    except Exception as exc:
        log.error("fill broadcast failed | id=%s | %s", order_id, exc)


# ── WebSocket listener ────────────────────────────────────────────────────────

async def _subscribe_payload(market_ids: list[str]) -> str:
    """Build the CLOB WS subscription message. Adjust to match actual API schema."""
    return json.dumps({
        "auth":    {"apiKey": CLOB_API_KEY},
        "type":    "subscribe",
        "channel": "market",
        "markets": market_ids,
    })


async def listen(market_ids: list[str]) -> None:
    """
    Connect to the CLOB WebSocket and dispatch order_update events.
    Reconnects automatically on disconnect.
    """
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    CLOB_WS_URL,
                    heartbeat=WS_PING_INTERVAL_S,
                    timeout=aiohttp.ClientTimeout(connect=10.0),
                ) as ws:
                    await ws.send_str(await _subscribe_payload(market_ids))
                    log.info("WebSocket connected | markets=%s", market_ids)

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                event = json.loads(msg.data)
                            except json.JSONDecodeError:
                                continue

                            if event.get("type") == "order_update":
                                # Fire-and-forget: don't await — keeps the WS loop hot
                                asyncio.create_task(handle_order_update(event))

                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            log.warning("WebSocket closed/error: %s", msg)
                            break

        except Exception as exc:
            log.error("WebSocket error: %s — reconnecting in %.0fs", exc, WS_RECONNECT_DELAY_S)

        await asyncio.sleep(WS_RECONNECT_DELAY_S)


# ── Entry point ───────────────────────────────────────────────────────────────

async def _main(market_ids: list[str]) -> None:
    log.info(
        "experimental_v2 starting | DRY_RUN=%s | eoa=%s | exchange=%s",
        DRY_RUN, EOA_ADDRESS, V2_EXCHANGE,
    )

    if DRY_RUN:
        log.warning("=" * 60)
        log.warning("DRY_RUN=true — no fills will be submitted")
        log.warning("Set DRY_RUN=false to enable live execution")
        log.warning("=" * 60)

    init_provider(RPC_URL)
    log.info("Web3 provider initialised")

    await fetch_token_id_map()
    log.info("token map primed")

    await listen(market_ids)


if __name__ == "__main__":
    # Pass market condition IDs as CLI args, e.g.:
    #   python3 experimental_v2/main.py 0xabc123 0xdef456
    ids = sys.argv[1:] or []
    if not ids:
        log.error("usage: python3 experimental_v2/main.py <market_id> [...]")
        sys.exit(1)

    asyncio.run(_main(ids))
