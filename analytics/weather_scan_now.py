#!/usr/bin/env python3
"""
Standalone weather-arb scan diagnostic.
Runs the full evaluation pipeline right now and prints ENTER / SKIP per city.
Usage:  python3 analytics/weather_scan_now.py
"""
import asyncio
import sys
import os
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

from strategy.weather_arb import (
    GAMMA_BASE, METEO_BASE,
    VALIDATED_CITY_SLUGS, STRAT1_SKIP_CITIES, CITY_NAME_TO_SLUG,
    CITY_ICAO, ICAO_UTC_OFFSET_H, CITY_COORDS,
    EDGE_MIN, MIN_FAIR_PROB, ASK_BAND_LO, ASK_BAND_HI,
    MIN_HOURS_BEFORE_RESOLUTION, SIGMA_SKIP_FLOOR,
    CITY_SIGMA_C_ERA5, CITY_SIGMA_C, CITY_ELEVATION_M,
    FORECAST_MODELS,
    _parse_city, _parse_outcome, _outcome_prob, _parse_token_ids,
    _get_regime,
)


def _hours_to_local_resolution(end_date_str: str, icao: str | None) -> float:
    utc_offset_h = ICAO_UTC_OFFSET_H.get(icao or "", 0)
    end_d = date.fromisoformat(end_date_str)
    midnight_local = datetime(end_d.year, end_d.month, end_d.day, tzinfo=timezone.utc) + timedelta(days=1) - timedelta(hours=utc_offset_h)
    now_utc = datetime.now(timezone.utc)
    return (midnight_local - now_utc).total_seconds() / 3600


async def fetch_events(sess: aiohttp.ClientSession) -> list[dict]:
    events: list[dict] = []
    offset = 0
    while True:
        url = f"{GAMMA_BASE}/events?closed=false&limit=200&offset={offset}&tag_slug=weather"
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                break
            page = await r.json()
        if not page:
            break
        events.extend(page)
        if len(page) < 200:
            break
        offset += len(page)
    return events


async def fetch_forecast(sess: aiohttp.ClientSession, lat: float, lon: float, tomorrow: str) -> tuple[float, float] | None:
    url = (f"{METEO_BASE}?latitude={lat}&longitude={lon}"
           f"&daily=temperature_2m_max&temperature_unit=celsius"
           f"&forecast_days=2&models={FORECAST_MODELS}")
    async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
        if r.status != 200:
            return None
        data = await r.json()
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    temp_keys = [k for k in daily if "temperature_2m_max" in k]
    for i, d in enumerate(dates):
        if d != tomorrow:
            continue
        vals = [float(daily[k][i]) for k in temp_keys if i < len(daily[k]) and daily[k][i] is not None]
        if not vals:
            return None
        mean = sum(vals) / len(vals)
        import math
        spread = max(vals) - min(vals) if len(vals) > 1 else 0.0
        sigma_nwp = spread / (2 * math.sqrt(3)) if spread > 0 else 0.0
        month = date.fromisoformat(tomorrow).month
        return mean, sigma_nwp
    return None


