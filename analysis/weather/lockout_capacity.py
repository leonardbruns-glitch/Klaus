"""
LOCKOUT capacity & edge analysis (ad-hoc, read-only).

Answers the keystone question for the "settlement-lock" strategy proposal:
among PHYSICALLY locked-out buckets (running_max already past bucket ceiling),
what is the REAL distribution of (a) gross edge = 1 - no_ask, (b) fillable NO
depth in USD, (c) safety margin = running_max - bucket_hi (contamination
robustness), and (d) hold time to close?

Dedup: one row per (token_id, end_date) at FIRST lockout observation (min ts_s).
This mirrors the validation gate's "unique (token_id, day) lockout events".

Win logic: a locked-out bucket (running_max > hi, monotonic) resolves NO with
prob ~1 EXCEPT if the running_max we triggered on is not the OFFICIAL hourly-METAR
max (the M1-beta contamination bug). We proxy robustness by safety margin band.

Usage: python3 analysis/weather/lockout_capacity.py
"""
from __future__ import annotations
import glob
import json
import statistics as st
from collections import defaultdict

FILES = sorted(glob.glob("logs/shadow/hot/2026-05-2*/metar_lockout.jsonl"))


def best_no_ask(rec):
    """Lowest NO ask price we could BUY at, preferring the real CLOB book."""
    nb = rec.get("no_book") or {}
    asks = nb.get("asks") or []
    prices = [a["price"] for a in asks if a.get("size", 0) > 0]
    clob = rec.get("no_ask_clob")
    if clob:
        prices.append(clob)
    if prices:
        return min(prices)
    yb = rec.get("yes_bid")
    return (1.0 - yb) if yb is not None else None


def no_depth_usd(rec, max_price):
    """USD fillable on the NO ask side at price <= max_price."""
    nb = rec.get("no_book") or {}
    tot = 0.0
    for a in nb.get("asks") or []:
        if a.get("price", 1.0) <= max_price and a.get("size", 0) > 0:
            tot += a.get("usd", a["price"] * a["size"])
    return tot


