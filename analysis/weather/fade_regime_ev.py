"""P1 Prong B — does the ACTUAL fade gap + EV partition by synoptic regime?

Prong A (hourly-curvature proxy from the parquet) was weak — but the real fade gap is
SUB-HOURLY and the parquet can't see it. Here we measure the real thing: reuse the
resolution-bias substrate (raw Mesonet METARs incl. the 4-group period-max + Gamma
resolution + CLOB prices) and tag each city-day with the regime AT THE PEAK ob (sky
cover + wind, parsed from the raw METAR), then partition:
  gap = period_max - hourly_max  (the sampling miss the fade harvests), and
  FADE-NO EV on cross days  (the live edge),
by  CLEAR/CALM  vs  CLOUDY/WINDY.

Hypothesis (sampling theory): clear+calm => sharp single peak missed by hourly
sampling => big gap => fat fade; cloudy+windy => flat/advective => small gap => thin
or false fade. If true => gate the live fade on clear+calm.

    PYTHONPATH=/root/Klaus python3 analysis/weather/fade_regime_ev.py --days 45
"""
from __future__ import annotations
import argparse, re, statistics
from datetime import date, timedelta, datetime, timezone
from zoneinfo import ZoneInfo

from analysis.weather.stations import STATIONS
from analysis.weather.resolution_bias_backtest import fetch_metars, _T, _G4, round_bin, cToF

US = ["miami", "dallas", "houston", "austin", "chicago", "atlanta",
      "los-angeles", "nyc", "denver", "seattle", "san-francisco"]


def sky_rank(raw):
    """0 clear (CLR/SKC/FEW), 1 partly (SCT), 2 cloudy (BKN/OVC). None if absent."""
    if re.search(r"\b(CLR|SKC|NSC|NCD)\b", raw):
        return 0
    groups = re.findall(r"\b(FEW|SCT|BKN|OVC)\d{3}", raw)
    if not groups:
        return None
    if any(g in ("BKN", "OVC") for g in groups):
        return 2
    if "SCT" in groups:
        return 1
    return 0  # only FEW


def wind_kt(raw):
    m = re.search(r"\b(\d{3}|VRB)(\d{2})(G\d{2})?KT", raw)
    return int(m.group(2)) if m else None


def day_detail(metars, tz, day):
    """(hourly_max_F, period_max_F, sky_at_peak, wind_at_peak) for local `day`."""
    z = ZoneInfo(tz) if tz else timezone.utc
    lo = datetime(day.year, day.month, day.day, tzinfo=z).astimezone(timezone.utc)
    hi = lo + timedelta(hours=24)
    by_hour = {}          # hour -> (temp_c, raw)
    g4 = []
    for t, raw in metars:
        if lo <= t < hi and (" SLP" in raw) and (_T(raw) is not None):
            by_hour[t.hour] = (_T(raw), raw)
        if hi <= t < hi + timedelta(hours=6):
            v = _G4(raw)
            if v is not None:
                g4.append(v)
    if not by_hour:
        return None
    peak_hour = max(by_hour, key=lambda h: by_hour[h][0])
    hmax_c, praw = by_hour[peak_hour]
    pmax_c = max(g4) if g4 else hmax_c
    return cToF(hmax_c), cToF(pmax_c), sky_rank(praw), wind_kt(praw)


def regime(sky, wind):
    if sky is None or wind is None:
        return None
    calm = wind <= 7
    if sky == 0 and calm:
        return "clear+calm"
    if sky >= 2 or wind >= 12:
        return "cloudy/windy"
    return "mixed"


def run(days):
    from analysis.weather.backtest import discover_resolved, attach_entry_prices
    rows = []
    for slug in US:
        st = STATIONS.get(slug)
        if not st or getattr(st, "unit", "") != "F":
            continue
        try:
            mkts = discover_resolved(slug, days)
        except Exception as e:
            print(f"  discover err {slug}: {str(e)[:50]}"); continue
        if not mkts:
            continue
        try:
            attach_entry_prices(mkts)
        except Exception as e:
            print(f"  prices err {slug}: {str(e)[:50]}")
        ds = sorted({m.valid_day for m in mkts})
        ms = fetch_metars(st.icao, min(ds), max(ds) + timedelta(days=2))
        for m in mkts:
            w = next((b for b in m.buckets if b.is_winner), None)
            if w is None:
                continue
            det = day_detail(ms, getattr(st, "tz", ""), m.valid_day)
            if det is None:
                continue
            h, p, sky, wind = det
            reg = regime(sky, wind)
            hbin, pbin = round_bin(h, "F"), round_bin(p, "F")
            wlo = w.lo_inclusive
            wbin = None if wlo == float("-inf") else int((round(wlo) // 2) * 2)
            # fade-NO EV on this day's period-bin (buy NO at ~1-yes), if cross + closed
            fade_pnl = None
            if hbin != pbin and wbin is not None:
                pp = next((b.entry_price for b in m.buckets
                           if b.lo_inclusive != float("-inf")
                           and int((round(b.lo_inclusive) // 2) * 2) == pbin
                           and b.entry_price is not None), None)
                if pp is not None:
                    no_cost = 1.0 - pp
                    win_is_p = (wbin == pbin)
                    fade_pnl = (1 - no_cost) if (not win_is_p) else (-no_cost)
            rows.append({"city": slug, "gap": p - h, "cross": hbin != pbin,
                         "reg": reg, "sky": sky, "wind": wind, "fade": fade_pnl})
        print(f"  {slug}: {len(mkts)} mkts", flush=True)
    report(rows)


def report(rows):
    n = len(rows)
    tagged = [r for r in rows if r["reg"]]
    print(f"\n=== n={n} resolved city-days; {len(tagged)} regime-tagged ===")
    print(f"overall gap mean={statistics.mean([r['gap'] for r in rows]):+.2f}F  "
          f"cross-rate={100*sum(r['cross'] for r in rows)/n:.0f}%")
    print("\n--- GAP (period-hourly) + CROSS-RATE by regime ---")
    for reg in ["clear+calm", "mixed", "cloudy/windy"]:
        g = [r for r in tagged if r["reg"] == reg]
        if g:
            gaps = [r["gap"] for r in g]
            print(f"  {reg:<13} n={len(g):>4}  gap mean={statistics.mean(gaps):+.2f}F "
                  f"med={statistics.median(gaps):+.2f}F  cross={100*sum(r['cross'] for r in g)/len(g):.0f}%")
    print("\n--- FADE-NO EV by regime (cross days, per $1; the live edge) ---")
    allf = [r["fade"] for r in rows if r["fade"] is not None]
    if allf:
        print(f"  ALL          n={len(allf):>4}  meanEV={statistics.mean(allf):+.3f}  "
              f"WR={100*sum(x>0 for x in allf)/len(allf):.0f}%  total={sum(allf):+.2f}")
    for reg in ["clear+calm", "mixed", "cloudy/windy"]:
        f = [r["fade"] for r in tagged if r["reg"] == reg and r["fade"] is not None]
        if f:
            print(f"  {reg:<13} n={len(f):>4}  meanEV={statistics.mean(f):+.3f}  "
                  f"WR={100*sum(x>0 for x in f)/len(f):.0f}%  total={sum(f):+.2f}")
    print("\n(thesis: clear+calm gap >> cloudy/windy gap, and clear+calm fade EV the fattest)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    run(ap.parse_args().days)
