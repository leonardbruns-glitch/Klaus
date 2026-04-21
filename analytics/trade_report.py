#!/usr/bin/env python3
"""Trade report — run from anywhere: python3 /root/Klaus/analytics/trade_report.py

Optional filter: --since "YYYY-MM-DD HH:MM"  (UTC)  [default: no filter]
"""
import json, datetime, os, sys
from collections import defaultdict

# Paths relative to project root, resolved from this file's location
_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_PATH = os.path.join(_ROOT, "logs", "trades.jsonl")
POST_PATH   = os.path.join(_ROOT, "logs", "post_exit.jsonl")

# ── --since filter ────────────────────────────────────────────────────────────
_since_ts = 0.0
_since_arg = None
for i, a in enumerate(sys.argv[1:]):
    if a == "--since" and i + 1 < len(sys.argv) - 1:
        _since_arg = sys.argv[i + 2]
        try:
            _since_ts = datetime.datetime.strptime(
                _since_arg, "%Y-%m-%d %H:%M"
            ).replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            print(f"[warn] bad --since '{_since_arg}', ignoring", file=sys.stderr)
            _since_ts = 0.0

with open(TRADES_PATH) as f:
    trades = [json.loads(l) for l in f if l.strip()]

if _since_ts > 0:
    trades = [t for t in trades
              if (t.get("ts_open", 0) or 0) >= _since_ts
              or (t.get("ts_close", 0) or 0) >= _since_ts]

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


# ── Aggregation footer ────────────────────────────────────────────────────────
def _fmt_pnl(v):
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"

def _outcome_bucket(r, net):
    r = (r or "").upper()
    if "TP_95" in r or "TP_99" in r or "BOND_TP" in r: return "TP"
    if "MOMENTUM_FAIL" in r:                             return "MOMENTUM_FAIL"
    if "LATE_EXHAUST" in r:                              return "LATE_EXHAUST"
    if "TIME_EXIT" in r:                                 return "TIME_EXIT"
    if "PRICE_SL" in r or "HARD_SL" in r:               return "HARD_SL"
    if "STOP_LOSS" in r or "_SL" in r:                   return "SL"
    if "EARLY_LOSS" in r:                                return "EARLY_LOSS"
    return "LOSS" if (net or 0) < 0 else "OTHER"

def _pct(vals, q):
    s = sorted(vals); n = len(s)
    return s[max(0, min(n - 1, int(q * n / 100)))] if n else 0.0

bond_trades = [t for t in trades if t.get("signal_source") == "BOND" or t.get("is_bond")]

