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
from strategy.window_sniper import WindowSniper, SniperBlock, _session_min_delta, CONTRARIAN_MAX_ASK
from analytics.shadow_log import log_shadow_result
from risk.manager import RiskManager
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

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await self.feed.start()
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
                            "BANKROLL SYNC: tracked=$%.2f  actual=$%.2f  delta=%+$.2f — syncing to actual",
                            tracked, real_balance, delta,
                        )
                    else:
                        logger.info(
                            "Bankroll verified: tracked=$%.2f matches actual=$%.2f",
                            tracked, real_balance,
                        )
                    self.risk.bankroll.capital = real_balance
                    self.risk.bankroll._save()
                else:
                    logger.warning("BANKROLL SYNC failed: fetch_usdc_balance returned None — using tracked=$%.2f", self.risk.bankroll.capital)

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

            _pos_ext = self._last_ext_signals.get(pos.asset)
            decision = self.risk.check_exit_conditions(token_id, current_price, ext=_pos_ext)

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
        now = time.time()
        # Per-asset debounce — feeds.py debounces at 1.5s, this adds a session-level guard
        last = self._last_spike_ts.get(asset, 0)
        if now - last < 1.5:
            return
        self._last_spike_ts[asset] = now

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

    async def _signal_loop(self) -> None:
        _consecutive_errors = 0
        _entries_blocked = False
        while self._running:
            try:
                await self.feed.poll_order_books()
                await self.feed.update_bars()
                if _entries_blocked:
                    logger.info("Signal loop recovered — entries unblocked")
                    _entries_blocked = False
                _consecutive_errors = 0  # reset on success
                await self._scan_for_signals()
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

    async def _scan_for_signals(self) -> None:

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

        # Fetch optional external signals for all assets in parallel
        ext_results = await asyncio.gather(
            *[self.feed.fetch_external_signals(a) for a in CONFIG.markets.tracked_assets],
            return_exceptions=True,
        )
        ext_signals = {
            asset: (r if not isinstance(r, Exception) else None)
            for asset, r in zip(CONFIG.markets.tracked_assets, ext_results)
        }

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

            elif token.market_type == "updown":
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

                logger.info(
                    "  └─ SNIPER ENTER %s/%s [p=%d conf=%.2f] | entry=%.4f edge=%.3f | %s",
                    token.asset, token.side,
                    b.get("priority", 99), llm_conf,
                    signal.entry_price, signal.edge,
                    llm_reason or signal.reason,
                )
                await self._enter_position(token_id, token.asset, signal, tpsl, decision,
                                           llm_rec=llm_decision, llm_rec_conf=llm_conf)

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
            return

        # Slippage guard: if fill is >10¢ below limit, the market moved hard against
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
            # Immediately sell back what we just bought to recover capital
            await self.orders.cascade_sell(
                token_id=token_id,
                shares=fill.total_size,
                current_price=fill.avg_fill_price,
                reason="SLIPPAGE_ABORT",
                neg_risk=getattr(self.feed.tokens.get(token_id), "neg_risk", False),
                tick_size=getattr(self.feed.tokens.get(token_id), "tick_size", "0.01"),
            )
            self.risk._pending_assets.discard(asset)  # release lock on slippage abort
            return

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
        }

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
        exit_fills = await self.orders.cascade_sell(
            token_id=token_id,
            total_shares=pos.remaining_shares,
            current_price=live_price,
            reason=reason,
            neg_risk=getattr(token_meta, "neg_risk", False),
            tick_size=getattr(token_meta, "tick_size", "0.01"),
            force_exit=True,  # full exits must always succeed regardless of notional value
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
        ghost_detected = any(
            "GHOST_POSITION" in (getattr(r, "error", "") or "")
            for r in exit_fills
        )
        if ghost_detected:
            logger.error(
                "GHOST POSITION purged: %s/%s — stake=$%.2f recorded as total loss. "
                "Cancel-race false positive in earlier session.",
                pos.asset, pos.direction.name, pos.stake,
            )
            ghost_pnl = self.risk.close_position(token_id, 0.0, "GHOST_POSITION", shares_override=pos.shares)
            _ghost_meta = self._open_meta.pop(token_id, {})
            self._pos_log_ts.pop(token_id, None)
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
            # Use the sell_price embedded in the error string (the price the cascade
            # was attempting when it detected dust). This reflects what the shares
            # were actually sold at, not the decayed live_price at detection time.
            import re as _re
            exit_price = live_price
            for _r in exit_fills:
                _err = getattr(_r, "error", "") or ""
                _m = _re.search(r'price=([0-9.]+)', _err)
                if _m:
                    exit_price = float(_m.group(1))
                    break
            exit_price = exit_price if exit_price > 0 else pos.entry_price
            logger.warning(
                "EXTERNALLY_SOLD purged: %s/%s — closing at sell_price %.4f. "
                "Shares already sold externally, stopping retry loop.",
                pos.asset, pos.direction.name, exit_price,
            )
            pnl = self.risk.close_position(token_id, exit_price, reason)
            _ext_meta = self._open_meta.pop(token_id, {})
            self._pos_log_ts.pop(token_id, None)
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
                    )
                except Exception as _rec_exc:
                    logger.error("record_trade EXTERNALLY_SOLD failed: %s", _rec_exc)
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
                )
            except Exception as _rec_exc:
                logger.error("record_trade failed (trade still closed): %s", _rec_exc)

        self._open_meta.pop(token_id, None)
        self._pos_log_ts.pop(token_id, None)
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
    ) -> None:
        """Sample token price at T+30s, T+60s, T+120s after exit.
        For SL exits: also samples at window_end_ts+60s to capture window resolution outcome.
        Tells us whether the exit was correct (price continued) or premature (price recovered).
        Logs 'resolved_correctly' — key metric for diagnosing premature SL exits.
        """
        import json as _json
        log_path = os.path.join("logs", "post_exit.jsonl")
        samples = {}
        elapsed = 0
        for delay in (30, 60, 120):
            await asyncio.sleep(delay - elapsed)
            elapsed = delay
            try:
                token = self.feed.tokens.get(token_id)
                if token and hasattr(token, "best_ask") and token.best_ask > 0:
                    price = token.best_ask
                else:
                    ob = self.feed._order_books.get(token_id, {})
                    price = ob.get("ask", 0.0) if ob else 0.0
                samples[f"t{delay}s"] = round(price, 4)
            except Exception:
                samples[f"t{delay}s"] = None

        # ── Resolution sample: window_end + 60s ────────────────────────────────
        # Only for SL exits. At this point the market has resolved (or is very close).
        # window_outcome_price: token price at window_end+60s for ALL trades.
        # entered_correctly: True if our token price ≥ 0.80 at resolution (we predicted right).
        # Applies regardless of how we exited — profit, SL, hard exit, trail stop.
        window_outcome_price = None
        entered_correctly = None
        resolution_delay_s = None
        _is_sl_exit = exit_reason.startswith("STOP_LOSS") or exit_reason in (
            "CIRCUIT_BREAKER", "TRAIL_STOP", "STOP_LOSS_EXT",
            "VELOCITY_EXIT", "SL_15S", "PRICE_FLOOR", "RATCHET_SL",
        ) or "TIGHT_SL" in exit_reason
        if window_end_ts > 0:
            now_ts = time.time()
            wait_until = window_end_ts + 60
            wait_s = max(0.0, wait_until - now_ts)
            if wait_s <= 900:  # skip if window ended >15 min ago (stale, bot was likely down)
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
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

        # Always write the record — even if price samples failed (e.g. resolved token
        # already removed from feed). Exit metadata alone is useful for analysis.
        _has_price_data = any(v for v in samples.values()) or window_outcome_price is not None
        if not _has_price_data:
            logger.debug("post_exit: no price samples for %s [%s], writing metadata-only record", asset, exit_reason)

        # Was the exit correct?
        # For a win exit: price should stay high or go higher (exit was right)
        # For a loss exit: price should continue falling (exit was right) or recover (premature)
        move_from_exit = {}
        for k, p in samples.items():
            if p and exit_price > 0:
                move_from_exit[k] = round((p - exit_price) / exit_price * 100, 2)

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
            "move_from_exit_pct": move_from_exit,
            # Window resolution — populated for all trades
            "window_outcome_price": window_outcome_price,
            "entered_correctly": entered_correctly,   # True/False/None(stale)
            "resolution_delay_s": resolution_delay_s,
            "window_end_ts": window_end_ts if window_end_ts > 0 else None,
        }

        try:
            os.makedirs("logs", exist_ok=True)
            with open(log_path, "a") as f:
                f.write(_json.dumps(record) + "\n")
            verdict = ""
            for k, m in move_from_exit.items():
                if m is not None:
                    if _is_sl_exit:
                        verdict = "EXIT_CORRECT" if m < 0 else "EXIT_PREMATURE"
                    else:
                        verdict = "EXIT_CORRECT" if m >= 0 else "EXIT_EARLY"
                    break
            _outcome_str = (
                " outcome=%.4f entered_correctly=%s" % (window_outcome_price, entered_correctly)
                if window_outcome_price is not None else ""
            )
            logger.info(
                "POST_EXIT %s/%s [%s] | exit=%.4f | +30s=%.4f +60s=%.4f +120s=%.4f | %s%s",
                asset, direction, exit_reason,
                exit_price,
                samples.get("t30s") or 0,
                samples.get("t60s") or 0,
                samples.get("t120s") or 0,
                verdict, _outcome_str,
            )
        except Exception as exc:
            logger.debug("post_exit log failed: %s", exc)

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
        while self._running:
            await asyncio.sleep(10)
            # Ping watchdog — proves event loop is alive to the daemon thread
            if _watchdog_ping is not None:
                _watchdog_ping[0] = time.monotonic()
            try:
                await self.orders.post_heartbeat()
                await self._sweep_residuals()
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
                    self.analytics.record_orphan_sell(
                        token_id=token_id,
                        asset=asset,
                        side=side,
                        shares_sold=sold,
                        avg_exit_price=avg_price,
                        is_live=not CONFIG.dry_run,
                    )
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
                    # Shares are gone — sold manually last session. Close the record.
                    logger.warning(
                        "STARTUP: %s/%s has 0 CLOB balance (manually sold) — purging tracked position",
                        pos.asset, pos.direction.name,
                    )
                    pnl = self.risk.close_position(token_id, pos.entry_price, "STARTUP_EXTERNALLY_SOLD")
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
                            entry_price=pos.entry_price, exit_price=pos.entry_price,
                            stake=pos.stake, shares=pos.shares,
                            entry_fill=meta.get("entry_fill"), exit_fills=[],
                            exit_reason="STARTUP_EXTERNALLY_SOLD", signal=_sig,
                            ts_open=meta.get("ts_open", pos.open_ts), ts_close=time.time(),
                            capital_before=self.risk.bankroll.capital,
                            heat_check_active=False, consecutive_wins=0,
                            net_pnl_actual=0.0,
                            market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                            is_live=not CONFIG.dry_run,
                            signal_source=meta.get("signal_source", "SNIPER"),
                            window_size_s=meta.get("window_size_s") or pos.window_seconds or 0,
                        )
                    except Exception as _e:
                        logger.error("record_trade STARTUP_EXTERNALLY_SOLD failed: %s", _e)
                    self._open_meta.pop(token_id, None)
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
