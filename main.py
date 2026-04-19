"""
Klaus — Momentum Scalper
Main async event loop: data → strategy → risk → execution → feedback.

Usage:
    python main.py                     # dry run (default)
    POLYMARKET_API_KEY=... python main.py  # live (set dry_run=False in config)

Loop cadence:
    - Every 1 second:  order-book scan for all open positions (exit check)
    - Every 5 seconds: full market sweep for new signals
    - Every 30 minutes: print feedback report
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections import deque
import os
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from config import CONFIG
from data.feeds import PolymarketFeed
from strategy.momentum import MomentumScorer, Direction, FeeZone, SignalBreakdown, calculate_tp_sl, TPSLLevels
from strategy.window_sniper import WindowSniper, SniperBlock, SniperSignal, _session_min_delta, CONTRARIAN_MAX_ASK, CONTRARIAN_DELTA_ENABLED, BOND_ENABLED, SNIPER_ENABLED, MOM_ENABLED
from analytics.shadow_log import log_shadow_result
from risk.manager import RiskManager, ExitStage
from analytics.lag_observations import log_lag_observation
from analytics.macro_engine import MacroEngine
from execution.order_manager import OrderManager, OrderResult, OrderStatus
from analytics.feedback import FeedbackEngine
from analytics.research import ResearchEngine

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log"),
    ],
)
# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Shadow monitor — counterfactual analysis for blocked sniper signals
# ---------------------------------------------------------------------------

async def _shadow_monitor(block: SniperBlock, feed: "PolymarketFeed",
                          active_set: set, dedup_key: tuple,
                          llm_boost: float = 0.0) -> None:
    """
    After the sniper blocks a candidate trade, watch the token's ask price at
    +30s, +60s, +120s, and at window close. Log what would have happened if
    we had entered at block.token_ask.

    This gives us the data to answer: "Are our blocks correct, or are we
    leaving profitable trades on the table?"

    Analysis: check logs/shadow_blocks.jsonl after 50+ blocks.
    """
    checkpoints = [30.0, 60.0, 120.0, 180.0]
    results: dict = {}
    start = time.time()
    time_remaining = block.window_end_ts - start

    if time_remaining <= 5:
        return  # window almost over — no useful data to collect

    for delay in checkpoints:
        target_ts = start + delay
        sleep_for = target_ts - time.time()
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

        # Window expired before checkpoint — record None and stop
        if time.time() >= block.window_end_ts:
            break

        ob = feed.get_order_book(block.token_id)
        ask = ob.asks[0][0] if (ob and ob.asks) else None
        results[f"ask_at_{int(delay)}s"] = ask

    # Wait for window close to get final ask (resolution proxy).
    # Cap at 1200s (20 min) to cover 15m windows blocked early in the window.
    # Previous cap of 120s was too short — most blocks happen at 25-60% elapsed,
    # leaving 6-11 minutes until close which was silently skipped.
    window_close_wait = block.window_end_ts - time.time()
    if 0 < window_close_wait <= 1200:
        await asyncio.sleep(window_close_wait + 2.0)  # +2s settle
        ob = feed.get_order_book(block.token_id)
        ask_final = ob.asks[0][0] if (ob and ob.asks) else None
    else:
        ask_final = None

    log_shadow_result(
        block=block,
        ask_at_30s=results.get("ask_at_30s"),
        ask_at_60s=results.get("ask_at_60s"),
        ask_at_120s=results.get("ask_at_120s"),
        ask_at_180s=results.get("ask_at_180s"),
        ask_at_window_end=ask_final,
        llm_boost=llm_boost,
    )

    label = f"{block.asset}/{block.side} [{block.block_reason}]"
    max_ask = max((v for v in [
        results.get("ask_at_30s"), results.get("ask_at_60s"),
        results.get("ask_at_120s"), ask_final
    ] if v is not None), default=None)
    active_set.discard(dedup_key)  # allow future windows to register new monitors

    if max_ask is not None:
        pnl = (max_ask - block.token_ask) / block.token_ask
        would_win = max_ask >= block.token_ask * 1.20
        logger.info(
            "SHADOW %s | entry_ask=%.3f max_ask=%.3f pnl=%+.1f%% would_win=%s "
            "(lag=%.0f%% edge=%+.3f fv=%.3f)",
            label, block.token_ask, max_ask, pnl * 100, would_win,
            block.lag_remaining_pct * 100, block.edge, block.fair_value,
        )


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

class KlausBot:
    """Top-level orchestrator."""

    def __init__(self) -> None:
        self.feed = PolymarketFeed()
        self.scorer = MomentumScorer()
        self.risk = RiskManager()
        self.orders = OrderManager()
        self.analytics = FeedbackEngine()
        self.research = ResearchEngine(self.feed, self.scorer)
        self.macro_engine = MacroEngine()
        self.sniper = WindowSniper()
        self._running = False
        self._last_report_ts = 0.0
        # track entry metadata for trade recording
        self._open_meta: Dict[str, dict] = {}
        self._pos_log_ts: Dict[str, float] = {}   # last log time per position
        # Shadow monitor dedup: track (token_id, window_end_ts) already being monitored
        # to avoid spawning a new task every 0.2s scan cycle for the same block.
        self._shadow_active: Set[tuple] = set()
        # Last known external signals per asset — shared between signal loop (writer)
        # and OB scan loop (reader). Used by advise_exit without a separate fetch.
        self._last_ext_signals: Dict[str, object] = {}
        # Reversal stop confirmation: counts consecutive 1s OB checks where spot is
        # above the adverse threshold. Fire only when count >= 2 — filters single-tick noise.
        self._rev_breach_count: Dict[str, int] = {}
        # BOND_DIR_REVERSAL confirmation: consecutive scans where window delta has reversed.
        # Requires 5 consecutive checks (~5s sustained) before firing exit.
        self._dir_rev_count: Dict[str, int] = {}
        # Buy attempt tracking for session report
        self._buy_tried: int = 0
        self._buy_filled: int = 0
        self._buy_failed_reasons: Dict[str, int] = {}
        # Residual share tracker: shares that survived a partial cascade_sell at close.
        # Format: token_id → {shares, asset, neg_risk, tick_size, attempts, last_try}
        # Background sweep retries every 60s up to 10 attempts (~10 min).
        self._residual_pending: Dict[str, dict] = {}
        # Exit concurrency guard: prevents multiple cascade_sells firing on the same
        # token while the first is still awaiting CLOB fills (OB scan runs every 200ms,
        # stage-1 cascade takes ~6s — without this lock, 30 concurrent cascades drain
        # the CLOB balance to near-zero by tranche 3, leaving shares unsold).
        self._exit_in_progress: set = set()
        # Pending entries: token_ids approved but _enter_position not yet complete.
        # Guards against race between spike path and 5s sweep both approving the
        # same token before either has called open_position(). Checked synchronously
        # (before first await) so asyncio single-thread guarantee makes it race-free.
        self._pending_entries: set = set()
        # Asset-level entry lock: prevents duplicate positions when spike + scan
        # both approve the same asset before either fill is confirmed.
        # Checked synchronously (before first await) — race-free in asyncio.
        self._pending_asset_entries: set = set()
        # Event-driven spike dedup: tracks last spike entry attempt per asset.
        # Separate from the 5s sweep — prevents double-entry when both paths fire.
        self._last_spike_ts: Dict[str, float] = {}
        # Post-entry price snapshots for path classification.
        # token_id → {30: price_at_T30s, 60: price_at_T60s}
        # Populated in _check_open_positions; consumed and cleared at close.
        self._entry_snaps: Dict[str, Dict[int, float]] = {}
        # BOND_PRICE_SL confirmation counter: increments each scan price is below 50%.
        # SL only fires after 7 consecutive scans (~7s) to filter stop-hunt wicks.
        self._sl_below_count: Dict[str, int] = {}
        # Positions that have had the T+30s stall check (one-shot per position).
        self._stall_checked: set = set()
        # Per-token rolling snapshot: deque of (ts, bond_delta, edge) for acceleration/drift.
        self._bond_snapshots: Dict[str, deque] = {}
        # Peak bond_move reached per position (for trailing stop on winners).
        self._peak_bond_move: Dict[str, float] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await self.feed.start()
        self.feed._on_bbo_update = self._ws_bond_tp_check
        await self.orders.start()
        self._running = True
        mode = "DRY RUN" if CONFIG.dry_run else "LIVE"

        # ── Bankroll sync: reconcile tracked capital with actual Polymarket balance ──
        # GET /balance-allowance is not CF-blocked — works from any machine.
        # Corrects drift from manual trades, crashed sessions, or manual deposits.
        #
        # GUARD: skip sync when LIVE positions exist from a previous session.
        # The USDC balance only reflects unspent cash — it does NOT include the
        # value of open token positions. Syncing while positions are open would
        # set capital = (capital − value_of_open_tokens), incorrectly lowering it.
        # Exception: positions loaded from file that have already expired are
        # treated as closed (market resolved on-chain); sync is safe then.
        now_ts = time.time()
        live_positions = {
            tid: pos for tid, pos in self.risk.open_positions.items()
            if pos.window_end_ts <= 0 or pos.window_end_ts > now_ts - 30
        }
        if not CONFIG.dry_run:
            if live_positions:
                logger.warning(
                    "BANKROLL SYNC skipped: %d live positions in memory "
                    "(balance = unspent cash only, would undercount capital)",
                    len(live_positions),
                )
            else:
                real_balance = self.orders.fetch_usdc_balance()
                if real_balance is not None:
                    tracked = self.risk.bankroll.capital
                    delta = real_balance - tracked
                    if abs(delta) > 0.05:  # $0.05 tolerance for rounding
                        logger.warning(
                            "BANKROLL SYNC: tracked=%.2f  actual=%.2f  delta=%+.2f — syncing to actual",
                            tracked, real_balance, delta,
                        )
                    else:
                        logger.info(
                            "Bankroll verified: tracked=%.2f matches actual=%.2f",
                            tracked, real_balance,
                        )
                    self.risk.bankroll.capital = real_balance
                    self.risk.bankroll._save()
                else:
                    logger.warning("BANKROLL SYNC failed: fetch_usdc_balance returned None — using tracked=%.2f", self.risk.bankroll.capital)

        logger.info("=" * 50)
        logger.info("Klaus Momentum Scalper — %s", mode)
        logger.info("Capital: $%.2f | Base stake: $%.2f | Scaled: $%.2f",
                    self.risk.bankroll.capital, CONFIG.bankroll.base_stake, CONFIG.bankroll.scaled_stake)
        logger.info("Markets: %s", CONFIG.markets.tracked_assets)
        logger.info("=" * 50)

        # Register event-driven delta spike callback.
        # Fires immediately from Binance aggTrade when asset delta crosses 0.03%.
        # Bypasses the 5s signal loop — detects lag the moment it opens.
        self.feed.register_delta_spike_callback(self._on_delta_spike)

        # Pre-warm py_clob_client caches (neg_risk + fee_rate) for all tracked tokens.
        # Without this, the first order per token triggers GET /neg-risk + GET /fee-rate
        # before submitting, adding ~2s of latency and causing the sniper to miss fills.
        if not CONFIG.dry_run:
            self.orders.prewarm_token_caches(self.feed.tokens)

        # Replay resolution tasks missed due to previous restarts (within 15min)
        asyncio.create_task(self._replay_pending_resolutions())

    async def stop(self) -> None:
        self._running = False
        await self.feed.stop()
        await self.orders.stop()
        report = self.analytics.generate_claude_report()
        logger.info("\nFINAL REPORT:\n%s", report)

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        await self.start()

        # Thread-based event loop watchdog — asyncio coroutines cannot monitor
        # each other when the loop itself is blocked (sync call, CPU-bound work,
        # deadlock). A daemon thread runs independently and kills the process if
        # the loop stops pinging within the threshold. systemd/launchd restarts.
        _watchdog_last_ping = [time.monotonic()]
        _WATCHDOG_THRESHOLD = 45.0  # seconds without a ping before hard kill

        def _watchdog_thread():
            import sys
            time.sleep(_WATCHDOG_THRESHOLD + 5)  # initial grace period
            while True:
                time.sleep(10.0)
                age = time.monotonic() - _watchdog_last_ping[0]
                if age > _WATCHDOG_THRESHOLD:
                    print(
                        f"WATCHDOG FATAL: event loop stalled {age:.0f}s — forcing restart",
                        file=sys.stderr, flush=True,
                    )
                    os._exit(1)  # bypass Python cleanup — systemd will restart

        import threading
        _wdt = threading.Thread(target=_watchdog_thread, daemon=True, name="loop-watchdog")
        _wdt.start()

        # Startup orphan sweep: sell any untracked token balances left over from
        # previous sessions. Delayed 10s to let the feed populate token list first.
        asyncio.create_task(self._startup_orphan_sweep())

        ob_task = asyncio.create_task(self._ob_scan_loop())
        signal_task = asyncio.create_task(self._signal_loop())
        report_task = asyncio.create_task(self._report_loop())
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(_watchdog_last_ping))
        research_task = asyncio.create_task(self.research.run())
        prewarm_task = asyncio.create_task(self._prewarm_loop())

        try:
            # return_exceptions=True: one task crashing doesn't cancel the others.
            # Each loop already catches exceptions internally; this is a safety net
            # for exceptions that escape the loop (startup errors, NameError, etc.)
            results = await asyncio.gather(
                ob_task, signal_task, report_task, heartbeat_task,
                research_task, prewarm_task,
                return_exceptions=True,
            )
            for i, r in enumerate(results):
                if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError):
                    logger.error("Task %d exited with exception: %s", i, r)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    # ── 1-second OB scan: monitor open positions ──────────────────────────────

    async def _ob_scan_loop(self) -> None:
        while self._running:
            try:
                await self._check_open_positions()
            except Exception as exc:
                logger.error("OB scan error: %s", exc)
            await asyncio.sleep(CONFIG.execution.ob_scan_interval)

    async def _ws_bond_tp_check(self, token_id: str, bid_price: float) -> None:
        """Instant BOND TP triggered by WS BBO update — no 1s scan delay."""
        try:
            pos = self.risk.open_positions.get(token_id)
            if pos is None or not pos.is_bond or token_id in self._exit_in_progress:
                return
            bond_remaining = pos.window_end_ts - time.time() if pos.window_end_ts > 0 else 999.0
            if bid_price >= 0.99 and bond_remaining <= 20.0:
                tp_reason = "BOND_TP_99"
            elif bid_price >= 0.95:
                tp_reason = "BOND_TP_95"
            else:
                return
            self._exit_in_progress.add(token_id)
            try:
                logger.info(
                    "BOND_TP_WS %s/%s bid=%.4f rem=%.0fs entry=%.4f",
                    pos.asset, pos.direction.name, bid_price, bond_remaining, pos.entry_price,
                )
                await self._exit_position(token_id, bid_price, tp_reason)
            finally:
                self._exit_in_progress.discard(token_id)
        except Exception as exc:
            logger.error("_ws_bond_tp_check error: %s", exc)

    async def _check_open_positions(self) -> None:
        positions = list(self.risk.open_positions.items())
        if not positions:
            return

        # Fetch all OBs in parallel — no reason to wait sequentially
        obs = await asyncio.gather(
            *[self.feed.fetch_order_book(tid) for tid, _ in positions],
            return_exceptions=True,
        )

        for (token_id, pos), ob in zip(positions, obs):
            # If OB is unavailable but window is expiring, force-exit immediately.
            # This was broken by no_trade_last_sec 60→10: at T-10s OBs are often
            # empty/None for near-resolved tokens, causing the skip below to fire
            # and EXIT_WINDOW_END to never trigger.
            if ob is None or isinstance(ob, Exception):
                now_ts = time.time()
                remaining_ts = pos.window_end_ts - now_ts if pos.window_end_ts > 0 else 999
                if pos.is_bond:
                    # BOND positions have a dedicated precise timer — never sell via OB_NOOB.
                    # OB commonly goes None in the last 45s of updown markets (thinning liquidity)
                    # which was causing 15-20s premature exits on T-60s entries.
                    continue
                if pos.window_end_ts > 0 and remaining_ts <= 45:
                    logger.warning(
                        "OB UNAVAILABLE near window end %s (%.0fs remaining) — "
                        "checking CLOB balance then force-purging",
                        token_id[:12], remaining_ts,
                    )
                    # Verify shares actually exist before trying to sell.
                    # If balance=0 the position was already sold (manually or by previous exit).
                    _balance = self.orders.fetch_token_balance(token_id)
                    if _balance is None or _balance < 0.05:
                        # Nothing to sell — just purge the tracking record.
                        logger.warning(
                            "OB_NOOB_PURGE %s: balance=%.4f — position closed externally, purging record",
                            token_id[:12], _balance or 0.0,
                        )
                        _pnl = self.risk.close_position(token_id, pos.entry_price, "NOOB_EXTERNALLY_SOLD")
                        _noob_meta = self._open_meta.pop(token_id, {})
                        self._pos_log_ts.pop(token_id, None)
                        if _pnl is not None:
                            _noob_sig = _noob_meta.get("signal") or SignalBreakdown(
                                direction=pos.direction, entry_price=pos.entry_price,
                                composite=0.0, confidence=0.0, breakout_score=0.0,
                                trend_score=0.0, volume_score=0.0, ob_score=0.0,
                                fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                                reason="noob_externally_sold",
                            )
                            try:
                                self.analytics.record_trade(
                                    token_id=token_id, asset=pos.asset, direction=pos.direction,
                                    entry_price=pos.entry_price, exit_price=pos.entry_price,
                                    stake=pos.stake, shares=pos.shares,
                                    entry_fill=_noob_meta.get("entry_fill"), exit_fills=[],
                                    exit_reason="NOOB_EXTERNALLY_SOLD", signal=_noob_sig,
                                    ts_open=_noob_meta.get("ts_open", pos.open_ts), ts_close=now_ts,
                                    capital_before=self.risk.bankroll.capital - _pnl,
                                    heat_check_active=_noob_meta.get("heat_check", False),
                                    consecutive_wins=_noob_meta.get("consecutive_wins", 0),
                                    net_pnl_actual=_pnl,
                                    market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                                    is_live=not CONFIG.dry_run,
                                    signal_source=_noob_meta.get("signal_source", "SNIPER"),
                                    window_size_s=_noob_meta.get("window_size_s") or pos.window_seconds or 0,
                                )
                            except Exception as _ne:
                                logger.error("record_trade NOOB_EXTERNALLY_SOLD failed: %s", _ne)
                    elif token_id not in self._exit_in_progress:
                        self._exit_in_progress.add(token_id)
                        try:
                            await self._exit_position(token_id, pos.entry_price, "EXIT_WINDOW_END_NOOB")
                        finally:
                            self._exit_in_progress.discard(token_id)
                continue
            current_price = ob.bids[0][0] if len(ob.bids) > 0 else ob.mid

            # Guard: corrupt/zero entry_price would cause division-by-zero in
            # move_pct and incorrect SL/TP comparisons. Skip rather than act on garbage.
            if not pos.entry_price or pos.entry_price <= 0:
                logger.error(
                    "GUARD: %s entry_price=%.6f — skipping exit check (corrupt state)",
                    token_id[:12], pos.entry_price,
                )
                continue

            # ── Position status log every 5s ─────────────────────────────────
            now = time.time()
            if now - self._pos_log_ts.get(token_id, 0) >= 5.0:
                self._pos_log_ts[token_id] = now
                held = now - pos.open_ts
                move_pct = (current_price - pos.entry_price) / pos.entry_price * 100
                unreal_pnl = (current_price - pos.entry_price) * pos.remaining_shares
                win_str = "+" if unreal_pnl >= 0 else "-"
                win_emoji = "▲" if unreal_pnl >= 0 else "▼"
                remaining_sec = max(0, pos.window_end_ts - now) if pos.window_end_ts > 0 else 0
                logger.info(
                    "POSITION %s %s %s | entry=%.4f curr=%.4f move=%+.1f%% | "
                    "PnL=%s$%.3f | TP=%.4f SL=%.4f | hold=%ds%s",
                    win_emoji, pos.asset, pos.direction.name,
                    pos.entry_price, current_price, move_pct,
                    win_str, abs(unreal_pnl),
                    pos.tp, pos.sl, int(held),
                    f" | window={remaining_sec:.0f}s" if remaining_sec > 0 else "",
                )

            # ── Post-entry path snapshots (T+30s, T+60s) ─────────────────────
            # Captured once per threshold — used by path classifier at close.
            # Diagnostic only: no entry/exit logic reads these.
            _held_for_snap = now - pos.open_ts
            _snaps = self._entry_snaps.setdefault(token_id, {})
            if 30 not in _snaps and _held_for_snap >= 30:
                _snaps[30] = current_price
            if 60 not in _snaps and _held_for_snap >= 60:
                _snaps[60] = current_price

            # ── BOND: time-based exit (bypasses normal TP/SL logic) ──────────
            if pos.is_bond and pos.window_end_ts > 0:
                bond_remaining = max(0.0, pos.window_end_ts - now)
                bond_move = (current_price - pos.entry_price) / pos.entry_price

                # ── Entry regime classification for this position ─────────────
                _entry_meta_b  = self._open_meta.get(token_id, {})
                _entry_sig_b   = _entry_meta_b.get("signal")
                _entry_edge_b  = getattr(_entry_sig_b, "edge", 0.0) if _entry_sig_b else 0.0
                _is_impulse_pos = bool(pos.bond_entry_class and pos.bond_entry_class.startswith("IMPULSE"))
                _is_extreme_pos = _entry_edge_b >= 0.10
                # Peak move tracker — update every scan for trailing stop
                if bond_move > self._peak_bond_move.get(token_id, -999.0):
                    self._peak_bond_move[token_id] = bond_move
                _peak_move = self._peak_bond_move.get(token_id, 0.0)

                # ── Position snapshot (30s edge/delta drift for open positions) ─
                _pos_drift = None   # edge_drift: positive = edge expanding (good)
                _pos_accel = None   # delta_accel: positive = momentum building
                _ext_pos = self._last_ext_signals.get(pos.asset)
                if _ext_pos and _ext_pos.spot_price:
                    _is_15m_pos_snap = pos.window_seconds >= 900
                    _ref_pos = ((_ext_pos.spot_window_open_15m if _is_15m_pos_snap else _ext_pos.spot_window_open_5m) or 0.0)
                    if _ref_pos > 0:
                        _delta_pos = (_ext_pos.spot_price - _ref_pos) / _ref_pos * 100
                        _elap_pos  = max(0.01, 1.0 - bond_remaining / pos.window_seconds)
                        _fv_pos    = 1.0 / (1.0 + math.exp(-8.0 * abs(_delta_pos) * min(4.0, 1.0 / max(0.05, 1.0 - _elap_pos) ** 0.5)))
                        _edge_pos  = _fv_pos - current_price
                        _snaps_pos = self._bond_snapshots.setdefault(token_id, deque())
                        _snaps_pos.append((now, _delta_pos, _edge_pos))
                        while _snaps_pos and now - _snaps_pos[0][0] > 60.0:
                            _snaps_pos.popleft()
                        _ref30_pos = next((s for s in _snaps_pos if 25.0 <= now - s[0] <= 35.0), None)
                        if _ref30_pos:
                            _pos_drift = _edge_pos  - _ref30_pos[2]
                            _pos_accel = _delta_pos - _ref30_pos[1]

                _wdelta_now = 0.0  # updated inside DIR_REVERSAL block when ext signal available

                # ── Entry-relative reversal guard (5m + 15m) ─────────────────
                # Measures reversal from entry-time spot, not window_open.
                # Old: window_open ref required +0.20% total reversal for -0.10%
                #   entry (spot must cross zero AND another 0.10%) — missed fast
                #   collapses where token hits $0 with only +0.10% reversal.
                # New: fires at 0.07% from entry spot — catches the first real
                #   sign of failure before token price collapses.
                # Dead zone: final 30s (TIME_EXIT handles cleanly).
                if True:
                    _ext_now = self._last_ext_signals.get(pos.asset)
                    if _ext_now and _ext_now.spot_price and bond_remaining > 30:
                        _is_15m_pos = pos.window_seconds >= 900
                        _entry_spot = pos.binance_price_at_entry
                        if _entry_spot > 0:
                            _wdelta_now = (_ext_now.spot_price - _entry_spot) / _entry_spot * 100
                        else:
                            # Fallback to window_open if entry spot not stored
                            _wref = ((_ext_now.spot_window_open_15m if _is_15m_pos else _ext_now.spot_window_open_5m) or 0.0)
                            _wdelta_now = (_ext_now.spot_price - _wref) / _wref * 100 if _wref > 0 else 0.0
                        if _entry_spot > 0 or True:
                            _REV_THRESH = 0.05
                            _wdelta_reversed = (
                                (pos.bond_outcome_direction == "down" and _wdelta_now >= _REV_THRESH) or
                                (pos.bond_outcome_direction == "up"   and _wdelta_now <= -_REV_THRESH)
                            )
                            if _wdelta_reversed:
                                _held_s = now - pos.open_ts
                                if _held_s < 25.0:
                                    # Minimum-hold gate: no non-HARD_SL exits before 25s.
                                    # Gives trades time to develop before evaluating reversal.
                                    pass
                                else:
                                    self._dir_rev_count[token_id] = self._dir_rev_count.get(token_id, 0) + 1
                                    logger.debug(
                                        "BOND_DIR_REV_TRACK %s/%s wdelta=%+.3f%% (thresh=%.2f%%) count=%d/2 move=%+.1f%% held=%.0fs",
                                        pos.asset, pos.bond_outcome_direction,
                                        _wdelta_now, _REV_THRESH,
                                        self._dir_rev_count[token_id], bond_move * 100, _held_s,
                                    )
                                    if self._dir_rev_count.get(token_id, 0) >= 2:
                                        # Structural filter: don't fire into expanding edge
                                        # (pullback in strong edge env ≠ reversal).
                                        _rev_edge_ok = _pos_drift is None or _pos_drift <= 0
                                        _rev_accel_ok = _pos_accel is None or _pos_accel < 0
                                        if not (_rev_edge_ok and _rev_accel_ok):
                                            logger.debug(
                                                "BOND_DIR_REV_SUPPRESSED %s/%s — edge expanding drift=%s accel=%s",
                                                pos.asset, pos.bond_outcome_direction,
                                                f"{_pos_drift:+.4f}" if _pos_drift is not None else "—",
                                                f"{_pos_accel:+.4f}" if _pos_accel is not None else "—",
                                            )
                                            self._dir_rev_count.pop(token_id, None)
                                        elif token_id not in self._exit_in_progress:
                                            self._exit_in_progress.add(token_id)
                                            logger.warning(
                                                "BOND_DIR_REVERSAL %s/%s %s | spot_rev=%+.3f%% ≥ %.2f%% from entry "
                                                "confirmed 2 scans (no recovery) | entry_spot=%.4f curr_spot=%.4f | "
                                                "ep=%.4f curr=%.4f | rem=%.0fs",
                                                pos.asset, pos.bond_outcome_direction,
                                                "15m" if _is_15m_pos else "5m",
                                                _wdelta_now, _REV_THRESH,
                                                _entry_spot, _ext_now.spot_price,
                                                pos.entry_price, current_price, bond_remaining,
                                            )
                                            try:
                                                await self._exit_position(token_id, current_price, "BOND_DIR_REVERSAL")
                                            finally:
                                                self._exit_in_progress.discard(token_id)
                                                self._dir_rev_count.pop(token_id, None)
                                            continue
                            else:
                                # Recovery detected — reset immediately (no partial credit)
                                self._dir_rev_count.pop(token_id, None)
                                logger.debug(
                                    "BOND_REV_OK %s/%s spot_rev=%+.3f%% (recovered within next scan — count reset)",
                                    pos.asset, pos.bond_outcome_direction, _wdelta_now, _REV_THRESH,
                                )
                else:
                    # 5m: no reversal guard — clear any stale count from prior position
                    self._dir_rev_count.pop(token_id, None)

                # ── T+Xs stall exit (one-shot, dynamic delay) ────────────────
                # Fires if all three conditions hold simultaneously:
                #   1. bond_move < +3%           — token hasn't moved meaningfully
                #   2. delta_now ≤ delta_entry   — window momentum not improved
                #   3. velocity not increasing   — spot not moving toward thesis
                # Delay scales with edge + delta: high edge / weak delta = more
                # time allowed before calling it a stall.
                _hold_s = now - pos.open_ts
                if (token_id not in self._stall_checked
                        and token_id not in self._exit_in_progress):
                    _sig_stall = self._open_meta.get(token_id, {}).get("signal")
                    _entry_edge_s  = getattr(_sig_stall, "edge",      0.05) if _sig_stall else 0.05
                    _entry_delta_s = abs(getattr(_sig_stall, "delta_pct", 0.09)) if _sig_stall else 0.09
                    # Patient trade: high edge + confirmed delta → eligible for adaptive delay.
                    # Delta gates eligibility only — does NOT modulate time directly.
                    _is_patient    = _entry_edge_s >= 0.05 and _entry_delta_s >= 0.08
                    _edge_bonus    = max(0.0, (_entry_edge_s - 0.04) * 1000) if _is_patient else 0.0
                    _delta_factor  = 1.15 if _entry_delta_s >= 0.11 else (0.85 if _entry_delta_s < 0.09 else 1.0)
                    _base_delay    = 30.0 + _edge_bonus
                    _stall_delay   = min(75.0, _base_delay * _delta_factor) if _is_patient else 30.0
                    if _is_extreme_pos:
                        _stall_delay = 20.0  # EXTREME: no patience, quick stall detection
                    elif _is_impulse_pos:
                        _stall_delay = 15.0  # IMPULSE: stall faster (velocity thesis or nothing)
                    # Minimum-hold gate: no non-HARD_SL exits before 25s.
                    _stall_delay = max(_stall_delay, 25.0)
                    if _hold_s >= _stall_delay:
                        self._stall_checked.add(token_id)
                        _ext_stall = self._last_ext_signals.get(pos.asset)
                        if _ext_stall and _ext_stall.spot_price:
                            _delta_entry = getattr(_sig_stall, "delta_pct", 0.0) if _sig_stall else 0.0
                            _is_15m_st = pos.window_seconds >= 900
                            _wref_st = ((_ext_stall.spot_window_open_15m if _is_15m_st else _ext_stall.spot_window_open_5m) or 0.0)
                            _delta_now_st = (_ext_stall.spot_price - _wref_st) / _wref_st * 100 if _wref_st > 0 else _delta_entry
                            _dir_sign = 1.0 if pos.bond_outcome_direction == "up" else -1.0
                            _delta_not_improving = (_delta_now_st * _dir_sign) <= (_delta_entry * _dir_sign)
                            _vel_not_increasing  = (_wdelta_now * _dir_sign) <= 0.0
                            if bond_move < 0.03 and _delta_not_improving and _vel_not_increasing:
                                self._exit_in_progress.add(token_id)
                                logger.info(
                                    "BOND_STALL %s/%s | T+%.0fs (delay=%.0fs edge=%.3f patient=%s) "
                                    "move=%+.1f%% delta_now=%+.3f%% delta_entry=%+.3f%% wdelta=%+.3f%%",
                                    pos.asset, pos.direction.name, _hold_s, _stall_delay,
                                    _entry_edge_s, _is_patient,
                                    bond_move * 100, _delta_now_st, _delta_entry, _wdelta_now,
                                )
                                try:
                                    await self._exit_position(token_id, current_price, "BOND_STALL")
                                finally:
                                    self._exit_in_progress.discard(token_id)
                                continue

                # ── Progress exit: trade used >60% of available time ──────────
                # Normalises time to entry: max_hold = (1 - elap_entry) * 0.60 * window_s
                # Late entries get proportionally less absolute time — not punished early.
                _sig_meta = self._open_meta.get(token_id, {}).get("signal")
                _elap_entry = getattr(_sig_meta, "elapsed_pct", None) if _sig_meta else None
                if _elap_entry is not None and token_id not in self._exit_in_progress:
                    _avail_s   = (1.0 - _elap_entry) * pos.window_seconds
                    _max_hold  = _avail_s * 0.60
                    if _is_extreme_pos:
                        _max_hold = min(_max_hold, 40.0)
                    elif _is_impulse_pos:
                        _max_hold = min(_max_hold, 30.0)
                    _hold_time = now - pos.open_ts
                    # Minimum-hold gate: no non-HARD_SL exits before 25s.
                    if _hold_time > _max_hold and _hold_time >= 25.0:
                        # Only exit if decay detected: both edge and momentum fading.
                        # If trend still alive (drift≥0 OR accel≥0), hold.
                        _decay = (_pos_drift is None) or (_pos_drift < 0 and _pos_accel < 0)
                        if _decay:
                            self._exit_in_progress.add(token_id)
                            logger.info(
                                "BOND_PROGRESS_EXIT %s/%s | held=%.0fs max=%.0fs "
                                "drift=%s accel=%s price=%.4f entry=%.4f",
                                pos.asset, pos.direction.name,
                                _hold_time, _max_hold,
                                f"{_pos_drift:+.4f}" if _pos_drift is not None else "—",
                                f"{_pos_accel:+.4f}" if _pos_accel is not None else "—",
                                current_price, pos.entry_price,
                            )
                            try:
                                await self._exit_position(token_id, current_price, "BOND_PROGRESS_EXIT")
                            finally:
                                self._exit_in_progress.discard(token_id)
                            continue

                # ── BOND token price stop-loss (75% drawdown, 7s confirmation) ─
                # Fires only when price is BELOW entry (never exits profitable)
                # AND stays below entry*0.80 for 7 consecutive scans (~7s).
                # Filters manufactured wicks that dip and recover quickly.
                _held_s = now - pos.open_ts
                if _held_s >= 3.0 and token_id not in self._exit_in_progress:
                    if current_price < pos.entry_price and current_price < pos.entry_price * 0.25:
                        self._sl_below_count[token_id] = self._sl_below_count.get(token_id, 0) + 1
                        logger.debug(
                            "BOND_SL_BELOW %s/%s curr=%.4f (%.1f%%) count=%d/7",
                            pos.asset, pos.direction.name, current_price,
                            (current_price - pos.entry_price) / pos.entry_price * 100,
                            self._sl_below_count[token_id],
                        )
                        if self._sl_below_count[token_id] >= 7:
                            self._exit_in_progress.add(token_id)
                            logger.warning(
                                "BOND_PRICE_SL %s/%s | curr=%.4f drawdown=%.1f%% | held=%.0fs rem=%.0fs (7s confirmed)",
                                pos.asset, pos.direction.name, current_price,
                                (current_price - pos.entry_price) / pos.entry_price * 100,
                                _held_s, bond_remaining,
                            )
                            try:
                                await self._exit_position(token_id, current_price, "BOND_PRICE_SL")
                            finally:
                                self._exit_in_progress.discard(token_id)
                                self._sl_below_count.pop(token_id, None)
                                self._stall_checked.discard(token_id)
                            continue
                    else:
                        if self._sl_below_count.pop(token_id, 0) > 0:
                            logger.debug(
                                "BOND_SL_RESET %s/%s — price recovered to %.4f",
                                pos.asset, pos.direction.name, current_price,
                            )


                # ── IMPULSE / EXTREME fast-fail and velocity-decay exits ───────
                if token_id not in self._exit_in_progress:
                    _vel_now_ff, _vel_age_ff = self.feed.get_velocity_5s(pos.asset)
                    _dir_sign_ff = 1.0 if pos.bond_outcome_direction == "up" else -1.0
                    _vel_aligned_ff = (_vel_now_ff * _dir_sign_ff) if _vel_age_ff < 999.0 else 0.0

                    # IMPULSE: velocity dropped below threshold → thesis failed
                    # Minimum-hold gate: no non-HARD_SL exits before 25s.
                    if (_is_impulse_pos
                            and 25.0 <= _held_s <= 35.0
                            and _vel_age_ff < 999.0
                            and abs(_vel_aligned_ff) < 0.01):
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            "BOND_IMPULSE_VDECAY %s/%s | vel=%.4f%% < 0.01%% at %.0fs — impulse thesis gone",
                            pos.asset, pos.direction.name, _vel_now_ff, _held_s,
                        )
                        try:
                            await self._exit_position(token_id, current_price, "BOND_IMPULSE_FAIL")
                        finally:
                            self._exit_in_progress.discard(token_id)
                        continue

                    # IMPULSE: no profit → cut (minimum-hold gate: 25s)
                    if (_is_impulse_pos
                            and _held_s >= 25.0
                            and bond_move <= 0.0):
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            "BOND_IMPULSE_FAIL %s/%s | move=%+.1f%% at %.0fs — no progress",
                            pos.asset, pos.direction.name, bond_move * 100, _held_s,
                        )
                        try:
                            await self._exit_position(token_id, current_price, "BOND_IMPULSE_FAIL")
                        finally:
                            self._exit_in_progress.discard(token_id)
                        continue

                    # EXTREME EDGE: no profit → cut (minimum-hold gate: 25s)
                    if (_is_extreme_pos
                            and _held_s >= 25.0
                            and bond_move <= 0.0):
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            "BOND_EXTREME_FAIL %s/%s | edge=%.4f move=%+.1f%% at %.0fs — no profit",
                            pos.asset, pos.direction.name, _entry_edge_b, bond_move * 100, _held_s,
                        )
                        try:
                            await self._exit_position(token_id, current_price, "BOND_EXTREME_FAIL")
                        finally:
                            self._exit_in_progress.discard(token_id)
                        continue

                    # Global early loss: any entry type, pnl <= 0 after 30s
                    if (not _is_impulse_pos        # IMPULSE handled above
                            and _held_s >= 30.0
                            and bond_move <= 0.0):
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            "BOND_EARLY_LOSS %s/%s | move=%+.1f%% at %.0fs — cut loser",
                            pos.asset, pos.direction.name, bond_move * 100, _held_s,
                        )
                        try:
                            await self._exit_position(token_id, current_price, "BOND_EARLY_LOSS")
                        finally:
                            self._exit_in_progress.discard(token_id)
                        continue

                # ── Adaptive SL envelope (time-decaying, state-gated) ─────────
                # Tolerance expands over time so normal mid-trade dips aren't cut.
                # All exits require structural degradation confirmation except the
                # catastrophic hard stop.
                #
                # Envelope: starts at -5% (t=0), widens by 0.2% per 10s, caps at -18%
                #   t=0s  → -5%    t=20s → -9%    t=40s → -13%
                #   t=10s → -7%    t=30s → -11%   t=65s → -18% (cap)
                #
                # Structural degradation (_degraded):
                #   When 30s history available: delta_accel<0 AND edge_drift<0 AND vel≤0
                #   When history unavailable (hold<25s): velocity-only (vel≤0)
                #
                # Catastrophic: -25% no state required — pure disaster cut.
                if token_id not in self._exit_in_progress:
                    _vel_cl, _vel_age_cl = self.feed.get_velocity_5s(pos.asset)
                    _dir_sign_cl = 1.0 if pos.bond_outcome_direction == "up" else -1.0
                    _vel_aligned_cl = (_vel_cl * _dir_sign_cl) if _vel_age_cl < 999.0 else 0.0
                    _vel_neg = _vel_aligned_cl <= 0.0

                    # Degradation check: full 3-signal when history available, vel-only otherwise
                    if _pos_drift is not None and _pos_accel is not None:
                        _degraded = _pos_accel < 0 and _pos_drift < 0 and _vel_neg
                    else:
                        _degraded = _vel_neg  # no 30s history yet — velocity is sole signal

                    # Smooth envelope: -(0.05 + 0.002*t) capped at -0.18
                    _sl_env = -(0.05 + min(0.002 * _held_s, 0.13))
                    # _sl_env at: t=0→-5%, t=10→-7%, t=20→-9%, t=30→-11%, t=65→-18%

                    _exit_label_cl = ""
                    if bond_move <= -0.25:
                        # Catastrophic: no state confirmation needed
                        _exit_label_cl = f"catastrophic/move≤-25%"
                    elif bond_move <= _sl_env and _degraded:
                        _exit_label_cl = (
                            f"adaptive/move≤{_sl_env:.1%}"
                            f"+{'full' if _pos_drift is not None else 'vel'}_degraded"
                        )

                    if _exit_label_cl:
                        self._exit_in_progress.add(token_id)
                        logger.warning(
                            "BOND_HARD_SL %s/%s | move=%+.1f%% held=%.0fs [%s] | "
                            "envelope=%.1f%% vel=%+.4f%% drift=%s accel=%s | entry=%.4f curr=%.4f",
                            pos.asset, pos.direction.name,
                            bond_move * 100, _held_s, _exit_label_cl,
                            _sl_env * 100, _vel_aligned_cl,
                            f"{_pos_drift:+.4f}" if _pos_drift is not None else "—",
                            f"{_pos_accel:+.4f}" if _pos_accel is not None else "—",
                            pos.entry_price, current_price,
                        )
                        try:
                            await self._exit_position(token_id, current_price, "BOND_HARD_SL")
                        finally:
                            self._exit_in_progress.discard(token_id)
                            self._sl_below_count.pop(token_id, None)
                            self._peak_bond_move.pop(token_id, None)
                        continue

                # ── Winner trailing stop (protect expanded profits) ────────────
                # Activates once peak move ≥ 8% and held ≥ 25s. Exits if giveback > 50%.
                # Minimum-hold gate: lets trades develop before trailing kicks in.
                if (_peak_move >= 0.08
                        and _held_s >= 25.0
                        and bond_move < _peak_move * 0.50
                        and token_id not in self._exit_in_progress):
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        "BOND_TRAIL_SL %s/%s | peak=%+.1f%% curr=%+.1f%% giveback=%.0f%% > 50%%",
                        pos.asset, pos.direction.name,
                        _peak_move * 100, bond_move * 100,
                        (1.0 - bond_move / _peak_move) * 100 if _peak_move > 0 else 0,
                    )
                    try:
                        await self._exit_position(token_id, current_price, "BOND_TRAIL_SL")
                    finally:
                        self._exit_in_progress.discard(token_id)
                        self._peak_bond_move.pop(token_id, None)
                    continue

                # ── BOND exhaustion exit (dynamic continuation vs decay) ─────
                # Fires when expected remaining upside < risk of giving back gains.
                # Requires 30s of position history, ≥8% profit, and ≥25s held.
                # DIR_REVERSAL and STALL handle their own regimes — this only fires
                # when the trend is still nominally valid but momentum is fading.
                if (bond_move >= 0.08
                        and _held_s >= 25.0
                        and _pos_drift is not None
                        and token_id not in self._exit_in_progress
                        and self._dir_rev_count.get(token_id, 0) < 2):
                    _dir_sign_ex = 1.0 if pos.bond_outcome_direction == "up" else -1.0

                    # continuation_score [0,1]: how likely is further gain?
                    _drift_c    = min(1.0, max(0.0, _pos_drift / 0.05 + 0.5))
                    _accel_c    = min(1.0, max(0.0, _pos_accel / 0.12 + 0.5))
                    _vel_c      = 1.0 if (_wdelta_now * _dir_sign_ex) >= 0.02 else 0.0
                    _cont_score = _drift_c * 0.45 + _accel_c * 0.35 + _vel_c * 0.20

                    # decay_pressure [0,1]: how likely is giving back gains?
                    _time_frac_ex = 1.0 - bond_remaining / max(1.0, pos.window_seconds)
                    _time_p_ex    = min(1.0, _time_frac_ex ** 2)
                    _ob_ex        = self.feed.get_order_book(token_id)
                    _bid_ex       = _ob_ex.bids[0][0] if (_ob_ex and _ob_ex.bids) else 0.0
                    _ask_ex       = _ob_ex.asks[0][0] if (_ob_ex and _ob_ex.asks) else 0.0
                    _spread_ex    = (_ask_ex - _bid_ex) if _ask_ex > _bid_ex else 0.05
                    _spread_p_ex  = min(1.0, _spread_ex / 0.06)
                    _decay_score  = _time_p_ex * 0.65 + _spread_p_ex * 0.35

                    logger.debug(
                        "BOND_EXHAUST_CHK %s/%s | cont=%.3f (drift=%.3f accel=%.3f vel=%d) "
                        "decay=%.3f (time=%.3f spread=%.3f) move=%+.1f%% rem=%.0fs",
                        pos.asset, pos.direction.name,
                        _cont_score, _drift_c, _accel_c, int(_vel_c),
                        _decay_score, _time_p_ex, _spread_p_ex,
                        bond_move * 100, bond_remaining,
                    )
                    if _cont_score < _decay_score:
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            "BOND_EXHAUSTION_EXIT %s/%s | cont=%.3f < decay=%.3f "
                            "move=%+.1f%% drift=%+.4f accel=%+.4f vel_ok=%s rem=%.0fs",
                            pos.asset, pos.direction.name,
                            _cont_score, _decay_score, bond_move * 100,
                            _pos_drift, _pos_accel, bool(_vel_c), bond_remaining,
                        )
                        try:
                            await self._exit_position(token_id, current_price, "BOND_EXHAUSTION_EXIT")
                        finally:
                            self._exit_in_progress.discard(token_id)
                        continue

                # $0.95 at any point — token at 95¢ with time remaining is high
                #   confidence; a reversal back to 80¢ costs ~$1.90 vs locking $1.72.
                # $0.99 in last 20s only — near-certain resolution, capture ~$0.49
                #   extra vs $0.95 TP with virtually no reversal risk at T-20s.
                _BOND_TP_EARLY  = 0.95   # fires any time during hold
                _BOND_TP_LATE   = 0.99   # fires only in last 20s
                _bond_tp_reason = None
                if current_price >= _BOND_TP_LATE and bond_remaining <= 20.0:
                    _bond_tp_reason = f"BOND_TP_99 curr={current_price:.4f} rem={bond_remaining:.0f}s"
                elif current_price >= _BOND_TP_EARLY:
                    _bond_tp_reason = f"BOND_TP_95 curr={current_price:.4f} rem={bond_remaining:.0f}s"
                if _bond_tp_reason and token_id not in self._exit_in_progress:
                    self._exit_in_progress.add(token_id)
                    logger.info(
                        "BOND_TP %s/%s | %s | entry=%.4f move=%+.1f%%",
                        pos.asset, pos.direction.name, _bond_tp_reason,
                        pos.entry_price, bond_move * 100,
                    )
                    try:
                        await self._exit_position(token_id, current_price, _bond_tp_reason.split()[0])
                    finally:
                        self._exit_in_progress.discard(token_id)
                    continue

                # Time exit: sell at bond_exit_sec before window close
                if bond_remaining <= pos.bond_exit_sec:
                    if token_id not in self._exit_in_progress:
                        self._exit_in_progress.add(token_id)
                        logger.info(
                            "BOND_TIME_EXIT %s/%s | remaining=%.0fs ≤ exit_at=%ds | "
                            "entry=%.4f curr=%.4f move=%+.1f%%",
                            pos.asset, pos.direction.name, bond_remaining,
                            pos.bond_exit_sec, pos.entry_price, current_price,
                            bond_move * 100,
                        )
                        try:
                            await self._exit_position(token_id, current_price, "BOND_TIME_EXIT")
                        finally:
                            self._exit_in_progress.discard(token_id)
                    continue

                # Still inside holding period — skip normal TP/SL
                continue

            _pos_ext = self._last_ext_signals.get(pos.asset)
            _binance_spot = self.feed._spot_price.get(pos.asset.upper(), 0.0)
            decision = self.risk.check_exit_conditions(
                token_id, current_price, ext=_pos_ext, binance_spot=_binance_spot
            )

            if decision is None:
                if pos.window_end_ts > 0:
                    time_held = now - pos.open_ts
                    remaining = max(0.0, pos.window_end_ts - now)
                    move_pct = (current_price - pos.entry_price) / pos.entry_price

                    # ── LLM SL-breach override: wick vs genuine reversal ──────
                    # When the SL timer is running but hasn't expired, ask Claude once.
                    # T00042: 0.59→0.44 in 25s (bot-painted stop), price recovered 0.78.
                    # Mechanical timer is blind to this. LLM sees VPIN/spot context.
                    # Guard: skip LLM query on weak entries (edge < 0.06, elapsed < 30%) —
                    # LLM has no signal advantage at 10-22s into a 5m window; let the
                    # mechanical 12s wick timer run without LLM interference. T00090.
                    _meta = self._open_meta.get(token_id, {})
                    _sig = _meta.get("signal")
                    _entry_edge = getattr(_sig, "edge", 1.0) if _sig else 1.0
                    _entry_elapsed = getattr(_sig, "elapsed_pct", 1.0) if _sig else 1.0
                    _weak_entry = _entry_edge < 0.06 and _entry_elapsed < 0.40
                    # Note: if _weak_entry=True, sl_breach_ts stays set → in_uncertain_zone
                    # below cannot fire (guards on sl_breach_ts == 0.0). Intentional: weak
                    # entries in breach are handled by mechanical wick timer only, not LLM.
                    if pos.sl_breach_ts > 0 and not pos.sl_breach_llm_queried and not _weak_entry:
                        pos.sl_breach_llm_queried = True
                        # Bypass stale cache — fresh read on breach
                        self.macro_engine._exit_advice_cache.pop(token_id, None)
                        ext = self._last_ext_signals.get(pos.asset)
                        action, tighten_sl, conf, adv_reason = await self.macro_engine.advise_exit(
                            token_id=token_id,
                            asset=pos.asset,
                            direction=pos.direction.name,
                            entry_price=pos.entry_price,
                            current_price=current_price,
                            time_held_s=time_held,
                            time_remaining_s=remaining,
                            stake=pos.stake,
                            vpin_score=ext.vpin_score if ext else None,
                            vpin_direction=ext.vpin_direction if ext else None,
                            spot_price=ext.spot_price if ext else None,
                            spot_change_pct=ext.spot_momentum_5m if ext else None,
                            breach_price=pos.sl_breach_price if pos.sl_breach_price > 0 else None,
                        )
                        if action == "HOLD" and conf >= 0.65:
                            # LLM says wick — reset breach timer, stay in
                            pos.sl_breach_ts = 0.0
                            pos.sl_breach_llm_queried = False  # allow re-query if price dips again
                            logger.info(
                                "LLM WICK OVERRIDE %s/%s (conf=%.2f move=%+.1f%%) — SL breach reset | %s",
                                pos.asset, pos.direction.name, conf, move_pct * 100, adv_reason,
                            )
                        elif action == "EXIT_NOW" and conf >= 0.65:
                            # LLM confirms reversal — but don't bypass wick timer entirely.
                            # T00090: BTC/YES wicked to -27% at 22s, LLM said EXIT_NOW, price
                            # then recovered to +40%. The LLM has almost no signal at 22s.
                            # Fix: LLM vote REDUCES wick confirmation window (12s → 4s for 5m,
                            # 20s → 8s for 15m), but doesn't bypass it. If price recovers
                            # above threshold before the reduced timer expires, the position
                            # is saved — the wick cleared before LLM could do damage.
                            is_5m_pos = pos.window_seconds < 900
                            reduced_confirm = 4 if is_5m_pos else 8
                            breach_age = now - pos.sl_breach_ts
                            if breach_age >= reduced_confirm:
                                logger.info(
                                    "LLM CONFIRMS EXIT %s/%s (conf=%.2f move=%+.1f%% held %.0fs) "
                                    "— breach age %.0fs ≥ %ds | %s",
                                    pos.asset, pos.direction.name, conf, move_pct * 100,
                                    time_held, breach_age, reduced_confirm, adv_reason,
                                )
                                await self._exit_position(token_id, current_price, "LLM_CONFIRMS_SL")
                                continue
                            else:
                                logger.info(
                                    "LLM EXIT_NOW %s/%s but breach only %.0fs old (need %ds) "
                                    "— waiting for wick to clear | %s",
                                    pos.asset, pos.direction.name, breach_age,
                                    reduced_confirm, adv_reason,
                                )
                        else:
                            logger.info(
                                "LLM SL CONSULT %s/%s → %s conf=%.2f — letting timer run | %s",
                                pos.asset, pos.direction.name, action, conf, adv_reason,
                            )

                    # ── LLM exit advisor: DISABLED — observational only ───────
                    # LLM_EXIT_NOW caused early exits at loss (T00153: -$0.894, T00157: -$0.648).
                    # Same pattern as entry veto: LLM hurts more than helps.
                    # Tracking recommendations vs outcomes for future validation.
                    is_15m_trade = pos.window_seconds >= 900
                    llm_min_hold = 180 if is_15m_trade else 15
                    in_uncertain_zone = (
                        time_held > llm_min_hold
                        and -0.35 < move_pct < 0.22
                        and remaining > 60
                        and pos.exit_stage.name == "NONE"
                        and pos.sl_breach_ts == 0.0  # breach handled above
                    )
                    if in_uncertain_zone:
                        ext = self._last_ext_signals.get(pos.asset)
                        action, tighten_sl, conf, adv_reason = await self.macro_engine.advise_exit(
                            token_id=token_id,
                            asset=pos.asset,
                            direction=pos.direction.name,
                            entry_price=pos.entry_price,
                            current_price=current_price,
                            time_held_s=time_held,
                            time_remaining_s=remaining,
                            stake=pos.stake,
                            vpin_score=ext.vpin_score if ext else None,
                            vpin_direction=ext.vpin_direction if ext else None,
                            spot_price=ext.spot_price if ext else None,
                            spot_change_pct=ext.spot_momentum_5m if ext else None,
                        )
                        if action == "EXIT_NOW":
                            logger.info(
                                "LLM WOULD-EXIT %s/%s (conf=%.2f move=%+.1f%%) — tracking only | %s",
                                pos.asset, pos.direction.name,
                                conf, move_pct * 100, adv_reason,
                            )
                        elif action == "TIGHTEN_STOP" and tighten_sl is not None:
                            logger.info(
                                "LLM WOULD-TIGHTEN %s/%s → -%.0f%% (conf=%.2f) — tracking only | %s",
                                pos.asset, pos.direction.name,
                                tighten_sl * 100, conf, adv_reason,
                            )

                    # ── LLM stage-2 advisor: DISABLED — observational only ───
                    # Same rationale as exit advisor above: tracking only, no stops tightened.
                    if (pos.exit_stage.name == "STAGE_1_DONE"
                            and time_held > 15
                            and 0.15 < move_pct < 0.45
                            and remaining > 60
                            and pos.sl_breach_ts == 0.0):
                        ext = self._last_ext_signals.get(pos.asset)
                        s2_action, s2_tighten, s2_conf, s2_reason = await self.macro_engine.advise_exit(
                            token_id=token_id,
                            asset=pos.asset,
                            direction=pos.direction.name,
                            entry_price=pos.entry_price,
                            current_price=current_price,
                            time_held_s=time_held,
                            time_remaining_s=remaining,
                            stake=pos.stake * 0.40,
                            vpin_score=ext.vpin_score if ext else None,
                            vpin_direction=ext.vpin_direction if ext else None,
                            spot_price=ext.spot_price if ext else None,
                            spot_change_pct=ext.spot_momentum_5m if ext else None,
                        )
                        logger.info(
                            "LLM STAGE2 WOULD-%s %s/%s (conf=%.2f move=%+.1f%%) — tracking only | %s",
                            s2_action, pos.asset, pos.direction.name,
                            s2_conf, move_pct * 100, s2_reason,
                        )
                continue

            if token_id in self._exit_in_progress:
                continue  # cascade already running for this token — skip to avoid concurrent sells
            if decision.partial:
                # Stage-1: sell 95 %, leave 5 % riding
                self._exit_in_progress.add(token_id)
                try:
                    await self._partial_exit(token_id, current_price, decision.reason)
                finally:
                    self._exit_in_progress.discard(token_id)
            else:
                self._exit_in_progress.add(token_id)
                try:
                    await self._exit_position(token_id, current_price, decision.reason)
                finally:
                    self._exit_in_progress.discard(token_id)

    # ── 5-second signal loop: scan for new entries ────────────────────────────

    async def _on_delta_spike(self, asset: str, delta_pct: float, spot_price: float) -> None:
        """
        Event-driven entry: fires immediately from Binance aggTrade when delta
        vs 5m window open crosses 0.03%. Bypasses the 5s signal sweep cycle.

        Flow: aggTrade tick → delta threshold → this callback → sniper.score()
              → risk.evaluate() → _enter_position() if approved.
        PM OB is served from the 1s REST cache — at most 1s stale, still 4s ahead
        of the sweep cycle. The sniper's own gates (lag, edge, elapsed) filter quality.
        """
        if not SNIPER_ENABLED:
            return
        now = time.time()
        # Hour gates removed — all UTC hours permitted.

        # Per-asset debounce — feeds.py debounces at 1.5s, this adds a session-level guard.
        # Timestamp set BEFORE the guard check to prevent two concurrent callbacks both
        # passing when they arrive within the same event loop tick.
        last = self._last_spike_ts.get(asset, 0)
        self._last_spike_ts[asset] = now
        if now - last < 1.5:
            return

        logger.info(
            "SPIKE %s | delta=%+.3f%% price=%.2f — immediate sniper eval",
            asset, delta_pct, spot_price,
        )

        ext = self._last_ext_signals.get(asset)
        if ext is None:
            # Fall back to a fresh fetch if not yet cached
            try:
                ext = await self.feed.fetch_external_signals(asset)
            except Exception as _e:
                logger.warning("SPIKE %s | ext signal fetch failed: %s — spike skipped", asset, _e)
                return
        if ext is None:
            return

        _queued_this_spike: set = set()  # condition dedup within this spike

        for token_id, token in list(self.feed.tokens.items()):
            if token.asset != asset or token.market_type != "updown":
                continue
            if token_id in self.risk.open_positions:
                continue
            # Pre-evaluate check: skip if asset is already locked by a concurrent
            # entry path (spike or scan loop). evaluate() has this check too, but
            # an early guard here prevents the evaluate() call entirely — cleaner
            # and eliminates any edge case where the lock state changes mid-loop.
            if asset in self.risk._pending_assets:
                logger.debug(
                    "SPIKE SKIP %s — asset already in _pending_assets (concurrent entry in progress)",
                    asset,
                )
                break  # no point checking other tokens for this asset
            if asset in self._pending_asset_entries:
                logger.debug(
                    "SPIKE SKIP %s — asset already in _pending_asset_entries",
                    asset,
                )
                break
            if token.window_end_ts > 0:
                remaining = token.window_end_ts - now
                if remaining < CONFIG.execution.no_trade_last_sec:
                    continue

            ob = self.feed.get_order_book(token_id)
            if ob is None:
                continue
            _ask = ob.asks[0][0] if ob.asks else ob.mid
            if _ask < 0.05 or _ask > 0.95:
                continue

            bars_5m = self.feed.get_bars_5m(token_id, n=30)
            sniper_sig = self.sniper.score(token, ob, ext, now=time.time())
            if sniper_sig is None:
                continue
            if sniper_sig.entry_price <= 0:
                continue

            # ── Velocity gate (event-driven path) ────────────────────────────
            # Mirrors the gate in _signal_loop. Without this, aggTrade-triggered
            # entries bypass velocity filtering entirely — confirmed root cause of
            # vel=+0.050% NO trade firing at 14:35 (VELOCITY_EXIT -$6.08).
            _vel_spike, _ = self.feed.get_velocity_5s(token.asset)
            _VEL_THRESHOLD_SPIKE = 0.001
            _vel_against_spike = (
                (token.side == "NO"  and _vel_spike >  _VEL_THRESHOLD_SPIKE) or
                (token.side == "YES" and _vel_spike < -_VEL_THRESHOLD_SPIKE)
            )
            if _vel_against_spike:
                logger.info(
                    "SPIKE VELOCITY_GATE %s/%s | vel=%+.4f%% against direction — skip",
                    token.asset, token.side, _vel_spike,
                )
                continue

            _cid = token.condition_id or ""
            if _cid and _cid in _queued_this_spike:
                continue

            tpsl = calculate_tp_sl(sniper_sig.entry_price, sniper_sig.direction, bars_5m, ob)
            decision = self.risk.evaluate(
                token_id, sniper_sig, tpsl,
                condition_id=_cid,
                window_end_ts=token.window_end_ts,
                asset=token.asset,
                market_type=token.market_type,
                cascade_discount=0.0,
                is_sniper=True,
                window_seconds=getattr(token, "window_seconds", 0),
            )

            if not decision.approved:
                logger.debug("SPIKE REJECTED %s/%s: %s", token.asset, token.side, decision.reason)
                continue

            if token_id in self._exit_in_progress:
                continue

            logger.info(
                "SPIKE ENTRY %s/%s | entry=%.4f edge=%.3f lag=%.0f%% | %s",
                token.asset, token.side,
                sniper_sig.entry_price, sniper_sig.edge,
                sniper_sig.lag_remaining_pct * 100,
                sniper_sig.reason,
            )

            if _cid:
                _queued_this_spike.add(_cid)

            asyncio.create_task(
                self._enter_position(token_id, token.asset, sniper_sig, tpsl, decision),
                name=f"spike_{asset}_{token.side}",
            )

    async def _refresh_ext_signals(self) -> None:
        """Fetch Binance ext signals for all tracked assets and cache in _last_ext_signals.
        Called every signal loop iteration regardless of SNIPER_ENABLED so BOND scanner
        always has delta data (BOND skip 'delta unavailable' when SNIPER disabled)."""
        ext_results = await asyncio.gather(
            *[self.feed.fetch_external_signals(a) for a in CONFIG.markets.tracked_assets],
            return_exceptions=True,
        )
        self._last_ext_signals = {
            asset: (r if not isinstance(r, Exception) else None)
            for asset, r in zip(CONFIG.markets.tracked_assets, ext_results)
        }

    async def _signal_loop(self) -> None:
        _consecutive_errors = 0
        _entries_blocked = False
        while self._running:
            try:
                await self.feed.poll_order_books()
                await self.feed.update_bars()
                await self._refresh_ext_signals()
                if _entries_blocked:
                    logger.info("Signal loop recovered — entries unblocked")
                    _entries_blocked = False
                _consecutive_errors = 0  # reset on success
                await self._scan_for_signals()
                await self._scan_bond_entries()
                await self._scan_reversal_candidates()
            except Exception as exc:
                _consecutive_errors += 1
                tb = traceback.format_exc()
                if _consecutive_errors > 3:
                    if not _entries_blocked:
                        logger.critical(
                            "Signal loop CRITICAL: %d consecutive errors — entries BLOCKED. "
                            "Last error: %s\n%s",
                            _consecutive_errors, exc, tb,
                        )
                        _entries_blocked = True
                    # Skip _scan_for_signals when data pipeline is broken
                else:
                    logger.error("Signal loop error: %s\n%s", exc, tb)
            await asyncio.sleep(CONFIG.markets.scan_interval)

    # ── High-probability bond scanner ────────────────────────────────────────

    async def _scan_bond_entries(self) -> None:
        """
        Bond strategy: buy high-probability tokens near window close, exit by time.

        15m windows: buy when ask ≥ 0.66 AND remaining ≤ 4 min, sell at T-30s.
        5m windows:  buy when ask ≥ 0.66 AND remaining ≤ 1.5 min, sell at T-20s.

        Edge: token at 0.70+ has already committed to an outcome. Capture final
        repricing walk to ~1.0 as window closes. Works in quiet/trending markets;
        prior losses were in high-volatility bearish conditions.
        """
        if not BOND_ENABLED:
            return
        now = time.time()
        _BOND_MIN_ASK = 0.57
        _BOND_MAX_ASK = 0.79

        for token_id, token in list(self.feed.tokens.items()):
            if token.market_type != "updown":
                continue
            if token.window_end_ts <= 0:
                continue
            if token_id in self.risk.open_positions:
                continue
            if token.asset in self.risk._pending_assets:
                continue
            if token.asset in self._pending_asset_entries:
                continue

            is_15m = getattr(token, "window_seconds", 0) >= 900
            is_5m  = 250 <= getattr(token, "window_seconds", 0) < 900

            remaining = token.window_end_ts - now

            if is_15m:
                continue  # 15m BOND disabled — 5m only until 15m edge re-validated
            elif is_5m:
                exit_sec = 10  # T-10s: OB_NOOB skip for BOND ensures precise timer fires cleanly
                if not (45 <= remaining <= 175):  # CORE 90–150s; EARLY >150s; LATE 45–90s
                    continue
            else:
                continue

            ob = self.feed.get_order_book(token_id)
            if ob is None:
                continue
            ask = ob.asks[0][0] if ob.asks else None
            if ask is None or ask < _BOND_MIN_ASK or ask > _BOND_MAX_ASK:
                logger.info("BOND SKIP %s/%s: ask=%s out of range [%.2f–%.2f]",
                            token.asset, token.side,
                            f"{ask:.4f}" if ask is not None else "None",
                            _BOND_MIN_ASK, _BOND_MAX_ASK)
                continue

            cid = getattr(token, "condition_id", "") or ""

            # Compute real window delta from cached ext signals.
            # If delta is unavailable we have no directional information — skip rather than
            # enter blind (delta=0 default gives fair_value=0.5, which is always negative
            # edge vs ask≥0.70 and caused the -0.301 edge entries like trade #78).
            _ext = getattr(self, "_last_ext_signals", {}).get(token.asset)
            _bond_delta = 0.0
            _delta_available = False
            if _ext and _ext.spot_price:
                _ref = (_ext.spot_window_open_15m if is_15m else _ext.spot_window_open_5m) or 0.0
                if _ref > 0:
                    _bond_delta = (_ext.spot_price - _ref) / _ref * 100
                    _delta_available = True
                else:
                    logger.info("BOND SKIP %s/%s: delta unavailable (ext exists but window_open ref=0)",
                                token.asset, token.side)
            else:
                logger.info("BOND SKIP %s/%s: delta unavailable (no ext signals cached, ext=%s)",
                            token.asset, token.side,
                            "None" if _ext is None else "no spot_price")
            if not _delta_available:
                continue
            _elapsed_pct = 1.0 - remaining / token.window_seconds
            if _elapsed_pct > 0.92:
                continue
            _bond_zone = "EARLY" if remaining > 150 else ("LATE" if remaining < 90 else "CORE")
            _token_dir = getattr(token, "outcome_direction", "up")

            # Directed delta gate: only enter a token when spot direction matches
            # outcome_direction. Without this, abs() would give high fair_value for
            # both sides and the bot enters the WRONG token when spot has reversed
            # mid-window (e.g. was DOWN, briefly ticked UP, DOWN-YES still at 0.72).
            # feeds.py OUTCOME_DIR logs confirm slug-suffix mapping is correct.
            # Direction match: sign alignment only — band gates handle minimums below.
            _dir_match = (
                (_token_dir == "down" and _bond_delta < 0) or
                (_token_dir == "up"   and _bond_delta > 0)
            )
            if not _dir_match:
                logger.debug(
                    "BOND SKIP %s/%s: delta=%+.3f%% direction mismatch odir=%s",
                    token.asset, token.side, _bond_delta, _token_dir,
                )
                continue

            _fair_value = 1.0 / (1.0 + math.exp(-8.0 * abs(_bond_delta) * min(4.0, 1.0 / max(0.05, 1.0 - _elapsed_pct) ** 0.5)))
            _edge = round(_fair_value - ask, 4)
            _asset_direction = 1 if _bond_delta >= 0 else -1

            # ── Velocity classification ───────────────────────────────────────
            # Must happen before band gates (band conditions depend on vel class).
            _VEL_BOND_THRESHOLD = 0.010
            _vel_now, _vel_age = self.feed.get_velocity_5s(token.asset)
            _vel_cold = (_vel_age >= 999.0)
            # INIT = measured velocity actively moving in trade direction.
            # Distinguishes fresh momentum entries from exhaustion/cold entries.
            _vel_init = (
                not _vel_cold and (
                    (_token_dir == "up"   and _vel_now >=  _VEL_BOND_THRESHOLD) or
                    (_token_dir == "down" and _vel_now <= -_VEL_BOND_THRESHOLD)
                )
            )
            _vel_label = (
                "INIT" if _vel_init
                else ("COLD" if _vel_cold else "CONT/EXH")
            )

            # ── 30s acceleration / drift snapshot ────────────────────────────
            _snaps = self._bond_snapshots.setdefault(token_id, deque())
            _snaps.append((now, _bond_delta, _edge))
            while _snaps and now - _snaps[0][0] > 60.0:
                _snaps.popleft()
            # Find snapshot closest to 30s ago (accept 25–35s window)
            _ref30 = next(
                (s for s in _snaps if 25.0 <= now - s[0] <= 35.0),
                None,
            )
            _delta_accel = (_bond_delta - _ref30[1]) if _ref30 else 0.0
            _edge_drift  = (_edge      - _ref30[2]) if _ref30 else 0.0
            _has_hist    = _ref30 is not None

            # ── Regime classification + entry filters ────────────────────────
            _abs_delta = abs(_bond_delta)
            _EDGE_DRIFT_CORE = 0.002

            # IMPULSE regime: velocity spike overrides accel/drift requirements.
            # Fires only in early window when the velocity IS the signal.
            _is_impulse = (
                not _vel_cold
                and abs(_vel_now) > 0.04
                and _elapsed_pct < 0.60
                and _edge > 0.035
            )

            if _is_impulse:
                _skip = _abs_delta < 0.05
                _skip_reason = (
                    f"IMPULSE needs delta≥0.05 | "
                    f"delta={_abs_delta:.3f}% vel={_vel_now:+.4f}% edge={_edge:.4f} elap={_elapsed_pct:.2f}"
                )
                _dzone = "IMPULSE"
            elif _bond_zone == "CORE":
                # Hard anchor: edge < 0.04 is non-compensable. Above this, score filters.
                if _edge < 0.04:
                    _skip = True
                    _skip_reason = f"CORE: edge={_edge:.4f} < 0.04 (hard floor)"
                else:
                    _drift_flag = 1.0 if (_has_hist and _edge_drift >= 0) or not _has_hist else 0.0
                    _accel_flag = 1.0 if (_has_hist and _delta_accel >= 0) or not _has_hist else 0.0
                    _edge_score = math.log(1.0 + _edge / 0.03)
                    _core_score = (
                        _edge_score                             * 0.40 +
                        min(1.0, _abs_delta / 0.13)            * 0.25 +
                        _drift_flag                            * 0.20 +
                        _accel_flag                            * 0.15
                    )
                    _skip = _core_score < 0.55
                    _skip_reason = (
                        f"CORE score={_core_score:.3f} (edge_s={_edge_score:.3f}×0.40 "
                        f"delta_s={min(1.0,_abs_delta/0.13):.2f}×0.25 "
                        f"drift={_drift_flag:.0f}×0.20 accel={_accel_flag:.0f}×0.15) | "
                        f"edge={_edge:.4f} delta={_abs_delta:.3f}% drift={_edge_drift:+.4f} accel={_delta_accel:+.4f}%"
                    )
                _dzone = "CORE"
            elif _bond_zone == "EARLY":
                _early_vel_ok = not _vel_cold and abs(_vel_now) >= 0.012
                _skip = (
                    (_abs_delta < 0.12 or _abs_delta > 0.13 or _edge < 0.05 or not _early_vel_ok) or
                    (_has_hist and not (_delta_accel > 0 or _edge_drift > 0))
                )
                _skip_reason = (
                    f"EARLY: delta={_abs_delta:.3f}% edge={_edge:.4f} "
                    f"vel={_vel_now:+.4f}% accel={_delta_accel:+.4f}% drift={_edge_drift:+.4f}"
                )
                _dzone = "EARLY"
            else:  # LATE (45–90s)
                _skip = (
                    (_abs_delta < 0.12 or _abs_delta > 0.13 or _edge < 0.06 or ask > 0.75) or
                    (_has_hist and _edge_drift < -0.005)
                )
                _skip_reason = (
                    f"LATE: delta={_abs_delta:.3f}% edge={_edge:.4f} "
                    f"ask={ask:.4f} drift={_edge_drift:+.4f}"
                )
                _dzone = "LATE"

            # Global edge floor: block any trade below 0.04 regardless of score
            if _edge < 0.04:
                _skip = True
                _skip_reason = f"edge={_edge:.4f} < 0.04 (global floor)"

            if _skip:
                logger.info("BOND SKIP %s/%s [%s]: %s", token.asset, token.side, _dzone, _skip_reason)
                continue

            # Build a minimal SniperSignal — reuses the existing entry machinery
            _wlabel = f"{token.window_seconds // 60}m"
            signal = SniperSignal(
                asset=token.asset,
                side=token.side,
                asset_direction=_asset_direction,
                delta_pct=round(_bond_delta, 4),
                fair_value=round(_fair_value, 4),
                token_ask=ask,
                edge=_edge,
                entry_price=ask,
                confidence=ask,
                composite=ask,
                direction=Direction.BUY_YES,
                fee_zone=FeeZone.EXTREME,
                elapsed_pct=_elapsed_pct,
                reason=f"BOND_{_wlabel}[{_dzone}/{_vel_label}] ask={ask:.3f} δ={_bond_delta:+.3f}% fv={_fair_value:.3f} rem={remaining:.0f}s exit@{exit_sec}s",
                quality_score=3,
                signal_source="BOND",
                is_bond=True,
                bond_exit_sec=exit_sec,
                bond_outcome_direction=_token_dir,
                bond_entry_class=f"{_dzone}/{_vel_label}",
            )

            tpsl = TPSLLevels(
                take_profit=min(0.99, round(ask + (1.0 - ask) * 0.90, 4)),
                stop_loss=max(0.01, round(ask * 0.80, 4)),
                tp_pct=round((1.0 - ask) / ask * 90, 1),
                sl_pct=20.0,
                risk_reward=1.5,
            )

            decision = self.risk.evaluate(
                token_id, signal, tpsl,
                condition_id=cid,
                window_end_ts=token.window_end_ts,
                asset=token.asset,
                market_type=token.market_type,
                cascade_discount=0.0,
                is_sniper=True,
                window_seconds=getattr(token, "window_seconds", 0),
            )

            if not decision.approved:
                logger.info("BOND REJECTED %s/%s: %s", token.asset, token.side, decision.reason)
                continue

            # Edge-confidence stake scaling:
            #   edge < 0.05      → 50%  (weak, capped exposure)
            #   edge 0.05–0.07   → 75%  (moderate conviction)
            #   edge 0.07–0.10   → 100% (full size)
            #   edge ≥ 0.10      → 65%  (EXTREME cap — volatile, risk-adjusted)
            if _edge >= 0.10:
                _edge_mult, _edge_label = 0.65, "EXTREME"
            elif _edge < 0.05:
                _edge_mult, _edge_label = 0.50, "WEAK"
            elif _edge < 0.07:
                _edge_mult, _edge_label = 0.75, "MODERATE"
            else:
                _edge_mult, _edge_label = 1.00, "FULL"
            if _edge_mult != 1.00:
                _orig_stake = decision.stake
                decision.stake = max(1.0, round(_orig_stake * _edge_mult, 2))
                logger.info(
                    "BOND %s EDGE stake %s: $%.2f → $%.2f (edge=%.4f × %.2f)",
                    _edge_label, token.asset, _orig_stake, decision.stake, _edge, _edge_mult,
                )

            logger.info(
                "BOND ENTRY %s/%s [%s] | ask=%.4f rem=%.0fs exit@%ds | stake=$%.2f | odir=%s δ=%+.3f%% | %s",
                token.asset, token.side, _wlabel,
                ask, remaining, exit_sec, decision.stake,
                _token_dir, _bond_delta,
                signal.reason,
            )
            asyncio.create_task(
                self._enter_position(token_id, token.asset, signal, tpsl, decision),
                name=f"bond_{token.asset}_{token.side}",
            )

    # ── Reversal candidate shadow logger ─────────────────────────────────────

    async def _scan_reversal_candidates(self) -> None:
        """
        Shadow-observe late-window reversal opportunities. No live trading.

        Fires when:
          - dominant token (ask ≥ 0.70) has the underlying spot moving AGAINST it
          - 30–90 s remaining in a 5m window
          - |delta_against| ≥ 0.05% (deliberately low for observation coverage)

        Logs to logs/reversal_cands.jsonl. Analyse with:
            python3 analytics/reversal_log.py
        """
        _DOM_MIN       = 0.70    # dominant token threshold
        _DOM_MAX       = 0.90    # cap — above 0.90 underdog is illiquid
        _DELTA_MIN     = 0.05    # min |delta| against dominant (low for coverage)
        _REM_MIN       = 30.0    # seconds
        _REM_MAX       = 90.0    # seconds

        now = time.time()
        seen_conditions: set = set()

        for token_id, token in list(self.feed.tokens.items()):
            if token.market_type != "updown":
                continue
            if not (250 <= getattr(token, "window_seconds", 0) < 900):
                continue  # 5m only for now
            if token.window_end_ts <= 0:
                continue

            remaining = token.window_end_ts - now
            if not (_REM_MIN <= remaining <= _REM_MAX):
                continue

            ob = self.feed.get_order_book(token_id)
            if ob is None:
                continue
            dom_ask = ob.asks[0][0] if ob.asks else None
            if dom_ask is None or not (_DOM_MIN <= dom_ask <= _DOM_MAX):
                continue

            cid = getattr(token, "condition_id", "") or ""
            if not cid or cid in seen_conditions:
                continue
            seen_conditions.add(cid)

            # Find the partner token (same condition, opposite side)
            underdog_id: str | None = None
            underdog_token = None
            underdog_ask: float | None = None
            for other_id, other in self.feed.tokens.items():
                if other_id == token_id:
                    continue
                if getattr(other, "condition_id", "") != cid:
                    continue
                other_ob = self.feed.get_order_book(other_id)
                if other_ob is None:
                    continue
                other_ask = other_ob.asks[0][0] if other_ob.asks else None
                if other_ask is None:
                    continue
                underdog_id = other_id
                underdog_token = other
                underdog_ask = other_ask
                break

            if underdog_id is None or underdog_ask is None:
                continue

            # Get delta for this asset
            _ext = getattr(self, "_last_ext_signals", {}).get(token.asset)
            if not _ext or not _ext.spot_price:
                continue
            _ref = _ext.spot_window_open_5m or 0.0
            if _ref <= 0:
                continue
            _delta = (_ext.spot_price - _ref) / _ref * 100

            # Is the underlying moving AGAINST the dominant token?
            _dom_dir = getattr(token, "outcome_direction", "up")
            _against = (
                (_dom_dir == "up"   and _delta <= -_DELTA_MIN) or
                (_dom_dir == "down" and _delta >= _DELTA_MIN)
            )
            if not _against:
                continue

            # Deduplicate: only log each condition once per scan cycle
            _rev_key = f"{cid}_{remaining:.0f}"
            _seen_rev = getattr(self, "_rev_cand_logged", set())
            if _rev_key in _seen_rev:
                continue
            _seen_rev.add(_rev_key)
            self._rev_cand_logged = _seen_rev

            logger.info(
                "REVERSAL_CAND %s dom=%s(%.3f) underdog=%s(%.3f) δ=%+.3f%% "
                "against_%s rem=%.0fs — shadow logging, no trade",
                token.asset, token.side, dom_ask,
                underdog_token.side if underdog_token else "?", underdog_ask,
                _delta, _dom_dir, remaining,
            )

            asyncio.create_task(
                self._monitor_reversal_candidate(
                    underdog_id=underdog_id,
                    underdog_ask=underdog_ask,
                    dominant_ask=dom_ask,
                    dominant_side=token.side,
                    asset=token.asset,
                    delta_pct=_delta,
                    remaining_s=remaining,
                    window_end_ts=token.window_end_ts,
                    window_seconds=getattr(token, "window_seconds", 0),
                ),
                name=f"rev_monitor_{token.asset}",
            )

    async def _monitor_reversal_candidate(
        self,
        underdog_id: str,
        underdog_ask: float,
        dominant_ask: float,
        dominant_side: str,
        asset: str,
        delta_pct: float,
        remaining_s: float,
        window_end_ts: float,
        window_seconds: int,
    ) -> None:
        """Track underdog price snapshots after REVERSAL_CAND detection."""
        from analytics.reversal_log import log_reversal_cand

        ts_detected = time.time()

        async def _snap(delay_s: float) -> float | None:
            await asyncio.sleep(delay_s)
            ob = self.feed.get_order_book(underdog_id)
            if ob and ob.asks:
                return ob.asks[0][0]
            return None

        ask_10s = await _snap(10.0)
        ask_20s = await _snap(10.0)   # cumulative 20s
        ask_30s = await _snap(10.0)   # cumulative 30s

        # Wait until just after window end
        wait_to_end = (window_end_ts + 4.0) - time.time()
        if wait_to_end > 0:
            await asyncio.sleep(min(wait_to_end, 200.0))

        ask_final: float | None = None
        ob = self.feed.get_order_book(underdog_id)
        if ob and ob.asks:
            ask_final = ob.asks[0][0]

        log_reversal_cand(
            ts=ts_detected,
            asset=asset,
            dominant_side=dominant_side,
            dominant_ask=dominant_ask,
            underdog_token_id=underdog_id,
            underdog_ask=underdog_ask,
            delta_pct=delta_pct,
            remaining_s=remaining_s,
            window_seconds=window_seconds,
            ask_at_10s=ask_10s,
            ask_at_20s=ask_20s,
            ask_at_30s=ask_30s,
            ask_at_window_end=ask_final,
        )

    async def _scan_for_signals(self) -> None:
        if not SNIPER_ENABLED and not MOM_ENABLED:
            return

        # Periodic updown token count — fires every ~10s to confirm discovery health
        now_ts = time.time()
        if now_ts - getattr(self, "_last_updown_log_ts", 0) > 10:
            self._last_updown_log_ts = now_ts
            updown_tokens = [t for t in self.feed.tokens.values() if t.market_type == "updown"]
            if updown_tokens:
                logger.info(
                    "UPDOWN tokens in feed: %d | %s",
                    len(updown_tokens),
                    ", ".join(
                        f"{t.asset}/{t.side}/{t.window_seconds//60}m"
                        for t in updown_tokens[:8]
                    ),
                )
            else:
                logger.warning(
                    "UPDOWN MISSING: no updown tokens in feed (total=%d tokens) — "
                    "discovery failed to find 5M/15M updown markets",
                    len(self.feed.tokens),
                )

        # Ext signals already fetched by _refresh_ext_signals() earlier this loop tick.
        ext_signals = dict(self._last_ext_signals)

        # ── LLM Signal Engine: inject Claude signal into external signals ────────
        # Fires all day on sharp BTC moves (≥0.25% in active sessions, ≥0.40% quiet)
        # OR when VPIN > 0.65 (informed order flow detected on Binance aggTrade).
        btc_ext = ext_signals.get("BTC")
        btc_spot = btc_ext.spot_price if btc_ext else None
        btc_vpin = btc_ext.vpin_score if btc_ext else None
        btc_vpin_dir = btc_ext.vpin_direction if btc_ext else None
        try:
            macro_signal = await asyncio.wait_for(
                self.macro_engine.tick(
                    btc_spot, vpin_score=btc_vpin, vpin_direction=btc_vpin_dir,
                    ext_signals=ext_signals,
                ),
                timeout=8.0,
            )
        except asyncio.TimeoutError:
            logger.warning("MacroEngine tick timeout (8s) — skipping LLM signal this cycle")
            macro_signal = None
        if macro_signal is None:
            macro_signal = self.macro_engine.get_signal()  # use cached if still valid
        if macro_signal:
            # Inject signed boost into ALL asset ext signals
            # BTC moves propagate to ETH/SOL within 10–30s (correlated assets)
            for asset in CONFIG.markets.tracked_assets:
                ext = ext_signals.get(asset)
                if ext is not None:
                    ext.macro_boost = macro_signal.boost_for_direction_yes()

        # Cache for OB scan loop (advise_exit needs VPIN without a separate fetch)
        self._last_ext_signals = ext_signals

        # ── Cross-asset cascade: score all tokens, find lead signals ─────────
        # When a strong leader (BTC) fires, follower assets (ETH, SOL) get a
        # reduced effective min_score to catch the correlated wave.
        lead_assets: Set[str] = set()
        all_scores: Dict[str, float] = {}
        for token_id, token in self.feed.tokens.items():
            ob = self.feed.get_order_book(token_id)
            if ob is not None and ob.mid > 0 and (ob.mid < 0.05 or ob.mid > 0.95):
                continue  # near-resolved, skip
            bars_5m = self.feed.get_bars_5m(token_id, n=30)
            bars_15m = self.feed.get_bars_15m(token_id, n=30)
            if len(bars_5m) < 12:
                continue
            sig = self.scorer.score(bars_5m, bars_15m, ob, ext_signals.get(token.asset))
            all_scores[token_id] = sig.composite
            if (sig.composite >= CONFIG.edge.cascade_trigger_score
                    and token.asset in CONFIG.edge.cascade_assets):
                lead_assets.add(token.asset)

        # Build set of follower assets that get score discount this cycle
        discounted_assets: Set[str] = set()
        for leader in lead_assets:
            for follower in CONFIG.edge.cascade_assets.get(leader, []):
                discounted_assets.add(follower)
                logger.debug("CASCADE: %s lead → %s gets %.2f score discount",
                             leader, follower, CONFIG.edge.cascade_score_discount)

        # Volatile-hours gate removed — all UTC hours permitted.

        # ── Phase 1: scan all tokens, collect sniper candidates + run momentum ──
        # Sniper candidates are queued for a single LLM briefing call (not per-token).
        # Momentum (non-updown) tokens are evaluated and entered inline as before.
        sniper_queue: list = []  # [(token_id, token, signal, tpsl, decision, ext)]
        _queued_conditions: set = set()  # dedup: one entry per condition_id per scan cycle
        _updown_scanned = 0
        _updown_fired = 0

        for token_id, token in self.feed.tokens.items():
            # Skip tokens already in open positions
            if token_id in self.risk.open_positions:
                continue

            # Skip tokens whose asset is locked by a concurrent entry (spike or this loop).
            # evaluate() has this check too, but an early guard here avoids the full
            # scoring pipeline for tokens we can't trade anyway.
            if token.asset in self.risk._pending_assets:
                continue
            if token.asset in self._pending_asset_entries:
                continue

            # Skip tokens that are in the no-trade final window — saves scan noise
            # and avoids scoring dead markets (near-expiry prices are extreme/meaningless).
            if token.window_end_ts > 0:
                remaining_window = token.window_end_ts - time.time()
                if remaining_window < CONFIG.execution.no_trade_last_sec:
                    continue

            ob = self.feed.get_order_book(token_id)

            # Skip near-resolved tokens — they produce entry=0 and will never trade.
            # Check ask price directly (mid can be 0 when there are no bids, which
            # hides near-dead tokens from the mid-based filter).
            if ob is not None:
                _ask = ob.asks[0][0] if ob.asks else ob.mid
                if _ask < 0.05 or _ask > 0.95:
                    continue
                # Target markets with no valid OB (ask=0) have no edge and no fills.
                # Skip them rather than wasting a scan cycle on entry=0.0000 noise.
                if token.market_type == "target" and _ask <= 0:
                    continue

            bars_5m = self.feed.get_bars_5m(token_id, n=30)
            bars_15m = self.feed.get_bars_15m(token_id, n=30)
            ext = ext_signals.get(token.asset)

            # ── Window Sniper: primary signal for updown markets ─────────────
            # Detects mid-window mispriced certainty (fair value vs token ask).
            # Fires when: 35–80% elapsed, asset moved >0.20% (active) / >0.35% (quiet), edge ≥ 0.02–0.04.
            # SniperSignal is compatible with risk manager (same fields: composite,
            # confidence, entry_price, direction, fee_zone, reason).
            sniper_sig = None
            if (token.market_type == "updown"
                    and token.asset not in CONFIG.edge.sniper_excluded_assets):
                _updown_scanned += 1
                sniper_sig = self.sniper.score(token, ob, ext, now=time.time())

            # ── Velocity gate: skip if Binance momentum is against trade direction ──
            # NO trade requires price still falling (vel < 0); YES requires rising (vel > 0).
            # Flat/cold (|vel| ≤ 0.001%) allowed through — no data is not a bad signal.
            # Live data: vel against direction → 0W/4L on SNI NO trades.
            if sniper_sig is not None:
                _vel_now, _ = self.feed.get_velocity_5s(token.asset)
                _VEL_THRESHOLD = 0.001   # % — dead zone for flat/no-data
                _vel_against = (
                    (token.side == "NO"  and _vel_now >  _VEL_THRESHOLD) or
                    (token.side == "YES" and _vel_now < -_VEL_THRESHOLD)
                )
                if _vel_against:
                    logger.info(
                        "SNIPER VELOCITY_GATE %s/%s | vel=%+.4f%% against direction — skip",
                        token.asset, token.side, _vel_now,
                    )
                    sniper_sig = None

            if sniper_sig is not None:
                _updown_fired += 1
                # Log the sniper detection here; briefing decision logged after the call
                _wlabel = f"{token.window_seconds//60}m" if token.window_seconds else "?"
                logger.info(
                    "SCAN [SNIPER] %s/%s [%s] | score=%.2f conf=%.2f entry=%.4f dir=%s | %s",
                    token.asset, token.side, _wlabel,
                    sniper_sig.composite, sniper_sig.confidence,
                    sniper_sig.entry_price, sniper_sig.direction.name,
                    sniper_sig.reason or "no signal",
                )

                if token.market_type == "updown" and ext is not None:
                    log_lag_observation(
                        ts=time.time(), asset=token.asset, token_id=token_id,
                        side=token.side, market_type=token.market_type,
                        window_end_ts=token.window_end_ts,
                        polymarket_price=sniper_sig.entry_price,
                        binance_spot_price=ext.spot_price,
                        binance_1m_pct=ext.spot_momentum_1m,
                        binance_5m_pct=ext.spot_momentum_5m,
                        binance_15m_pct=ext.spot_momentum_15m,
                    )

                if sniper_sig.entry_price <= 0:
                    logger.warning("SKIP %s/%s — zero entry price", token.asset, token.side)
                    continue

                tpsl = calculate_tp_sl(sniper_sig.entry_price, sniper_sig.direction, bars_5m, ob)
                decision = self.risk.evaluate(
                    token_id, sniper_sig, tpsl,
                    condition_id=token.condition_id,
                    window_end_ts=token.window_end_ts,
                    asset=token.asset,
                    market_type=token.market_type,
                    cascade_discount=0.0,
                    is_sniper=True,
                    window_seconds=getattr(token, "window_seconds", 0),
                )

                if not decision.approved:
                    logger.info("  └─ REJECTED: %s", decision.reason)
                else:
                    _cid = token.condition_id or ""
                    if _cid and _cid in _queued_conditions:
                        logger.info("  └─ SKIP %s/%s — condition already queued this cycle", token.asset, token.side)
                    else:
                        sniper_queue.append((token_id, token, sniper_sig, tpsl, decision, ext))
                        if _cid:
                            _queued_conditions.add(_cid)
                continue  # updown token handled — skip momentum path

            elif token.market_type == "updown" and CONTRARIAN_DELTA_ENABLED:
                # ── Delta contrarian: small Binance move → buy opposite direction ──
                # Fires when abs(delta) in [0.05%, 0.06%] and this token is OPPOSITE
                # to the Binance direction. Hypothesis: small moves reverse before PM reprices.
                # Half stake (qs=0). No lag/edge gates.
                if token.asset not in CONFIG.edge.sniper_excluded_assets:
                    _dc_sig = self.sniper.score_delta_contrarian(token, ob, ext, now=time.time())
                    if _dc_sig is not None:
                        _wlabel = f"{token.window_seconds//60}m" if token.window_seconds else "?"
                        logger.info(
                            "SCAN [DELTA_CONTRARIAN] %s/%s [%s] | entry=%.4f delta=%+.3f%% elapsed=%.0f%%",
                            token.asset, token.side, _wlabel,
                            _dc_sig.entry_price, _dc_sig.delta_pct, _dc_sig.elapsed_pct * 100,
                        )
                        _dc_tpsl = calculate_tp_sl(_dc_sig.entry_price, _dc_sig.direction, bars_5m, ob)
                        _dc_decision = self.risk.evaluate(
                            token_id, _dc_sig, _dc_tpsl,
                            condition_id=token.condition_id,
                            window_end_ts=token.window_end_ts,
                            asset=token.asset,
                            market_type=token.market_type,
                            cascade_discount=0.0,
                            is_sniper=True,
                            window_seconds=getattr(token, "window_seconds", 0),
                        )
                        if _dc_decision.approved:
                            _dc_decision.stake = max(1.0, round(_dc_decision.stake / 2, 2))
                            _cid = token.condition_id or ""
                            if _cid and _cid in _queued_conditions:
                                logger.info("  └─ DELTA_CONTRARIAN SKIP %s/%s — condition already queued", token.asset, token.side)
                            else:
                                sniper_queue.append((token_id, token, _dc_sig, _dc_tpsl, _dc_decision, ext))
                                if _cid:
                                    _queued_conditions.add(_cid)
                        else:
                            logger.info("  └─ DELTA_CONTRARIAN REJECTED: %s", _dc_decision.reason)

            if token.market_type == "updown":
                # ── Contrarian check: buy cheap side when opponent is ≥0.90 early ──
                # When the opposite token is at ≥0.90 in the first 40% of the window,
                # the cheap side (~0.10) may offer mean-reversion value.
                # Normal sniper skips this token (ask < MIN_TOKEN_ASK=0.35 or wrong side).
                # This path catches the contrarian opportunity independently.
                if (ob is not None and ob.asks
                        and ob.asks[0][0] <= CONTRARIAN_MAX_ASK
                        and token.asset not in CONFIG.edge.sniper_excluded_assets):
                    # Find the paired opposite token for this window
                    _opponent_ask = 0.0
                    for _tid, _t in self.feed.tokens.items():
                        if (_t.asset == token.asset
                                and _t.side != token.side
                                and abs(_t.window_end_ts - token.window_end_ts) < 5):
                            _opp_ob = self.feed.get_order_book(_tid)
                            if _opp_ob and _opp_ob.asks:
                                _opponent_ask = _opp_ob.asks[0][0]
                            break
                    if _opponent_ask > 0:
                        _cntr_sig = self.sniper.score_contrarian(token, ob, _opponent_ask, ext, now=time.time())
                        if _cntr_sig is not None:
                            _wlabel = f"{token.window_seconds//60}m" if token.window_seconds else "?"
                            logger.info(
                                "SCAN [CONTRARIAN] %s/%s [%s] | entry=%.4f opponent=%.3f elapsed=%.0f%%",
                                token.asset, token.side, _wlabel,
                                _cntr_sig.entry_price, _opponent_ask, _cntr_sig.elapsed_pct * 100,
                            )
                            # Custom TP/SL: fixed percentages sized for low-price reversal plays.
                            # TP=+150% (buy 0.10, target 0.25), SL=−50% (0.10→0.05). RR=3:1.
                            # Break-even WR=25%. Normal calculate_tp_sl uses ATR which is
                            # tiny for a 0.10 token → would produce useless tight targets.
                            _ep = _cntr_sig.entry_price
                            _cntr_tpsl = TPSLLevels(
                                take_profit=round(min(0.98, _ep * 2.5), 4),
                                stop_loss=round(max(0.01, _ep * 0.50), 4),
                                tp_pct=150.0,
                                sl_pct=50.0,
                                risk_reward=3.0,
                            )
                            _cntr_decision = self.risk.evaluate(
                                token_id, _cntr_sig, _cntr_tpsl,
                                condition_id=token.condition_id,
                                window_end_ts=token.window_end_ts,
                                asset=token.asset,
                                market_type=token.market_type,
                                cascade_discount=0.0,
                                is_sniper=True,
                                window_seconds=getattr(token, "window_seconds", 0),
                            )
                            if _cntr_decision.approved:
                                _ccid = token.condition_id or ""
                                if _ccid and _ccid in _queued_conditions:
                                    logger.info("  └─ CONTRARIAN SKIP %s/%s — condition already queued", token.asset, token.side)
                                else:
                                    # Half stake: contrarian is speculative — $10 base → $5 per contrarian trade
                                    _cntr_decision.stake = max(1.0, round(_cntr_decision.stake / 2, 2))
                                    sniper_queue.append(
                                        (token_id, token, _cntr_sig, _cntr_tpsl, _cntr_decision, ext)
                                    )
                                    if _ccid:
                                        _queued_conditions.add(_ccid)
                            else:
                                logger.info("  └─ CONTRARIAN REJECTED: %s", _cntr_decision.reason)

                # Sniper didn't fire on this updown token → skip entirely.
                # Momentum scorer on updown markets has confirmed ZERO edge:
                # 19 live trades, WR=36.8%, losses score HIGHER than wins (0.531 vs 0.511).
                # Breakout and trend signals are anti-predictive on updown markets.
                # Only the Window Sniper (fair-value model) is allowed to enter updown.
                if ob is not None:
                    logger.debug(
                        "UPDOWN SKIP %s/%s | sniper=None ask=%.3f | "
                        "window_end=%s window=%ds",
                        token.asset, token.side,
                        ob.asks[0][0] if ob.asks else 0,
                        token.window_end_ts, token.window_seconds,
                    )
                # Shadow monitor: spawn once per (token_id, window_end_ts) —
                # not every scan cycle. The sniper repopulates last_block every
                # 0.2s; dedup via _shadow_active prevents duplicate tasks.
                block = self.sniper.last_block.pop((token.asset, token.side), None)
                if block is not None and block.token_id == token_id:
                    dedup_key = (block.token_id, block.window_end_ts)
                    if dedup_key not in self._shadow_active:
                        self._shadow_active.add(dedup_key)
                        _macro_sig = self.macro_engine.get_signal()
                        _llm_boost = _macro_sig.boost_for_direction_yes() if _macro_sig else 0.0
                        asyncio.create_task(
                            _shadow_monitor(block, self.feed, self._shadow_active, dedup_key,
                                            llm_boost=_llm_boost),
                            name=f"shadow_{token.asset}_{token.side}",
                        )
                continue
            else:
                # Non-updown (price-target markets): use momentum scorer
                # Re-enabled 2026-04-18 at 0.5× stake for data collection.
                if not MOM_ENABLED:
                    continue

                if len(bars_5m) < 12:
                    continue  # not enough bar history yet

                signal = self.scorer.score(bars_5m, bars_15m, ob, ext)
                signal_source = "MOMENTUM"

                # For NO tokens: scorer labels uptrend as BUY_YES (rising token price).
                # Flip so direction reflects the actual trade: rising NO = BUY_NO.
                if token.side == "NO" and signal.direction != Direction.NO_TRADE:
                    signal.direction = (
                        Direction.BUY_NO
                        if signal.direction == Direction.BUY_YES
                        else Direction.BUY_YES
                    )

            # Only log NO_TRADE at DEBUG — SCAN cycle summary covers the quiet state.
            # Log at INFO when something actionable is happening (score > 0 with direction).
            _log_fn = logger.debug if signal.direction == Direction.NO_TRADE else logger.info
            _mtype = (f"{token.window_seconds//60}m" if token.market_type == "updown" and token.window_seconds
                      else token.market_type)
            _log_fn(
                "SCAN [%s] %s/%s [%s] | score=%.2f conf=%.2f entry=%.4f dir=%s | %s",
                signal_source,
                token.asset, token.side, _mtype,
                signal.composite, signal.confidence,
                signal.entry_price, signal.direction.name,
                signal.reason or "no signal",
            )

            if signal.direction == Direction.NO_TRADE:
                continue

            # Lag research: record Binance price + Polymarket price every scan.
            # No trading logic affected. Used by analytics/lag_analysis.py.
            # (Updown lag logging happens in the sniper path above.)
            if ext is not None:
                log_lag_observation(
                    ts=time.time(),
                    asset=token.asset,
                    token_id=token_id,
                    side=token.side,
                    market_type=token.market_type,
                    window_end_ts=token.window_end_ts,
                    polymarket_price=signal.entry_price,
                    binance_spot_price=ext.spot_price,
                    binance_1m_pct=ext.spot_momentum_1m,
                    binance_5m_pct=ext.spot_momentum_5m,
                    binance_15m_pct=ext.spot_momentum_15m,
                )

            # Route YES tokens to BUY_YES trades, NO tokens to BUY_NO trades.
            # Momentum path: NO token with BUY_YES after flip → redirect to YES counterpart.
            if token.side == "YES" and signal.direction == Direction.BUY_NO:
                continue
            if token.side == "NO" and signal.direction == Direction.BUY_YES:
                yes_token_id = next(
                    (tid for tid, t in self.feed.tokens.items()
                     if t.condition_id and t.condition_id == token.condition_id
                     and t.side == "YES" and tid not in self.risk.open_positions),
                    None,
                )
                if not yes_token_id:
                    continue  # no YES counterpart available
                # Redirect: trade YES token at the mirror price (1 - no_price)
                token_id = yes_token_id
                token = self.feed.tokens[yes_token_id]
                signal.entry_price = round(1.0 - signal.entry_price, 4)
                logger.info(
                    "  └─ REDIRECT NO→YES: using %s YES token @ %.4f (NO was %.4f)",
                    token.asset, signal.entry_price, 1.0 - signal.entry_price,
                )

            if signal.entry_price <= 0:
                logger.warning("SKIP %s/%s — zero entry price (bad feed data)", token.asset, token.side)
                continue

            tpsl = calculate_tp_sl(signal.entry_price, signal.direction, bars_5m, ob)
            decision = self.risk.evaluate(
                token_id, signal, tpsl,
                condition_id=token.condition_id,
                window_end_ts=token.window_end_ts,
                asset=token.asset,
                market_type=token.market_type,
                cascade_discount=CONFIG.edge.cascade_score_discount
                    if token.asset in discounted_assets else 0.0,
                window_seconds=getattr(token, "window_seconds", 0),
            )

            if not decision.approved:
                logger.info("  └─ REJECTED: %s", decision.reason)
                continue

            # MOMENTUM: trade at 0.5× size while the strategy is re-validating
            if signal_source == "MOMENTUM":
                _orig_stake = decision.stake
                decision.stake = max(1.0, round(_orig_stake * 0.50, 2))
                logger.info(
                    "  └─ MOMENTUM stake reduction %s: $%.2f → $%.2f (0.5×)",
                    token.asset, _orig_stake, decision.stake,
                )

            cascade_tag = " [CASCADE]" if token.asset in discounted_assets else ""
            logger.info(
                "  └─ SIGNAL%s %s | %s %s | entry=%.4f conf=%.2f score=%.2f | %s",
                cascade_tag, token.asset, signal.direction.name, signal.fee_zone.name,
                signal.entry_price, signal.confidence, signal.composite,
                signal.reason,
            )
            await self._enter_position(token_id, token.asset, signal, tpsl, decision)

        # ── Scan cycle summary ─────────────────────────────────────────────────
        # Show asset deltas so user can see why sniper is/isn't firing
        _delta_parts = []
        for _a in CONFIG.markets.tracked_assets:
            _ext = ext_signals.get(_a)
            if _ext and _ext.spot_price:
                _parts = []
                if _ext.spot_window_open_5m:
                    _d5 = (_ext.spot_price - _ext.spot_window_open_5m) / _ext.spot_window_open_5m * 100
                    _parts.append(f"5m={_d5:+.3f}%")
                if _ext.spot_window_open_15m:
                    _d15 = (_ext.spot_price - _ext.spot_window_open_15m) / _ext.spot_window_open_15m * 100
                    _parts.append(f"15m={_d15:+.3f}%")
                if _parts:
                    _delta_parts.append(f"{_a}[{' '.join(_parts)}]")
        _thr_5m = _session_min_delta(is_15m=False)
        _thr_15m = _session_min_delta(is_15m=True)
        _threshold_str = f"5m≥{_thr_5m:.2f}% / 15m≥{_thr_15m:.2f}%"
        _status = "SNIPER WAITING" if _updown_fired == 0 else f"SNIPER FIRED={_updown_fired}"
        logger.info(
            "[SNIPER] %s | %d updown scanned | deltas: %s | need %s",
            _status, _updown_scanned,
            " ".join(_delta_parts) if _delta_parts else "no Binance data",
            _threshold_str,
        )

        # ── Phase 2: LLM briefing for all sniper candidates ───────────────────
        # ONE call with ALL candidates → Claude sees portfolio context, ranks by quality.
        # Much more powerful than per-token calls: can avoid correlated duplicates,
        # can deprioritize weak edges when capital is limited.
        if sniper_queue:
            briefing_candidates = [
                {
                    "token_id": tid,
                    "asset": tok.asset,
                    "side": tok.side,
                    "delta_pct": sig.delta_pct,
                    "fair_value": sig.fair_value,
                    "token_ask": sig.token_ask,
                    "edge": sig.edge,
                    "lag_remaining_pct": sig.lag_remaining_pct,
                    "elapsed_pct": sig.elapsed_pct,
                    "window_seconds": tok.window_seconds,
                    "vpin_score": (ex.vpin_score if ex else None),
                    "vpin_direction": (ex.vpin_direction if ex else None),
                }
                for tid, tok, sig, tpsl, dec, ex in sniper_queue
            ]
            # Briefing disabled: LLM veto never fires (always overridden), adds 1-2s
            # latency before order placement, kills fills on fast-moving tokens.
            briefing = {}

            # Sort by LLM priority (lower = better), then enter
            sniper_queue.sort(key=lambda x: briefing.get(x[0], {}).get("priority", 99))

            for token_id, token, signal, tpsl, decision, ext in sniper_queue:
                # Re-check: another iteration may have filled max positions
                if token_id in self.risk.open_positions:
                    continue

                b = briefing.get(token_id, {})
                llm_decision = b.get("decision", "ENTER")
                llm_conf = b.get("confidence", 0.5)
                llm_reason = b.get("reason", "")

                # LLM veto DISABLED — track recommendation vs outcome instead.
                # Log what the LLM would have done so we can validate its accuracy later.
                if llm_decision == "SKIP":
                    logger.info(
                        "  └─ LLM WOULD-VETO %s/%s (conf=%.2f) — entering anyway for data: %s",
                        token.asset, token.side, llm_conf, llm_reason,
                    )

                if not SNIPER_ENABLED:
                    logger.info(
                        "  └─ SNIPER GATED (SNIPER_ENABLED=False) %s/%s — skipping entry",
                        token.asset, token.side,
                    )
                    continue
                logger.info(
                    "  └─ SNIPER ENTER %s/%s [p=%d conf=%.2f] | entry=%.4f edge=%.3f | %s",
                    token.asset, token.side,
                    b.get("priority", 99), llm_conf,
                    signal.entry_price, signal.edge,
                    llm_reason or signal.reason,
                )
                await self._enter_position(token_id, token.asset, signal, tpsl, decision,
                                           llm_rec=llm_decision, llm_rec_conf=llm_conf)

        # ── Bond scan moved to _signal_loop — runs independently of sniper ──────
        # (removed from here so sniper's early return doesn't block BOND)

    # ── Entry ─────────────────────────────────────────────────────────────────

    async def _enter_position(self, token_id, asset, signal, tpsl, decision,
                              llm_rec: str = "", llm_rec_conf: float = 0.0) -> None:
        # Synchronous guard (no await before this) — prevents race between spike path
        # and sweep both approving the same token. _pending_entries is checked and set
        # atomically before any await point, so asyncio single-thread makes this safe.
        if token_id in self.risk.open_positions or token_id in self._pending_entries:
            logger.warning(
                "ENTRY GUARD %s/%s — already open or pending (token), skipping duplicate",
                asset, token_id[:8],
            )
            return
        # Asset-level guard: catches spike+scan race where different token_ids
        # for the same asset both pass the token-level check above.
        if asset in self._pending_asset_entries:
            logger.warning(
                "ENTRY GUARD %s — already pending entry for this asset, skipping duplicate",
                asset,
            )
            return
        for pos in self.risk.open_positions.values():
            if pos.asset == asset:
                logger.warning("ENTRY GUARD %s — already have open position, skipping", asset)
                return
        self._pending_entries.add(token_id)
        self._pending_asset_entries.add(asset)
        try:
            await self._enter_position_inner(token_id, asset, signal, tpsl, decision,
                                             llm_rec=llm_rec, llm_rec_conf=llm_rec_conf)
        except Exception as _entry_exc:
            # Any exception in _enter_position_inner must clear the risk manager's
            # _pending_assets lock. Without this, the asset is permanently locked
            # until restart — bot stops entering that asset silently.
            self.risk._pending_assets.discard(asset)
            # Same for condition dedup: exception before fill means no trade happened.
            _cid_exc = getattr(self.feed.tokens.get(token_id), "condition_id", "")
            if _cid_exc:
                self.risk._traded_conditions.discard(_cid_exc)
            logger.error(
                "ENTRY EXCEPTION %s — _pending_assets cleared, re-raising: %s",
                asset, _entry_exc,
            )
            raise
        finally:
            self._pending_entries.discard(token_id)
            self._pending_asset_entries.discard(asset)

    async def _enter_position_inner(self, token_id, asset, signal, tpsl, decision,
                                    llm_rec: str = "", llm_rec_conf: float = 0.0) -> None:
        capital_before = self.risk.bankroll.capital
        ts_open = time.time()

        # Capture entry-context data before placing order
        _ext_entry = self._last_ext_signals.get(asset)
        spot_at_entry = _ext_entry.spot_price if _ext_entry and _ext_entry.spot_price else 0.0
        pre_entry_momentum_pct = _ext_entry.spot_momentum_1m if _ext_entry and _ext_entry.spot_momentum_1m else 0.0
        _ob_entry = self.feed.get_order_book(token_id)
        ob_depth_at_entry = 0.0
        if _ob_entry:
            _bid_depth = sum(qty for _, qty in (_ob_entry.bids[:5] if _ob_entry.bids else []))
            _ask_depth = sum(qty for _, qty in (_ob_entry.asks[:5] if _ob_entry.asks else []))
            ob_depth_at_entry = _bid_depth + _ask_depth

        token_meta = self.feed.tokens.get(token_id)
        self._buy_tried += 1
        fill = await self.orders.market_buy(
            token_id=token_id,
            intended_price=signal.entry_price,
            stake_usd=decision.stake,
            direction=signal.direction,
            neg_risk=getattr(token_meta, "neg_risk", False),
            tick_size=getattr(token_meta, "tick_size", "0.01"),
        )

        if fill.avg_fill_price == 0:
            reason = fill.error or "unknown"
            self._buy_failed_reasons[reason] = self._buy_failed_reasons.get(reason, 0) + 1
            logger.error("Fill failed for %s: %s", asset, reason)
            self.risk._pending_assets.discard(asset)  # release lock on fill failure
            # Release condition dedup lock: the trade never actually happened, so
            # the same condition must be eligible for re-entry on the next signal.
            _cid_fail = getattr(self.feed.tokens.get(token_id), "condition_id", "")
            if _cid_fail:
                self.risk._traded_conditions.discard(_cid_fail)
            return

        # Slippage guard: two tiers.
        # Tier 1 (entry_slip_cap): fill is >3.5% ABOVE the signal price — we paid more
        # than expected, meaning PM moved up between signal and fill. Our fair-value
        # model used the pre-fill price; the entry is now anchored to a worse basis.
        # At 3.5% above signal price the fee-adjusted edge is materially degraded.
        # (Different from Tier 2: Tier 1 = fill too expensive; Tier 2 = fill too cheap)
        #
        # PREVIOUS BEHAVIOR (WRONG): sell immediately on slip cap breach.
        # Problem: the fill already happened — selling immediately adds another round
        # of fees and potentially exits at a worse price (observed: fill=0.64, sold=0.56
        # → -12.5% loss on a position that would have won). 2026-04-14.
        # NEW BEHAVIOR: warn and continue tracking at actual fill price. The fill is done,
        # the edge still exists (slightly reduced). Normal exit logic manages it.
        _slip_cap = self.risk.exec_cfg.entry_slip_cap  # 0.035 = 3.5%
        _slip_above = (fill.avg_fill_price - signal.entry_price) / signal.entry_price if signal.entry_price > 0 else 0
        if _slip_above > _slip_cap:
            logger.warning(
                "ENTRY_SLIP_CAP %s: fill=%.4f vs signal=%.4f (+%.1f%% > cap %.1f%%) "
                "— tracking at fill price (position already open, selling would lose more)",
                asset, fill.avg_fill_price, signal.entry_price,
                _slip_above * 100, _slip_cap * 100,
            )

        # Tier 2: if fill is >10¢ below limit, the market moved hard against
        # us mid-order — signal is invalidated. Close immediately rather than enter
        # a position anchored to a stale thesis. (T00026: limit=0.495 fill=0.310)
        slippage_on_entry = signal.entry_price - fill.avg_fill_price
        if slippage_on_entry > 0.10:
            self._buy_failed_reasons["slippage_abort"] = \
                self._buy_failed_reasons.get("slippage_abort", 0) + 1
            logger.warning(
                "SLIPPAGE ABORT %s: fill=%.4f vs limit=%.4f (slippage=%.4f > 0.10) "
                "— market moved against signal mid-order, not opening position",
                asset, fill.avg_fill_price, signal.entry_price, slippage_on_entry,
            )
            # Immediately sell back what we just bought to recover capital.
            # If the sell fails (exception), fall through to track the position normally
            # rather than leaving tokens in the wallet as an untracked orphan.
            _token_meta_sa = self.feed.tokens.get(token_id)
            try:
                await self.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=fill.total_size,
                    current_price=fill.avg_fill_price,
                    reason="SLIPPAGE_ABORT",
                    neg_risk=getattr(_token_meta_sa, "neg_risk", False),
                    tick_size=getattr(_token_meta_sa, "tick_size", "0.01"),
                )
                self.risk._pending_assets.discard(asset)  # release lock on slippage abort
                return
            except Exception as _sa_exc:
                logger.error(
                    "SLIPPAGE_ABORT cascade_sell failed for %s (%s) — "
                    "tracking position at fill price instead to avoid orphan",
                    asset, _sa_exc,
                )
                # Fall through: open_position() below will track it and clear _pending_assets

        self._buy_filled += 1

        # Use actual fill cost as stake — CLOB 5-share minimum may require more than
        # the risk-approved stake (e.g. $1 stake but minimum order is $3.45 at price 0.69).
        actual_stake = fill.avg_fill_price * fill.total_size
        if actual_stake <= 0:
            actual_stake = decision.stake  # fallback to approved stake if fill data incomplete

        # Recalculate TP/SL from actual fill price if it differs significantly from the
        # limit price (>2 ticks). Pre-fill tpsl uses signal.entry_price which can be
        # far from actual fill when the market moves between signal and execution —
        # e.g. limit=0.495 fill=0.310 would put SL=0.480 above entry, triggering instantly.
        token = self.feed.tokens.get(token_id)
        fill_slippage = abs(fill.avg_fill_price - signal.entry_price)
        if fill_slippage > 0.02:
            ob_now = self.feed.get_order_book(token_id)
            bars_now = self.feed.get_bars_5m(token_id)
            tpsl = calculate_tp_sl(fill.avg_fill_price, signal.direction, bars_now, ob_now)
            logger.info(
                "TP/SL recalculated from actual fill %.4f (limit was %.4f, slippage=%.4f): "
                "TP=%.4f SL=%.4f",
                fill.avg_fill_price, signal.entry_price, fill_slippage,
                tpsl.take_profit, tpsl.stop_loss,
            )

        pos = self.risk.open_position(
            token_id=token_id,
            asset=asset,
            direction=signal.direction,
            stake=actual_stake,
            entry_price=fill.avg_fill_price,
            tpsl=tpsl,
            condition_id=getattr(token, "condition_id", ""),
            window_end_ts=getattr(token, "window_end_ts", 0.0),
            window_seconds=getattr(token, "window_seconds", 0),
            quality_score=getattr(signal, "quality_score", 0),
            binance_price_at_entry=(
                self.feed._spot_price.get(asset.upper(), 0.0)
                or spot_at_entry  # fallback: ext signal spot price captured before order
            ),
            entry_delta_pct=abs(getattr(signal, "delta_pct", 0.0)) / 100,  # convert % → fraction
            entry_lag_pct=getattr(signal, "lag_remaining_pct", 0.0),
            entry_fair_value=getattr(signal, "fair_value", 0.0),
            is_bond=getattr(signal, "is_bond", False),
            bond_exit_sec=getattr(signal, "bond_exit_sec", 0),
            bond_outcome_direction=getattr(signal, "bond_outcome_direction", "down"),
            bond_entry_class=getattr(signal, "bond_entry_class", ""),
        )

        # Verify actual CLOB balance immediately after fill — CLOB may credit slightly
        # fewer shares than stake/price due to rounding or fee deduction from token amount.
        # Using the authoritative balance eliminates "not enough balance" errors at exit
        # and ensures the cascade sells exactly what we own, not what we computed we own.
        if not CONFIG.dry_run:
            _clob_balance = self.orders.fetch_token_balance(token_id)
            if _clob_balance is not None and _clob_balance > 0:
                computed = pos.shares
                if abs(_clob_balance - computed) > 0.05:
                    logger.info(
                        "BALANCE VERIFY %s: computed=%.4f CLOB=%.4f — using CLOB value",
                        asset, computed, _clob_balance,
                    )
                pos.shares = round(_clob_balance, 4)
                pos.remaining_shares = round(_clob_balance, 4)
            else:
                logger.warning(
                    "BALANCE VERIFY %s: CLOB returned %.4f — keeping computed %.4f",
                    asset, _clob_balance or 0.0, pos.shares,
                )
            # FIX: double-fill orphan prevention. CF retry loop can place 2-3 orders that
            # all fill; the initial balance check above may miss fills that haven't
            # propagated to the CLOB read-replica yet (typically <1s latency).
            # Recheck after 1.5s to absorb any late-arriving duplicate fill tokens into
            # the tracked position so normal exit logic sells them all (no orphans).
            asyncio.create_task(self._deferred_balance_sync(token_id, asset))

        signal_to_fill_ms = (time.time() - ts_open) * 1000.0
        _vel_5s, _move_age = self.feed.get_velocity_5s(asset)

        self._open_meta[token_id] = {
            "signal": signal,
            "signal_source": getattr(signal, "signal_source", "SNIPER")
                             if hasattr(signal, "delta_pct") else "MOMENTUM",
            "entry_fill": fill,
            "ts_open": ts_open,
            "capital_before": capital_before,
            "heat_check": decision.is_scaled,
            "consecutive_wins": self.risk.bankroll.consecutive_wins,
            "window_size_s": getattr(token, "window_seconds", 0) or pos.window_seconds,
            "spot_at_entry": spot_at_entry,
            "pre_entry_momentum_pct": pre_entry_momentum_pct,
            "ob_depth_at_entry": ob_depth_at_entry,
            "signal_to_fill_ms": signal_to_fill_ms,
            "llm_rec": llm_rec,
            "llm_rec_conf": llm_rec_conf,
            "velocity_5s_pct": _vel_5s,
            "move_age_s": _move_age,
        }

        # BOND: launch a dedicated timer task so TIME_EXIT fires at exactly
        # T-exit_sec regardless of scan loop delays under load.
        if getattr(signal, "is_bond", False) and pos.window_end_ts > 0:
            asyncio.create_task(
                self._bond_precise_timer(token_id, pos.window_end_ts, pos.bond_exit_sec),
                name=f"bond_timer_{asset}_{token_id[:8]}",
            )

    # ── BOND precise timer ────────────────────────────────────────────────────

    async def _bond_precise_timer(
        self, token_id: str, window_end_ts: float, exit_sec: int
    ) -> None:
        """
        Dedicated asyncio timer for BOND TIME_EXIT.

        Sleeps until exactly window_end_ts - exit_sec, then fires the exit.
        Bypasses the 1s scan loop which can drift 3-8s under load, causing
        TIME_EXIT to fire too close to window close (→ BOND_TIME_EXIT_EXT).

        The scan loop TIME_EXIT check remains as a fallback, but this task
        fires first when both are eligible.
        """
        target_ts = window_end_ts - exit_sec
        wait_s = target_ts - time.time()
        if wait_s > 0:
            await asyncio.sleep(wait_s)

        # Re-check: position might have already been exited by TP or reversal stop
        if token_id not in self.risk.open_positions:
            return
        pos = self.risk.open_positions.get(token_id)
        if pos is None or not getattr(pos, "is_bond", False):
            return
        if token_id in self._exit_in_progress:
            return

        ob = self.feed.get_order_book(token_id)
        current_price = (
            ob.bids[0][0] if (ob and ob.bids)
            else (pos.entry_price if pos else 0.50)
        )
        actual_remaining = max(0.0, window_end_ts - time.time())
        logger.info(
            "BOND_TIMER %s: precise exit firing | remaining=%.1fs target=T-%ds",
            pos.asset if pos else token_id[:8], actual_remaining, exit_sec,
        )
        self._exit_in_progress.add(token_id)
        try:
            await self._exit_position(token_id, current_price, "BOND_TIME_EXIT")
        finally:
            self._exit_in_progress.discard(token_id)

    # ── Double-fill protection ────────────────────────────────────────────────

    async def _deferred_balance_sync(self, token_id: str, asset: str, delay: float = 1.5) -> None:
        """
        Re-check CLOB token balance 1.5s after position open to absorb any
        CF-retry double-fill shares that hadn't propagated to the read-replica yet.

        Race scenario: CF 403 on attempt-0 → sleep 0.5s → pop_fill_for_token
        finds nothing (WS latency ~400ms) → attempt-1 also fills → position opened
        with attempt-1's shares → attempt-0's tokens arrive in wallet ~200ms later →
        initial balance check misses them → they become orphans at window-end.

        This deferred check runs after the propagation window and absorbs the extra
        shares into the tracked position so the normal exit logic sells all of them.
        """
        await asyncio.sleep(delay)
        if CONFIG.dry_run:
            return
        pos = self.risk.open_positions.get(token_id)
        if pos is None:
            return  # position already closed before recheck fired
        balance = self.orders.fetch_token_balance(token_id)
        if balance is not None and balance > pos.remaining_shares + 0.05:
            extra = round(balance - pos.remaining_shares, 4)
            logger.warning(
                "DEFERRED BALANCE SYNC %s: %.4f tracked → %.4f CLOB "
                "(%.4f extra shares from CF-retry double-fill — absorbed into position)",
                asset, pos.remaining_shares, balance, extra,
            )
            pos.shares = round(balance, 4)
            pos.remaining_shares = round(balance, 4)

    # ── Exit helpers ──────────────────────────────────────────────────────────

    def _calc_exit_price(self, exit_fills, fallback: float) -> float:
        total_size = sum(f.total_size for f in exit_fills)
        return (
            sum(f.avg_fill_price * f.total_size for f in exit_fills) / total_size
            if exit_fills and total_size > 0 else fallback
        )

    async def _partial_exit(self, token_id: str, live_price: float, reason: str) -> None:
        """Stage-1: sell 60%, leave 40% for stage-2 with floor stop at cost+12%."""
        pos = self.risk.open_positions.get(token_id)
        if not pos:
            return

        # 60/40 split: sell 60% at stage-1, leave 40% riding to stage-2 (+35% target).
        # Floor stop at cost+12% protects the 40% from reversing to a loss.
        residual_value = pos.remaining_shares * 0.40 * live_price
        sell_pct = 0.60 if residual_value >= 1.50 else 1.0
        if sell_pct == 1.0:
            logger.info(
                "Stage-1 selling 100%% — 40%% residual=$%.2f < $1.50 CLOB minimum",
                residual_value,
            )

        token_meta = self.feed.tokens.get(token_id)
        sell_shares = round(pos.remaining_shares * sell_pct, 4)
        exit_fills = await self.orders.cascade_sell(
            token_id=token_id,
            total_shares=sell_shares,
            current_price=live_price,
            reason=reason,
            neg_risk=getattr(token_meta, "neg_risk", False),
            tick_size=getattr(token_meta, "tick_size", "0.01"),
            force_exit=True,  # P5: single-shot — eliminates 3-tranche CLOB lag partial-sell bug
        )
        sold = sum(f.total_size for f in exit_fills)

        if sold == 0:
            # Reconcile against actual CLOB balance — fills may have landed on Polymarket
            # but WS confirmation was dropped. Without this, bot retries with stale quantity,
            # CLOB rejects (insufficient balance), shares left unsold at window resolution.
            actual_balance = self.orders.fetch_token_balance(token_id)
            if actual_balance is not None:
                discrepancy = pos.remaining_shares - actual_balance
                if discrepancy > 0.05:
                    logger.warning(
                        "FILL RECONCILE %s/%s: bot=%.4f shares CLOB=%.4f — "
                        "%.4f sold without confirmation, updating tracking",
                        pos.asset, pos.direction.name,
                        pos.remaining_shares, actual_balance, discrepancy,
                    )
                    pos.remaining_shares = round(actual_balance, 4)
                if actual_balance < 0.05:
                    logger.info(
                        "FILL RECONCILE %s/%s: CLOB balance=0 — all shares sold, "
                        "forcing STAGE_1_DONE",
                        pos.asset, pos.direction.name,
                    )
                    pos.exit_stage = ExitStage.STAGE_1_DONE
                    return

            pos.stage1_attempts += 1
            if pos.stage1_attempts >= 3:
                logger.warning(
                    "STAGE-1 FORCE-DONE %s/%s: %d failed attempts (0 fills each) — "
                    "forcing STAGE_1_DONE, hard exit will close remaining %.4f shares",
                    pos.asset, pos.direction.name, pos.stage1_attempts, pos.remaining_shares,
                )
                pos.exit_stage = ExitStage.STAGE_1_DONE
            else:
                logger.warning(
                    "STAGE-1 ZERO FILLS %s/%s (attempt %d/3) — will retry next scan",
                    pos.asset, pos.direction.name, pos.stage1_attempts,
                )
            return

        s1_fill_price = self._calc_exit_price(exit_fills, live_price)
        self.risk.record_stage1_sell(token_id, sold, sell_price=s1_fill_price)
        # Store stage-1 fills so analytics can compute accurate weighted exit price
        meta = self._open_meta.get(token_id)
        if meta is not None:
            meta.setdefault("stage1_fills", []).extend(exit_fills)
        logger.info(
            "STAGE-1 %s %s | sold=%.4f @ %.4f | reason=%s",
            pos.asset, pos.direction.name, sold, s1_fill_price, reason,
        )

        # When stage-1 sold 100% (residual below $1.50 CLOB minimum), close and
        # record the trade immediately — remaining_shares=0 means stage-2 would
        # fire with an empty cascade, producing EXTERNALLY_SOLD with PnL≈0.
        _pos_after = self.risk.open_positions.get(token_id)
        if sell_pct == 1.0 and _pos_after is not None and _pos_after.remaining_shares < 0.05:
            _meta = self._open_meta.get(token_id, {})
            _all_shares = pos.shares
            _net_pnl = self.risk.close_position(
                token_id, s1_fill_price, reason, shares_override=_all_shares,
            )
            self._open_meta.pop(token_id, None)
            self._pos_log_ts.pop(token_id, None)
            if _net_pnl is not None:
                _entry_fill = _meta.get("entry_fill") or OrderResult(
                    status=OrderStatus.FILLED, avg_fill_price=pos.entry_price,
                    total_size=_all_shares, slippage=0.0,
                )
                _signal = _meta.get("signal") or SignalBreakdown(
                    direction=pos.direction, entry_price=pos.entry_price,
                    composite=0.0, confidence=0.0, breakout_score=0.0,
                    trend_score=0.0, volume_score=0.0, ob_score=0.0,
                    fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                    reason="stage1_full_exit",
                )
                _token_meta = self.feed.tokens.get(token_id)
                try:
                    self.analytics.record_trade(
                        token_id=token_id, asset=pos.asset, direction=pos.direction,
                        entry_price=pos.entry_price, exit_price=s1_fill_price,
                        stake=pos.stake, shares=_all_shares,
                        entry_fill=_entry_fill, exit_fills=exit_fills,
                        exit_reason=reason,
                        signal=_signal,
                        ts_open=_meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                        capital_before=self.risk.bankroll.capital - _net_pnl,
                        heat_check_active=_meta.get("heat_check", False),
                        consecutive_wins=_meta.get("consecutive_wins", 0),
                        net_pnl_actual=_net_pnl,
                        market_type=getattr(_token_meta, "market_type", "unknown"),
                        is_live=not CONFIG.dry_run,
                        signal_source=_meta.get("signal_source", "SNIPER"),
                        window_size_s=_meta.get("window_size_s") or pos.window_seconds or 0,
                        spot_at_entry=_meta.get("spot_at_entry", 0.0),
                        spot_at_exit=0.0,
                        signal_to_fill_ms=_meta.get("signal_to_fill_ms", 0.0),
                        ob_depth_at_entry=_meta.get("ob_depth_at_entry", 0.0),
                        pre_entry_momentum_pct=_meta.get("pre_entry_momentum_pct", 0.0),
                        max_price_seen=pos.highest_price,
                        min_price_seen=pos.lowest_price,
                        bond_entry_class=pos.bond_entry_class,
                    )
                except Exception as _s1e:
                    logger.error("record_trade STAGE1_FULL_EXIT failed: %s", _s1e)
            return  # fully closed — skip stage-2 CLOB sync

        # CLOB balance sync: verify remaining_shares matches reality before stage-2.
        # CLOB cache lag can cause cascade_sell to fill a slightly different amount,
        # leaving remaining_shares out of sync. Sync now so stage-2 sells the right qty.
        if not CONFIG.dry_run and token_id in self.risk.open_positions:
            await asyncio.sleep(1.5)  # let CLOB balance settle
            _clob_remaining = self.orders.fetch_token_balance(token_id)
            _pos = self.risk.open_positions.get(token_id)
            if _clob_remaining is not None and _pos is not None:
                if abs(_clob_remaining - _pos.remaining_shares) > 0.05:
                    logger.warning(
                        "STAGE-1 SYNC %s/%s: tracked=%.4f CLOB=%.4f — correcting to CLOB value",
                        _pos.asset, _pos.direction.name,
                        _pos.remaining_shares, _clob_remaining,
                    )
                    _pos.remaining_shares = round(_clob_remaining, 4)
                    self.risk._save_positions()
                else:
                    logger.debug(
                        "STAGE-1 SYNC %s/%s: %.4f shares confirmed on CLOB",
                        _pos.asset, _pos.direction.name, _clob_remaining,
                    )

        # POST-STAGE1 SWEEP REMOVED:
        # Originally needed when stage-1 used 3 tranches — tranche 3 failed due to
        # CLOB balance lag, leaving shares unsold. Sweep caught them immediately.
        # Now stage-1 is single-shot (force_exit=True), so no tranche lag occurs.
        # More importantly: with 60/40 split, the 40% remaining after stage-1 is
        # INTENTIONAL stage-2 inventory. Sweep was selling it at the stale stage-1
        # price instead of letting it ride to +45% / trailing stop.

    async def _exit_position(self, token_id: str, live_price: float, reason: str) -> None:
        pos = self.risk.open_positions.get(token_id)
        if not pos:
            return

        meta = self._open_meta.get(token_id, {})
        _ext_exit = self._last_ext_signals.get(pos.asset)
        spot_at_exit = _ext_exit.spot_price if _ext_exit and _ext_exit.spot_price else 0.0

        token_meta = self.feed.tokens.get(token_id)
        # Mandatory exits (TIME_EXIT, WINDOW_END, HARD_EXIT, REVERSAL, VELOCITY,
        # SIGNAL_FLIPPED, PRICE_FLOOR, CATASTROPHIC_SL) MUST fill at any cost —
        # allow 10% price stepdown so thin OBs near window close don't cause a
        # sell-resting spin loop (Guard 1 retry every 4.5s → window closes → ep=xp).
        # Profit exits (PROFIT_*, MOON_BAG*, RATCHET*, BOND_TP*) hold their price
        # and retry with a fresh OB price next scan — Guard 1 handles that cleanly.
        _PROFIT_REASONS = ("PROFIT", "MOON_BAG", "RATCHET", "BOND_TP", "BOND_EXHAUSTION", "BOND_TRAIL_SL")
        _allow_stepdown = not any(r in reason for r in _PROFIT_REASONS)
        exit_fills = await self.orders.cascade_sell(
            token_id=token_id,
            total_shares=pos.remaining_shares,
            current_price=live_price,
            reason=reason,
            neg_risk=getattr(token_meta, "neg_risk", False),
            tick_size=getattr(token_meta, "tick_size", "0.01"),
            force_exit=True,  # full exits must always succeed regardless of notional value
            allow_stepdown=_allow_stepdown,
        )

        # Combine stage-1 + stage-2 fills for full-position PnL accounting.
        # Must be done BEFORE close_position so bankroll uses the same weighted
        # avg price as analytics — not just the 5% stage-2 tranche.
        stage1_fills = meta.get("stage1_fills", [])
        all_exit_fills = stage1_fills + exit_fills
        sold_shares = sum(f.total_size for f in all_exit_fills)

        stage1_done = pos.exit_stage.name == "STAGE_1_DONE"
        this_sell = sum(f.total_size for f in exit_fills)   # this cascade attempt only
        expected_this_sell = pos.remaining_shares            # what we tried to sell

        # Ghost position guard: MUST run BEFORE Guard 1 (which returns early on 0 fills).
        # CLOB balance=0 means we never owned these tokens — cancel-race false positive.
        # Close at 0 immediately so bot stops retrying and capital tracking stays honest.
        # EXCEPTION: if entry_fill exists in meta, the position was real (we have proof of
        # purchase). CLOB balance=0 then means it was sold/resolved externally — reclassify
        # as EXTERNALLY_SOLD so the EXT path handles it (not recorded as full $0 loss).
        # 2026-04-16: ETH GHOST_POSITION fired on a real position that resolved externally.
        ghost_detected = any(
            "GHOST_POSITION" in (getattr(r, "error", "") or "")
            for r in exit_fills
        )
        if ghost_detected:
            _ghost_check_meta = self._open_meta.get(token_id, {})
            _has_entry_fill = _ghost_check_meta.get("entry_fill") is not None
            if _has_entry_fill:
                # Real position confirmed by entry_fill — reclassify to EXTERNALLY_SOLD
                # so EXT path uses entry_price fallback (not full $0 loss).
                logger.warning(
                    "GHOST→EXT reclassify %s/%s — entry_fill exists, position was real. "
                    "CLOB balance=0 means externally sold/resolved. Using EXT path.",
                    pos.asset, pos.direction.name,
                )
                for _r in exit_fills:
                    if "GHOST_POSITION" in (getattr(_r, "error", "") or ""):
                        _r.error = _r.error.replace("GHOST_POSITION", "EXTERNALLY_SOLD")
                # Fall through to ext_sold_detected block below
            else:
                logger.error(
                    "GHOST POSITION purged: %s/%s — stake=$%.2f recorded as total loss. "
                    "Cancel-race false positive in earlier session.",
                    pos.asset, pos.direction.name, pos.stake,
                )
                ghost_pnl = self.risk.close_position(token_id, 0.0, "GHOST_POSITION", shares_override=pos.shares)
                _ghost_meta = self._open_meta.pop(token_id, {})
                self._pos_log_ts.pop(token_id, None)
                self._dir_rev_count.pop(token_id, None)
                self._entry_snaps.pop(token_id, None)
                self._sl_below_count.pop(token_id, None)
                self._stall_checked.discard(token_id)
                self._peak_bond_move.pop(token_id, None)
                if ghost_pnl is not None:
                    _ghost_signal = _ghost_meta.get("signal") or SignalBreakdown(
                        direction=pos.direction, entry_price=pos.entry_price,
                        composite=0.0, confidence=0.0, breakout_score=0.0,
                        trend_score=0.0, volume_score=0.0, ob_score=0.0,
                        fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                        reason="ghost_position",
                    )
                    try:
                        self.analytics.record_trade(
                            token_id=token_id, asset=pos.asset, direction=pos.direction,
                            entry_price=pos.entry_price, exit_price=0.0,
                            stake=pos.stake, shares=pos.shares,
                            entry_fill=_ghost_meta.get("entry_fill"), exit_fills=[],
                            exit_reason="GHOST_POSITION", signal=_ghost_signal,
                            ts_open=_ghost_meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                            capital_before=self.risk.bankroll.capital - ghost_pnl,
                            heat_check_active=_ghost_meta.get("heat_check", False),
                            consecutive_wins=_ghost_meta.get("consecutive_wins", 0),
                            net_pnl_actual=ghost_pnl,
                            market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                            is_live=not CONFIG.dry_run,
                            signal_source=_ghost_meta.get("signal_source", "SNIPER"),
                            window_size_s=_ghost_meta.get("window_size_s") or pos.window_seconds or 0,
                        )
                    except Exception as _e:
                        logger.error("record_trade GHOST_POSITION failed: %s", _e)
                return

        # Externally sold guard: balance < 0.01 shares = sold manually outside the bot.
        # Close the position at current price so PnL tracking stays accurate.
        ext_sold_detected = any(
            "EXTERNALLY_SOLD" in (getattr(r, "error", "") or "")
            for r in exit_fills
        )
        if ext_sold_detected:
            # Use weighted avg price across ALL fills (stage-1 + stage-2 attempt),
            # same as the normal exit path. This prevents gross_pnl from being
            # computed as (stage2_price - entry) × full_shares when stage1 already
            # sold 60% at a different price — which inflated gross/fee in the log.
            import re as _re
            # Only trust live_price if a price is embedded in the fill error — that
            # means the CLOB confirmed the fill price. If no price is in the error
            # (network-miss: our cascade timed out but order executed on Polymarket),
            # fall back to entry_price so we record a flat exit instead of a phantom
            # profit/loss at whatever the OB happens to show now (2026-04-16 bug:
            # cascade failed on REVERSAL_STOP, TIME_EXIT_EXT used resolution price
            # $0.96 while actual fill was $0.55 → fee ≈ gross, bankroll overstated ~$5).
            _price_found_in_error = False
            _raw_exit = live_price if live_price > 0 else pos.entry_price  # use trigger price, not entry
            for _r in exit_fills:
                _err = getattr(_r, "error", "") or ""
                _m = _re.search(r'price=([0-9.]+)', _err)
                if _m:
                    _raw_exit = float(_m.group(1))
                    _price_found_in_error = True
                    break
            if not _price_found_in_error:
                # No price in error message — cascade_sell confirmation was dropped
                # (CF block / WS miss). Query CLOB trade history to recover the
                # actual exit price. This fixes the bankroll drift seen 2026-04-16
                # where real losses of ~$2 were recorded as -$0.10 (fee only).
                # 4s delay: CLOB /trades indexing can lag 2-5s for fresh fills.
                await asyncio.sleep(4.0)
                try:
                    _clob_sells = await asyncio.to_thread(
                        self.orders.fetch_recent_token_sells,
                        token_id,
                        pos.open_ts,
                    )
                    if _clob_sells:
                        _total_sz = sum(s for _, s in _clob_sells)
                        _total_val = sum(p * s for p, s in _clob_sells)
                        if _total_sz > 0:
                            _raw_exit = round(_total_val / _total_sz, 6)
                            _price_found_in_error = True
                            logger.info(
                                "EXT price recovered from CLOB history: %s/%s → %.4f "
                                "(%d fill(s), %.4f shares total)",
                                pos.asset, pos.direction.name,
                                _raw_exit, len(_clob_sells), _total_sz,
                            )
                except Exception as _clob_exc:
                    logger.warning(
                        "fetch_recent_token_sells %s failed: %s", token_id[:8], _clob_exc
                    )
            _is_resolved_zero = False
            if not _price_found_in_error:
                # Check if the token resolved worthless (wrong direction).
                # A best bid < $0.02 with no sell fills = token expired at $0,
                # not an external sell. Record the real loss instead of entry_price.
                _ob_chk = self.feed.get_order_book(token_id)
                _best_bid_chk = _ob_chk.bids[0][0] if (_ob_chk and _ob_chk.bids) else 0.0
                if _best_bid_chk < 0.02:
                    _raw_exit = 0.0
                    _is_resolved_zero = True
                    logger.warning(
                        "EXTERNALLY_SOLD %s/%s — token resolved worthless "
                        "(best_bid=%.4f), recording full loss exit_price=0.0000",
                        pos.asset, pos.direction.name, _best_bid_chk,
                    )
                else:
                    # Shares not confirmed sold — check CLOB balance before giving up.
                    # If balance > 0, shares are still in wallet (thin OB stalled the exit).
                    # Force-sell them now before closing position tracking.
                    _residual_bal = await asyncio.to_thread(
                        self.orders.fetch_token_balance, token_id
                    ) if not CONFIG.dry_run else None
                    if _residual_bal and _residual_bal > 0.05:
                        logger.warning(
                            "EXTERNALLY_SOLD %s/%s — CLOB balance=%.4f shares still in wallet "
                            "(thin OB stalled exit). Force-selling before close.",
                            pos.asset, pos.direction.name, _residual_bal,
                        )
                        _ob_now = self.feed.get_order_book(token_id)
                        _bid_now = _ob_now.bids[0][0] if (_ob_now and _ob_now.bids) else _best_bid_chk
                        _rescue_fills = await self.orders.cascade_sell(
                            token_id=token_id,
                            total_shares=_residual_bal,
                            current_price=_bid_now if _bid_now > 0.001 else 0.01,
                            reason="EXT_RESCUE",
                            neg_risk=getattr(token_meta, "neg_risk", False),
                            tick_size=getattr(token_meta, "tick_size", "0.01"),
                            force_exit=True,
                        )
                        _rescued = sum(f.total_size for f in _rescue_fills)
                        if _rescued > 0:
                            all_exit_fills.extend(_rescue_fills)
                            _rescue_val = sum(f.avg_fill_price * f.total_size for f in _rescue_fills)
                            _raw_exit = round(_rescue_val / _rescued, 6)
                            _price_found_in_error = True
                            logger.info(
                                "EXT_RESCUE %s/%s: sold %.4f shares @ %.4f",
                                pos.asset, pos.direction.name, _rescued, _raw_exit,
                            )
                        else:
                            logger.warning(
                                "EXT_RESCUE %s/%s failed — using live_price=%.4f as fallback",
                                pos.asset, pos.direction.name, _raw_exit,
                            )
                    else:
                        logger.warning(
                            "EXTERNALLY_SOLD %s/%s — no fill price in error or CLOB history, "
                            "CLOB balance=%.4f (sold externally or resolved). "
                            "using live_price=%.4f (bankroll may drift vs Polymarket balance)",
                            pos.asset, pos.direction.name,
                            _residual_bal if _residual_bal is not None else -1.0, _raw_exit,
                        )
            if not _is_resolved_zero:
                _raw_exit = _raw_exit if _raw_exit > 0 else pos.entry_price
            # Weighted avg across all fills gives correct gross_pnl when stage-1
            # already sold 60% at a different price. Falls back to _raw_exit if
            # no fills with sizes are present (e.g. pure externally-sold dust).
            exit_price = self._calc_exit_price(all_exit_fills, _raw_exit)
            logger.warning(
                "EXTERNALLY_SOLD purged: %s/%s — closing at weighted_price %.4f "
                "(raw=%.4f). Shares already sold externally, stopping retry loop.",
                pos.asset, pos.direction.name, exit_price, _raw_exit,
            )
            pnl = self.risk.close_position(token_id, _raw_exit, reason)
            _ext_meta = self._open_meta.pop(token_id, {})
            self._pos_log_ts.pop(token_id, None)
            self._dir_rev_count.pop(token_id, None)
            self._entry_snaps.pop(token_id, None)
            self._sl_below_count.pop(token_id, None)
            self._stall_checked.discard(token_id)
            self._peak_bond_move.pop(token_id, None)
            if pnl is not None:
                _signal = _ext_meta.get("signal")
                if _signal is None:
                    _signal = SignalBreakdown(
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        composite=0.0, confidence=0.0, breakout_score=0.0,
                        trend_score=0.0, volume_score=0.0, ob_score=0.0,
                        fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                        reason="externally_sold",
                    )
                capital_before = self.risk.bankroll.capital - pnl
                # exit_reason = real trigger (STOP_LOSS / PROFIT_1 / HARD_EXIT / etc.)
                # with _EXT suffix to flag that the position was already gone at sell time
                _logged_reason = f"{reason}_EXT" if reason != "EXTERNALLY_SOLD" else "EXTERNALLY_SOLD"
                try:
                    self.analytics.record_trade(
                        token_id=token_id,
                        asset=pos.asset,
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        stake=pos.stake,
                        shares=pos.shares,
                        entry_fill=_ext_meta.get("entry_fill"),
                        exit_fills=all_exit_fills,
                        exit_reason=_logged_reason,
                        signal=_signal,
                        ts_open=_ext_meta.get("ts_open", pos.open_ts),
                        ts_close=time.time(),
                        capital_before=capital_before,
                        heat_check_active=_ext_meta.get("heat_check", False),
                        consecutive_wins=_ext_meta.get("consecutive_wins", 0),
                        net_pnl_actual=pnl,
                        market_type=getattr(token_meta, "market_type", "unknown"),
                        is_live=not CONFIG.dry_run,
                        signal_source=_ext_meta.get("signal_source", "SNIPER"),
                        window_size_s=_ext_meta.get("window_size_s") or pos.window_seconds or 0,
                        spot_at_entry=_ext_meta.get("spot_at_entry", 0.0),
                        spot_at_exit=spot_at_exit,
                        signal_to_fill_ms=_ext_meta.get("signal_to_fill_ms", 0.0),
                        ob_depth_at_entry=_ext_meta.get("ob_depth_at_entry", 0.0),
                        pre_entry_momentum_pct=_ext_meta.get("pre_entry_momentum_pct", 0.0),
                        max_price_seen=pos.highest_price,
                        min_price_seen=pos.lowest_price,
                        highest_price_ts=pos.highest_price_ts,
                        lowest_price_ts=pos.lowest_price_ts,
                        bond_entry_class=pos.bond_entry_class,
                    )
                except Exception as _rec_exc:
                    logger.error("record_trade EXTERNALLY_SOLD failed: %s", _rec_exc)
            asyncio.create_task(self._track_post_exit(
                token_id=token_id,
                trade_id=self.analytics.last_trade_id,
                asset=pos.asset,
                direction=pos.direction.name,
                exit_price=exit_price,
                exit_reason=_logged_reason,
                entry_price=pos.entry_price,
                window_end_ts=pos.window_end_ts,
                binance_price_at_entry=pos.binance_price_at_entry,
            ))
            if pos.window_end_ts > 0:
                try:
                    os.makedirs("logs", exist_ok=True)
                    with open(os.path.join("logs", "pending_resolutions.jsonl"), "a") as _pf:
                        _pf.write(json.dumps(dict(
                            token_id=token_id,
                            trade_id=self.analytics.last_trade_id,
                            asset=pos.asset,
                            direction=pos.direction.name,
                            exit_price=exit_price,
                            exit_reason=_logged_reason,
                            entry_price=pos.entry_price,
                            window_end_ts=pos.window_end_ts,
                            binance_price_at_entry=pos.binance_price_at_entry,
                        )) + "\n")
                except Exception:
                    pass
            return

        # Guard 1: zero sell before stage-1 → network/CLOB error, retry next scan.
        # Calling close_position on 0 fills ghosts the position: bot records a loss
        # while shares remain on Polymarket (T00011: 4.9 ETH shares left to resolve).
        if sold_shares <= 0 and not stage1_done:
            if token_id in self.risk.open_positions:
                self.risk.open_positions[token_id].hard_exit_triggered = False
            logger.warning(
                "EXIT RETRY: cascade sold 0 shares for %s/%s (network/CLOB error) — "
                "position kept open, retrying next OB scan",
                pos.asset, pos.direction.name,
            )
            return

        # Guard 1b: stage-2 cascade sold nothing. Check actual CLOB balance before
        # retrying — if balance=0, the shares resolved or were sold externally.
        # Previous behaviour (infinite reset loop) left positions stuck forever.
        _DUST_SHARES = 0.05           # below this, accept residual as done
        if this_sell <= 0 and stage1_done and expected_this_sell > _DUST_SHARES:
            _s2_balance = self.orders.fetch_token_balance(token_id)
            if _s2_balance is None or _s2_balance < 0.05:
                # Balance gone — resolved or sold externally. Close the record.
                # Compute weighted exit price across stage-1 fills + live_price for remaining,
                # and use all shares so bankroll captures 100% of the trade PnL.
                logger.warning(
                    "STAGE-2 balance=0 for %s/%s — shares resolved/sold, closing record",
                    pos.asset, pos.direction.name,
                )
                _s2_meta = self._open_meta.get(token_id, {})
                _s1_fills = _s2_meta.get("stage1_fills", [])
                if _s1_fills and pos.shares > 0:
                    _s1_sold = sum(f.total_size for f in _s1_fills)
                    _s1_notional = sum(f.avg_fill_price * f.total_size for f in _s1_fills)
                    _s2_remaining = max(0.0, pos.shares - _s1_sold)
                    _w_price = (_s1_notional + live_price * _s2_remaining) / pos.shares
                    _s2r_exit_price = round(_w_price, 6)
                    pnl = self.risk.close_position(token_id, _s2r_exit_price, "STAGE2_RESOLVED",
                                                   shares_override=pos.shares)
                else:
                    _s2r_exit_price = live_price
                    pnl = self.risk.close_position(token_id, _s2r_exit_price, "STAGE2_RESOLVED")
                _s2r_all_shares = pos.shares
                _s2r_entry_fill = _s2_meta.get("entry_fill")
                _s2r_signal = _s2_meta.get("signal")
                self._open_meta.pop(token_id, None)
                self._pos_log_ts.pop(token_id, None)
                self._dir_rev_count.pop(token_id, None)
                self._entry_snaps.pop(token_id, None)
                self._sl_below_count.pop(token_id, None)
                self._stall_checked.discard(token_id)
                self._peak_bond_move.pop(token_id, None)
                if pnl is not None:
                    if _s2r_entry_fill is None:
                        _s2r_entry_fill = OrderResult(
                            status=OrderStatus.FILLED, avg_fill_price=pos.entry_price,
                            total_size=pos.shares, slippage=0.0,
                        )
                    if _s2r_signal is None:
                        _s2r_signal = SignalBreakdown(
                            direction=pos.direction, entry_price=pos.entry_price,
                            composite=0.0, confidence=0.0, breakout_score=0.0,
                            trend_score=0.0, volume_score=0.0, ob_score=0.0,
                            fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                            reason="stage2_resolved",
                        )
                    try:
                        self.analytics.record_trade(
                            token_id=token_id, asset=pos.asset, direction=pos.direction,
                            entry_price=pos.entry_price, exit_price=_s2r_exit_price,
                            stake=pos.stake, shares=_s2r_all_shares,
                            entry_fill=_s2r_entry_fill, exit_fills=_s1_fills,
                            exit_reason="STAGE2_RESOLVED", signal=_s2r_signal,
                            ts_open=_s2_meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                            capital_before=self.risk.bankroll.capital - pnl,
                            heat_check_active=_s2_meta.get("heat_check", False),
                            consecutive_wins=_s2_meta.get("consecutive_wins", 0),
                            net_pnl_actual=pnl,
                            market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                            is_live=not CONFIG.dry_run,
                            signal_source=_s2_meta.get("signal_source", "SNIPER"),
                            window_size_s=_s2_meta.get("window_size_s") or pos.window_seconds or 0,
                        )
                    except Exception as _s2re:
                        logger.error("record_trade STAGE2_RESOLVED failed: %s", _s2re)
                asyncio.create_task(self._track_post_exit(
                    token_id=token_id,
                    trade_id=self.analytics.last_trade_id,
                    asset=pos.asset,
                    direction=pos.direction.name,
                    exit_price=_s2r_exit_price,
                    exit_reason="STAGE2_RESOLVED",
                    entry_price=pos.entry_price,
                    window_end_ts=pos.window_end_ts,
                    binance_price_at_entry=pos.binance_price_at_entry,
                ))
                return
            # Shares still exist — reset and retry next cycle
            if token_id in self.risk.open_positions:
                self.risk.open_positions[token_id].hard_exit_triggered = False
            logger.warning(
                "STAGE-2 sold 0 of %.4f %s shares (CLOB=%.4f) — retrying next scan",
                expected_this_sell, pos.asset, _s2_balance,
            )
            return

        # Guard 2: significant partial fill → update remaining and retry.
        # Applies to both full exits (not stage1_done) and PROFIT_2 (stage1_done):
        # if <80% of remaining filled, update count and retry rather than ghost-closing.
        # Dust residuals (<0.10 shares) are accepted and position is closed.
        _PARTIAL_FILL_THRESH = 0.80   # require selling ≥80% of remaining
        if (this_sell < expected_this_sell * _PARTIAL_FILL_THRESH
                and expected_this_sell > _DUST_SHARES):
            if token_id in self.risk.open_positions:
                if this_sell > 0:
                    self.risk.open_positions[token_id].remaining_shares = max(
                        0.0, expected_this_sell - this_sell
                    )
                self.risk.open_positions[token_id].hard_exit_triggered = False
            logger.warning(
                "PARTIAL EXIT %s/%s: sold %.4f of %.4f shares (%.0f%%) — "
                "updating remaining, retrying next scan",
                pos.asset, pos.direction.name,
                this_sell, expected_this_sell,
                100 * this_sell / expected_this_sell if expected_this_sell > 0 else 0,
            )
            return

        stage2_fallback = self._calc_exit_price(exit_fills, pos.entry_price)

        # Weighted avg exit price across ALL tranches (stage-1 95% + stage-2 5%).
        analytics_exit_price = self._calc_exit_price(all_exit_fills, stage2_fallback)
        # Capture from pos before close_position pops it from the dict.
        all_shares = pos.shares
        _highest_price = pos.highest_price
        _lowest_price = pos.lowest_price

        # Residual share recovery: if cascade_sell partially filled, try one immediate
        # retry before closing the position. If that also fails, queue for background sweep.
        _DUST_THRESHOLD = 0.10
        if sold_shares < all_shares - _DUST_THRESHOLD:
            residual = round(all_shares - sold_shares, 4)
            logger.warning(
                "RESIDUAL SHARES: %.4f %s unsold (sold %.4f of %.4f) — attempting immediate sweep",
                residual, pos.asset, sold_shares, all_shares,
            )
            try:
                sweep_fills = await self.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=residual,
                    current_price=live_price,
                    reason="RESIDUAL_SWEEP",
                    neg_risk=getattr(token_meta, "neg_risk", False),
                    tick_size=getattr(token_meta, "tick_size", "0.01"),
                    force_exit=True,
                )
                swept = sum(f.total_size for f in sweep_fills)
                if swept > 0:
                    all_exit_fills.extend(sweep_fills)
                    sold_shares += swept
                    residual = round(all_shares - sold_shares, 4)
                    analytics_exit_price = self._calc_exit_price(all_exit_fills, stage2_fallback)
                    logger.info("RESIDUAL SWEEP: recovered %.4f shares immediately", swept)
            except Exception as _sweep_exc:
                logger.warning("RESIDUAL SWEEP failed: %s", _sweep_exc)

            if residual > _DUST_THRESHOLD:
                # Queue for background retry — sweep loop will retry every 60s
                self._residual_pending[token_id] = {
                    "shares": residual,
                    "asset": pos.asset,
                    "neg_risk": getattr(token_meta, "neg_risk", False),
                    "tick_size": getattr(token_meta, "tick_size", "0.01"),
                    "attempts": 0,
                    "last_try": 0.0,
                    "entry_price": pos.entry_price,
                    "stake": pos.stake,
                    "ts_open": meta.get("ts_open", pos.open_ts),
                    "signal_source": meta.get("signal_source", "SNIPER"),
                    "window_size_s": meta.get("window_size_s", 0),
                    "market_type": getattr(token_meta, "market_type", "unknown"),
                }
                logger.warning(
                    "RESIDUAL QUEUED: %.4f %s shares → background sweep will retry every 60s",
                    residual, pos.asset,
                )

        capital_before = meta.get("capital_before", self.risk.bankroll.capital)

        # Sum actual fees from BOTH entry and exit fills (CLOB-reconciled).
        # Polymarket charges taker fee on each side of the trade independently.
        # Previous code only summed exit fees — missing the entry-side fee.
        # Falls back to estimated (risk manager config) when actual=0 (timing lag,
        # dry-run, or maker orders with zero fee).
        entry_fill = meta.get("entry_fill")
        entry_fee = (
            sum(f.fee for f in entry_fill.fills if f.fee > 0)
            if (entry_fill and entry_fill.fills) else 0.0
        )
        exit_fee = sum(f.fee for r in all_exit_fills for f in r.fills if f.fee > 0)
        actual_fee_total = (entry_fee + exit_fee) if (entry_fee + exit_fee) > 0 else None

        # Pass full shares + weighted avg price so bankroll records 100% of trade PnL.
        # Without shares_override, close_position uses remaining_shares (5% after
        # stage-1 sell), silently missing the 95% stage-1 tranche in bankroll.
        net_pnl = self.risk.close_position(
            token_id, analytics_exit_price, reason,
            shares_override=all_shares,
            actual_fee=actual_fee_total,
        )

        if net_pnl is not None:
            # entry_fill and signal: use from meta if available; construct
            # minimal placeholders if the position was restored from disk and
            # meta wasn't populated for this session.
            entry_fill = meta.get("entry_fill")
            signal = meta.get("signal")

            if entry_fill is None:
                # Position was recovered from disk; synthesize a minimal entry fill
                # so analytics can still record the trade.
                entry_fill = OrderResult(
                    status=OrderStatus.FILLED,
                    avg_fill_price=pos.entry_price,
                    total_size=pos.shares,
                    slippage=0.0,
                )

            if signal is None:
                # Build a minimal signal stub so analytics doesn't crash.
                signal = SignalBreakdown(
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    composite=0.0,
                    confidence=0.0,
                    breakout_score=0.0,
                    trend_score=0.0,
                    volume_score=0.0,
                    ob_score=0.0,
                    fee_zone=FeeZone.FAT_MIDDLE,
                    external_boost=0.0,
                    reason="recovered_from_disk",
                )

            token_meta = self.feed.tokens.get(token_id)
            # ── Path classification ───────────────────────────────────────────
            _snaps = self._entry_snaps.pop(token_id, {})
            _ep = pos.entry_price
            _s30 = _snaps.get(30, 0.0)
            _s60 = _snaps.get(60, 0.0)
            _r30 = (_s30 - _ep) / _ep * 100 if _ep > 0 and _s30 > 0 else None
            _r60 = (_s60 - _ep) / _ep * 100 if _ep > 0 and _s60 > 0 else None
            _max_adv = ((_ep - _lowest_price) / _ep * 100) if _ep > 0 and _lowest_price > 0 else 0.0
            _hold_s = time.time() - meta.get("ts_open", pos.open_ts)
            _path_class, _path_conf, _path_reason = _classify_path(
                r30=_r30, r60=_r60, max_adv_pct=_max_adv, hold_s=_hold_s,
                exit_reason=reason, exit_price=analytics_exit_price, entry_price=_ep,
            )
            logger.info(
                "PATH_CLASS %s/%s [%s] | conf=%d | %s | r30=%s r60=%s max_adv=%.1f%%",
                pos.asset, pos.direction.name, _path_class, _path_conf, _path_reason,
                f"{_r30:+.1f}%" if _r30 is not None else "—",
                f"{_r60:+.1f}%" if _r60 is not None else "—",
                _max_adv,
            )

            try:
                self.analytics.record_trade(
                    token_id=token_id,
                    asset=pos.asset,
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    exit_price=analytics_exit_price,
                    stake=pos.stake,
                    shares=all_shares,
                    entry_fill=entry_fill,
                    exit_fills=all_exit_fills,
                    exit_reason=reason,
                    signal=signal,
                    ts_open=meta.get("ts_open", pos.open_ts),
                    ts_close=time.time(),
                    capital_before=capital_before,
                    # capital_after computed inside record_trade as capital_before + net_pnl
                    heat_check_active=meta.get("heat_check", False),
                    consecutive_wins=meta.get("consecutive_wins", 0),
                    net_pnl_actual=net_pnl,
                    market_type=getattr(token_meta, "market_type", "unknown"),
                    is_live=not CONFIG.dry_run,
                    signal_source=meta.get("signal_source", "MOMENTUM"),
                    window_size_s=meta.get("window_size_s") or pos.window_seconds or 0,
                    spot_at_entry=meta.get("spot_at_entry", 0.0),
                    spot_at_exit=spot_at_exit,
                    signal_to_fill_ms=meta.get("signal_to_fill_ms", 0.0),
                    ob_depth_at_entry=meta.get("ob_depth_at_entry", 0.0),
                    pre_entry_momentum_pct=meta.get("pre_entry_momentum_pct", 0.0),
                    llm_rec=meta.get("llm_rec", ""),
                    llm_rec_conf=meta.get("llm_rec_conf", 0.0),
                    max_price_seen=_highest_price,
                    min_price_seen=_lowest_price,
                    highest_price_ts=pos.highest_price_ts,
                    lowest_price_ts=pos.lowest_price_ts,
                    binance_price_at_entry=pos.binance_price_at_entry,
                    binance_reversal_count_at_exit=pos.binance_reversal_count,
                    velocity_5s_pct=meta.get("velocity_5s_pct", 0.0),
                    move_age_s=meta.get("move_age_s", 999.0),
                    path_class=_path_class,
                    path_confidence=_path_conf,
                    path_reason=_path_reason,
                    entry_snap_30s_pct=_r30 if _r30 is not None else 0.0,
                    entry_snap_60s_pct=_r60 if _r60 is not None else 0.0,
                    bond_entry_class=pos.bond_entry_class,
                )
            except Exception as _rec_exc:
                logger.error("record_trade failed (trade still closed): %s", _rec_exc)

        self._open_meta.pop(token_id, None)
        self._pos_log_ts.pop(token_id, None)
        self._dir_rev_count.pop(token_id, None)
        self._entry_snaps.pop(token_id, None)
        self._sl_below_count.pop(token_id, None)
        self._stall_checked.discard(token_id)
        self._peak_bond_move.pop(token_id, None)
        bankroll = self.risk.bankroll.summary()
        logger.info(
            "EXIT %s %s | reason=%s | PnL=$%.3f | capital=$%.2f | streak=%d",
            pos.asset, pos.direction.name, reason,
            net_pnl or 0, bankroll["capital"], bankroll["consecutive_wins"],
        )

        # Post-exit price tracking — answers "was our exit right?"
        # Samples token price at T+30s, T+60s, T+120s after exit.
        # For SL exits: also samples at window_end+60s to capture resolution outcome.
        # Logs to logs/post_exit.jsonl for strategy analysis.
        _post_exit_kwargs = dict(
            token_id=token_id,
            trade_id=self.analytics.last_trade_id,
            asset=pos.asset,
            direction=pos.direction.name,
            exit_price=analytics_exit_price,
            exit_reason=reason,
            entry_price=pos.entry_price,
            window_end_ts=pos.window_end_ts,
            binance_price_at_entry=pos.binance_price_at_entry,
        )
        # Persist to disk so restarts don't lose the resolution task
        if pos.window_end_ts > 0:
            try:
                os.makedirs("logs", exist_ok=True)
                with open(os.path.join("logs", "pending_resolutions.jsonl"), "a") as _pf:
                    _pf.write(json.dumps(_post_exit_kwargs) + "\n")
            except Exception:
                pass
        asyncio.create_task(self._track_post_exit(**_post_exit_kwargs))

    async def _track_post_exit(
        self,
        token_id: str,
        trade_id: str,
        asset: str,
        direction: str,
        exit_price: float,
        exit_reason: str,
        entry_price: float,
        window_end_ts: float = 0.0,
        binance_price_at_entry: float = 0.0,
    ) -> None:
        """Sample token price at T+30s, T+60s, T+120s after exit.
        For SL exits: also samples at window_end_ts+60s to capture window resolution outcome.
        Tells us whether the exit was correct (price continued) or premature (price recovered).
        Also samples Binance spot at each time point to measure correlation:
          binance_move_at_exit_pct  — how far Binance moved from entry at exit moment
          binance_move_t30s/t60s    — Binance move at T+30s/60s (confirms or diverges)
        Logs 'resolved_correctly' — key metric for diagnosing premature SL exits.
        """
        import json as _json
        log_path = os.path.join("logs", "post_exit.jsonl")
        samples = {}
        binance_samples = {}  # Binance move % from entry at each time point
        # Binance move at exit moment (before any sleep) — key correlation metric.
        # binance_move_at_exit_pct > 0 for BUY_NO = Binance has recovered (reversed).
        # binance_move_at_exit_pct ≈ 0 = Binance flat while PM dropped (PM-specific event).
        # binance_move_at_exit_pct < 0 for BUY_NO = Binance confirming our direction.
        _b_exit = self.feed._spot_price.get(asset.upper(), 0.0)
        binance_move_at_exit_pct = None
        if _b_exit > 0 and binance_price_at_entry > 0:
            binance_move_at_exit_pct = round(
                (_b_exit - binance_price_at_entry) / binance_price_at_entry * 100, 4
            )

        elapsed = 0
        for delay in (30, 60, 120):
            await asyncio.sleep(delay - elapsed)
            elapsed = delay
            try:
                # Always use live fetch — in-memory cache (best_ask / _order_books)
                # is stale or empty after exit, giving null samples. fetch_order_book
                # makes a real API call and is confirmed working (same path as
                # window_outcome_price which is always populated).
                price = 0.0
                token = self.feed.tokens.get(token_id)
                if token and hasattr(token, "best_ask") and token.best_ask > 0:
                    price = token.best_ask
                if not price:
                    _ob = await self.feed.fetch_order_book(token_id)
                    if _ob and _ob.asks:
                        price = _ob.asks[0][0]
                samples[f"t{delay}s"] = round(price, 4) if price else None
                # Binance spot at this time point — measures whether Binance
                # is confirming, diverging, or reversing vs our entry direction.
                _b_now = self.feed._spot_price.get(asset.upper(), 0.0)
                if _b_now > 0 and binance_price_at_entry > 0:
                    _b_move = (_b_now - binance_price_at_entry) / binance_price_at_entry * 100
                    binance_samples[f"binance_move_t{delay}s_pct"] = round(_b_move, 4)
            except Exception:
                samples[f"t{delay}s"] = None

        # ── Write T+30/60/120 record immediately after samples are collected ──────
        # Previous bug: write was deferred until after window_end + 60s wait,
        # meaning for a 15m trade exited at elap=0.07, the write happened ~15 min
        # later — after restarts or session ends, data was lost.
        # Fix: write now with what we have; resolution outcome appended separately.
        _is_sl_exit = exit_reason.startswith("STOP_LOSS") or exit_reason in (
            "CIRCUIT_BREAKER", "TRAIL_STOP", "STOP_LOSS_EXT",
            "VELOCITY_EXIT", "SL_15S", "PRICE_FLOOR", "RATCHET_SL",
        ) or "TIGHT_SL" in exit_reason
        move_from_exit = {}
        for k, p in samples.items():
            if p and exit_price > 0:
                move_from_exit[k] = round((p - exit_price) / exit_price * 100, 2)

        move_from_entry = {}
        for k, p in samples.items():
            if p and entry_price > 0:
                move_from_entry[k] = round((p - entry_price) / entry_price * 100, 2)

        record = {
            "trade_id": trade_id,
            "asset": asset,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "drawdown_pct": round((entry_price - exit_price) / entry_price * 100, 1) if entry_price > 0 else None,
            "sl_tier": (
                "T1_30pct" if entry_price > 0 and (entry_price - exit_price) / entry_price <= 0.35
                else "T2_50pct" if entry_price > 0 and (entry_price - exit_price) / entry_price <= 0.55
                else "T3_catastrophic"
            ) if exit_reason in ("STOP_LOSS", "STOP_LOSS_EXT") else None,
            **samples,
            "move_from_entry_pct": move_from_entry,
            "move_from_exit_pct": move_from_exit,
            # Resolution fields — populated below after window ends, null for now
            "window_outcome_price": None,
            "entered_correctly": None,
            "resolution_delay_s": None,
            "window_end_ts": window_end_ts if window_end_ts > 0 else None,
            "binance_move_at_exit_pct": binance_move_at_exit_pct,
            **binance_samples,
        }

        try:
            os.makedirs("logs", exist_ok=True)
            with open(log_path, "a") as f:
                f.write(_json.dumps(record) + "\n")
            logger.info(
                "POST_EXIT %s/%s [%s] | exit=%.4f | +30s=%s +60s=%s +120s=%s",
                asset, direction, exit_reason, exit_price,
                samples.get("t30s"), samples.get("t60s"), samples.get("t120s"),
            )
        except Exception as exc:
            logger.debug("post_exit log failed: %s", exc)

        # ── Resolution sample: window_end + 60s (written as separate record) ────
        # Appended to post_exit.jsonl with record_type="resolution" so joins still
        # work — report can left-join and prefer the resolution record if present.
        if window_end_ts > 0:
            now_ts = time.time()
            wait_until = window_end_ts + 60
            wait_s = max(0.0, wait_until - now_ts)
            if wait_s <= 900:  # skip if window ended >15 min ago
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
                window_outcome_price = None
                entered_correctly = None
                resolution_delay_s = None
                try:
                    token = self.feed.tokens.get(token_id)
                    if token and hasattr(token, "best_ask") and token.best_ask > 0:
                        window_outcome_price = round(token.best_ask, 4)
                    else:
                        _ob = await self.feed.fetch_order_book(token_id)
                        if _ob and _ob.asks:
                            window_outcome_price = round(_ob.asks[0][0], 4)
                    if window_outcome_price is not None:
                        entered_correctly = window_outcome_price >= 0.80
                        resolution_delay_s = round(time.time() - window_end_ts)
                except Exception as _res_exc:
                    logger.debug("resolution sample failed %s: %s", token_id[:8], _res_exc)
                if window_outcome_price is not None:
                    try:
                        res_record = {
                            "trade_id": trade_id,
                            "record_type": "resolution",
                            "window_outcome_price": window_outcome_price,
                            "entered_correctly": entered_correctly,
                            "resolution_delay_s": resolution_delay_s,
                        }
                        with open(log_path, "a") as f:
                            f.write(_json.dumps(res_record) + "\n")
                        logger.info(
                            "RESOLUTION %s/%s [%s] | outcome=%.4f entered_correctly=%s",
                            asset, direction, exit_reason,
                            window_outcome_price, entered_correctly,
                        )
                    except Exception as _re:
                        logger.debug("resolution log failed: %s", _re)

    # ── Pending resolution replay (restart recovery) ─────────────────────────

    async def _replay_pending_resolutions(self) -> None:
        """Re-schedule post-exit resolution tasks lost due to bot restarts."""
        pending_path = os.path.join("logs", "pending_resolutions.jsonl")
        post_exit_path = os.path.join("logs", "post_exit.jsonl")
        if not os.path.exists(pending_path):
            return
        # Load trade_ids already resolved
        completed: set = set()
        if os.path.exists(post_exit_path):
            try:
                with open(post_exit_path) as f:
                    for line in f:
                        try:
                            rec = json.loads(line.strip())
                            if rec.get("trade_id"):
                                completed.add(rec["trade_id"])
                        except Exception:
                            pass
            except Exception:
                pass
        now = time.time()
        replayed = 0
        try:
            with open(pending_path) as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip())
                        tid = rec.get("trade_id")
                        wend = rec.get("window_end_ts", 0)
                        if not tid or tid in completed:
                            continue
                        if wend == 0 or wend + 900 < now:
                            continue  # too stale (>15 min past window end)
                        asyncio.create_task(self._track_post_exit(**rec))
                        replayed += 1
                    except Exception:
                        pass
        except Exception:
            pass
        if replayed > 0:
            logger.info("Replayed %d pending resolution tasks from previous session", replayed)

    # ── Residual share sweep ──────────────────────────────────────────────────

    async def _sweep_residuals(self) -> None:
        """Retry selling shares that survived partial cascade_sell at position close."""
        if not self._residual_pending:
            return
        now = time.time()
        to_remove = []
        for token_id, r in list(self._residual_pending.items()):
            if now - r["last_try"] < 60:
                continue
            if r["attempts"] >= 10:
                logger.error(
                    "RESIDUAL ABANDONED: %.4f %s shares after 10 attempts (~10 min) — "
                    "forcing bankroll update and removing from pending.",
                    r["shares"], r["asset"],
                )
                try:
                    _res_pnl = self.risk.close_position(token_id, 0.50, "RESIDUAL_ABANDONED", shares_override=r["shares"])
                    if _res_pnl is not None:
                        try:
                            self.analytics.record_trade(
                                token_id=token_id, asset=r["asset"], direction=Direction.BUY_YES,
                                entry_price=r.get("entry_price", 0.50), exit_price=0.50,
                                stake=r.get("stake", 0.0), shares=r["shares"],
                                entry_fill=None, exit_fills=[],
                                exit_reason="RESIDUAL_ABANDONED", signal=SignalBreakdown(
                                    direction=Direction.BUY_YES, entry_price=0.50,
                                    composite=0.0, confidence=0.0, breakout_score=0.0,
                                    trend_score=0.0, volume_score=0.0, ob_score=0.0,
                                    fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                                    reason="residual_abandoned",
                                ),
                                ts_open=r.get("ts_open", time.time()), ts_close=time.time(),
                                capital_before=self.risk.bankroll.capital - _res_pnl,
                                heat_check_active=False, consecutive_wins=0,
                                net_pnl_actual=_res_pnl,
                                market_type=r.get("market_type", "unknown"),
                                is_live=not CONFIG.dry_run,
                                signal_source=r.get("signal_source", "SNIPER"),
                                window_size_s=r.get("window_size_s", 0),
                            )
                        except Exception as _re:
                            logger.error("record_trade RESIDUAL_ABANDONED failed: %s", _re)
                except Exception as _close_err:
                    logger.error("RESIDUAL ABANDONED close_position failed: %s", _close_err)
                to_remove.append(token_id)
                continue
            r["attempts"] += 1
            r["last_try"] = now
            try:
                fills = await self.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=round(r["shares"], 4),
                    current_price=0.50,   # mid estimate; CLOB adjusts to actual bid
                    reason="RESIDUAL_RETRY",
                    neg_risk=r["neg_risk"],
                    tick_size=r["tick_size"],
                    force_exit=True,
                )
                sold = sum(f.total_size for f in fills)
                if sold > 0:
                    r["shares"] = round(r["shares"] - sold, 4)
                    logger.info(
                        "RESIDUAL RETRY %s: sold %.4f shares (attempt %d, %.4f remaining)",
                        r["asset"], sold, r["attempts"], r["shares"],
                    )
                if r["shares"] <= 0.05:
                    to_remove.append(token_id)
            except Exception as exc:
                logger.warning("RESIDUAL RETRY %s attempt %d failed: %s",
                               r["asset"], r["attempts"], exc)
        for tid in to_remove:
            self._residual_pending.pop(tid, None)

    # ── 10-second CLOB heartbeat ──────────────────────────────────────────────

    async def _heartbeat_loop(self, _watchdog_ping: list = None) -> None:
        """Keep CLOB session alive; prevents silent GTC order cancellation."""
        _hb_failures = 0
        _last_reconcile_ts = 0.0
        _RECONCILE_INTERVAL = 3600  # reconcile bankroll vs actual USDC every hour
        _RECONCILE_DRIFT_WARN = 0.50  # warn if internal vs actual diverges > $0.50
        _RECONCILE_DRIFT_CORRECT = 2.00  # auto-correct if divergence > $2.00
        _last_full_orphan_scan_ts = 0.0
        _FULL_ORPHAN_SCAN_INTERVAL = 120  # full balance sweep every 2min — 5m windows need fast detection
        while self._running:
            await asyncio.sleep(10)
            # Ping watchdog — proves event loop is alive to the daemon thread
            if _watchdog_ping is not None:
                _watchdog_ping[0] = time.monotonic()
            try:
                await self.orders.post_heartbeat()
                await self._sweep_residuals()
                # Periodic full scan: force_all=True every 5min catches orphans created
                # mid-session (not just near window-close). Without this, an orphan can
                # sit undetected for up to 13min (15m window) until the 120s horizon fires.
                _now_hb = time.time()
                if _now_hb - _last_full_orphan_scan_ts >= _FULL_ORPHAN_SCAN_INTERVAL:
                    logger.debug("HEARTBEAT: periodic full orphan scan (force_all=True)")
                    await self._window_end_balance_sweep(force_all=True)
                    _last_full_orphan_scan_ts = _now_hb
                else:
                    await self._window_end_balance_sweep()
                _hb_failures = 0  # reset on success

                # ── Hourly bankroll reconciliation ───────────────────────────
                # Compare internal capital estimate to actual Polymarket USDC balance.
                # Drift sources: fee estimation errors, orphan sells, crash-recovery gaps.
                # Auto-corrects large divergences; warns on small ones.
                now = time.time()
                has_open = bool(self.risk.open_positions)
                if (now - _last_reconcile_ts >= _RECONCILE_INTERVAL
                        and not CONFIG.dry_run
                        and not has_open):  # only reconcile when flat — open positions distort USDC
                    _last_reconcile_ts = now
                    actual_usdc = self.orders.fetch_usdc_balance()
                    if actual_usdc is not None:
                        internal = self.risk.bankroll.capital
                        drift = actual_usdc - internal
                        if abs(drift) >= _RECONCILE_DRIFT_WARN:
                            logger.warning(
                                "BANKROLL DRIFT: internal=$%.2f actual=$%.2f drift=%+.2f",
                                internal, actual_usdc, drift,
                            )
                        if abs(drift) >= _RECONCILE_DRIFT_CORRECT:
                            logger.warning(
                                "BANKROLL AUTO-CORRECT: $%.2f → $%.2f (drift=%+.2f)",
                                internal, actual_usdc, drift,
                            )
                            self.risk.bankroll.capital = actual_usdc
                            self.risk.bankroll._save()
                        else:
                            logger.debug(
                                "Bankroll reconcile OK: internal=$%.2f actual=$%.2f drift=%+.2f",
                                internal, actual_usdc, drift,
                            )

            except Exception as exc:
                _hb_failures += 1
                if _hb_failures >= 2:
                    logger.critical(
                        "Heartbeat CRITICAL failure #%d: %s — GTC orders may expire",
                        _hb_failures, exc,
                    )
                else:
                    logger.warning("Heartbeat failure #%d: %s", _hb_failures, exc)

    # ── Window-end CLOB balance sweep ─────────────────────────────────────────

    async def _window_end_balance_sweep(self, force_all: bool = False) -> None:
        """
        For every tracked updown token within 120s of window close, fetch the
        actual CLOB balance and force-sell any non-zero holding.

        Catches shares that survived partial cascades or came from sessions the
        bot didn't track — anything sitting in the wallet that will resolve at
        0 or 1 without being sold.

        force_all=True: bypass the 120s time window check — used at startup to
        immediately sell orphan tokens from previous sessions (otherwise they
        wait up to 13 minutes before the normal sweep catches them).
        """
        if CONFIG.dry_run:
            return
        now = time.time()
        _WINDOW_END_HORIZON = 120  # seconds before close to start checking

        for token_id, token in list(self.feed.tokens.items()):
            if token.market_type != "updown":
                continue
            if token.window_end_ts <= 0:
                continue
            time_to_close = token.window_end_ts - now
            # Only act in the final 120s window, or if already past close (up to 60s after),
            # OR if force_all=True (startup sweep — sell any untracked balance immediately).
            if not force_all and not (-60 <= time_to_close <= _WINDOW_END_HORIZON):
                continue

            # Rate-limit: don't hammer CLOB for the same token more than once per 30s
            _last_key = f"_webs_{token_id}"
            if now - self._open_meta.get(_last_key, 0) < 30:
                continue
            self._open_meta[_last_key] = now

            balance = self.orders.fetch_token_balance(token_id)
            if balance is None or balance < 0.05:
                continue

            asset = token.asset
            side = getattr(token, "side", "?")

            # Update tracked position's remaining_shares if we have one
            if token_id in self.risk.open_positions:
                pos = self.risk.open_positions[token_id]
                if abs(balance - pos.remaining_shares) > 0.05:
                    logger.warning(
                        "WINDOW-END SYNC %s/%s: tracked=%.4f CLOB=%.4f — correcting",
                        asset, side, pos.remaining_shares, balance,
                    )
                    pos.remaining_shares = round(balance, 4)
                # Let the normal exit loop handle it (will fire HARD_EXIT or FLOOR_SELL)
                continue

            # Orphaned balance — not in tracked positions. Force-sell immediately.
            if token_id in self._exit_in_progress:
                continue
            logger.warning(
                "WINDOW-END ORPHAN %s/%s: %.4f shares in CLOB wallet, not tracked — force-selling",
                asset, side, balance,
            )
            self._exit_in_progress.add(token_id)
            try:
                token_meta = self.feed.tokens.get(token_id)
                ob = self.feed.get_order_book(token_id)
                sell_price = ob.bids[0][0] if (ob and ob.bids) else 0.50
                orphan_fills = await self.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=balance,
                    current_price=sell_price,
                    reason="ORPHAN_SELL",
                    neg_risk=getattr(token_meta, "neg_risk", False),
                    tick_size=getattr(token_meta, "tick_size", "0.01"),
                    force_exit=True,
                )
                sold = sum(f.total_size for f in orphan_fills)
                avg_price = (
                    sum(f.avg_fill_price * f.total_size for f in orphan_fills) / sold
                    if sold > 0 else sell_price
                )
                if sold > 0:
                    logger.info(
                        "ORPHAN SOLD %s/%s: %.4f shares @ %.4f",
                        asset, side, sold, avg_price,
                    )
                    # Recover entry price from CLOB BUY history so PnL is real.
                    # Orphans arise when entry filled on Polymarket but wasn't tracked
                    # locally (CF block during confirmation). The CLOB has the buy fill.
                    _orphan_entry_price = 0.0
                    if not CONFIG.dry_run:
                        await asyncio.sleep(1.5)
                        try:
                            _all_fills = await asyncio.to_thread(
                                self.orders.fetch_recent_token_sells,
                                token_id,
                                time.time() - 900,  # last 15 min
                            )
                            # Buys are fills priced meaningfully below the exit price.
                            _buy_fills = [
                                (p, s) for p, s in _all_fills
                                if p < avg_price * 0.97
                            ]
                            if _buy_fills:
                                _b_sz  = sum(s for _, s in _buy_fills)
                                _b_val = sum(p * s for p, s in _buy_fills)
                                if _b_sz > 0:
                                    _orphan_entry_price = round(_b_val / _b_sz, 6)
                                    logger.info(
                                        "ORPHAN entry recovered from CLOB: %s/%s ep=%.4f "
                                        "(%d buy fill(s), %.4f shares)",
                                        asset, side, _orphan_entry_price,
                                        len(_buy_fills), _b_sz,
                                    )
                        except Exception as _ce:
                            logger.warning("ORPHAN CLOB entry lookup failed: %s", _ce)

                    self.analytics.record_orphan_sell(
                        token_id=token_id,
                        asset=asset,
                        side=side,
                        shares_sold=sold,
                        avg_exit_price=avg_price,
                        is_live=not CONFIG.dry_run,
                        avg_entry_price=_orphan_entry_price,
                    )
                    # Reconcile bankroll from actual CLOB USDC balance — ground truth.
                    # Avoids drift from double-counting or missed entry deductions.
                    if not CONFIG.dry_run:
                        await asyncio.sleep(2.0)
                        try:
                            _real_bal = await asyncio.to_thread(self.orders.fetch_usdc_balance)
                            if _real_bal is not None:
                                _old_cap = self.risk.bankroll.capital
                                self.risk.bankroll.capital = round(_real_bal, 4)
                                self.risk.bankroll._save()
                                logger.warning(
                                    "Post-orphan bankroll reconciled: $%.2f → $%.2f (delta=%+.2f)",
                                    _old_cap, _real_bal, _real_bal - _old_cap,
                                )
                            else:
                                logger.warning("Post-orphan USDC balance fetch returned None")
                        except Exception as _re:
                            logger.warning("Post-orphan bankroll reconcile failed: %s", _re)
                else:
                    logger.warning(
                        "ORPHAN SELL FAILED %s/%s: %.4f shares unsold",
                        asset, side, balance,
                    )
            except Exception as _e:
                logger.error("ORPHAN SELL error %s: %s", token_id[:12], _e)
            finally:
                self._exit_in_progress.discard(token_id)

    # ── Startup orphan sweep ──────────────────────────────────────────────────

    async def _startup_orphan_sweep(self) -> None:
        """
        On startup:
        1. Validate tracked positions — if CLOB balance = 0, the user sold manually
           last session. Close the position record immediately rather than tracking
           a ghost forever.
        2. Sell any untracked token balances from previous sessions.

        Waits 10s for feed to populate before scanning.
        """
        if CONFIG.dry_run:
            return
        await asyncio.sleep(10.0)
        logger.info("STARTUP ORPHAN SWEEP: validating tracked positions and orphan balances...")

        # Step 1: validate tracked positions have actual CLOB balances
        for token_id, pos in list(self.risk.open_positions.items()):
            try:
                balance = self.orders.fetch_token_balance(token_id)
                if balance is None:
                    logger.warning(
                        "STARTUP: can't verify balance for tracked %s/%s — will retry via normal loop",
                        pos.asset, pos.direction.name,
                    )
                    continue
                if balance < 0.05:
                    # Guard: if position was opened very recently, CLOB balance may not
                    # have propagated yet (fresh buy shows 0 for up to ~30s).
                    # Don't close a position that was just bought this session.
                    _pos_age_s = time.time() - pos.open_ts
                    if _pos_age_s < 120:
                        logger.warning(
                            "STARTUP: %s/%s balance=0 but position only %.0fs old — "
                            "CLOB propagation lag, skipping close, normal loop will handle",
                            pos.asset, pos.direction.name, _pos_age_s,
                        )
                        continue
                    # Shares are gone — sold last session (cascade or manual).
                    # Try CLOB history to recover actual exit price before closing flat.
                    logger.warning(
                        "STARTUP: %s/%s has 0 CLOB balance — querying CLOB history for exit price",
                        pos.asset, pos.direction.name,
                    )
                    _startup_exit_price = pos.entry_price  # fallback: flat
                    try:
                        _clob_sells = await asyncio.to_thread(
                            self.orders.fetch_recent_token_sells,
                            token_id,
                            pos.open_ts,
                        )
                        if _clob_sells:
                            _sz = sum(s for _, s in _clob_sells)
                            _val = sum(p * s for p, s in _clob_sells)
                            if _sz > 0:
                                _startup_exit_price = round(_val / _sz, 6)
                                logger.info(
                                    "STARTUP: %s/%s exit price recovered from CLOB → %.4f",
                                    pos.asset, pos.direction.name, _startup_exit_price,
                                )
                    except Exception as _ce:
                        logger.warning("STARTUP CLOB recovery %s failed: %s", token_id[:8], _ce)
                    pnl = self.risk.close_position(token_id, _startup_exit_price, "STARTUP_EXTERNALLY_SOLD")
                    meta = self._open_meta.get(token_id, {})
                    _sig = meta.get("signal") or SignalBreakdown(
                        direction=pos.direction, entry_price=pos.entry_price,
                        composite=0.0, confidence=0.0, breakout_score=0.0,
                        trend_score=0.0, volume_score=0.0, ob_score=0.0,
                        fee_zone=FeeZone.FAT_MIDDLE, external_boost=0.0,
                        reason="startup_externally_sold",
                    )
                    try:
                        self.analytics.record_trade(
                            token_id=token_id, asset=pos.asset, direction=pos.direction,
                            entry_price=pos.entry_price, exit_price=_startup_exit_price,
                            stake=pos.stake, shares=pos.shares,
                            entry_fill=meta.get("entry_fill"), exit_fills=[],
                            exit_reason="STARTUP_EXTERNALLY_SOLD", signal=_sig,
                            ts_open=meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                            capital_before=self.risk.bankroll.capital,
                            heat_check_active=False, consecutive_wins=0,
                            net_pnl_actual=pnl or 0.0,
                            market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                            is_live=not CONFIG.dry_run,
                            signal_source=meta.get("signal_source", "SNIPER"),
                            window_size_s=meta.get("window_size_s") or pos.window_seconds or 0,
                        )
                    except Exception as _e:
                        logger.error("record_trade STARTUP_EXTERNALLY_SOLD failed: %s", _e)
                    self._open_meta.pop(token_id, None)
                else:
                    _token_in_feed = token_id in self.feed.tokens
                    if not _token_in_feed:
                        # Shares confirmed on CLOB but token is no longer in the feed
                        # (window expired and was removed). The normal exit loop iterates
                        # self.feed.tokens only — it will never fire for this token.
                        # Force-sell immediately to recover the capital.
                        logger.warning(
                            "STARTUP: %s/%s has %.4f shares but token NOT in feed "
                            "(window expired?) — force-selling orphan",
                            pos.asset, pos.direction.name, balance,
                        )
                        self._exit_in_progress.add(token_id)
                        try:
                            ob = self.feed.get_order_book(token_id)
                            sell_price = ob.bids[0][0] if (ob and ob.bids) else 0.50
                            orphan_fills = await self.orders.cascade_sell(
                                token_id=token_id,
                                total_shares=balance,
                                current_price=sell_price,
                                reason="ORPHAN_SELL",
                                neg_risk=False,
                                tick_size="0.01",
                                force_exit=True,
                            )
                            sold = sum(f.total_size for f in orphan_fills)
                            avg_price = (
                                sum(f.avg_fill_price * f.total_size for f in orphan_fills) / sold
                                if sold > 0 else sell_price
                            )
                            if sold > 0:
                                logger.info(
                                    "STARTUP ORPHAN SOLD %s/%s: %.4f shares @ %.4f",
                                    pos.asset, pos.direction.name, sold, avg_price,
                                )
                                if not CONFIG.dry_run:
                                    _proceeds = round(sold * avg_price, 4)
                                    self.risk.bankroll.capital = round(
                                        self.risk.bankroll.capital + _proceeds, 4
                                    )
                                    self.risk.bankroll._save()
                                    logger.warning(
                                        "STARTUP ORPHAN PROCEEDS +$%.4f → cap=$%.2f",
                                        _proceeds, self.risk.bankroll.capital,
                                    )
                            else:
                                logger.warning(
                                    "STARTUP ORPHAN SELL FAILED %s/%s: %.4f shares unsold",
                                    pos.asset, pos.direction.name, balance,
                                )
                            self.risk.close_position(
                                token_id,
                                avg_price if sold > 0 else pos.entry_price,
                                "ORPHAN_SELL",
                            )
                            self._open_meta.pop(token_id, None)
                        except Exception as _oe:
                            logger.error(
                                "STARTUP ORPHAN SELL (tracked) failed for %s: %s",
                                token_id[:12], _oe,
                            )
                        finally:
                            self._exit_in_progress.discard(token_id)
                    else:
                        logger.info(
                            "STARTUP: %s/%s confirmed %.4f shares on CLOB — tracking continues",
                            pos.asset, pos.direction.name, balance,
                        )
            except Exception as _e:
                logger.error("STARTUP balance check failed for %s: %s", token_id[:12], _e)

        # Step 2: sell untracked orphan balances from previous sessions
        await self._window_end_balance_sweep(force_all=True)

        # Step 3: write recovery records for expired stage-1 positions.
        # These are positions where stage-1 sold 60% of shares but bot crashed before stage-2.
        # The window expired so we can't sell the remaining 40% — but we can log what we know.
        # stage1_sell_price was saved to disk by record_stage1_sell; remaining shares were
        # likely resolved on-chain. Record the stage-1 profit so WR/PnL stats are accurate.
        for r in self.risk._expired_stage1_positions:
            try:
                s1_price = r.get("stage1_sell_price", 0.0)
                entry = r["entry_price"]
                shares = r["shares"]
                remaining = r["remaining_shares"]
                s1_shares = round(shares - remaining, 4)
                if s1_price <= 0 or s1_shares <= 0:
                    logger.warning(
                        "RECOVERY SKIP %s/%s: missing stage-1 price (%.4f) or shares (%.4f) — "
                        "no stage1_sell_price saved (old version); skipping recovery record",
                        r["asset"], r["direction"], s1_price, s1_shares,
                    )
                    continue
                # Stage-1 was profitable (that's why it fired). Remaining 40% resolved on-chain.
                # Use entry_price as the conservative floor for remaining shares
                # (worst case: resolved at 0, they lost the 40% stake = entry * remaining).
                gross_s1 = s1_shares * (s1_price - entry)
                gross_remaining = remaining * (entry - entry)  # 0 — can't know resolution
                gross_pnl = round(gross_s1 + gross_remaining, 6)
                # Fee estimate: extreme odds for most SNIPER trades
                fee_rate = CONFIG.fees.extreme_fee_rate if entry < 0.30 or entry > 0.70 else CONFIG.fees.middle_fee_rate
                exit_notional = s1_price * s1_shares
                entry_notional = entry * shares
                fee_est = round((entry_notional + exit_notional) * fee_rate, 6)
                net_pnl = round(gross_pnl - fee_est, 6)
                now_ts = time.time()
                self.analytics._trade_counter += 1
                trade_id = f"T{self.analytics._trade_counter:05d}_{r['asset']}_{int(r['open_ts'])}_RECOVERED"
                self.analytics.last_trade_id = trade_id
                record = {
                    "trade_id": trade_id,
                    "token_id": r["token_id"],
                    "asset": r["asset"],
                    "direction": r["direction"],
                    "market_type": "updown",
                    "signal_source": "SNIPER",
                    "exit_reason": "STAGE1_RECOVERY",
                    "ts_open": r["open_ts"],
                    "ts_close": r.get("window_end_ts", now_ts),
                    "entry_price": entry,
                    "exit_price": s1_price,
                    "stake": r["stake"],
                    "shares": shares,
                    "gross_pnl": gross_pnl,
                    "fee_paid": fee_est,
                    "net_pnl": net_pnl,
                    "slippage_entry": 0.0,
                    "slippage_exit": 0.0,
                    "hold_seconds": round(r.get("window_end_ts", now_ts) - r["open_ts"], 1),
                    "hour_utc": int(time.gmtime(r["open_ts"]).tm_hour),
                    "window_size_s": r.get("window_size_s", 0),
                    "is_live": not CONFIG.dry_run,
                    "capital_before": self.risk.bankroll.capital - net_pnl,
                    "capital_after": self.risk.bankroll.capital,
                    "note": (
                        f"STAGE-1 RECOVERY: sold {s1_shares:.4f} of {shares:.4f} shares @ {s1_price:.4f}. "
                        f"Remaining {remaining:.4f} shares expired on-chain (resolution unknown). "
                        "Bot crashed between stage-1 and stage-2. PnL reflects stage-1 only."
                    ),
                }
                self.analytics._write_jsonl(CONFIG.trade_log, record)
                logger.warning(
                    "STAGE-1 RECOVERY %s/%s: stage-1 PnL=%.4f logged as %s "
                    "(remaining %.4f shares expired unlogged)",
                    r["asset"], r["direction"], net_pnl, trade_id, remaining,
                )
            except Exception as _e:
                logger.error("STAGE-1 RECOVERY failed for %s/%s: %s", r.get("asset"), r.get("direction"), _e)
        self.risk._expired_stage1_positions.clear()

        logger.info("STARTUP ORPHAN SWEEP: complete")

        # Second sweep at t+30s — catches tokens that weren't in self.feed.tokens
        # at the t+10s sweep because the feed loads asynchronously. Tokens for
        # windows that started recently often appear 15-25s after bot startup.
        asyncio.create_task(self._delayed_orphan_sweep())

    async def _delayed_orphan_sweep(self) -> None:
        """Second orphan sweep at t+30s after startup to catch late-loading tokens."""
        await asyncio.sleep(20.0)  # 10s (first sweep) + 20s = t+30s total
        logger.info("STARTUP ORPHAN SWEEP (delayed): scanning for late-loaded tokens...")
        await self._window_end_balance_sweep(force_all=True)
        logger.info("STARTUP ORPHAN SWEEP (delayed): complete")

    # ── 250s prewarm loop: refresh py_clob_client cache before 300s TTL expires ──

    async def _prewarm_loop(self) -> None:
        """Refresh neg_risk + fee_rate caches every 250s (TTL=300s in py_clob_client)."""
        while self._running:
            await asyncio.sleep(250)
            if not CONFIG.dry_run:
                self.orders.prewarm_token_caches(self.feed.tokens)

    # ── 30-min report loop ────────────────────────────────────────────────────

    async def _report_loop(self) -> None:
        while self._running:
            await asyncio.sleep(1800)
            self.analytics.inject_telemetry(
                connectivity=self.feed.connectivity_stats(),
                order_latency=self.orders.latency_stats(),
            )
            report = self.analytics.generate_claude_report()
            # Append buy attempt stats to the report
            failed = self._buy_tried - self._buy_filled
            fail_rate = failed / self._buy_tried if self._buy_tried else 0
            buy_lines = [
                "",
                "BUY EXECUTION",
                f"  Attempted:  {self._buy_tried}",
                f"  Filled:     {self._buy_filled}",
                f"  Failed:     {failed}  ({fail_rate:.0%})",
            ]
            if self._buy_failed_reasons:
                buy_lines.append("  Failure reasons:")
                for reason, count in sorted(self._buy_failed_reasons.items(),
                                            key=lambda x: -x[1]):
                    buy_lines.append(f"    {count}× {reason}")
            logger.info("\n%s\n%s", report, "\n".join(buy_lines))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _classify_path(
    r30: Optional[float],
    r60: Optional[float],
    max_adv_pct: float,
    hold_s: float,
    exit_reason: str,
    exit_price: float,
    entry_price: float,
) -> tuple:
    """
    Classify post-entry price path into SMOOTH_RUNNER / EARLY_CHOP / DEAD_DRIFT.

    Diagnostic label only — no entry/exit logic uses this output.

    Returns (path_class: str, confidence: int 0-100, reason: str).
    """
    ep = entry_price
    xp = exit_price
    exit_pct = (xp - ep) / ep * 100 if ep > 0 else 0.0
    _tp_exit = exit_reason in ("BOND_TP_95", "BOND_TP_95_EXT", "SNIPER_TP", "TP_STAGE1", "TP_STAGE2", "BOND_EXHAUSTION_EXIT", "BOND_TRAIL_SL")
    _sl_exit = "SL" in exit_reason or "STOP" in exit_reason or "PRICE_SL" in exit_reason

    # ── SMOOTH_RUNNER ────────────────────────────────────────────────────────
    # Immediate follow-through, no significant adverse excursion, TP likely.
    smooth_score = 0
    smooth_reasons = []

    if r30 is not None and r30 >= 10:
        smooth_score += 35
        smooth_reasons.append(f"r30={r30:+.1f}%≥+10%")
    elif r30 is not None and r30 >= 5:
        smooth_score += 15
        smooth_reasons.append(f"r30={r30:+.1f}%")

    if max_adv_pct < 10:
        smooth_score += 20
        smooth_reasons.append(f"max_adv={max_adv_pct:.1f}%<10%")

    if _tp_exit and exit_pct >= 15:
        smooth_score += 30
        smooth_reasons.append(f"TP exit +{exit_pct:.1f}%")

    if r60 is not None and r60 >= 15:
        smooth_score += 15
        smooth_reasons.append(f"r60={r60:+.1f}%≥+15%")

    # ── EARLY_CHOP ───────────────────────────────────────────────────────────
    # Significant adverse dip but recovery — OB noise / wick-driven.
    chop_score = 0
    chop_reasons = []

    if max_adv_pct >= 15 and max_adv_pct <= 50:
        chop_score += 35
        chop_reasons.append(f"max_adv={max_adv_pct:.1f}% (15–50%)")

    if r30 is not None and -15 <= r30 < 5:
        chop_score += 20
        chop_reasons.append(f"r30={r30:+.1f}% (noise range)")

    if _sl_exit and exit_pct > -50:
        # SL fired but not catastrophic — could be dirty-path exit
        chop_score += 20
        chop_reasons.append(f"SL but moderate exit {exit_pct:.1f}%")
    elif _tp_exit and max_adv_pct >= 15:
        # TP but had adverse excursion first
        chop_score += 25
        chop_reasons.append(f"TP after {max_adv_pct:.1f}% dip")

    if r60 is not None and r30 is not None and r60 > r30 and r30 < 0:
        chop_score += 20
        chop_reasons.append(f"recovery r30={r30:+.1f}%→r60={r60:+.1f}%")

    # ── DEAD_DRIFT ───────────────────────────────────────────────────────────
    # No sustained directional movement; flat path with micro-reversals.
    drift_score = 0
    drift_reasons = []

    if r30 is not None and -10 <= r30 <= 8:
        drift_score += 30
        drift_reasons.append(f"r30={r30:+.1f}% (flat)")

    if r60 is not None and -10 <= r60 <= 8:
        drift_score += 20
        drift_reasons.append(f"r60={r60:+.1f}% (flat)")

    if max_adv_pct < 15 and not _tp_exit and exit_pct < 15:
        drift_score += 25
        drift_reasons.append("no expansion, no TP")

    if hold_s >= 60 and exit_pct < 10 and not _tp_exit:
        drift_score += 15
        drift_reasons.append(f"held {hold_s:.0f}s without direction")

    # ── Decision ─────────────────────────────────────────────────────────────
    if r30 is None and r60 is None:
        # Insufficient data (trade < 30s) — use exit outcome only
        if _tp_exit and exit_pct >= 15:
            return "SMOOTH_RUNNER", 50, f"short hold, TP +{exit_pct:.1f}% (no snaps)"
        elif _sl_exit:
            return "EARLY_CHOP", 40, f"short hold, SL {exit_pct:.1f}% (no snaps)"
        return "DEAD_DRIFT", 30, f"short hold {hold_s:.0f}s, no snaps"

    scores = {
        "SMOOTH_RUNNER": smooth_score,
        "EARLY_CHOP": chop_score,
        "DEAD_DRIFT": drift_score,
    }
    winner = max(scores, key=scores.__getitem__)
    conf = min(100, scores[winner])
    if winner == "SMOOTH_RUNNER":
        return winner, conf, "; ".join(smooth_reasons) or "smooth"
    elif winner == "EARLY_CHOP":
        return winner, conf, "; ".join(chop_reasons) or "chop"
    else:
        return winner, conf, "; ".join(drift_reasons) or "drift"


async def _main() -> None:
    bot = KlausBot()

    loop = asyncio.get_running_loop()

    def _shutdown(sig):
        logger.info("Shutdown signal %s received", sig)
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, _shutdown, s)

    await bot.run()


if __name__ == "__main__":
    import atexit

    _PID_FILE = os.path.join(os.path.dirname(__file__), "logs", "bot.pid")

    # Refuse to start if another instance is already running.
    if os.path.exists(_PID_FILE):
        try:
            _existing_pid = int(open(_PID_FILE).read().strip())
            os.kill(_existing_pid, 0)          # signal 0 = existence check
            print(
                f"ERROR: bot already running as PID {_existing_pid}. "
                f"Kill it first: kill {_existing_pid}",
                file=sys.stderr,
            )
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            pass  # stale PID file — previous run didn't clean up

    with open(_PID_FILE, "w") as _f:
        _f.write(str(os.getpid()))

    @atexit.register
    def _remove_pid():
        try:
            os.unlink(_PID_FILE)
        except FileNotFoundError:
            pass

    asyncio.run(_main())
