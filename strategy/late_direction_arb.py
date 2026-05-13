"""
Late-window directional arb (LDA).

Signal: Binance 5m-return direction (spot vs open_5m).
Gate  : predicted-winner token ask in [0.60, 0.98] + bid > 0.50 + vol_regime==normal.
Timing: up to 3 entries per window (one per rem bucket), T-8 to T-300s.
          ask≥0.90 → rem≤60s (dead1 kept); ask[0.80,0.90) → rem≤300s (dead2 removed).
BNC   : adaptive floor — 0.10% at ask<0.70, 0.05% at ask<0.90, 0.07% else.
Exit  : PROFIT_TARGET fires at bid≥0.99; BOND_DEADLINE T-3s catches the rest.
        Multi-entry: uses add_to_position for 2nd/3rd fill on same window.

Live: n=69 direction WR=89.7%; dead2 removal evidence n=27/80 (shadow vol=normal).
Stake: $5 per entry. Raise after n≥100 direction WR and WR>55%.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Set, Tuple

from strategy.momentum import Direction, TPSLLevels

logger = logging.getLogger(__name__)

ASK_FLOOR    = 0.60
ASK_CEIL     = 0.98   # 0.994→0.98: exit is bid≥0.999 so entries above 0.98 have near-zero margin
BID_MIN      = 0.50    # safeguard: both tokens on wrong side if bid < 0.50
REM_MIN_S    = 8.0     # don't enter if <8s left (can't fill reliably)
REM_MAX_S    = 300.0   # extended from 90s; ask-conditional ceiling still blocks ask≥0.90 + rem>60s
STAKE_USD         = 5.00
STAKE_USD_REDUCED = 2.00   # trending-weak hour×bucket cells, pending n≥100 per cell
BLOCKED_HOURS_UTC = {0, 1}  # H00 WR=66% n=106 CI=[56.6%,74.4%] (shadow May8-12); H01 WR=88.6% n=79

# [120,300s) bucket — all-asset structural blocks:
_ALL_BLOCKED_LATE = frozenset({13})       # WR=70% all-asset n=87; volatile, user-confirmed

# [120,300s) bucket — per-asset structural blocks (CI fully below asset baseline):
_SOL_BLOCKED_LATE = frozenset({6, 22})   # WR=63%/57%, CI<77.3% baseline (n=38/28)

# [120,300s) bucket — per-asset trending-weak, reduce stake pending n≥100:
_SOL_WATCH_LATE   = frozenset({3, 13})   # WR=68%/66%, n=40/47 — inconsistent days
_ETH_WATCH_LATE   = frozenset({8, 9, 22})  # WR=63%/69%/65%, n=24/16/17


def _entry_stake(asset: str, hour_utc: int, remaining: float) -> float:
    """Full stake normally; $2 for trending-weak hour×bucket cells."""
    if remaining > 120:
        if asset == "SOL" and hour_utc in _SOL_WATCH_LATE:
            return STAKE_USD_REDUCED
        if asset == "ETH" and hour_utc in _ETH_WATCH_LATE:
            return STAKE_USD_REDUCED
    return STAKE_USD

# Adaptive BNC floor by ask zone (shadow n=27-80, vol=normal, May 8-12):
#   [0.60,0.70): raise 0.07→0.10 — 0.05-0.10% moves are noise at low ask
#   [0.70,0.90): lower 0.07→0.05 — 0.05-0.07% moves are valid; EV improves
#   [0.90,0.98): keep 0.07 — insufficient data to move
def _bnc_floor(ask: float) -> float:
    if ask < 0.70:
        return 0.10
    if ask < 0.90:
        return 0.05
    return 0.07


class LateDirectionArb:
    """Per-tick late-window directional arb."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.enabled: bool = True

        self._fired: Set[Tuple[str, int, int]] = set()  # (cid, wend, rem_bucket) dedup per bucket
        self._tasks = []

        self.entries_attempted: int = 0
        self.entries_filled: int = 0

    # ── Public: called synchronously from timeline sampler ────────────────────

    def schedule_if_ready(self, rec: dict) -> None:
        """Check current tick; spawn async entry task if conditions met."""
        if not self.enabled:
            return

        remaining = rec.get("seconds_to_resolution", 0.0)
        if not (REM_MIN_S <= remaining <= REM_MAX_S):
            return

        cid  = rec.get("condition_id", "")
        wend = rec.get("window_end_ts", 0)
        if not cid or not wend:
            return

        # Multi-entry: one entry per rem bucket per window.
        # Buckets: [0,60s)=0, [60,120s)=1, [120,300s)=2.
        rem_bucket = 0 if remaining < 60 else (1 if remaining < 120 else 2)
        key = (cid, wend, rem_bucket)
        if key in self._fired:
            return

        hour_utc = datetime.fromtimestamp(wend, tz=timezone.utc).hour
        if hour_utc in BLOCKED_HOURS_UTC:
            return

        ask = rec.get("best_ask", 0.0)
        bid = rec.get("best_bid", 0.0)
        if not (ASK_FLOOR <= ask <= ASK_CEIL) or bid < BID_MIN:
            return

        # Ask-conditional rem ceiling (shadow-validated, 5m, vol=normal, n≥100):
        #   ask≥0.90 + rem>60s   → dead zone 1 (EV -0.14 to -0.22)
        #   ask≥0.80 + rem>120s  → dead zone 2 partial: [90,120) EV+0.22 kept; [120,300s) EV -0.06 to -0.11
        #   ask<0.70 + rem>180s  → WR=63%, EV=-0.23 (n=130)
        if remaining > 60 and ask >= 0.90:
            return
        if remaining > 120 and ask >= 0.80:
            return
        if remaining > 180 and ask < 0.70:
            return

        # Hour blocks for early-rem low-ask zone (shadow n=99/123):
        #   [0.70,0.80) × rem>120s: H12 WR=65% EV=-0.70, H16 WR=65% EV=-0.61
        #   vs all other hours WR=77% EV=+0.15
        if remaining > 120 and 0.70 <= ask < 0.80 and hour_utc in (12, 16):
            return

        # Vol regime: volatile/extreme destroy edge (WR 54%/43% vs 71% normal).
        # Critical gate for ask<0.80 where volatile EV=-1.64 vs normal EV=+0.58.
        if rec.get("vol_regime", "normal") != "normal":
            return

        feed = self.bot.feed
        asset_up = rec.get("asset", "").upper()
        spot    = feed._spot_price.get(asset_up, 0.0)
        open_5m = feed._spot_open_5m.get(asset_up, 0.0)
        if spot <= 0 or open_5m <= 0:
            return

        bnc_move_pct = (spot - open_5m) / open_5m * 100.0
        bnc_abs = abs(bnc_move_pct)
        if bnc_abs < _bnc_floor(ask):
            return  # adaptive floor: 0.10% at ask<0.70, 0.05% at ask<0.90, 0.07% else

        # Per-asset / per-window-size bnc gates (shadow data, n=1631, May 8-12):
        #   ETH 15m: all bnc zones NEG EV or LOW WR → block entirely
        #   SOL 15m: 0.07-0.10% NEG EV (dominant bucket), rest too small → block entirely
        #   BTC 15m: 0.07-0.10% LOW WR (87.5%) → require bnc >= 0.10%
        #   SOL 5m:  0.10-0.15% and 0.15%+ NEG EV (ask too high by then) → cap at 0.10%
        wsz   = rec.get("window_size_s", 300)
        asset = rec.get("asset", "").upper()
        if wsz == 900:  # 15m window
            if asset in ("ETH", "SOL"):
                return
            if asset == "BTC" and bnc_abs < 0.10:
                return
        elif wsz == 300 and asset == "SOL" and bnc_abs >= 0.10:
            return

        # All assets [120,300s): H13 WR=70% n=87 — volatile, user-confirmed block
        if remaining > 120 and hour_utc in _ALL_BLOCKED_LATE:
            return

        # SOL [120,300s): H06+H22 CI fully below 77.3% baseline (shadow n=38/28, May8-12)
        if remaining > 120 and asset == "SOL" and hour_utc in _SOL_BLOCKED_LATE:
            return

        bnc_dir = "up" if bnc_move_pct > 0 else "down"
        if bnc_dir != rec.get("outcome_dir"):
            return  # this token is NOT on the predicted winning side

        stake_usd = _entry_stake(asset, hour_utc, remaining)

        # Mark fired BEFORE creating task to prevent a second tick from double-firing.
        self._fired.add(key)
        self.entries_attempted += 1

        task = asyncio.create_task(
            self._fire(dict(rec), bnc_dir, spot, open_5m, bnc_move_pct, stake_usd),
            name=f"lda_{cid[:8]}_{wend}",
        )
        self._tasks.append(task)
        if len(self._tasks) > 128:
            self._tasks = [t for t in self._tasks if not t.done()]

    async def stop(self) -> None:
        live = [t for t in self._tasks if not t.done()]
        for t in live:
            t.cancel()
        if live:
            await asyncio.gather(*live, return_exceptions=True)

    # ── Async entry execution ─────────────────────────────────────────────────

    async def _fire(
        self,
        rec: dict,
        bnc_dir: str,
        spot: float,
        open_5m: float,
        bnc_move_pct: float,
        stake_usd: float = STAKE_USD,
    ) -> None:
        """Execute the buy and register the position. Never raises."""
        try:
            await self._fire_inner(rec, bnc_dir, spot, bnc_move_pct, stake_usd)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[LDA] unhandled error %s/%s", rec.get("asset"), rec.get("window_end_ts"))

    async def _fire_inner(
        self,
        rec: dict,
        bnc_dir: str,
        spot: float,
        bnc_move_pct: float,
        stake_usd: float = STAKE_USD,
    ) -> None:
        from execution.order_manager import OrderStatus

        token_id = rec["token_id"]
        asset    = rec["asset"]
        ask      = rec["best_ask"]
        rem      = rec["seconds_to_resolution"]
        cid      = rec["condition_id"]
        wend     = rec["window_end_ts"]

        logger.info(
            "[LDA] ENTER %s/%s ask=%.4f rem=%.1fs bnc_move=%+.4f%% stake=$%.2f",
            asset, bnc_dir, ask, rem, bnc_move_pct, stake_usd,
        )

        fill = await self.bot.orders.limit_buy(
            token_id=token_id,
            intended_price=ask,
            stake_usd=stake_usd,
            direction=Direction.BUY_YES,
        )

        if fill.status != OrderStatus.FILLED or fill.total_size <= 0:
            logger.info("[LDA] fill failed %s: %s", asset, getattr(fill, "error", "?"))
            rem_bucket = 0 if rec.get("seconds_to_resolution", 0) < 60 else (1 if rec.get("seconds_to_resolution", 0) < 120 else 2)
            self._fired.discard((cid, wend, rem_bucket))
            self.entries_attempted -= 1
            return

        self.entries_filled += 1
        actual_stake = fill.avg_fill_price * fill.total_size

        logger.info(
            "[LDA] FILLED %s/%s %.4f shares @ %.4f | cost=$%.2f expect=$%.2f (+$%.2f)",
            asset, bnc_dir, fill.total_size, fill.avg_fill_price,
            actual_stake, fill.total_size, fill.total_size - actual_stake,
        )

        import time as _time

        try:
            if token_id in self.bot.risk.open_positions:
                # Scale into existing position (multi-entry, different rem bucket)
                self.bot.risk.add_to_position(
                    token_id=token_id,
                    add_shares=fill.total_size,
                    add_fill_price=fill.avg_fill_price,
                    add_stake=actual_stake,
                )
                logger.info("[LDA] SCALE %s/%s +%.4f @ %.4f", asset, bnc_dir, fill.total_size, fill.avg_fill_price)
            else:
                tpsl = TPSLLevels(
                    take_profit=0.0, stop_loss=0.0,
                    tp_pct=0.0, sl_pct=0.0, risk_reward=0.0,
                )
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
                    bond_outcome_direction=bnc_dir,
                    bond_entry_class="LDA",
                )
                self.bot._open_meta[token_id] = {
                    "signal_source": "LDA",
                    "ts_open": _time.time(),
                    "spot_at_entry": spot,
                    "pre_entry_momentum_pct": bnc_move_pct,
                    "window_size_s": rec.get("window_size_s", 300),
                    "capital_before": self.bot.risk.bankroll.capital,
                }
        except Exception:
            logger.exception("[LDA] risk position update failed %s", asset)