async def main():
    now_utc = datetime.now(timezone.utc)
    today = now_utc.strftime("%Y-%m-%d")
    tomorrow = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
    target_dates = {today, tomorrow}
    print(f"Scan at {now_utc.strftime('%H:%M UTC')} | today={today} tomorrow={tomorrow}\n")

    async with aiohttp.ClientSession() as sess:
        events = await fetch_events(sess)
    print(f"Fetched {len(events)} weather events from Gamma\n")

    results = []
    async with aiohttp.ClientSession() as sess:
        for ev in events:
            city = _parse_city(ev.get("title", ""))
            city_slug = CITY_NAME_TO_SLUG.get(city, "")

            if city_slug not in VALIDATED_CITY_SLUGS:
                continue
            if city_slug in STRAT1_SKIP_CITIES:
                results.append((city, "SKIP", "STRAT1_SKIP_CITIES"))
                continue

            coords = CITY_COORDS.get(city)
            if not coords:
                results.append((city, "SKIP", "no coords"))
                continue
            lat, lon = coords

            city_icao = CITY_ICAO.get(city)
            import json

            # Collect valid markets for this city across both dates
            valid_mkts = []
            for mkt in ev.get("markets", []):
                end_dt_str = mkt.get("endDate", "")
                end = end_dt_str[:10]
                if end not in target_dates:
                    continue
                if mkt.get("closed", False):
                    continue
                end_dt = datetime.fromisoformat(end_dt_str.replace("Z", "+00:00"))
                if end_dt <= now_utc:
                    continue
                h_left = _hours_to_local_resolution(end, city_icao)
                if h_left < MIN_HOURS_BEFORE_RESOLUTION:
                    continue
                prices_raw = mkt.get("outcomePrices", '["0.5","0.5"]')
                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                if float(prices[0]) <= 0.001:
                    continue
                valid_mkts.append((end, mkt))

            if not valid_mkts:
                results.append((city, "SKIP", "no valid markets (all too close to resolution or closed)"))
                continue

            # Use the earliest valid end_date for forecast/regime
            target_end = min(d for d, _ in valid_mkts)
            target_regime_date = target_end

            if _get_regime(city_slug, target_regime_date) == "volatile":
                results.append((city, "SKIP", f"regime=volatile ({target_regime_date})"))
                continue

            fc = await fetch_forecast(sess, lat, lon, target_end)
            if fc is None:
                results.append((city, "SKIP", "no forecast"))
                continue
            forecast_mean, sigma_nwp = fc

            month = date.fromisoformat(target_end).month
            cal_sigma = CITY_SIGMA_C.get(city_slug, {}).get(month)
            sigma_c = cal_sigma if cal_sigma is not None else max(sigma_nwp, 1.0)

            if sigma_c > SIGMA_SKIP_FLOOR:
                results.append((city, "SKIP", f"sigma={sigma_c:.2f} > {SIGMA_SKIP_FLOOR}"))
                continue

            era5_sigma = CITY_SIGMA_C_ERA5.get(city_slug, {}).get(month)

            best_edge = None
            best_poly = None
            best_fair = None
            best_label = None
            for end, mkt in valid_mkts:
                if end != target_end:
                    continue
                prices_raw = mkt.get("outcomePrices", '["0.5","0.5"]')
                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                poly_yes = float(prices[0])
                lo_c, hi_c, is_celsius = _parse_outcome(mkt.get("question", ""))
                if lo_c is None and hi_c is None:
                    continue
                fair_prob = _outcome_prob(forecast_mean, lo_c, hi_c, sigma_c)
                edge = fair_prob - poly_yes
                if edge >= EDGE_MIN and (best_edge is None or edge > best_edge):
                    best_edge = edge
                    best_poly = poly_yes
                    best_fair = fair_prob
                    best_label = f"edge={edge:.3f} fair={fair_prob:.3f} ask={poly_yes:.3f} fc={forecast_mean:.1f}°C σ={sigma_c:.2f} | {mkt.get('question','')[:55]}"

            if best_edge is None:
                results.append((city, "SKIP", f"no edge (fc={forecast_mean:.1f}°C σ={sigma_c:.2f}) era5σ={era5_sigma}"))
            elif best_fair < MIN_FAIR_PROB:
                results.append((city, "SKIP", f"fair={best_fair:.3f} < MIN_FAIR_PROB={MIN_FAIR_PROB} | {best_label}"))
            elif not (ASK_BAND_LO <= best_poly < ASK_BAND_HI):
                results.append((city, "SKIP", f"ask={best_poly:.3f} outside [{ASK_BAND_LO},{ASK_BAND_HI}) | {best_label}"))
            else:
                results.append((city, "ENTER", best_label))

    enters = [r for r in results if r[1] == "ENTER"]
    skips  = [r for r in results if r[1] == "SKIP"]

    print(f"{'='*60}")
    print(f"ENTER ({len(enters)}):")
    for city, _, reason in enters:
        print(f"  ✓ {city:20s} {reason}")

    print(f"\nSKIP ({len(skips)}):")
    for city, _, reason in skips:
        print(f"  ✗ {city:20s} {reason}")

    print(f"\nTotal evaluated: {len(results)} | ENTER: {len(enters)} | SKIP: {len(skips)}")


if __name__ == "__main__":
    asyncio.run(main())