if bond_trades:
    print("\n" + "=" * 78)
    print(f"BOND AGGREGATIONS  n={len(bond_trades)}"
          f"  since={_since_arg or 'all'}")
    print("=" * 78)

    # Overview
    total = sum((t.get("net_pnl", 0) or 0) for t in bond_trades)
    wins  = [t for t in bond_trades if (t.get("net_pnl", 0) or 0) > 0]
    loss  = [t for t in bond_trades if (t.get("net_pnl", 0) or 0) <= 0]
    wr    = len(wins) / len(bond_trades) * 100 if bond_trades else 0
    aw    = sum(t["net_pnl"] for t in wins) / len(wins) if wins else 0
    al    = sum(t["net_pnl"] for t in loss) / len(loss) if loss else 0
    pf    = (sum(t["net_pnl"] for t in wins)
             / max(0.01, abs(sum(t["net_pnl"] for t in loss)))) if loss else 0
    print(f"\n── OVERVIEW ────────────────────────────────────────────────────────────")
    print(f"  n={len(bond_trades)}  WR={wr:.1f}%  net={_fmt_pnl(total)}  "
          f"avg_win={_fmt_pnl(aw)}  avg_loss={_fmt_pnl(al)}  PF={pf:.2f}")

    # By exit bucket
    by_b: dict = defaultdict(list)
    for t in bond_trades:
        by_b[_outcome_bucket(t.get("exit_reason"), t.get("net_pnl", 0))].append(t["net_pnl"])
    print(f"\n── BY EXIT BUCKET ──────────────────────────────────────────────────────")
    for b in sorted(by_b, key=lambda k: sum(by_b[k]), reverse=True):
        v = by_b[b]
        w = sum(1 for x in v if x > 0)
        print(f"  {b:<16} n={len(v):>3}  WR={w/len(v)*100:>4.0f}%  "
              f"avg={_fmt_pnl(sum(v)/len(v))}  sum={_fmt_pnl(sum(v))}")

    # By entry class
    by_c: dict = defaultdict(list)
    for t in bond_trades:
        by_c[t.get("bond_entry_class", "?") or "?"].append(t["net_pnl"])
    print(f"\n── BY ENTRY CLASS ──────────────────────────────────────────────────────")
    for c in sorted(by_c, key=lambda k: sum(by_c[k]), reverse=True):
        v = by_c[c]
        w = sum(1 for x in v if x > 0)
        print(f"  {c:<30} n={len(v):>3}  WR={w/len(v)*100:>4.0f}%  "
              f"avg={_fmt_pnl(sum(v)/len(v))}  sum={_fmt_pnl(sum(v))}")

    # By path class (if any labels exist)
    by_p: dict = defaultdict(list)
    for t in bond_trades:
        pc = t.get("path_class", "") or "UNLABELED"
        by_p[pc].append(t["net_pnl"])
    if len(by_p) > 1:
        print(f"\n── BY PATH CLASS ───────────────────────────────────────────────────────")
        for p in sorted(by_p, key=lambda k: sum(by_p[k]), reverse=True):
            v = by_p[p]
            w = sum(1 for x in v if x > 0)
            print(f"  {p:<20} n={len(v):>3}  WR={w/len(v)*100:>4.0f}%  "
                  f"avg={_fmt_pnl(sum(v)/len(v))}  sum={_fmt_pnl(sum(v))}")

    # SL signature decomposition (ZOMBIE / FLASH / COLLAPSE)
    # Classify every losing-bucket trade by how much upside it ever saw.
    # ZOMBIE   = fav ≤ 0%    — never profitable → entry filter
    # FLASH    = fav 0%–5%   — brief flicker → micro-structure filter
    # COLLAPSE = fav > 5%    — was profitable → trailing-stop / peel logic
    sl_trades = [t for t in bond_trades
                 if _outcome_bucket(t.get("exit_reason"), t.get("net_pnl", 0))
                 in ("HARD_SL", "SL", "EARLY_LOSS", "LATE_EXHAUST", "MOMENTUM_FAIL")]
    if sl_trades:
        sigs: dict = defaultdict(list)
        for t in sl_trades:
            fav = float(t.get("max_favourable_pct", 0) or 0)
            sig = "ZOMBIE" if fav <= 0.0 else ("FLASH" if fav <= 5.0 else "COLLAPSE")
            sigs[sig].append(t)
        print(f"\n── SL SIGNATURE (max_favourable_pct) ───────────────────────────────────")
        for sig in ("ZOMBIE", "FLASH", "COLLAPSE"):
            rows = sigs.get(sig, [])
            if not rows:
                continue
            pnls = [t["net_pnl"] for t in rows]
            favs = [float(t.get("max_favourable_pct", 0) or 0) for t in rows]
            advs = [float(t.get("max_adverse_pct", 0) or 0) for t in rows]
            hint = {"ZOMBIE":   "→ entry filter (never had upside)",
                    "FLASH":    "→ entry micro-structure (bad timing)",
                    "COLLAPSE": "→ exit/trailing logic (gave back profit)"}[sig]
            print(f"  {sig:<9} n={len(rows):>3}  sum={_fmt_pnl(sum(pnls))}  "
                  f"avg_fav={sum(favs)/len(favs):+.1f}%  "
                  f"avg_adv={sum(advs)/len(advs):+.1f}%  {hint}")

    # Winner vs loser distribution
    def _row(label, w_vals, l_vals, fmt="+.2f"):
        if not w_vals or not l_vals:
            return
        print(f"  {label:<24}  "
              f"W[p25/p50/p75]={_pct(w_vals,25):{fmt}}/{_pct(w_vals,50):{fmt}}/{_pct(w_vals,75):{fmt}}  "
              f"L[p25/p50/p75]={_pct(l_vals,25):{fmt}}/{_pct(l_vals,50):{fmt}}/{_pct(l_vals,75):{fmt}}")

    if wins and loss:
        print(f"\n── WINNER vs LOSER DISTRIBUTION ────────────────────────────────────────")
        for label, key, fmt in [
            ("entry_price",           "entry_price",            ".3f"),
            ("max_favourable_pct",    "max_favourable_pct",     "+.1f"),
            ("max_adverse_pct",       "max_adverse_pct",        "+.1f"),
            ("hold_seconds",          "hold_seconds",           ".0f"),
            ("velocity_5s_pct",       "velocity_5s_pct",        "+.3f"),
            ("bond_delta_penalty",    "bond_delta_penalty",     ".3f"),
            ("bond_weak_vel_penalty", "bond_weak_vel_penalty",  ".3f"),
            ("entry_snap_30s_pct",    "entry_snap_30s_pct",     "+.1f"),
            ("entry_snap_60s_pct",    "entry_snap_60s_pct",     "+.1f"),
        ]:
            _row(label,
                 [float(t.get(key, 0) or 0) for t in wins],
                 [float(t.get(key, 0) or 0) for t in loss],
                 fmt)
        # Newly added raw primitives — only non-zero for post-fix trades
        new_w = [t for t in wins if float(t.get("bond_adj_edge_at_entry", 0) or 0) != 0]
        new_l = [t for t in loss if float(t.get("bond_adj_edge_at_entry", 0) or 0) != 0]
        if new_w and new_l:
            print(f"  ─ raw entry primitives (post-fix trades only, n_w={len(new_w)} n_l={len(new_l)}) ─")
            _row("bond_adj_edge_at_entry",
                 [float(t.get("bond_adj_edge_at_entry", 0) or 0) for t in new_w],
                 [float(t.get("bond_adj_edge_at_entry", 0) or 0) for t in new_l], ".3f")
            _row("bond_delta_at_entry",
                 [float(t.get("bond_delta_at_entry", 0) or 0) for t in new_w],
                 [float(t.get("bond_delta_at_entry", 0) or 0) for t in new_l], "+.3f")
            _row("bond_vel_at_entry",
                 [float(t.get("bond_vel_at_entry", 0) or 0) for t in new_w],
                 [float(t.get("bond_vel_at_entry", 0) or 0) for t in new_l], ".3f")
