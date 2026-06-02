"""Two mechanical weather-market edges from the NegRisk partition trade tape.

Substrate: logs/shadow/hot/<date>/maker_flow.jsonl (executed-trade tape for weather
markets: price/size/side/outcome, eventSlug+slug => buckets group by city-day, txHash
dedup). Resolutions joined from Gamma by event slug.

Every trade is mapped to the YES book side it hit (a BUY-NO lifts the NO ask = hits the
YES bid, etc.), giving a de-bounced two-sided mid per bucket. ΣP(bucket)=1 is exact for
a mutually-exclusive/exhaustive (NegRisk) partition, which is the conserved quantity both
edges exploit.

EDGE 1 — Conservation-Lag Sibling Fade (cross-sectional):
  When an adjacent bucket takes an informed up-shock (mid jumps >=3c), the directly-traded
  bucket prices the info efficiently (post-shock mid ~= realized resolution), but the
  mutually-exclusive SIBLING's separate orderbook lags. Conditional on a +shock to a
  neighbor, the sibling resolves YES BELOW its unconditional calibration by +2.8pp
  (mid 0.4-0.6) to +9.2pp (mid 0.6-0.8). Trade: buy NO on the sibling, hold to resolution.

EDGE 2 — Order-Flow Imbalance Resolution Follow (time-series):
  Rolling 600s signed-notional OFI per bucket predicts resolution BEYOND price. At mid
  0.4-0.6: net-selling (OFI<-0.3) resolves 0.376 vs mid 0.473 (-9.8pp); net-buying
  (OFI>0.3) resolves 0.549 vs 0.500 (+5.0pp). Trade: follow the flow, hold to resolution.

Inputs (built by the helpers below if absent):
  /tmp/wx_temp.parquet   - parsed temperature trade tape
  /tmp/res_by_slug.json  - {"event||market_slug": resolved_yes 0/1}
Usage: python3 analysis/weather/conservation_alpha.py
"""
import json, re, glob
from collections import deque
import numpy as np
import pandas as pd

TAPE = "/tmp/wx_temp.parquet"
RES  = "/tmp/res_by_slug.json"
SHOCK = 0.03
OFI_WIN = 600.0


def _yes_side(outcome, side):
    oc, sd = str(outcome).lower(), str(side).upper()
    return "ask" if ((oc == "yes" and sd == "BUY") or (oc == "no" and sd == "SELL")) else "bid"


def _deg(slug):
    m = re.search(r"(\d+)(c|f)$", str(slug))
    return int(m.group(1)) if m else np.nan


def load():
    wx = pd.read_parquet(TAPE)
    wx["yside"] = [_yes_side(o, s) for o, s in zip(wx["outcome"], wx["side"])]
    wx["deg"] = wx["slug"].apply(_deg)
    res = json.load(open(RES))
    return wx, res


def _mid(la, lb, b):
    a, x = la.get(b, np.nan), lb.get(b, np.nan)
    if np.isnan(a) and np.isnan(x):
        return np.nan
    if np.isnan(a):
        return x
    if np.isnan(x):
        return a
    return 0.5 * (a + x)


def run(wx, res):
    rget = lambda ev, slug: res.get("%s||%s" % (ev, slug))
    uncond, sib, ofi = [], [], []
    for ev, d in wx.groupby("event"):
        if d["slug"].nunique() < 6 or len(d) < 300:
            continue
        d = d.sort_values("ts")
        buckets = list(d["slug"].unique())
        degmap = {b: d[d["slug"] == b]["deg"].iloc[0] for b in buckets}
        la, lb = {}, {}
        flow = {b: deque() for b in buckets}      # (ts, signed$, abs$)
        for ts, slug, ypx, ys, pr, sz in d[["ts", "slug", "yes_px", "yside", "price", "size"]].values.tolist():
            pm = _mid(la, lb, slug)
            (la if ys == "ask" else lb)[slug] = ypx
            nm = _mid(la, lb, slug)
            # EDGE 2: rolling OFI on this bucket
            q = flow[slug]
            notion = pr * sz
            q.append((ts, notion if ys == "ask" else -notion, notion))
            while q and ts - q[0][0] > OFI_WIN:
                q.popleft()
            ry = rget(ev, slug)
            if not np.isnan(nm) and ry is not None:
                uncond.append((nm, ry))
                tot = sum(a for _, _, a in q)
                if tot >= 50 and 0.05 < nm < 0.95:
                    ofi.append((sum(s for _, s, _ in q) / tot, nm, ry))
            # EDGE 1: shock -> adjacent sibling
            if not np.isnan(pm) and not np.isnan(nm) and abs(nm - pm) >= SHOCK:
                for b in buckets:
                    if b == slug or np.isnan(degmap[b]) or np.isnan(degmap[slug]):
                        continue
                    if abs(degmap[b] - degmap[slug]) != 1:
                        continue
                    mb = _mid(la, lb, b)
                    ryb = rget(ev, b)
                    if np.isnan(mb) or mb < 0.05 or mb > 0.95 or ryb is None:
                        continue
                    sib.append((np.sign(nm - pm), mb, ryb))
    return pd.DataFrame(uncond, columns=["mid", "res"]), \
           pd.DataFrame(sib, columns=["dksign", "mid", "res"]), \
           pd.DataFrame(ofi, columns=["ofi", "mid", "res"])


def report(U, S, O):
    bands = [(0.2, 0.4), (0.4, 0.6), (0.6, 0.8)]
    ucal = lambda lo, hi: U[(U.mid >= lo) & (U.mid < hi)]["res"].mean()
    print("EDGE 1 — Conservation-Lag Sibling Fade (short sibling after +shock to neighbor)")
    print("  mid band   n     unconditional   sibling|dk>0   conservation_extra")
    for lo, hi in bands:
        sp = S[(S.dksign > 0) & (S.mid >= lo) & (S.mid < hi)]
        print("  %.1f-%.1f  %5d   %.3f          %.3f (n%d)   +%.4f"
              % (lo, hi, len(sp), ucal(lo, hi), sp.res.mean(), len(sp), ucal(lo, hi) - sp.res.mean()))
    print("\nEDGE 2 — Order-Flow Imbalance Resolution Follow (hold to resolution)")
    print("  mid band   sell(OFI<-.3) edge   buy(OFI>.3) edge   spread")
    for lo, hi in bands:
        sub = O[(O.mid >= lo) & (O.mid < hi)]
        se = sub[sub.ofi < -0.3]; bu = sub[sub.ofi > 0.3]
        se_e = se.res.mean() - se.mid.mean(); bu_e = bu.res.mean() - bu.mid.mean()
        print("  %.1f-%.1f   %+.4f (n%d)      %+.4f (n%d)    %.4f"
              % (lo, hi, se_e, len(se), bu_e, len(bu), bu_e - se_e))


if __name__ == "__main__":
    wx, res = load()
    U, S, O = run(wx, res)
    print("resolved-joined obs: uncond=%d sibling-shock=%d ofi=%d\n" % (len(U), len(S), len(O)))
    report(U, S, O)