def main():
    first = {}  # (token_id, end_date) -> record at min ts_s
    n_raw = 0
    for fp in FILES:
        with open(fp) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("record_type") != "metar_lockout_candidate":
                    continue
                n_raw += 1
                key = (r.get("token_id"), r.get("end_date"))
                cur = first.get(key)
                if cur is None or r.get("ts_s", 1e18) < cur.get("ts_s", 1e18):
                    first[key] = r

    events = list(first.values())
    print(f"raw records:        {n_raw:,}")
    print(f"unique (token,day): {len(events):,}")
    print(f"days covered:       {len({e.get('end_date') for e in events})}")
    print(f"cities:             {len({e.get('city') for e in events})}")
    print()

    # core distributions
    edges, margins, depths_1, depths_2, holds, lag = [], [], [], [], [], []
    for e in events:
        na = best_no_ask(e)
        if na is None:
            continue
        edge = 1.0 - na
        edges.append(edge)
        hi = e.get("bucket_hi_c_padded")
        rm = e.get("running_max_c")
        if hi is not None and rm is not None:
            margins.append(rm - hi)
        depths_1.append(no_depth_usd(e, 0.99))   # edge >= 1%
        depths_2.append(no_depth_usd(e, 0.98))   # edge >= 2%
        s2c = e.get("seconds_to_event_close")
        if s2c is not None:
            holds.append(s2c / 3600.0)
        sfl = e.get("seconds_since_first_lockout")
        if sfl is not None:
            lag.append(sfl)

    def pct(xs, p):
        if not xs:
            return float("nan")
        xs = sorted(xs)
        i = min(len(xs) - 1, int(p / 100 * len(xs)))
        return xs[i]

    def line(name, xs, fmt="{:.3f}"):
        if not xs:
            print(f"{name:22s} (none)")
            return
        print(f"{name:22s} n={len(xs):5d}  "
              f"p10={fmt.format(pct(xs,10))}  p25={fmt.format(pct(xs,25))}  "
              f"med={fmt.format(pct(xs,50))}  p75={fmt.format(pct(xs,75))}  "
              f"p90={fmt.format(pct(xs,90))}  max={fmt.format(max(xs))}")

    print("=== gross edge (1 - no_ask) — what we capture per share ===")
    line("gross_edge", edges)
    print()
    print("=== safety margin (running_max - bucket_hi, deg C) — robustness ===")
    line("safety_margin_C", margins, "{:.2f}")
    print()
    print("=== fillable NO depth (USD) at price<=0.99 (edge>=1%) ===")
    line("depth_usd@1%", depths_1, "{:.1f}")
    print("=== fillable NO depth (USD) at price<=0.98 (edge>=2%) ===")
    line("depth_usd@2%", depths_2, "{:.1f}")
    print()
    print("=== hold time to close (hours) ===")
    line("hold_hours", holds, "{:.2f}")
    print("=== seconds since first lockout at first capture (poll lag) ===")
    line("lag_seconds", lag, "{:.0f}")
    print()

    # The money question: deployable $ and gross profit, by edge band, with a
    # per-event fill cap (can't take infinite size). Cap at depth AND at $25/leg.
    CAP = 25.0
    print("=== DEPLOYABLE CAPITAL & GROSS PROFIT over %d days (cap $%.0f/leg) ===" % (
        len({e.get('end_date') for e in events}), CAP))
    bands = [(0.005, 0.01), (0.01, 0.02), (0.02, 0.05), (0.05, 0.15), (0.15, 1.01)]
    tot_dep = tot_prof = 0.0
    print(f"{'edge band':>14s} {'n':>5s} {'sum_deploy$':>12s} {'gross_profit$':>14s} {'avg_edge':>9s}")
    for lo, hi in bands:
        ndep = nsum = nprof = 0
        sdep = sprof = 0.0
        ed = 0.0
        for e in events:
            na = best_no_ask(e)
            if na is None:
                continue
            edge = 1.0 - na
            if not (lo <= edge < hi):
                continue
            # fillable at <= (1-lo) price, capped
            dep = min(no_depth_usd(e, 1.0 - lo), CAP)
            if dep <= 0:
                continue
            ndep += 1
            sdep += dep
            sprof += dep * edge   # gross (WR~1 assumed for locked-out)
            ed += edge
        avg = ed / ndep if ndep else 0.0
        tot_dep += sdep
        tot_prof += sprof
        print(f"{lo:.3f}-{hi:.3f} {ndep:5d} {sdep:12.1f} {sprof:14.2f} {avg:9.4f}")
    days = len({e.get('end_date') for e in events})
    print(f"{'TOTAL':>14s} {'':>5s} {tot_dep:12.1f} {tot_prof:14.2f}")
    print(f"\nPER-DAY: deploy ~${tot_dep/days:.1f}  gross profit ~${tot_prof/days:.2f}  "
          f"(before fees, slippage, adverse selection)")

    # robustness: how much of the profit comes from thin (<0.5C) margins (the
    # contamination-risk zone)?
    print("\n=== profit by safety-margin band (contamination robustness) ===")
    mbands = [(-99, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 99)]
    print(f"{'margin C':>14s} {'n':>5s} {'gross_profit$':>14s}")
    for lo, hi in mbands:
        nsum = 0
        sprof = 0.0
        for e in events:
            na = best_no_ask(e)
            hb = e.get("bucket_hi_c_padded")
            rm = e.get("running_max_c")
            if na is None or hb is None or rm is None:
                continue
            m = rm - hb
            if not (lo <= m < hi):
                continue
            edge = 1.0 - na
            if edge < 0.005:
                continue
            dep = min(no_depth_usd(e, 0.995), CAP)
            if dep <= 0:
                continue
            nsum += 1
            sprof += dep * edge
        print(f"{lo:>6.1f}-{hi:<6.1f} {nsum:5d} {sprof:14.2f}")


if __name__ == "__main__":
    main()
