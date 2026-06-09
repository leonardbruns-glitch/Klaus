"""FAVORITE-EV — does predicting the winner beat the market? (READ-ONLY)

Settles the user claim "being correctly priced is fine as long as we predict the
winner." Theory: if a bucket's market ask == true win prob, buying YES = -fee EV.
Profit needs our model p(winner) > market price(winner). This MEASURES it on the
DEPLOYED model (p_ps logged live) joined to REAL CLOB asks + REAL Gamma resolution.

Strategy under test (the FAVORITE play):
  (A) BUY YES on the model argmax-p_ps bucket at the live CLOB ask.
  (B) BUY NO  on the buckets the model predicts will LOSE (low p_ps) at live CLOB ask.
Diagnostic (C): model-favorite WR vs market-favorite WR, and the DIVERGENCE subset
  (model argmax bucket != market highest-price bucket) — the only place a winner-ID
  edge can live.

MECHANICS (non-negotiable):
- argmax p_ps is the model favorite (calibration-independent — g is monotone).
- Decision time = the LAST PRE_PEAK pricer_eval snapshot for that city-day (no look-ahead).
- Market ask read from CLOB prices-history at that decision ts.
- Resolution = Gamma outcomePrices (is_winner). Daily-max settlement.
- EXCLUDE buckets already locked out at decision time (running_max past hi) from the
  YES-favorite test (lockout-NO is a different edge). Report them separately.
- Fee = prob-weighted taker_fee_rate(p)=0.0125*4*p*(1-p) on the TRADED price.
- AGGREGATE PER MARKET (city,day). One row per (city,day). n>=100 for any verdict.

    PYTHONPATH=/root/Klaus python3 analysis/weather/favorite_ev.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from analysis.weather.backtest import discover_resolved, attach_entry_prices
from analysis.weather.stations import STATIONS
from strategy.fee_model import taker_fee_rate

PRICER_DAYS = ["2026-05-31", "2026-06-01", "2026-06-02", "2026-06-03"]
LOG_ROOT = "/root/Klaus/logs/shadow/hot"
DAYS_BACK = 8          # discover_resolved lookback (covers weather days 05-30..06-03)
MIN_PX, MAX_PX = 0.02, 0.98   # tradeable ask band (avoid pinned/degenerate quotes)
NO_LOSER_MAX_PPS = 0.05       # "model predicts LOSE" = p_ps below this
NO_LOSER_PX_MIN = 0.03        # NO leg must have a real (non-trivial) YES ask to short


def c_to_unit(c: float, unit: str) -> float:
    return c * 9.0 / 5.0 + 32.0 if unit == "F" else c


def weather_day(t_close: float, tz: ZoneInfo):
    """t_close ~ 00:00-01:00 LOCAL the day AFTER the weather day. Back off 3h."""
    return (datetime.fromtimestamp(t_close - 3 * 3600, tz)).date()


def bucket_id(lo_c: float, hi_c: float, unit: str):
    """Canonical integer bucket label matching backtest's lo_inclusive (market unit).

    Returns ('lo', None)/('hi', None) for open-ended buckets, else ('mid', int_lo).
    Pricer lo/hi are PADDED (+/-0.5 unit) edges stored in degC.
    """
    open_lo = lo_c <= -900
    open_hi = hi_c >= 900
    if open_lo:
        return ("lo", None)
    if open_hi:
        return ("hi", None)
    lo_u = c_to_unit(lo_c, unit)
    # pricer lo_u is integer-0.5; backtest lo_inclusive is that integer.
    return ("mid", int(round(lo_u + 0.5)))


def backtest_bucket_id(b, unit: str):
    if b.lo_inclusive == float("-inf"):
        return ("lo", None)
    if b.hi_exclusive == float("inf"):
        return ("hi", None)
    return ("mid", int(round(b.lo_inclusive)))


def px_at(history, ts):
    """Last CLOB price at or before ts (the ask we could have lifted)."""
    p = None
    for h in history:
        if h["t"] <= ts:
            p = float(h["p"])
        else:
            break
    return p


# ---------- 1. Load deployed-model decision snapshots ----------

def load_decision_snapshots():
    """One snapshot per (city, weather_day): the LAST PRE_PEAK pricer_eval row-set.

    Returns: dict[(city, dayiso)] -> {
        'ts': decision_ts, 'unit': unit,
        'buckets': { bucket_id : {'p_ps':float, 'running_max':float, 'lo_c','hi_c'} } }
    """
    # group rows by (city,day); track latest PRE_PEAK ts; collect that ts's buckets
    # pass 1: find latest PRE_PEAK ts per (city,day)
    latest_ts = {}
    for d in PRICER_DAYS:
        path = os.path.join(LOG_ROOT, d, "stwa_pricer_eval.jsonl")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("phase") != "PRE_PEAK":
                    continue
                city = r["city"]
                st = STATIONS.get(city)
                if st is None:
                    continue
                tz = ZoneInfo(st.tz)
                day = weather_day(r["t_close"], tz).isoformat()
                key = (city, day)
                ts = r["ts"]
                if key not in latest_ts or ts > latest_ts[key]:
                    latest_ts[key] = ts

    # pass 2: collect bucket rows at exactly that latest ts (within a small window)
    snaps = {}
    for d in PRICER_DAYS:
        path = os.path.join(LOG_ROOT, d, "stwa_pricer_eval.jsonl")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("phase") != "PRE_PEAK":
                    continue
                city = r["city"]
                st = STATIONS.get(city)
                if st is None:
                    continue
                tz = ZoneInfo(st.tz)
                day = weather_day(r["t_close"], tz).isoformat()
                key = (city, day)
                if key not in latest_ts:
                    continue
                # rows at the decision instant are logged with identical ts per scan
                if abs(r["ts"] - latest_ts[key]) > 1.0:
                    continue
                bid = bucket_id(r["lo"], r["hi"], st.unit)
                snap = snaps.setdefault(key, {"ts": latest_ts[key], "unit": st.unit, "buckets": {}})
                snap["buckets"][bid] = {
                    "p_ps": float(r.get("p_ps", 0.0) or 0.0),
                    "running_max": float(r.get("running_max", -999.0)),
                    "lo_c": r["lo"], "hi_c": r["hi"],
                }
    return snaps


# ---------- 2. Load resolved markets + CLOB history ----------

def load_markets():
    """dict[(city, dayiso)] -> MarketView with entry history attached."""
    out = {}
    cities = sorted({c for (c, _d) in DECISION_KEYS})
    for c in cities:
        try:
            ms = discover_resolved(c, DAYS_BACK)
        except Exception as e:
            print(f"  discover {c}: {str(e)[:60]}", file=sys.stderr)
            continue
        if not ms:
            continue
        attach_entry_prices(ms)   # populates b.history (full CLOB prices-history)
        for m in ms:
            out[(c, m.valid_day.isoformat())] = m
    return out


def main():
    global DECISION_KEYS
    snaps = load_decision_snapshots()
    DECISION_KEYS = list(snaps.keys())
    print(f"model decision snapshots (PRE_PEAK, last-per-city-day): {len(snaps)}", flush=True)

    markets = load_markets()
    print(f"resolved markets discovered + CLOB-attached: {len(markets)}", flush=True)

    # ---- join ----
    yes_fav = []     # per-market: dict for the model-favorite YES bet
    no_loser = []    # per-market aggregate of NO bets on model-predicted-losers
    diverge = []     # per-market: model-fav vs market-fav comparison
    mkt_fav = []     # market-favorite baseline
    join_fail = defaultdict(int)
    n_join = 0
    locked_fav = 0   # model favorite already locked out (excluded from YES test)

    for key, snap in snaps.items():
        city, day = key
        m = markets.get(key)
        if m is None:
            join_fail["no_market"] += 1
            continue
        unit = snap["unit"]
        ts = snap["ts"]

        # index backtest buckets by canonical id, with history price at decision ts
        bt = {}
        for b in m.buckets:
            bid = backtest_bucket_id(b, unit)
            ask = px_at(getattr(b, "history", []) or [], ts)
            bt[bid] = {"is_winner": bool(b.is_winner), "ask": ask,
                       "lo": b.lo_inclusive, "hi": b.hi_exclusive, "label": b.label}

        # require overlapping buckets
        common = [bid for bid in snap["buckets"] if bid in bt]
        if len(common) < 3:
            join_fail["too_few_common_buckets"] += 1
            continue
        # require a real resolution (exactly one winner among buckets)
        winners = [bid for bid in bt if bt[bid]["is_winner"]]
        if len(winners) != 1:
            join_fail["bad_resolution"] += 1
            continue
        n_join += 1

        # ---- model favorite (argmax p_ps over common buckets) ----
        fav_bid = max(common, key=lambda b: snap["buckets"][b]["p_ps"])
        fav_pps = snap["buckets"][fav_bid]["p_ps"]
        fav_info = bt[fav_bid]
        fav_won = fav_info["is_winner"]

        # ---- market favorite (highest CLOB ask among common buckets w/ a price) ----
        priced = [bid for bid in common if bt[bid]["ask"] is not None]
        mfav_bid = max(priced, key=lambda b: bt[b]["ask"]) if priced else None

        # lockout check on the model favorite: running_max already past hi?
        fav_rm = snap["buckets"][fav_bid]["running_max"]
        fav_hi_c = snap["buckets"][fav_bid]["hi_c"]
        fav_locked = (fav_hi_c < 900) and (fav_rm >= fav_hi_c - 1e-9)

        # ===== (A) YES on model favorite =====
        ask = fav_info["ask"]
        if ask is not None and MIN_PX <= ask <= MAX_PX and not fav_locked:
            fee = taker_fee_rate(ask)
            pnl = (1.0 - ask) - fee if fav_won else (-ask - fee)
            yes_fav.append({"city": city, "day": day, "ask": ask, "won": fav_won,
                            "pnl": pnl, "p_ps": fav_pps,
                            "diverge": (mfav_bid is not None and mfav_bid != fav_bid)})
        elif fav_locked:
            locked_fav += 1

        # ===== (B) NO on model-predicted losers =====
        # one aggregate row per market: mean EV across the NO legs we'd place
        leg_pnls = []
        leg_wins = 0
        for bid in common:
            if bid == fav_bid:
                continue
            info = snap["buckets"][bid]
            if info["p_ps"] > NO_LOSER_MAX_PPS:
                continue
            yes_ask = bt[bid]["ask"]
            if yes_ask is None or yes_ask < NO_LOSER_PX_MIN or yes_ask > MAX_PX:
                continue
            # NO ask ~= 1 - yes_bid; we approximate NO entry = 1 - yes_ask (cross to NO)
            no_px = 1.0 - yes_ask
            if no_px <= MIN_PX or no_px >= MAX_PX:
                continue
            won_no = (not bt[bid]["is_winner"])
            fee = taker_fee_rate(no_px)
            pnl = (1.0 - no_px) - fee if won_no else (-no_px - fee)
            leg_pnls.append(pnl)
            leg_wins += int(won_no)
        if leg_pnls:
            no_loser.append({"city": city, "day": day, "n_legs": len(leg_pnls),
                             "mean_pnl": float(np.mean(leg_pnls)),
                             "sum_pnl": float(np.sum(leg_pnls)),
                             "wr": leg_wins / len(leg_pnls)})

        # ===== (C) divergence diagnostic =====
        if mfav_bid is not None:
            mfav_won = bt[mfav_bid]["is_winner"]
            mfav_ask = bt[mfav_bid]["ask"]
            mkt_fav.append({"won": mfav_won, "ask": mfav_ask})
            diverge.append({
                "city": city, "day": day,
                "is_divergent": (mfav_bid != fav_bid),
                "model_fav_won": fav_won,
                "mkt_fav_won": mfav_won,
                "model_fav_ask": ask,
                "mkt_fav_ask": mfav_ask,
            })

    # ---------- report ----------
    def fmt(rows, key="pnl"):
        if not rows:
            return "n=0"
        v = [r[key] for r in rows]
        wr = np.mean([r["won"] for r in rows]) if "won" in rows[0] else None
        s = f"n={len(rows)} meanEV/contract={np.mean(v):+.4f} total=${np.sum(v):+.2f}"
        if wr is not None:
            s += f" WR={100*wr:.1f}%"
        return s

    print("\n================= JOIN YIELD =================")
    print(f"  model snapshots:        {len(snaps)}")
    print(f"  joined city-days (n_markets, clean resolution): {n_join}")
    print(f"  join failures: {dict(join_fail)}")
    print(f"  model favorite already locked-out (excluded from YES): {locked_fav}")

    print("\n================= (A) BUY YES on MODEL FAVORITE =================")
    print(f"  {fmt(yes_fav)}")
    if yes_fav:
        avg_ask = np.mean([r["ask"] for r in yes_fav])
        wr = np.mean([r["won"] for r in yes_fav])
        print(f"  avg ask (market-implied p)={avg_ask:.3f}  vs  realized WR={wr:.3f}")
        print(f"  -> if WR ~= avg_ask, favorite is efficiently priced; EV ~= -fee")
        # FORENSIC: split YES-favorite by divergence + by whether market also liked it
        conv = [r for r in yes_fav if not r["diverge"]]
        dvg = [r for r in yes_fav if r["diverge"]]
        for tag, sub in (("model-fav == market-fav (CONVERGENT)", conv),
                         ("model-fav != market-fav (DIVERGENT)", dvg)):
            if sub:
                print(f"    {tag}: n={len(sub)} WR={100*np.mean([r['won'] for r in sub]):.0f}% "
                      f"avg_ask={np.mean([r['ask'] for r in sub]):.3f} "
                      f"meanEV={np.mean([r['pnl'] for r in sub]):+.4f} total=${np.sum([r['pnl'] for r in sub]):+.2f}")
        # ask-floor sensitivity (does +EV survive dropping the cheap-tail longshots?)
        for floor in (0.02, 0.05, 0.10, 0.20, 0.30):
            sub = [r for r in yes_fav if r["ask"] >= floor]
            if sub:
                print(f"    ask>= {floor:.2f}: n={len(sub)} WR={100*np.mean([r['won'] for r in sub]):.0f}% "
                      f"meanEV={np.mean([r['pnl'] for r in sub]):+.4f} total=${np.sum([r['pnl'] for r in sub]):+.2f}")

    print("\n================= (B) BUY NO on MODEL-PREDICTED LOSERS =================")
    if no_loser:
        mp = [r["mean_pnl"] for r in no_loser]
        sp = [r["sum_pnl"] for r in no_loser]
        wr = np.mean([r["wr"] for r in no_loser])
        tot_legs = sum(r["n_legs"] for r in no_loser)
        print(f"  n_markets={len(no_loser)} (total NO legs={tot_legs})")
        print(f"  meanEV/contract (avg per leg)={np.mean(mp):+.4f}  per-market mean sum=${np.mean(sp):+.4f}")
        print(f"  total$=${np.sum(sp):+.2f}  leg-WR={100*wr:.1f}%")
    else:
        print("  n=0")

    print("\n================= (C) DIVERGENCE — model-fav vs market-fav =================")
    if diverge:
        agree = [d for d in diverge if not d["is_divergent"]]
        disagree = [d for d in diverge if d["is_divergent"]]
        mwr = np.mean([d["model_fav_won"] for d in diverge])
        kwr = np.mean([d["mkt_fav_won"] for d in diverge])
        print(f"  all city-days n={len(diverge)}: model-fav WR={100*mwr:.1f}%  market-fav WR={100*kwr:.1f}%")
        print(f"  AGREE (model fav == market fav): n={len(agree)}  fav WR={100*np.mean([d['model_fav_won'] for d in agree]):.1f}%" if agree else "  AGREE: n=0")
        if disagree:
            dmwr = np.mean([d["model_fav_won"] for d in disagree])
            dkwr = np.mean([d["mkt_fav_won"] for d in disagree])
            print(f"  *** DIVERGENT (model fav != market fav): n={len(disagree)} ***")
            print(f"      model-pick WR={100*dmwr:.1f}%   market-pick WR={100*dkwr:.1f}%")
            print(f"      (this subset is the ONLY place a winner-ID edge can live)")
            # EV of buying the MODEL pick on divergent days
            dev = []
            for d in disagree:
                a = d["model_fav_ask"]
                if a is None or not (MIN_PX <= a <= MAX_PX):
                    continue
                fee = taker_fee_rate(a)
                dev.append((1 - a) - fee if d["model_fav_won"] else (-a - fee))
            if dev:
                print(f"      BUY YES model-pick on divergent days: n={len(dev)} "
                      f"meanEV={np.mean(dev):+.4f} total=${np.sum(dev):+.2f}")
            # FORENSIC: where does any positive EV come from? dump asks of winners vs losers
            dwin = [d["model_fav_ask"] for d in disagree if d["model_fav_won"] and d["model_fav_ask"] is not None]
            dlose = [d["model_fav_ask"] for d in disagree if not d["model_fav_won"] and d["model_fav_ask"] is not None]
            print(f"      FORENSIC divergent model-pick asks: WINNERS n={len(dwin)} "
                  f"asks={sorted(round(x,3) for x in dwin)}")
            print(f"        LOSERS n={len(dlose)} mean_ask={np.mean(dlose):.3f} "
                  f"(payout if you keep buying these = -ask each)")
            # ask-floor sensitivity on the divergent YES model-pick EV
            for floor in (0.02, 0.05, 0.10, 0.20):
                sub = [d for d in disagree if d["model_fav_ask"] is not None
                       and floor <= d["model_fav_ask"] <= MAX_PX]
                if sub:
                    ev = []
                    for d in sub:
                        a = d["model_fav_ask"]; fee = taker_fee_rate(a)
                        ev.append((1 - a) - fee if d["model_fav_won"] else (-a - fee))
                    print(f"        ask>= {floor:.2f}: n={len(sub)} WR={100*np.mean([d['model_fav_won'] for d in sub]):.0f}% "
                          f"meanEV={np.mean(ev):+.4f} total=${np.sum(ev):+.2f}")
        else:
            print("  DIVERGENT: n=0 (model favorite always == market favorite)")

    print("\n================= MARKET-FAVORITE EFFICIENCY BASELINE =================")
    if mkt_fav:
        priced = [r for r in mkt_fav if r["ask"] is not None]
        wr = np.mean([r["won"] for r in mkt_fav])
        avg_ask = np.mean([r["ask"] for r in priced]) if priced else None
        print(f"  n={len(mkt_fav)} market-fav realized WR={100*wr:.1f}%  avg implied price={avg_ask:.3f}")
        print(f"  efficiently priced iff WR ~= implied price (within sampling noise)")


if __name__ == "__main__":
    DECISION_KEYS = []
    main()
