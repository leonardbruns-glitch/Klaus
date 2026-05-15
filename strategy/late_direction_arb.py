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
Stake: BNC-tiered half-Kelly scaled with live bankroll.
  [0.05,0.07%): 10% bankroll; [0.07,0.10%): 12%; [0.10%,∞): 10%. B0 flat $3.
  Portfolio-adjusted for expected 1.4 simultaneous assets/window. Cap $100.
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

# B3 [180,300s) re-enabled 2026-05-15: user instruction. Ask range 0.70-<0.80 (existing dead zones apply).
# Two-tier flat stakes per asset: base (BNC < strong threshold) vs strong (BNC >= threshold)
# Strong threshold chosen where WR peaks and n≥20; B3 gets no strong tier (WR flat vs BNC)

# BNC-tiered half-Kelly (portfolio-adjusted for ~1.4 simultaneous assets/window).
# 3 tiers from 5m first-fire WR vs BNC analysis 2026-05-14 (n=2688 post-gate):
#   [0.05,0.07%): WR 82-92% across cells, sweet spot in all assets
#   [0.07,0.10%): WR 88-97%, peak Kelly zone
#   [0.10%,∞):    thin n; hold at same fraction until n≥100 per bin
# 0.08-0.09% sub-bin dip (WR<adjacent bins in 4/6 cells) real but n=12-40, not actionable yet.
_BNC_TIER_LOW_FRAC  = 0.10   # bnc [0.05, 0.07%)
_BNC_TIER_MID_FRAC  = 0.12   # bnc [0.07, 0.10%)
_BNC_TIER_HIGH_FRAC = 0.10   # bnc [0.10%, ∞)

# B0 [8,60s): ask near resolution; Kelly≈0 at ask>0.90 (73% of B0 volume); keep flat
_STAKE_B0 = 3.0

# Cumulative Kelly targets per rem-bucket (fraction of full tier target).
# B3 fires first at 50%; B2 tops up to 75%; B1 tops up to 100%.
# Total across all 3 buckets = 1× Kelly — same cap, distributed across entries.
# If only B1 fires (no prior buckets): gets full 100% immediately.
_BUCKET_KELLY_CUM = {3: 0.50, 2: 0.75, 1: 1.00}

# Kelly targets retained for any future non-BTC/ETH/SOL asset
_KELLY_TARGET = {1: 3.00, 2: 5.50, 3: 9.00}
BLOCKED_HOURS_UTC = {0, 1, 2, 3, 23}  # H00/H01 shadow May8-12; H02 user block 2026-05-15 (n=18 WR=22% -$249); H03 B2 gap; H23 user block 2026-05-15 (n=7 WR=29% -$186)

# [120,300s) bucket — all-asset structural blocks (shadow May8-13, n≥29 per hour):
_ALL_BLOCKED_LATE = frozenset({3, 5, 6, 7, 12, 15})
# H03 EV=-30.6% n=33; H06 EV=-11.8% n=29; H12 EV=-29.2% n=46;
# H13 unblocked user instruction 2026-05-14; H15 EV=-0.74% n=100 — BNC cannot fix

# [60,120s) bucket — all-asset structural blocks:
_ALL_BLOCKED_LATE_B1 = frozenset({4, 5, 12, 15})  # H07 unblocked user instruction 2026-05-15
# H04 EV=-12.4% n=44; H12 ETH n=30 EV=-0.57 SOL n=44 EV=-0.49; H15 EV=-5.6% n=29

_ETH_BLOCKED_B1 = frozenset({1, 2})         # H01 n=34 EV=-0.71; H02 n=20 EV=-0.291 3/4d bad

# [120,300s) bucket — ETH structural blocks:
_ETH_BLOCKED_LATE = frozenset({0, 8, 9, 13, 16, 17, 21, 22})
# H00 EV=-1.24 n=32 3/5d; H08 EV=-0.754 n=25 2/5d; H09 EV=-0.304 n=24 3/6d; H16 WR=72% n=18; H17 EV=-0.26 n=56 5/7d; H21 EV=-1.18 n=19
# H13 B3 EV=-0.155 n=43; H22 B3 EV=-0.354 n=25 (B2 H13/H22 near-zero n<10, acceptable loss)

