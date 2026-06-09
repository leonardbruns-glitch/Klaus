"""
Maker-MVP Stage-0 fill-feasibility backtest (read-only, no capital).

Question: as the MAKER on provenance-clean near-locked weather buckets, how much
PROFITABLE taker flow could we capture, at what realized edge, vs the competing book?

Two profitable maker actions on a locked bucket (NO is the ~certain winner):
  Path A  post NO BID  -> capture taker SELL-No flow. Buy NO at price p, NO pays ~1.
          our pnl/share = (no_won - p).                         (no new primitive)
  Path B  mint+sell YES -> capture taker BUY-Yes flow. Sell YES at p, keep NO (minted).
          our pnl/share = (p - yes_won).                        (needs a mint primitive)
Both use ACTUAL Gamma resolution (token_won) from the harvested taker trades — no assumed WR.

Provenance gate: lock confirmed in metar_lockout with safety margin >= MARGIN_MIN
(running_max - bucket_hi), excluding known-bad source cities. Only trades AFTER the
first observed lock time on that market are counted (we could only post once locked).

Competition: incumbent same-side book depth (from metar_lockout) is the queue ahead of us;
we report gross pool + edge, then net $/day under capture haircuts.

Run: python3 analysis/weather/maker_backtest.py
"""
from __future__ import annotations
import glob, json
import numpy as np
import pandas as pd

TT = "data/taker_trades_2026-05-24_2026-05-28.parquet"
LK_GLOB = "logs/shadow/hot/2026-05-2[4-6]/metar_lockout.jsonl"
MARGIN_MIN = 0.5                      # °C safety margin to call a lock provenance-robust
BAD_CITIES = {"hong-kong", "moscow", "istanbul", "tel-aviv"}
FEE = 0.0                             # Polymarket taker/maker fee (currently ~0)
DAYS = 3


def norm(s): return (s or "").strip().lower().replace(" ", "-").replace("_", "-")


def load_locks():
    """condition_id -> dict(margin_max, first_lock_ts, city, no_bid_depth, yes_ask_depth)."""
    info = {}
    for fp in glob.glob(LK_GLOB):
        for line in open(fp):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("record_type") != "metar_lockout_candidate":
                continue
            rm, hi = r.get("running_max_c"), r.get("bucket_hi_c_padded")
            if rm is None or hi is None or rm <= hi:
                continue
            cid = r.get("condition_id")
            if not cid:
                continue
            margin = rm - hi
            nb = (r.get("no_book") or {}).get("bids") or []
            ya = (r.get("yes_book") or {}).get("asks") or []
            no_bid_depth = sum(b.get("usd", b["price"]*b["size"]) for b in nb)
            yes_ask_depth = sum(a.get("usd", a["price"]*a["size"]) for a in ya)
            d = info.get(cid)
            if d is None:
                info[cid] = dict(margin=margin, first_ts=r.get("ts_s", 0),
                                 city=norm(r.get("city")), nbd=[no_bid_depth], yad=[yes_ask_depth])
            else:
                d["margin"] = max(d["margin"], margin)
                d["first_ts"] = min(d["first_ts"], r.get("ts_s", 0))
                d["nbd"].append(no_bid_depth); d["yad"].append(yes_ask_depth)
    return info


def main():
    tt = pd.read_parquet(TT)
    locks = load_locks()
    print(f"taker trades: {len(tt):,} | locked cids in lockout log: {len(locks)}")

    # provenance-gated locked cids
    good = {c: d for c, d in locks.items()
            if d["margin"] >= MARGIN_MIN and d["city"] not in BAD_CITIES}
    print(f"provenance-gated locked cids (margin>={MARGIN_MIN}C, good city): {len(good)}")

    f = tt[tt.cid.isin(good)].copy()
    f["first_ts"] = f.cid.map(lambda c: good[c]["first_ts"])
    f = f[f.ts >= f.first_ts]           # only after the lock was observable
    print(f"taker trades on gated locked buckets, post-lock: {len(f):,}  notional ${f.notional.sum():,.0f}\n")

    def report(name, side, outcome, edge_fn):
        s = f[(f.side == side) & (f.outcome == outcome)].copy()
        if not len(s):
            print(f"{name}: no flow\n"); return
        s["e"] = edge_fn(s)                       # realized pnl/share if WE were the maker
        gross = (s.e * s["size"]).sum()
        pool = s.notional.sum()
        wr = float((s.e > 0).mean())
        nM = s.cid.nunique()
        # per-market edge (each locked market = one vote) to avoid pseudo-replication
        pm = s.groupby("cid").apply(lambda x: np.average(x.e, weights=x["size"]))
        ev_pm = pm.mean(); se = pm.std()/np.sqrt(len(pm))
        print(f"{name}  (capture taker {side} {outcome})")
        print(f"  flow pool ${pool:,.0f} over {DAYS}d = ${pool/DAYS:,.0f}/day across {nM} markets")
        print(f"  realized WR(maker-side win)={100*wr:.0f}%  avg taker price={s.price.mean():.3f}")
        print(f"  GROSS maker pnl if we took ALL of it: ${gross:,.0f} ({DAYS}d) = ${gross/DAYS:,.0f}/day")
        print(f"  per-market edge/share = {ev_pm:+.3f} [{ev_pm-1.96*se:+.3f},{ev_pm+1.96*se:+.3f}]")
        # incumbent competition depth (median, from book)
        nbd = np.median([np.median(good[c]["nbd"]) for c in s.cid.unique() if good[c]["nbd"]])
        yad = np.median([np.median(good[c]["yad"]) for c in s.cid.unique() if good[c]["yad"]])
        print(f"  incumbent book depth (median/mkt): NO-bid ${nbd:,.0f}  YES-ask ${yad:,.0f}  (queue ahead of us)")
        for hc in (0.10, 0.25, 0.50):
            print(f"    if we capture {int(hc*100)}% of flow: net ${hc*gross/DAYS:,.0f}/day "
                  f"(after {FEE*100:.0f}% fee)")
        print()

    # Path A: post NO bid, capture SELL No. pnl/share = no_won - price.
    report("PATH A: NO-BID", "SELL", "No", lambda s: s.token_won - s.price)
    # Path B: mint + sell YES, capture BUY Yes. pnl/share = price - yes_won.
    report("PATH B: SELL-YES(mint)", "BUY", "Yes", lambda s: s.price - s.token_won)

    print("baseline to beat: validated TAKER path = 70% fill, ~$500 notional/burst, "
          "edge at NO<0.90 (settlement_lock_validation).")


if __name__ == "__main__":
    main()
