"""Live monitor of WU's Summary "High Temp" widget across the 7 stations.

Polls each station every `--interval` seconds. Detects the moment WU's daily
Summary transitions from "No data recorded" to a populated High Temp value.
That transition IS the rebalancing trigger for the strategy — it's when the
final daily-high number is published and the market will converge to it
within minutes.

Tracks two candidate weather-days per station (UTC today and UTC yesterday)
because station-local "trading day" can fall on either side of UTC midnight.

Output:
  - JSONL: one line per (station, day) scrape per cycle, written to --out
  - stderr: human-readable TRANSITION events when a Summary first populates,
    plus a one-line cycle summary

Usage:
    python3 -m analysis.weather.wu_monitor --interval 60 --out /tmp/wu_monitor.jsonl
    python3 -m analysis.weather.wu_monitor --interval 30 --cities nyc,tokyo --max-cycles 10
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from playwright.async_api import async_playwright

from analysis.weather.stations import STATIONS, Station
from analysis.weather.wu_high_scraper import scrape_one
from analysis.weather.live_accumulator import log_actual

DEFAULT_INTERVAL_S = 60
DEFAULT_MAX_PARALLEL = 14   # 7 stations × 2 days


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _days_to_monitor() -> list[date]:
    """UTC today + UTC yesterday. Captures both sides of timezone boundary."""
    t = _today_utc()
    return [t, t - timedelta(days=1)]


async def _scrape_with(page, station: Station, day: date) -> dict:
    return await scrape_one(page, station, day)


async def monitor_cycle(pages: list, stations: list[Station], days: list[date]) -> list[dict]:
    """One sweep: scrape every (station, day) pair concurrently across pages."""
    targets = list(itertools.product(stations, days))
    # Round-robin across the page pool
    n = len(pages)
    tasks = [
        _scrape_with(pages[i % n], st, d)
        for i, (st, d) in enumerate(targets)
    ]
    return await asyncio.gather(*tasks, return_exceptions=False)


def _log_jsonl(fh, rec: dict, cycle_idx: int) -> None:
    rec["cycle"] = cycle_idx
    fh.write(json.dumps(rec) + "\n")
    fh.flush()


def _emit_transition(rec: dict) -> None:
    msg = (f"  *** TRANSITION  {rec['city']:<14}  {rec['date']}  "
           f"high={rec['high_f']}°F ({rec['high_c']}°C)  "
           f"at {rec['fetched_at_utc']}")
    print(msg, file=sys.stderr, flush=True)


async def run(cities: list[str], interval_s: int, out_path: Optional[str],
              max_cycles: Optional[int]) -> int:
    stations = [STATIONS[c] for c in cities]
    days_fn = _days_to_monitor  # re-evaluated each cycle (rolls over at UTC midnight)

    fh = open(out_path, "a") if out_path else None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
            viewport={"width": 1400, "height": 1800},
            locale="en-US",
        )
        n_pages = min(DEFAULT_MAX_PARALLEL, len(stations) * 2)
        pages = [await ctx.new_page() for _ in range(n_pages)]

        # State: per (city, date) the last observed high_f. None until first scrape.
        # Transition fires when value goes from None → not-None for the first time.
        last_high: dict[tuple[str, str], Optional[float]] = {}

        cycle = 0
        try:
            while True:
                cycle += 1
                started = datetime.now(timezone.utc)
                days = days_fn()
                results = await monitor_cycle(pages, stations, days)
                n_populated = 0
                n_transitions = 0
                for rec in results:
                    key = (rec["city"], rec["date"])
                    prev = last_high.get(key)
                    cur = rec["high_f"]
                    if cur is not None:
                        n_populated += 1
                    if cur is not None and prev is None:
                        n_transitions += 1
                        _emit_transition(rec)
                        try:
                            log_actual(
                                slug=f"wu-{rec['city']}-{rec['date']}",
                                city_slug=rec["city"],
                                valid_day=rec["date"],
                                wu_high_c=float(rec["high_c"]),
                            )
                        except Exception:
                            pass
                    last_high[key] = cur
                    if fh is not None:
                        _log_jsonl(fh, rec, cycle)
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                print(f"[cycle {cycle:>3}] scraped={len(results)} "
                      f"populated={n_populated} transitions={n_transitions} "
                      f"elapsed={elapsed:.1f}s",
                      file=sys.stderr, flush=True)

                if max_cycles is not None and cycle >= max_cycles:
                    break
                # Sleep to honor interval, accounting for cycle time
                sleep_s = max(1.0, interval_s - elapsed)
                await asyncio.sleep(sleep_s)
        finally:
            await browser.close()
            if fh is not None:
                fh.close()
    return 0


def _cli():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_S,
                    help=f"seconds between cycles (default {DEFAULT_INTERVAL_S})")
    ap.add_argument("--cities", help="comma-separated city slugs (default all 7)")
    ap.add_argument("--out", help="JSONL output file (appended)")
    ap.add_argument("--max-cycles", type=int, help="stop after N cycles (default: run forever)")
    args = ap.parse_args()
    cities = args.cities.split(",") if args.cities else list(STATIONS.keys())
    for c in cities:
        if c not in STATIONS:
            print(f"ERROR: unknown city: {c}. Known: {sorted(STATIONS)}", file=sys.stderr)
            return 2
    return asyncio.run(run(cities, args.interval, args.out, args.max_cycles))


if __name__ == "__main__":
    sys.exit(_cli())
