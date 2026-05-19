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
THR_PCT          = 0.005   # lowered 0.020→0.005: broader gate acceptance
THR_PCT_RELAXED  = 0.001   # H06/H21: tighter THR kills edge there; use original threshold
ASK_MIN          = 0.05
ASK_MAX          = 0.50    # reverted from 0.65: live ask[0.55,0.65) EV=-$1.22 (n=26 clean); ask<0.55 EV=+$3.75 (n=13)
ASK_MAX_HIGH_CONV = 0.60   # extended ceiling only when range_pos>0.8 (6m: WR=75% n=64, EV=+0.295)
REM_MIN_S        = 10.0    # lowered 35→10: shadow [10,15) EV=+0.394, [15,35) all positive
REM_MAX_S        = 95.0    # lowered 105→95: [95,105) EV=-0.025 (n=251, corrected shadow)
REM_BLOCK_LO     = 65.0    # [65,75) blocked
REM_BLOCK_HI     = 75.0
REM_BLOCK2_LO    = 85.0
REM_BLOCK2_HI    = 95.0
KELLY_FRACTION   = 0.137
STAKE_CAP_USD    = 15.00
STAKE_FLOOR_USD  = 15.00
# Per-asset stakes raised 2026-05-18 with THR=0.02 (EV=+0.247, all assets positive)
# Shadow: BTC EV=+0.220, ETH EV=+0.195, SOL EV=+0.365 at this threshold
ASSET_STAKE: dict = {"BTC": 15.00, "ETH": 15.00, "SOL": 3.00}
MAX_CONCURRENT   = 2
# Partial-fill mode: take up to target stake, but accept smaller fills down to CLOB
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

    async def schedule_if_ready(self, rec: dict) -> None:
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
        if REM_BLOCK_LO <= remaining < REM_BLOCK_HI:
            return
        if REM_BLOCK2_LO <= remaining < REM_BLOCK2_HI:
            return

        # Global blocks: H01-05/08 negative; H12 EV=-0.093; H14 user; H16 EV=-0.157
        # H18 blocked 2026-05-18: shadow EV=-0.305; VOLARB WR=60% there (swapped)
        hour_utc = datetime.fromtimestamp(wend, tz=timezone.utc).hour
        if hour_utc in [1, 2, 3, 5, 14, 16, 18, 21]:
            return
        # SOL-specific blocks: H05/11/13/18/22/23 all negative EV in shadow
        if asset == "SOL" and hour_utc in {5, 11, 13, 18, 22, 23}:
            return

        ask = rec.get("best_ask", 0.0)
        if not (ASK_MIN <= ask <= ASK_MAX_HIGH_CONV):
            return

        ask_size = rec.get("ob_top1_ask_size") or 0.0
        if ask_size < ASK_DEPTH_MIN_SH:
            return
        # Per-asset fixed stake (overrides Kelly).
        target_stake = ASSET_STAKE.get(asset, STAKE_CAP_USD)
        shares_to_buy = min(target_stake / ask, ask_size)
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



        # ob_imb gate: shadow-only until n>=100. Sweet spot [0.1,0.5): WR=67%, EV=+0.499.
        # [0,0.1) is a trap (WR=33%, EV=-0.339); <0 = mildly ok (WR=52%, EV=+0.115).
        ob_imb = rec.get("ob_imb_top3", None)
        if ob_imb is not None and not (0.1 <= ob_imb < 0.5):
            logger.info("[CAS] imb_shadow WOULD_BLOCK %s ob_imb=%.3f", asset, ob_imb)

        snap_30s_pct = rec.get("tok_snap_30s", 0.0)

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

        thr = THR_PCT_RELAXED if hour_utc in {6, 21} else THR_PCT
        if bet_dir == "UP":
            if not (partials[pa] >= thr and partials[pb] >= thr):
                return
            if partials[c] < 0.0:
                return
        else:
            if not (partials[pa] <= -thr and partials[pb] <= -thr):
                return
            if partials[c] > 0.0:
                return

        # Extended ask gate [ASK_MAX, ASK_MAX_HIGH_CONV]: only allow when range_pos > 0.8.
        # range_pos = price position within 5m high-low range at T-60s (1=at extreme).
        if ask > ASK_MAX:
            h5m = feed._spot_5m_high.get(c, 0.0)
            l5m = feed._spot_5m_low.get(c, 0.0)
            cur = feed._spot_price.get(c, 0.0)
            rng = h5m - l5m
            if not rng or not h5m or not l5m or not cur:
                return
            range_pos = (cur - l5m) / rng if bet_dir == "UP" else (h5m - cur) / rng
            if range_pos <= 0.8:
                return
            logger.info("[CAS] high-conv ask=%.4f range_pos=%.3f %s", ask, range_pos, c)

        if token_id in self.bot.risk.open_positions:
            return

        self._fired_tokens.add(token_id)
        self._fired_asset_windows.add(aw_key)
        self.entries_attempted += 1
        self._log_preseed_fire(rec, bet_dir)
        try:
            await asyncio.wait_for(self._fire(rec, partials, bet_dir, actual_stake), timeout=0.5)
        except asyncio.TimeoutError:
            logger.warning("[CAS] order submission timeout %s, attempting recovery", token_id)
            await self._recover_orphan(rec, bet_dir, cid, wend)
        except Exception as e:
            logger.exception("[CAS] order submission error %s: %s", token_id, e)
            self._fired_tokens.discard(token_id)
            self._fired_asset_windows.discard((asset.upper(), int(wend)))

    def _log_preseed_fire(self, rec: dict, bet_dir: str) -> None:
        try:
            import time as _time, json as _json, os as _os
            entry = {
                "record_type":   "cas_fire",
                "ts":            _time.time(),
                "asset":         rec.get("asset"),
                "window_end_ts": rec.get("window_end_ts"),
                "outcome_dir":   rec.get("outcome_dir"),
                "bet_dir":       bet_dir,
                "rem":           round(rec.get("seconds_to_resolution", 0), 1),
                "ask":           rec.get("best_ask"),
                "ask_age_ms":    rec.get("ask_age_ms", 0),
                "ask_delta_30s": rec.get("ask_delta_30s", 0.0),
                "ob_imb":        rec.get("ob_imb_top3", None),
            }
            log_dir = "logs/shadow"
            _os.makedirs(log_dir, exist_ok=True)
            with open(f"{log_dir}/preseed_shadow.jsonl", "a") as f:
                f.write(_json.dumps(entry) + "\n")
        except Exception:
            pass

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

        # Fast retry: if fill failed, check cached OB immediately (no scan-cycle wait).
        # Only retry if ask hasn't drifted beyond 2× original — prevents chasing rips.
        if fill.status != OrderStatus.FILLED or fill.total_size <= 0:
            _ob = self.bot.feed.get_order_book(token_id)
            _new_ask = _ob.asks[0][0] if (_ob and _ob.asks) else None
            if (
                _new_ask is not None
                and _new_ask <= ask * 2.0
                and ASK_MIN <= _new_ask <= ASK_MAX_HIGH_CONV
                and (wend - time.time()) >= REM_MIN_S
            ):
                _target = ASSET_STAKE.get(asset.upper(), STAKE_CAP_USD)
                _sh = min(_target / _new_ask, _ob.asks[0][1])
                _retry_stake = _sh * _new_ask
                if _retry_stake >= MIN_NOTIONAL_USD:
                    logger.info("[CAS] fast-retry %s ask %.4f→%.4f", asset, ask, _new_ask)
                    fill = await self.bot.orders.limit_buy(
                        token_id=token_id,
                        intended_price=_new_ask,
                        stake_usd=_retry_stake,
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

    async def _recover_orphan(self, rec: dict, bet_dir: str, cid: str, wend: float) -> None:
        """Recover orphaned position that timed out before logging entry."""
        token_id = rec["token_id"]
        asset = rec["asset"]
        outcome_dir = rec.get("outcome_dir", "up")
        side = rec.get("outcome_side", "YES")

        try:
            pos = await self.bot.clob_client.get_position(token_id)
            if not pos or pos.get("balance", 0) <= 0:
                logger.warning("[CAS] orphan recovery: no position found for %s", asset)
                self._fired_tokens.discard(token_id)
                self._fired_asset_windows.discard((asset.upper(), int(wend)))
                return

            shares = pos.get("balance", 0)
            entry_price = pos.get("average_buy_price", 0.0)
            if not entry_price or entry_price <= 0:
                logger.warning("[CAS] orphan recovery: invalid entry price %s for %s shares", entry_price, shares)
                self._fired_tokens.discard(token_id)
                self._fired_asset_windows.discard((asset.upper(), int(wend)))
                return

            actual_stake = shares * entry_price
            logger.info("[CAS] orphan recovery FOUND %s: %s shares @ %.4f = $%.2f", asset, shares, entry_price, actual_stake)

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
                    entry_price=entry_price,
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
                self.entries_filled += 1
                logger.info("[CAS] orphan recovery: position tracking restored")
            except Exception:
                logger.exception("[CAS] orphan recovery: open_position error")
                self._fired_tokens.discard(token_id)
                self._fired_asset_windows.discard((asset.upper(), int(wend)))
        except Exception:
            logger.exception("[CAS] orphan recovery failed for %s", asset)
            self._fired_tokens.discard(token_id)
            self._fired_asset_windows.discard((asset.upper(), int(wend)))

    async def stop(self) -> None:
        self.enabled = False
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
