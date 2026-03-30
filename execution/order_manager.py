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
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        MarketOrderArgs, OrderType, OrderArgs,
        BalanceAllowanceParams, AssetType,
        PartialCreateOrderOptions,
    )
    from py_clob_client.order_builder.constants import BUY as CLOB_BUY, SELL as CLOB_SELL
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
    import py_clob_client.http_helpers.helpers as _clob_helpers
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
        import py_clob_client.http_helpers.helpers as _h

        _orig_client = _h._http_client
        _h._http_client = _httpx.Client(http2=False, timeout=15.0)  # HTTP/1.1 for auth — HTTP/2 hangs on Python 3.14
        try:
            client = ClobClient(**kwargs)
            api_creds = client.create_or_derive_api_creds()
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

        for attempt in range(self.cfg.retry_attempts):
            try:
                result = await self._submit_limit_order(
                    token_id, OrderSide.BUY, limit_price, size,
                    neg_risk=neg_risk, tick_size=tick_size,
                )
                if result.status == OrderStatus.FILLED:
                    return result
                await asyncio.sleep(self.cfg.retry_delay * (2 ** attempt))
            except Exception as exc:
                logger.error("Limit buy attempt %d failed: %s", attempt + 1, exc)
                await asyncio.sleep(self.cfg.retry_delay * (2 ** attempt))

        return OrderResult(status=OrderStatus.FAILED, error="All retry attempts exhausted")

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
        """
        if CONFIG.dry_run:
            return True
        if self._client is None:
            return False
        try:
            self._client.update_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.CONDITIONAL,
                    token_id=token_id,
                )
            )
            await asyncio.sleep(1.0)  # approval propagation delay
            logger.debug("Token approved for sell: %s", token_id[:8])
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
    ) -> List[OrderResult]:
        """
        Exit in tranches: market order primary, limit order fallback.
        Up to 15 attempts per tranche (ported from baseline bot).
        Approves token before first attempt.
        """
        if total_shares <= 0:
            return []

        # Apply 0.99× sell factor to avoid CLOB balance cache bug (Issue #287):
        # CLOB backend sometimes caches a balance slightly below the actual fill.
        # Selling 99% avoids "not enough balance/allowance" failures; dust settles
        # at market resolution.
        total_shares = round(total_shares * 0.99, 4)
        if total_shares <= 0:
            return []

        # Token approval before selling (critical for live)
        await self.approve_token_for_sell(token_id)

        n = self.cfg.cascade_levels
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
                neg_risk=neg_risk, tick_size=tick_size,
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

        sell_price = max(current_price * 0.90, 0.01)
        orig_price = sell_price
        total_sold = 0.0
        # Track actual fill prices per attempt for accurate analytics
        fill_value = 0.0   # sum(price * size) across all attempts

        for attempt in range(max_attempts):
            if shares - total_sold < 0.01:
                break

            remaining = shares - total_sold

            # Market order attempt
            try:
                sell_amount = round(remaining * sell_price, 4)
                result = await self._submit_market_order_sell(token_id, sell_amount)
                if result.status == OrderStatus.FILLED and result.total_size > 0:
                    total_sold += result.total_size
                    fill_value += result.avg_fill_price * result.total_size
                    sell_price = orig_price
                    continue
            except Exception:
                pass

            # Limit order fallback
            try:
                result = await self._submit_limit_order(
                    token_id, OrderSide.SELL, sell_price, remaining,
                    neg_risk=neg_risk, tick_size=tick_size,
                )
                if result.status == OrderStatus.FILLED and result.total_size > 0:
                    total_sold += result.total_size
                    fill_value += result.avg_fill_price * result.total_size
                    continue
            except Exception:
                pass

            # Step price down 10 %
            sell_price = max(sell_price * 0.90, 0.01)
            logger.debug("Sell retry %d: %.4f @ %.4f", attempt + 1, remaining, sell_price)

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
            # neg_risk=False is falsy in py_clob_client — triggers auto-detection.
            # tick_size: pass None unless non-default provided (auto-detect from CLOB,
            # cached 300s) to avoid "invalid tick size" if Gamma data is stale.
            opts = PartialCreateOrderOptions(
                tick_size=tick_size if tick_size and tick_size != "0.01" else None,
                neg_risk=True if neg_risk else None,
            )
            signed = self._client.create_order(order_args, options=opts)

            # GTC for all orders. FAK has an unsatisfiable integer maker-amount
            # constraint (maker_micro must be multiple of 10000) for any non-trivial
            # price. GTC limit orders have no such constraint and fill immediately
            # when our +5% buffer limit price crosses the best ask.
            order_type = OrderType.GTC

            # Cloudflare WAF blocks datacenter IPs on POST /order ~30-50% of the time.
            # Retry with exponential backoff; CF challenges are transient.
            resp = None
            for _cf_attempt in range(3):
                resp = self._client.post_order(signed, order_type)
                err_str = str(resp) if resp else ""
                if resp and "cloudflare" not in err_str.lower() and "403" not in err_str:
                    break
                if _cf_attempt < 2:
                    wait = 0.5 * (2 ** _cf_attempt)  # 0.5s, 1s
                    logger.warning("Cloudflare block on order POST (attempt %d) — retry in %.1fs",
                                   _cf_attempt + 1, wait)
                    await asyncio.sleep(wait)

            if not resp:
                return OrderResult(status=OrderStatus.FAILED, error="Empty response")

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
                    # PRIMARY: wait on user channel WS fill event (sub-100ms).
                    # FALLBACK: poll REST every 1s if WS not connected.
                    # Both paths timeout after 10s then cancel.
                    logger.info(
                        "BUY order resting — awaiting fill via user WS (up to 10s): %s",
                        order_id[:12],
                    )

                    fill_data = None
                    if self._fill_tracker.is_connected:
                        # Fast path: WS delivers fill event in ~50-200ms
                        fill_data = await self._fill_tracker.wait_fill(order_id, timeout=10.0)
                    else:
                        # Slow path: poll REST at 1s intervals (WS down/reconnecting)
                        for _poll in range(10):
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
                        try:
                            self._client.cancel(order_id)
                            logger.info("Cancelled unfilled resting BUY %s", order_id[:12])
                        except Exception:
                            pass
                        return OrderResult(
                            status=OrderStatus.FAILED,
                            error="BUY resting — cancelled after 10s (no fill)",
                        )
                else:
                    # SELL resting: no bid at our floor price — cascade will retry lower.
                    if order_id:
                        try:
                            self._client.cancel(order_id)
                            logger.info("Cancelled resting GTC SELL %s", order_id[:12])
                        except Exception:
                            pass
                    return OrderResult(status=OrderStatus.FAILED, error="SELL resting on book (live)")

            if status != "matched" or taking_f <= 0:
                logger.info(
                    "Order not filled (status=%s takingAmount=%s) — skipping",
                    status, taking,
                )
                return OrderResult(status=OrderStatus.FAILED, error=f"Unfilled: {status}")

            fill_size = taking_f
            fill_cost = _to_float(making) or (fill_size * price)
            fill_price = fill_cost / fill_size if fill_size > 0 else price
            slippage = abs(fill_price - price)

            fill = Fill(
                order_id=resp.get("id", ""),
                token_id=token_id,
                side=side,
                price=fill_price,
                size=fill_size,
                fee=0.0,
                slippage=slippage,
            )
            self.fill_history.append(fill)
            return OrderResult(
                status=OrderStatus.FILLED,
                fills=[fill],
                avg_fill_price=fill_price,
                total_size=fill_size,
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
            self._client.cancel(order_id)
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
