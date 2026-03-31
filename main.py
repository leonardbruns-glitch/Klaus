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
from typing import Dict, Optional, Set

from config import CONFIG
from data.feeds import PolymarketFeed
from strategy.momentum import MomentumScorer, Direction, FeeZone, SignalBreakdown, calculate_tp_sl
from strategy.window_sniper import WindowSniper
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
        # GUARD: skip sync when positions exist from a previous session.
        # The USDC balance only reflects unspent cash — it does NOT include the
        # value of open token positions. Syncing while positions are open would
        # set capital = (capital − value_of_open_tokens), incorrectly lowering it.
        if not CONFIG.dry_run and not self.risk.open_positions:
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
                continue

            if decision.partial:
                # Stage-1: sell 95 %, leave 5 % riding
                await self._partial_exit(token_id, current_price, decision.reason)
            else:
                await self._exit_position(token_id, current_price, decision.reason)

    # ── 5-second signal loop: scan for new entries ────────────────────────────

    async def _signal_loop(self) -> None:
        while self._running:
            try:
                await self.feed.poll_order_books()
                await self.feed.update_bars()
                await self._scan_for_signals()
            except Exception as exc:
                logger.error("Signal loop error: %s", exc)
            await asyncio.sleep(CONFIG.markets.scan_interval)

    async def _scan_for_signals(self) -> None:
        if self.risk.bankroll.is_halted:
            logger.warning("Trading HALTED — daily loss limit reached")
            return

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
        macro_signal = await self.macro_engine.tick(
            btc_spot, vpin_score=btc_vpin, vpin_direction=btc_vpin_dir
        )
        if macro_signal is None:
            macro_signal = self.macro_engine.get_signal()  # use cached if still valid
        if macro_signal:
            # Inject signed boost into ALL asset ext signals
            # BTC moves propagate to ETH/SOL within 10–30s (correlated assets)
            for asset in CONFIG.markets.tracked_assets:
                ext = ext_signals.get(asset)
                if ext is not None:
                    ext.macro_boost = macro_signal.boost_for_direction_yes()

        # ── Cross-asset cascade: score all tokens, find lead signals ─────────
        # When a strong leader (BTC) fires, follower assets (ETH, SOL) get a
        # reduced effective min_score to catch the correlated wave.
        lead_assets: Set[str] = set()
        all_scores: Dict[str, float] = {}
        for token_id, token in self.feed.tokens.items():
            bars_5m = self.feed.get_bars_5m(token_id, n=30)
            bars_15m = self.feed.get_bars_15m(token_id, n=30)
            ob = self.feed.get_order_book(token_id)
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

            bars_5m = self.feed.get_bars_5m(token_id, n=30)
            bars_15m = self.feed.get_bars_15m(token_id, n=30)
            ob = self.feed.get_order_book(token_id)
            ext = ext_signals.get(token.asset)

            # ── Window Sniper: primary signal for updown markets ─────────────
            # Detects mid-window mispriced certainty (fair value vs token ask).
            # Fires when: 25–80% elapsed, asset moved >0.06%, edge ≥ 0.02–0.04.
            # SniperSignal is compatible with risk manager (same fields: composite,
            # confidence, entry_price, direction, fee_zone, reason).
            sniper_sig = None
            if token.market_type == "updown":
                sniper_sig = self.sniper.score(token, ob, ext, now=time.time())

            if sniper_sig is not None:
                # Sniper fired — use it as the signal; skip momentum scorer
                signal = sniper_sig
                signal_source = "SNIPER"
            elif token.market_type == "updown":
                # Sniper didn't fire on this updown token → skip entirely.
                # Momentum scorer on updown markets has confirmed ZERO edge:
                # 19 live trades, WR=36.8%, losses score HIGHER than wins (0.531 vs 0.511).
                # Breakout and trend signals are anti-predictive on updown markets.
                # Only the Window Sniper (fair-value model) is allowed to enter updown.
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

            # Log every token scored, including NO_TRADE (for visibility)
            logger.info(
                "SCAN [%s] %s/%s | score=%.2f conf=%.2f entry=%.4f dir=%s | %s",
                signal_source,
                token.asset, token.side,
                signal.composite, signal.confidence,
                signal.entry_price, signal.direction.name,
                signal.reason or "no signal",
            )

            # Lag research: record Binance price + Polymarket price every scan.
            # No trading logic affected. Used by analytics/lag_analysis.py.
            if token.market_type == "updown" and ext is not None:
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

            if signal.direction == Direction.NO_TRADE:
                continue

            # Route YES tokens to BUY_YES trades, NO tokens to BUY_NO trades.
            # Sniper: direction is always BUY_YES for the matched token side,
            # so YES tokens execute directly; NO tokens also execute directly
            # (sniper already verified NO token is the winning side).
            # Momentum path: NO token with BUY_YES after flip → redirect to YES counterpart.
            if token.side == "YES" and signal.direction == Direction.BUY_NO:
                continue
            if token.side == "NO" and signal.direction == Direction.BUY_YES:
                if signal_source == "SNIPER":
                    # Sniper: BUY_YES on NO token = buy this NO token (already aligned)
                    pass
                else:
                    # Momentum path: find YES counterpart for the redirect
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

            tpsl = calculate_tp_sl(
                signal.entry_price,
                signal.direction,
                bars_5m,
                ob,
            )

            decision = self.risk.evaluate(
                token_id, signal, tpsl,
                condition_id=token.condition_id,
                window_end_ts=token.window_end_ts,
                asset=token.asset,
                market_type=token.market_type,
                cascade_discount=CONFIG.edge.cascade_score_discount
                    if token.asset in discounted_assets else 0.0,
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

    # ── Entry ─────────────────────────────────────────────────────────────────

    async def _enter_position(self, token_id, asset, signal, tpsl, decision) -> None:
        capital_before = self.risk.bankroll.capital
        ts_open = time.time()

        token_meta = self.feed.tokens.get(token_id)
        fill = await self.orders.market_buy(
            token_id=token_id,
            intended_price=signal.entry_price,
            stake_usd=decision.stake,
            direction=signal.direction,
            neg_risk=getattr(token_meta, "neg_risk", False),
            tick_size=getattr(token_meta, "tick_size", "0.01"),
        )

        if fill.avg_fill_price == 0:
            logger.error("Fill failed for %s", asset)
            return

        # Use actual fill cost as stake — CLOB 5-share minimum may require more than
        # the risk-approved stake (e.g. $1 stake but minimum order is $3.45 at price 0.69).
        actual_stake = fill.avg_fill_price * fill.total_size
        if actual_stake <= 0:
            actual_stake = decision.stake  # fallback to approved stake if fill data incomplete

        token = self.feed.tokens.get(token_id)
        pos = self.risk.open_position(
            token_id=token_id,
            asset=asset,
            direction=signal.direction,
            stake=actual_stake,
            entry_price=fill.avg_fill_price,
            tpsl=tpsl,
            condition_id=getattr(token, "condition_id", ""),
            window_end_ts=getattr(token, "window_end_ts", 0.0),
        )

        self._open_meta[token_id] = {
            "signal": signal,
            "signal_source": getattr(signal, "signal_source", "SNIPER")
                             if hasattr(signal, "delta_pct") else "MOMENTUM",
            "entry_fill": fill,
            "ts_open": ts_open,
            "capital_before": capital_before,
            "heat_check": decision.is_scaled,
            "consecutive_wins": self.risk.bankroll.consecutive_wins,
        }

    # ── Exit helpers ──────────────────────────────────────────────────────────

    def _calc_exit_price(self, exit_fills, fallback: float) -> float:
        total_size = sum(f.total_size for f in exit_fills)
        return (
            sum(f.avg_fill_price * f.total_size for f in exit_fills) / total_size
            if exit_fills and total_size > 0 else fallback
        )

    async def _partial_exit(self, token_id: str, live_price: float, reason: str) -> None:
        """Stage-1: sell 95% if 5% residual is CLOB-sellable, else sell 100% to avoid dust."""
        pos = self.risk.open_positions.get(token_id)
        if not pos:
            return

        # 5% residual only makes sense to keep when it can later be sold via CLOB ($1 min).
        # Add 50% buffer → $1.50 threshold. At current $2-4 positions, 5% = $0.10-0.25
        # → permanent dust. For future large positions ($30+), 5% = $1.50+ → keep the split.
        residual_value = pos.remaining_shares * 0.05 * live_price
        sell_pct = 0.95 if residual_value >= 1.50 else 1.0
        if sell_pct == 1.0:
            logger.info(
                "Stage-1 selling 100%% — 5%% residual=$%.2f < $1.50 CLOB minimum (permanent dust avoided)",
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
        )
        sold = sum(f.total_size for f in exit_fills)
        self.risk.record_stage1_sell(token_id, sold)
        # Store stage-1 fills so analytics can compute accurate weighted exit price
        meta = self._open_meta.get(token_id)
        if meta is not None:
            meta.setdefault("stage1_fills", []).extend(exit_fills)
        logger.info(
            "STAGE-1 %s %s | sold=%.4f @ ~%.4f | reason=%s",
            pos.asset, pos.direction.name, sold, live_price, reason,
        )

    async def _exit_position(self, token_id: str, live_price: float, reason: str) -> None:
        pos = self.risk.open_positions.get(token_id)
        if not pos:
            return

        meta = self._open_meta.get(token_id, {})

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

    # ── 10-second CLOB heartbeat ──────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Keep CLOB session alive; prevents silent GTC order cancellation."""
        while self._running:
            await asyncio.sleep(10)
            try:
                await self.orders.post_heartbeat()
            except Exception as exc:
                logger.debug("Heartbeat error: %s", exc)

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
            report = self.analytics.generate_claude_report()
            logger.info("\n%s", report)


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
