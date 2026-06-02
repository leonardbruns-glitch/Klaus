"""P2 Stage-2 — does the VELOCITY first-passage pricer beat the actual MARKET?

Stage-1 proved velocity beats a velocity-BLIND empirical pricer out-of-sample. The
real gate (prior climatology/thermo probes beat their baselines but LOST to market):
does conditioning on dT/dt beat the live CLOB price? Decision = climatological peak
+ OFFSET (POST-peak grey zone, where the static CDF overprices the next-up bucket when
temp is already falling). Reconstruct running_max / T_now / v_now from real METARs at
the decision instant, price grey-zone buckets (steps 0/1/2 above the current max int)
with the Stage-1 pmf, read the real CLOB price, trade |edge|>THR, score on Gamma
resolution. pmf trained on 2021-23 ASOS; test markets 2026 → no leakage.

Runs BOTH the velocity-AWARE and velocity-BLIND pricers on the SAME trades so the
velocity contribution vs market is isolated. The win signature = vel-AWARE meanEV>0
with |edge|-HIGH half POSITIVE, where vel-BLIND is flat/negative.

    PYTHONPATH=/root/Klaus python3 analysis/weather/stwa_firstpassage_ev.py
"""
from __future__ import annotations
import numpy as np
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from analysis.weather.backtest import discover_resolved, attach_entry_prices
from analysis.weather.resolution_bias_backtest import fetch_metars, _T
from analysis.weather.stations import STATIONS
import analysis.weather.stwa_firstpassage_velocity as F

OFFSETS = [0, 1]                 # decision hours past climatological peak (grey zone)
THR = 0.10
DAYS = 30
CITIES = ["austin", "houston", "dallas", "chicago", "atlanta"]   # clean US °F join


def to_unit(c, unit):
    return c * 9.0 / 5.0 + 32.0 if unit == "F" else c


def vbin(v):
    i = int(np.digitize([v], F.V_BINS)[0]) - 1
    return F.V_LBL[min(max(i, 0), len(F.V_LBL) - 1)]


def px_at(history, ts):
    p = None
    for h in history:
        if h["t"] <= ts:
            p = float(h["p"])
        else:
            break
    return p


def build_pricers():
    df = F.add_climatology(F.build_decision_table())
    tr = df[df.year.isin(F.TRAIN_YEARS)]
    M, _ = F.fit_pmf(tr, ["htp", "hroom", "vbin"])
    B1, _ = F.fit_pmf(tr, ["htp", "hroom"])
    g = tr.groupby("steps").size().reindex(range(F.STEP_CAP + 1), fill_value=1).values.astype(float)
    g = g / g.sum()
    cpk = tr.groupby(["city", "month"]).agg(clim_peak=("peak_hour", "mean"),
                                            clim_dmax=("dmax_int", "mean"))
    return M, B1, g, cpk


def pmf_lookup(tab, key, fallback):
    try:
        return tab.loc[key].values
    except (KeyError, TypeError):
        return fallback


