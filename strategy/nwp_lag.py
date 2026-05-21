"""
STRATEGY #1 — NWP-LAG ARBITRAGE (the HFT one).

Edge thesis:
    Polymarket prices reprice only when traders act. NWP models publish on
    fixed wall-clock schedules. The 5–15 minute window between a new model
    run becoming available and Polymarket fully reflecting the shift is the
    single most-documented edge in weather prediction markets (Polymarket
    Weather Strategy Guide 2026; competitive bot reports).

Mechanism:
    1. Wait at known NWP publish slots (precomputed). At T+1 minute after each
       slot, fetch the freshest run from that ONE model for every active city.
    2. Per (city, market), compare μ_new vs μ_old (cached from the prior run
       of the same model). If |Δμ| ≥ DELTA_TRIGGER_C, this is a model shift.
    3. Check the Polymarket bucket whose probability gained the most under
       the shift. If its ask hasn't moved >ASK_STABILITY_PCT in the last
       ANCHOR_SECONDS, the market is stale → enter FAK taker.
    4. Hold HOLD_SECONDS (target ~30–90 min). Exit FAK taker at best bid.

This is the HFT-style strategy in our portfolio:
  - Sub-minute decision cycle around publish events
  - FAK taker (latency-sensitive; accept 0.8% fee burden for 5-15pp edge)
  - Tight hold time (do not hold to resolution; we are scalping the reprice)
  - Edge is gone after ~30 min once retail/other-bot competition catches up

This module DOES NOT touch STRAT_3/STRAT_4 — they live as independent edges.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


# ── Publish schedule (UTC) ───────────────────────────────────────────────────
# Each (model, [utc_hours_when_run_is_available]).
# Run cycle + processing delay (typical ~3-4h after init for global models).
# We poll T+5min after publish to catch the fresh run.
NWP_PUBLISH_SCHEDULE: dict[str, list[int]] = {
    "gfs_seamless":           [4, 10, 16, 22],   # 00/06/12/18Z + ~4h
    "ecmwf_ifs025":           [7, 19],           # 00/12Z + ~7h
    "ecmwf_aifs025":          [7, 19],           # AIFS released same window as IFS
    "gfs_graphcast025":       [5, 11, 17, 23],   # GraphCast follows GFS init + 1h
    "icon_seamless":          [3, 9, 15, 21],    # 00/06/12/18Z + ~3h
    "jma_seamless":           [4, 10, 16, 22],
    "ukmo_seamless":          [6, 18],           # UKMO 00/12Z + ~6h
    "meteofrance_seamless":   [5, 11, 17, 23],
    "gem_seamless":           [5, 11, 17, 23],
}
POLL_OFFSET_MINUTES = 5      # poll at T+5min after publish hour

# ── Trigger thresholds ───────────────────────────────────────────────────────
DELTA_TRIGGER_C       = 0.5    # min |μ_new − μ_old| to consider it a model shift
ASK_STABILITY_PCT     = 0.04   # ask must not have moved more than 4pp in window
ANCHOR_SECONDS        = 300    # ask stability check window (5 min)
MIN_EDGE_AFTER_FEE    = 0.05   # net edge after fees must be ≥ 5pp
MAX_ENTRY_ASK         = 0.85   # don't chase deep favourites
MIN_ENTRY_ASK         = 0.03   # avoid sub-3¢ dust
HOLD_SECONDS_TARGET   = 2400   # 40 min hold target (let market reprice)
HOLD_SECONDS_MAX      = 5400   # 90 min hard exit cap

# ── Stake sizing ─────────────────────────────────────────────────────────────
NWPLAG_ENABLED        = True
NWPLAG_BANKROLL_FRAC  = 0.20   # 20% of bankroll reserved for NWP-LAG positions
NWPLAG_PER_POSITION   = 0.05   # 5% of bankroll per position (Kelly cap)
NWPLAG_MIN_STAKE      = 5.0
NWPLAG_MAX_STAKE      = 30.0
NWPLAG_MAX_CONCURRENT = 4


class NwpLagArbitrage:
    """Wall-clock-scheduled NWP-publish-event scanner + executor."""

    def __init__(self, bot) -> None:
        self.bot     = bot
        self._task: Optional[asyncio.Task] = None
        # μ history: { (model_name, city_slug): (run_ts, μ_celsius) }
        self._mu_history: dict[tuple[str, str], tuple[float, float]] = {}
        # ask history for stability check: { token_id: [(ts, ask), ...] }
        self._ask_history: dict[str, list[tuple[float, float]]] = defaultdict(list)
        # Active NWP-LAG positions: { token_id: {opened_ts, target_exit_ts, ...} }
        self._active_positions: dict[str, dict] = {}
        # Disabled if Polymarket scan dependencies fail
        self._enabled = NWPLAG_ENABLED

    def start(self) -> None:
        if not self._enabled:
            logger.info("[NWPLAG] disabled by config")
            return
        self._task = asyncio.create_task(self._loop(), name="nwp_lag_loop")
        logger.info("[NWPLAG] started — %d models, %d publish slots/day",
                    len(NWP_PUBLISH_SCHEDULE),
                    sum(len(v) for v in NWP_PUBLISH_SCHEDULE.values()))

    async def _loop(self) -> None:
        """Main loop: sleeps until the next publish event, then scans."""
        # Wait 60s for bot init
        await asyncio.sleep(60.0)
        while True:
            try:
                next_slot, models_to_check = self._next_publish_slot()
                wait_s = max(10.0, (next_slot - datetime.now(timezone.utc)).total_seconds())
                if wait_s > 7200:
                    # Cap sleeps at 2h to ride out clock skew / DST transitions
                    wait_s = 7200
                logger.info("[NWPLAG] sleeping %.0fs until %s (models: %s)",
                            wait_s, next_slot.strftime("%H:%M UTC"), ",".join(models_to_check))
                await asyncio.sleep(wait_s)
                await self._scan_after_publish(models_to_check)
                await self._monitor_exits()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[NWPLAG] loop error — sleeping 60s")
                await asyncio.sleep(60.0)

    # ── Schedule computation ────────────────────────────────────────────────

    def _next_publish_slot(self) -> tuple[datetime, list[str]]:
        """Return (next_slot_time, [model_names_publishing_at_that_slot])."""
        now = datetime.now(timezone.utc)
        # Build flat list of (datetime, model) for next 24h
        events: list[tuple[datetime, str]] = []
        for model, hours in NWP_PUBLISH_SCHEDULE.items():
            for h in hours:
                # Today + offset, tomorrow + offset
                for day_delta in (0, 1):
                    slot = now.replace(hour=h, minute=POLL_OFFSET_MINUTES,
                                       second=0, microsecond=0) + timedelta(days=day_delta)
                    if slot > now:
                        events.append((slot, model))
        events.sort()
        # Group by exact same minute
        first_ts = events[0][0]
        same_slot = [m for ts, m in events if ts == first_ts]
        return first_ts, same_slot

    # ── Core: scan + decision after each publish event ──────────────────────

    async def _scan_after_publish(self, models: list[str]) -> None:
        """For each city with an active market, fetch the freshly-published models,
        diff μ vs prior, evaluate entry on the bucket whose P shifted most."""
        from analysis.weather.daily_audit import is_killed
        if is_killed("WEATHER_NWPLAG"):
            logger.info("[NWPLAG] auto-killed by daily_audit — skipping scan")
            return
        # Reuse the parent WeatherArb's caches: today's markets list, ICAO map, etc.
        wa = getattr(self.bot, "weather_arb", None)
        if wa is None:
            logger.debug("[NWPLAG] WeatherArb not attached — skipping scan")
            return
        if len(self._active_positions) >= NWPLAG_MAX_CONCURRENT:
            logger.info("[NWPLAG] %d/%d slots full — skipping new entries",
                        len(self._active_positions), NWPLAG_MAX_CONCURRENT)
            return

        # Need fresh markets list and METAR for context
        await wa._refresh_today_markets()
        markets = wa._today_markets_cache or []
        if not markets:
            logger.debug("[NWPLAG] no active markets — skip")
            return

        # Deduplicate by city (single forecast call per city per scan)
        cities_seen: set[str] = set()
        scanned = 0
        entered = 0

        for entry in markets:
            city = entry["city"]
            if city in cities_seen:
                continue
            cities_seen.add(city)
            lat, lon = entry["lat"], entry["lon"]

            # Fetch the new μ for each freshly-published model
            new_mu_by_model = await self._fetch_models_for_city(lat, lon, models)
            if not new_mu_by_model:
                continue

            # Compute μ_new and μ_old for this city
            from strategy.weather_arb import CITY_NAME_TO_SLUG
            slug = CITY_NAME_TO_SLUG.get(city, "")
            shift_summary = self._compute_shift(slug, new_mu_by_model)
            if not shift_summary:
                continue

            scanned += 1
            delta_mu = shift_summary["delta_mu"]
            mu_new   = shift_summary["mu_new"]
            mu_old   = shift_summary["mu_old"]

            if abs(delta_mu) < DELTA_TRIGGER_C:
                logger.debug(
                    "[NWPLAG] %s no shift: μ %.2f→%.2f (Δ=%+.2f < %.2f°C)",
                    city, mu_old, mu_new, delta_mu, DELTA_TRIGGER_C,
                )
                continue

            logger.info(
                "[NWPLAG] %s SHIFT μ %.2f→%.2f (Δ=%+.2f°C, models: %s)",
                city, mu_old, mu_new, delta_mu, ",".join(new_mu_by_model.keys()),
            )

            # Now evaluate ALL buckets for this city against new μ — find the bucket
            # whose ask is stale relative to the new model probability.
            try:
                ok = await self._evaluate_and_enter(wa, city, lat, lon, mu_new, delta_mu)
                if ok:
                    entered += 1
                    if len(self._active_positions) >= NWPLAG_MAX_CONCURRENT:
                        break
            except Exception:
                logger.exception("[NWPLAG] entry error %s", city)

        logger.info("[NWPLAG] scan done — %d cities scanned, %d entries",
                    scanned, entered)

    async def _fetch_models_for_city(self, lat: float, lon: float,
                                      models: list[str]) -> dict[str, float]:
        """Fetch D+0 daily max for each requested model. One API call total."""
        models_param = ",".join(models)
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max&temperature_unit=celsius"
            f"&forecast_days=2&models={models_param}"
        )
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return {}
                    data = await resp.json()
            daily = data.get("daily", {})
            today_str = datetime.now(timezone.utc).date().isoformat()
            times = daily.get("time", [])
            try:
                today_idx = times.index(today_str)
            except ValueError:
                today_idx = 0
            out: dict[str, float] = {}
            for k in daily:
                if "temperature_2m_max" not in k:
                    continue
                suffix = k[len("temperature_2m_max"):].lstrip("_") or models[0]
                arr = daily[k]
                if today_idx < len(arr) and arr[today_idx] is not None:
                    out[suffix] = float(arr[today_idx])
            return out
        except Exception as e:
            logger.debug("[NWPLAG] fetch error lat=%.2f: %s", lat, e)
            return {}

    def _compute_shift(self, slug: str, new_mu_by_model: dict[str, float]
                       ) -> Optional[dict]:
        """Compare new μ_ensemble to prior cached μ_ensemble; return delta if any."""
        new_mu = sum(new_mu_by_model.values()) / len(new_mu_by_model)
        # Pull each model's prior cached μ
        old_mus = []
        for model in new_mu_by_model:
            entry = self._mu_history.get((model, slug))
            if entry:
                old_mus.append(entry[1])
        if not old_mus:
            # First observation — cache and skip
            for model, mu in new_mu_by_model.items():
                self._mu_history[(model, slug)] = (time.time(), mu)
            return None

        old_mu = sum(old_mus) / len(old_mus)

        # Update cache
        now_ts = time.time()
        for model, mu in new_mu_by_model.items():
            self._mu_history[(model, slug)] = (now_ts, mu)

        return {"mu_new": new_mu, "mu_old": old_mu, "delta_mu": new_mu - old_mu}

    async def _evaluate_and_enter(self, wa, city: str, lat: float, lon: float,
                                    mu_new: float, delta_mu: float) -> bool:
        """Find the bucket whose ask is most stale vs the new μ; enter if edge passes."""
        from strategy.weather_arb import (
            CITY_NAME_TO_SLUG, CITY_SIGMA_C, _outcome_prob, _parse_outcome,
            _parse_token_ids,
        )
        from strategy.fee_model import taker_fee_rate

        slug      = CITY_NAME_TO_SLUG.get(city, "")
        month     = datetime.now(timezone.utc).month
        cal_sigma = CITY_SIGMA_C.get(slug, {}).get(month, 1.0)

        best_candidate = None
        best_edge_after_fee = -1.0

        # Iterate all current today's-market buckets for this city
        for entry in wa._today_markets_cache:
            if entry["city"] != city:
                continue
            mkt = entry["mkt"]
            if mkt.get("closed", False):
                continue
            token_ids = _parse_token_ids(mkt.get("clobTokenIds", []))
            if not token_ids:
                continue
            token_id = token_ids[0]
            if token_id in wa._fired_tokens or token_id in self._active_positions:
                continue
            prices_raw = mkt.get("outcomePrices", '["0.5"]')
            prices     = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            ask = float(prices[0])
            if ask < MIN_ENTRY_ASK or ask > MAX_ENTRY_ASK:
                continue

            lo_c, hi_c, _ = _parse_outcome(mkt.get("question", ""))
            if lo_c is None and hi_c is None:
                continue

            # Compute new fair_prob under shifted μ
            fair_prob = _outcome_prob(mu_new, lo_c, hi_c, cal_sigma)
            edge_gross = fair_prob - ask
            if edge_gross <= 0:
                continue

            # Estimate net edge after taker fee
            fee_rate = taker_fee_rate(ask)
            edge_after_fee = edge_gross - fee_rate  # 1pp fee = 0.01 edge reduction (approx)
            if edge_after_fee < MIN_EDGE_AFTER_FEE:
                continue

            # Ask-stability check: only fire if ask hasn't moved much recently
            if not self._ask_is_stable(token_id, ask):
                logger.debug("[NWPLAG] %s ask=%.3f moved >%.2fpp in %ds — skip (already repriced)",
                             city, ask, ASK_STABILITY_PCT, ANCHOR_SECONDS)
                continue

            if edge_after_fee > best_edge_after_fee:
                best_edge_after_fee = edge_after_fee
                best_candidate = {
                    "token_id":  token_id,
                    "mkt":       mkt,
                    "ask":       ask,
                    "fair_prob": fair_prob,
                    "lo_c":      lo_c,
                    "hi_c":      hi_c,
                    "edge":      edge_gross,
                    "edge_net":  edge_after_fee,
                    "delta_mu":  delta_mu,
                    "mu_new":    mu_new,
                }

        if best_candidate is None:
            return False

        return await self._execute_entry(wa, city, best_candidate)

    def _ask_is_stable(self, token_id: str, current_ask: float) -> bool:
        """Return True if ask hasn't moved >ASK_STABILITY_PCT in last ANCHOR_SECONDS.
        Without WS feed in this module, approximate: we cache asks per scan cycle.
        On first observation we accept the trade (no history yet to be unstable).
        """
        history = self._ask_history[token_id]
        now_ts  = time.time()
        # Trim old
        cutoff = now_ts - ANCHOR_SECONDS
        history[:] = [(ts, a) for ts, a in history if ts >= cutoff]
        if not history:
            history.append((now_ts, current_ask))
            return True
        max_a = max(a for _, a in history)
        min_a = min(a for _, a in history)
        if (max_a - min_a) > ASK_STABILITY_PCT:
            history.append((now_ts, current_ask))
            return False
        history.append((now_ts, current_ask))
        return True

    async def _execute_entry(self, wa, city: str, cand: dict) -> bool:
        """Execute FAK taker entry, register position with hold-time exit target."""
        from strategy.momentum import Direction as _Dir, TPSLLevels as _TPSL
        from execution.order_manager import OrderStatus

        bankroll = wa._get_bankroll()
        # Kelly-ish sizing: stake = bankroll × per_position × edge / (1 − ask)
        kelly_f = cand["edge_net"] / max(0.01, 1.0 - cand["ask"])
        raw_stake = bankroll * NWPLAG_PER_POSITION * kelly_f
        stake = max(NWPLAG_MIN_STAKE,
                    min(NWPLAG_MAX_STAKE,
                        bankroll * NWPLAG_BANKROLL_FRAC,
                        raw_stake))

        logger.info(
            "[NWPLAG] ENTRY %s ask=%.3f fair=%.3f edge=%.3f(net=%.3f) μ_shift=%+.2f°C stake=$%.1f",
            city, cand["ask"], cand["fair_prob"], cand["edge"], cand["edge_net"],
            cand["delta_mu"], stake,
        )

        token_id = cand["token_id"]
        mkt      = cand["mkt"]

        try:
            fill = await self.bot.orders.limit_buy(
                token_id=token_id,
                intended_price=cand["ask"],
                stake_usd=stake,
                direction=_Dir.BUY_YES,
                neg_risk=mkt.get("negRisk", True),
                fast_fail=True,   # FAK: take what's at top of book; cancel rest
            )
            if fill.status != OrderStatus.FILLED or fill.total_size <= 0:
                logger.info("[NWPLAG] entry not filled %s status=%s", city, fill.status)
                return False

            self.bot.risk.open_position(
                token_id=token_id,
                asset="WEATHER",
                direction=_Dir.BUY_YES,
                stake=fill.total_size * fill.avg_fill_price,
                entry_price=fill.avg_fill_price,
                tpsl=_TPSL(take_profit=0.0, stop_loss=0.0,
                            tp_pct=0.0, sl_pct=0.0, risk_reward=0.0),
                condition_id=mkt.get("conditionId", ""),
                window_end_ts=0.0,
                is_bond=True,
                bond_outcome_direction="up",
                bond_entry_class="WEATHER_NWPLAG",
            )
            # Mark our position so the main weather loop doesn't double-touch it
            wa._fired_tokens.add(token_id)
            meta = self.bot._open_meta.setdefault(token_id, {})
            meta["signal_source"] = f"WEATHER/{city}/STRAT_5_NWPLAG"
            meta["city"] = city
            now_ts = time.time()
            self._active_positions[token_id] = {
                "opened_ts":      now_ts,
                "target_exit_ts": now_ts + HOLD_SECONDS_TARGET,
                "hard_exit_ts":   now_ts + HOLD_SECONDS_MAX,
                "entry_price":    fill.avg_fill_price,
                "city":           city,
                "lo_c":           cand["lo_c"],
                "hi_c":           cand["hi_c"],
            }
            logger.info(
                "[NWPLAG] FILLED %s @ %.4f size=%.0f tag=NWPLAG hold→%dmin",
                city, fill.avg_fill_price, fill.total_size,
                HOLD_SECONDS_TARGET // 60,
            )
            return True
        except Exception:
            logger.exception("[NWPLAG] order error %s", city)
            return False

    # ── Exit logic ──────────────────────────────────────────────────────────

    async def _monitor_exits(self) -> None:
        """Sweep _active_positions and exit positions past their hold target.

        Exit rule:
          - If now ≥ target_exit_ts AND best_bid ≥ entry_price + 0.03: take profit (FAK)
          - If now ≥ hard_exit_ts: force exit regardless of bid (FAK)
        """
        if not self._active_positions:
            return
        now_ts = time.time()
        to_close: list[str] = []

        for token_id, info in list(self._active_positions.items()):
            risk_pos = getattr(self.bot.risk, "open_positions", {}).get(token_id)
            if risk_pos is None:
                to_close.append(token_id)
                continue
            current_bid = getattr(risk_pos, "current_price", 0.0) or 0.0
            entry_price = info["entry_price"]
            held_s = now_ts - info["opened_ts"]

            # Target window: take profit if reprice has happened
            if now_ts >= info["target_exit_ts"] and now_ts < info["hard_exit_ts"]:
                if current_bid >= entry_price + 0.03:
                    await self._exit_position(token_id, info, current_bid, "TARGET_TP")
                    to_close.append(token_id)
                continue

            # Hard exit: regardless of bid
            if now_ts >= info["hard_exit_ts"]:
                await self._exit_position(token_id, info, current_bid, "HARD_TIMEOUT")
                to_close.append(token_id)
                continue

            logger.debug(
                "[NWPLAG] held %s for %.0fs bid=%.3f entry=%.3f Δ=%+.3f",
                token_id[:10], held_s, current_bid, entry_price, current_bid - entry_price,
            )

        for tid in to_close:
            self._active_positions.pop(tid, None)

    async def _exit_position(self, token_id: str, info: dict,
                              current_bid: float, reason: str) -> None:
        """FAK taker exit at (bid − 0.01)."""
        try:
            risk_pos = self.bot.risk.open_positions.get(token_id)
            if risk_pos is None:
                return
            sell_price = max(0.01, round(current_bid - 0.01, 4))
            logger.info(
                "[NWPLAG] EXIT %s reason=%s bid=%.3f sell@%.3f Δ_from_entry=%+.3f",
                info["city"], reason, current_bid, sell_price,
                current_bid - info["entry_price"],
            )
            await self.bot.orders.limit_sell(
                token_id=token_id,
                price=sell_price,
                size=risk_pos.shares,
                condition_id=risk_pos.condition_id,
            )
        except Exception:
            logger.exception("[NWPLAG] exit error %s", info.get("city", "?"))
