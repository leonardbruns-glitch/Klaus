"""
CITY-CENTRE DIVERGENCE — DATA COLLECTION ONLY (trading disabled 2026-05-22).

Rationale for disabling:
    STRAT_1 (WEATHER_ARB) already uses airport NWP as its model, so it detects
    the same mispricing that CITYCTR was designed to exploit.  CITYCTR adds no
    independent signal — it is STRAT_1 with extra steps and a lower edge floor.

Data collection purpose:
    Scan each hour and log every case where μ_airport (NWP) and μ_retail
    (μ_airport + CITY_VS_AIRPORT_DELTA) fall in different Polymarket buckets.
    Records go to logs/weather/cityctr_divergence.jsonl.

    Over time this lets us answer:
      - How often does bucket divergence produce genuine mispricing that
        STRAT_1 misses (because the structural gap is NOT in the NWP)?
      - Is the static delta table accurate, or does live city-centre data diverge?
      - Are there cities/months where δ is large enough to create a real edge?

    If the data shows STRAT_1 systematically misses these, re-enable with a
    real city-centre WU scrape as μ_retail instead of the static table.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
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

# ── Parameters ───────────────────────────────────────────────────────────────
CITYCTR_ENABLED              = False  # trading disabled — data collection only
CITYCTR_MIN_DELTA_C          = 0.6   # min delta to log a divergence event
CITYCTR_BOUNDARY_PROXIMITY_C = 0.4   # μ_airport within this of a boundary
CITYCTR_MIN_EDGE             = 0.05  # edge threshold (logged but not traded)
CITYCTR_ASK_LO               = 0.05
CITYCTR_ASK_HI               = 0.45
CITYCTR_SCAN_INTERVAL_S      = 3600  # 1h passive scan

DIVERGENCE_LOG = Path("logs/weather/cityctr_divergence.jsonl")


class CityCentreArb:
    """Passive divergence logger — no trading. Writes cityctr_divergence.jsonl."""

    def __init__(self, bot) -> None:
        self.bot   = bot
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="city_centre_arb_loop")
        logger.info("[CITYCTR] data-collection mode — %d cities, writing %s",
                    len(CITY_VS_AIRPORT_DELTA_C), DIVERGENCE_LOG)

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

        from strategy.weather_arb import (
            CITY_NAME_TO_SLUG, CITY_SIGMA_C, _outcome_prob, _parse_outcome,
            _parse_token_ids,
        )
        from strategy.fee_model import taker_fee_rate, MAKER_REBATE_FRAC

        now_utc   = datetime.now(timezone.utc)
        month     = now_utc.month
        tomorrow  = (date.today() + timedelta(days=1)).isoformat()
        today_str = date.today().isoformat()
        scanned_cities: set[str] = set()
        logged = 0

        for entry in markets:
            city = entry["city"]
            if city in scanned_cities:
                continue
            scanned_cities.add(city)

            slug  = CITY_NAME_TO_SLUG.get(city, "")
            delta = CITY_VS_AIRPORT_DELTA_C.get(slug, {}).get(month)
            if delta is None or abs(delta) < CITYCTR_MIN_DELTA_C:
                continue

            lat, lon = entry["lat"], entry["lon"]
            forecast = await wa._get_forecast(lat, lon, today_str, tomorrow, city)
            if not forecast or tomorrow not in forecast:
                continue
            mu_airport, sigma = forecast[tomorrow]
            cal_sigma  = CITY_SIGMA_C.get(slug, {}).get(month, sigma)
            mu_retail  = mu_airport + delta

            for mk_entry in markets:
                if mk_entry["city"] != city:
                    continue
                mkt = mk_entry["mkt"]
                if mkt.get("closed", False):
                    continue
                token_ids = _parse_token_ids(mkt.get("clobTokenIds", []))
                if not token_ids:
                    continue

                lo_c, hi_c, _ = _parse_outcome(mkt.get("question", ""))
                if lo_c is None or hi_c is None:
                    continue

                # Airport bucket: μ_airport strictly inside, μ_retail strictly outside
                if not (lo_c <= mu_airport < hi_c):
                    continue
                if lo_c <= mu_retail < hi_c:
                    continue

                dist_to_boundary = abs(mu_airport - (lo_c if delta > 0 else hi_c))
                if dist_to_boundary > CITYCTR_BOUNDARY_PROXIMITY_C:
                    continue

                prices_raw = mkt.get("outcomePrices", '["0.5"]')
                prices     = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                ask = float(prices[0])
                if ask < CITYCTR_ASK_LO or ask > CITYCTR_ASK_HI:
                    continue

                fair_prob  = _outcome_prob(mu_airport, lo_c, hi_c, cal_sigma)
                edge_gross = fair_prob - ask
                rebate     = MAKER_REBATE_FRAC * taker_fee_rate(ask)
                edge_net   = edge_gross + rebate

                record = {
                    "ts":            now_utc.isoformat(),
                    "city":          city,
                    "resolution_date": tomorrow,
                    "mu_airport":    round(mu_airport, 2),
                    "mu_retail":     round(mu_retail, 2),
                    "delta_c":       round(delta, 2),
                    "sigma":         round(cal_sigma, 2),
                    "bucket_lo":     lo_c,
                    "bucket_hi":     hi_c,
                    "dist_to_boundary": round(dist_to_boundary, 2),
                    "ask":           round(ask, 4),
                    "fair_prob":     round(fair_prob, 4),
                    "edge_gross":    round(edge_gross, 4),
                    "edge_net":      round(edge_net, 4),
                    "would_trade":   edge_net >= CITYCTR_MIN_EDGE,
                    "token_id":      token_ids[0],
                    "condition_id":  mkt.get("conditionId", ""),
                }
                self._log_divergence(record)
                logged += 1
                logger.debug(
                    "[CITYCTR] divergence %s bucket=[%.1f,%.1f) μ_air=%.2f μ_ret=%.2f "
                    "ask=%.3f fair=%.3f edge=%.3f would_trade=%s",
                    city, lo_c, hi_c, mu_airport, mu_retail,
                    ask, fair_prob, edge_net, record["would_trade"],
                )

        logger.info("[CITYCTR] scan done — %d cities, %d divergences logged",
                    len(scanned_cities), logged)

    def _log_divergence(self, record: dict) -> None:
        try:
            DIVERGENCE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with DIVERGENCE_LOG.open("a") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception:
            logger.exception("[CITYCTR] failed to write divergence log")
