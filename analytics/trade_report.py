#!/usr/bin/env python3
"""Trade report — run from anywhere: python3 /root/Klaus/analytics/trade_report.py"""
import json, datetime, os, sys

# Paths relative to project root, resolved from this file's location
_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_PATH = os.path.join(_ROOT, "logs", "trades.jsonl")
POST_PATH   = os.path.join(_ROOT, "logs", "post_exit.jsonl")

with open(TRADES_PATH) as f:
    trades = [json.loads(l) for l in f if l.strip()]

post = {}
if os.path.exists(POST_PATH):
    with open(POST_PATH) as f:
        for l in f:
            if l.strip():
                r = json.loads(l)
                tid = r.get("trade_id", "")
                if tid and r.get("record_type") != "resolution":
                    post[tid] = r

def g(t, k, d=None):
    return t.get(k, d)

def pf(v, fmt="+.3f", unit="", dash="\u2014"):
    if v in (None, "", 0.0):
        return dash
    try:
        return f"{v:{fmt}}{unit}"
    except Exception:
        return str(v)

def ps(v, dash="\u2014"):
    return f"{v:.0f}s" if v not in (None, 0.0) else dash

def pb(v):
    if v is None:
        return "?"
    return "Y" if v else "N"

def pd(v, dash="\u2014"):
    return f"{v:+.1f}%" if v is not None else dash

GREEN  = "\033[32m"
RED    = "\033[31m"
RESET  = "\033[0m"

for t in trades:
    pnl  = g(t, "net_pnl", 0.0) or 0.0
    win  = (GREEN + "W" + RESET) if pnl > 0 else (RED + "L" + RESET if pnl < 0 else "-")
    ws   = g(t, "window_size_s", 0)
    wl   = f"{ws//60}m" if ws else "?m"
    hc   = "*" if g(t, "heat_check_active") else ""
    ts   = g(t, "ts_open", 0)
    dt   = datetime.datetime.utcfromtimestamp(ts).strftime("%m-%d %H:%M") if ts else "\u2014\u2014\u2014\u2014\u2014\u2014"
    adv  = g(t, "max_adverse_pct")
    fav  = g(t, "max_favourable_pct")
    t_fav = g(t, "t_fav_s")
    t_adv = g(t, "t_adv_s")
    src  = (g(t, "signal_source", "?") or "?")[:3]
    dr   = g(t, "direction", "") or ""
    dr_s = "NO" if "NO" in dr else "YES"
    asset = g(t, "asset", "?")

    pe   = post.get(g(t, "trade_id", ""), {})
    mfe  = pe.get("move_from_exit_pct", {})
    d30  = pd(mfe.get("t30s"))
    d60  = pd(mfe.get("t60s"))
    d120 = pd(mfe.get("t120s"))
    mfn  = pe.get("move_from_entry_pct", {})
    e30  = pd(mfn.get("t30s"))
    e60  = pd(mfn.get("t60s"))
    e120 = pd(mfn.get("t120s"))
    ec_raw = g(t, "entered_correctly")
    ec2  = pb(pe.get("entered_correctly", ec_raw))

    ep   = g(t, "entry_price", 0) or 0.0
    xp   = g(t, "exit_price", 0) or 0.0
    fv   = g(t, "sniper_fair_value")
    edge = g(t, "sniper_edge")
    lag  = g(t, "sniper_lag_remaining")
    delt = g(t, "sniper_delta_pct")
    elap = g(t, "sniper_elapsed_pct")
    qs   = g(t, "quality_score", "\u2014")
    vpin = g(t, "sniper_vpin")
    reg  = g(t, "regime", "\u2014") or "\u2014"
    hr   = g(t, "hour_utc", 0)
    hold = g(t, "hold_seconds", 0) or 0
    slip_e = g(t, "slippage_entry")
    slip_x = g(t, "slippage_exit")
    llm  = g(t, "sniper_llm_boost")
    cwin = g(t, "consecutive_wins_at_entry", 0)
    stake = g(t, "stake", 0) or 0.0
    fee  = g(t, "fee_paid", 0) or 0.0
    gross = g(t, "gross_pnl")
    cap  = g(t, "capital_after", 0) or 0.0
    reason = g(t, "exit_reason", "?")
    vel  = g(t, "velocity_5s_pct")   # % Binance price change in last 5s at entry
    age  = g(t, "move_age_s")        # seconds since last >0.02% Binance tick
    bec  = g(t, "bond_entry_class", "") or ""   # e.g. "CORE/hot", "IMPULSE/hot"

    print(
        f"{win}{hc} {dt} {asset:<3} {dr_s} {wl} {src} | "
        f"ep={ep:.4f} xp={xp:.4f} | "
        f"fv={pf(fv, ',.4f')} edge={pf(edge, '+.3f')} | "
        f"lag={pf(lag, '.2f')} delta={pf(delt, '+.3f')} elap={pf(elap, '.2f')} | "
        f"qs={qs} vpin={pf(vpin, '.2f')} regime={reg:<11} zone={bec or '—':<12} | "
        f"hr={hr:02d} hold={hold:.0f}s | "
        f"adv={pf(adv, '+.1f', '%')}@{ps(t_adv)} fav={pf(fav, '+.1f', '%')}@{ps(t_fav)} | "
        f"from_exit: +30s={d30} +60s={d60} +120s={d120} | from_entry: +30s={e30} +60s={e60} +120s={e120} ec={ec2} | "
        f"slip_e={pf(slip_e, '+.4f')} slip_x={pf(slip_x, '+.4f')} | "
        f"llm={pf(llm, '+.2f')} cwin={cwin} | "
        f"vel={pf(vel, '+.3f', '%')} age={'cold' if age is None or age >= 999 else f'{age:.0f}s'} | "
        f"stake=${stake:.2f} fee=${fee:.3f} gross={pf(gross, '+.3f', '$')} net={pnl:+.3f} cap=${cap:.2f} | "
        f"{reason}"
    )
