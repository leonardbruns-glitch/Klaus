"""
Late-window directional arb (LDA).

Signal: Binance 5m-return direction (spot vs open_5m).
Gate  : predicted-winner token ask in [0.60, 0.98] + bid > 0.50 + vol_regime==normal.
Timing: up to 3 entries per window (one per rem bucket), T-8 to T-300s.
          ask≥0.90 → rem≤60s (dead1 kept); ask[0.80,0.90) → rem≤300s (dead2 removed).
BNC   : adaptive floor — 0.07% at rem<60s (B0); 0.10% at ask<0.70; 0.05% at ask<0.90; 0.07% else.
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

# [120,300s) bucket — all-asset structural blocks (shadow May8-13, n≥29 per hour):
_ALL_BLOCKED_LATE = frozenset({3, 6, 12, 13, 15})
# H03 EV=-30.6% n=33; H06 EV=-11.8% n=29; H12 EV=-29.2% n=46;
# H13 WR=70% n=87 user-confirmed; H15 EV=-0.74% n=100 — BNC cannot fix

# [60,120s) bucket — all-asset structural blocks (shadow May8-13):
_ALL_BLOCKED_LATE_B1 = frozenset({4, 13, 15})
# H04 EV=-12.4% n=44; H13 EV=-8.3% n=34; H15 EV=-5.6% n=29

# [120,300s) bucket — per-asset structural blocks (CI fully below asset baseline):
_SOL_BLOCKED_LATE = frozenset({22})      # H22 WR=57% n=28; H06 promoted to _ALL_BLOCKED_LATE

# [120,300s) bucket — per-asset trending-weak, reduce stake pending n≥100:
_SOL_WATCH_LATE   = frozenset()          # H03/H13 promoted to _ALL_BLOCKED_LATE
_ETH_WATCH_LATE   = frozenset({8, 9, 22})  # WR=63%/69%/65%, n=24/16/17


def _entry_stake(asset: str, hour_utc: int, remaining: float) -> float:
    """Full stake normally; $2 for trending-weak hour×bucket cells."""
    if remaining > 120:
        if asset == "SOL" and hour_utc in _SOL_WATCH_LATE:
            return STAKE_USD_REDUCED
        if asset == "ETH" and hour_utc in _ETH_WATCH_LATE:
            return STAKE_USD_REDUCED
    return STAKE_USD

# Adaptive BNC floor by ask zone and rem bucket (shadow May8-13):
#   B0 (<60s): flat 0.07 — ask-zone split not needed; low-ask signals at B0 are structurally clean
#   B1/B2 [0.60,0.70): raise 0.07→0.10 — 0.05-0.10% moves are noise at low ask
#   B1/B2 [0.70,0.90): lower 0.07→0.05 — 0.05-0.07% moves are valid; EV improves
#   B1/B2 [0.90,0.98): keep 0.07 — insufficient data to move
def _bnc_floor(ask: float, remaining: float = 999.0) -> float:
    if remaining < 60:
        return 0.07
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
        if bnc_abs < _bnc_floor(ask, remaining):
            return  # adaptive floor: 0.07 at B0; 0.10/0.05/0.07 by ask zone at B1/B2

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

        # All assets [120,300s): EV-negative hours, shadow May8-13
        if remaining > 120 and hour_utc in _ALL_BLOCKED_LATE:
            return

        # All assets [60,120s): EV-negative hours, shadow May8-13
        if rem_bucket == 1 and hour_utc in _ALL_BLOCKED_LATE_B1:
            return

        # SOL [120,300s): H22 CI fully below 77.3% baseline (shadow n=28, May8-13)
        if remaining > 120 and asset == "SOL" and hour_utc in _SOL_BLOCKED_LATE:
            return

        # Elevated BNC floors for structurally weak hour×bucket cells (shadow May8-13):
        #   H02 B2: raise floor 0.05→0.07 — EV=-3.1% at 0.05, EV=+1.2% at 0.07 (n=41)
        #   H03 B1: require 0.06% — partial uplift; full block deferred to n≥100
        #   H20 B2: raise floor 0.05→0.06 — EV=-1.8% at 0.05; moderate improvement (n=38)
        if remaining > 120 and hour_utc == 2 and bnc_abs < 0.07:
            return
        if rem_bucket == 1 and hour_utc == 3 and bnc_abs < 0.06:
            return
        if remaining > 120 and hour_utc == 20 and bnc_abs < 0.06:
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

        # ── BNC-decay freshness re-check ─────────────────────────────────────
        # Re-read Binance spot ~500ms after signal eval. If the 5m return has
        # reversed by more than 0.03% against bet direction, skip — the
        # underlying momentum that justified the signal has died.
        # Shadow (May 9-13, n=2643): blocks 6.7%, kill ratio 1.77:1 (113L/64W),
        # lifts kept WR 81.1% → 84.3%. Holds in every cell.
        await asyncio.sleep(0.5)
        feed = self.bot.feed
        asset_up = asset.upper()
        spot_now    = feed._spot_price.get(asset_up, 0.0)
        open_5m_now = feed._spot_open_5m.get(asset_up, 0.0)
        if spot_now > 0 and open_5m_now > 0:
            bnc_now_pct = (spot_now - open_5m_now) / open_5m_now * 100.0
            sign        = 1.0 if bnc_dir == "up" else -1.0
            s_bnc_now   = sign * bnc_now_pct
            if s_bnc_now < -0.03:
                logger.info(
                    "[LDA] BNC_DECAY skip %s/%s ask=%.4f rem=%.1fs: signed_bnc %+.4f%% (was %+.4f%%)",
                    asset, bnc_dir, ask, rem, s_bnc_now, sign * bnc_move_pct,
                )
                self.entries_attempted -= 1
                # Keep _fired marker — signal is degraded, don't retry this bucket.
                return

        # ── Flip exit: sell opposite-direction LDA position in same window ────────
        # Strategy D: when BNC reverses and fires the complementary token, sell
        # the first position at its current bid rather than holding to resolution.
        # Shadow n=194: first-dir WR=13.4%; selling at bid_avg=0.18 + holding the
        # flip token saves $0.99/window vs holding both. ~$14/day at current volume.
        flip_token_id: str = ""
        for _tid, _pos in list(self.bot.risk.open_positions.items()):
            if (
                _pos.condition_id == cid
                and _pos.bond_outcome_direction != bnc_dir
                and _pos.bond_entry_class == "LDA"
                and _pos.remaining_shares > 0
            ):
                flip_token_id = _tid
                break

        if flip_token_id:
            _flip = self.bot.risk.open_positions.get(flip_token_id)
            if _flip is not None:
                _peer_bid = rec.get("peer_bid", 0.0)
                if _peer_bid <= 0:
                    _peer_bid = max(0.01, 1.0 - ask)  # complementary token pricing fallback
                _flip_shares = _flip.remaining_shares
                logger.info(
                    "[LDA] FLIP_EXIT %s/%s→%s %.4f shr @ ~%.4f bid (entry=%.4f)",
                    asset, _flip.bond_outcome_direction, bnc_dir,
                    _flip_shares, _peer_bid, _flip.entry_price,
                )
                _flip_results = await self.bot.orders.cascade_sell(
                    token_id=flip_token_id,
                    total_shares=_flip_shares,
                    current_price=_peer_bid,
                    reason="LDA_FLIP_EXIT",
                    force_exit=True,
                )
                _filled = [
                    r for r in _flip_results
                    if getattr(r, "status", None) == OrderStatus.FILLED
                    and getattr(r, "total_size", 0) > 0
                ]
                if _filled:
                    _exit_px = (
                        sum(r.avg_fill_price * r.total_size for r in _filled)
                        / sum(r.total_size for r in _filled)
                    )
                    self.bot.risk.close_position(flip_token_id, _exit_px, "LDA_FLIP_EXIT")
                    logger.info(
                        "[LDA] FLIP_EXIT done %.4f shr @ %.4f",
                        sum(r.total_size for r in _filled), _exit_px,
                    )
                else:
                    logger.warning("[LDA] FLIP_EXIT sell returned no fills — position stays open")

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
