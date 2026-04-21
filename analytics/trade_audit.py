#!/usr/bin/env python3
"""
Trade audit — reads trades.jsonl + bot.log and produces a structured
performance report with stability-class breakdown and observation params.

Usage:
    python3 analytics/trade_audit.py [--since "2026-04-20 17:00"]
"""
from __future__ import annotations
import json, re, sys, os
from collections import defaultdict
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
TRADES_FILE = os.path.join(os.path.dirname(__file__), "../logs/trades.jsonl")
BOT_LOG     = os.path.join(os.path.dirname(__file__), "../logs/bot.log")

DEFAULT_SINCE = "2026-04-20 17:00"

def parse_since(s: str) -> float:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0

# ── Outcome bucket mapping ─────────────────────────────────────────────────────
def outcome_bucket(exit_reason: str, net_pnl: float) -> str:
    r = exit_reason.upper()
    if "TP_95" in r or "TP_99" in r or "BOND_TP" in r: return "TP"
    if "MOMENTUM_FAIL" in r:                             return "MOMENTUM_FAIL"
    if "LATE_EXHAUST" in r:                              return "LATE_EXHAUST"
    if "TIME_EXIT" in r:                                 return "TIME_EXIT"
    if "PRICE_SL" in r or "HARD_SL" in r:               return "HARD_SL"
    if "STOP_LOSS" in r or "_SL" in r:                   return "SL"
    if "EARLY_LOSS" in r:                                return "EARLY_LOSS"
    if net_pnl < 0:                                      return "LOSS"
    return "OTHER"

# ── Parse BOND_STAB lines from bot.log ────────────────────────────────────────
STAB_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*BOND_STAB\s+"
    r"(\w+)/(\w+)\s+\[(\S+)\]\s+\|\s+class=(\S+)\s+score=(\d+)\s+\|"
    r".*xp_bad=(\S+)\s+slip_bad=(\S+)\s+delta_bad=(\S+)\s+edge_weak=(\S+)\s+vel_flat=(\S+)\s+\|"
    r".*xp=([0-9.]+)\s+slip_e=([0-9.]+)\s+edge=([0-9.-]+)\s+fv=([0-9.]+)\s+delta=([0-9.+\-]+)%\s+vel=([0-9.+\-]+)%"
)

VELREG_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*EARLY_A_VELREG_WOULDBLOCK\s+(\w+)/(\w+)"
)

