#!/usr/bin/env python3
"""
model_no_scorecard.py — READ-ONLY. Realized PnL of the favorite-longshot engine
model-NO (STWA_REGULAR_NO_ENABLED). PnL is ALREADY booked by the resolver
(weather_arb._stwa_close_resolved → trades.jsonl: kline_pnl/net_pnl_actual);
this just reads it back cleanly so we can track n toward the n>=100 decision gate
instead of ad-hoc queries.

Filter: bond_entry_class=WEATHER_STWA, direction=BUY_NO. The CURRENT strategy is
the entry>=PRICE_FLOOR(0.50) slice; the cheap-NO below it is the old (now
PRICE_FLOOR-gated-out) bleed and is shown only for contrast.
"""
from __future__ import annotations
import json, statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PRICE_FLOOR = 0.50
REENABLE_TS = datetime(2026, 6, 5, tzinfo=timezone.utc).timestamp()  # favorite-longshot NO re-enable
N_GATE = 100


def _won(t):  # NO resolves YES->0 (loss) / NO->1 (win); exit>=0.99 == NO won
    return (t.get("exit_price") or 0) >= 0.99


def _stats(label, sub):
    if not sub:
        print(f"  {label:<34} n=0"); return
    pnl = [s.get("kline_pnl", s.get("net_pnl_actual", 0.0)) or 0.0 for s in sub]
    wr = sum(_won(s) for s in sub) / len(sub)
    tot = sum(pnl)
    ev = statistics.mean(pnl)
    print(f"  {label:<34} n={len(sub):<4} total=${tot:+7.2f}  mean=${ev:+.3f}  WR={wr:.0%}")


def main():
    rows = []
    fp = ROOT / "logs/trades.jsonl"
    for l in open(fp):
        l = l.strip()
        if not l:
            continue
        try: t = json.loads(l)
        except: continue
        if t.get("bond_entry_class") == "WEATHER_STWA" and t.get("direction") == "BUY_NO":
            rows.append(t)

    cur = [t for t in rows if (t.get("entry_price") or 0) >= PRICE_FLOOR]
    cheap = [t for t in rows if (t.get("entry_price") or 0) < PRICE_FLOOR]
    post = [t for t in cur if t.get("ts_open", 0) >= REENABLE_TS]

    print("=== model-NO scorecard (realized, WEATHER_STWA BUY_NO) ===")
    _stats("favorite-longshot (entry>=0.50)", cur)
    _stats("  └ since 06-05 re-enable", post)
    _stats("old cheap-NO (entry<0.50, gated out)", cheap)

    # decision-gate progress on the current strategy
    n = len(cur)
    bar = "#" * int(30 * min(1, n / N_GATE))
    print(f"\n  n>=100 gate:  {n}/{N_GATE}  [{bar:<30}]  "
          f"{'CONFIRMED — can act' if n >= N_GATE else 'TREND-ONLY — do not scale'}")

    # entry-price band breakdown (where does the NO edge actually live?)
    print("\n  by entry-price band (current strategy):")
    bands = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.85), (0.85, 1.01)]
    for lo, hi in bands:
        _stats(f"    [{lo:.2f},{hi:.2f})", [t for t in cur if lo <= (t.get("entry_price") or 0) < hi])

    if post:
        print("\n  recent settled (since re-enable):")
        for t in sorted(post, key=lambda r: r.get("ts_open", 0))[-10:]:
            ts = datetime.fromtimestamp(t.get("ts_open", 0), timezone.utc).strftime("%m-%d %H:%M")
            print(f"    {ts}  {str(t.get('signal_source',''))[:26]:<26}  "
                  f"entry={t.get('entry_price'):.2f}  exit={t.get('exit_price')}  "
                  f"pnl=${t.get('kline_pnl',0):+.2f}")


if __name__ == "__main__":
    main()
