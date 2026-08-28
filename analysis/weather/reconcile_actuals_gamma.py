"""Re-source the skill-matrix learning actuals from Gamma settlement.

ROOT CAUSE (flagged in commit 14505049, 2026-06-04, and project_running_max_oracle_broken):
the self-learning loop (_log_weather_actuals in weather_arb.py) emits one `actual`
per (city, day) using official_running_max_c — the AWC/NWS hourly-METAR max as the
bot accumulated it LOCALLY. That value UNDERSHOOTS the true daily high (incomplete
fetch / obs missed before the post-peak emit time), so the matrix learns "forecast
runs warm" and over-corrects. The only ground truth is Gamma/UMA settlement.

WHAT THIS DOES (post-hoc, read-only by default — does NOT touch the live path):
  1. Read logs/weather/forecast_actuals.jsonl `actual` events.
  2. For each (city, day), pull ALL resolved Gamma daily-high markets and reconstruct
     the settled high in the market's native unit from the cumulative threshold
     ladder (an "X or below" YES + "(X-1) or below" NO pins the rounded high to X;
     an "X or higher" YES raises the floor; an exact "be X" YES fixes it outright).
  3. Convert to °C, compare to the logged official_running_max_c actual, and classify
     CLEAN / UNDERSHOOT / OVERSHOOT. Report the per-city bias the contamination put
     into the learning signal.
  4. With --write, emit logs/weather/forecast_actuals_gamma.jsonl: the SAME schema as
     live_accumulator.log_actual, but wu_high_c = Gamma-settled high, provenance tagged.
     The matrix refit can then consume the clean file instead of the contaminated one.

This is the "re-source actuals from Gamma" TODO. It is reconciliation, not a runtime
change: the live _log_weather_actuals stays (it powers same-day exits); this fixes the
TRAINING signal the nightly matrix merge reads.

Usage:
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.reconcile_actuals_gamma
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.reconcile_actuals_gamma --write
    PYTHONPATH=/root/Klaus python3 -m analysis.weather.reconcile_actuals_gamma --days 2026-05-22 2026-06-04
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from analytics.backfill_weather_resolution import fetch_weather_events, parse_weather_question

LOGS = Path(__file__).parent.parent.parent / "logs" / "weather"
ACTUALS_FILE = LOGS / "forecast_actuals.jsonl"
OUT_FILE = LOGS / "forecast_actuals_gamma.jsonl"

# Gamma question city -> our slug, where they differ.
CITY_ALIAS = {"new-york-city": "nyc"}
# HKO oracle mismatch — never trust Hong Kong settlement for learning (CLAUDE.md).
BLOCK = {"hong-kong"}

CLEAN_TOL_C = 0.6      # |gamma - logged| within this = consistent (sub-bucket rounding)


def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def _yes(entry: dict):
    """1 / 0 / None for the YES outcome of a closed, unambiguous market."""
    if not entry.get("closed"):
        return None
    op = entry.get("outcomePrices") or []
    try:
        y = float(op[0])
    except (IndexError, ValueError, TypeError):
        return None
    if y >= 0.99:
        return 1
    if y <= 0.01:
        return 0
    return None


def settled_high_native(markets: list[dict]) -> tuple[float | None, str, float, float]:
    """Reconstruct the resolved daily high in NATIVE unit from the threshold ladder.

    Returns (high_native | None, method, L, U). The high is AUTHORITATIVE only when
    the ladder pins it to a tight interval (exact / pinned, method != "bound").
    Otherwise [L, U] is just the bound the YES/NO pattern implies — often one-sided
    because the winning bucket is the open-ended "X or higher" at the top of the
    ladder, which constrains the high but does NOT reveal it. In that case the caller
    must bound-CHECK the logged value, not replace it.
    """
    L, U = -math.inf, math.inf
    exact_val = None
    for m in markets:
        y = _yes(m)
        if y is None:
            continue
        p = parse_weather_question(m["question"])
        bt = p.get("weather_bucket_type")
        lo, hi = p.get("weather_threshold_lo"), p.get("weather_threshold_hi")
        if bt == "exact":
            if y == 1:
                exact_val = lo
            elif lo is not None:                 # "be X" NO -> high != X (weak; ignore)
                pass
        elif bt == "above":                      # "X or higher"
            if y == 1 and lo is not None:
                L = max(L, lo)
            elif y == 0 and lo is not None:
                U = min(U, lo - 1)               # high < X  ->  <= X-1 (whole degree)
        elif bt == "below":                      # "X or below"
            if y == 1 and hi is not None:
                U = min(U, hi)
            elif y == 0 and hi is not None:
                L = max(L, hi + 1)
        elif bt == "range" and y == 1:
            if lo is not None:
                L = max(L, lo)
            if hi is not None:
                U = min(U, hi)

    if exact_val is not None:
        return float(exact_val), "exact", exact_val, exact_val
    if math.isfinite(L) and math.isfinite(U) and U >= L and (U - L) <= 1.0:
        return (L + U) / 2.0, "pinned", L, U
    # not pinned -> bound only (possibly one-sided / wide). value is None.
    return None, "bound", L, U


def load_actuals() -> list[dict]:
    out = []
    if not ACTUALS_FILE.exists():
        return out
    for line in ACTUALS_FILE.open():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") == "actual":
            out.append(r)
    return out


def _build_ladders(dmin: str, dmax: str):
    """(slug, day) -> list of resolved HIGHEST-temperature markets over [dmin, dmax]."""
    from datetime import date, timedelta
    dmax_plus = (date.fromisoformat(dmax) + timedelta(days=1)).isoformat()
    _tok, cond = fetch_weather_events(dmin, dmax_plus)
    ladder: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in cond.values():
        q = (e.get("question") or "").lower()
        if "highest temperature" not in q:
            continue
        p = parse_weather_question(e.get("question", ""))
        city, d = p.get("weather_city"), p.get("weather_date")
        if not city or not d:
            continue
        slug = CITY_ALIAS.get(city, city)
        ladder[(slug, d)].append(e)
    return ladder


def backfill(dmin: str, dmax: str, write: bool) -> None:
    """Emit authoritative Gamma-settled actuals for every resolved (city, day),
    bypassing the broken live loop. Only EXACT/PINNED highs are emitted — open-ended
    winners (e.g. '35°C or higher' YES) reveal only a bound, not a usable scalar high,
    so they are reported but not written (would bias the corpus)."""
    print(f"backfilling Gamma-settled highest-temp actuals {dmin}..{dmax}...")
    ladder = _build_ladders(dmin, dmax)
    recon, skipped_open, by_city = [], 0, defaultdict(int)
    for (slug, day), mk in ladder.items():
        if slug in BLOCK:
            continue
        unit = next((parse_weather_question(m["question"]).get("weather_unit")
                     for m in mk if parse_weather_question(m["question"]).get("weather_unit")), None)
        high_n, method, L, U = settled_high_native(mk)
        if unit is None or method not in ("exact", "pinned"):
            skipped_open += 1
            continue
        gamma_c = (f_to_c(high_n) if unit == "F" else high_n)
        by_city[slug] += 1
        recon.append({
            "event": "actual", "slug": slug, "city_slug": slug, "valid_day": day,
            "month": int(day[5:7]), "wu_high_c": round(gamma_c, 3),
            "provenance": "gamma_backfill", "method": method, "ts_utc": None,
        })
    print(f"authoritative city-days: {len(recon)} across {len(by_city)} cities "
          f"(skipped open-ended/unresolved: {skipped_open})")
    print("per-city corpus depth:", dict(sorted(by_city.items(), key=lambda kv: -kv[1])))
    if write:
        # append to the reconciled file, de-duping by (slug, day) — backfill fills
        # history; the per-actual reconcile fills recent days the loop logged.
        existing = {}
        if OUT_FILE.exists():
            for line in OUT_FILE.open():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                existing[(r["slug"], r["valid_day"])] = r
        for rec in recon:
            existing[(rec["slug"], rec["valid_day"])] = rec
        with OUT_FILE.open("w") as f:
            for rec in sorted(existing.values(), key=lambda r: (r["valid_day"], r["slug"])):
                f.write(json.dumps(rec) + "\n")
        print(f"\nwrote {len(existing)} total Gamma actuals -> {OUT_FILE}")
    else:
        print("\n(dry-run — add --write to emit the corpus)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs=2, metavar=("MIN", "MAX"),
                    help="date range (default: span of logged actuals)")
    ap.add_argument("--write", action="store_true",
                    help="emit forecast_actuals_gamma.jsonl with Gamma-settled highs")
    ap.add_argument("--backfill", nargs=2, metavar=("MIN", "MAX"),
                    help="enumerate ALL Gamma-resolved highest-temp city-days in the "
                         "range and emit authoritative actuals — independent of the "
                         "(broken) live loop. Builds the clean training corpus.")
    args = ap.parse_args()

    if args.backfill:
        return backfill(args.backfill[0], args.backfill[1], write=args.write)

    actuals = load_actuals()
    if not actuals:
        print("no logged actuals — nothing to reconcile")
        return
    days = sorted({a["valid_day"] for a in actuals})
    dmin, dmax = (args.days if args.days else (days[0], days[-1]))
    print(f"logged actuals: {len(actuals)} events over {days[0]}..{days[-1]} "
          f"({len(set((a['city_slug'], a['valid_day']) for a in actuals))} city-days)")
    print(f"fetching Gamma resolutions {dmin}..{dmax} (day-by-day, may take a minute)...")

    # markets are end-dated the resolution day; query [dmin, dmax+1] to be safe.
    from datetime import date, timedelta
    dmax_plus = (date.fromisoformat(dmax) + timedelta(days=1)).isoformat()
    _tok, cond = fetch_weather_events(dmin, dmax_plus)

    # bucket all resolved markets by (slug, day) — HIGHEST-temperature markets ONLY.
    # The same event carries "lowest temperature" buckets whose YES would otherwise
    # be read as a false ceiling on the high (the NYC 66-67°F low vs 86-87°F high bug).
    ladder: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in cond.values():
        q = (e.get("question") or "").lower()
        if "highest temperature" not in q:
            continue
        p = parse_weather_question(e.get("question", ""))
        city, d = p.get("weather_city"), p.get("weather_date")
        if not city or not d:
            continue
        slug = CITY_ALIAS.get(city, city)
        ladder[(slug, d)].append(e)

    rows, recon = [], []
    miss = 0
    for a in actuals:
        key = (a["city_slug"], a["valid_day"])
        logged = a.get("wu_high_c")
        if a["city_slug"] in BLOCK:
            continue
        mk = ladder.get(key)
        if not mk:
            miss += 1
            continue
        # need the native unit — take it from any parsed market
        unit = next((parse_weather_question(m["question"]).get("weather_unit")
                     for m in mk if parse_weather_question(m["question"]).get("weather_unit")), None)
        high_n, method, L, U = settled_high_native(mk)
        if unit is None or logged is None:
            miss += 1
            continue
        to_c = (f_to_c if unit == "F" else (lambda v: v))
        Lc = to_c(L) if math.isfinite(L) else -math.inf
        Uc = to_c(U) if math.isfinite(U) else math.inf

        if method in ("exact", "pinned"):
            # authoritative: the ladder reveals the high. Gamma replaces logged.
            corrected = to_c(high_n)
            delta = corrected - logged
            cls = ("CLEAN" if abs(delta) <= CLEAN_TOL_C else
                   "UNDERSHOOT" if delta > 0 else "OVERSHOOT")
            authoritative = True
        else:
            # bound only — CHECK logged against [Lc, Uc]; keep it if consistent.
            if Lc - CLEAN_TOL_C <= logged <= Uc + CLEAN_TOL_C:
                corrected, cls, delta = logged, "CLEAN", 0.0
            elif logged < Lc:                    # logged violates floor -> undershoot
                corrected, cls, delta = Lc, "UNDERSHOOT", Lc - logged
            else:                                # logged above ceiling -> overshoot
                corrected, cls, delta = Uc, "OVERSHOOT", Uc - logged
            authoritative = False

        rows.append({"city": a["city_slug"], "day": a["valid_day"], "unit": unit,
                     "logged_c": logged, "gamma_c": round(corrected, 2),
                     "delta_c": round(delta, 2), "method": method, "cls": cls,
                     "auth": authoritative})
        recon.append({
            "event": "actual", "slug": a["city_slug"], "city_slug": a["city_slug"],
            "valid_day": a["valid_day"], "month": int(a["valid_day"][5:7]),
            "wu_high_c": round(corrected, 3),
            "provenance": "gamma_reconciled" if authoritative else "gamma_bound_checked",
            "method": method, "official_running_max_c": logged, "ts_utc": a.get("ts_utc"),
        })

    # ---- report ----
    by_cls = defaultdict(int)
    by_city = defaultdict(lambda: [0, 0.0])    # city -> [n, sum_abs_delta]
    for r in rows:
        by_cls[r["cls"]] += 1
        if r["delta_c"] is not None:
            by_city[r["city"]][0] += 1
            by_city[r["city"]][1] += r["delta_c"]   # signed -> net learning bias

    print(f"\nreconciled {len(rows)} city-days "
          f"(no Gamma match / unresolved: {miss})")
    print("class breakdown:", dict(by_cls))
    print("\nworst contamination (mean signed gamma-logged, +ve = logged UNDERSHOOT):")
    print(f"  {'city':14} {'n':>3} {'mean_delta_c':>12} {'effect on learning'}")
    for city, (n, s) in sorted(by_city.items(), key=lambda kv: -abs(kv[1][1] / max(1, kv[1][0]))):
        mean = s / n
        eff = "matrix learned forecast too WARM" if mean > 0.3 else (
              "matrix learned forecast too COOL" if mean < -0.3 else "~ok")
        print(f"  {city:14} {n:3d} {mean:12.2f}   {eff}")

    bad = [r for r in rows if r["cls"] in ("UNDERSHOOT", "OVERSHOOT")]
    if bad:
        print(f"\nlargest single mismatches:")
        for r in sorted(bad, key=lambda x: -abs(x["delta_c"]))[:15]:
            print(f"  {r['day']} {r['city']:14} logged={r['logged_c']:6.2f}C "
                  f"gamma={r['gamma_c']:6.2f}C  Δ={r['delta_c']:+5.2f}C  [{r['cls']} via {r['method']}]")

    if args.write:
        with OUT_FILE.open("w") as f:
            for rec in recon:
                f.write(json.dumps(rec) + "\n")
        print(f"\nwrote {len(recon)} Gamma-reconciled actuals -> {OUT_FILE}")
        print("next: point the nightly matrix merge at this file before refit "
              "(refresh_skill_matrix --mode live), then re-validate calibration.")
    else:
        print(f"\n(dry-run — re-run with --write to emit {OUT_FILE.name})")


if __name__ == "__main__":
    main()
