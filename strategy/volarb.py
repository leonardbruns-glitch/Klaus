"""
VOLARB — Volatility-mispricing arb (Phase 1 conservative deploy).

Signal: logit on leak-safe Binance microstructure features predicts P(this YES/NO token resolves to 1.0).
Edge   = model_p - market_mid. When edge >= +0.15 and ask in [0.10, 0.60] with sufficient depth,
         buy this token at ask. Hold to resolution.

Backtest: 4d train / 5d OOS test (May 12-16) at edge>=0.10:
  n=2909, WR=51.7%, EV=+$4.86/trade, PF=3.01, CI95=[+$3.79, +$6.20] on $5 stake.
  Without ask<0.10 longshots: n=2779, EV=+$1.49, CI=[+$1.22, +$1.76] — still clears zero.
  Phase 1 deploys ask 0.10-0.60 ONLY (no longshots until n>=100 OOS in <0.10 cell).

Model trained 2026-05-16 on 346,976 rows from May 8-16 (sample_every=10), sec_to_res>=60 (leak guard).
Train acc 59.15% vs 49.88% base rate.

Phase 1 gates:
  - Edge floor 0.15 (more conservative than backtest's 0.10)
  - Ask band [0.10, 0.60]
  - $1 stake
  - Max 3 concurrent VOLARB positions
  - Vol regime != extreme
  - sec_to_res in [60, 280]
  - Per-token-id dedup (one entry per token lifetime)
  - Top-1 ask depth >= 3x intended shares
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any, Dict, Set

from strategy.momentum import Direction, TPSLLevels

logger = logging.getLogger(__name__)

# ── Phase 1 gates ─────────────────────────────────────────────────────────────
EDGE_FLOOR     = 0.15
# ASK_FLOOR lowered 0.10 → 0.00 2026-05-17 (user instruction). Activates the
# backtest "longshot" bucket: n=95 OOS, WR 50.5%, +$90.32/trade ($5 stake) —
# 88% of total backtest PnL. Variance is high; single drought can wipe gains.
ASK_FLOOR      = 0.00
ASK_CEIL       = 0.60
REM_MIN_S      = 60.0    # leak guard (training also gated at sec_to_res>=60)
REM_MAX_S      = 280.0   # avoid the wild [280, 300) window-open noise
STAKE_USD      = 1.00    # Phase 1 conservative
MAX_CONCURRENT = 3
ASK_DEPTH_MULT = 3.0     # require top-1 ask_size >= 3x our shares

# ── Baked-in model (extracted from /tmp/volarb_train_export.py on 2026-05-16) ─
# Features (in order): r5s, r30s, r60s, r60m, vel5s, sec_to_res, vol_reg, trend_reg, liq_reg, ob_imb, vpin, tok_snap_30s
VOL_REG_MAP   = {"calm": 0, "normal": 1, "volatile": 2, "extreme": 3}
TREND_REG_MAP = {"flat": 0, "weak": 1, "strong": 2}
LIQ_REG_MAP   = {"thin": 0, "normal": 1, "deep": 2}

INTERCEPT = -0.0041255984286758815
WEIGHTS = [
    0.0,
    0.18920318825033883,
    0.29627865173801426,
    0.09252134319057682,
    0.05860105745778085,
    0.0034079587793086493,
    0.0341562504564953,
    0.0,
    -0.011251830210286713,
    0.003305922944054851,
    -0.02510443071763102,
    -0.019841559398103014,
]
SCALER_MEAN = [
    0.0,
    0.00010945569722401537,
    0.00011498749193027713,
    -0.028948110532141344,
    -9.601240431614795e-06,
    188.49604987089143,
    0.47469277413999816,
    0.0,
    1.1487163377294107,
    0.00477040141104854,
    0.2721732970003356,
    0.06876460072166497,
]
SCALER_SCALE = [
    1.0,
    0.029538165636611928,
    0.035216358034906046,
    0.3928973993184744,
    0.012298194449206124,
    73.70181947481252,
    0.6013636199204366,
    1.0,
    0.7637332228439315,
    0.45704450678481434,
    0.1504366297992796,
    22.974534680158744,
]


def _extract_feats(rec: dict) -> list[float]:
    """Pull the 12 leak-safe features from a market_timeline-style rec dict."""
    return [
        float(rec.get("binance_ret_5s_pct") or 0.0),
        float(rec.get("binance_ret_30s_pct") or 0.0),
        float(rec.get("binance_ret_60s_pct") or 0.0),
        float(rec.get("binance_ret_60m_pct") or 0.0),
        float(rec.get("binance_vel_5s_pct") or 0.0),
        float(rec.get("seconds_to_resolution") or 0.0),
        VOL_REG_MAP.get(rec.get("vol_regime") or "normal", 1),
        TREND_REG_MAP.get(rec.get("trend_regime") or "flat", 0),
        LIQ_REG_MAP.get(rec.get("liquidity_regime") or "normal", 1),
        float(rec.get("ob_imb_top3") or 0.0),
        float(rec.get("vpin_score") or 0.0),
        float(rec.get("tok_snap_30s") or 0.0),
    ]


def _predict_p(x: list[float]) -> float:
    """Logit forward-pass. Returns P(token resolves to 1.0)."""
    z = INTERCEPT
    for i, xi in enumerate(x):
        scaled = (xi - SCALER_MEAN[i]) / SCALER_SCALE[i]
        z += WEIGHTS[i] * scaled
    # sigmoid with overflow guard
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


class Volarb:
    """Per-tick volatility-mispricing arb. Mirrors LateDirectionArb's interface."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.enabled: bool = True
        self._fired_tokens: Set[str] = set()  # one entry per token lifetime
        self._tasks: list = []
        self.entries_attempted: int = 0
        self.entries_filled: int = 0

    def schedule_if_ready(self, rec: dict) -> None:
        """Called from timeline sampler per tick. Spawns _fire if all gates pass."""
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

        # Per-token dedup
        if token_id in self._fired_tokens:
            return

        # Per-strategy concurrency cap
        n_open_volarb = sum(
            1 for p in self.bot.risk.open_positions.values()
            if getattr(p, "bond_entry_class", "") == "VOLARB"
        )
        if n_open_volarb >= MAX_CONCURRENT:
            return

        # Window/asset gates
        if (rec.get("window_size_s") or 0) != 300:
            return
        if rec.get("asset", "").upper() not in ("BTC", "ETH", "SOL"):
            return
        remaining = rec.get("seconds_to_resolution", 0.0)
        if not (REM_MIN_S <= remaining <= REM_MAX_S):
            return

        # Vol regime: extreme is excluded (training had it sparse; live-eval safety)
        if rec.get("vol_regime") == "extreme":
            return

        # Price gates (ask in [0.10, 0.60])
        ask = rec.get("best_ask", 0.0)
        if not (ASK_FLOOR <= ask <= ASK_CEIL):
            return

        # Liquidity: need depth >= 3x our shares
        ask_size = rec.get("ob_top1_ask_size") or 0.0
        shares_wanted = STAKE_USD / ask
        if shares_wanted > (ASK_DEPTH_MULT * ask_size):
            return

        # Compute model edge
        try:
            feats = _extract_feats(rec)
            model_p = _predict_p(feats)
        except Exception:
            logger.debug("[VOLARB] feature/predict error", exc_info=True)
            return
        market_p = rec.get("mid", (rec.get("best_bid", 0.0) + ask) / 2.0)
        edge = model_p - market_p
        if edge < EDGE_FLOOR:
            return  # Phase 1: only take LONG edge on THIS token

        # Block double-take: skip if LDA already entered this exact token this window
        if token_id in self.bot.risk.open_positions:
            return

        # Mark + fire
        self._fired_tokens.add(token_id)
        self.entries_attempted += 1
        task = asyncio.create_task(self._fire(rec, model_p, edge))
        self._tasks.append(task)
        task.add_done_callback(lambda t: self._tasks.remove(t) if t in self._tasks else None)

    async def _fire(self, rec: dict, model_p: float, edge: float) -> None:
        try:
            await self._fire_inner(rec, model_p, edge)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[VOLARB] unhandled error %s/%s", rec.get("asset"), rec.get("window_end_ts"))

    async def _fire_inner(self, rec: dict, model_p: float, edge: float) -> None:
        from execution.order_manager import OrderStatus

        token_id = rec["token_id"]
        asset = rec["asset"]
        ask = rec["best_ask"]
        rem = rec["seconds_to_resolution"]
        cid = rec["condition_id"]
        wend = rec["window_end_ts"]
        outcome_dir = rec.get("outcome_dir", "up")
        side = rec.get("outcome_side", "YES")

        logger.info(
            "[VOLARB] ENTER %s/%s/%s ask=%.4f mid=%.4f rem=%.1fs model_p=%.3f edge=%+.3f stake=$%.2f",
            asset, outcome_dir, side, ask, rec.get("mid", 0.0), rem, model_p, edge, STAKE_USD,
        )

        fill = await self.bot.orders.limit_buy(
            token_id=token_id,
            intended_price=ask,
            stake_usd=STAKE_USD,
            direction=Direction.BUY_YES,  # always buy THIS token (the YES side of its own market)
        )

        if fill.status != OrderStatus.FILLED or fill.total_size <= 0:
            logger.info("[VOLARB] fill failed %s: %s", asset, getattr(fill, "error", "?"))
            self._fired_tokens.discard(token_id)
            return

        self.entries_filled += 1
        actual_stake = fill.avg_fill_price * fill.total_size
        logger.info(
            "[VOLARB] FILLED %s/%s/%s %.4f shares @ %.4f | cost=$%.2f expect=$%.2f",
            asset, outcome_dir, side, fill.total_size, fill.avg_fill_price,
            actual_stake, fill.total_size,
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
                bond_entry_class="VOLARB",
            )
        except Exception:
            logger.exception("[VOLARB] open_position error")

    async def stop(self) -> None:
        self.enabled = False
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
