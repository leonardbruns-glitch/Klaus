"""Forensic on the favorite bands (0.60-0.98): is the 100% WR a real standing
underpricing edge, or an entry-timing artifact (price already converged toward
$1 by first_trade+5min)? Also probes the 0.20-0.40 +EV mid-band stability.

Dumps, per favorite bucket: city, day, entry_price, won, entry_ts offset from
first trade, and time-from-entry-to-resolution (how late the entry is).
"""
from __future__ import annotations
import sys
from collections import defaultdict
import numpy as np
from analysis.weather.backtest import discover_resolved, attach_entry_prices
from analysis.weather.stations import STATIONS

DAYS_BACK = 10


def fee(a): return 0.05 * a * (1 - a)


def main():
    obs = []
    for c in sorted(STATIONS.keys()):
        try:
            ms = discover_resolved(c, DAYS_BACK)
            attach_entry_prices(ms)
        except Exception:
            continue
        for m in ms:
            if sum(b.is_winner for b in m.buckets) != 1:
                continue
            for b in m.buckets:
                a = b.entry_price
                if a is None or a <= 0 or a >= 1:
                    continue
                hist = getattr(b, "history", []) or []
                first_ts = hist[0]["t"] if hist else None
                last_ts = hist[-1]["t"] if hist else None
                ent_ts = getattr(b, "entry_ts", None)
                # time from entry to resolution (last hist pt), and entry offset from first trade
                off_first = (ent_ts - first_ts) if (ent_ts and first_ts) else None
                to_res = (last_ts - ent_ts) if (last_ts and ent_ts) else None
                # span of full series
                span = (last_ts - first_ts) if (first_ts and last_ts) else None
                obs.append({"city": c, "day": m.valid_day.isoformat(), "price": a,
                            "won": b.is_winner, "off_first": off_first, "to_res": to_res,
                            "span": span, "label": b.label, "n_hist": len(hist)})

    # Favorite + mid bands
    for lo, hi in [(0.20, 0.40), (0.40, 0.60), (0.60, 0.80), (0.80, 0.92), (0.92, 0.98)]:
        rs = [o for o in obs if lo <= o["price"] < hi]
        if not rs:
            print(f"[{lo:.2f},{hi:.2f}) n=0"); continue
        wr = np.mean([r["won"] for r in rs])
        yev = np.mean([(1 - r["price"]) - fee(r["price"]) if r["won"] else -r["price"] - fee(r["price"]) for r in rs])
        # entry lateness: median minutes from entry to resolution
        tr = [r["to_res"]/60 for r in rs if r["to_res"] is not None]
        off = [r["off_first"]/60 for r in rs if r["off_first"] is not None]
        print(f"\n[{lo:.2f},{hi:.2f}) n={len(rs)} WR={wr:.3f} BUY-YES_EV={yev:+.4f} "
              f"cities={len(set(r['city'] for r in rs))}")
        if tr:
            print(f"   min from entry->resolution: median={np.median(tr):.0f} p25={np.percentile(tr,25):.0f} p75={np.percentile(tr,75):.0f}")
        if off:
            print(f"   min from first-trade->entry: median={np.median(off):.1f} (>5 means sparse early book)")
        # per-row dump for the favorites
        if lo >= 0.60:
            for r in sorted(rs, key=lambda x: x["price"]):
                trm = f"{r['to_res']/60:.0f}m" if r["to_res"] is not None else "?"
                print(f"     {r['city']:<14}{r['day']} px={r['price']:.3f} won={int(r['won'])} "
                      f"to_res={trm} n_hist={r['n_hist']} {r['label']}")


if __name__ == "__main__":
    main()
