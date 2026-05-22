"""Scrape WU's "Summary > High Temp" for the validated airport stations.

This is the resolution source per Polymarket market rules. WU renders the
Summary widget client-side via Angular, so we use Playwright. The value is
always shown in °F when the browser locale is en-US; convert for °C markets.

Usage:
    python3 -m analysis.weather.wu_high_scraper --date 2026-05-19
    python3 -m analysis.weather.wu_high_scraper --date 2026-05-19 --city nyc
    python3 -m analysis.weather.wu_high_scraper --date today

Writes one JSON line per (city, date) to stdout. Also appendable to a file
via --out for the backtest harness to consume.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import date, datetime, timezone

from playwright.async_api import Page, async_playwright

from analysis.weather.stations import STATIONS, Station

WU_BASE = "https://www.wunderground.com/history/daily"
NAV_TIMEOUT_MS = 60_000
RENDER_WAIT_MS = 2_500
COOKIE_WAIT_MS = 800


async def _dismiss_cookies(page: Page) -> None:
    try:
        btn = await page.query_selector("button:has-text('Accept all')")
        if btn:
            await btn.click()
            await page.wait_for_timeout(COOKIE_WAIT_MS)
    except Exception:
        pass


def _parse_hourly_max(body: str, high_f: float | None) -> str | None:
    """Return local time string (e.g. '2:53 PM') of the max-temp hour from the
    WU hourly observations table. WU inner_text renders rows as:
      '2:53 PM\\t74\\t55\\t71\\tWSW\\t...'
    First tries to match a row within ±1°F of the Summary high_f; falls back
    to the row with the maximum temperature."""
    rows = re.findall(r'(\d{1,2}:\d{2}\s+[AP]M)\s+(\d{2,3}(?:\.\d+)?)', body, re.IGNORECASE)
    if not rows:
        return None
    if high_f is not None:
        for t_str, temp_str in rows:
            try:
                if abs(float(temp_str) - high_f) <= 1.0:
                    return t_str.strip()
            except ValueError:
                continue
    # Fallback: time of maximum observed temperature
    best_t, best_temp = None, float("-inf")
    for t_str, temp_str in rows:
        try:
            temp = float(temp_str)
            if temp > best_temp:
                best_temp, best_t = temp, t_str.strip()
        except ValueError:
            continue
    return best_t


async def scrape_one(page: Page, station: Station, day: date) -> dict:
    """Return dict with high_f, high_c, no_data, raw fields. Never raises on
    parse failure — caller checks `no_data` / `error`."""
    url = f"{WU_BASE}/{station.wu_path}/date/{day.year}-{day.month}-{day.day}"
    out = {
        "city": station.city_slug,
        "icao": station.icao,
        "date": day.isoformat(),
        "unit_market": station.unit,
        "bucket_width": station.bucket_width,
        "tz": station.tz,
        "url": url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "high_f": None,
        "high_c": None,
        "high_time_local": None,
        "low_f": None,
        "avg_f": None,
        "no_data": False,
        "error": None,
    }
    try:
        await page.goto(url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_timeout(RENDER_WAIT_MS)
        await _dismiss_cookies(page)

        body = await page.inner_text("body")
        out["no_data"] = "No data recorded" in body

        # WU Summary widget format (locale-default unit; °F for en-US):
        #   "High Temp\t<val>\t<historic>\t<record>"
        #   "Low Temp\t<val>\t<historic>\t<record>"
        #   "Day Average Temp\t<val>\t<historic>\t<record>"
        high = re.search(r"High\s*Temp\s*([\d.]+)", body)
        low  = re.search(r"Low\s*Temp\s*([\d.]+)", body)
        avg  = re.search(r"Day\s*Average\s*Temp\s*([\d.]+)", body)
        if high:
            f = float(high.group(1))
            out["high_f"] = f
            out["high_c"] = round((f - 32.0) * 5.0 / 9.0, 2)
            out["high_time_local"] = _parse_hourly_max(body, f)
        if low:
            out["low_f"] = float(low.group(1))
        if avg:
            out["avg_f"] = float(avg.group(1))
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


async def scrape_many(stations: list[Station], days: list[date]) -> list[dict]:
    results: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 1800},
            locale="en-US",
        )
        page = await ctx.new_page()
        for station in stations:
            for day in days:
                res = await scrape_one(page, station, day)
                results.append(res)
                print(json.dumps(res), flush=True)
        await browser.close()
    return results


def _parse_date(s: str) -> date:
    if s == "today":
        return datetime.now(timezone.utc).date()
    return date.fromisoformat(s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True, help="YYYY-MM-DD or 'today'")
    ap.add_argument("--end-date", help="If set, scrape inclusive range from --date to --end-date")
    ap.add_argument("--city", action="append",
                    help="One or more city slugs (default: all). Repeatable.")
    ap.add_argument("--out", help="File to append JSON lines to (in addition to stdout)")
    args = ap.parse_args()

    start = _parse_date(args.date)
    end = _parse_date(args.end_date) if args.end_date else start
    if end < start:
        print("ERROR: --end-date must be >= --date", file=sys.stderr)
        return 2

    days: list[date] = []
    d = start
    while d <= end:
        days.append(d)
        d = date.fromordinal(d.toordinal() + 1)

    if args.city:
        try:
            stations = [STATIONS[c] for c in args.city]
        except KeyError as e:
            print(f"ERROR: unknown city slug: {e}. Known: {sorted(STATIONS)}", file=sys.stderr)
            return 2
    else:
        stations = list(STATIONS.values())

    results = asyncio.run(scrape_many(stations, days))

    if args.out:
        with open(args.out, "a") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
