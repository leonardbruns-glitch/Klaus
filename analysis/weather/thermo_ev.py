"""Stage 2 for the THERMO NOWCAST — does it beat the actual market (not climatology)?

Decision = climatological peak - 3h (pre-peak, the nowcast's edge zone, market
liquid). Price each bin from the morning thermo nowcast (dew + velocity + air
mass), read the real CLOB price at that timestamp, trade |edge|>THR, score on the
Gamma resolution. Model trained on 2021-24 ASOS; test markets 2026 (no leakage).

    PYTHONPATH=/root/Klaus python3 analysis/weather/thermo_ev.py
"""
from __future__ import annotations
import re, numpy as np
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sklearn.ensemble import HistGradientBoostingRegressor

import analysis.weather.thermo_nowcast as tn
from analysis.weather.climatology_pricer import season
from analysis.weather.backtest import discover_resolved, attach_entry_prices
from analysis.weather.resolution_bias_backtest import fetch_metars, _T
from analysis.weather.stations import STATIONS

OFFSET = -3
THR = 0.10
DAYS = 30
CITIES = ["austin", "houston", "dallas", "chicago", "atlanta"]
FEATS = ["depr", "vel", "t5", "rm5", "month", "cityc"]   # no cloud (METAR sky parse unreliable)


def _Td(raw):
    m = re.search(r" T([01])(\d{3})([01])(\d{3})", raw)
    return (-1 if m.group(3) == '1' else 1) * int(m.group(4)) / 10.0 if m else None


def fToC(f): return (f - 32) * 5 / 9


def train_model():
    tn.MORNING_OFFSET = OFFSET
    D = tn.frame()
    citycode = {c: i for i, c in enumerate(sorted(D.city.unique()))}
    D["cityc"] = D.city.map(citycode)
    gb = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05,
                                       max_iter=400, l2_regularization=1.0)
    gb.fit(D[FEATS], D.rr)
    resid = np.sort((D.rr - gb.predict(D[FEATS])).values)        # empirical residual law
    peak = D.groupby(["city", "season"])["pk"].agg(
        lambda s: int(s.round().mode().iloc[0])).to_dict()
    return gb, resid, peak, citycode


def metar_series(metars):
    """[(utc_dt, temp_c, dew_c)] for SLP routine-hourly obs with a T-group."""
    out = []
    for t, raw in metars:
        if " SLP" in raw:
            tc, dc = _T(raw), _Td(raw)
            if tc is not None:
                out.append((t, tc, dc))
    return sorted(out)


def px_at(history, ts):
    p = None
    for h in history:
        if h["t"] <= ts:
            p = float(h["p"])
        else:
            break
    return p


def run():
    gb, resid, peak, citycode = train_model()
    print(f"thermo model trained; residual law n={len(resid)}; decision=peak{OFFSET}h THR={THR}")
    trades = []
    for city in CITIES:
        st = STATIONS.get(city)
        if st is None or city not in citycode:
            continue
        try:
            mks = discover_resolved(city, DAYS)
        except Exception as e:
            print(f"  {city}: {str(e)[:40]}"); continue
        if not mks:
            continue
        attach_entry_prices(mks)
        ser = metar_series(fetch_metars(st.icao, min(m.valid_day for m in mks),
                                        max(m.valid_day for m in mks) + timedelta(days=2)))
        tz = ZoneInfo(st.tz) if st.tz else timezone.utc
        for m in mks:
            day = m.valid_day; sea = season(day.month)
            pk = peak.get((city, sea))
            if pk is None:
                continue
            dec = (datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(hours=pk + OFFSET))
            dec_utc = dec.astimezone(timezone.utc)
            dec_ts = int(dec_utc.timestamp())
            lo_utc = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc)
            obs = [(t, tc, dc) for (t, tc, dc) in ser if lo_utc <= t <= dec_utc]
            if not obs:
                continue
            t5, d5 = obs[-1][1], obs[-1][2]
            if d5 is None:
                continue
            rm5 = max(tc for _, tc, _ in obs)
            t2 = next((tc for t, tc, _ in reversed(obs) if t <= dec_utc - timedelta(hours=2)), t5)
            X = [[t5 - d5, t5 - t2, t5, rm5, day.month, citycode[city]]]
            rise = float(gb.predict(X)[0])
            Mdist = rm5 + rise + resid                      # predictive law for daily max (C)
            for b in m.buckets:
                hist = getattr(b, "history", None)
                if not hist:
                    continue
                mkt = px_at(hist, dec_ts)
                if mkt is None or mkt <= 0.03 or mkt >= 0.97:
                    continue
                lo = fToC(b.lo_inclusive) if b.lo_inclusive > -1e8 else -1e9
                hi = fToC(b.hi_exclusive) if b.hi_exclusive < 1e8 else 1e9
                if st.unit == "C":
                    lo = b.lo_inclusive if b.lo_inclusive > -1e8 else -1e9
                    hi = b.hi_exclusive if b.hi_exclusive < 1e8 else 1e9
                p_th = float(np.mean((Mdist >= lo) & (Mdist < hi)))
                edge = p_th - mkt
                if edge > THR:
                    trades.append((edge, (1 - mkt) if b.is_winner else -mkt, "YES", b.is_winner))
                elif edge < -THR:
                    trades.append((edge, mkt if not b.is_winner else -(1 - mkt), "NO", not b.is_winner))
        print(f"  {city}: {len(mks)} mkts, cum trades={len(trades)}")

    if not trades:
        print("no trades"); return
    pnl = [t[1] for t in trades]
    print(f"\n=== THERMO NOWCAST vs MARKET (decision peak{OFFSET}h) ===")
    print(f"trades={len(trades)} WR={100*sum(t[3] for t in trades)/len(trades):.0f}% "
          f"meanEV={np.mean(pnl):+.4f}/contract total={sum(pnl):+.2f}")
    for nm in ("YES", "NO"):
        g = [t for t in trades if t[2] == nm]
        if g:
            print(f"  BUY {nm}: n={len(g)} WR={100*sum(t[3] for t in g)/len(g):.0f}% "
                  f"meanEV={np.mean([t[1] for t in g]):+.4f} total={sum(t[1] for t in g):+.2f}")
    ts = sorted(trades, key=lambda x: abs(x[0]))
    for q, (a, b) in enumerate([(0, .5), (.5, 1.0)]):
        ch = ts[int(a*len(ts)):int(b*len(ts))]
        if ch:
            print(f"  |edge| {'low' if q==0 else 'high'} half: n={len(ch)} "
                  f"meanEV={np.mean([c[1] for c in ch]):+.4f} avg|edge|={np.mean([abs(c[0]) for c in ch]):.2f}")


if __name__ == "__main__":
    run()
