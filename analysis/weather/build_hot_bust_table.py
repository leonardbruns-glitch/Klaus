"""
Empirical HOT_BUST_RATE table builder.

For each (city, month, gap_c) computes P(actual_daily_max - gfs_d1_forecast >= gap_c)
from ~3yr of matched GFS D+1 forecasts (Open-Meteo Previous Runs) vs ASOS truth.

Output: strategy/hot_bust_rates.json
  {
    "_meta": {"built": "2026-05-21", "n_days": 1095, "gaps_c": [...]},
    "cities": {
      "shanghai": {
        "5": {"n": 92, "p_bust": {"0.5": 0.47, "1.0": 0.38, "1.5": 0.30, ...}}
      }
    }
  }

Daily cron mode (--mode append):
  - Fetches yesterday's GFS D+1 + ASOS actual for all cities
  - Appends one row per city to logs/weather/hot_bust_observations.jsonl
  - Rebuilds hot_bust_rates.json if >=7 new rows were appended

Lookup API (used by weather_arb.py):
  from analysis.weather.build_hot_bust_table import HotBustRates
  p = HotBustRates().query("shanghai", month=5, gap_c=1.5)  # float or 0.0

Usage:
    python3 -m analysis.weather.build_hot_bust_table [--days 1095] [--dry-run]
    python3 -m analysis.weather.build_hot_bust_table --mode append [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from analysis.weather.stations import STATIONS
from analysis.weather.backtest_6mo import (
    fetch_d1_forecasts,
    fetch_asos_daily_max,
    _http_get_text_retry,
)

logger = logging.getLogger(__name__)

HOT_BUST_RATES_PATH = Path(__file__).parent.parent.parent / "strategy" / "hot_bust_rates.json"
OBS_LOG_PATH        = Path(__file__).parent.parent.parent / "logs" / "weather" / "hot_bust_observations.jsonl"
CACHE_DIR           = Path(__file__).parent.parent.parent / "logs" / "backtest_cache"

# GFS model name in Open-Meteo Previous Runs API
GFS_MODEL = "gfs_seamless"

# Gaps (°C) at which P(bust >= gap) is tabulated.
# Negative gaps: P(actual >= gfs - |gap|) — useful when GFS already exceeds running_max.
BUST_GAPS_C = [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]

# Minimum number of matched observations per (city, month) to report a cell.
MIN_N_PER_MONTH = 8

# HOT_BUST_MIN_PROB: cities/months with P(bust >= 1.5°C) >= this threshold fire Trigger C.
# 0.10 is the discovery threshold (wider universe). Live-tested cities were ~0.20+.
HOT_BUST_MIN_PROB = 0.10


class HotBustRates:
    """
    Singleton loader for strategy/hot_bust_rates.json.

    query(slug, month, gap_c) → float [0, 1]
        P(actual_daily_max - gfs_d1 >= gap_c) for this (city, month).
        Returns 0.0 if no data (safe default: no Trigger C for unknown cities).

    interpolate(slug, month, gap_c) → float
        Linear interpolation between tabulated gaps (more accurate for runtime gaps
        that fall between table breakpoints).
    """

    _instance: Optional["HotBustRates"] = None
    _loaded: bool = False

    def __new__(cls) -> "HotBustRates":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not self._loaded:
            self._data: dict = {}
            self._meta: dict = {}
            self._mtime: float = 0.0
            self._load()
            HotBustRates._loaded = True

    def _load(self) -> None:
        if not HOT_BUST_RATES_PATH.exists():
            logger.warning("[HBR] hot_bust_rates.json not found — Trigger C disabled. "
                           "Run: python3 -m analysis.weather.build_hot_bust_table")
            return
        try:
            mtime = HOT_BUST_RATES_PATH.stat().st_mtime
            if mtime == self._mtime:
                return
            raw = json.loads(HOT_BUST_RATES_PATH.read_text())
            self._meta = raw.get("_meta", {})
            self._data = raw.get("cities", {})
            self._mtime = mtime
            logger.info("[HBR] loaded %d cities, built %s",
                        len(self._data), self._meta.get("built", "?"))
        except Exception as e:
            logger.error("[HBR] failed to load: %s", e)

    def reload(self) -> None:
        self._load()

    def _cell(self, slug: str, month: int) -> Optional[dict]:
        self._load()
        return self._data.get(slug, {}).get(str(month))

    def query(self, slug: str, month: int, gap_c: float = 1.5) -> float:
        """
        Returns P(actual - gfs_d1 >= gap_c).
        Uses nearest-table-breakpoint (no interpolation). 0.0 if no data.
        """
        cell = self._cell(slug, month)
        if cell is None or cell.get("n", 0) < MIN_N_PER_MONTH:
            return 0.0
        p_bust = cell.get("p_bust", {})
        # Find nearest gap
        gaps = sorted(float(k) for k in p_bust)
        if not gaps:
            return 0.0
        nearest = min(gaps, key=lambda g: abs(g - gap_c))
        return p_bust.get(str(nearest), p_bust.get(f"{nearest:.1f}", 0.0))

    def interpolate(self, slug: str, month: int, gap_c: float = 1.5) -> float:
        """
        Linear interpolation between the two bracketing gap values in the table.
        Returns 0.0 if no data or gap_c is beyond all tabulated breakpoints.
        """
        cell = self._cell(slug, month)
        if cell is None or cell.get("n", 0) < MIN_N_PER_MONTH:
            return 0.0
        p_bust = cell.get("p_bust", {})
        pairs = sorted((float(k), v) for k, v in p_bust.items())
        if not pairs:
            return 0.0
        if gap_c <= pairs[0][0]:
            return pairs[0][1]
        if gap_c >= pairs[-1][0]:
            return pairs[-1][1]
        for i in range(len(pairs) - 1):
            g0, p0 = pairs[i]
            g1, p1 = pairs[i + 1]
            if g0 <= gap_c <= g1:
                t = (gap_c - g0) / (g1 - g0)
                return round(p0 + t * (p1 - p0), 4)
        return 0.0

    def coverage_report(self) -> str:
        lines = [f"HOT_BUST_RATE coverage ({self._meta.get('built', '?')}):"]
        for slug in sorted(self._data):
            months = sorted(int(m) for m in self._data[slug])
            cells  = [self._data[slug][str(m)] for m in months]
            p15    = [f"M{m}={c.get('p_bust', {}).get('1.5', 0):.2f}(n={c.get('n',0)})"
                      for m, c in zip(months, cells)]
            lines.append(f"  {slug}: " + ", ".join(p15))
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# Builder logic
# ════════════════════════════════════════════════════════════════════════════

def _compute_bust_rates(errors_by_month: dict[int, list[float]]) -> dict[str, dict]:
    """
    From {month: [error_c, ...]} where error = actual - gfs_d1:
    Returns {month_str: {"n": n, "p_bust": {gap_str: float}}}
    """
    result = {}
    for month, errs in errors_by_month.items():
        n = len(errs)
        if n < MIN_N_PER_MONTH:
            continue
        p_bust = {}
        for gap in BUST_GAPS_C:
            count = sum(1 for e in errs if e >= gap)
            p_bust[f"{gap:.1f}"] = round(count / n, 4)
        result[str(month)] = {"n": n, "p_bust": p_bust}
    return result


def _build_for_city(slug: str, start: date, end: date) -> dict[str, dict]:
    """
    Fetch GFS D+1 + ASOS daily max for one city over [start, end].
    Returns {month_str: {"n": ..., "p_bust": {gap_str: float}}}
    """
    station = STATIONS[slug]
    cache_key = f"hbr_{slug}_{start}_{end}"

    print(f"  {slug.upper()} ({station.icao})", file=sys.stderr, end="", flush=True)
    d1 = fetch_d1_forecasts(
        station.lat, station.lon, (GFS_MODEL,),
        start.isoformat(), end.isoformat(),
        cache_key=cache_key,
    )
    asos = fetch_asos_daily_max(
        station.icao, start.isoformat(), end.isoformat(),
        cache_key=cache_key,
    )

    if not d1 or not asos:
        print(f" — no data", file=sys.stderr)
        return {}

    errors_by_month: dict[int, list[float]] = defaultdict(list)
    n_matched = 0
    for day, models in d1.items():
        gfs_fc = models.get(GFS_MODEL)
        actual = asos.get(day)
        if gfs_fc is None or actual is None:
            continue
        month = int(day[5:7])
        errors_by_month[month].append(actual - gfs_fc)
        n_matched += 1

    print(f" n={n_matched}", file=sys.stderr)
    return _compute_bust_rates(errors_by_month)


def build_table(days: int = 1095, dry_run: bool = False) -> dict:
    """Full rebuild from scratch over `days` days of history."""
    end   = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    print(f"Building HOT_BUST_RATE table: {start} → {end} ({days} days)", file=sys.stderr)
    print(f"Cities: {len(STATIONS)}", file=sys.stderr)

    cities: dict[str, dict] = {}
    for slug in STATIONS:
        cell = _build_for_city(slug, start, end)
        if cell:
            cities[slug] = cell

    matrix = {
        "_meta": {
            "built": date.today().isoformat(),
            "start": start.isoformat(),
            "end":   end.isoformat(),
            "days":  days,
            "n_cities": len(cities),
            "gaps_c": BUST_GAPS_C,
            "model":  GFS_MODEL,
            "note":   "P(actual_daily_max - gfs_d1 >= gap_c) per (city, month)",
        },
        "cities": cities,
    }

    if dry_run:
        print("\n[dry-run] not writing hot_bust_rates.json", file=sys.stderr)
    else:
        HOT_BUST_RATES_PATH.write_text(json.dumps(matrix, indent=2))
        print(f"\n→ {HOT_BUST_RATES_PATH} written ({len(cities)} cities)", file=sys.stderr)

    _print_summary(matrix)
    return matrix


def _print_summary(matrix: dict) -> None:
    """Print cities with P(bust>=1.5) > HOT_BUST_MIN_PROB for each month."""
    cities = matrix.get("cities", {})
    header = f"\n{'City':<20} {'Month':<6} {'n':>5}  " + "  ".join(f"p{g:+.1f}" for g in BUST_GAPS_C)
    print(header, file=sys.stderr)
    print("-" * len(header), file=sys.stderr)
    rows = []
    for slug, months in cities.items():
        for m_str, cell in months.items():
            p15 = cell.get("p_bust", {}).get("1.5", 0.0)
            if p15 >= HOT_BUST_MIN_PROB:
                p_vals = "  ".join(f"{cell['p_bust'].get(f'{g:.1f}', 0):5.2f}" for g in BUST_GAPS_C)
                rows.append((p15, slug, int(m_str), cell["n"], p_vals))
    rows.sort(reverse=True)
    for p15, slug, m, n, p_vals in rows[:40]:
        print(f"  {slug:<20} M{m:<4d}  {n:>5}  {p_vals}", file=sys.stderr)


# ════════════════════════════════════════════════════════════════════════════
# Daily append mode (cron)
# ════════════════════════════════════════════════════════════════════════════

def _load_existing_table() -> dict:
    if HOT_BUST_RATES_PATH.exists():
        return json.loads(HOT_BUST_RATES_PATH.read_text())
    return {"_meta": {}, "cities": {}}


def append_yesterday(dry_run: bool = False) -> int:
    """
    Fetch yesterday's GFS D+1 vs ASOS for all cities.
    Append new rows to hot_bust_observations.jsonl.
    Returns number of rows appended.
    """
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    OBS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing observation dates to avoid duplicates
    existing: set[str] = set()
    if OBS_LOG_PATH.exists():
        for line in OBS_LOG_PATH.read_text().splitlines():
            try:
                row = json.loads(line)
                existing.add(f"{row['city']}|{row['date']}")
            except Exception:
                pass

    new_rows = []
    for slug, station in STATIONS.items():
        key = f"{slug}|{yesterday}"
        if key in existing:
            continue
        cache_key = f"hbr_{slug}_{yesterday}_{yesterday}"
        d1 = fetch_d1_forecasts(
            station.lat, station.lon, (GFS_MODEL,),
            yesterday, yesterday,
            cache_key=cache_key,
        )
        asos = fetch_asos_daily_max(
            station.icao, yesterday, yesterday,
            cache_key=cache_key,
        )
        gfs_fc = (d1.get(yesterday) or {}).get(GFS_MODEL)
        actual = asos.get(yesterday)
        if gfs_fc is None or actual is None:
            print(f"  SKIP {slug}: missing data gfs={gfs_fc} actual={actual}", file=sys.stderr)
            continue
        row = {
            "date":     yesterday,
            "city":     slug,
            "month":    int(yesterday[5:7]),
            "gfs_d1":   round(float(gfs_fc), 2),
            "actual":   round(float(actual), 2),
            "error":    round(float(actual) - float(gfs_fc), 2),
        }
        new_rows.append(row)
        print(f"  {slug}: gfs={gfs_fc:.1f}°C actual={actual:.1f}°C "
              f"error={row['error']:+.1f}°C", file=sys.stderr)

    if not dry_run and new_rows:
        with OBS_LOG_PATH.open("a") as f:
            for row in new_rows:
                f.write(json.dumps(row) + "\n")
        print(f"\nAppended {len(new_rows)} rows to {OBS_LOG_PATH}", file=sys.stderr)
    elif dry_run:
        print(f"\n[dry-run] would append {len(new_rows)} rows", file=sys.stderr)

    return len(new_rows)


def rebuild_from_observations(dry_run: bool = False) -> dict:
    """
    Build hot_bust_rates.json from the accumulated hot_bust_observations.jsonl.
    Richer than `build_table` because it also includes the daily live observations.
    Falls back to build_table if log has < MIN_N_PER_MONTH × 2 rows.
    """
    if not OBS_LOG_PATH.exists():
        print("[HBR] no observations log — running full build", file=sys.stderr)
        return build_table(dry_run=dry_run)

    errors_by_city_month: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    with OBS_LOG_PATH.open() as f:
        for line in f:
            try:
                row = json.loads(line)
                errors_by_city_month[row["city"]][row["month"]].append(row["error"])
            except Exception:
                pass

    cities: dict[str, dict] = {}
    for slug, by_month in errors_by_city_month.items():
        cell = _compute_bust_rates(by_month)
        if cell:
            cities[slug] = cell

    matrix = {
        "_meta": {
            "built":   date.today().isoformat(),
            "source":  str(OBS_LOG_PATH.name),
            "n_cities": len(cities),
            "gaps_c":  BUST_GAPS_C,
            "model":   GFS_MODEL,
        },
        "cities": cities,
    }

    if not dry_run:
        HOT_BUST_RATES_PATH.write_text(json.dumps(matrix, indent=2))
        print(f"→ {HOT_BUST_RATES_PATH} rebuilt from observations ({len(cities)} cities)", file=sys.stderr)
    else:
        print("[dry-run] not writing", file=sys.stderr)

    return matrix


# ════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ════════════════════════════════════════════════════════════════════════════

def _cli():
    ap = argparse.ArgumentParser(description="Build empirical HOT_BUST_RATE table for weather_arb")
    ap.add_argument("--mode",   choices=["build", "append"], default="build",
                    help="build=full rebuild from API; append=daily cron (yesterday only)")
    ap.add_argument("--days",   type=int, default=1095,
                    help="history window for --mode build (default 3yr=1095)")
    ap.add_argument("--cities", default="",
                    help="comma-sep slugs (default: all STATIONS)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.mode == "append":
        n = append_yesterday(dry_run=args.dry_run)
        if n >= 7:
            print(f"\n{n} new rows — rebuilding table from observations...", file=sys.stderr)
            rebuild_from_observations(dry_run=args.dry_run)
        else:
            print(f"\n{n} new rows — table not rebuilt (threshold=7)", file=sys.stderr)

    else:  # build
        if args.cities:
            slugs = [s.strip() for s in args.cities.split(",") if s.strip()]
            # Temporarily restrict STATIONS for the build loop
            import analysis.weather.stations as _st
            orig = dict(_st.STATIONS)
            _st.STATIONS = {k: v for k, v in orig.items() if k in slugs}
        build_table(days=args.days, dry_run=args.dry_run)
        if args.cities:
            _st.STATIONS = orig


if __name__ == "__main__":
    _cli()
