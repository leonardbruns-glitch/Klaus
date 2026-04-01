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
from typing import Dict, Optional, Set

from config import CONFIG
from data.feeds import PolymarketFeed
from strategy.momentum import MomentumScorer, Direction, FeeZone, SignalBreakdown, calculate_tp_sl
from strategy.window_sniper import WindowSniper, _session_min_delta
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

        # Pre-warm py_clob_client caches (neg_risk + fee_rate) for all tracked tokens.
        # Without this, the first order per token triggers GET /neg-risk + GET /fee-rate
        # before submitting, adding ~2s of latency and causing the sniper to miss fills.
        if not CONFIG.dry_run:
            self.orders.prewarm_token_caches(self.feed.tokens)

    async def stop(self) -> None:
        self._running = False
        await self.feed.stop()
        await self.orders.stop()
        report = self.analytics.generate_claude_report()
        logger.info("\nFINAL REPORT:\n%s", report)

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        await self.start()

        ob_task = asyncio.create_task(self._ob_scan_loop())
        signal_task = asyncio.create_task(self._signal_loop())
        report_task = asyncio.create_task(self._report_loop())
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        research_task = asyncio.create_task(self.research.run())
        prewarm_task = asyncio.create_task(self._prewarm_loop())

        try:
            await asyncio.gather(ob_task, signal_task, report_task, heartbeat_task, research_task, prewarm_task)
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
            if not isinstance(ob, object) or ob is None or isinstance(ob, Exception):
                continue
            current_price = ob.bids[0][0] if len(ob.bids) > 0 else ob.mid

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

            decision = self.risk.check_exit_conditions(token_id, current_price)

            if decision is None:
                if pos.window_end_ts > 0:
                    time_held = now - pos.open_ts
                    remaining = max(0.0, pos.window_end_ts - now)
                    move_pct = (current_price - pos.entry_price) / pos.entry_price

                    # ── LLM SL-breach override: wick vs genuine reversal ──────
                    # When the SL timer is running but hasn't expired, ask Claude once.
                    # T00042: 0.59→0.44 in 25s (bot-painted stop), price recovered 0.78.
                    # Mechanical timer is blind to this. LLM sees VPIN/spot context.
                    if pos.sl_breach_ts > 0 and not pos.sl_breach_llm_queried:
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
                            logger.info(
                                "LLM CONFIRMS EXIT %s/%s (conf=%.2f move=%+.1f%%) — not a wick | %s",
                                pos.asset, pos.direction.name, conf, move_pct * 100, adv_reason,
                            )
                            await self._exit_position(token_id, current_price, "LLM_CONFIRMS_SL")
                            continue
                        else:
                            logger.info(
                                "LLM SL CONSULT %s/%s → %s conf=%.2f — letting timer run | %s",
                                pos.asset, pos.direction.name, action, conf, adv_reason,
                            )

                    # ── LLM exit advisor: manage the uncertain zone ───────────
                    # Rule-based exits haven't fired. Ask Claude when:
                    #   - Held > 15s (entry confirmed, not a noise tick)
                    #   - Move between -35% and +22% (covers SL approach zone too)
                    #   - Window has > 60s remaining (enough time to act)
                    # Claude reasons holistically: P&L, momentum, VPIN, session.
                    # LLM exit gate: 15m trades need 3 min before LLM can exit.
                    # T00050: LLM_EXIT_NOW at 80s was premature — 69% window remaining.
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
                        if action == "EXIT_NOW" and conf >= 0.65:
                            logger.info(
                                "LLM EXIT NOW %s/%s (conf=%.2f move=%+.1f%%) | %s",
                                pos.asset, pos.direction.name,
                                conf, move_pct * 100, adv_reason,
                            )
                            await self._exit_position(token_id, current_price, "LLM_EXIT_NOW")
                            continue
                        elif action == "TIGHTEN_STOP" and tighten_sl is not None and conf >= 0.60:
                            if pos.dynamic_sl_override == 0.0 or tighten_sl > pos.dynamic_sl_override:
                                logger.info(
                                    "LLM TIGHTEN STOP %s/%s → -%.0f%% (was -%.0f%%) | %s",
                                    pos.asset, pos.direction.name,
                                    tighten_sl * 100,
                                    pos.dynamic_sl_override * 100,
                                    adv_reason,
                                )
                                pos.dynamic_sl_override = tighten_sl
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

    async def _signal_loop(self) -> None:
        _consecutive_errors = 0
        while self._running:
            try:
                await self.feed.poll_order_books()
                await self.feed.update_bars()
                await self._scan_for_signals()
                _consecutive_errors = 0  # reset on success
            except Exception as exc:
                _consecutive_errors += 1
                tb = traceback.format_exc()
                if _consecutive_errors > 3:
                    logger.critical(
                        "Signal loop CRITICAL: %d consecutive errors — bot is blind. "
                        "Last error: %s\n%s",
                        _consecutive_errors, exc, tb,
                    )
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
                    sniper_queue.append((token_id, token, sniper_sig, tpsl, decision, ext))
                continue  # updown token handled — skip momentum path

            elif token.market_type == "updown":
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
                    "elapsed_pct": sig.elapsed_pct,
                    "window_seconds": tok.window_seconds,
                    "vpin_score": (ex.vpin_score if ex else None),
                    "vpin_direction": (ex.vpin_direction if ex else None),
                }
                for tid, tok, sig, tpsl, dec, ex in sniper_queue
            ]
            briefing = await self.macro_engine.market_briefing(
                candidates=briefing_candidates,
                open_count=len(self.risk.open_positions),
                capital=self.risk.bankroll.capital,
            )

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

                if llm_decision == "SKIP" and llm_conf >= 0.80:
                    logger.info(
                        "  └─ LLM VETO %s/%s (conf=%.2f): %s",
                        token.asset, token.side, llm_conf, llm_reason,
                    )
                    continue

                logger.info(
                    "  └─ SNIPER ENTER %s/%s [p=%d conf=%.2f] | entry=%.4f edge=%.3f | %s",
                    token.asset, token.side,
                    b.get("priority", 99), llm_conf,
                    signal.entry_price, signal.edge,
                    llm_reason or signal.reason,
                )
                await self._enter_position(token_id, token.asset, signal, tpsl, decision)

    # ── Entry ─────────────────────────────────────────────────────────────────

    async def _enter_position(self, token_id, asset, signal, tpsl, decision) -> None:
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
            "window_size_s": getattr(token, "window_seconds", 0),
            "spot_at_entry": spot_at_entry,
            "pre_entry_momentum_pct": pre_entry_momentum_pct,
            "ob_depth_at_entry": ob_depth_at_entry,
            "signal_to_fill_ms": signal_to_fill_ms,
        }

    # ── Exit helpers ──────────────────────────────────────────────────────────

    def _calc_exit_price(self, exit_fills, fallback: float) -> float:
        total_size = sum(f.total_size for f in exit_fills)
        return (
            sum(f.avg_fill_price * f.total_size for f in exit_fills) / total_size
            if exit_fills and total_size > 0 else fallback
        )

    async def _partial_exit(self, token_id: str, live_price: float, reason: str) -> None:
        """Stage-1: sell 60% single-shot if 40% residual is CLOB-sellable, else sell 100%."""
        pos = self.risk.open_positions.get(token_id)
        if not pos:
            return

        # P6: changed 95/5 split → 60/40 split to let winning trades run to Stage-2 (+45%).
        # Previous 5% residual was ~$0.10-0.25 = permanent dust, contributing nothing.
        # 40% residual at current stake (~$4) = $1.60-2.40 = meaningful Stage-2 upside.
        # P5: force_exit=True makes cascade single-shot (no 3-tranche CLOB lag issue).
        residual_value = pos.remaining_shares * 0.40 * live_price
        sell_pct = 0.60 if residual_value >= 1.50 else 1.0
        if sell_pct == 1.0:
            logger.info(
                "Stage-1 selling 100%% — 40%% residual=$%.2f < $1.50 CLOB minimum (dust avoided)",
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

        self.risk.record_stage1_sell(token_id, sold)
        # Store stage-1 fills so analytics can compute accurate weighted exit price
        meta = self._open_meta.get(token_id)
        if meta is not None:
            meta.setdefault("stage1_fills", []).extend(exit_fills)
        logger.info(
            "STAGE-1 %s %s | sold=%.4f @ ~%.4f | reason=%s",
            pos.asset, pos.direction.name, sold, live_price, reason,
        )

        # ── Post-stage1 balance verification ─────────────────────────────────
        # The cascade splits into 3 tranches. The 3rd tranche frequently fails
        # because CLOB reports a stale balance (lag after the first two fills).
        # Rather than waiting for the 60s background sweep, verify immediately:
        # wait 1s for CLOB to reconcile, then fetch actual balance and sell it.
        if not CONFIG.dry_run:
            await asyncio.sleep(1.0)
            clob_balance = self.orders.fetch_token_balance(token_id)
            if clob_balance is not None and clob_balance > 0.10:
                logger.info(
                    "POST-STAGE1 SWEEP %s: CLOB shows %.4f shares still held — selling now",
                    pos.asset, clob_balance,
                )
                token_meta = self.feed.tokens.get(token_id)
                sweep_fills = await self.orders.cascade_sell(
                    token_id=token_id,
                    total_shares=clob_balance,
                    current_price=live_price,
                    reason="POST_STAGE1_SWEEP",
                    neg_risk=getattr(token_meta, "neg_risk", False),
                    tick_size=getattr(token_meta, "tick_size", "0.01"),
                    force_exit=True,
                )
                swept = sum(f.total_size for f in sweep_fills)
                if swept > 0:
                    self.risk.record_stage1_sell(token_id, swept)
                    if meta is not None:
                        meta.setdefault("stage1_fills", []).extend(sweep_fills)
                    logger.info(
                        "POST-STAGE1 SWEEP %s: sold %.4f more shares (total stage-1: %.4f)",
                        pos.asset, swept, sold + swept,
                    )
                else:
                    logger.warning(
                        "POST-STAGE1 SWEEP %s: %.4f shares unsold — CLOB still lagging, "
                        "stage-2 will handle",
                        pos.asset, clob_balance,
                    )

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
                        capital_before=self.risk.bankroll.summary()["bankroll"] - ghost_pnl,
                        heat_check_active=_ghost_meta.get("heat_check", False),
                        consecutive_wins=_ghost_meta.get("consecutive_wins", 0),
                        net_pnl_actual=ghost_pnl,
                        market_type=getattr(self.feed.tokens.get(token_id), "market_type", "unknown"),
                        is_live=not CONFIG.dry_run,
                        signal_source=_ghost_meta.get("signal_source", "SNIPER"),
                        window_size_s=_ghost_meta.get("window_size_s", 0),
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
            pnl = self.risk.close_position(token_id, exit_price, "EXTERNALLY_SOLD")
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
                capital_before = self.risk.bankroll.summary()["bankroll"] - pnl
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
                        exit_reason="EXTERNALLY_SOLD",
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
                        window_size_s=_ext_meta.get("window_size_s", 0),
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

        # Guard 1b: PROFIT_2 sold nothing — CLOB rejected residual (sub-$1 notional
        # or network error). Keep position open so HARD_EXIT can force-close it.
        # Root cause: stage-1 CLOB balance adjustment leaves more shares than expected
        # (e.g. 0.9 instead of 0.245), and sub-$1 notional fails at the exchange.
        _DUST_SHARES = 0.10           # below this, accept residual as done
        if this_sell <= 0 and stage1_done and expected_this_sell > _DUST_SHARES:
            if token_id in self.risk.open_positions:
                self.risk.open_positions[token_id].hard_exit_triggered = False
            logger.warning(
                "PROFIT_2 sold 0 of %.4f remaining %s shares — keeping open, "
                "HARD_EXIT will force-close (BTC-residual-dust bug)",
                expected_this_sell, pos.asset,
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
        # Capture full share count before close_position pops pos from dict.
        all_shares = pos.shares

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
                    window_size_s=meta.get("window_size_s", 0),
                    spot_at_entry=meta.get("spot_at_entry", 0.0),
                    spot_at_exit=spot_at_exit,
                    signal_to_fill_ms=meta.get("signal_to_fill_ms", 0.0),
                    ob_depth_at_entry=meta.get("ob_depth_at_entry", 0.0),
                    pre_entry_momentum_pct=meta.get("pre_entry_momentum_pct", 0.0),
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
        # Logs to logs/post_exit.jsonl for strategy analysis.
        asyncio.create_task(self._track_post_exit(
            token_id=token_id,
            trade_id=self.analytics.last_trade_id,
            asset=pos.asset,
            direction=pos.direction.name,
            exit_price=analytics_exit_price,
            exit_reason=reason,
            entry_price=pos.entry_price,
        ))

    async def _track_post_exit(
        self,
        token_id: str,
        trade_id: str,
        asset: str,
        direction: str,
        exit_price: float,
        exit_reason: str,
        entry_price: float,
    ) -> None:
        """Sample token price at T+30s, T+60s, T+120s after exit.
        Tells us whether the exit was correct (price continued) or premature (price recovered).
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

        if not any(v for v in samples.values()):
            return

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
            **samples,
            "move_from_exit_pct": move_from_exit,
        }

        try:
            os.makedirs("logs", exist_ok=True)
            with open(log_path, "a") as f:
                f.write(_json.dumps(record) + "\n")
            verdict = ""
            for k, m in move_from_exit.items():
                if m is not None:
                    if exit_reason in ("STOP_LOSS", "LLM_CONFIRMS_SL", "LLM_TIGHT_SL(8%)", "LLM_EXIT_NOW"):
                        verdict = "EXIT_CORRECT" if m < 0 else "EXIT_PREMATURE"
                    else:
                        verdict = "EXIT_CORRECT" if m >= 0 else "EXIT_EARLY"
                    break
            logger.info(
                "POST_EXIT %s/%s [%s] | exit=%.4f | +30s=%.4f +60s=%.4f +120s=%.4f | %s",
                asset, direction, exit_reason,
                exit_price,
                samples.get("t30s") or 0,
                samples.get("t60s") or 0,
                samples.get("t120s") or 0,
                verdict,
            )
        except Exception as exc:
            logger.debug("post_exit log failed: %s", exc)

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
                                capital_before=self.risk.bankroll.summary()["bankroll"] - _res_pnl,
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

    async def _heartbeat_loop(self) -> None:
        """Keep CLOB session alive; prevents silent GTC order cancellation."""
        _hb_failures = 0
        while self._running:
            await asyncio.sleep(10)
            try:
                await self.orders.post_heartbeat()
                await self._sweep_residuals()
                await self._window_end_balance_sweep()
                _hb_failures = 0  # reset on success
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

    async def _window_end_balance_sweep(self) -> None:
        """
        For every tracked updown token within 120s of window close, fetch the
        actual CLOB balance and force-sell any non-zero holding.

        Catches shares that survived partial cascades or came from sessions the
        bot didn't track — anything sitting in the wallet that will resolve at
        0 or 1 without being sold.

        Also runs at startup (called once with window_seconds=0 guard bypassed)
        to sell orphans from previous sessions.
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
            # Only act in the final 120s window, or if already past close (up to 60s after)
            if not (-60 <= time_to_close <= _WINDOW_END_HORIZON):
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
                else:
                    logger.warning(
                        "ORPHAN SELL FAILED %s/%s: %.4f shares unsold",
                        asset, side, balance,
                    )
            except Exception as _e:
                logger.error("ORPHAN SELL error %s: %s", token_id[:12], _e)
            finally:
                self._exit_in_progress.discard(token_id)

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
    asyncio.run(_main())
