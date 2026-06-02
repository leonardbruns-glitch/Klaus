#!/usr/bin/env python3
"""
edge2_shadow_summary.py — join EDGE 2 shadow signals to Gamma resolution and report
forward WR / EV per band. Read-only. Run after edge2_shadow.py has accumulated signals.

For each logged signal: predicted YES if direction==BUY_YES else NO. Realized from the
market's resolved outcomePrices. Net edge per contract (hold-to-resolution, one spread
crossing already implied by entering at the touch):
  BUY_YES: realized_yes - entry_ask        (you pay the ask, win 1 if YES)
  BUY_NO : (1-realized_yes) - (1-entry_bid) = entry_bid - realized_yes
Reports WR, mean net edge, and n by mid band + by |OFI|, flagging the n>=100 gate.

Usage: python3 analysis/weather/edge2_shadow_summary.py
"""
import glob
import json
import time
import urllib.request

import numpy as np

GAMMA = "https://gamma-api.polymarket.com"


def _gj(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return json.load(urllib.request.urlopen(req, timeout=20))
    except Exception:
        return None


def load_signals():
    rows = []
    for fn in sorted(glob.glob("logs/shadow/hot/*/edge2_shadow.jsonl")):
        for l in open(fn):
            try:
                rows.append(json.loads(l))
            except Exception:
                pass
    # keep last signal per cid (one fire/bucket/day already enforced; dedup across days by cid+day)
    return rows


def fetch_resolution(cids):
    res = {}
    for i, cid in enumerate(cids):
        m = _gj(f"{GAMMA}/markets?condition_ids={cid}")
        if m and isinstance(m, list):
            op = m[0].get("outcomePrices")
            if isinstance(op, str):
                try:
                    op = json.loads(op)
                except Exception:
                    op = None
            if op and len(op) >= 2:
                try:
                    yp = float(op[0])
                except ValueError:
                    yp = None
                if yp is not None and (yp > 0.98 or yp < 0.02):
                    res[cid] = 1 if yp > 0.5 else 0
        if i % 40 == 0:
            time.sleep(0.2)
    return res


def main():
    sig = load_signals()
    print(f"signals logged: {len(sig)}")
    if not sig:
        return
    cids = sorted({r["cid"] for r in sig})
    res = fetch_resolution(cids)
    print(f"resolved: {len(res)}/{len(cids)} buckets\n")
    rec = []
    for r in sig:
        ry = res.get(r["cid"])
        if ry is None:
            continue
        mid = r["entry_yes_mid"]
        if r["direction"] == "BUY_YES":
            edge = ry - r.get("best_ask", mid)
            win = ry == 1
        else:
            edge = r.get("best_bid", mid) - ry
            win = ry == 0
        rec.append((mid, abs(r["ofi"]), r["direction"], edge, win, r.get("fillable_usd_side", 0)))
    if not rec:
        print("no resolved signals yet")
        return
    arr = rec
    def report(name, sub):
        if not sub:
            return
        e = np.array([x[3] for x in sub]); w = np.array([x[4] for x in sub])
        print(f"  {name:22} n={len(sub):4} WR={w.mean()*100:5.1f}%  netEV/contract={e.mean():+.4f}  "
              f"median_depth=${np.median([x[5] for x in sub]):.0f}")
    print("=== overall ===")
    report("ALL", arr)
    report("BUY_YES (follow buy)", [x for x in arr if x[2] == "BUY_YES"])
    report("BUY_NO (follow sell)", [x for x in arr if x[2] == "BUY_NO"])
    print("\n=== by entry mid band ===")
    for lo, hi in [(0.2, 0.4), (0.4, 0.6), (0.6, 0.8)]:
        report(f"mid {lo:.1f}-{hi:.1f}", [x for x in arr if lo <= x[0] < hi])
    print("\n=== by |OFI| ===")
    for lo, hi in [(0.30, 0.5), (0.5, 0.75), (0.75, 1.01)]:
        report(f"|OFI| {lo:.2f}-{hi:.2f}", [x for x in arr if lo <= x[1] < hi])
    n = len(arr)
    print(f"\nn>=100 gate: {'MET' if n >= 100 else 'NOT MET (%d/100)' % n} — "
          f"do not size up until each traded band clears n>=100 with netEV>0.")


if __name__ == "__main__":
    main()
