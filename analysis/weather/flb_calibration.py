"""FAVORITE-LONGSHOT calibration: REAL CLOB YES price -> realized resolution WR.

Pure price->WR calibration. NO model. For every resolved Polymarket weather
bucket across all discoverable city-days, take its REAL CLOB YES entry price
(price at first_trade + 5min, the reachable pre-convergence ask), bin it, and
measure the realized YES win-rate against Gamma resolution (is_winner).

Per bin:
  n, realized YES win-rate (WR), implied (=mean price), MISPRICE = WR - implied,
  NET EV/contract of BUY-YES and of BUY-NO after fee 0.05*a*(1-a).

  BUY-YES @ a:  win -> (1-a) - fee ; lose -> -a - fee     (won = is_winner)
  BUY-NO  @ a:  enter at no_px = 1-a (cross to NO).
                win(no) when NOT is_winner -> (1-no_px) - fee_no = a - fee_no
                lose(no) when is_winner    -> -no_px - fee_no = -(1-a) - fee_no
                fee_no = 0.05 * no_px * (1-no_px) = 0.05 * a * (1-a)  (symmetric)

Repeatability: split-half by day-parity and by city; report misprice sign hold.
Capacity: fillable depth at +EV bands from the real CLOB books (n history pts as
a coarse liquidity proxy; deep book pull is a separate live snapshot).

    PYTHONPATH=/root/Klaus python3 analysis/weather/flb_calibration.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

from analysis.weather.backtest import discover_resolved, attach_entry_prices
from analysis.weather.stations import STATIONS

DAYS_BACK = 10
# Task-specified bands
BANDS = [
    (0.02, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.40),
    (0.40, 0.60), (0.60, 0.80), (0.80, 0.92), (0.92, 0.98),
]
TAIL_BANDS = [(0.02, 0.05), (0.05, 0.10)]
FAV_BANDS = [(0.80, 0.92), (0.92, 0.98)]


def fee(a: float) -> float:
    """Polymarket weather taker fee = 0.0125*4*p(1-p) = 0.05*p(1-p). Symmetric a<->1-a."""
    return 0.05 * a * (1.0 - a)


def band_of(p: float):
    for lo, hi in BANDS:
        if lo <= p < hi:
            return (lo, hi)
    return None


def yes_ev(a: float, won: bool) -> float:
    f = fee(a)
    return (1.0 - a) - f if won else (-a - f)


def no_ev(a: float, won: bool) -> float:
    """BUY-NO at no_px=1-a. NO wins when YES loses."""
    no_px = 1.0 - a
    f = fee(a)  # symmetric
    won_no = not won
    return (1.0 - no_px) - f if won_no else (-no_px - f)


def collect():
    """Return list of bucket observations: {city, day, price, won, n_hist}."""
    obs = []
    cities = sorted(STATIONS.keys())
    n_markets = 0
    n_clean = 0
    for c in cities:
        try:
            ms = discover_resolved(c, DAYS_BACK)
        except Exception as e:
            print(f"  discover {c}: {str(e)[:50]}", file=sys.stderr)
            continue
        if not ms:
            continue
        try:
            attach_entry_prices(ms)
        except Exception as e:
            print(f"  prices {c}: {str(e)[:50]}", file=sys.stderr)
            continue
        for m in ms:
            n_markets += 1
            winners = [b for b in m.buckets if b.is_winner]
            if len(winners) != 1:
                continue  # require exactly one real resolution
            n_clean += 1
            for b in m.buckets:
                a = b.entry_price
                if a is None or a <= 0.0 or a >= 1.0:
                    continue
                obs.append({
                    "city": c, "day": m.valid_day.isoformat(),
                    "price": float(a), "won": bool(b.is_winner),
                    "n_hist": int(getattr(b, "n_history_points", 0) or 0),
                    "label": b.label,
                })
        print(f"  {c}: {len(ms)} mkts", file=sys.stderr)
    print(f"markets={n_markets} clean-resolution={n_clean} bucket-obs={len(obs)}", file=sys.stderr)
    return obs


def band_stats(obs):
    by = defaultdict(list)
    for o in obs:
        b = band_of(o["price"])
        if b is None:
            continue
        by[b].append(o)
    rows = []
    for band in BANDS:
        rs = by.get(band, [])
        n = len(rs)
        if n == 0:
            rows.append({"band": band, "n": 0})
            continue
        wr = np.mean([r["won"] for r in rs])
        implied = np.mean([r["price"] for r in rs])
        misprice = wr - implied
        buy_yes_ev = np.mean([yes_ev(r["price"], r["won"]) for r in rs])
        buy_no_ev = np.mean([no_ev(r["price"], r["won"]) for r in rs])
        rows.append({
            "band": band, "n": n, "wr": float(wr), "implied": float(implied),
            "misprice": float(misprice), "buy_yes_ev": float(buy_yes_ev),
            "buy_no_ev": float(buy_no_ev),
            "obs": rs,
        })
    return rows, by


def split_half_sign(rs, key_fn):
    """Return (groupA_misprice, groupB_misprice, nA, nB) by a binary key."""
    A = [r for r in rs if key_fn(r)]
    B = [r for r in rs if not key_fn(r)]
    def mp(g):
        if not g:
            return None
        return float(np.mean([r["won"] for r in g]) - np.mean([r["price"] for r in g]))
    return mp(A), mp(B), len(A), len(B)


def main():
    obs = collect()
    rows, by = band_stats(obs)

    print("\n================= PRICE -> REALIZED-WR CALIBRATION =================")
    print(f"{'band':<14}{'n':<7}{'WR':<9}{'implied':<10}{'misprice':<11}{'BUY-YES EV':<12}{'BUY-NO EV':<11}")
    for r in rows:
        if r["n"] == 0:
            print(f"[{r['band'][0]:.2f},{r['band'][1]:.2f})   {0:<7}--")
            continue
        print(f"[{r['band'][0]:.2f},{r['band'][1]:.2f})   {r['n']:<7}{r['wr']:<9.3f}"
              f"{r['implied']:<10.3f}{r['misprice']:<+11.3f}{r['buy_yes_ev']:<+12.4f}{r['buy_no_ev']:<+11.4f}")

    # Repeatability: split-half by day parity + by city-count
    print("\n================= REPEATABILITY (split-half) =================")
    for r in rows:
        if r.get("n", 0) < 20:
            continue
        rs = r["obs"]
        # by day parity (day-of-month even/odd)
        a_mp, b_mp, na, nb = split_half_sign(rs, lambda o: int(o["day"][-2:]) % 2 == 0)
        cities = sorted({o["city"] for o in rs})
        # by city alphabetical half
        mid = cities[len(cities)//2] if cities else ""
        ca_mp, cb_mp, nca, ncb = split_half_sign(rs, lambda o: o["city"] < mid)
        sign_consistent_day = (a_mp is not None and b_mp is not None and (a_mp > 0) == (b_mp > 0))
        sign_consistent_city = (ca_mp is not None and cb_mp is not None and (ca_mp > 0) == (cb_mp > 0))
        print(f"[{r['band'][0]:.2f},{r['band'][1]:.2f}) n={r['n']} ncities={len(cities)} "
              f"day-split mp=({a_mp:+.3f}/{b_mp:+.3f}) n=({na}/{nb}) consistent={sign_consistent_day} | "
              f"city-split mp=({ca_mp:+.3f}/{cb_mp:+.3f}) consistent={sign_consistent_city}")

    # Concentration check: is the misprice driven by a few city-days?
    print("\n================= CONCENTRATION (per-city misprice in key bands) =================")
    for r in rows:
        if r.get("n", 0) < 20:
            continue
        rs = r["obs"]
        per_city = defaultdict(list)
        for o in rs:
            per_city[o["city"]].append(o)
        cmps = []
        for cty, g in per_city.items():
            if len(g) < 3:
                continue
            cmps.append((cty, len(g), float(np.mean([x["won"] for x in g]) - np.mean([x["price"] for x in g]))))
        cmps.sort(key=lambda x: x[2])
        same_sign = sum(1 for _, _, m in cmps if (m > 0) == (r["misprice"] > 0))
        print(f"[{r['band'][0]:.2f},{r['band'][1]:.2f}) overall mp={r['misprice']:+.3f}  "
              f"cities-with-n>=3={len(cmps)}  same-sign-as-overall={same_sign}/{len(cmps)}")

    # Capacity proxy: history-point depth at +EV bands
    print("\n================= CAPACITY PROXY (history points) =================")
    for r in rows:
        if r.get("n", 0) == 0:
            continue
        rs = r["obs"]
        nh = [x["n_hist"] for x in rs]
        print(f"[{r['band'][0]:.2f},{r['band'][1]:.2f}) n={r['n']} median_hist_pts={int(np.median(nh))} "
              f"mean={np.mean(nh):.0f}")

    # Dump JSON for the structured caller
    out = {"bands": [{k: v for k, v in r.items() if k != "obs"} for r in rows]}
    print("\n@@JSON@@" + json.dumps(out))


if __name__ == "__main__":
    main()
