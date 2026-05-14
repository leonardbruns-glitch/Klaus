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
Stake: incremental Kelly per binary outcome, scaled with bankroll.
  1 asset co-firing: target $3/outcome; 2 assets: $5.50; 3 assets: $9.
  Each bucket entry stakes the gap to target (max $7/entry, min $1).
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
STAKE_USD_REDUCED = 2.00   # watch-cell cap per entry (ETH/SOL weak hours, pending n≥100)
STAKE_MIN_USD     = 1.00   # floor per entry — always enter even when target already met
STAKE_MAX_USD     = 7.00   # ceiling per entry (ETH/SOL Kelly); BTC uses bucket stakes below

# BTC bucket-based flat stakes (user instruction 2026-05-14; BTC only)
_BTC_STAKE_B4 =  5.0   # rem 180-300s: early entry, low certainty
_BTC_STAKE_B3 = 20.0   # rem 120-180s: shadow WR=82%, n=34
_BTC_STAKE_B1 = 10.0   # rem  60-120s: core bucket, shadow WR=89%
_BTC_STAKE_B2 =  5.0   # rem    0-60s: high ask, lowest EV

# Incremental Kelly targets per binary outcome per window (half-Kelly, ρ=0.75 corr-adj):
# shadow May8-14 n=5575: 1A EV=-3.2% Kelly=0%; 2A EV=-0.6% Kelly≈0%; 3A EV=+3.5% Kelly=18%
# Scaled by bankroll/100 at runtime so stakes grow with capital automatically.
_KELLY_TARGET = {1: 3.00, 2: 5.50, 3: 9.00}
BLOCKED_HOURS_UTC = {0, 1}  # H00 WR=66% n=106 CI=[56.6%,74.4%] (shadow May8-12); H01 WR=88.6% n=79

# [120,300s) bucket — all-asset structural blocks (shadow May8-13, n≥29 per hour):
_ALL_BLOCKED_LATE = frozenset({3, 6, 12, 15})
# H03 EV=-30.6% n=33; H06 EV=-11.8% n=29; H12 EV=-29.2% n=46;
# H13 unblocked user instruction 2026-05-14; H15 EV=-0.74% n=100 — BNC cannot fix

# [60,120s) bucket — all-asset structural blocks (shadow May8-13):
_ALL_BLOCKED_LATE_B1 = frozenset({4, 15})
# H04 EV=-12.4% n=44; H13 unblocked user instruction 2026-05-14; H15 EV=-5.6% n=29

# [120,300s) bucket — per-asset structural blocks (CI fully below asset baseline):
_SOL_BLOCKED_LATE = frozenset({22})      # H22 WR=57% n=28; H06 promoted to _ALL_BLOCKED_LATE

# SOL — all buckets: user instruction 2026-05-14 (H07/H09 draining live capital)
_SOL_BLOCKED_ALL  = frozenset({7, 9})

# [120,300s) bucket — per-asset trending-weak, reduce stake pending n≥100:
_SOL_WATCH_LATE   = frozenset()          # H03/H13 promoted to _ALL_BLOCKED_LATE
_ETH_WATCH_LATE   = frozenset({8, 9, 22})  # WR=63%/69%/65%, n=24/16/17



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
        self._window_assets: Dict[Tuple[int, str], Set[str]] = {}  # (wend, odir) → assets fired
        self._window_staked: Dict[Tuple[str, int, str], float] = {}  # (cid, wend, odir) → $ staked
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
        rem_bucket = 0 if remaining < 60 else (1 if remaining < 120 else (2 if remaining < 180 else 3))
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

        # SOL all-bucket hour blocks (user instruction 2026-05-14)
        if asset == "SOL" and hour_utc in _SOL_BLOCKED_ALL:
            return

        # SOL rem restriction: only buckets 2-3 (user instruction 2026-05-14)
        # 0-60s WR=0% n=7; 180-300s worst by $ (-$210 today) — cut both extremes
        if asset == "SOL" and (remaining < 60 or remaining >= 180):
            return

        # SOL bucket 3 (120-180s): tighter ask ceiling 0.97 (user instruction 2026-05-14)
        if asset == "SOL" and remaining >= 120 and ask > 0.97:
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

        # ── Incremental Kelly sizing ──────────────────────────────────────────
        # Count assets that have already fired all_pass this window+direction.
        # More co-firing assets → higher conditional WR → higher Kelly target.
        wa_key = (wend, bnc_dir)
        if wa_key not in self._window_assets:
            self._window_assets[wa_key] = set()
        self._window_assets[wa_key].add(asset)
        n_co = len(self._window_assets[wa_key])

        bankroll = max(10.0, getattr(self.bot.risk.bankroll, "capital", 100.0))
        scale    = bankroll / 100.0
        target   = _KELLY_TARGET[n_co] * scale

        already   = self._window_staked.get((cid, wend, bnc_dir), 0.0)
        if asset == "BTC":
            # Bucket-based flat stakes — bypass Kelly for BTC (user instruction 2026-05-14)
            if remaining < 60:
                stake_usd = _BTC_STAKE_B2
            elif remaining < 120:
                stake_usd = _BTC_STAKE_B1
            elif remaining < 180:
                stake_usd = _BTC_STAKE_B3
            else:
                stake_usd = _BTC_STAKE_B4
        else:
            stake_usd = max(STAKE_MIN_USD, min(STAKE_MAX_USD, target - already))

        # Watch-cell cap: trending-weak hour×bucket cells remain reduced
        if remaining > 120 and (
            (asset == "SOL" and hour_utc in _SOL_WATCH_LATE)
            or (asset == "ETH" and hour_utc in _ETH_WATCH_LATE)
        ):
            stake_usd = min(stake_usd, STAKE_USD_REDUCED * scale)

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
        stake_usd: float = STAKE_MAX_USD,
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
        stake_usd: float = STAKE_MAX_USD,
    ) -> None:
        from execution.order_manager import OrderStatus

        token_id = rec["token_id"]
        asset    = rec["asset"]
        ask      = rec["best_ask"]
        rem      = rec["seconds_to_resolution"]
        cid      = rec["condition_id"]
        wend     = rec["window_end_ts"]

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
            rem_bucket = 0 if rec.get("seconds_to_resolution", 0) < 60 else (1 if rec.get("seconds_to_resolution", 0) < 120 else (2 if rec.get("seconds_to_resolution", 0) < 180 else 3))
            self._fired.discard((cid, wend, rem_bucket))
            self.entries_attempted -= 1
            return

        self.entries_filled += 1
        actual_stake = fill.avg_fill_price * fill.total_size

        # Track total staked on this binary outcome so subsequent bucket entries
        # compute the correct incremental Kelly gap.
        _wk = (cid, wend, bnc_dir)
        self._window_staked[_wk] = self._window_staked.get(_wk, 0.0) + actual_stake

        logger.info(
            "[LDA] FILLED %s/%s %.4f shares @ %.4f | cost=$%.2f expect=$%.2f (+$%.2f) "
            "[outcome_staked=$%.2f n_assets=%d]",
            asset, bnc_dir, fill.total_size, fill.avg_fill_price,
            actual_stake, fill.total_size, fill.total_size - actual_stake,
            self._window_staked[_wk],
            len(self._window_assets.get((wend, bnc_dir), {asset})),
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
