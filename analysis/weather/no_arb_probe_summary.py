#!/usr/bin/env python3
"""Summarize the NO-arb real-book SHADOW probe (logs/shadow/hot/<date>/no_arb_probe.jsonl).

The probe (weather_arb._no_arb_shadow_probe) fetches REAL CLOB books for the top
NO-arb-eligible cities each interval and records real Σno_ask + per-leg fillable
depth. This answers the only question that matters: does a *fillable* neg-risk
NO-arb (every leg quoted with depth, real Σno_ask < N−1 beyond the spread) ever
actually open — or is the engine's "eligibility" just the Gamma-proxy overround?

Usage:
    python3 analysis/weather/no_arb_probe_summary.py [YYYY-MM-DD] [--min-depth 5]

Only baskets with all_legs_fillable=True can be realized as a taker; the headline
verdict is driven by those. Test artifacts (cityA/cityB) are dropped.
"""
import json, sys, glob, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

TEST_SLUGS = {"cityA", "cityB"}
EDGE_REAL_THR = 0.01  # 1% — a basket must clear this to be worth 11-leg execution risk


def _load(date_str):
    base = Path(__file__).resolve().parents[2] / "logs" / "shadow" / "hot"
    if date_str:
        paths = [base / date_str / "no_arb_probe.jsonl"]
    else:
        paths = sorted(base.glob("*/no_arb_probe.jsonl"))
    rows = []
    for p in paths:
        if not Path(p).exists():
            continue
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("city") in TEST_SLUGS:
                continue
            rows.append(r)
    return rows, paths


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    date_str = args[0] if args else datetime.now(timezone.utc).date().isoformat()
    rows, paths = _load(date_str)
    if not rows:
        print(f"no probe rows for {date_str} (looked in {[str(p) for p in paths]})")
        return

    cycles = sorted({r["ts"] for r in rows})
    fillable = [r for r in rows if r.get("all_legs_fillable")]
    real_arbs = [r for r in fillable if r.get("real_arb")]
    tradeable = [r for r in real_arbs if (r.get("real_edge") or -9) >= EDGE_REAL_THR]

    span_h = (cycles[-1] - cycles[0]) / 3600.0 if len(cycles) > 1 else 0.0
    print(f"=== NO-arb real-book probe — {date_str} ===")
    print(f"cycles={len(cycles)} span={span_h:.1f}h  city-samples={len(rows)}")
    print(f"all-legs-fillable baskets:      {len(fillable):>4} / {len(rows)}  ({100*len(fillable)/len(rows):.0f}%)")
    print(f"  of those, REAL_ARB (Σno<N-1): {len(real_arbs):>4}")
    print(f"  of those, edge >= {EDGE_REAL_THR:.0%}:        {len(tradeable):>4}  <-- the only economically real ones")

    if fillable:
        edges = sorted((r["real_edge"] for r in fillable if r.get("real_edge") is not None))
        print(f"\nreal_edge over FILLABLE baskets: min={edges[0]:+.4f} med={statistics.median(edges):+.4f} max={edges[-1]:+.4f}")
        # proxy vs real bias: how much the Gamma proxy understates real Σno
        bias = [r["real_sum_no"] - r["proxy_sum_no"] for r in rows
                if r.get("real_sum_no") and r.get("proxy_sum_no")]
        if bias:
            print(f"proxy understatement (realΣno - proxyΣno): med={statistics.median(bias):+.3f} "
                  f"(positive ⇒ proxy fabricates edge by understating real NO cost)")

    # per-city: best fillable edge + fillability rate
    by_city = defaultdict(list)
    for r in rows:
        by_city[r["city"]].append(r)
    print(f"\n{'city':<14} {'n':>3} {'fillable%':>9} {'bestEdge*':>9} {'maxRealArb':>10}")
    for city in sorted(by_city):
        rs = by_city[city]
        fr = [r for r in rs if r.get("all_legs_fillable")]
        best = max((r["real_edge"] for r in fr if r.get("real_edge") is not None), default=None)
        anyarb = any(r.get("real_arb") for r in fr)
        print(f"{city:<14} {len(rs):>3} {100*len(fr)/len(rs):>8.0f}% "
              f"{(f'{best:+.4f}' if best is not None else '   n/a'):>9} {str(anyarb):>10}")
    print("\n* bestEdge = best real_edge among all-legs-fillable snapshots (only those are realizable as a taker).")
    if not tradeable:
        print(f"\nVERDICT: no fillable NO-arb above {EDGE_REAL_THR:.0%} observed — engine 'eligibility' is the proxy overround, not a real edge.")
    else:
        print(f"\nVERDICT: {len(tradeable)} fillable basket(s) >= {EDGE_REAL_THR:.0%} — inspect; a real (if thin) arb may exist.")


if __name__ == "__main__":
    main()
