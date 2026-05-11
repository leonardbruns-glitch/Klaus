"""Oracle sweep — exploits the 35-second Chainlink latency window.

VERIFIED (2026-05-11, n=3,678 windows):
  - 99% of windows: oracle fires exactly 35s after window_end_ts.
  - 100% of flat-kline windows (open==close, n=43): resolve YES UP.
  - Winning token asks confirmed at 0.01–0.96 in final 35s window (n=876 trades).
  - One confirmed sweep: SOL UP at $0.01 → $331 payout (9,900% return).

Two sub-strategies per window close:

  A) Kline sweep (T+0 to T+33s):
     Fetch Binance kline at window close. Result is deterministic (close>=open → YES).
     Buy any ask < ASK_CEILING on winning token. Sell at 0.99 or let auto-settle.

  B) Stale-ask sweep (same window):
     Orphaned limit sells placed early in window at stale prices.
     Same logic — buy any ask < ASK_CEILING on winning token.

Architecture:
  - OracleSweeper.register_token() called from TimelineSampler._sample_once() each tick.
    Builds a cid → {outcome_dir: token_id} map before window closes.
  - OracleSweeper.schedule() called once per (cid, wend). Spawns asyncio task.
  - Task sleeps until wend + SWEEP_DELAY_S, fetches kline, sweeps cheap asks.
  - Exit: cascade_sell at 0.99 immediately; if unfilled by wend+ORACLE_FIRES_S, cancel
    and hold for on-chain auto-settlement.

Risk limits:
  MAX_STAKE_PER_WINDOW = $50    (hard cap regardless of book depth)
  ASK_CEILING          = 0.97   (must yield at least 3% after taker fee)
  MIN_PROFIT_THRESHOLD = 0.005  (skip windows where expected edge < $0.005)

Capital tracking: separate from BOND/DISCOVER. Logged to shadow as "oracle_sweep" events.
Never raises — all exceptions caught internally.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Set, Tuple

import aiohttp

from strategy.momentum import Direction

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
SWEEP_DELAY_S      = 0.0    # fire immediately at window close (WS kline cache eliminates REST wait)
ORACLE_FIRES_S     = 33.0   # sell/cancel before this (oracle fires at ~35s)
ASK_CEILING        = 0.97   # maximum price we'll pay (must leave 3% margin)
MAX_STAKE_PER_WIN  = 50.0   # max USDC per window
MIN_EDGE_USD       = 0.01   # skip if expected profit < $0.01

# A1 — flat-market pre-entry constants
# Verified: 43/43 windows where kclose==kopen resolved YES UP (tie rule).
# If Binance candle is near-flat in final 30s, YES_UP has structural edge.
FLAT_PCT_THRESHOLD  = 0.020  # |candle_return_pct| < 0.02% = effectively flat
FLAT_ENTRY_REM_MIN  = 5.0    # enter no earlier than 30s before close
FLAT_ENTRY_REM_MAX  = 30.0
FLAT_ASK_CEILING    = 0.70   # pay up to 0.70 for near-certain YES_UP in flat market
FLAT_MAX_STAKE      = 20.0   # more capital — tie is structural guarantee

_SYMBOL_MAP   = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
_INTERVAL_MAP = {300: "5m", 900: "15m"}
_CLOB_BOOK_URL = "https://clob.polymarket.com/book"


class OracleSweeper:
    """Fires after every window close. Sweeps cheap asks on the winning token."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.enabled: bool = True

        # cid → {"up": token_id, "down": token_id}
        self._cid_tokens: Dict[str, Dict[str, str]] = {}
        # (cid, wend) already scheduled
        self._scheduled: Set[Tuple[str, int]] = set()
        # active asyncio tasks
        self._tasks = []

        # Lifetime stats
        self.sweeps_attempted: int = 0
        self.sweeps_filled: int   = 0
        self.gross_profit_usd: float = 0.0

    # ── Public API called from TimelineSampler ─────────────────────────────────

    def register_token(self, cid: str, outcome_dir: str, token_id: str) -> None:
        """Record the token_id for a given market side. Called every tick — idempotent."""
        if not cid or not token_id:
            return
        if cid not in self._cid_tokens:
            self._cid_tokens[cid] = {}
        self._cid_tokens[cid][outcome_dir] = token_id

    def schedule(
        self,
        cid: str,
        wend: int,
        asset: str,
        window_size_s: int,
    ) -> None:
        """Idempotent. First call per (cid, wend) spawns post-close sweep + A1 flat-entry task."""
        if not self.enabled:
            return
        key = (cid, wend)
        if key in self._scheduled:
            return
        tokens = self._cid_tokens.get(cid, {})
        if "up" not in tokens or "down" not in tokens:
            return
        self._scheduled.add(key)
        # Post-close sweep (A2 + A3)
        task = asyncio.create_task(
            self._run(cid, wend, asset, window_size_s, dict(tokens)),
            name=f"oracle_sweep_{cid[:8]}_{wend}",
        )
        self._tasks.append(task)
        # A1: flat-market pre-entry — 5m windows only.
        # A1 checks the current 5m Binance candle for flatness. For 15m windows,
        # the resolution kline is 15m (not 5m), so A1's signal is wrong for them.
        if window_size_s == 300:
            flat_task = asyncio.create_task(
                self._flat_entry(cid, wend, asset, dict(tokens)),
                name=f"flat_entry_{cid[:8]}_{wend}",
            )
            self._tasks.append(flat_task)
        if len(self._tasks) > 256:
            self._tasks = [t for t in self._tasks if not t.done()]

    async def stop(self) -> None:
        live = [t for t in self._tasks if not t.done()]
        for t in live:
            t.cancel()
        if live:
            await asyncio.gather(*live, return_exceptions=True)

    # ── A1: flat-market pre-entry ──────────────────────────────────────────────

    async def _flat_entry(
        self,
        cid: str,
        wend: int,
        asset: str,
        tokens: Dict[str, str],
    ) -> None:
        """A1 exploit: verified that 100% of flat-kline windows resolve YES UP.
        In the final 30s, if Binance candle is near-flat, pre-buy YES_UP.
        Never raises."""
        try:
            # Sleep until FLAT_ENTRY_REM_MAX seconds before window close
            wake_at = wend - FLAT_ENTRY_REM_MAX
            wait = wake_at - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
            if time.time() > wend - FLAT_ENTRY_REM_MIN:
                return  # too late

            feed = self.bot.feed
            asset_up = asset.upper()
            spot     = feed._spot_price.get(asset_up, 0.0)
            open_5m  = feed._spot_open_5m.get(asset_up, 0.0)
            if spot <= 0 or open_5m <= 0:
                return

            candle_pct = abs((spot - open_5m) / open_5m * 100.0)
            logger.info("flat_entry A1: %s candle_pct=%.4f%% (flat<%.3f%%)", asset, candle_pct, FLAT_PCT_THRESHOLD)
            if candle_pct >= FLAT_PCT_THRESHOLD:
                return  # not flat enough

            yes_token_id = tokens.get("up")
            if not yes_token_id:
                return
            # Already in a position?
            if yes_token_id in self.bot.risk.open_positions:
                return

            # Get current ask on YES_UP token
            ob = feed.get_order_book(yes_token_id)
            if ob is None or not ob.asks:
                return
            ask = ob.asks[0][0]
            if ask > FLAT_ASK_CEILING:
                return  # too expensive

            logger.info(
                "flat_entry A1: %s candle_pct=%.4f%% YES ask=%.4f rem=%.0fs — ENTERING",
                asset, candle_pct, ask, wend - time.time(),
            )

            stake = min(FLAT_MAX_STAKE, ask * ob.asks[0][1])
            stake = max(stake, 1.0)
            result = await self.bot.orders.limit_buy(
                token_id=yes_token_id,
                intended_price=ask,
                stake_usd=stake,
                direction=Direction.BUY_YES,
            )
            from execution.order_manager import OrderStatus
            if result.status == OrderStatus.FILLED and result.total_size > 0:
                logger.info(
                    "flat_entry A1 FILLED: %.4f shares @ %.4f $%.2f | %s",
                    result.total_size, ask, ask * result.total_size, asset,
                )
                self._emit_shadow(asset, "up", yes_token_id, ask,
                                  result.total_size, ask * result.total_size, wend,
                                  extra={"candle_pct": round(candle_pct, 5), "entry_type": "flat_A1"})
                # Exit: T-3s safety sell. CLOB minimum is 5 shares — skip if below.
                exit_wait = max(1.0, wend - time.time() - 3.0)
                await asyncio.sleep(exit_wait)
                if result.total_size < 5.0:
                    logger.info("flat_A1 exit: %.4f shares < 5 CLOB minimum — holding to settle", result.total_size)
                    return
                ob2 = feed.get_order_book(yes_token_id)
                bid = ob2.bids[0][0] if (ob2 and ob2.bids) else 0.99
                await self.bot.orders.cascade_sell(
                    token_id=yes_token_id,
                    total_shares=result.total_size,
                    current_price=max(bid, 0.01),
                    reason="flat_A1_exit",
                    force_exit=True,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.info("flat_entry error %s wend=%s", asset, wend, exc_info=True)

    # ── Sweep task ─────────────────────────────────────────────────────────────

    async def _run(
        self,
        cid: str,
        wend: int,
        asset: str,
        window_size_s: int,
        tokens: Dict[str, str],  # {"up": tid, "down": tid}
    ) -> None:
        """Main sweep coroutine. Never raises."""
        try:
            await self._run_inner(cid, wend, asset, window_size_s, tokens)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("oracle_sweep unhandled error cid=%s wend=%s", cid[:8], wend)

    async def _run_inner(
        self,
        cid: str,
        wend: int,
        asset: str,
        window_size_s: int,
        tokens: Dict[str, str],
    ) -> None:
        # Wait until SWEEP_DELAY_S after window close
        wait = (wend + SWEEP_DELAY_S) - time.time()
        if wait > 2.0:
            await asyncio.sleep(wait)
        elif wait < -ORACLE_FIRES_S:
            # Already past the oracle fire window — nothing to do
            return

        # Fetch Binance kline to determine the winner
        winner_dir = await self._kline_winner(asset, wend, window_size_s)
        if winner_dir is None:
            logger.debug("oracle_sweep: kline fetch failed — %s wend=%s", asset, wend)
            return

        winning_token_id = tokens.get(winner_dir)
        if not winning_token_id:
            return

        logger.info(
            "oracle_sweep: wend=%s %s winner=%s token=%s",
            wend, asset, winner_dir, winning_token_id[:12],
        )

        # Fetch CLOB book for winning token via REST
        cheap_asks = await self._get_cheap_asks(winning_token_id)
        if not cheap_asks:
            # Log actual book state so we can diagnose: empty vs priced-out vs swept
            ob = self.bot.feed.get_order_book(winning_token_id)
            if ob and ob.asks:
                best_ask = ob.asks[0][0]
                n_asks = len(ob.asks)
                logger.info(
                    "oracle_sweep: no stale asks ≤%.2f for %s/%s (book: %d asks, best=%.4f)",
                    ASK_CEILING, asset, winner_dir, n_asks, best_ask,
                )
            else:
                logger.info(
                    "oracle_sweep: no stale asks ≤%.2f for %s/%s (book: EMPTY)",
                    ASK_CEILING, asset, winner_dir,
                )
            return

        # Check time budget — must sweep before ORACLE_FIRES_S
        time_left = (wend + ORACLE_FIRES_S) - time.time()
        if time_left < 3.0:
            logger.info("oracle_sweep: insufficient time (%.1fs left) — skipping", time_left)
            return

        # Sweep each cheap ask level up to MAX_STAKE_PER_WIN
        budget = MAX_STAKE_PER_WIN
        total_spent = 0.0
        total_shares = 0.0

        for ask_price, ask_size in cheap_asks:
            if budget < MIN_EDGE_USD:
                break
            expected_profit = (1.0 - ask_price) * ask_size - (ask_price * ask_size * 0.02)
            if expected_profit < MIN_EDGE_USD:
                continue

            stake = min(budget, ask_price * ask_size)
            if stake < 1.0:  # CLOB minimum
                continue

            self.sweeps_attempted += 1
            logger.info(
                "oracle_sweep: BUY %s ask=%.4f stake=$%.2f expected_profit=$%.2f",
                asset, ask_price, stake, (1.0 - ask_price) * (stake / ask_price),
            )

            try:
                result = await self.bot.orders.limit_buy(
                    token_id=winning_token_id,
                    intended_price=ask_price,
                    stake_usd=stake,
                    direction=Direction.BUY_YES,
                )
                from execution.order_manager import OrderStatus
                if result.status == OrderStatus.FILLED and result.total_size > 0:
                    self.sweeps_filled += 1
                    spent = ask_price * result.total_size
                    total_spent += spent
                    total_shares += result.total_size
                    budget -= spent
                    expected = result.total_size * 1.0
                    self.gross_profit_usd += expected - spent
                    logger.info(
                        "oracle_sweep FILLED: %.4f shares @ %.4f | cost=$%.2f expected_return=$%.2f",
                        result.total_size, ask_price, spent, expected,
                    )
                    self._emit_shadow(asset, winner_dir, winning_token_id, ask_price,
                                      result.total_size, spent, wend)
                else:
                    logger.info("oracle_sweep: fill failed at ask=%.4f", ask_price)
            except Exception as exc:
                logger.info("oracle_sweep: buy error: %s", exc)

        if total_shares <= 0:
            return

        # Schedule exit sell at ORACLE_FIRES_S - 2s
        exit_wait = max(0.5, (wend + ORACLE_FIRES_S - 2) - time.time())
        logger.info(
            "oracle_sweep: scheduling exit in %.1fs (%.4f shares, cost=$%.2f)",
            exit_wait, total_shares, total_spent,
        )
        await asyncio.sleep(exit_wait)
        try:
            await self.bot.orders.cascade_sell(
                token_id=winning_token_id,
                total_shares=total_shares,
                current_price=0.99,
                reason="oracle_sweep_exit",
                force_exit=True,
            )
            logger.info("oracle_sweep: exit sell submitted (%.4f shares)", total_shares)
        except Exception as exc:
            # Exit failed — token will auto-settle on-chain at resolution
            logger.info("oracle_sweep: exit sell failed (%s) — holding to auto-settle", exc)

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _kline_winner(
        self,
        asset: str,
        wend: int,
        window_size_s: int,
    ) -> Optional[str]:
        """Determine winner from closed kline. WS cache first (0ms), REST fallback (258ms)."""
        # ── Fast path: WS kline close event already populated the cache ──────────
        ws_cache = getattr(self.bot.feed, "_kline_winner_cache", {})
        cached = ws_cache.get(asset.upper())
        if cached:
            direction, cached_wend = cached
            if abs(cached_wend - wend) <= 2:
                logger.debug("oracle_sweep: kline WS cache hit %s → %s (wend=%s)", asset, direction, wend)
                return direction
        # WS not yet delivered — wait briefly then retry cache once before REST
        await asyncio.sleep(0.15)
        cached = ws_cache.get(asset.upper())
        if cached:
            direction, cached_wend = cached
            if abs(cached_wend - wend) <= 2:
                logger.debug("oracle_sweep: kline WS cache hit (retry) %s → %s", asset, direction)
                return direction

        # ── Slow path: REST fallback (~258ms) ─────────────────────────────────
        symbol   = _SYMBOL_MAP.get(asset.upper())
        interval = _INTERVAL_MAP.get(window_size_s)
        if not symbol or not interval:
            return None
        session = getattr(self.bot.feed, "_session", None)
        if session is None:
            return None
        wstart_ms = int((wend - window_size_s) * 1000)
        try:
            async with session.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": symbol, "interval": interval,
                        "startTime": wstart_ms, "limit": 1},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return None
                klines = await resp.json()
        except Exception as exc:
            logger.debug("oracle_sweep kline fetch %s/%s: %s", asset, wend, exc)
            return None
        if not klines or len(klines[0]) < 5:
            return None
        kopen  = float(klines[0][1])
        kclose = float(klines[0][4])
        return "up" if kclose >= kopen else "down"

    async def _get_cheap_asks(
        self,
        token_id: str,
    ) -> list:
        """Returns (price, size) asks below ASK_CEILING. WS book cache first (0ms), REST fallback."""
        # ── Fast path: WS order book already cached by CLOB websocket ────────────
        ob = self.bot.feed.get_order_book(token_id)
        if ob and ob.asks:
            result = [(p, s) for p, s in ob.asks if p < ASK_CEILING and s > 0]
            if result:
                logger.debug("oracle_sweep: WS book hit %s — %d cheap asks", token_id[:12], len(result))
                return result

        # ── Slow path: REST fallback (~43ms) ──────────────────────────────────
        session = getattr(self.bot.feed, "_session", None)
        if session is None:
            return []
        try:
            async with session.get(
                _CLOB_BOOK_URL,
                params={"token_id": token_id},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception as exc:
            logger.debug("oracle_sweep book fetch %s: %s", token_id[:12], exc)
            return []
        asks = data.get("asks", [])
        result = []
        for entry in asks:
            try:
                p = float(entry.get("price", 1.0))
                s = float(entry.get("size",  0.0))
                if p < ASK_CEILING and s > 0:
                    result.append((p, s))
            except (TypeError, ValueError):
                continue
        result.sort(key=lambda x: x[0])
        return result

    def _emit_shadow(
        self,
        asset: str,
        winner_dir: str,
        token_id: str,
        price: float,
        shares: float,
        cost_usd: float,
        wend: int,
        extra: Optional[dict] = None,
    ) -> None:
        """Log the sweep to shadow pipeline if available."""
        pipeline = getattr(self.bot, "shadow_pipeline", None)
        if pipeline is None:
            return
        try:
            rec = {
                "schema_version": 1,
                "record_type": "oracle_sweep",
                "ts_s": int(time.time()),
                "asset": asset,
                "winner_dir": winner_dir,
                "token_id": token_id,
                "fill_price": round(price, 4),
                "fill_shares": round(shares, 4),
                "cost_usd": round(cost_usd, 4),
                "expected_return_usd": round(shares, 4),
                "expected_profit_usd": round(shares - cost_usd, 4),
                "window_end_ts": wend,
            }
            if extra:
                rec.update(extra)
            pipeline.emit(rec)
        except Exception:
            pass
