"""Stage 2 — Remaining-Rise Climatology Pricer vs the ACTUAL MARKET (EV test).

Stage 1 proved the empirical pricer beats a Gaussian OOS. This asks the real
question: does it beat the live Polymarket price? For each resolved city-day we
price every bin from the climatology at a POST-PEAK decision time, read the real
CLOB price at that same timestamp, trade the divergence, and score on the actual
Gamma resolution.

  edge(bin) = P_climatology(bin) - market_price(bin)
    edge > +THR  -> buy YES  (pay px, get 1 if winner)
    edge < -THR  -> buy NO   (pay 1-px, get 1 if NOT winner)

Climatology cells are built from the 2021-24 ASOS parquet; the test markets are
2026 -> no leakage (disjoint period AND source). Run on VPS (CLOB+Gamma+Mesonet):

    PYTHONPATH=/root/Klaus python3 analysis/weather/climatology_ev.py
"""
from __future__ import annotations
import numpy as np
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import analysis.weather.climatology_pricer as cp
from analysis.weather.climatology_pricer import season
from analysis.weather.backtest import discover_resolved, attach_entry_prices
from analysis.weather.resolution_bias_backtest import fetch_metars, _T
from analysis.weather.stations import STATIONS

OFFSET = 1            # decision hour = climatological peak + 1  (post-peak)
THR = 0.10            # trade only when |climatology - market| > 10pp
DAYS = 30
CITIES = ["austin", "houston", "dallas", "chicago", "atlanta"]


def cToF(c): return c * 9 / 5 + 32
def fToC(f): return (f - 32) * 5 / 9


def build_climatology():
    cp.TRAIN_MAX_YEAR = 2024                      # use ALL parquet years as train
    df = cp.build_frame("data/stwa_asos.parquet")
    base = cp.day_table(df)
    sub = base.dropna(subset=[f"R{OFFSET}"]).copy()
    sub["rr"] = (sub["M"] - sub[f"R{OFFSET}"]).clip(lower=0)
    cells = {k: np.sort(v["rr"].values) for k, v in sub.groupby(["city", "season"])
             if len(v) >= 40}
    gpool = np.sort(sub["rr"].values)
    peak = base.groupby(["city", "season"])["peak_clim"].first().to_dict()
    return cells, gpool, peak


def ecdf(ssort, x):
    return np.searchsorted(ssort, x, "right") / len(ssort)


def px_at(history, ts):
    """Last CLOB price at or before ts; None if history starts after ts."""
    p = None
    for h in history:
        if h["t"] <= ts:
            p = float(h["p"])
        else:
            break
    return p


def run():
    cells, gpool, peak = build_climatology()
    print(f"climatology cells: {len(cells)} (city,season); decision = peak+{OFFSET}h, THR={THR}")
    trades = []   # (edge, pnl, side, won)
    n_days = 0
    for city in CITIES:
        st = STATIONS.get(city)
        if st is None:
            continue
        try:
            mks = discover_resolved(city, DAYS)
        except Exception as e:
            print(f"  {city}: discover err {str(e)[:50]}"); continue
        if not mks:
            continue
        attach_entry_prices(mks)
        d1 = max(m.valid_day for m in mks) + timedelta(days=2)
        d0 = min(m.valid_day for m in mks)
        metars = fetch_metars(st.icao, d0, d1)
        tz = ZoneInfo(st.tz) if st.tz else timezone.utc
        for m in mks:
            day = m.valid_day
            sea = season(day.month)
            pk = peak.get((city, sea))
            if pk is None:
                continue
            # decision timestamp (UTC) = local peak+OFFSET that day
            dec_local = datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(hours=pk + OFFSET)
            dec_ts = int(dec_local.astimezone(timezone.utc).timestamp())
            lo_utc = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc)
            # running_max (C) from SLP routine-hourly obs up to decision time
            rm = None
            for t, raw in metars:
                if lo_utc <= t <= dec_local.astimezone(timezone.utc) and " SLP" in raw:
                    v = _T(raw)
                    if v is not None:
                        rm = v if rm is None else max(rm, v)
            if rm is None:
                continue
            samp = cells.get((city, sea), gpool)
            n_days += 1
            for b in m.buckets:
                hist = getattr(b, "history", None)
                if not hist:
                    continue
                mkt = px_at(hist, dec_ts)
                if mkt is None or mkt <= 0.02 or mkt >= 0.98:
                    continue
                lo_c = fToC(b.lo_inclusive) if b.lo_inclusive > -1e8 else -1e9
                hi_c = fToC(b.hi_exclusive) if b.hi_exclusive < 1e8 else 1e9
                if st.unit == "C":
                    lo_c = b.lo_inclusive if b.lo_inclusive > -1e8 else -1e9
                    hi_c = b.hi_exclusive if b.hi_exclusive < 1e8 else 1e9
                p_clim = ecdf(samp, hi_c - rm) - ecdf(samp, lo_c - rm)
                edge = p_clim - mkt
                if edge > THR:                       # buy YES
                    pnl = (1 - mkt) if b.is_winner else -mkt
                    trades.append((edge, pnl, "YES", b.is_winner))
                elif edge < -THR:                    # buy NO
                    pnl = mkt if not b.is_winner else -(1 - mkt)
                    trades.append((edge, pnl, "NO", not b.is_winner))
        print(f"  {city}: {len(mks)} mkts, cum trades={len(trades)}")

    if not trades:
        print("no trades"); return
    pnl = [t[1] for t in trades]
    yes = [t for t in trades if t[2] == "YES"]
    no = [t for t in trades if t[2] == "NO"]
    print(f"\n=== CLIMATOLOGY vs MARKET — EV (decision peak+{OFFSET}h, n_days={n_days}) ===")
    print(f"total trades: {len(trades)}  WR={100*sum(t[3] for t in trades)/len(trades):.0f}%  "
          f"meanEV={np.mean(pnl):+.4f}/contract  total={sum(pnl):+.2f}")
    for nm, grp in [("BUY YES (climatology>market)", yes), ("BUY NO  (climatology<market)", no)]:
        if grp:
            g = [t[1] for t in grp]
            print(f"  {nm}: n={len(grp)} WR={100*sum(t[3] for t in grp)/len(grp):.0f}% "
                  f"meanEV={np.mean(g):+.4f} total={sum(g):+.2f}")
    # EV by edge magnitude (is bigger divergence -> bigger edge? = real signal)
    print("  by |edge| decile:")
    ts = sorted(trades, key=lambda x: abs(x[0]))
    for q,(a,b) in enumerate([(0,.33),(.33,.66),(.66,1.0)]):
        chunk = ts[int(a*len(ts)):int(b*len(ts))]
        if chunk:
            g=[c[1] for c in chunk]
            print(f"    |edge| tier {q}: n={len(chunk)} meanEV={np.mean(g):+.4f} "
                  f"avg|edge|={np.mean([abs(c[0]) for c in chunk]):.2f}")


if __name__ == "__main__":
    run()
