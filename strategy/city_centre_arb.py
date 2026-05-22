"""
STRATEGY #2 — CITY-CENTRE ARBITRAGE.

Edge thesis (Polymarket Weather research, May 2026):
    "Polymarket weather markets resolve at specific NOAA/WU airport stations.
    Most retail traders price off city-centre weather apps. The gap between
    city-centre and airport temperatures has a predictable sign and magnitude
    based on local geography."

Example (LAX):
    City-centre LA midday max:  28°C (urban heat island)
    KLAX airport (coastal):     24°C (marine layer)
    Retail apps quote ≈28°C → market overprices "28°C" bucket and underprices "24°C".
    But WU resolves against KLAX → "24°C" wins.

Mechanism:
    1. Maintain per-city CITY_VS_AIRPORT_DELTA table from 5yr ASOS pairs.
    2. Forecast μ_airport via the normal ensemble (already in WeatherArb).
    3. Compute μ_retail = μ_airport + delta_to_retail (the temp retail will see).
    4. If buckets containing μ_retail and μ_airport are DIFFERENT, the
       airport bucket is structurally underpriced → enter GTC maker order
       at best_ask − 1¢ (post-only).
    5. Hold to resolution. Settle for $1 if airport bucket wins.

This is a SET-AND-FORGET strategy:
    - GTC maker orders earn rebate
    - Hold to resolution = no exit fee
    - Low frequency (only triggers when μ straddles a boundary the wrong way)
    - High per-trade edge (structural, doesn't get arbed by other bots looking
      at the same NWP data — the gap IS our information advantage)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta, date
from typing import Optional

logger = logging.getLogger(__name__)

# ── Per-city airport-vs-city-centre delta (°C) ───────────────────────────────
# Sign convention: T_city_centre − T_airport
# Positive = airport is COOLER than retail thinks (coastal, suburban airports)
# Negative = airport is HOTTER than retail thinks (urban heat island stations)
#
# Calibrated from 5yr ASOS airport vs NCEI city-centre stations (approximate).
# Refine empirically with the live accumulator over 30+ days.
CITY_VS_AIRPORT_DELTA_C: dict[str, dict[int, float]] = {
    # Coastal / marine-layer airports: city centre runs WARMER than airport in summer
    "los-angeles":    {1: +0.5, 2: +0.5, 3: +1.0, 4: +1.5, 5: +2.0, 6: +2.5,
                        7: +3.0, 8: +3.0, 9: +2.5, 10: +2.0, 11: +1.0, 12: +0.5},
    "san-francisco":  {1: +1.0, 2: +1.0, 3: +1.5, 4: +2.0, 5: +2.5, 6: +3.0,
                        7: +3.0, 8: +3.0, 9: +2.5, 10: +2.0, 11: +1.5, 12: +1.0},
    "seattle":        {1: +0.5, 2: +0.5, 3: +1.0, 4: +1.0, 5: +1.5, 6: +1.5,
                        7: +1.5, 8: +1.5, 9: +1.0, 10: +1.0, 11: +0.5, 12: +0.5},
    "miami":          {1: +0.5, 2: +0.5, 3: +0.5, 4: +0.5, 5: +1.0, 6: +1.0,
                        7: +1.0, 8: +1.0, 9: +1.0, 10: +0.5, 11: +0.5, 12: +0.5},
    "amsterdam":      {1: +0.5, 2: +0.5, 3: +0.5, 4: +1.0, 5: +1.0, 6: +1.5,
                        7: +1.5, 8: +1.5, 9: +1.0, 10: +0.5, 11: +0.5, 12: +0.5},
    "london":         {1: +0.5, 2: +0.5, 3: +1.0, 4: +1.0, 5: +1.5, 6: +1.5,
                        7: +2.0, 8: +2.0, 9: +1.5, 10: +1.0, 11: +0.5, 12: +0.5},
    # Suburban airports: similar
    "nyc":            {1: +0.5, 2: +0.5, 3: +1.0, 4: +1.0, 5: +1.5, 6: +1.5,
                        7: +1.5, 8: +1.5, 9: +1.0, 10: +1.0, 11: +0.5, 12: +0.5},
    "chicago":        {1: +0.5, 2: +0.5, 3: +0.5, 4: +1.0, 5: +1.0, 6: +1.5,
                        7: +1.5, 8: +1.5, 9: +1.0, 10: +1.0, 11: +0.5, 12: +0.5},
    "toronto":        {1: +0.0, 2: +0.0, 3: +0.5, 4: +0.5, 5: +1.0, 6: +1.0,
                        7: +1.0, 8: +1.0, 9: +0.5, 10: +0.5, 11: +0.0, 12: +0.0},
    "tokyo":          {1: +0.5, 2: +0.5, 3: +1.0, 4: +1.5, 5: +1.5, 6: +1.5,
                        7: +1.5, 8: +1.5, 9: +1.0, 10: +1.0, 11: +0.5, 12: +0.5},
    "paris":          {1: +0.5, 2: +0.5, 3: +1.0, 4: +1.0, 5: +1.5, 6: +1.5,
                        7: +2.0, 8: +2.0, 9: +1.5, 10: +1.0, 11: +0.5, 12: +0.5},
    "madrid":         {1: +0.0, 2: +0.0, 3: +0.5, 4: +0.5, 5: +0.5, 6: +0.5,
                        7: +0.5, 8: +0.5, 9: +0.5, 10: +0.5, 11: +0.0, 12: +0.0},
    # Inland airports often hotter than city centre (less green cover at airport)
    "denver":         {1: -0.5, 2: -0.5, 3: -0.5, 4: -0.5, 5: -0.5, 6: -1.0,
                        7: -1.0, 8: -1.0, 9: -0.5, 10: -0.5, 11: -0.5, 12: -0.5},
    "dallas":         {1: +0.0, 2: +0.0, 3: +0.0, 4: +0.0, 5: +0.5, 6: +0.5,
                        7: +0.5, 8: +0.5, 9: +0.5, 10: +0.0, 11: +0.0, 12: +0.0},
    "houston":        {1: +0.0, 2: +0.0, 3: +0.5, 4: +0.5, 5: +0.5, 6: +1.0,
                        7: +1.0, 8: +1.0, 9: +1.0, 10: +0.5, 11: +0.0, 12: +0.0},
    "atlanta":        {1: +0.0, 2: +0.0, 3: +0.5, 4: +0.5, 5: +0.5, 6: +1.0,
                        7: +1.0, 8: +1.0, 9: +0.5, 10: +0.5, 11: +0.0, 12: +0.0},
}

# ── Strategy parameters ──────────────────────────────────────────────────────
CITYCTR_ENABLED              = True
CITYCTR_MIN_DELTA_C          = 0.6   # delta must be at least this large to consider
CITYCTR_BOUNDARY_PROXIMITY_C = 0.4   # μ_airport must be within this of a bucket boundary
CITYCTR_MIN_EDGE             = 0.05  # net edge after fees
CITYCTR_ASK_LO               = 0.05  # min ask
CITYCTR_ASK_HI               = 0.45  # max ask (avoid favourites)
CITYCTR_BANKROLL_FRAC        = 0.15  # 15% of bankroll reserved
CITYCTR_PER_POSITION         = 0.04  # 4% per position
CITYCTR_MIN_STAKE            = 5.0
CITYCTR_MAX_STAKE            = 25.0
CITYCTR_MAX_CONCURRENT       = 3
CITYCTR_SCAN_INTERVAL_S      = 3600  # 1h scan loop (set-and-forget)


class CityCentreArb:
    """Structural-mispricing strategy. GTC maker entries; hold to resolution."""

    def __init__(self, bot) -> None:
        self.bot      = bot
        self._task: Optional[asyncio.Task] = None
        self._fired:  set[str] = set()   # token_ids already entered this run
        self._enabled = CITYCTR_ENABLED

    def start(self) -> None:
        if not self._enabled:
            logger.info("[CITYCTR] disabled by config")
            return
        self._task = asyncio.create_task(self._loop(), name="city_centre_arb_loop")
        logger.info("[CITYCTR] started — %d cities calibrated", len(CITY_VS_AIRPORT_DELTA_C))

    async def _loop(self) -> None:
        await asyncio.sleep(120.0)  # wait for bot init + first NWP fetch cycle
        while True:
            try:
                await self._scan()
            except Exception:
                logger.exception("[CITYCTR] scan error")
            await asyncio.sleep(CITYCTR_SCAN_INTERVAL_S)

    async def _scan(self) -> None:
        wa = getattr(self.bot, "weather_arb", None)
        if wa is None:
            return
        await wa._refresh_today_markets()
        markets = wa._today_markets_cache or []
        if not markets:
            return

        if sum(1 for _ in self._fired) >= CITYCTR_MAX_CONCURRENT:
            logger.info("[CITYCTR] %d slots full", len(self._fired))
            return

        from strategy.weather_arb import (
            CITY_NAME_TO_SLUG, CITY_SIGMA_C, _outcome_prob, _parse_outcome,
            _parse_token_ids,
        )
        from strategy.fee_model import taker_fee_rate, MAKER_REBATE_FRAC

        month = datetime.now(timezone.utc).month
        scanned_cities: set[str] = set()
        entries_made = 0

        for entry in markets:
            city = entry["city"]
            if city in scanned_cities:
                continue
            scanned_cities.add(city)

            slug  = CITY_NAME_TO_SLUG.get(city, "")
            delta = CITY_VS_AIRPORT_DELTA_C.get(slug, {}).get(month)
            if delta is None or abs(delta) < CITYCTR_MIN_DELTA_C:
                continue

            # Get tomorrow's NWP forecast (airport-aligned)
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            today_str = date.today().isoformat()
            lat, lon = entry["lat"], entry["lon"]
            forecast = await wa._get_forecast(lat, lon, today_str, tomorrow, city)
            if not forecast or tomorrow not in forecast:
                continue
            mu_airport, sigma = forecast[tomorrow]
            cal_sigma = CITY_SIGMA_C.get(slug, {}).get(month, sigma)

            # Compute the temp retail would see
            mu_retail = mu_airport + delta

            # Find buckets — we want the bucket containing μ_airport when it's
            # DIFFERENT from the bucket containing μ_retail (boundary crossing).
            for mk_entry in markets:
                if mk_entry["city"] != city:
                    continue
                mkt = mk_entry["mkt"]
                if mkt.get("closed", False):
                    continue
                token_ids = _parse_token_ids(mkt.get("clobTokenIds", []))
                if not token_ids:
                    continue
                token_id = token_ids[0]
                if token_id in self._fired or token_id in wa._fired_tokens:
                    continue

                lo_c, hi_c, _ = _parse_outcome(mkt.get("question", ""))
                if lo_c is None or hi_c is None:
                    continue

                # Bucket must CONTAIN μ_airport
                if not (lo_c - 0.5 <= mu_airport < hi_c + 0.5):
                    continue
                # ... AND NOT contain μ_retail (retail prices it elsewhere)
                if lo_c - 0.5 <= mu_retail < hi_c + 0.5:
                    continue
                # μ_airport must be reasonably close to the boundary on the
                # retail side (otherwise the model already prices it correctly)
                dist_to_retail_side = abs(mu_airport - (lo_c if delta > 0 else hi_c))
                if dist_to_retail_side > CITYCTR_BOUNDARY_PROXIMITY_C:
                    continue

                prices_raw = mkt.get("outcomePrices", '["0.5"]')
                prices     = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                ask = float(prices[0])
                if ask < CITYCTR_ASK_LO or ask > CITYCTR_ASK_HI:
                    continue

                # Compute model fair_prob from μ_airport (which we trust)
                fair_prob = _outcome_prob(mu_airport, lo_c, hi_c, cal_sigma)
                edge_gross = fair_prob - ask
                # Maker rebate net: we earn rebate, so effective edge ≈ gross + 0.3% rebate
                rebate_rate = MAKER_REBATE_FRAC * taker_fee_rate(ask)
                edge_net = edge_gross + rebate_rate
                if edge_net < CITYCTR_MIN_EDGE:
                    continue

                logger.info(
                    "[CITYCTR] CANDIDATE %s bucket=[%.1f,%.1f) μ_air=%.2f μ_ret=%.2f "
                    "Δ=%+.2f ask=%.3f fair=%.3f edge=%.3f",
                    city, lo_c, hi_c, mu_airport, mu_retail, delta,
                    ask, fair_prob, edge_net,
                )

                if await self._execute_maker_entry(wa, city, mkt, token_id, ask,
                                                     fair_prob, lo_c, hi_c, mu_airport,
                                                     edge_net, delta):
                    entries_made += 1
                    if entries_made + len(self._fired) >= CITYCTR_MAX_CONCURRENT:
                        return

        logger.debug("[CITYCTR] scan done — %d cities scanned, %d new entries",
                     len(scanned_cities), entries_made)

    async def _execute_maker_entry(self, wa, city: str, mkt: dict, token_id: str,
                                     ask: float, fair_prob: float,
                                     lo_c: float, hi_c: float, mu_airport: float,
                                     edge_net: float, delta: float) -> bool:
        """GTC post-only maker entry at (best_ask − 1¢) to earn rebate."""
        from strategy.momentum import Direction as _Dir, TPSLLevels as _TPSL
        from execution.order_manager import OrderStatus

        bankroll = wa._get_bankroll()
        kelly_f = edge_net / max(0.01, 1.0 - ask)
        raw_stake = bankroll * CITYCTR_PER_POSITION * kelly_f
        stake = max(CITYCTR_MIN_STAKE,
                    min(CITYCTR_MAX_STAKE,
                        bankroll * CITYCTR_BANKROLL_FRAC,
                        raw_stake))

        # Place GTC at (ask − 1¢) → wait for a taker to cross to us
        maker_price = round(max(0.01, ask - 0.01), 4)
        logger.info(
            "[CITYCTR] ENTRY %s GTC@%.3f stake=$%.1f bucket=[%.1f,%.1f) Δ=%+.2f°C",
            city, maker_price, stake, lo_c, hi_c, delta,
        )

        try:
            # Limit-buy at maker price; if order manager doesn't support post-only,
            # the order rests until filled or cancelled
            fill = await self.bot.orders.limit_buy(
                token_id=token_id,
                intended_price=maker_price,
                stake_usd=stake,
                direction=_Dir.BUY_YES,
                neg_risk=mkt.get("negRisk", True),
                fast_fail=False,   # GTC: wait for fill
            )
            if fill.status != OrderStatus.FILLED or fill.total_size <= 0:
                logger.info("[CITYCTR] no immediate fill %s — order rests on book", city)
                # Still mark as in-flight so we don't re-submit
                self._fired.add(token_id)
                wa._fired_tokens.add(token_id)
                return True   # we did place an order; "entered" from a workflow POV

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
                bond_entry_class="WEATHER_CITYCTR",
            )
            meta = self.bot._open_meta.setdefault(token_id, {})
            meta["signal_source"] = f"WEATHER/{city}/STRAT_6_CITYCTR"
            meta["city"] = city
            meta["weather_question"] = mkt.get("question", "")
            meta["weather_date"] = (mkt.get("endDate", "") or "")[:10]
            self._fired.add(token_id)
            wa._fired_tokens.add(token_id)
            logger.info("[CITYCTR] FILLED %s @ %.4f size=%.0f tag=CITYCTR",
                        city, fill.avg_fill_price, fill.total_size)
            return True
        except Exception:
            logger.exception("[CITYCTR] order error %s", city)
            return False