# [60,120s) bucket — BTC structural blocks (5m first-fire 2026-05-14):
_BTC_BLOCKED_B1 = frozenset({13})           # H13 n=26 EV=-0.274 4/6d bad

# [120,180s)+[180,300s) bucket — BTC structural blocks (bad at both B2 and B3):
_BTC_BLOCKED_LATE = frozenset({17})         # H17: B2 EV=-0.252 n=20 4/6d; B3 EV=-0.298 n=44 3/7d

# [180,300s) bucket — BTC structural blocks (B3-only; B2 is positive at these hours):
_BTC_BLOCKED_B3 = frozenset({1, 4, 18, 21, 23})   # H01 EV=-0.28 n=33; H04 EV=-1.15 n=12; H18 EV=-0.27 n=21 (B2 H18=+0.94); H21 shadow+0.43 n=15 user block; H23 EV=-0.58 n=18

# [120,300s) bucket — per-asset trending-weak, reduce stake pending n≥100:
_ETH_WATCH_LATE   = frozenset({22})      # WR=65% n=17; H08/H09 promoted to _ETH_BLOCKED_LATE



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


def _bnc_tier_stake(bnc_abs: float, bankroll: float) -> float:
    """Half-Kelly stake for B1/B2/B3 by BNC magnitude tier."""
    if bnc_abs < 0.07:
        frac = _BNC_TIER_LOW_FRAC
    elif bnc_abs < 0.10:
        frac = _BNC_TIER_MID_FRAC
    else:
        frac = _BNC_TIER_HIGH_FRAC
    return max(5.0, min(100.0, bankroll * frac))


