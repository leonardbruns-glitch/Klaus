"""OFI edge vs TIME-TO-RESOLUTION — READ-ONLY.

conservation_alpha.py measured EDGE 2 (OFI resolution-follow) POOLED across all
horizons (no seconds-to-close gate). This bins the SAME observations by time-to-
resolution to answer: where in a market's life does the OFI->resolution edge live?
That is exactly the cut the live gates (OFI_MIN_SEC_TO_CLOSE=120, the 6h cap) assume
but the finding never tested.

Edge per cell = resolution - entry mid (hold-to-resolution, identical to EDGE 2).
close_ts proxy = max(trade ts) within an event (we have no settlement timestamp
offline; trading runs to resolution so last-trade ~ close, biased slightly EARLY).

Reuses wx_tape_build.build_tape() (offline) + cached /tmp/res_by_slug.json.
"""
import json
from collections import deque
import numpy as np
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from wx_tape_build import build_tape

OFI_WIN = 600.0
OFI_TRIG = 0.30        # |OFI| trigger, matches conservation_alpha EDGE 2
VOL_MIN  = 50.0
# time-to-resolution bins (seconds)
TTC_BINS = [(0, 1800, "<30m"), (1800, 3600, "30-60m"), (3600, 7200, "1-2h"),
            (7200, 21600, "2-6h"), (21600, 43200, "6-12h"), (43200, 1e12, ">12h")]
MID_BANDS = [(0.2, 0.4), (0.4, 0.6), (0.6, 0.8)]


def _yes_side(outcome, side):
    oc, sd = str(outcome).lower(), str(side).upper()
    return "ask" if ((oc == "yes" and sd == "BUY") or (oc == "no" and sd == "SELL")) else "bid"


def _mid(la, lb, b):
    a, x = la.get(b, np.nan), lb.get(b, np.nan)
    if np.isnan(a) and np.isnan(x):
        return np.nan
    if np.isnan(a):
        return x
    if np.isnan(x):
        return a
    return 0.5 * (a + x)


def build_obs(wx, res):
    rget = lambda ev, slug: res.get("%s||%s" % (ev, slug))
    rows = []
    for ev, d in wx.groupby("event"):
        if d["slug"].nunique() < 6 or len(d) < 300:
            continue
        d = d.sort_values("ts")
        close_ts = d["ts"].max()                       # proxy resolution time
        la, lb = {}, {}
        flow = {b: deque() for b in d["slug"].unique()}
        for ts, slug, ypx, ys, pr, sz in d[["ts", "slug", "yes_px", "yside", "price", "size"]].values.tolist():
            (la if ys == "ask" else lb)[slug] = ypx
            nm = _mid(la, lb, slug)
            q = flow[slug]
            notion = pr * sz
            q.append((ts, notion if ys == "ask" else -notion, notion))
            while q and ts - q[0][0] > OFI_WIN:
                q.popleft()
            ry = rget(ev, slug)
            if np.isnan(nm) or ry is None:
                continue
            tot = sum(a for _, _, a in q)
            if tot >= VOL_MIN and 0.05 < nm < 0.95:
                ofi = sum(s for _, s, _ in q) / tot
                rows.append((ofi, nm, int(ry), close_ts - ts))
    return pd.DataFrame(rows, columns=["ofi", "mid", "res", "ttc"])


def report(O):
    print("total OFI obs: %d  (events with >=6 buckets & >=300 fills)\n" % len(O))
    for lo, hi in MID_BANDS:
        band = O[(O.mid >= lo) & (O.mid < hi)]
        print("=== MID %.1f-%.1f  (n=%d) ===" % (lo, hi, len(band)))
        print("  ttc bin     n_buy  buy_edge   n_sell sell_edge   SPREAD")
        for a, b, lbl in TTC_BINS:
            seg = band[(band.ttc >= a) & (band.ttc < b)]
            bu = seg[seg.ofi > OFI_TRIG]
            se = seg[seg.ofi < -OFI_TRIG]
            be = (bu.res.mean() - bu.mid.mean()) if len(bu) else np.nan
            see = (se.res.mean() - se.mid.mean()) if len(se) else np.nan
            spread = (be - see) if (len(bu) and len(se)) else np.nan
            print("  %-9s  %5d  %+7.3f   %5d  %+7.3f   %+7.3f"
                  % (lbl, len(bu), be if not np.isnan(be) else 0,
                     len(se), see if not np.isnan(see) else 0,
                     spread if not np.isnan(spread) else 0))
        print()


if __name__ == "__main__":
    wx = build_tape()
    wx["yside"] = [_yes_side(o, s) for o, s in zip(wx["outcome"], wx["side"])]
    res = json.load(open("/tmp/res_by_slug.json"))
    print("tape fills=%d  events=%d  resolved buckets=%d\n"
          % (len(wx), wx["event"].nunique(), len(res)))
    O = build_obs(wx, res)
    report(O)
