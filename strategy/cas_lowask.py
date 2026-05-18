"""
CAS-LowAsk — Cross-Asset Synchrony × Low-Ask cheap-tail entry.

Signal: at T-60s (rem in [50, 70]s), evaluate Binance 5m partial return for BTC/ETH/SOL.
If 2 of the 3 assets have partial return >= +0.01% (UP case) or <= -0.01% (DOWN case)
AND the third asset's partial return confirms same direction (>=0 or <=0), buy the
third asset's matching-direction token ONLY IF its ask is in [0.05, 0.50] with
sufficient top-1 depth.

Backtest 2026-05-08 → 2026-05-17 (9.4 days of shadow data, n=425, 10/10 days positive):
  WR 46.4% [41.7%, 51.1% Wilson], avg_ask $0.214, EV/trade +$0.248/$1 stake
  bootstrap 95% CI [+$0.2015, +$0.3000], +$11.20/day @ $1 stake (45 trades/day).
  Size>=20 shares (~$5 fillable): 65% of opportunities.

Thesis: the synchrony itself is mostly priced in at high ask. The edge is structural
cheap-tail mispricing — when 2 of 3 are aligned and the third's matching-direction
token is quoted <$0.50, market is underpricing. WR is coin-flip-ish (46%) but the
asymmetric payout (~$0.80 win vs -$0.20 loss) makes it +EV.

Hold to resolution. PROFIT_TARGET 0.95 in bond monitor handles upside exit.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Set, Tuple

from strategy.momentum import Direction, TPSLLevels

logger = logging.getLogger(__name__)

# ── Gates ────────────────────────────────────────────────────────────────────
# THR_PCT lowered 0.01 → 0.001 and ASK_MAX raised 0.50 → 0.65 on 2026-05-17 after
# broader-ASK sweep. Same expected $/day (~$214 vs $209) but 2× the trade count
# (65/d vs 30/d), WR up to 53% (from 48%), much smoother daily PnL. Variance
# reduction makes the -$10 daily kill switch less likely to fire.
# Backtest 9.4 days shadow at this config: n=613, WR=52.7%, EV/$1=+$0.747, +$214.65/d.
THR_PCT          = 0.001   # 0.001% partial-return threshold (loose; was 0.01%)
ASK_MIN          = 0.05
ASK_MAX          = 0.65    # was 0.50
REM_MIN_S        = 50.0
REM_MAX_S        = 70.0
STAKE_USD        = 5.00
MAX_CONCURRENT   = 2       # tight: caps simultaneous risk at $10 given ~$13 capital
# Partial-fill mode: take up to STAKE_USD worth, but accept smaller fills down to CLOB
# minimums (5 shares / $1 notional). WR is determined by token resolution not stake
# size, so smaller fills preserve EV per dollar while capturing more opportunities.
ASK_DEPTH_MIN_SH = 5       # CLOB minimum order size
MIN_NOTIONAL_USD = 1.00    # CLOB minimum maker amount


class CASLowAsk:
    """Cross-asset synchrony low-ask cheap-tail strategy."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.enabled: bool = True
        self._fired_tokens: Set[str] = set()
        self._fired_asset_windows: Set[Tuple[str, int]] = set()
        self._tasks: list = []
        self.entries_attempted: int = 0
        self.entries_filled: int = 0

    def schedule_if_ready(self, rec: dict) -> None:
        if not self.enabled:
            return

        bankroll = self.bot.risk.bankroll
        if bankroll.is_ruined or bankroll.is_halted:
            return

        token_id = rec.get("token_id", "")
        cid = rec.get("condition_id", "")
        wend = rec.get("window_end_ts", 0)
        if not token_id or not cid or not wend:
            return

        if token_id in self._fired_tokens:
            return

        asset = rec.get("asset", "").upper()
        if asset not in ("BTC", "ETH", "SOL"):
            return

        aw_key = (asset, int(wend))
        if aw_key in self._fired_asset_windows:
            return

        # Concurrency cap
        n_open = sum(
            1 for p in self.bot.risk.open_positions.values()
            if getattr(p, "bond_entry_class", "") == "CAS_LOWASK"
        )
        if n_open >= MAX_CONCURRENT:
            return

        if (rec.get("window_size_s") or 0) != 300:
            return

        remaining = rec.get("seconds_to_resolution", 0.0)
        if not (REM_MIN_S <= remaining <= REM_MAX_S):
            return

        # Block CAS at H01, H02, H08, H11, H18 (reserved for VOLARB)
        hour_utc = datetime.fromtimestamp(wend, tz=timezone.utc).hour
        if hour_utc in [1, 2, 8, 11, 18]:
            return

        ask = rec.get("best_ask", 0.0)
        if not (ASK_MIN <= ask <= ASK_MAX):
            return

        ask_size = rec.get("ob_top1_ask_size") or 0.0
        if ask_size < ASK_DEPTH_MIN_SH:
            return
        # Partial-fill sizing: take up to $5 worth, but cap at top-1 size to avoid
        # walking the book. Skip if the resulting notional is below CLOB $1 minimum.
        shares_to_buy = min(STAKE_USD / ask, ask_size)
        actual_stake = shares_to_buy * ask
        if actual_stake < MIN_NOTIONAL_USD:
            return

        # Canonical bet token: ('up','YES') = bet UP, ('down','NO') = bet DOWN
        od = rec.get("outcome_dir", "")
        os_ = rec.get("outcome_side", "")
        if od == "up" and os_ == "YES":
            bet_dir = "UP"
        elif od == "down" and os_ == "NO":
            bet_dir = "DOWN"
        else:
            return

        # Cross-asset partial state
        feed = self.bot.feed
        partials = {}
        for a in ("BTC", "ETH", "SOL"):
            spot = feed._spot_price.get(a, 0.0)
            o5m = feed._spot_open_5m.get(a, 0.0)
            if not spot or not o5m:
                return
            partials[a] = (spot - o5m) / o5m * 100.0  # percent

        c = asset
        pair = [a for a in ("BTC", "ETH", "SOL") if a != c]
        pa, pb = pair[0], pair[1]

        if bet_dir == "UP":
            if not (partials[pa] >= THR_PCT and partials[pb] >= THR_PCT):
                return
            if partials[c] < 0.0:
                return
        else:
            if not (partials[pa] <= -THR_PCT and partials[pb] <= -THR_PCT):
                return
            if partials[c] > 0.0:
                return

        if token_id in self.bot.risk.open_positions:
            return

        self._fired_tokens.add(token_id)
        self._fired_asset_windows.add(aw_key)
        self.entries_attempted += 1
        task = asyncio.create_task(self._fire(rec, partials, bet_dir, actual_stake))
        self._tasks.append(task)
        task.add_done_callback(lambda t: self._tasks.remove(t) if t in self._tasks else None)

    async def _fire(self, rec: dict, partials: dict, bet_dir: str, stake: float) -> None:
        try:
            await self._fire_inner(rec, partials, bet_dir, stake)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[CAS] unhandled error %s/%s", rec.get("asset"), rec.get("window_end_ts"))

    async def _fire_inner(self, rec: dict, partials: dict, bet_dir: str, stake: float) -> None:
        from execution.order_manager import OrderStatus

        token_id = rec["token_id"]
        asset = rec["asset"]
        ask = rec["best_ask"]
        rem = rec["seconds_to_resolution"]
        cid = rec["condition_id"]
        wend = rec["window_end_ts"]
        outcome_dir = rec.get("outcome_dir", "up")
        side = rec.get("outcome_side", "YES")

        c = asset.upper()
        pair = [a for a in ("BTC", "ETH", "SOL") if a != c]

        logger.info(
            "[CAS] ENTER %s/%s/%s ask=%.4f rem=%.1fs bet=%s partials: %s=%+.3f%% %s=%+.3f%% %s=%+.3f%% stake=$%.2f",
            asset, outcome_dir, side, ask, rem, bet_dir,
            pair[0], partials[pair[0]], pair[1], partials[pair[1]], c, partials[c],
            stake,
        )

        fill = await self.bot.orders.limit_buy(
            token_id=token_id,
            intended_price=ask,
            stake_usd=stake,
            direction=Direction.BUY_YES,
            fast_fail=True,
        )

        if fill.status != OrderStatus.FILLED or fill.total_size <= 0:
            logger.info("[CAS] fill failed %s: %s", asset, getattr(fill, "error", "?"))
            self._fired_tokens.discard(token_id)
            self._fired_asset_windows.discard((asset.upper(), int(wend)))
            return

        self.entries_filled += 1
        actual_stake = fill.avg_fill_price * fill.total_size
        logger.info(
            "[CAS] FILLED %s/%s/%s %.4f shares @ %.4f | cost=$%.2f",
            asset, outcome_dir, side, fill.total_size, fill.avg_fill_price, actual_stake,
        )

        try:
            tpsl = TPSLLevels(
                take_profit=0.0, stop_loss=0.0,
                tp_pct=0.0, sl_pct=0.0, risk_reward=0.0,
            )
            spot = self.bot.feed._spot_price.get(asset.upper(), 0.0)
            self.bot.risk.open_position(
                token_id=token_id,
                asset=asset,
                direction=Direction.BUY_YES,
                stake=actual_stake,
                entry_price=fill.avg_fill_price,
                tpsl=tpsl,
                condition_id=cid,
                window_end_ts=wend,
                window_seconds=rec.get("window_size_s", 300),
                quality_score=0,
                binance_price_at_entry=spot,
                is_bond=True,
                bond_outcome_direction=outcome_dir,
                bond_entry_class="CAS_LOWASK",
            )
        except Exception:
            logger.exception("[CAS] open_position error")

    async def stop(self) -> None:
        self.enabled = False
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
