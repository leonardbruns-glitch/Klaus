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
from typing import Dict, Optional

from config import CONFIG
from data.feeds import PolymarketFeed
from strategy.momentum import MomentumScorer, Direction, calculate_tp_sl
from risk.manager import RiskManager
from execution.order_manager import OrderManager
from analytics.feedback import FeedbackEngine

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
        self._running = False
        self._last_report_ts = 0.0
        # track entry metadata for trade recording
        self._open_meta: Dict[str, dict] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await self.feed.start()
        await self.orders.start()
        self._running = True
        mode = "DRY RUN" if CONFIG.dry_run else "LIVE"
        logger.info("=" * 50)
        logger.info("Klaus Momentum Scalper — %s", mode)
        logger.info("Capital: $%.2f | Base stake: $%.2f | Scaled: $%.2f",
                    CONFIG.bankroll.total, CONFIG.bankroll.base_stake, CONFIG.bankroll.scaled_stake)
        logger.info("Markets: %s", CONFIG.markets.tracked_assets)
        logger.info("=" * 50)

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

        try:
            await asyncio.gather(ob_task, signal_task, report_task)
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
        for token_id, pos in list(self.risk.open_positions.items()):
            ob = await self.feed.fetch_order_book(token_id)
            if ob is None:
                continue
            current_price = ob.bids[0][0] if len(ob.bids) > 0 else ob.mid

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

        # Fetch optional external signals per asset
        ext_signals = {}
        for asset in CONFIG.markets.tracked_assets:
            try:
                ext = await self.feed.fetch_external_signals(asset)
                ext_signals[asset] = ext
            except Exception:
                ext_signals[asset] = None  # never block on missing external data

        for token_id, token in self.feed.tokens.items():
            # Skip tokens already in open positions
            if token_id in self.risk.open_positions:
                continue

            bars_5m = self.feed.get_bars_5m(token_id, n=30)
            bars_15m = self.feed.get_bars_15m(token_id, n=30)
            ob = self.feed.get_order_book(token_id)

            if len(bars_5m) < 12:
                continue  # not enough history yet

            ext = ext_signals.get(token.asset)
            signal = self.scorer.score(bars_5m, bars_15m, ob, ext)

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
                "SCAN %s/%s | score=%.2f conf=%.2f entry=%.4f dir=%s | %s",
                token.asset, token.side,
                signal.composite, signal.confidence,
                signal.entry_price, signal.direction.name,
                signal.reason or "no signal",
            )

            if signal.direction == Direction.NO_TRADE:
                continue

            # Route YES tokens to BUY_YES trades, NO tokens to BUY_NO trades
            if token.side == "YES" and signal.direction == Direction.BUY_NO:
                continue
            if token.side == "NO" and signal.direction == Direction.BUY_YES:
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
                window_end_ts=getattr(token, "window_end_ts", 0.0),
                asset=token.asset,
            )

            if not decision.approved:
                logger.info("  └─ REJECTED: %s", decision.reason)
                continue

            logger.info(
                "  └─ SIGNAL %s | %s %s | entry=%.4f conf=%.2f score=%.2f | %s",
                token.asset, signal.direction.name, signal.fee_zone.name,
                signal.entry_price, signal.confidence, signal.composite,
                signal.reason,
            )

            await self._enter_position(token_id, token.asset, signal, tpsl, decision)

    # ── Entry ─────────────────────────────────────────────────────────────────

    async def _enter_position(self, token_id, asset, signal, tpsl, decision) -> None:
        capital_before = self.risk.bankroll.capital
        ts_open = time.time()

        fill = await self.orders.market_buy(
            token_id=token_id,
            intended_price=signal.entry_price,
            stake_usd=decision.stake,
            direction=signal.direction,
        )

        if fill.avg_fill_price == 0:
            logger.error("Fill failed for %s", asset)
            return

        token = self.feed.tokens.get(token_id)
        pos = self.risk.open_position(
            token_id=token_id,
            asset=asset,
            direction=signal.direction,
            stake=decision.stake,
            entry_price=fill.avg_fill_price,
            tpsl=tpsl,
            condition_id=getattr(token, "condition_id", ""),
            window_end_ts=getattr(token, "window_end_ts", 0.0),
        )

        self._open_meta[token_id] = {
            "signal": signal,
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
        """Stage-1: sell 95 % of position, leave 5 % riding to +45 %."""
        pos = self.risk.open_positions.get(token_id)
        if not pos:
            return

        sell_shares = round(pos.remaining_shares * 0.95, 4)
        exit_fills = await self.orders.cascade_sell(
            token_id=token_id,
            total_shares=sell_shares,
            current_price=live_price,
            reason=reason,
        )
        sold = sum(f.total_size for f in exit_fills)
        self.risk.record_stage1_sell(token_id, sold)
        logger.info(
            "STAGE-1 %s %s | sold=%.4f @ ~%.4f | reason=%s",
            pos.asset, pos.direction.name, sold, live_price, reason,
        )

    async def _exit_position(self, token_id: str, live_price: float, reason: str) -> None:
        pos = self.risk.open_positions.get(token_id)
        if not pos:
            return

        meta = self._open_meta.get(token_id, {})

        exit_fills = await self.orders.cascade_sell(
            token_id=token_id,
            total_shares=pos.remaining_shares,
            current_price=live_price,
            reason=reason,
        )

        exit_price = self._calc_exit_price(exit_fills, pos.entry_price)
        capital_before = meta.get("capital_before", self.risk.bankroll.capital)
        net_pnl = self.risk.close_position(token_id, exit_price, reason)

        if net_pnl is not None and meta.get("entry_fill") and meta.get("signal"):
            self.analytics.record_trade(
                token_id=token_id,
                asset=pos.asset,
                direction=pos.direction,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                stake=pos.stake,
                shares=pos.shares,
                entry_fill=meta["entry_fill"],
                exit_fills=exit_fills,
                exit_reason=reason,
                signal=meta["signal"],
                ts_open=meta.get("ts_open", pos.open_ts),
                ts_close=time.time(),
                capital_before=capital_before,
                capital_after=self.risk.bankroll.capital,
                heat_check_active=meta.get("heat_check", False),
                consecutive_wins=meta.get("consecutive_wins", 0),
            )

        self._open_meta.pop(token_id, None)
        bankroll = self.risk.bankroll.summary()
        logger.info(
            "EXIT %s %s | reason=%s | PnL=$%.3f | capital=$%.2f | streak=%d",
            pos.asset, pos.direction.name, reason,
            net_pnl or 0, bankroll["capital"], bankroll["consecutive_wins"],
        )

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
