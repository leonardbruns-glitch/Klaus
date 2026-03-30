"""
Klaus — Research Engine
Passive market scanner that records tick-level signal data and surfaces
edge patterns for strategy calibration. Runs as a background task.

Output: logs/market_ticks.jsonl — newline-delimited JSON, one record per
token per minute. Reports every 30 minutes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
import time
from collections import defaultdict
from typing import Dict, List, Optional

from config import CONFIG
from data.feeds import PolymarketFeed
from strategy.momentum import MomentumScorer

logger = logging.getLogger("research")

TICK_LOG = os.path.join(CONFIG.analytics.log_dir, "market_ticks.jsonl")
TICK_INTERVAL = 60          # seconds between _record_tick calls
REPORT_INTERVAL = 1800      # seconds between _print_report calls
HIGH_SCORE_THRESHOLD = 0.55 # ticks above this are worth examining
MAX_REPORT_LINES = 500      # how many recent lines to load for report


class ResearchEngine:
    """
    Runs continuously in the background.
    Every 60s: scores all tokens and appends a tick record to market_ticks.jsonl.
    Every 30min: reads the last 500 ticks and emits a structured analysis report.
    """

    def __init__(self, feed: PolymarketFeed, scorer: MomentumScorer) -> None:
        self.feed = feed
        self.scorer = scorer
        os.makedirs(CONFIG.analytics.log_dir, exist_ok=True)

    # ── Background loop ───────────────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop: record ticks every 60s, report every 30min."""
        last_report_ts = 0.0
        try:
            while True:
                await self._record_tick()

                now = time.time()
                if now - last_report_ts >= REPORT_INTERVAL:
                    self._print_report()
                    last_report_ts = now

                await asyncio.sleep(TICK_INTERVAL)
        except asyncio.CancelledError:
            pass

    # ── Tick recorder ─────────────────────────────────────────────────────────

    async def _record_tick(self) -> None:
        """Score every known token and append a JSON line to market_ticks.jsonl."""
        now_ts = int(time.time())
        hour_utc = int(time.gmtime(now_ts).tm_hour)

        for token_id, token in list(self.feed.tokens.items()):
            try:
                bars_5m = self.feed.get_bars_5m(token_id, n=30)
                bars_15m = self.feed.get_bars_15m(token_id, n=30)
                ob = self.feed.get_order_book(token_id)

                if len(bars_5m) < 12:
                    continue

                sig = self.scorer.score(bars_5m, bars_15m, ob, None)

                # Current mid price: use OB mid if available, else last bar close
                if ob is not None and ob.mid > 0:
                    price = ob.mid
                elif bars_5m:
                    price = bars_5m[-1].close
                else:
                    price = 0.0

                record = {
                    "ts": now_ts,
                    "token_id": token_id,
                    "asset": token.asset,
                    "side": token.side,
                    "market_type": token.market_type,
                    "price": round(price, 5),
                    "score": round(sig.composite, 4),
                    "confidence": round(sig.confidence, 4),
                    "direction": sig.direction.name,
                    "breakout": round(sig.breakout_score, 4),
                    "trend": round(sig.trend_score, 4),
                    "volume": round(sig.volume_score, 4),
                    "ob_imb": round(sig.ob_score, 4),
                    "hour_utc": hour_utc,
                }

                with open(TICK_LOG, "a") as f:
                    f.write(json.dumps(record) + "\n")

            except Exception as exc:
                logger.debug("research._record_tick skipped %s: %s", token_id[:12], exc)

    # ── 30-min report ─────────────────────────────────────────────────────────

    def _print_report(self) -> None:
        """Read recent ticks and log a structured analysis report."""
        ticks = self._load_recent_ticks(MAX_REPORT_LINES)
        if not ticks:
            logger.info("[RESEARCH] No tick data yet — report skipped.")
            return

        now_ts = time.time()
        window_start = now_ts - REPORT_INTERVAL

        report_lines: List[str] = [
            "=" * 60,
            "RESEARCH ENGINE REPORT — Klaus Momentum Scalper",
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
            f"Ticks in window: {len(ticks)}",
            "=" * 60,
        ]

        # ── 1. Top 5 signals right now ────────────────────────────────────────
        # "right now" = ticks from the most recent _record_tick cycle
        if ticks:
            latest_ts = max(t["ts"] for t in ticks)
            latest_ticks = [t for t in ticks if t["ts"] >= latest_ts - TICK_INTERVAL]
            top5 = sorted(latest_ticks, key=lambda t: t["score"], reverse=True)[:5]
        else:
            top5 = []

        report_lines.append("")
        report_lines.append("TOP 5 SIGNALS (current cycle)")
        if top5:
            for t in top5:
                report_lines.append(
                    f"  {t['asset']}/{t['side']} | score={t['score']:.3f} | "
                    f"price={t['price']:.4f} | dir={t['direction']}"
                )
        else:
            report_lines.append("  (no recent ticks)")

        # ── 2. Score distribution ─────────────────────────────────────────────
        all_scores = [t["score"] for t in ticks]
        if all_scores:
            sorted_scores = sorted(all_scores)
            n = len(sorted_scores)
            mean_score = statistics.mean(all_scores)
            p50 = sorted_scores[int(n * 0.50)]
            p75 = sorted_scores[int(n * 0.75)]
            p90 = sorted_scores[int(n * 0.90)]

            report_lines.append("")
            report_lines.append("SCORE DISTRIBUTION")
            report_lines.append(
                f"  mean={mean_score:.3f}  p50={p50:.3f}  p75={p75:.3f}  p90={p90:.3f}"
            )

        # ── 3. By-hour analysis ───────────────────────────────────────────────
        by_hour: Dict[int, List[dict]] = defaultdict(list)
        for t in ticks:
            by_hour[t["hour_utc"]].append(t)

        if by_hour:
            report_lines.append("")
            report_lines.append("BY-HOUR ANALYSIS (UTC)")
            for hour in sorted(by_hour.keys()):
                hour_ticks = by_hour[hour]
                mean_s = statistics.mean(t["score"] for t in hour_ticks)
                asset_counts: Dict[str, int] = defaultdict(int)
                for t in hour_ticks:
                    asset_counts[t["asset"]] += 1
                top_asset = max(asset_counts, key=lambda a: asset_counts[a])
                report_lines.append(
                    f"  {hour:02d}:00  count={len(hour_ticks):4d}  "
                    f"mean_score={mean_s:.3f}  top_asset={top_asset}"
                )

        # ── 4. By-asset analysis ──────────────────────────────────────────────
        by_asset: Dict[str, List[dict]] = defaultdict(list)
        for t in ticks:
            by_asset[t["asset"]].append(t)

        report_lines.append("")
        report_lines.append("BY-ASSET ANALYSIS")
        for asset in ["BTC", "ETH", "SOL"]:
            asset_ticks = by_asset.get(asset, [])
            if not asset_ticks:
                report_lines.append(f"  {asset}: no data")
                continue
            mean_s = statistics.mean(t["score"] for t in asset_ticks)
            max_s = max(t["score"] for t in asset_ticks)
            buy_yes = sum(1 for t in asset_ticks if t["direction"] == "BUY_YES")
            buy_pct = buy_yes / len(asset_ticks) * 100 if asset_ticks else 0.0
            report_lines.append(
                f"  {asset}: mean={mean_s:.3f}  max={max_s:.3f}  "
                f"BUY_YES={buy_pct:.0f}%  BUY_NO={100 - buy_pct:.0f}%"
            )

        # ── 5. High-score events in last 30 min ───────────────────────────────
        recent_high = [
            t for t in ticks
            if t["ts"] >= window_start and t["score"] > HIGH_SCORE_THRESHOLD
        ]

        report_lines.append("")
        report_lines.append(
            f"HIGH-SCORE EVENTS (score > {HIGH_SCORE_THRESHOLD}) — last 30 min"
        )
        if recent_high:
            for t in sorted(recent_high, key=lambda x: x["score"], reverse=True):
                ts_str = time.strftime("%H:%M:%S", time.gmtime(t["ts"]))
                report_lines.append(
                    f"  {ts_str}  {t['asset']}/{t['side']}  score={t['score']:.3f}  "
                    f"price={t['price']:.4f}  dir={t['direction']}  "
                    f"brk={t['breakout']:.3f}  trn={t['trend']:.3f}  "
                    f"vol={t['volume']:.3f}  ob={t['ob_imb']:.3f}"
                )
        else:
            report_lines.append("  (none)")

        report_lines.append("=" * 60)

        for line in report_lines:
            logger.info(line)

    # ── I/O helpers ───────────────────────────────────────────────────────────

    def _load_recent_ticks(self, max_lines: int) -> List[dict]:
        """Read the last max_lines records from market_ticks.jsonl."""
        if not os.path.exists(TICK_LOG):
            return []
        try:
            with open(TICK_LOG) as f:
                raw_lines = f.readlines()
        except Exception as exc:
            logger.debug("research._load_recent_ticks: %s", exc)
            return []

        recent_lines = raw_lines[-max_lines:] if len(raw_lines) > max_lines else raw_lines
        ticks = []
        for line in recent_lines:
            line = line.strip()
            if not line:
                continue
            try:
                ticks.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return ticks
