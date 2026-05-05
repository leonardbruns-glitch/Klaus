"""
Experimental V2 branch — Polymarket CLOB order listener + pre-flight guard + on-chain fill.

Environment variables required:
    POLYGON_RPC_URL   — Polygon HTTP RPC (add to .env — not in main bot's .env)
    FUNDER_ADDRESS    — EOA address (already in .env)
    PRIVATE_KEY       — signing key (already in .env, shared with main bot)
    CLOB_API_KEY      — Polymarket CLOB API key (add to .env)
    DRY_RUN           — already in .env; ensure it is "true" before first run

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

from tools.collateral import CollateralStatus, check_and_approve_collateral
from tools.preflight import Abort, V2_EXCHANGE, init_provider, pre_flight_check
from experimental_v2.strategy import StrategyLayer, SniperSignal

_COLLATERAL_NEEDS_NONCE = {CollateralStatus.APPROVAL_SENT, CollateralStatus.APPROVAL_PENDING}

# ── Configuration ─────────────────────────────────────────────────────────────

RPC_URL      = os.environ["POLYGON_RPC_URL"]        # add to .env
EOA_ADDRESS  = os.environ["FUNDER_ADDRESS"]          # already in .env
CLOB_API_KEY = os.environ.get("CLOB_API_KEY", "")   # add to .env

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


# ── Taker order builder ───────────────────────────────────────────────────────

def _build_clob_client():
    """
    Initialise py_clob_client for signing and submitting taker orders.
    Requires CLOB_API_SECRET and CLOB_API_PASSPHRASE in .env (not yet set).
    """
    from py_clob_client.client import ClobClient
    return ClobClient(
        host           = CLOB_REST_URL,
        key            = os.environ["PRIVATE_KEY"],
        chain_id       = 137,  # Polygon
        signature_type = int(os.environ.get("SIGNATURE_TYPE", "1")),
        funder         = EOA_ADDRESS,
    )


async def _build_taker_order(signal: SniperSignal) -> Optional[dict[str, Any]]:
    """
    Build a signed GTC limit order to take the signalled ask.
    Returns the signed order dict ready for POST /order, or None on failure.
    """
    try:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
        client      = _build_clob_client()
        order_args  = OrderArgs(
            price    = signal.price,
            size     = signal.size_usdc / signal.price,  # convert USDC → shares
            side     = BUY,
            token_id = signal.token_id,
        )
        signed = client.create_order(order_args)
        return signed
    except Exception as exc:
        log.error("order build failed | token=%s | %s", signal.token_id[:12], exc)
        return None


async def _submit_taker_order(signed_order: dict[str, Any]) -> Optional[str]:
    """POST signed order to CLOB REST API. Returns order_id or None."""
    try:
        from py_clob_client.clob_types import OrderType
        client   = _build_clob_client()
        response = client.post_order(signed_order, OrderType.GTC)
        return response.get("orderID") or response.get("id")
    except Exception as exc:
        log.error("order submit failed: %s", exc)
        return None


# ── Snipe executor ────────────────────────────────────────────────────────────

async def execute_snipe(signal: SniperSignal) -> None:
    """
    Full execution path for a sniper signal:
        1. Build signed taker order
        2. Collateral check (concurrent with order build)
        3. Pre-flight simulation
        4. Submit to CLOB REST API
    """
    log.info(
        "SNIPE EXECUTE | token=%s… | ask=%.4f | fair=%.4f | discount=%.2f%% | $%.2f",
        signal.token_id[:12], signal.price, signal.fair_price,
        signal.discount_pct * 100, signal.size_usdc,
    )

    # ── Build order and check collateral concurrently ─────────────────────────
    order_task      = asyncio.create_task(_build_taker_order(signal))
    collateral_task = asyncio.create_task(check_and_approve_collateral(
        {"makerAmount": str(int(signal.size_usdc * 1e6))},  # pUSD has 6 decimals
        rpc_url      = RPC_URL,
        owner        = EOA_ADDRESS,
        await_receipt = False,
    ))

    signed_order, collateral = await asyncio.gather(
        order_task, collateral_task, return_exceptions=True
    )

    if isinstance(signed_order, Exception) or signed_order is None:
        log.error("SNIPE ABORT — order build failed | token=%s…", signal.token_id[:12])
        return
    if isinstance(collateral, Exception) or collateral.status == CollateralStatus.FAILED:
        log.error("SNIPE ABORT — collateral failed | %s", getattr(collateral, "error", collateral))
        return

    # ── Pre-flight simulation ─────────────────────────────────────────────────
    preflight = await pre_flight_check(
        signed_order,
        rpc_url          = RPC_URL,
        fetch_token_id_map = fetch_token_id_map,
        sender           = EOA_ADDRESS,
    )

    if not preflight.go:
        log.warning(
            "SNIPE ABORT — preflight %s | %s | %.1fms",
            preflight.abort_reason.name, preflight.revert_msg, preflight.elapsed_ms,
        )
        return

    log.info(
        "SNIPE PREFLIGHT OK | gas=%s | collateral=%s | %.1fms",
        preflight.gas_estimate, collateral.status.name, preflight.elapsed_ms,
    )

    if DRY_RUN:
        log.info(
            "DRY_RUN — snipe suppressed | token=%s… | ask=%.4f | $%.2f",
            signal.token_id[:12], signal.price, signal.size_usdc,
        )
        return

    # ── Submit ────────────────────────────────────────────────────────────────
    order_id = await _submit_taker_order(signed_order)
    if order_id:
        log.info("SNIPE SUBMITTED | order_id=%s | token=%s… | ask=%.4f | $%.2f",
                 order_id, signal.token_id[:12], signal.price, signal.size_usdc)
    else:
        log.error("SNIPE SUBMIT FAILED | token=%s…", signal.token_id[:12])


# ── WebSocket listener ────────────────────────────────────────────────────────

async def _resolve_asset_ids(condition_ids: list[str]) -> list[str]:
    """
    Convert condition IDs → token asset IDs for the market channel subscription.
    Market channel takes asset_ids (token IDs), not condition IDs.
    """
    asset_ids = []
    async with aiohttp.ClientSession() as session:
        for cid in condition_ids:
            try:
                async with session.get(
                    f"{CLOB_REST_URL}/markets/{cid}",
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    for token in data.get("tokens", []):
                        tid = token.get("token_id")
                        if tid:
                            asset_ids.append(str(tid))
            except Exception as exc:
                log.warning("could not resolve token IDs for %s: %s", cid, exc)
    return asset_ids


async def _subscribe_payload(asset_ids: list[str]) -> str:
    """
    Market channel subscription. Type IS the channel name ("market").
    Uses asset_ids (token IDs), not condition IDs.
    Auth field uses "apiKey" — "key" causes immediate server close.
    """
    return json.dumps({
        "auth":      {"apiKey": CLOB_API_KEY},
        "type":      "market",
        "assets_ids": asset_ids,
    })


async def listen(condition_ids: list[str], strategy: StrategyLayer) -> None:
    """
    Connect to the CLOB market WebSocket and dispatch order_update events.
    Resolves condition IDs → asset token IDs before subscribing.
    Reconnects automatically on disconnect.
    """
    import ssl as _ssl
    try:
        import certifi as _certifi
        _ssl_ctx = _ssl.create_default_context(cafile=_certifi.where())
    except ImportError:
        _ssl_ctx = _ssl.create_default_context()

    asset_ids = await _resolve_asset_ids(condition_ids)
    if not asset_ids:
        log.error("no asset IDs resolved from condition IDs — cannot subscribe")
        return
    log.info("resolved %d asset IDs for subscription", len(asset_ids))

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    CLOB_WS_URL,
                    ssl=_ssl_ctx,
                    heartbeat=WS_PING_INTERVAL_S,
                    timeout=aiohttp.ClientTimeout(connect=10.0),
                ) as ws:
                    await ws.send_str(await _subscribe_payload(asset_ids))
                    log.info("WebSocket connected | assets=%d", len(asset_ids))

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            log.debug("RAW WS: %s", msg.data[:300])
                            try:
                                payload = json.loads(msg.data)
                            except json.JSONDecodeError:
                                continue

                            events = payload if isinstance(payload, list) else [payload]
                            for event in events:
                                # Initial book snapshot (list of per-token dicts with bids/asks)
                                if "bids" in event or "asks" in event:
                                    strategy.process_book_snapshot(event)
                                # Incremental price_changes updates
                                elif "price_changes" in event:
                                    for signal in strategy.process(event):
                                        asyncio.create_task(execute_snipe(signal))

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

    strategy = StrategyLayer()
    log.info("strategy layer ready | threshold=%.0f%% | max=$%.0f",
             strategy.snipe_threshold * 100, strategy.max_usdc)

    await listen(ids, strategy)


if __name__ == "__main__":
    # Pass market condition IDs as CLI args, e.g.:
    #   python3 experimental_v2/main.py 0xabc123 0xdef456
    ids = sys.argv[1:] or []
    if not ids:
        log.error("usage: python3 experimental_v2/main.py <market_id> [...]")
        sys.exit(1)

    asyncio.run(_main(ids))
