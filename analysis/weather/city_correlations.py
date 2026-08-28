"""
Compute pairwise cross-city temperature lag correlations from ASOS 10yr data.

Output: top city pairs ranked by Pearson r at lag 0, 1, and 2 days.
Used to empirically validate and update upstream_map.py.

Usage:
    python3 -m analysis.weather.city_correlations [--lag 1] [--min-r 0.40] [--months 6,7,8,9]
    python3 -m analysis.weather.city_correlations --pair dallas chicago  # single pair detail
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from analysis.weather.stations import STATIONS
from analysis.weather.build_skill_matrix import fetch_asos_daily_max

CACHE_DIR = Path(__file__).parent.parent.parent / "logs" / "asos_cache"
YEAR_START = 2015
YEAR_END   = 2024


def _cache_path(icao: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{icao}_{YEAR_START}_{YEAR_END}.json"


def load_city_temps(city_slug: str) -> dict[str, float]:
    """Load or fetch ASOS temps for a city. Caches to disk."""
    station = STATIONS[city_slug]
    cp = _cache_path(station.icao)
    if cp.exists():
        return json.loads(cp.read_text())
    print(f"  fetching {city_slug} ({station.icao})...", end=" ", flush=True, file=sys.stderr)
    try:
        data = fetch_asos_daily_max(station.icao, YEAR_START, YEAR_END)
        cp.write_text(json.dumps(data))
        print(f"{len(data)} days", flush=True, file=sys.stderr)
        time.sleep(0.3)
        return data
    except Exception as e:
        print(f"ERROR: {e}", flush=True, file=sys.stderr)
        return {}


def pearson_r(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 10:
        return 0.0
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom = math.sqrt(
        sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)
    )
    return num / denom if denom > 0 else 0.0


def lag_correlation(
    upstream: dict[str, float],
    downstream: dict[str, float],
    lag_days: int = 1,
    months: set[int] | None = None,
) -> tuple[float, int]:
    """
    Pearson r between upstream[d] and downstream[d + lag_days].
    Returns (r, n_pairs).
    """
    from datetime import date, timedelta
    pairs_up: list[float] = []
    pairs_dn: list[float] = []
    for d_str, up_val in upstream.items():
        if months:
            m = int(d_str[5:7])
            if m not in months:
                continue
        try:
            dn_date = (date.fromisoformat(d_str) + timedelta(days=lag_days)).isoformat()
        except ValueError:
            continue
        dn_val = downstream.get(dn_date)
        if dn_val is None:
            continue
        pairs_up.append(up_val)
        pairs_dn.append(dn_val)
    return pearson_r(pairs_up, pairs_dn), len(pairs_up)


def compute_all_pairs(
    city_temps: dict[str, dict[str, float]],
    lag_days: int = 1,
    months: set[int] | None = None,
    min_r: float = 0.30,
) -> list[tuple[str, str, float, int]]:
    """Return [(city_a, city_b, r, n)] sorted by r descending."""
    results = []
    cities = list(city_temps.keys())
    for a, b in combinations(cities, 2):
        r, n = lag_correlation(city_temps[a], city_temps[b], lag_days, months)
        if r >= min_r:
            results.append((a, b, r, n))
    return sorted(results, key=lambda x: -x[2])


def _cli():
    ap = argparse.ArgumentParser(description="City pairwise temperature lag correlations")
    ap.add_argument("--lag",    type=int, default=1,    help="lag in days (default 1)")
    ap.add_argument("--min-r",  type=float, default=0.35, help="minimum Pearson r to report")
    ap.add_argument("--months", default="",             help="comma-separated months e.g. 6,7,8,9")
    ap.add_argument("--pair",   nargs=2,                help="single pair: city_a city_b")
    ap.add_argument("--top",    type=int, default=40,   help="show top N pairs")
    ap.add_argument("--cities", default="",             help="comma-separated city slugs to include (default=all)")
    args = ap.parse_args()

    months = set(int(m) for m in args.months.split(",") if m.strip().isdigit()) if args.months else None
    month_str = f"months={sorted(months)}" if months else "all months"

    target_cities = [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities else list(STATIONS.keys())

    # Load all temps
    print(f"Loading temps for {len(target_cities)} cities ({month_str}, lag={args.lag}d)...", file=sys.stderr)
    city_temps: dict[str, dict[str, float]] = {}
    for slug in target_cities:
        if slug not in STATIONS:
            continue
        data = load_city_temps(slug)
        if data:
            city_temps[slug] = data

    if args.pair:
        a, b = args.pair
        for lag in range(0, 4):
            r, n = lag_correlation(city_temps.get(a, {}), city_temps.get(b, {}), lag, months)
            print(f"  lag={lag}d  r={r:+.4f}  n={n}  ({a} → {b})")
        for lag in range(0, 4):
            r, n = lag_correlation(city_temps.get(b, {}), city_temps.get(a, {}), lag, months)
            print(f"  lag={lag}d  r={r:+.4f}  n={n}  ({b} → {a})")
        return

    print(f"\n=== Top pairs by lag-{args.lag}d Pearson r ({month_str}) ===", flush=True)
    pairs = compute_all_pairs(city_temps, args.lag, months, args.min_r)
    for a, b, r, n in pairs[:args.top]:
        print(f"  {a:<20} → {b:<20}  r={r:.4f}  n={n}")

    print(f"\nTotal pairs with r>={args.min_r}: {len(pairs)}")


if __name__ == "__main__":
    _cli()
