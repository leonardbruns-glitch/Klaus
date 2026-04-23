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
post_res = {}
if os.path.exists(POST_PATH):
    with open(POST_PATH) as f:
        for l in f:
            if l.strip():
                r = json.loads(l)
                tid = r.get("trade_id", "")
                if not tid:
                    continue
                if r.get("record_type") == "resolution":
                    post_res[tid] = r   # window-end resolution record
                else:
                    post[tid] = r       # T+30s/60s/120s record

def g(t, k, d=None):
    return t.get(k, d)

def pf(v, fmt="+.3f", unit="", dash="—"):
    if v in (None, "", 0.0):
        return dash
    try:
        return f"{v:{fmt}}{unit}"
    except Exception:
        return str(v)

def ps(v, dash="—"):
    return f"{v:.0f}s" if v not in (None, 0.0) else dash

def pb(v):
    if v is None:
        return "?"
    return "Y" if v else "N"

def pd(v, dash="—"):
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
    dt   = datetime.datetime.utcfromtimestamp(ts).strftime("%m-%d %H:%M") if ts else "——————"
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
    _res = post_res.get(g(t, "trade_id", ""), {})
    ec_raw = _res.get("entered_correctly", g(t, "entered_correctly"))
    ec2  = pb(ec_raw)
    wop  = _res.get("window_outcome_price")   # price at window_end+60s
    wmax_adv = _res.get("window_max_adv_from_entry_pct")  # post-exit max adverse

    ep   = g(t, "entry_price", 0) or 0.0
    xp   = g(t, "exit_price", 0) or 0.0
    fv   = g(t, "sniper_fair_value")
    edge = g(t, "sniper_edge")
    lag  = g(t, "sniper_lag_remaining")
    delt = g(t, "sniper_delta_pct")
    elap = g(t, "sniper_elapsed_pct")
    qs   = g(t, "quality_score", "—")
    vpin = g(t, "sniper_vpin")
    reg  = g(t, "regime", "—") or "—"
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
    vel  = g(t, "velocity_5s_pct")
    age  = g(t, "move_age_s")
    bec  = g(t, "bond_entry_class", "") or ""
    mac  = (g(t, "bond_macro_regime", "") or "")[:8]   # TREND_UP / TREND_DOWN / CHOP
    pc   = (g(t, "path_class", "") or "")[:12]         # SMOOTH_RUNNER / EARLY_CHOP / DEAD_DRIFT
    b10  = g(t, "mae_bounce_10s_pct")                  # bounce within 10s of MAE (% of entry)
    stab = (g(t, "bond_stab_class", "") or "")[:9]     # CLEAN / NOISY / HIGH_RISK / FATAL
    sscore = g(t, "bond_stability_score", 0) or 0
    # Pre-entry trajectory (what the market was doing for the 30s before entry)
    daccel30 = g(t, "bond_delta_accel_30s")
    edrift30 = g(t, "bond_edge_drift_30s")
    aclsust  = g(t, "bond_accel_sustained")
    has_hist = g(t, "bond_has_hist")

    print(
        f"{win}{hc} {dt} {asset:<3} {dr_s} {wl} {src} | "
        f"ep={ep:.4f} xp={xp:.4f} | "
        f"fv={pf(fv, ',.4f')} edge={pf(edge, '+.3f')} | "
        f"lag={pf(lag, '.2f')} delta={pf(delt, '+.3f')} elap={pf(elap, '.2f')} | "
        f"qs={qs} vpin={pf(vpin, '.2f')} regime={reg:<11} zone={bec or '—':<12} mac={mac or '—':<9} pc={pc or '—'} stab={(stab or '—'):<9}/{sscore} | "
        f"pre30: daccel={pf(daccel30, '+.3f')} edrift={pf(edrift30, '+.4f')} sust={'T' if aclsust else 'F' if aclsust is False else '—'} hist={'T' if has_hist else 'F' if has_hist is False else '—'} | "
        f"hr={hr:02d} hold={hold:.0f}s | "
        f"adv={pf(adv, '+.1f', '%')}@{ps(t_adv)} fav={pf(fav, '+.1f', '%')}@{ps(t_fav)} bounce10={pf(b10, '+.1f', '%')} | "
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
    pf_   = (sum(t["net_pnl"] for t in wins)
             / max(0.01, abs(sum(t["net_pnl"] for t in loss)))) if loss else 0
    print(f"\n── OVERVIEW ────────────────────────────────────────────────────────────")
    print(f"  n={len(bond_trades)}  WR={wr:.1f}%  net={_fmt_pnl(total)}  "
          f"avg_win={_fmt_pnl(aw)}  avg_loss={_fmt_pnl(al)}  PF={pf_:.2f}")

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

    # By macro regime
    by_mac: dict = defaultdict(list)
    for t in bond_trades:
        by_mac[t.get("bond_macro_regime", "?") or "?"].append(t["net_pnl"])
    if len(by_mac) > 1 or (len(by_mac) == 1 and "?" not in by_mac):
        print(f"\n── BY MACRO REGIME ─────────────────────────────────────────────────────")
        for m in sorted(by_mac, key=lambda k: sum(by_mac[k]), reverse=True):
            v = by_mac[m]
            w = sum(1 for x in v if x > 0)
            print(f"  {m:<12} n={len(v):>3}  WR={w/len(v)*100:>4.0f}%  "
                  f"avg={_fmt_pnl(sum(v)/len(v))}  sum={_fmt_pnl(sum(v))}")

    # By BOND_STAB class (pre-entry quality → stake modulation)
    by_stab: dict = defaultdict(list)
    for t in bond_trades:
        by_stab[t.get("bond_stab_class", "?") or "?"].append(t["net_pnl"])
    if len(by_stab) > 1 or (len(by_stab) == 1 and "?" not in by_stab):
        print(f"\n── BY STAB CLASS ───────────────────────────────────────────────────────")
        _order = {"CLEAN": 0, "NOISY": 1, "HIGH_RISK": 2, "FATAL": 3, "?": 9}
        for s in sorted(by_stab, key=lambda k: _order.get(k, 9)):
            v = by_stab[s]
            w = sum(1 for x in v if x > 0)
            print(f"  {s:<11} n={len(v):>3}  WR={w/len(v)*100:>4.0f}%  "
                  f"avg={_fmt_pnl(sum(v)/len(v))}  sum={_fmt_pnl(sum(v))}")

    # By individual stab flag (frequency + PnL attribution)
    _flags = ("bond_stab_xp_bad", "bond_stab_slip_bad", "bond_stab_delta_bad",
              "bond_stab_edge_weak", "bond_stab_vel_flat")
    _flag_any = any(any(t.get(f) for f in _flags) for t in bond_trades)
    if _flag_any:
        print(f"\n── BY STAB FLAG (trades where flag=True) ───────────────────────────────")
        for f in _flags:
            vs = [t["net_pnl"] for t in bond_trades if t.get(f)]
            if not vs:
                continue
            w = sum(1 for x in vs if x > 0)
            label = f.replace("bond_stab_", "").replace("_", " ")
            print(f"  {label:<11} n={len(vs):>3}  WR={w/len(vs)*100:>4.0f}%  "
                  f"avg={_fmt_pnl(sum(vs)/len(vs))}  sum={_fmt_pnl(sum(vs))}")

    # ── Pre-entry trajectory analysis ──────────────────────────────────────
    _traj_trades = [t for t in bond_trades if "bond_delta_accel_30s" in t]
    if _traj_trades:
        def _split(pred, label_t, label_f):
            t_yes = [t["net_pnl"] for t in _traj_trades if pred(t)]
            t_no  = [t["net_pnl"] for t in _traj_trades if not pred(t)]
            for lbl, v in ((label_t, t_yes), (label_f, t_no)):
                if not v:
                    continue
                w = sum(1 for x in v if x > 0)
                print(f"  {lbl:<28} n={len(v):>3}  WR={w/len(v)*100:>4.0f}%  "
                      f"avg={_fmt_pnl(sum(v)/len(v))}  sum={_fmt_pnl(sum(v))}")

        print(f"\n── BY PRE-ENTRY TRAJECTORY ─────────────────────────────────────────────")

        # Delta acceleration (30s): building vs flat vs decaying toward trade direction
        # Aligned: for UP tokens, positive daccel is good; for DOWN tokens, negative is good.
        def _daccel_aligned(t):
            da = t.get("bond_delta_accel_30s", 0) or 0
            is_up = "YES" in (t.get("direction") or "")  # proxy — YES-of-UP tokens
            # Use bond_delta direction: if delta and token agree, accel aligned means
            # accel in same sign as delta. Approximation: treat sign of macro regime.
            mac = t.get("bond_macro_regime", "")
            if mac == "TREND_UP":   return da > 0.01
            if mac == "TREND_DOWN": return da < -0.01
            return abs(da) > 0.01

        _split(_daccel_aligned,
               "daccel aligned (|>0.01|)", "daccel flat/against")

        # Edge drift: rising vs falling vs flat
        _split(lambda t: (t.get("bond_edge_drift_30s", 0) or 0) > 0.003,
               "edge rising (drift>0.003)", "edge flat/falling")

        # Sustained acceleration (15s AND 30s both positive)
        _split(lambda t: bool(t.get("bond_accel_sustained")),
               "accel_sustained", "not sustained")

        # Has 30s history at entry
        _split(lambda t: bool(t.get("bond_has_hist")),
               "has_hist (≥30s)", "no_hist (cold start)")

        # Delta acceleration buckets — magnitude-based
        print(f"\n── BY DELTA_ACCEL_30s BUCKET ───────────────────────────────────────────")
        buckets = [(-99, -0.03, "<-0.03 (decaying)"),
                   (-0.03, -0.01, "-0.03 to -0.01"),
                   (-0.01, 0.01, "|<0.01| (flat)"),
                   (0.01, 0.03, "+0.01 to +0.03"),
                   (0.03, 99, ">+0.03 (building)")]
        for lo, hi, lbl in buckets:
            v = [t["net_pnl"] for t in _traj_trades
                 if lo <= (t.get("bond_delta_accel_30s", 0) or 0) < hi]
            if not v:
                continue
            w = sum(1 for x in v if x > 0)
            print(f"  {lbl:<22} n={len(v):>3}  WR={w/len(v)*100:>4.0f}%  "
                  f"avg={_fmt_pnl(sum(v)/len(v))}  sum={_fmt_pnl(sum(v))}")

        # ── pre_score (Layer 1, observation mode) ──────────────────────────
        # Strict integrity gates BEFORE any aggregation:
        #   1. exclude FAIL validity records (causality leakage)
        #   2. group by schema_hash — never mix scores from different schemas
        #
        # Phase B trigger: PER-BUCKET (regime, zone) monotonic ordering with
        # n ≥ 50, stable across 2 consecutive recomputes. Global monotonicity
        # is unreliable because regime mix is non-stationary.
        _ps_all = [t for t in bond_trades if t.get("pre_score_version")]
        if _ps_all:
            n_pass = sum(1 for t in _ps_all if (t.get("pre_score_validity") or "").startswith("PASS"))
            n_fail = len(_ps_all) - n_pass
            _hashes: dict = {}
            for t in _ps_all:
                h = t.get("pre_score_schema_hash", "?") or "?"
                _hashes.setdefault(h, []).append(t)

            print(f"\n── PRE_SCORE INTEGRITY ────────────────────────────────────────────────")
            print(f"  total scored: {len(_ps_all)}  PASS: {n_pass}  FAIL: {n_fail}")
            for h, rows in sorted(_hashes.items(), key=lambda kv: -len(kv[1])):
                vers = sorted({(r.get("pre_score_version") or "?") for r in rows})
                print(f"  schema_hash={h}  n={len(rows)}  versions={','.join(vers)}")
            if len(_hashes) > 1:
                print(f"  ⚠ MULTIPLE SCHEMA HASHES — scores NOT comparable across hashes")

            # Aggregate only PASS records, only the dominant schema hash
            _dom_hash = max(_hashes.items(), key=lambda kv: len(kv[1]))[0] if _hashes else None
            _ps_trades = [t for t in _ps_all
                          if (t.get("pre_score_validity") or "").startswith("PASS")
                          and (t.get("pre_score_schema_hash", "?") or "?") == _dom_hash]

            if _ps_trades:
                print(f"\n── BY PRE_SCORE (n={len(_ps_trades)}, schema={_dom_hash}, PASS only) ──")
                ps_buckets = [(-99, -1.0, "<-1.0  (very weak)"),
                              (-1.0,  0.0, "-1.0 to 0.0"),
                              ( 0.0,  1.0, "0.0 to 1.0"),
                              ( 1.0,  2.0, "1.0 to 2.0"),
                              ( 2.0,  3.0, "2.0 to 3.0"),
                              ( 3.0, 99,   ">3.0  (very strong)")]
                for lo, hi, lbl in ps_buckets:
                    v = [t["net_pnl"] for t in _ps_trades
                         if lo <= (t.get("pre_score", 0) or 0) < hi]
                    if not v:
                        continue
                    w = sum(1 for x in v if x > 0)
                    print(f"  {lbl:<22} n={len(v):>3}  WR={w/len(v)*100:>4.0f}%  "
                          f"avg={_fmt_pnl(sum(v)/len(v))}  sum={_fmt_pnl(sum(v))}")
                print(f"  NOTE: global ordering NOT a Phase B trigger (regime mix is non-stationary)")

                # Per (regime, zone) — Phase B readiness check
                print(f"\n── PHASE B READINESS — per (REGIME, ZONE) bucket ──────────────────────")
                print(f"  Trigger: n≥50  AND  top-tercile WR > bottom-tercile WR by ≥5pp")
                from collections import defaultdict as _dd
                ps_groups: dict = _dd(list)
                for t in _ps_trades:
                    key = (t.get("bond_macro_regime", "?") or "?",
                           t.get("bond_entry_zone", "?") or "?")
                    ps_groups[key].append(t)
                for (mr, zn), rows in sorted(ps_groups.items(),
                                              key=lambda kv: -len(kv[1])):
                    scores = [t.get("pre_score", 0) or 0 for t in rows]
                    rows_sorted = sorted(rows, key=lambda t: t.get("pre_score", 0) or 0)
                    n = len(rows_sorted)
                    if n >= 9:
                        bot = rows_sorted[: n // 3]
                        top = rows_sorted[-(n // 3):]
                        wr_bot = sum(1 for t in bot if t["net_pnl"] > 0) / len(bot) * 100
                        wr_top = sum(1 for t in top if t["net_pnl"] > 0) / len(top) * 100
                        gap = wr_top - wr_bot
                        gap_str = f"top_wr={wr_top:>4.0f}% bot_wr={wr_bot:>4.0f}% Δ={gap:+5.1f}pp"
                    else:
                        gap, gap_str = 0.0, "(need n≥9 for terciles)"
                    if n >= 50 and gap >= 5.0:
                        ready = "✓ PHASE_B_READY"
                    elif n < 50:
                        ready = f"need {50 - n} more trades"
                    else:
                        ready = f"n=ok but Δ<5pp (gap={gap:+.1f}pp)"
                    print(f"  ({mr:<11}, {zn:<5}) n={n:>3}  {gap_str}  → {ready}")

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

    # MAE > 40% bounce cohort: reversal vs collapse discriminator
    # bounce_10s = max price recovery within 10s after MAE, as % of entry.
    # REVERSAL  = bounce ≥ 5% of entry  → price snapped back quickly
    # COLLAPSE  = bounce < 5% of entry  → price kept falling (real breakdown)
    # Only trades with mae_bounce_10s_pct populated (post-fix deployments).
    mae40 = [t for t in bond_trades
             if float(t.get("max_adverse_pct", 0) or 0) >= 40.0
             and float(t.get("mae_bounce_10s_pct", 0) or 0) > 0]
    if mae40:
        print(f"\n── MAE>40% BOUNCE COHORT (reversal vs collapse, n={len(mae40)}) ─────────")
        rev = [t for t in mae40 if float(t.get("mae_bounce_10s_pct", 0) or 0) >= 5.0]
        col = [t for t in mae40 if float(t.get("mae_bounce_10s_pct", 0) or 0) < 5.0]
        for label, rows in [("REVERSAL (bounce≥5%)", rev), ("COLLAPSE (bounce<5%)", col)]:
            if not rows:
                continue
            pnls  = [(t.get("net_pnl", 0) or 0) for t in rows]
            advs  = [float(t.get("max_adverse_pct",  0) or 0) for t in rows]
            b10s  = [float(t.get("mae_bounce_10s_pct", 0) or 0) for t in rows]
            w     = sum(1 for x in pnls if x > 0)
            print(f"  {label:<22} n={len(rows):>3}  WR={w/len(rows)*100:>4.0f}%  "
                  f"sum={_fmt_pnl(sum(pnls))}  "
                  f"avg_adv={sum(advs)/len(advs):+.1f}%  "
                  f"avg_bounce={sum(b10s)/len(b10s):+.1f}%")
    elif any(float(t.get("max_adverse_pct", 0) or 0) >= 40.0 for t in bond_trades):
        print(f"\n── MAE>40% BOUNCE COHORT ───────────────────────────────────────────────")
        print(f"  (no bounce data yet — will populate after next deploy)")

    # ── Window resolution outcome ─────────────────────────────────────────────
    # Did the market move in our direction from entry to window close?
    # Measures the TRUE edge — independent of our exit timing.
    # Source: post_exit.jsonl resolution records (sampled at window_end + 60s).
    _res_trades = [(t, post_res.get(t.get("trade_id", ""), {})) for t in bond_trades]
    _res_known   = [(t, r) for t, r in _res_trades if r.get("entered_correctly") is not None]
    if _res_known:
        _n_res = len(_res_known)
        _n_correct   = sum(1 for _, r in _res_known if r["entered_correctly"])
        _n_incorrect = _n_res - _n_correct
        _correct_pnls   = [t["net_pnl"] for t, r in _res_known if r["entered_correctly"]]
        _incorrect_pnls = [t["net_pnl"] for t, r in _res_known if not r["entered_correctly"]]
        # Direction labels: for DOWN tokens (outcome_direction="down"), the YES token
        # resolves to 1.0 when the underlying goes DOWN. entered_correctly=True means
        # the underlying went in the direction we bet on (DOWN for DOWN tokens, UP for UP).
        # "Resolved for us" = underlying went our way = token at ~1.0 at window_end+60s.
        # "Resolved against" = underlying went against our bet = token at ~0.0.
        print(f"\n── WINDOW RESOLUTION (n={_n_res} with resolution data) ─────────────────")
        print(f"  Key: 'for us' = underlying went in bet direction (token→1.0 at window_end+60s)")
        print(f"       'against' = underlying went opposite (token→0.0); direction check uses final price")
        print(f"  Resolved FOR us:   n={_n_correct:>3}  "
              f"({_n_correct/_n_res*100:.0f}%)  "
              f"{'avg='+_fmt_pnl(sum(_correct_pnls)/_n_correct) if _correct_pnls else ''}  "
              f"{'sum='+_fmt_pnl(sum(_correct_pnls)) if _correct_pnls else ''}")
        print(f"  Resolved AGAINST:  n={_n_incorrect:>3}  "
              f"({_n_incorrect/_n_res*100:.0f}%)  "
              f"{'avg='+_fmt_pnl(sum(_incorrect_pnls)/_n_incorrect) if _incorrect_pnls else ''}  "
              f"{'sum='+_fmt_pnl(sum(_incorrect_pnls)) if _incorrect_pnls else ''}")

        # Exit vs resolution disagreements — these are the interesting cases
        _wl_but_wrong = [(t, r) for t, r in _res_known
                         if t["net_pnl"] > 0 and not r["entered_correctly"]]
        _ll_but_right = [(t, r) for t, r in _res_known
                         if t["net_pnl"] <= 0 and r["entered_correctly"]]
        if _wl_but_wrong:
            print(f"  ⚠ WON trade but market resolved AGAINST: n={len(_wl_but_wrong)} "
                  f"(sold before resolution flip?)")
        if _ll_but_right:
            print(f"  ⚠ LOST trade but market resolved FOR us: n={len(_ll_but_right)} "
                  f"(premature stop / wick eviction)")
        if _ll_but_right:
            pnls_ll = [t["net_pnl"] for t, _ in _ll_but_right]
            reasons = [t.get("exit_reason", "?") for t, _ in _ll_but_right]
            print(f"    Reasons: {', '.join(sorted(set(reasons)))}  "
                  f"total_loss={_fmt_pnl(sum(pnls_ll))}")

        # ── SL EFFECTIVENESS DIAGNOSTIC ──────────────────────────────────────
        # For every SL exit, did the window ultimately resolve FOR or AGAINST us?
        #   GOOD_SL:  SL triggered AND window resolved against us
        #             → entry was wrong, SL correctly preserved capital
        #   BAD_SL:   SL triggered AND window resolved for us
        #             → premature stop, wick eviction, stop-hunt success
        #             the entry was right, the stop was wrong
        # Ratio GOOD/BAD is the diagnostic: >0.70 = SL useful, <0.40 = SL costs more than it saves.
        _sl_res = [(t, r) for t, r in _res_known
                   if _outcome_bucket(t.get("exit_reason"), t.get("net_pnl", 0))
                   in ("HARD_SL", "SL", "EARLY_LOSS", "MOMENTUM_FAIL")]
        if _sl_res:
            # PRIMARY check: underlying direction at final window resolution
            #   GOOD_SL = stopped AND underlying ultimately went against our bet (final token ~0.0)
            #   BAD_SL  = stopped BUT underlying ultimately went our way (final token ~1.0)
            good_sl = [(t, r) for t, r in _sl_res if not r["entered_correctly"]]
            bad_sl  = [(t, r) for t, r in _sl_res if r["entered_correctly"]]
            # SECONDARY check: did the price ever recover post-exit above entry?
            # This catches "wick SLs" where token briefly recovered but then resolved against us.
            # Uses window_max_fav_from_entry_pct — best post-exit price vs entry price.
            # Positive = price recovered above entry at some point after our SL.
            _recoverable = [(t, r) for t, r in _sl_res
                            if (r.get("window_max_fav_from_entry_pct") or 0) > 0
                            and not r["entered_correctly"]]  # final outcome still against us
            n_sl = len(_sl_res)
            _good_ratio = len(good_sl) / n_sl if n_sl else 0.0
            _verdict = (
                "SL useful (preserves capital)" if _good_ratio >= 0.70 else
                "SL marginal — review thresholds" if _good_ratio >= 0.40 else
                "SL COSTLY — premature stops > saves"
            )
            print(f"\n── SL EFFECTIVENESS (n={n_sl} SL exits with resolution) ──────────────")
            print(f"  GOOD_SL (stopped AND resolved against):  n={len(good_sl):>3}  "
                  f"({_good_ratio*100:.0f}%)  "
                  f"sum={_fmt_pnl(sum(t['net_pnl'] for t, _ in good_sl))}")
            print(f"  BAD_SL  (stopped BUT resolved for us):   n={len(bad_sl):>3}  "
                  f"({(1 - _good_ratio)*100:.0f}%)  "
                  f"sum={_fmt_pnl(sum(t['net_pnl'] for t, _ in bad_sl))}  "
                  f"← underlying went our way at window end")
            if _recoverable:
                _rec_fav = [r.get("window_max_fav_from_entry_pct", 0) for _, r in _recoverable]
                print(f"  WICK_SL  (stopped, recovered post-exit, but final resolved against): "
                      f"n={len(_recoverable)}  avg_best_recovery={sum(_rec_fav)/len(_rec_fav):+.1f}%  "
                      f"← stop-hunt candidates (price did bounce, just didn't hold)")
            print(f"  Verdict: {_verdict}")
            # Per exit_reason breakdown — which SL flavor is the worst offender?
            _by_reason: dict = defaultdict(lambda: {"good": 0, "bad": 0, "bad_pnl": 0.0})
            for t, r in _sl_res:
                k = t.get("exit_reason", "?")
                if r["entered_correctly"]:
                    _by_reason[k]["bad"] += 1
                    _by_reason[k]["bad_pnl"] += t["net_pnl"]
                else:
                    _by_reason[k]["good"] += 1
            if len(_by_reason) > 1:
                print(f"  ── by exit_reason ───")
                for reason in sorted(_by_reason, key=lambda k: -_by_reason[k]["bad"]):
                    d = _by_reason[reason]
                    n_r = d["good"] + d["bad"]
                    ratio = d["good"] / n_r if n_r else 0
                    print(f"    {reason:<22} n={n_r:>2} good={d['good']:>2} bad={d['bad']:>2} "
                          f"({ratio*100:>3.0f}% good)  bad_sum={_fmt_pnl(d['bad_pnl'])}")

        # Window max adverse post-exit (how bad did it get after we left?)
        _wmax_known = [(t, r) for t, r in _res_known
                       if r.get("window_max_adv_from_entry_pct") is not None]
        if _wmax_known:
            wmax_vals = [r["window_max_adv_from_entry_pct"] for _, r in _wmax_known]
            winners   = [r["window_max_adv_from_entry_pct"] for t, r in _wmax_known
                         if t["net_pnl"] > 0]
            losers    = [r["window_max_adv_from_entry_pct"] for t, r in _wmax_known
                         if t["net_pnl"] <= 0]
            print(f"  Max adverse through window_end (n={len(_wmax_known)}):")
            if winners:
                print(f"    Winners: avg={sum(winners)/len(winners):+.1f}%  "
                      f"p50={sorted(winners)[len(winners)//2]:+.1f}%  "
                      f"p75={sorted(winners)[int(len(winners)*0.75)]:+.1f}%")
            if losers:
                print(f"    Losers:  avg={sum(losers)/len(losers):+.1f}%  "
                      f"p50={sorted(losers)[len(losers)//2]:+.1f}%  "
                      f"p75={sorted(losers)[int(len(losers)*0.75)]:+.1f}%")
    else:
        n_pending = sum(1 for t in bond_trades
                        if t.get("window_end_ts", 0) and t.get("trade_id")
                        and t["trade_id"] not in post_res)
        print(f"\n── WINDOW RESOLUTION ───────────────────────────────────────────────────")
        print(f"  No resolution data yet. "
              f"{n_pending} trade(s) pending (resolution sampled at window_end+60s).")

    # Winner vs loser distribution
    #
    # Some fields were added after many BOND trades were recorded (e.g. MFE/MAE
    # mirror 215af00, mae_bounce_10s_pct 1c350fa). Those trades have the field
    # as 0 in the log — which means "not measured", not "actually zero".
    # Showing p25/p50/p75 = 0/0/0 on such fields is misinformation, not data.
    # Per CLAUDE.md data-integrity rule: "distinguish signal absence from zero".
    #
    # The `measured_fn` hook filters out trades where the field was not captured.
    # Returns True if the trade has a real measurement for this field.
    def _row(label, w_vals, l_vals, fmt="+.2f", n_total=None):
        if n_total and (not w_vals or not l_vals):
            # Sparse field with no measurements on at least one side — make
            # the absence explicit rather than silently dropping the row.
            print(f"  {label:<26}  "
                  f"(not enough measured data — n_w={len(w_vals)}/{n_total[0]} "
                  f"n_l={len(l_vals)}/{n_total[1]})")
            return
        if not w_vals or not l_vals:
            return
        n_suffix = f"  n_w={len(w_vals)}/{n_total[0]} n_l={len(l_vals)}/{n_total[1]}" if n_total else ""
        print(f"  {label:<26}  "
              f"W[p25/p50/p75]={_pct(w_vals,25):{fmt}}/{_pct(w_vals,50):{fmt}}/{_pct(w_vals,75):{fmt}}  "
              f"L[p25/p50/p75]={_pct(l_vals,25):{fmt}}/{_pct(l_vals,50):{fmt}}/{_pct(l_vals,75):{fmt}}"
              f"{n_suffix}")

    def _measured_mfe_mae(t):
        """True if the trade recorded any price movement from entry.
        Pre-215af00 BOND trades have both fav=0 and adv=0 (not measured).
        Post-fix trades almost always have at least one side non-zero."""
        return (float(t.get("max_favourable_pct", 0) or 0) != 0.0
                or float(t.get("max_adverse_pct", 0) or 0) != 0.0)

    def _measured_bounce(t):
        """mae_bounce_10s_pct only populates on trades after 1c350fa and
        only when price dipped below entry (to set a lowest_price anchor)."""
        return float(t.get("mae_bounce_10s_pct", 0) or 0) > 0.0

    def _measured_penalty(t, key):
        """Penalties only fire under specific signal conditions.
        Treat 0 as 'penalty not applied' — not 'not measured'. Include them,
        but report applied-rate separately below."""
        return True

    def _measured_snap(t, sec):
        """entry_snap_Ns captured only when hold_seconds ≥ N AND the snapshot
        differs from entry. Value of exactly 0 almost always means not captured."""
        hold = float(t.get("hold_seconds", 0) or 0)
        return hold >= sec and float(t.get(f"entry_snap_{sec}s_pct", 0) or 0) != 0.0

    def _collect(rows, key, filter_fn=None):
        if filter_fn is None:
            return [float(t.get(key, 0) or 0) for t in rows]
        return [float(t.get(key, 0) or 0) for t in rows if filter_fn(t)]

    if wins and loss:
        print(f"\n── WINNER vs LOSER DISTRIBUTION ────────────────────────────────────────")
        # Dense fields: every trade has them populated
        for label, key, fmt in [
            ("entry_price",             "entry_price",            ".3f"),
            ("hold_seconds",            "hold_seconds",           ".0f"),
            ("velocity_5s_pct",         "velocity_5s_pct",        "+.3f"),
        ]:
            _row(label, _collect(wins, key), _collect(loss, key), fmt)

        # Sparse fields: filter to trades where the field was actually measured
        # and report sample size alongside percentiles (n_measured/n_total).
        _nw, _nl = len(wins), len(loss)

        _wf = _collect(wins, "max_favourable_pct", _measured_mfe_mae)
        _lf = _collect(loss, "max_favourable_pct", _measured_mfe_mae)
        _row("max_favourable_pct", _wf, _lf, "+.1f", n_total=(_nw, _nl))

        _wa = _collect(wins, "max_adverse_pct", _measured_mfe_mae)
        _la = _collect(loss, "max_adverse_pct", _measured_mfe_mae)
        _row("max_adverse_pct", _wa, _la, "+.1f", n_total=(_nw, _nl))

        _wb = _collect(wins, "mae_bounce_10s_pct", _measured_bounce)
        _lb = _collect(loss, "mae_bounce_10s_pct", _measured_bounce)
        _row("mae_bounce_10s_pct", _wb, _lb, "+.1f", n_total=(_nw, _nl))

        _w30 = _collect(wins, "entry_snap_30s_pct", lambda t: _measured_snap(t, 30))
        _l30 = _collect(loss, "entry_snap_30s_pct", lambda t: _measured_snap(t, 30))
        _row("entry_snap_30s_pct", _w30, _l30, "+.1f", n_total=(_nw, _nl))

        _w60 = _collect(wins, "entry_snap_60s_pct", lambda t: _measured_snap(t, 60))
        _l60 = _collect(loss, "entry_snap_60s_pct", lambda t: _measured_snap(t, 60))
        _row("entry_snap_60s_pct", _w60, _l60, "+.1f", n_total=(_nw, _nl))

        # Penalties: 0 is legitimate (penalty not applied). Include all trades,
        # but also print applied-rate as a separate line for interpretability.
        for label, key in [
            ("bond_delta_penalty",    "bond_delta_penalty"),
            ("bond_weak_vel_penalty", "bond_weak_vel_penalty"),
        ]:
            w_all = _collect(wins, key)
            l_all = _collect(loss, key)
            _row(label, w_all, l_all, ".3f")
            w_app = sum(1 for v in w_all if v > 0)
            l_app = sum(1 for v in l_all if v > 0)
            if w_app or l_app:
                print(f"    ↳ applied: W={w_app}/{_nw} ({w_app/_nw*100:.0f}%)  "
                      f"L={l_app}/{_nl} ({l_app/_nl*100:.0f}%)")
            else:
                print(f"    ↳ never applied to any trade — signal condition not firing")
        # Raw entry primitives — only non-zero for post-fix trades
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