def run():
    M, B1, gpmf, cpk = build_pricers()
    print(f"pricers built (vel-aware M, vel-blind B1); decision=peak+{OFFSETS}h THR={THR}", flush=True)
    # collect trades: each = (edge, pnl, side, won) per pricer, keyed identically
    rec = {"M": [], "B1": []}
    for city in CITIES:
        st = STATIONS.get(city)
        if st is None:
            continue
        try:
            mks = discover_resolved(city, DAYS)
        except Exception as e:
            print(f"  {city}: {str(e)[:50]}"); continue
        if not mks:
            continue
        attach_entry_prices(mks)
        ser = sorted((t, _T(raw)) for t, raw in
                     fetch_metars(st.icao, min(m.valid_day for m in mks),
                                  max(m.valid_day for m in mks) + timedelta(days=2))
                     if " SLP" in raw and _T(raw) is not None)
        tz = ZoneInfo(st.tz) if st.tz else timezone.utc
        n_eval = 0
        for m in mks:
            day = m.valid_day; mo = day.month
            try:
                pk = int(round(cpk.loc[(city, mo), "clim_peak"]))
                cdmax = float(cpk.loc[(city, mo), "clim_dmax"])
            except KeyError:
                continue
            lo_utc = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc)
            for off in OFFSETS:
                dec = datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(hours=pk + off)
                dec_utc = dec.astimezone(timezone.utc); dec_ts = int(dec_utc.timestamp())
                obs = [(t, tc) for (t, tc) in ser if lo_utc <= t <= dec_utc]
                if len(obs) < 3:
                    continue
                t_now = to_unit(obs[-1][1], st.unit)
                rm = to_unit(max(tc for _, tc in obs), st.unit)
                t1 = next((to_unit(tc, st.unit) for t, tc in reversed(obs)
                           if t <= dec_utc - timedelta(hours=1)), t_now)
                v = t_now - t1
                cur_int = int(round(rm))
                htp = int(np.clip(round((pk + off) - cpk.loc[(city, mo), "clim_peak"]), -4, 4))
                hroom = int(np.clip(round(cdmax - rm), -1, 5))
                pmfM = pmf_lookup(M, (htp, hroom, vbin(v)), pmf_lookup(B1, (htp, hroom), gpmf))
                pmfB = pmf_lookup(B1, (htp, hroom), gpmf)
                n_eval += 1
                for b in m.buckets:
                    hist = getattr(b, "history", None)
                    if not hist or b.lo_inclusive < -1e8 or b.hi_exclusive > 1e8:
                        continue
                    lo_u = b.lo_inclusive if st.unit == "F" else b.lo_inclusive
                    hi_u = b.hi_exclusive if st.unit == "F" else b.hi_exclusive
                    b_int = int(round((lo_u + hi_u) / 2.0))
                    steps = b_int - cur_int
                    if steps < 0 or steps > 2:
                        continue
                    mkt = px_at(hist, dec_ts)
                    if mkt is None or mkt <= 0.03 or mkt >= 0.97:
                        continue
                    won = bool(b.is_winner)
                    for tag, pmf in (("M", pmfM), ("B1", pmfB)):
                        edge = float(pmf[steps]) - mkt
                        if edge > THR:
                            rec[tag].append((edge, (1 - mkt) if won else -mkt, "YES", won))
                        elif edge < -THR:
                            rec[tag].append((edge, mkt if not won else -(1 - mkt), "NO", (not won)))
        print(f"  {city}: {len(mks)} mkts, {n_eval} decision pts", flush=True)

    for tag, name in (("B1", "velocity-BLIND (baseline)"), ("M", "velocity-AWARE (P2)")):
        tr = rec[tag]
        print(f"\n=== {name} vs MARKET (decision peak+{OFFSETS}h) ===")
        if not tr:
            print("  no trades"); continue
        pnl = [t[1] for t in tr]
        print(f"  trades={len(tr)} WR={100*sum(t[3] for t in tr)/len(tr):.0f}% "
              f"meanEV={np.mean(pnl):+.4f}/contract total={sum(pnl):+.2f}")
        for nm in ("YES", "NO"):
            g = [t for t in tr if t[2] == nm]
            if g:
                print(f"    BUY {nm}: n={len(g)} WR={100*sum(t[3] for t in g)/len(g):.0f}% "
                      f"meanEV={np.mean([t[1] for t in g]):+.4f} total={sum(t[1] for t in g):+.2f}")
        ts = sorted(tr, key=lambda x: abs(x[0]))
        for q, (a, b) in enumerate([(0, .5), (.5, 1.0)]):
            ch = ts[int(a*len(ts)):int(b*len(ts))]
            if ch:
                print(f"    |edge| {'low ' if q==0 else 'high'} half: n={len(ch)} "
                      f"meanEV={np.mean([c[1] for c in ch]):+.4f} avg|edge|={np.mean([abs(c[0]) for c in ch]):.2f}")


if __name__ == "__main__":
    run()
