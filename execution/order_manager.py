"""
Klaus — Order Manager
Handles Polymarket CLOB order placement, cascade selling, fill tracking,
slippage measurement, and token approval.

Ported from baseline bot v4:
  - Token approval (update_balance_allowance) before every sell
  - Fill verification: only trust status=="matched" + takingAmount > 0
  - Limit entry with 5 % buffer capped at max_entry_price
  - Market order primary, limit order fallback in cascade (up to 15 attempts)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional
import logging

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2.clob_types import (
        MarketOrderArgs, OrderType, OrderArgs,
        BalanceAllowanceParams, AssetType,
        PartialCreateOrderOptions,
    )
    from py_clob_client_v2.order_builder.constants import BUY as CLOB_BUY, SELL as CLOB_SELL
    CLOB_CLIENT_AVAILABLE = True
except ImportError:
    CLOB_CLIENT_AVAILABLE = False

# ── Cloudflare bypass: curl_cffi Chrome TLS impersonation ─────────────────
# py_clob_client sets User-Agent: py_clob_client + httpx TLS fingerprint.
# Cloudflare correlates these as bot signals and blocks POST /order ~30-50%.
# curl_cffi impersonates Chrome's exact TLS cipher suite + extensions,
# eliminating the JA3 fingerprint signal. Used by OpenClaw ($7M Polymarket bot).
# Requires: pip install curl_cffi
# Docs: https://github.com/lexiforest/curl_cffi
try:
    import py_clob_client_v2.http_helpers.helpers as _clob_helpers
    from curl_cffi.requests import Session as _CffiSession

    class _ChromeTransport:
        """Drop-in replacement for py_clob_client's httpx transport.
        Emits Chrome TLS fingerprint to bypass Cloudflare JA3 detection."""
        _CHROME_UA = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        def __init__(self):
            self._sess = _CffiSession(impersonate="chrome")

        def request(self, method, url, headers=None, content=None, json=None, **kw):
            hdrs = dict(headers or {})
            hdrs["User-Agent"] = self._CHROME_UA
            return self._sess.request(
                method, url, headers=hdrs,
                data=content, json=json, **kw
            )

    _clob_helpers._http_client = _ChromeTransport()
    _CURL_CFFI_ACTIVE = True
except Exception as _cf_exc:
    _CURL_CFFI_ACTIVE = False
    _CURL_CFFI_ERR = str(_cf_exc)

from config import CONFIG
from strategy.momentum import Direction
from execution.fill_tracker import FillTracker

logger = logging.getLogger("execution")

if _CURL_CFFI_ACTIVE:
    logger.info("curl_cffi Chrome transport active — Cloudflare JA3 bypass enabled")
else:
    logger.debug("curl_cffi not available (%s) — using default httpx transport", _CURL_CFFI_ERR)

# Max entry price cap — mirrors old bot's 0.30 hard ceiling
MAX_ENTRY_PRICE = 0.30
TICK_SIZE = "0.01"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class OrderSide(Enum):
    BUY = auto()
    SELL = auto()


class OrderStatus(Enum):
    PENDING = auto()
    FILLED = auto()
    PARTIAL = auto()
    CANCELLED = auto()
    FAILED = auto()


@dataclass
class Fill:
    order_id: str
    token_id: str
    side: OrderSide
    price: float
    size: float
    fee: float
    ts: float = field(default_factory=time.time)
    slippage: float = 0.0


@dataclass
class OrderResult:
    status: OrderStatus
    fills: List[Fill] = field(default_factory=list)
    avg_fill_price: float = 0.0
    total_size: float = 0.0
    total_fee: float = 0.0
    slippage: float = 0.0
    error: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# CLOB client builder
# ---------------------------------------------------------------------------

def _build_clob_client() -> Optional[Any]:
    if not CLOB_CLIENT_AVAILABLE:
        logger.warning("py_clob_client not installed — stub mode")
        return None
    if not CONFIG.wallet_private_key:
        logger.warning("No wallet private key — stub mode")
        return None
    try:
        kwargs = dict(
            host=CONFIG.markets.clob_api_url,
            chain_id=137,
            key=CONFIG.wallet_private_key,
            signature_type=CONFIG.signature_type,
        )
        if CONFIG.funder_address:
            kwargs["funder"] = CONFIG.funder_address

        # Auth endpoints (/auth/api-key) don't need CF bypass — only POST /order does.
        # curl_cffi response is subtly incompatible with py_clob_client's httpx-based
        # PolyApiException, so we restore the stock httpx client during auth only.
        import httpx as _httpx
        import py_clob_client_v2.http_helpers.helpers as _h

        _orig_client = _h._http_client
        _h._http_client = _httpx.Client(http2=False, timeout=15.0)  # HTTP/1.1 for auth — HTTP/2 hangs on Python 3.14
        try:
            client = ClobClient(**kwargs)
            api_creds = client.create_or_derive_api_key()
        finally:
            _h._http_client = _orig_client  # restore curl_cffi for order posting

        client.set_api_creds(api_creds)
        logger.info("CLOB client authenticated (sig_type=%d)", CONFIG.signature_type)
        return client
    except Exception as exc:
        logger.error("CLOB client build failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Order Manager
# ---------------------------------------------------------------------------

class OrderManager:

    def __init__(self) -> None:
        self.cfg = CONFIG.execution
        self._client = _build_clob_client() if not CONFIG.dry_run else None
        self._session: Optional[aiohttp.ClientSession] = None
        self.fill_history: List[Fill] = []
        self._fill_tracker = FillTracker()
        self._setup_fill_tracker()
        # ── Order latency telemetry (VPS justification data) ─────────────────
        # Measures round-trip time from order submission to CLOB response.
        # High latency (>500ms) = network is the bottleneck.
        self._order_latencies_ms: List[float] = []  # all order RTTs this session

    def _setup_fill_tracker(self) -> None:
        """Extract API creds from the CLOB client and give them to FillTracker."""
        if self._client is None:
            return
        try:
            # After set_api_creds(), py_clob_client stores creds at client.creds
            creds = getattr(self._client, "creds", None)
            if creds and hasattr(creds, "api_key"):
                self._fill_tracker.set_creds(
                    api_key=creds.api_key,
                    api_secret=creds.api_secret,
                    api_passphrase=creds.api_passphrase,
                )
                logger.debug("FillTracker: creds loaded from CLOB client")
        except Exception as exc:
            logger.debug("FillTracker creds not available: %s", exc)

    async def start(self) -> None:
        if AIOHTTP_AVAILABLE:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        # Cancel any resting GTC orders left over from previous sessions.
        # Stale orders tie up USDC balance and trigger "not enough balance" errors.
        if self._client is not None:
            try:
                self._client.cancel_all()
                logger.info("Startup: cancelled all stale open orders")
            except Exception as exc:
                logger.debug("Startup cancel_all failed (may be none): %s", exc)
        await self._fill_tracker.start()

    def prewarm_token_caches(self, tokens: dict) -> None:
        """
        Pre-populate py_clob_client's internal neg_risk and fee_rate caches
        for all tracked tokens. Without this, the first order per token triggers
        GET /neg-risk and GET /fee-rate before the order is submitted (~2s each).
        Call this after token discovery and again every 250s before the 300s TTL expires.
        """
        if self._client is None:
            return
        for token_id, token_meta in tokens.items():
            try:
                self._client.get_neg_risk(token_id)
            except Exception:
                pass
            try:
                self._client.get_fee_rate_bps(token_id)
            except Exception:
                pass
        logger.info("prewarm_token_caches: populated neg_risk + fee_rate for %d tokens", len(tokens))

    async def stop(self) -> None:
        await self._fill_tracker.stop()
        if self._session:
            await self._session.close()

    # ── Limit buy with buffer ─────────────────────────────────────────────────

    async def limit_buy(
        self,
        token_id: str,
        intended_price: float,
        stake_usd: float,
        direction: Direction,
        neg_risk: bool = False,
        tick_size: str = TICK_SIZE,
    ) -> OrderResult:
        """
        Place a limit buy at price * (1 + buffer), hard-capped at MAX_ENTRY_PRICE.
        Ported from old bot: min(price * 1.05, 0.30).
        Verifies fill before returning (status==matched + takingAmount > 0).
        """
        if CONFIG.dry_run:
            return self._simulate_fill(token_id, intended_price, stake_usd, OrderSide.BUY)

        if stake_usd <= 0 or intended_price <= 0:
            return OrderResult(status=OrderStatus.FAILED, error="Invalid stake or price")

        # Both sides: cap at 0.99 ceiling. Risk manager already filters by max_entry_price
        # (0.27) before calling here; applying MAX_ENTRY_PRICE (0.30) here created ghost
        # orders at wrong prices for updown YES tokens trading at 0.50–0.92.
        price_ceil = 0.99
        limit_price = round(
            min(intended_price * (1 + self.cfg.entry_price_buffer), price_ceil), 4
        )
        size = round(stake_usd / limit_price, 2)

        # Refresh USDC allowance before buy — CLOB allowance depletes with each order
        # and must be reset or buys fail with "not enough balance / allowance".
        # Same pattern as _approve_token() for sells (AssetType.CONDITIONAL).
        try:
            self._client.update_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=CONFIG.signature_type,
                )
            )
        except Exception as _exc:
            logger.warning("USDC allowance refresh failed: %s", _exc)

        # Single attempt only for 5-min window entries.
        # Retrying a resting BUY wastes 3s × N attempts = up to 15s of a 240s window.
        # If the order doesn't fill in 3s, the price has moved — abort cleanly.
        try:
            result = await self._submit_limit_order(
                token_id, OrderSide.BUY, limit_price, size,
                neg_risk=neg_risk, tick_size=tick_size,
            )
            if result.status == OrderStatus.FILLED:
                return result
        except Exception as exc:
            err = str(exc)
            # curl errno 7 = CURLE_COULDNT_CONNECT (network unreachable / CLOB down)
            if "curl: (7)" in err or "Failed to connect" in err or "ConnectionError" in err:
                logger.warning(
                    "CLOB unreachable (network/geoblocking) — order skipped, will retry next cycle"
                )
                return OrderResult(status=OrderStatus.FAILED, error="network error — CLOB unreachable")
            else:
                logger.error("Limit buy failed: %s", exc)

        # Last-resort orphan guard: _submit_limit_order returned FAILED (WS timeout,
        # cancel race, CLOB read-replica lag). Extended to 4 shots (3s/5s/10s/20s):
        # 3s+5s confirmed insufficient — SOL fills appearing after 5s repeatedly.
        # asyncio.sleep is non-blocking so other coroutines run during waits.
        _cumulative = 0.0
        for _wait_s in (1.0, 2.0, 3.0):  # checks at 1s, 3s, 6s total — fast fail for terminal entries
            await asyncio.sleep(_wait_s)
            _cumulative += _wait_s
            _orphan_balance = self.fetch_token_balance(token_id)
            if _orphan_balance is not None and _orphan_balance >= 0.05:
                logger.warning(
                    "ORPHAN FILL RECOVERED in limit_buy @ %.0fs: _submit_limit_order returned "
                    "FAILED but CLOB balance=%.4f for %s — recovering @ estimated price=%.4f",
                    _cumulative, _orphan_balance, token_id[:12], limit_price,
                )
                _orphan_fill = Fill(
                    order_id="orphan-recovered",
                    token_id=token_id,
                    side=OrderSide.BUY,
                    price=limit_price,
                    size=_orphan_balance,
                    fee=0.0,
                )
                return OrderResult(
                    status=OrderStatus.FILLED,
                    fills=[_orphan_fill],
                    avg_fill_price=limit_price,
                    total_size=_orphan_balance,
                )
            logger.debug(
                "ORPHAN CHECK @%.0fs: balance=0 for %s — CLOB propagation still pending",
                _cumulative, token_id[:12],
            )

        return OrderResult(status=OrderStatus.FAILED, error="Entry not filled — price moved")

    # kept as alias for backward compatibility with main.py
    async def market_buy(
        self,
        token_id: str,
        intended_price: float,
        stake_usd: float,
        direction: Direction,
        neg_risk: bool = False,
        tick_size: str = TICK_SIZE,
    ) -> OrderResult:
        return await self.limit_buy(token_id, intended_price, stake_usd, direction,
                                    neg_risk=neg_risk, tick_size=tick_size)

    # ── Token approval ────────────────────────────────────────────────────────

    async def approve_token_for_sell(self, token_id: str) -> bool:
        """
        Calls update_balance_allowance before any sell.
        Critical for live trading — sells fail without this.
        Ported from baseline bot v4.

        Refreshes BOTH conditional token allowance AND USDC (collateral) allowance.
        With multiple concurrent positions, free USDC depletes and sell orders fail
        with "not enough balance / allowance" even though tokens are held.
        """
        if CONFIG.dry_run:
            return True
        if self._client is None:
            return False
        try:
            # Refresh conditional token allowance (the tokens being sold)
            self._client.update_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.CONDITIONAL,
                    token_id=token_id,
                )
            )
            # Refresh USDC allowance — required even for sells when free USDC is low
            # (concurrent positions lock USDC; CLOB needs a small reserve for fees)
            self._client.update_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=CONFIG.signature_type,
                )
            )
            await asyncio.sleep(1.0)  # approval propagation delay
            logger.debug("Token + USDC approved for sell: %s", token_id[:8])
            return True
        except Exception as exc:
            logger.error("Token approval failed %s: %s", token_id[:8], exc)
            return False

    # ── Cascade sell ─────────────────────────────────────────────────────────

    async def cascade_sell(
        self,
        token_id: str,
        total_shares: float,
        current_price: float,
        reason: str = "cascade",
        neg_risk: bool = False,
        tick_size: str = TICK_SIZE,
        force_exit: bool = False,
        allow_stepdown: bool = False,
    ) -> List[OrderResult]:
        """
        Exit in tranches: market order primary, limit order fallback.
        Up to 15 attempts per tranche (ported from baseline bot).
        Approves token before first attempt.
        force_exit=True bypasses the dust threshold — required for stop loss / hard exit
        so a declining position can always be closed regardless of remaining notional value.
        allow_stepdown=True: step sell price down 10% per retry (for reversal stops only).
        allow_stepdown=False (default): hold price — TP and TIME_EXIT should never sell
        at disaster prices due to USDC depletion or transient CLOB errors.
        """
        if total_shares <= 0:
            return []

        # NOTE: 0.99× factor removed. The SELL integer snap (floor-division) already
        # ensures we never request more shares than we own, making the 0.99× redundant.
        # "not enough balance" errors are now handled inline in the retry loop below.

        # Token approval before selling (critical for live)
        await self.approve_token_for_sell(token_id)

        n = self.cfg.cascade_levels
        # If each tranche at worst-case 80% of current price would be below $1.50
        # (the CLOB $1 minimum + 50% buffer), sell everything in one shot.
        # Root cause: 5-share CLOB minimum produces ~4.85-share positions. At
        # 33% cascade split = 1.62 shares, and any exit price below $0.93 puts
        # the tranche under $1.50. One single sell avoids tranching entirely.
        # force_exit: always single-shot since the whole position is already below threshold.
        tranche_est = total_shares / n
        worst_sell = max(current_price * 0.80, 0.01)
        if tranche_est * worst_sell < 1.50 or force_exit:
            n = 1
            logger.info(
                "Single-shot sell: %.4f shares (tranche would be $%.2f < $1.50 at 80%% discount)",
                total_shares, tranche_est * worst_sell,
            )

        results = []
        remaining = total_shares

        for i in range(n):
            is_last = (i == n - 1)
            tranche = remaining if is_last else round(total_shares * self.cfg.cascade_pct, 4)
            if tranche <= 0:
                break

            logger.info(
                "Cascade %d/%d: %.4f shares @ ~%.4f | %s",
                i + 1, n, tranche, current_price, reason,
            )

            result = await self._sell_tranche_with_fallback(
                token_id, tranche, current_price,
                neg_risk=neg_risk, tick_size=tick_size, force_exit=force_exit,
                allow_stepdown=allow_stepdown,
            )
            results.append(result)

            if result.status == OrderStatus.FILLED:
                remaining -= result.total_size
            else:
                logger.warning("Tranche %d/%d unfilled — aborting cascade", i + 1, n)
                break

            if not is_last:
                await asyncio.sleep(self.cfg.cascade_interval)

        return results

    async def _sell_tranche_with_fallback(
        self,
        token_id: str,
        shares: float,
        current_price: float,
        max_attempts: int = 15,
        neg_risk: bool = False,
        tick_size: str = TICK_SIZE,
        force_exit: bool = False,
        allow_stepdown: bool = False,
    ) -> OrderResult:
        """
        Market order first; limit order fallback with price stepping.
        Mirrors baseline bot's cascade loop.
        Tracks actual fill prices from each successful attempt and returns
        a weighted average — NOT the stale current_price snapshot.
        """
        if CONFIG.dry_run:
            return self._simulate_fill(
                token_id, current_price, shares * current_price, OrderSide.SELL
            )

        # Start at 5% discount (was 10%).
        # For profit-taking (not force_exit): 5% below mid ensures immediate fill vs resting orders.
        # For SL/hard exits (force_exit=True): start at 99% of current bid.
        #   OB data is ~100-300ms stale by the time the order reaches the CLOB.
        #   Starting at 100% means the bid may have moved 0.5-1% → order rests.
        #   1% below bid guarantees taker fill even with OB staleness, without
        #   meaningfully reducing exit price (BOND exit at 0.85 → 0.842 start,
        #   still well above entry; Polymarket may even fill at the full bid).
        sell_price = max(current_price * (0.99 if force_exit else 0.95), 0.01)
        orig_price = sell_price
        total_sold = 0.0
        # Track actual fill prices per attempt for accurate analytics
        fill_value = 0.0   # sum(price * size) across all attempts

        for attempt in range(max_attempts):
            if shares - total_sold < 0.01:
                break

            remaining = shares - total_sold

            # Skip dust: CLOB $1 minimum + 50% buffer = $1.50 threshold.
            # Consistent with cascade single-shot threshold so partial residuals
            # from snapping also settle cleanly at resolution.
            # force_exit=True bypasses this check — stop loss / hard exit must always
            # be able to close a position even when value has dropped below $1.50.
            if remaining * sell_price < 1.50 and not force_exit:
                logger.info(
                    "Dust skip: %.4f shares @ %.4f = $%.3f < $1.50 threshold — "
                    "flagging EXTERNALLY_SOLD so position closes cleanly",
                    remaining, sell_price, remaining * sell_price,
                )
                return OrderResult(
                    status=OrderStatus.FAILED,
                    error=f"EXTERNALLY_SOLD:balance={int(remaining * 1_000_000)}:price={sell_price:.4f}",
                )

            # Limit order sell. Market order (FOK SELL) removed: its amount
            # semantics differ from BUY (tokens vs USDC), causing under-sells.
            # Limit order at sell_price (starting at 95% of current) fills
            # immediately when marketable; steps down 10% each retry if resting.
            try:
                result = await self._submit_limit_order(
                    token_id, OrderSide.SELL, sell_price, remaining,
                    neg_risk=neg_risk, tick_size=tick_size,
                )
                if result.status == OrderStatus.FILLED and result.total_size > 0:
                    total_sold += result.total_size
                    fill_value += result.avg_fill_price * result.total_size
                    sell_price = orig_price
                    continue
                # _submit_limit_order catches exceptions internally and returns FAILED.
                # The except block below never fires for CLOB errors — check result.error.
                err = result.error or ""
                # SELL resting: bid moved below our limit after order submission.
                # allow_stepdown=False (TP/TIME_EXIT): break out immediately so Guard 1
                #   retries next OB scan with a fresh bid. Staying in the loop wastes
                #   45s (15 × 3s) stuck in _exit_in_progress while stepping toward a
                #   bad fill and potentially missing the fill confirmation (→ ep=xp).
                # allow_stepdown=True (reversal stops): keep stepping down 10% to force
                #   exit regardless of price — reversal means we MUST exit now.
                if "SELL resting on book" in err and not allow_stepdown:
                    logger.info(
                        "SELL resting %s — bid moved below %.4f, Guard 1 will retry "
                        "next scan with fresh OB price",
                        token_id[:12], sell_price,
                    )
                    break
                # Network-level failure: no point retrying immediately.
                if "curl: (7)" in err or "Failed to connect" in err or "Could not connect" in err:
                    logger.warning(
                        "SELL aborted: CLOB unreachable (network error) after %d attempt(s) — "
                        "position stays open, retrying next OB scan",
                        attempt + 1,
                    )
                    break
                # Orderbook gone (market resolved/expired) — 400 error, retrying is pointless.
                if "does not exist" in err or "orderbook" in err.lower() and "400" in err:
                    logger.warning(
                        "SELL aborted: orderbook %s no longer exists (market resolved/expired) — "
                        "treating as externally closed",
                        token_id[:12],
                    )
                    return OrderResult(
                        status=OrderStatus.FAILED,
                        error="ORDERBOOK_NOT_FOUND:resolved",
                    )
                # CLOB balance cache bug: CLOB cached balance is slightly below actual.
                # Parse the actual available balance from the error and retry exactly.
                # Error format: "not enough balance ... -> balance: XXXXXX, order amount: YYYYYY"
                # CLOB amounts are in micro-tokens (1 share = 1,000,000).
                if "not enough balance" in err.lower() or "not enough allowance" in err.lower():
                    import re as _re
                    _m = _re.search(r'balance[:\s]+(\d+)', err, _re.IGNORECASE)
                    if _m:
                        actual_ticks = int(_m.group(1))
                        actual_shares = round(actual_ticks / 1_000_000, 6)
                        # GHOST POSITION: balance=0 — but may be CLOB propagation delay.
                        # A fresh buy takes 3–10s to appear in CLOB balance. Retrying
                        # immediately after entry will show balance=0 even though tokens
                        # exist. Wait 3s and retry up to 3 times before declaring ghost.
                        if actual_ticks == 0:
                            if attempt < 3:
                                logger.warning(
                                    "GHOST suspect %s (attempt %d) — CLOB balance=0 "
                                    "(propagation delay or stale USDC cache), refreshing + retry",
                                    token_id[:12], attempt + 1,
                                )
                                try:
                                    from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
                                    self._client.update_balance_allowance(
                                        BalanceAllowanceParams(
                                            asset_type=AssetType.COLLATERAL,
                                            signature_type=CONFIG.signature_type))
                                except Exception:
                                    pass
                                await asyncio.sleep(3.0)
                                continue  # retry at same price
                            # CRITICAL: if some shares already sold before balance hit 0,
                            # preserve those fills — don't declare full GHOST and lose them.
                            if total_sold > 0:
                                logger.warning(
                                    "GHOST POSITION partial %s: CLOB balance=0 after %d checks "
                                    "but %.4f shares already sold — returning partial fill.",
                                    token_id[:12], attempt + 1, total_sold,
                                )
                                break  # fall through to FILLED path at line 672
                            logger.error(
                                "GHOST POSITION %s: CLOB balance=0 after %d checks — "
                                "tokens never received. Flagging for immediate position purge.",
                                token_id[:12], attempt + 1,
                            )
                            return OrderResult(
                                status=OrderStatus.FAILED,
                                error="GHOST_POSITION:balance=0",
                            )
                        if actual_shares < 0.05:
                            # Dust balance — position was sold externally (manual sell) or
                            # cascade partial-filled and leftover is sub-$1.50 dust.
                            # CRITICAL: if some shares already sold, preserve those fills.
                            if total_sold > 0:
                                logger.warning(
                                    "EXTERNALLY_SOLD dust %s: %.6f shares remain but %.4f already "
                                    "sold — returning partial fill, dust orphaned to residual tracker.",
                                    token_id[:12], actual_shares, total_sold,
                                )
                                break  # fall through to FILLED path
                            logger.warning(
                                "EXTERNALLY_SOLD %s: CLOB balance=%d micro-tokens (%.6f shares) "
                                "— dust remainder, treating as closed.",
                                token_id[:12], actual_ticks, actual_shares,
                            )
                            return OrderResult(
                                status=OrderStatus.FAILED,
                                error=f"EXTERNALLY_SOLD:balance={actual_ticks}",
                            )
                        if 0.01 <= actual_shares < remaining - 0.001:
                            logger.info(
                                "CLOB balance cache: adjusting sell %.4f → %.6f shares (cached lag)",
                                remaining, actual_shares,
                            )
                            shares = actual_shares
                            remaining = actual_shares
                            continue  # retry immediately with corrected size
                    # "not enough balance/allowance" — refresh USDC allowance inline.
                    # Price step-down is controlled by allow_stepdown flag (False for
                    # TP/TIME_EXIT, True for reversal stops).
                    logger.warning(
                        "SELL balance/allowance error %s (attempt %d) — "
                        "refreshing USDC allowance, retrying at price %.4f",
                        token_id[:12], attempt + 1, sell_price,
                    )
                    try:
                        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
                        self._client.update_balance_allowance(
                            BalanceAllowanceParams(
                                asset_type=AssetType.COLLATERAL,
                                signature_type=CONFIG.signature_type,
                            )
                        )
                    except Exception as _usdc_exc:
                        logger.debug("inline USDC refresh failed: %s", _usdc_exc)
            except Exception as _sell_exc:
                # Safety net for exceptions that escape _submit_limit_order (rare).
                err = str(_sell_exc)
                if "curl: (7)" in err or "Failed to connect" in err or "Could not connect" in err:
                    logger.warning(
                        "SELL aborted: CLOB unreachable (network error) after %d attempt(s)",
                        attempt + 1,
                    )
                    break
                logger.debug("Sell attempt %d error: %s", attempt + 1, _sell_exc)

            # Step price down 10% — only for reversal stops (allow_stepdown=True).
            # TP/TIME_EXIT: price held. "SELL resting" with allow_stepdown=False
            # already broke out of the loop above — this branch only runs when
            # the error was something other than resting (e.g. balance error retry).
            if allow_stepdown:
                sell_price = max(sell_price * 0.90, 0.01)
                logger.debug("Sell retry %d: %.4f @ %.4f (10%% stepdown)", attempt + 1, remaining, sell_price)
            else:
                logger.debug("Sell retry %d: %.4f @ %.4f (price held — no stepdown)", attempt + 1, remaining, sell_price)

        if total_sold > 0:
            # Actual weighted average fill price across all successful attempts.
            # Fall back to current_price ONLY if fill_value is 0 (e.g. market order
            # returns no avg_fill_price — should not happen in practice).
            actual_avg_price = fill_value / total_sold if fill_value > 0 else current_price
            if actual_avg_price != current_price:
                logger.debug(
                    "Cascade sell actual avg price %.4f (snapshot was %.4f, delta %.4f)",
                    actual_avg_price, current_price, actual_avg_price - current_price,
                )
            fill = Fill(
                order_id=f"cascade_{token_id[:6]}_{int(time.time())}",
                token_id=token_id,
                side=OrderSide.SELL,
                price=actual_avg_price,
                size=total_sold,
                fee=0.0,
            )
            return OrderResult(
                status=OrderStatus.FILLED,
                fills=[fill],
                avg_fill_price=actual_avg_price,
                total_size=total_sold,
            )
        return OrderResult(status=OrderStatus.FAILED, error="All cascade attempts failed")

    # ── CLOB order submission ─────────────────────────────────────────────────

    async def _submit_limit_order(
        self,
        token_id: str,
        side: OrderSide,
        price: float,
        size: float,
        neg_risk: bool = False,
        tick_size: str = TICK_SIZE,
    ) -> OrderResult:
        if self._client is None:
            return OrderResult(status=OrderStatus.FAILED, error="No CLOB client")
        try:
            clob_side = CLOB_BUY if side == OrderSide.BUY else CLOB_SELL
            # Snap price to valid tick — CLOB rejects prices not aligned to tick_size.
            # round(p / 0.01) * 0.01 handles this; simple round(..., 4) can produce
            # e.g. 0.2257 which is not a valid 0.01-tick price.
            try:
                tick_f = float(tick_size) if tick_size else 0.01
                snap_decimals = len(tick_size.rstrip('0').split('.')[-1]) if '.' in tick_size else 0
                price = round(round(price / tick_f) * tick_f, snap_decimals + 2)
            except Exception:
                pass  # best-effort; if snap fails the server will reject with a clear error

            # Integer arithmetic to satisfy CLOB constraints exactly (no floating-point rounding):
            #   maker_micro = price_cents × size_ticks  (both integers)
            #   maker_micro must be divisible by 10000 (GTC/FAK constraint)
            import math as _math
            price_cents = round(price * 100)
            if price_cents <= 0:
                return OrderResult(status=OrderStatus.FAILED, error="Price rounds to zero cents")
            step = 10000 // _math.gcd(price_cents, 10000)   # smallest valid size_ticks increment
            requested_ticks = round(size * 10000)

            if side == OrderSide.BUY:
                # BUY: snap UP — must meet 5-share min AND $1 maker min
                min_ticks = max(
                    _math.ceil(1_000_000 / price_cents),    # $1 minimum maker amount
                    50_000,                                   # 5-share minimum for resting buys
                )
                snapped_ticks = _math.ceil(max(requested_ticks, min_ticks) / step) * step
                maker_usd = (price_cents * snapped_ticks) / 1_000_000
                # Guard: skip if min compliant order exceeds 50% of bankroll.
                # 5-share min at high prices (e.g. $0.92 → $4.60 on $10 account) is too risky.
                max_allowed = CONFIG.bankroll.total * 0.50
                if maker_usd > max_allowed:
                    logger.info(
                        "SKIP %s — min order $%.2f exceeds 50%% of bankroll $%.2f (price=%.4f)",
                        token_id[:12], maker_usd, CONFIG.bankroll.total, price,
                    )
                    return OrderResult(
                        status=OrderStatus.FAILED,
                        error=f"Min order ${maker_usd:.2f} exceeds 50% of bankroll (5-share min at price {price:.4f})",
                    )
            else:
                # SELL: snap DOWN to nearest valid step — never oversell shares we own.
                # Marketable sells (price below bid) fill immediately; no 5-share resting minimum.
                snapped_ticks = max((requested_ticks // step) * step, step)

            size = snapped_ticks / 10000
            logger.debug(
                "Order snap: side=%s price=%.4f size=%.4f maker=$%.4f (step=%d ticks)",
                side.name, price, size, (price_cents * snapped_ticks) / 1_000_000, step,
            )

            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=clob_side,
            )
            # Always pass explicit tick_size and neg_risk — prevents py_clob_client
            # from making GET /tick-size and GET /neg-risk before every order.
            # tick_size "0.01" is valid; passing None triggers an unnecessary API call.
            # neg_risk: py_clob_client checks `is None`, so False is safe to pass.
            opts = PartialCreateOrderOptions(
                tick_size=tick_size or "0.01",
                neg_risk=neg_risk if neg_risk else None,
            )
            # GTC for all orders. FAK has an unsatisfiable integer maker-amount
            # constraint (maker_micro must be multiple of 10000) for any non-trivial
            # price. GTC limit orders have no such constraint and fill immediately
            # when our +5% buffer limit price crosses the best ask.
            order_type = OrderType.GTC

            # Cloudflare WAF blocks datacenter IPs on POST /order ~30-50% of the time.
            # CLOB also returns transient 5xx (e.g. 'could not run the execution') under
            # load. Retry both with exponential backoff; both are server-side and transient.
            # CRITICAL: create_order INSIDE the retry loop — reusing the same signed
            # order across retries triggers "order is invalid. Duplicated." from CLOB.
            resp = None
            _transient_exc = None
            _order_t0 = time.time()
            _attempted_order_ids: list = []   # track ALL order IDs placed this call
            for _cf_attempt in range(3):
                signed = self._client.create_order(order_args, options=opts)
                # Capture order ID from signed order BEFORE posting — the ID is
                # deterministic (hash of parameters + signature) and available even
                # if CF blocks the POST response. Used to cancel stale resting orders
                # from previous attempts after a successful fill is confirmed.
                _signed_id = (
                    signed.get("id", "") if isinstance(signed, dict)
                    else getattr(signed, "id", "")
                )
                if _signed_id:
                    _attempted_order_ids.append(_signed_id)
                try:
                    resp = self._client.post_order(signed, order_type)
                    _transient_exc = None
                except Exception as _post_exc:
                    # PolyApiException: status_code=500 with 'could not run the execution'
                    # is a transient CLOB execution-engine error — retry with backoff.
                    # Also catch 502/503/504 and timeouts. 4xx errors (invalid order,
                    # auth failure) are permanent and bubble up to the outer except.
                    _exc_str = str(_post_exc)
                    _is_5xx = any(f"status_code={c}" in _exc_str for c in (500, 502, 503, 504))
                    _is_exec_err = "could not run the execution" in _exc_str
                    _is_timeout = "timeout" in _exc_str.lower() or "timed out" in _exc_str.lower()
                    if _is_5xx or _is_exec_err or _is_timeout:
                        _transient_exc = _post_exc
                        resp = None
                    else:
                        raise
                err_str = str(resp) if resp else (str(_transient_exc) if _transient_exc else "")
                if resp and "cloudflare" not in err_str.lower() and "403" not in err_str:
                    break
                if _cf_attempt < 2:
                    wait = 0.5 * (2 ** _cf_attempt)  # 0.5s, 1s
                    _reason = "CLOB 5xx/exec error" if _transient_exc else "Cloudflare block"
                    logger.warning("%s on order POST (attempt %d) — retry in %.1fs: %s",
                                   _reason, _cf_attempt + 1, wait, err_str[:140])
                    await asyncio.sleep(wait)
                    # Before retrying, check if the previous attempt actually filled
                    # despite the error response. If the WS buffered a fill for this
                    # token, skip the retry — a second order would create double-fill orphans.
                    if self._fill_tracker and self._fill_tracker.is_connected:
                        _early = self._fill_tracker.pop_fill_for_token(token_id, side="BUY")
                        if _early is not None:
                            logger.warning(
                                "Retry cancelled — attempt %d already filled token %s",
                                _cf_attempt + 1, token_id[:12],
                            )
                            resp = {"status": "matched", "takingAmount": str(_early["size"]),
                                    "makingAmount": str(_early["cost"]),
                                    "id": _early["order_id"], "_from_early_fill": True}
                            _transient_exc = None
                            break
                    # Belt-and-suspenders: check CLOB directly for the previous attempt's
                    # order ID. Fill tracker only sees FILLED orders via WS — a resting
                    # order that landed silently on CLOB (5xx ambiguous case) would be
                    # missed here, leading to a duplicate order on retry. get_order
                    # covers that gap. If the order is on the book in ANY active state,
                    # skip the retry and let downstream logic handle the existing order.
                    if _signed_id:
                        try:
                            _prev_order = self._client.get_order(_signed_id)
                            _prev_status = (
                                (_prev_order.get("status") or "").lower()
                                if _prev_order else ""
                            )
                            # Active statuses = order alive on CLOB → reuse, do not retry.
                            # Terminal failure statuses (canceled/expired/failed/rejected)
                            # mean the order is dead and retry is safe.
                            if _prev_status in ("matched", "filled", "live", "open"):
                                logger.warning(
                                    "Retry cancelled — previous attempt %d on CLOB "
                                    "(status=%s): %s — reusing existing order",
                                    _cf_attempt + 1, _prev_status, _signed_id[:12],
                                )
                                resp = _prev_order
                                _transient_exc = None
                                break
                        except Exception as _gs_exc:
                            # get_order failure typically = order not found on CLOB
                            # (never ingested) → safe to retry with a fresh order.
                            logger.debug(
                                "pre-retry get_order check failed for %s (assuming "
                                "order not ingested, retry safe): %s",
                                _signed_id[:12], _gs_exc,
                            )
            _order_ms = (time.time() - _order_t0) * 1000
            self._order_latencies_ms.append(_order_ms)
            if _order_ms > 500:
                logger.warning("SLOW ORDER: %.0fms round-trip (cf_attempts=%d) — VPS may help",
                               _order_ms, _cf_attempt + 1)

            if not resp:
                _err_msg = (
                    f"CLOB transient error after 3 retries: {_transient_exc}"
                    if _transient_exc else "Empty response"
                )
                return OrderResult(status=OrderStatus.FAILED, error=_err_msg)

            # Fill verification: only trust matched orders with actual fill
            status = resp.get("status", "")
            taking = resp.get("takingAmount", "0")
            making = resp.get("makingAmount", "0")

            def _to_float(v) -> float:
                # Handles: "5.0000", "50000", "-3.5", "1.2e6", int, float.
                # The old isdigit() check rejected negatives and scientific notation.
                try:
                    result = float(v)
                    return result if result >= 0 else 0.0   # negative fill size = invalid
                except (TypeError, ValueError):
                    return 0.0

            taking_f = _to_float(taking)

            if status == "live":
                order_id = resp.get("id", resp.get("orderID", ""))

                if side == OrderSide.BUY and order_id:
                    # BUY resting: ask moved above our limit right after signing.
                    # A marketable limit (+5% buffer) fills in <500ms if liquidity exists.
                    # Wait max 3s — in a 5-min window wasting 10s per attempt burns
                    # 12% of the tradeable window (240s after no_trade_last_sec=60).
                    # PRIMARY: wait on user channel WS fill event (sub-100ms).
                    # FALLBACK: poll REST every 1s if WS not connected.
                    # Both paths timeout after 3s then cancel.
                    _FILL_TIMEOUT = 1.0  # reduced 3→1s: fast-moving tokens reprice in <2s; waiting 3s guarantees missing the fill window
                    logger.info(
                        "BUY order resting — awaiting fill via user WS (up to %.0fs): %s",
                        _FILL_TIMEOUT, order_id[:12],
                    )

                    fill_data = None
                    if self._fill_tracker.is_connected:
                        # Fast path: WS delivers fill event in ~50-200ms
                        fill_data = await self._fill_tracker.wait_fill(order_id, timeout=_FILL_TIMEOUT)
                    else:
                        # Slow path: poll REST at 1s intervals (WS down/reconnecting)
                        for _poll in range(int(_FILL_TIMEOUT)):
                            await asyncio.sleep(1.0)
                            try:
                                order_info = self._client.get_order(order_id)
                                if order_info.get("status") == "matched":
                                    sz = _to_float(order_info.get("takingAmount", "0"))
                                    if sz > 0:
                                        fill_data = {
                                            "size": sz,
                                            "price": price,
                                            "cost": _to_float(order_info.get("makingAmount", "0")) or sz * price,
                                            "order_id": order_id,
                                            "_rest_fallback": True,
                                        }
                                        logger.info(
                                            "BUY resting filled via REST poll after %ds: %s",
                                            _poll + 1, order_id[:12],
                                        )
                                        break
                            except Exception as _pe:
                                logger.debug("REST poll %d failed: %s", _poll, _pe)

                    if fill_data:
                        # Normalise WS/REST fill into REST response format for downstream
                        sz = fill_data.get("size", 0)
                        cost = fill_data.get("cost") or sz * price
                        resp = {
                            "id": order_id,
                            "status": "matched",
                            "takingAmount": str(sz),
                            "makingAmount": str(cost),
                        }
                        status = "matched"
                        taking = str(sz)
                        taking_f = float(sz)
                        making = str(cost)
                        logger.info(
                            "BUY fill confirmed: order %s size=%.4f price=~%.4f",
                            order_id[:12], sz, price,
                        )
                    else:
                        # WS timeout — check CLOB balance BEFORE cancelling.
                        # Fills can land on Polymarket while WS confirmation is dropped.
                        # Cancelling without checking leaves orphaned shares untracked.
                        _pre_cancel_balance = self.fetch_token_balance(token_id)
                        if _pre_cancel_balance is not None and _pre_cancel_balance >= 0.05:
                            # Tokens received — order filled even though WS didn't confirm.
                            # Recover the fill using the balance and limit price.
                            logger.info(
                                "BUY fill recovered via balance check: %s balance=%.4f @ ~%.4f",
                                order_id[:12], _pre_cancel_balance, price,
                            )
                            resp = {
                                "id": order_id, "status": "matched",
                                "takingAmount": str(_pre_cancel_balance),
                                "makingAmount": str(_pre_cancel_balance * price),
                            }
                            status = "matched"
                            taking = str(_pre_cancel_balance)
                            taking_f = _pre_cancel_balance
                            making = str(_pre_cancel_balance * price)
                        else:
                            cancel_race_fill = False
                            try:
                                self._client.cancel_orders([order_id])
                                logger.info("Cancelled unfilled resting BUY %s", order_id[:12])
                            except Exception as _cancel_err:
                                # Cancel can fail when the order filled in the <1ms window
                                # between our 3s timeout check and the cancel request arriving
                                # at the CLOB. Silently swallowing this leaves a filled position
                                # on Polymarket that the bot doesn't know about.
                                # Recover: check order status and extract the fill if matched.
                                logger.warning(
                                    "BUY cancel failed for %s (%s) — checking for race fill",
                                    order_id[:12], _cancel_err,
                                )
                                try:
                                    await asyncio.sleep(0.3)  # wait for fill to propagate to read replica
                                    order_info = self._client.get_order(order_id)
                                    if order_info.get("status") == "matched":
                                        sz = _to_float(order_info.get("takingAmount", "0"))
                                        if sz > 0:
                                            resp = {
                                                "id": order_id, "status": "matched",
                                                "takingAmount": str(sz),
                                                "makingAmount": str(sz * price),
                                            }
                                            status = "matched"
                                            taking = str(sz)
                                            taking_f = sz
                                            cancel_race_fill = True
                                            logger.info(
                                                "BUY cancel-race fill recovered: %s size=%.4f @ ~%.4f",
                                                order_id[:12], sz, price,
                                            )
                                except Exception as _check_err:
                                    logger.debug("cancel-race order check failed: %s", _check_err)
                            if not cancel_race_fill:
                                # CLOB silently ignores cancel on already-matched orders.
                                # Wait 3s and recheck balance — fill may have landed between
                                # the pre-cancel balance check and the cancel arriving at CLOB.
                                await asyncio.sleep(3.0)
                                _post_cancel_balance = self.fetch_token_balance(token_id)
                                if _post_cancel_balance is not None and _post_cancel_balance >= 0.05:
                                    logger.warning(
                                        "BUY post-cancel recovery %s: %.4f shares found after 3s "
                                        "— fill landed during WS miss window, cancel was no-op",
                                        order_id[:12], _post_cancel_balance,
                                    )
                                    return OrderResult(
                                        status=OrderStatus.FILLED,
                                        avg_fill_price=price,
                                        total_size=_post_cancel_balance,
                                    )
                                return OrderResult(
                                    status=OrderStatus.FAILED,
                                    error=f"BUY resting — cancelled after {_FILL_TIMEOUT:.0f}s (no fill)",
                                )
                        # cancel_race_fill=True or balance-recovery=True: fall through to fill processing below
                else:
                    # SELL partially filled: POST response may carry a partial taker fill
                    # in takingAmount even when status="live" (remainder resting on book).
                    # Record the partial fill, cancel the resting remainder, and return
                    # FILLED so cascade accounts for the shares already sold.
                    # Without this, bot state diverges: Polymarket shows fewer tokens
                    # than open_positions.remaining_shares → oversell attempt on next cycle.
                    if taking_f > 0:
                        logger.info(
                            "SELL partial fill: %.4f shares @ ~%.4f — cancelling resting remainder",
                            taking_f, price,
                        )
                        if order_id:
                            try:
                                self._client.cancel_orders([order_id])
                            except Exception:
                                pass
                        partial_fill = Fill(
                            order_id=order_id or "",
                            token_id=token_id,
                            side=OrderSide.SELL,
                            price=price,
                            size=taking_f,
                            fee=0.0,
                        )
                        return OrderResult(
                            status=OrderStatus.FILLED,
                            fills=[partial_fill],
                            avg_fill_price=price,
                            total_size=taking_f,
                        )
                    # No fill at all: wait briefly for fill before cancelling.
                    # At T-10s BOND exits the book is thin — sell orders go "live"
                    # instead of matching immediately. Waiting 2s lets a buyer appear
                    # rather than cancelling + retrying which creates cancel-race GHOST.
                    _resting_fill = None
                    if order_id and self._fill_tracker and self._fill_tracker.is_connected:
                        _resting_fill = await self._fill_tracker.wait_fill(order_id, timeout=2.0)
                    if _resting_fill is not None:
                        fill_sz   = _resting_fill.get("size", 0)
                        fill_cost = _resting_fill.get("cost") or (fill_sz * price)
                        fill_pr   = fill_cost / fill_sz if fill_sz > 0 else price
                        logger.info(
                            "SELL resting-wait fill: %s size=%.4f @ %.4f (WS confirmed after 2s)",
                            order_id[:12], fill_sz, fill_pr,
                        )
                        partial_fill = Fill(
                            order_id=order_id, token_id=token_id,
                            side=OrderSide.SELL, price=fill_pr, size=fill_sz, fee=0.0,
                        )
                        return OrderResult(
                            status=OrderStatus.FILLED, fills=[partial_fill],
                            avg_fill_price=fill_pr, total_size=fill_sz,
                        )
                    # Still no fill — cancel and let cascade retry.
                    if order_id:
                        try:
                            self._client.cancel_orders([order_id])
                            logger.info("Cancelled resting GTC SELL %s", order_id[:12])
                            # ── Post-cancel fill recovery ──────────────────────────────
                            # Polymarket cancel is IDEMPOTENT: cancelling an already-filled
                            # order returns SUCCESS (no exception). The cancel-exception path
                            # below never fires for fills that completed just before cancel.
                            # Check fill_tracker buffer AND REST to avoid logging ep=xp.
                            if self._fill_tracker and self._fill_tracker.is_connected:
                                _post_cancel = self._fill_tracker.pop_fill_for_token(token_id, side="SELL")
                                if _post_cancel is not None:
                                    _pc_sz   = _post_cancel.get("size", 0)
                                    _pc_cost = _post_cancel.get("cost") or (_pc_sz * price)
                                    _pc_pr   = _pc_cost / _pc_sz if _pc_sz > 0 else price
                                    logger.info(
                                        "Post-cancel fill recovered (WS buffer): %s "
                                        "size=%.4f @ %.4f (fill arrived after 2s timeout, "
                                        "cancel was no-op on Polymarket)",
                                        order_id[:12], _pc_sz, _pc_pr,
                                    )
                                    partial_fill = Fill(
                                        order_id=order_id, token_id=token_id,
                                        side=OrderSide.SELL, price=_pc_pr,
                                        size=_pc_sz, fee=0.0,
                                    )
                                    return OrderResult(
                                        status=OrderStatus.FILLED, fills=[partial_fill],
                                        avg_fill_price=_pc_pr, total_size=_pc_sz,
                                    )
                            # REST fallback: WS disconnected or fill not in buffer yet
                            try:
                                await asyncio.sleep(0.5)
                                _oi = self._client.get_order(order_id)
                                _oi_st = (_oi.get("status") or "").lower()
                                if _oi_st in ("matched", "filled"):
                                    _mk = _to_float(_oi.get("makingAmount", "0"))
                                    _tk = _to_float(_oi.get("takingAmount", "0"))
                                    # SELL: makingAmount=tokens given, takingAmount=USDC received
                                    _sz = _mk if _mk > 0 else _tk
                                    _pr = _tk / _sz if _sz > 0 else price
                                    if _sz > 0:
                                        logger.info(
                                            "Post-cancel fill recovered (REST): %s "
                                            "size=%.4f @ %.4f",
                                            order_id[:12], _sz, _pr,
                                        )
                                        partial_fill = Fill(
                                            order_id=order_id, token_id=token_id,
                                            side=OrderSide.SELL, price=_pr,
                                            size=_sz, fee=0.0,
                                        )
                                        return OrderResult(
                                            status=OrderStatus.FILLED, fills=[partial_fill],
                                            avg_fill_price=_pr, total_size=_sz,
                                        )
                            except Exception:
                                pass
                        except Exception as _cancel_err:
                            # Cancel failed = order filled in the cancel-race window.
                            # Recover via fill_tracker or order status to avoid GHOST.
                            logger.warning(
                                "SELL cancel-race %s (%s) — recovering fill",
                                order_id[:12], _cancel_err,
                            )
                            # REST is authoritative — check this order_id directly.
                            # pop_fill_for_token searches by token_id and can find stale
                            # BUY fills from earlier trades, giving exit_price = entry_price.
                            try:
                                await asyncio.sleep(0.3)
                                _oi = self._client.get_order(order_id)
                                if _oi.get("status") == "matched":
                                    _mk = _to_float(_oi.get("makingAmount", "0"))
                                    _tk = _to_float(_oi.get("takingAmount", "0"))
                                    # SELL: makingAmount=tokens given, takingAmount=USDC received
                                    _sz = _mk if _mk > 0 else _tk
                                    _pr = _tk / _sz if _sz > 0 else price
                                    partial_fill = Fill(
                                        order_id=order_id, token_id=token_id,
                                        side=OrderSide.SELL, price=_pr, size=_sz, fee=0.0,
                                    )
                                    return OrderResult(
                                        status=OrderStatus.FILLED, fills=[partial_fill],
                                        avg_fill_price=_pr, total_size=_sz,
                                    )
                            except Exception:
                                pass
                            # WS buffer fallback (only if REST unavailable)
                            if self._fill_tracker and self._fill_tracker.is_connected:
                                _race = self._fill_tracker.pop_fill_for_token(token_id, side="SELL")
                                if _race is not None:
                                    r_sz   = _race.get("size", 0)
                                    r_cost = _race.get("cost") or (r_sz * price)
                                    r_pr   = r_cost / r_sz if r_sz > 0 else price
                                    partial_fill = Fill(
                                        order_id=order_id, token_id=token_id,
                                        side=OrderSide.SELL, price=r_pr, size=r_sz, fee=0.0,
                                    )
                                    return OrderResult(
                                        status=OrderStatus.FILLED, fills=[partial_fill],
                                        avg_fill_price=r_pr, total_size=r_sz,
                                    )
                    return OrderResult(status=OrderStatus.FAILED, error="SELL resting on book (live)")

            if status != "matched" or taking_f <= 0:
                logger.info(
                    "Order not filled (status=%s takingAmount=%s) — skipping",
                    status, taking,
                )
                return OrderResult(status=OrderStatus.FAILED, error=f"Unfilled: {status}")

            # ── Fill price calculation (BUY vs SELL semantics differ) ────────
            # Polymarket CLOB API returns makingAmount and takingAmount in WHOLE units.
            # BUY:  makingAmount = USDC paid,   takingAmount = tokens received
            # SELL: makingAmount = tokens given, takingAmount = USDC received
            # T00193 note: a prior fix added /1_000_000 (assuming micro-units) which
            # was wrong — the API returns whole units, giving fill_price ≈ 520000.
            making_f = _to_float(making)  # whole units — do NOT divide by 1_000_000
            if side == OrderSide.SELL:
                # SELL: makingAmount = tokens given, takingAmount = USDC received
                fill_size = making_f if making_f > 0 else taking_f  # tokens
                fill_price = taking_f / fill_size if fill_size > 0 else price  # USDC/token
            else:
                # BUY: takingAmount = tokens received, makingAmount = USDC paid
                fill_size = taking_f  # tokens
                fill_price = making_f / fill_size if fill_size > 0 else price  # USDC/token

            # ── Unit sanity check ───────────────────────────────────────────
            # Binary market prices must be in [0.01, 0.99].
            # After the BUY/SELL fix above this should rarely fire — but keep as safety net.
            if not (0.01 <= fill_price <= 0.99):
                logger.warning(
                    "Fill price %.6f outside valid range [0.01,0.99] — "
                    "raw taking=%s making=%s price=%.4f; falling back to limit price",
                    fill_price, taking, making, price,
                )
                fill_price = price
                fill_size = making_f if (side == OrderSide.SELL and making_f > 0) else (
                    taking_f if taking_f > 0 else size
                )
                if not (0.01 <= fill_price <= 0.99) or fill_size <= 0:
                    logger.error(
                        "Cannot recover fill price for order — aborting fill acceptance"
                    )
                    return OrderResult(
                        status=OrderStatus.FAILED,
                        error=f"Unrecoverable fill price {fill_price:.6f} (raw: taking={taking} making={making})",
                    )

            slippage = abs(fill_price - price)

            # ── Actual fill reconciliation ──────────────────────────────────
            # GET /data/trades?id=<order_id> returns actual fill price and fee.
            # No CF blocking on GET. Worth 150-300ms for accurate analytics.
            # If it fails, fall back to the values above (unchanged behaviour).
            #
            # IMPORTANT: wait 400ms before querying. The CLOB REST /data/trades
            # API has a propagation lag — calling immediately after "matched"
            # returns an empty list, causing us to record fee=0 and fall back to
            # the config estimate. 400ms covers the observed ~100-300ms lag.
            actual_fee = 0.0
            order_id_str = resp.get("id", resp.get("orderID", ""))
            if order_id_str:
                await asyncio.sleep(0.4)
                actual = self.fetch_order_fills(order_id_str)
                if not (actual and actual["total_size"] > 0):
                    # Propagation lag can exceed 400ms on busy blocks — retry once after 600ms.
                    # Without this, SELL exit_price falls back to limit-order price (decision-time),
                    # not actual fill price. T00193: logged $0.60 but actually filled at $0.66.
                    await asyncio.sleep(0.6)
                    actual = self.fetch_order_fills(order_id_str)
                    if not (actual and actual["total_size"] > 0):
                        logger.warning(
                            "fetch_order_fills %s: no data after 2 attempts (1.0s total) — "
                            "using POST-response fill price %.4f; may be inaccurate for SELL",
                            order_id_str[:12], fill_price,
                        )
                if actual and actual["total_size"] > 0:
                    reconciled_price = actual["avg_price"]
                    if 0.01 <= reconciled_price <= 0.99:
                        fill_price = reconciled_price
                        fill_size = actual["total_size"]
                        slippage = abs(fill_price - price)
                    actual_fee = actual["total_fee_usd"]
                    logger.debug(
                        "Fill reconciled from CLOB: price=%.4f size=%.4f fee=$%.5f (%g bps)",
                        fill_price, fill_size, actual_fee, actual.get("fee_rate_bps", 0),
                    )

            # ── Cancel stale resting orders from CF retry attempts ──────────────
            # If previous CF-retry attempts submitted orders that got through to
            # CLOB despite returning 403 to us, those orders rest on the book and
            # fill later as the market moves — creating double-fill orphans 60-200s
            # after the position opens. Cancel all tracked order IDs except the one
            # that just filled. Fire-and-forget: cancel failures are non-critical
            # (order may already be cancelled/filled, or CLOB may return "not found").
            _winning_id = order_id_str
            for _stale_id in _attempted_order_ids:
                if _stale_id and _stale_id != _winning_id:
                    try:
                        self._client.cancel_orders([_stale_id])
                        logger.warning(
                            "CF_STALE_CANCEL: cancelled resting order %s "
                            "(previous attempt for token %s — double-fill prevention)",
                            _stale_id[:12], token_id[:12],
                        )
                    except Exception as _cancel_exc:
                        logger.debug(
                            "CF_STALE_CANCEL failed for %s (may already be gone): %s",
                            _stale_id[:12], _cancel_exc,
                        )

            fill = Fill(
                order_id=order_id_str,
                token_id=token_id,
                side=side,
                price=fill_price,
                size=fill_size,
                fee=actual_fee,     # actual fee from CLOB (not hardcoded 0.0)
                slippage=slippage,
            )
            self.fill_history.append(fill)
            return OrderResult(
                status=OrderStatus.FILLED,
                fills=[fill],
                avg_fill_price=fill_price,
                total_size=fill_size,
                total_fee=actual_fee,
                slippage=slippage,
                raw=resp,
            )
        except Exception as exc:
            logger.error("Limit order error: %s", exc)
            return OrderResult(status=OrderStatus.FAILED, error=str(exc))

    async def _submit_market_order(
        self,
        token_id: str,
        side: OrderSide,
        usdc_amount: float,
        intended_price: float,
    ) -> OrderResult:
        if self._client is None:
            return OrderResult(status=OrderStatus.FAILED, error="No CLOB client")
        try:
            clob_side = CLOB_BUY if side == OrderSide.BUY else CLOB_SELL
            mo = MarketOrderArgs(
                token_id=token_id,
                amount=usdc_amount,
                side=clob_side,
            )
            signed = self._client.create_market_order(mo)
            resp = self._client.post_order(signed, OrderType.FOK)

            if not resp:
                return OrderResult(status=OrderStatus.FAILED, error="Empty response")

            fill_price = float(resp.get("average_price", intended_price))
            if fill_price <= 0:
                logger.error(
                    "Market order returned invalid fill_price=%.6f (order_id=%s) — treating as failed",
                    fill_price, resp.get("order_id", "?"),
                )
                return OrderResult(status=OrderStatus.FAILED, error=f"Invalid fill_price: {fill_price}")
            usdc_matched = float(resp.get("size_matched", usdc_amount))
            fill_size = usdc_matched / fill_price if fill_price > 0 else 0
            fee = float(resp.get("fee", 0))
            slippage = abs(fill_price - intended_price)

            fill = Fill(
                order_id=resp.get("order_id", ""),
                token_id=token_id,
                side=side,
                price=fill_price,
                size=fill_size,
                fee=fee,
                slippage=slippage,
            )
            self.fill_history.append(fill)
            return OrderResult(
                status=OrderStatus.FILLED,
                fills=[fill],
                avg_fill_price=fill_price,
                total_size=fill_size,
                total_fee=fee,
                slippage=slippage,
                raw=resp,
            )
        except Exception as exc:
            logger.error("Market order error: %s", exc)
            return OrderResult(status=OrderStatus.FAILED, error=str(exc))

    async def _submit_market_order_sell(
        self, token_id: str, usdc_amount: float
    ) -> OrderResult:
        return await self._submit_market_order(
            token_id, OrderSide.SELL, usdc_amount, 0.0
        )

    def latency_stats(self) -> dict:
        """Return order placement latency stats for session report."""
        lats = self._order_latencies_ms
        if not lats:
            return {"n": 0, "avg_ms": 0, "max_ms": 0, "slow_pct": 0}
        slow = sum(1 for l in lats if l > 500)
        return {
            "n": len(lats),
            "avg_ms": round(sum(lats) / len(lats), 1),
            "max_ms": round(max(lats), 1),
            "slow_pct": round(slow / len(lats) * 100, 1),  # % of orders taking >500ms
        }

    # ── Polymarket data reconciliation (GET endpoints — no CF blocking) ──────

    def fetch_token_balance(self, token_id: str) -> Optional[float]:
        """
        Fetch actual token (share) balance from Polymarket CLOB.
        Uses GET /balance-allowance?asset_type=CONDITIONAL&token_id=...
        Returns shares held (None on failure).

        Called after cascade_sell returns 0 fills to reconcile against reality.
        Catches the case where fills landed on Polymarket but WS confirmation
        was dropped — bot retries with stale quantity, CLOB rejects due to
        insufficient balance, shares remain unsold at window resolution.
        """
        if self._client is None or CONFIG.dry_run:
            return None
        try:
            ba = self._client.get_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.CONDITIONAL,
                    token_id=token_id,
                    signature_type=CONFIG.signature_type,
                )
            )
            raw = float(ba.get("balance", 0))
            shares = raw / 1_000_000
            return shares
        except Exception as exc:
            logger.warning("fetch_token_balance %s failed: %s", token_id[:8], exc)
            return None

    def fetch_recent_token_sells(
        self, token_id: str, since_ts: float
    ) -> list:
        """
        Query CLOB /trades for recent fills on token_id since since_ts.
        Returns list of (price, size) tuples.

        Called when cascade_sell fill confirmation was dropped (CF/WS miss) so
        the bot has no local fills but Polymarket executed the sale. Querying
        trade history recovers the real exit price for accurate PnL tracking.

        Queries both taker_address and maker_address with both funder_address
        and EOA address (from private key) to handle sig_type=0 and sig_type=1/2.
        Does NOT filter by side — CLOB side field perspective varies; any fill
        for our token after entry timestamp is our exit.
        """
        if CONFIG.dry_run:
            return []

        try:
            import requests as _req
        except ImportError:
            logger.warning("fetch_recent_token_sells: requests not available")
            return []

        # Build candidate wallet addresses to query.
        # sig_type=0 (EOA): trades associated with EOA derived from private key.
        # sig_type=1/2 (proxy/safe): trades associated with funder_address.
        # Try both so we always find the fills regardless of signature_type.
        wallets: list[str] = []
        funder = getattr(CONFIG, "funder_address", "") or ""
        if funder:
            wallets.append(funder)
        try:
            from eth_account import Account as _Acct
            _eoa = _Acct.from_key(CONFIG.wallet_private_key).address
            if _eoa.lower() != funder.lower():
                wallets.append(_eoa)
                logger.debug(
                    "fetch_recent_token_sells: querying EOA=%s in addition to funder=%s",
                    _eoa[:10], funder[:10] if funder else "none",
                )
        except Exception:
            pass
        if not wallets:
            logger.warning("fetch_recent_token_sells: no wallet address available")
            return []

        def _parse_trade_ts(val) -> float:
            """Parse CLOB timestamp to unix seconds."""
            if not val:
                return 0.0
            if isinstance(val, (int, float)):
                v = float(val)
                return v / 1000.0 if v > 1e12 else v
            try:
                v = float(val)
                return v / 1000.0 if v > 1e12 else v
            except (ValueError, TypeError):
                pass
            try:
                from datetime import datetime as _dt
                return _dt.fromisoformat(str(val).replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0.0

        results = []
        seen_ids: set = set()

        for wallet in wallets:
            for role in ("taker_address", "maker_address"):
                try:
                    r = _req.get(
                        f"{CONFIG.markets.clob_api_url}/trades",
                        params={role: wallet, "asset_id": token_id, "limit": 50},
                        timeout=6,
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    r.raise_for_status()
                    data = r.json()
                    trades = (
                        data.get("data", []) if isinstance(data, dict)
                        else data if isinstance(data, list)
                        else []
                    )

                    # Debug: log raw schema of first trade so we can see field names
                    if trades:
                        logger.debug(
                            "CLOB /trades wallet=%s role=%s → %d trades; "
                            "first keys=%s",
                            wallet[:10], role, len(trades),
                            list(trades[0].keys())[:12],
                        )
                    else:
                        logger.debug(
                            "CLOB /trades wallet=%s role=%s → 0 trades",
                            wallet[:10], role,
                        )

                    for t in trades:
                        tid = t.get("id") or t.get("trade_id") or ""
                        if tid and tid in seen_ids:
                            continue
                        if tid:
                            seen_ids.add(tid)

                        # Filter by token_id (field may be asset_id or token_id)
                        t_token = t.get("asset_id") or t.get("token_id") or ""
                        if t_token != token_id:
                            continue

                        # Filter by timestamp with 10s clock-skew buffer
                        trade_ts = _parse_trade_ts(
                            t.get("created_at") or t.get("timestamp")
                        )
                        if trade_ts > 0 and trade_ts < since_ts - 10.0:
                            continue

                        # Accept any side — perspective varies (taker vs maker).
                        # Our cascades always SELL, so any fill here is our exit.
                        price = float(t.get("price") or 0)
                        size = float(t.get("size") or t.get("shares") or 0)
                        if price > 0 and size > 0:
                            side_raw = (t.get("side") or t.get("type") or "?").upper()
                            logger.info(
                                "CLOB fill found: token=%s wallet=%s role=%s "
                                "side=%s price=%.4f size=%.4f ts=%s",
                                token_id[:12], wallet[:10], role,
                                side_raw, price, size,
                                t.get("created_at") or t.get("timestamp", "?"),
                            )
                            results.append((price, size))

                except Exception as exc:
                    logger.warning(
                        "fetch_recent_token_sells(%s) wallet=%s role=%s: %s",
                        token_id[:8], wallet[:10], role, exc,
                    )

        if not results:
            logger.warning(
                "fetch_recent_token_sells(%s): no fills found across %d wallet(s) "
                "since_ts=%.0f (now=%.0f delta=%.0fs)",
                token_id[:12], len(wallets), since_ts,
                time.time(), time.time() - since_ts,
            )
        return results

    def fetch_usdc_balance(self) -> Optional[float]:
        """
        Fetch actual USDC balance from Polymarket CLOB.
        Uses GET /balance-allowance — no Cloudflare restrictions, works from
        any machine. Returns balance in USDC (None on failure).
        """
        if self._client is None:
            return None
        try:
            ba = self._client.get_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=CONFIG.signature_type,
                )
            )
            raw = float(ba.get("balance", 0))
            # CLOB returns balance in micro-USDC (1 USDC = 1,000,000 units)
            usdc = raw / 1_000_000
            logger.info("Polymarket USDC balance (actual): $%.4f", usdc)
            return usdc
        except Exception as exc:
            logger.warning("fetch_usdc_balance failed: %s", exc)
            return None

    def fetch_order_fills(self, order_id: str) -> Optional[dict]:
        """
        Query CLOB for actual fill data after an order matches.
        GET /data/trades?id=<order_id> — no CF blocking from any machine.
        Returns dict with actual avg_price, total_size, total_fee_usd, fee_rate_bps.
        Actual fee = price × size × fee_rate_bps / 10000.
        """
        if self._client is None or not order_id:
            return None
        try:
            from py_clob_client_v2.clob_types import TradeParams
            trades = self._client.get_trades(TradeParams(id=order_id))
            if not trades:
                return None
            total_size = sum(float(t.get("size", 0)) for t in trades)
            total_value = sum(
                float(t.get("price", 0)) * float(t.get("size", 0)) for t in trades
            )
            # fee_rate_bps per trade; actual fee = notional × bps / 10000
            total_fee = sum(
                float(t.get("price", 0)) * float(t.get("size", 0))
                * float(t.get("fee_rate_bps", 0)) / 10_000
                for t in trades
            )
            avg_price = total_value / total_size if total_size > 0 else 0
            bps = float(trades[0].get("fee_rate_bps", 0)) if trades else 0
            logger.debug(
                "Order %s actual: size=%.4f avg_price=%.4f fee=$%.5f (%g bps)",
                order_id[:12], total_size, avg_price, total_fee, bps,
            )
            return {
                "order_id": order_id,
                "total_size": total_size,
                "avg_price": avg_price,
                "total_fee_usd": total_fee,
                "fee_rate_bps": bps,
                "n_fills": len(trades),
            }
        except Exception as exc:
            logger.debug("fetch_order_fills %s failed: %s", order_id[:12], exc)
            return None

    async def post_heartbeat(self) -> None:
        """
        Keep the CLOB session alive. CLOB cancels all GTC orders on book if no
        heartbeat for 15 seconds. Call this every 10s during live trading.
        No-op in dry-run or when client is not initialised.
        """
        if CONFIG.dry_run or self._client is None:
            return
        try:
            self._client.post_heartbeat()
        except Exception as exc:
            logger.debug("Heartbeat failed: %s", exc)

    async def cancel_order(self, order_id: str) -> bool:
        if CONFIG.dry_run:
            return True
        if self._client is None:
            return False
        try:
            self._client.cancel_orders([order_id])
            return True
        except Exception as exc:
            logger.error("Cancel failed for %s: %s", order_id, exc)
            return False

    async def cancel_all(self) -> bool:
        if CONFIG.dry_run:
            return True
        if self._client is None:
            return False
        try:
            self._client.cancel_all()
            logger.info("All orders cancelled")
            return True
        except Exception as exc:
            logger.error("Cancel all failed: %s", exc)
            return False

    # ── Dry-run simulation ────────────────────────────────────────────────────

    def _simulate_fill(
        self,
        token_id: str,
        price: float,
        stake_usd: float,
        side: OrderSide,
    ) -> OrderResult:
        import random
        slip = random.uniform(0, 0.003)
        fill_price = price + (slip if side == OrderSide.BUY else -slip)
        fill_price = max(0.01, min(0.99, fill_price))
        size = stake_usd / fill_price if fill_price > 0 else 0
        fee = stake_usd * (
            CONFIG.fees.extreme_fee_rate
            if price < CONFIG.fees.extreme_low or price > CONFIG.fees.extreme_high
            else CONFIG.fees.middle_fee_rate
        )
        fill = Fill(
            order_id=f"dry_{token_id[:6]}_{int(time.time())}",
            token_id=token_id,
            side=side,
            price=fill_price,
            size=size,
            fee=fee,
            slippage=slip,
        )
        self.fill_history.append(fill)
        logger.debug("[DRY] %s %.4f @ %.4f fee=%.4f", side.name, size, fill_price, fee)
        return OrderResult(
            status=OrderStatus.FILLED,
            fills=[fill],
            avg_fill_price=fill_price,
            total_size=size,
            total_fee=fee,
            slippage=slip,
        )