class LateDirectionArb:
    """Per-tick late-window directional arb."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.enabled: bool = True

        self._fired: Set[Tuple[str, int, int]] = set()  # (cid, wend, rem_bucket) dedup per bucket
        self._window_assets: Dict[Tuple[int, str], Set[str]] = {}  # (wend, odir) → assets fired
        self._window_staked: Dict[Tuple[str, int, str], float] = {}  # (cid, wend, odir) → $ staked
        self._asset_window_staked: Dict[Tuple[str, int, str, str], float] = {}  # (cid, wend, asset, odir) → $ staked
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
        # Buckets: [0,60s)=0, [60,120s)=1, [120,180s)=2, [180,300s)=3.
        rem_bucket = 0 if remaining < 60 else (1 if remaining < 120 else (2 if remaining < 180 else 3))
        key = (cid, wend, rem_bucket)
        if key in self._fired:
            return

        hour_utc = datetime.fromtimestamp(wend, tz=timezone.utc).hour
        if hour_utc in BLOCKED_HOURS_UTC:
            return

        asset = rec.get("asset", "").upper()
        if asset == "SOL":  # user instruction 2026-05-15: full block (n=178 WR=53.4% net=-$791)
            return

        ask = rec.get("best_ask", 0.0)
        bid = rec.get("best_bid", 0.0)
        if not (ASK_FLOOR <= ask <= ASK_CEIL) or bid < BID_MIN:
            return

        # Ask-conditional rem ceiling (shadow-validated, 5m, vol=normal, n≥100):
        #   ask≥0.90 + rem>60s   → dead zone 1 (EV -0.14 to -0.22)
        #   ask≥0.80 + rem>120s  → dead zone 2 partial: [90,120) EV+0.22 kept; [120,300s) EV -0.06 to -0.11
        #   ask<0.69 + rem>120s  → B2 floor 0.69 (user instruction 2026-05-15)
        #   ask<0.70 + rem>180s  → WR=63%, EV=-0.23 (n=130); B3 floor 0.70
        if remaining > 60 and ask >= 0.90:
            return
        if remaining > 120 and ask >= 0.80:
            return
        if remaining > 120 and ask < 0.69:
            return
        if remaining > 180 and ask < 0.70:
            return

        # Vol regime: volatile/extreme destroy edge (WR 54%/43% vs 71% normal).
        # Critical gate for ask<0.80 where volatile EV=-1.64 vs normal EV=+0.58.
        if rec.get("vol_regime", "normal") != "normal":
            return

        feed = self.bot.feed
        asset_up = asset
        spot    = feed._spot_price.get(asset_up, 0.0)
        open_5m = feed._spot_open_5m.get(asset_up, 0.0)
        if spot <= 0 or open_5m <= 0:
            return

        bnc_move_pct = (spot - open_5m) / open_5m * 100.0
        bnc_abs = abs(bnc_move_pct)
        if bnc_abs < _bnc_floor(ask, remaining):
            return  # adaptive floor: 0.07 at B0; 0.10/0.05/0.07 by ask zone at B1/B2

        # Per-asset / per-window-size bnc gates:
        wsz = rec.get("window_size_s", 300)
        if wsz == 900:  # 15m window — block all assets (user directive 2026-05-14)
            return

        # B3 [180,300s): ETH+BTC only
        # ETH B3 bad hours via _ETH_BLOCKED_LATE; BTC B3 via _BTC_BLOCKED_B3
        if remaining >= 180 and asset not in ("ETH", "BTC"):
            return
        if remaining >= 180 and asset == "BTC" and hour_utc in _BTC_BLOCKED_B3:
            return

        # All assets [120,300s): EV-negative hours, shadow May8-13
        # Exception: BTC B3 H15 EV=+0.238 n=47 5/7d — positive despite all-late block
        if remaining > 120 and hour_utc in _ALL_BLOCKED_LATE:
            if not (asset == "BTC" and remaining >= 180 and hour_utc == 15):
                return

        # All assets [60,120s): EV-negative hours
        if rem_bucket == 1 and hour_utc in _ALL_BLOCKED_LATE_B1:
            return

        # ETH [60,120s): per-asset EV-negative hours (5m first-fire 2026-05-14)
        if rem_bucket == 1 and asset == "ETH" and hour_utc in _ETH_BLOCKED_B1:
            return

        # BTC [60,120s): per-asset EV-negative hours (5m first-fire 2026-05-14)
        if rem_bucket == 1 and asset == "BTC" and hour_utc in _BTC_BLOCKED_B1:
            return

        # ETH [120,300s): structural bad hours (shadow May8-14)
        if remaining > 120 and asset == "ETH" and hour_utc in _ETH_BLOCKED_LATE:
            return

        # BTC [120,300s): H17 bad at both B2+B3 (shadow 2026-05-14)
        if remaining > 120 and asset == "BTC" and hour_utc in _BTC_BLOCKED_LATE:
            return

        # ETH [60,120s) H16: [0.70,0.80) ask band is bad; [0.80,0.90) positive — raise floor
        if rem_bucket == 1 and asset == "ETH" and hour_utc == 16 and ask < 0.80:
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

        # BNC-tiered half-Kelly — B0 flat $3; B1/B2/B3 use cumulative targets
        # B3→B2→B1 each top up to their cumulative fraction of the full Kelly target:
        #   B3: 50%  B2: 75%  B1: 100% — total capped at 1× Kelly regardless of buckets fired
        if remaining < 60:
            stake_usd = _STAKE_B0
        elif asset in ("BTC", "ETH"):
            full_target = _bnc_tier_stake(bnc_abs, bankroll)
            bucket_target = full_target * _BUCKET_KELLY_CUM.get(rem_bucket, 1.0)
            _aws_key = (cid, wend, asset, bnc_dir)
            remaining_budget = bucket_target - self._asset_window_staked.get(_aws_key, 0.0)
            if remaining_budget < 5.0:
                self._fired.add(key)  # suppress future ticks in this bucket
                return
            stake_usd = remaining_budget
        else:
            already = self._window_staked.get((cid, wend, bnc_dir), 0.0)
            stake_usd = max(STAKE_MIN_USD, min(STAKE_MAX_USD, target - already))

        # Watch-cell cap: trending-weak hour×bucket cells remain reduced
        if remaining > 120 and asset == "ETH" and hour_utc in _ETH_WATCH_LATE:
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
        # Per-asset Kelly budget tracker (multi-bucket cap)
        _awk = (cid, wend, asset.upper(), bnc_dir)
        self._asset_window_staked[_awk] = self._asset_window_staked.get(_awk, 0.0) + actual_stake

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