def load_stab_log(since_ts: float):
    stab: dict[str, dict] = {}   # key: "ASSET/SIDE" -> most recent stab entry by timestamp
    velreg_set: set[str] = set() # "ASSET/SIDE"

    if not os.path.exists(BOT_LOG):
        return stab, velreg_set

    with open(BOT_LOG, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = STAB_RE.search(line)
            if m:
                ts_str, asset, side, dzone, cls, score, xp_b, slip_b, delta_b, edge_w, vel_f, \
                    xp, slip_e, edge, fv, delta, vel = m.groups()
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                except ValueError:
                    continue
                if ts < since_ts:
                    continue
                key = f"{asset}/{side}"
                stab[key] = {
                    "ts": ts, "dzone": dzone, "stab_class": cls, "score": int(score),
                    "xp_bad": xp_b == "True", "slip_bad": slip_b == "True",
                    "delta_bad": delta_b == "True", "edge_weak": edge_w == "True",
                    "vel_flat": vel_f == "True",
                    "xp": float(xp), "slip_e": float(slip_e), "edge": float(edge),
                    "fv": float(fv), "delta": float(delta), "vel": float(vel),
                }
                continue
            m2 = VELREG_RE.search(line)
            if m2:
                ts_str, asset, side = m2.groups()
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                except ValueError:
                    continue
                if ts >= since_ts:
                    velreg_set.add(f"{asset}/{side}")

    return stab, velreg_set

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    since_arg = DEFAULT_SINCE
    for i, a in enumerate(sys.argv[1:]):
        if a == "--since" and i + 1 < len(sys.argv) - 1:
            since_arg = sys.argv[i + 2]
    since_ts = parse_since(since_arg)

    trades: list[dict] = []
    if not os.path.exists(TRADES_FILE):
        print(f"[WARN] {TRADES_FILE} not found")
    else:
        with open(TRADES_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    t = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if t.get("ts_close", 0) >= since_ts or t.get("ts_open", 0) >= since_ts:
                    trades.append(t)

    stab_log, velreg_set = load_stab_log(since_ts)

    bond_trades = [t for t in trades if t.get("signal_source") == "BOND" or t.get("is_bond")]
    all_trades  = [t for t in trades if not (t.get("signal_source") == "BOND" or t.get("is_bond"))]

    print(f"\n{'='*70}")
    print(f"TRADE AUDIT  since={since_arg}  |  bond={len(bond_trades)}  other={len(all_trades)}")
    print(f"{'='*70}")

    if not bond_trades:
        print("[no BOND trades in window]")
    else:
        _print_bond_report(bond_trades, stab_log, velreg_set)

    if all_trades:
        _print_other_summary(all_trades)

def _fmt_pnl(v: float) -> str:
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"

def _stats(vals: list[float]) -> str:
    if not vals: return "n=0"
    avg = sum(vals) / len(vals)
    wins = sum(1 for v in vals if v > 0)
    wr = wins / len(vals) * 100
    return f"n={len(vals)} WR={wr:.0f}% avg={_fmt_pnl(avg)} sum={_fmt_pnl(sum(vals))}"

def _print_bond_report(trades: list[dict], stab_log: dict, velreg_set: set):
    # Attach stab info to each trade (best-effort by asset+side proximity)
    # Stab log is keyed by "ASSET/SIDE"; we grab the most recent before ts_open
    for t in trades:
        key = f"{t.get('asset','?')}/{t.get('direction','?').replace('BUY_','')}"
        stab = stab_log.get(key, {})
        t["_stab"]    = stab
        t["_velreg"]  = key in velreg_set
        t["_bucket"]  = outcome_bucket(t.get("exit_reason",""), t.get("net_pnl", 0))

    total_pnl = sum(t.get("net_pnl", 0) for t in trades)
    wins  = [t for t in trades if t.get("net_pnl", 0) > 0]
    loss  = [t for t in trades if t.get("net_pnl", 0) <= 0]
    wr = len(wins) / len(trades) * 100 if trades else 0

    print(f"\n── BOND OVERVIEW ──────────────────────────────────────────────────────")
    print(f"  n={len(trades)}  WR={wr:.1f}%  net={_fmt_pnl(total_pnl)}")
    avg_win  = sum(t["net_pnl"] for t in wins)  / len(wins)  if wins  else 0
    avg_loss = sum(t["net_pnl"] for t in loss) / len(loss)  if loss else 0
    print(f"  avg_win={_fmt_pnl(avg_win)}  avg_loss={_fmt_pnl(avg_loss)}  "
          f"PF={(sum(t['net_pnl'] for t in wins) / max(0.01, abs(sum(t['net_pnl'] for t in loss)))):.2f}")

    # ── Outcome bucket breakdown ───────────────────────────────────────────────
    print(f"\n── BY EXIT BUCKET ─────────────────────────────────────────────────────")
    by_bucket: dict[str, list] = defaultdict(list)
    for t in trades:
        by_bucket[t["_bucket"]].append(t["net_pnl"])
    for bucket in sorted(by_bucket, key=lambda b: sum(by_bucket[b]), reverse=True):
        print(f"  {bucket:<20} {_stats(by_bucket[bucket])}")

    # ── Entry class breakdown ─────────────────────────────────────────────────
    print(f"\n── BY ENTRY CLASS (bond_entry_class) ──────────────────────────────────")
    by_class: dict[str, list] = defaultdict(list)
    for t in trades:
        by_class[t.get("bond_entry_class","?")].append(t["net_pnl"])
    for cls in sorted(by_class, key=lambda c: sum(by_class[c]), reverse=True):
        print(f"  {cls:<30} {_stats(by_class[cls])}")

    # ── Macro regime breakdown ────────────────────────────────────────────────
    print(f"\n── BY MACRO REGIME (bond_macro_regime) ────────────────────────────────")
    by_regime: dict[str, list] = defaultdict(list)
    for t in trades:
        by_regime[t.get("bond_macro_regime","?")].append(t["net_pnl"])
    for reg in sorted(by_regime, key=lambda r: sum(by_regime[r]), reverse=True):
        print(f"  {reg:<20} {_stats(by_regime[reg])}")

    # ── Stability class breakdown ─────────────────────────────────────────────
    print(f"\n── BY STABILITY CLASS (BOND_STAB log) ─────────────────────────────────")
    stab_matched = [t for t in trades if t["_stab"]]
    stab_miss    = [t for t in trades if not t["_stab"]]
    by_stab: dict[str, list] = defaultdict(list)
    for t in stab_matched:
        by_stab[t["_stab"]["stab_class"]].append(t["net_pnl"])
    for sc in ["CLEAN", "NOISY", "HIGH_RISK", "FATAL"]:
        if sc in by_stab:
            print(f"  {sc:<12} {_stats(by_stab[sc])}")
    if stab_miss:
        print(f"  UNMATCHED    n={len(stab_miss)}  (stab log entry not found for these trades)")

    # ── Stability × Outcome cross-tab ─────────────────────────────────────────
    if stab_matched:
        print(f"\n── STABILITY × OUTCOME CROSS-TAB ──────────────────────────────────────")
        sxo: dict[tuple, list] = defaultdict(list)
        for t in stab_matched:
            sxo[(t["_stab"]["stab_class"], t["_bucket"])].append(t["net_pnl"])
        stab_order   = ["CLEAN", "NOISY", "HIGH_RISK", "FATAL"]
        bucket_order = ["TP", "TIME_EXIT", "LATE_EXHAUST", "MOMENTUM_FAIL", "HARD_SL", "SL", "EARLY_LOSS", "LOSS", "OTHER"]
        buckets_seen = sorted({b for _, b in sxo}, key=lambda b: bucket_order.index(b) if b in bucket_order else 99)
        header = f"  {'CLASS':<12}" + "".join(f"  {b:<16}" for b in buckets_seen)
        print(header)
        for sc in stab_order:
            row = f"  {sc:<12}"
            for b in buckets_seen:
                cell = sxo.get((sc, b), [])
                if cell:
                    wr = sum(1 for v in cell if v > 0) / len(cell) * 100
                    row += f"  n={len(cell)} {_fmt_pnl(sum(cell)):<9}"
                else:
                    row += f"  {'—':<16}"
            print(row)

    # ── VelReg wouldblock trades ──────────────────────────────────────────────
    velreg_trades = [t for t in trades if t["_velreg"]]
    if velreg_trades:
        print(f"\n── VELREG WOULDBLOCK (would have been blocked by vel gate) ────────────")
        print(f"  {_stats([t['net_pnl'] for t in velreg_trades])}")
        by_bk: dict[str, list] = defaultdict(list)
        for t in velreg_trades:
            by_bk[t["_bucket"]].append(t["net_pnl"])
        for b, pnls in sorted(by_bk.items(), key=lambda x: sum(x[1]), reverse=True):
            print(f"    {b:<20} {_stats(pnls)}")

    # ── Per-trade detail ──────────────────────────────────────────────────────
    print(f"\n── PER-TRADE DETAIL ────────────────────────────────────────────────────")
    print(f"  {'TIME':>16}  {'ASSET':<8}  {'CLASS':>10}  {'ENTRY':>6}  {'EXIT':>6}"
          f"  {'MOVE':>7}  {'PNL':>8}  {'REASON':<22}  {'STAB':<10}  SCORE")
    for t in sorted(trades, key=lambda x: x.get("ts_open", 0)):
        ts   = datetime.fromtimestamp(t.get("ts_open", 0), tz=timezone.utc).strftime("%m-%d %H:%M:%S")
        move = (t.get("exit_price",0) - t.get("entry_price",0)) / max(0.001, t.get("entry_price",1)) * 100
        stab = t["_stab"]
        sc   = stab.get("stab_class", "?") if stab else "?"
        sc_n = stab.get("score", "?") if stab else "?"
        velreg_flag = "⚑" if t["_velreg"] else ""
        print(f"  {ts:>16}  {t.get('asset','?'):<8}  {t.get('bond_entry_class','?')[:10]:>10}"
              f"  {t.get('entry_price',0):.3f}  {t.get('exit_price',0):.3f}"
              f"  {move:>+6.1f}%  {_fmt_pnl(t.get('net_pnl',0)):>8}"
              f"  {t.get('exit_reason','?'):<22}  {sc:<10}  {sc_n}{velreg_flag}")

    # ── Raw stab signal distributions (for matched trades) ────────────────────
    if stab_matched:
        print(f"\n── ENTRY PRIMITIVE DISTRIBUTIONS (matched trades) ─────────────────────")
        xp_vals   = [t["_stab"]["xp"]    for t in stab_matched]
        edge_vals = [t["_stab"]["edge"]  for t in stab_matched]
        delta_vals= [t["_stab"]["delta"] for t in stab_matched]
        vel_vals  = [t["_stab"]["vel"]   for t in stab_matched]
        slip_vals = [t["_stab"]["slip_e"]for t in stab_matched]
        def percentiles(vals, label):
            s = sorted(vals)
            n = len(s)
            p = lambda q: s[int(q * n / 100)]
            print(f"  {label:<10} min={p(0):.4f}  p25={p(25):.4f}  p50={p(50):.4f}"
                  f"  p75={p(75):.4f}  max={p(99 if n > 1 else 0):.4f}")
        percentiles(xp_vals,    "xp")
        percentiles(edge_vals,  "edge")
        percentiles(delta_vals, "delta%")
        percentiles(vel_vals,   "vel%")
        percentiles(slip_vals,  "slip_e")

def _print_other_summary(trades: list[dict]):
    print(f"\n── NON-BOND TRADES ─────────────────────────────────────────────────────")
    total_pnl = sum(t.get("net_pnl", 0) for t in trades)
    wr = sum(1 for t in trades if t.get("net_pnl", 0) > 0) / len(trades) * 100 if trades else 0
    print(f"  n={len(trades)}  WR={wr:.1f}%  net={_fmt_pnl(total_pnl)}")

if __name__ == "__main__":
    main()
