#!/usr/bin/env python3
"""Validation layer for ExitPolicyShadow (deployed 2026-05-08, commit 5179da6).

Joins gate_trace ∩ exit_policy_shadow ∩ window_resolution to produce:
  Section 1 — Validation-criteria status vs audit Deliverable 3 thresholds.
  Section 2 — Regime-stratified realistic PnL (session, direction, asset,
              BNC quartile, snap30 quartile, kline outcome, trigger mix).
  Section 3 — Post-hoc entry-tightening sensitivity using gate_trace fields
              (ask floor, snap30 floor, rem band, combinations).
  Section 4 — Vs-live cross-check: where live also took the trade, sim PnL
              vs actual_net_pnl/stake.

Usage:
    python3 analytics/exit_policy_validate.py
    python3 analytics/exit_policy_validate.py --days 7 --policy PT0.95+30s
    python3 analytics/exit_policy_validate.py --shadow-root logs/shadow

Default: scan the most recent 7 days under logs/shadow/hot/<date>/.
Stdlib only — no external deps.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

# ── Validation thresholds (audit Deliverable 3) ───────────────────────────────
VALIDATION = {
    "min_n":              500,    # unique fires per policy
    "min_days":           5,
    "min_quartile_n":     40,
    "min_realistic_mean": 1.0,    # %
    "max_worst_quartile": -1.0,   # %
    "max_derate_pp":      0.5,    # clean - realistic
    "max_cat_rate":       2.0,    # % of fires with realistic_pnl_pct ≤ -70
}

POLICIES = ["PT0.95+30s", "PT0.93+30s", "BE_trail_5_3"]

# Coarse session grouping for parity with audit panels (ASIA / LDN / NY).
COARSE_SESSION = {
    "asia": "ASIA", "ldn_open": "LDN", "eu_overlap": "LDN",
    "ny_pre": "NY", "ny_open": "NY", "ny_lunch": "NY",
    "power_hour": "NY", "after_hours": "ASIA",
}


# ── IO ────────────────────────────────────────────────────────────────────────

def find_dates(root: str, days: int) -> List[str]:
    today = datetime.now(timezone.utc).date()
    out = []
    for i in range(days):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if os.path.isdir(os.path.join(root, "hot", d)):
            out.append(d)
    return sorted(out)


def load_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def join_shadow(dates: List[str], root: str) -> List[dict]:
    """Returns enriched exit_policy_shadow rows with gate_trace and resolution
    fields merged in. One row per (first_fire, policy_id) preserved."""
    gt_index: Dict[Tuple[str, int], dict] = {}
    res_index: Dict[Tuple[str, int], dict] = {}
    eps_rows: List[dict] = []
    for d in dates:
        base = os.path.join(root, "hot", d)
        for r in load_jsonl(os.path.join(base, "gate_trace.jsonl")):
            if r.get("record_type") != "gate_trace":
                continue
            try:
                key = (r["token_id"], int(r["ts_s"]))
            except (KeyError, TypeError, ValueError):
                continue
            gt_index[key] = r
        for r in load_jsonl(os.path.join(base, "window_resolution.jsonl")):
            if r.get("record_type") != "window_resolution":
                continue
            try:
                key = (r.get("condition_id", ""), int(r.get("window_end_ts", 0)))
            except (TypeError, ValueError):
                continue
            res_index[key] = r
        for r in load_jsonl(os.path.join(base, "exit_policy_shadow.jsonl")):
            if r.get("record_type") != "exit_policy_shadow":
                continue
            eps_rows.append(r)
    enriched = []
    for r in eps_rows:
        merged = dict(r)
        try:
            gt_key = (r["token_id"], int(r["fire_ts_s"]))
        except (KeyError, TypeError, ValueError):
            gt_key = None
        if gt_key:
            gt = gt_index.get(gt_key)
            if gt is not None:
                merged["entry_ask"] = float(gt.get("ask", 0.0) or 0.0)
                merged["entry_gate_results"] = gt.get("gate_results", {})
        try:
            res_key = (r.get("condition_id", ""), int(r.get("window_end_ts", 0)))
        except (TypeError, ValueError):
            res_key = None
        if res_key:
            res = res_index.get(res_key)
            if res is not None:
                merged["resolved_yes"] = bool(res.get("resolved_yes"))
                merged["realized_move_pct"] = float(res.get("realized_move_pct", 0.0) or 0.0)
                merged["kline_close"] = float(res.get("binance_close_5m", 0.0) or 0.0)
        merged["coarse_session"] = COARSE_SESSION.get(r.get("session_bucket", ""), "?")
        enriched.append(merged)
    return enriched


# ── Stats helpers ─────────────────────────────────────────────────────────────

def stats_block(rows: List[dict], key: str = "realistic_pnl_pct") -> dict:
    vals = [float(r.get(key, 0.0) or 0.0) for r in rows]
    if not vals:
        return {"n": 0, "mean": 0.0, "median": 0.0, "p10": 0.0,
                "p25": 0.0, "p75": 0.0, "wr": 0.0, "cat_rate": 0.0}
    n = len(vals)
    s = sorted(vals)
    return {
        "n":        n,
        "mean":     sum(vals) / n,
        "median":   s[n // 2],
        "p10":      s[max(0, n // 10 - 1)] if n >= 10 else s[0],
        "p25":      s[n // 4],
        "p75":      s[(3 * n) // 4],
        "wr":       100.0 * sum(1 for v in vals if v > 0) / n,
        "cat_rate": 100.0 * sum(1 for v in vals if v <= -70) / n,
    }


def n_flag(n: int) -> str:
    if n < 40:  return " [INSUFFICIENT]"
    if n < 100: return " [TREND]"
    return ""


def fmt(x: float, suffix: str = "%", width: int = 7) -> str:
    return f"{x:>+{width}.2f}{suffix}"


def quartile_bins(values: List[float]) -> List[float]:
    """Returns the 3 cut points splitting `values` into roughly equal quartiles."""
    if not values:
        return [0.0, 0.0, 0.0]
    s = sorted(values)
    n = len(s)
    return [s[n // 4], s[n // 2], s[(3 * n) // 4]]


def assign_quartile(v: float, cuts: List[float]) -> int:
    if v <= cuts[0]: return 0
    if v <= cuts[1]: return 1
    if v <= cuts[2]: return 2
    return 3


# ── Section 1: Validation status ──────────────────────────────────────────────

def section_validation(by_policy: Dict[str, List[dict]], policies: List[str]) -> None:
    print("=" * 84)
    print("SECTION 1 — VALIDATION CRITERIA STATUS")
    print(f"  Thresholds (audit Deliverable 3): n>={VALIDATION['min_n']}, "
          f"days>={VALIDATION['min_days']}, mean>=+{VALIDATION['min_realistic_mean']}%, "
          f"worst quartile>={VALIDATION['max_worst_quartile']}%, "
          f"derate<={VALIDATION['max_derate_pp']}pp, cat<={VALIDATION['max_cat_rate']}%")
    print("=" * 84)
    hdr = f"{'Policy':<15} {'N':>5} {'days':>5} {'mean':>9} {'p10':>9} {'cat%':>6} {'derate':>8}  status"
    print(hdr)
    print("-" * len(hdr))
    for pid in policies:
        rs = by_policy.get(pid, [])
        if not rs:
            print(f"{pid:<15} (no records)")
            continue
        days_covered = len(set(
            datetime.fromtimestamp(int(r.get("fire_ts_s", 0)), timezone.utc).date()
            for r in rs if r.get("fire_ts_s")
        ))
        s = stats_block(rs, "realistic_pnl_pct")
        clean_mean = sum(float(r.get("clean_pnl_pct", 0.0)) for r in rs) / len(rs)
        derate = clean_mean - s["mean"]
        flags = []
        if s["n"] < VALIDATION["min_n"]: flags.append(f"N<{VALIDATION['min_n']}")
        if days_covered < VALIDATION["min_days"]: flags.append(f"days<{VALIDATION['min_days']}")
        if s["mean"] < VALIDATION["min_realistic_mean"]: flags.append(f"mean<{VALIDATION['min_realistic_mean']}")
        if s["cat_rate"] > VALIDATION["max_cat_rate"]: flags.append(f"cat>{VALIDATION['max_cat_rate']}")
        if derate > VALIDATION["max_derate_pp"]: flags.append(f"derate>{VALIDATION['max_derate_pp']}")
        status = "OK" if not flags else " ".join(flags)
        print(f"{pid:<15} {s['n']:>5} {days_covered:>5} {fmt(s['mean'], '%', 8):>9} "
              f"{fmt(s['p10'], '%', 8):>9} {s['cat_rate']:>5.1f}% {derate:>+7.2f}pp  {status}")
    print()


# ── Section 2: Regime stratification ──────────────────────────────────────────

def section_regimes(by_policy: Dict[str, List[dict]], policies: List[str]) -> None:
    print("=" * 84)
    print("SECTION 2 — REGIME-STRATIFIED REALISTIC PnL")
    print("=" * 84)
    for pid in policies:
        rs = by_policy.get(pid, [])
        if not rs:
            continue
        print(f"\n[{pid}] — n={len(rs)}")
        # Trigger mix
        trig = Counter(r.get("exit_trigger", "?") for r in rs)
        print("  Trigger distribution:")
        for t in ("PT", "FALLBACK_30s", "BE_TRAIL", "WINDOW_END"):
            cnt = trig.get(t, 0)
            pct = 100.0 * cnt / len(rs)
            sub = [r for r in rs if r.get("exit_trigger") == t]
            s = stats_block(sub) if sub else None
            mean_s = f"mean={fmt(s['mean'])}" if s else ""
            print(f"    {t:<14} n={cnt:>4} ({pct:>5.1f}%)  {mean_s}")

        def panel(label: str, group_fn: Callable[[dict], str], order: Optional[List[str]] = None) -> None:
            buckets: Dict[str, List[dict]] = defaultdict(list)
            for r in rs:
                buckets[group_fn(r)].append(r)
            keys = order if order else sorted(buckets.keys())
            print(f"\n  By {label}:")
            for k in keys:
                if k not in buckets:
                    continue
                s = stats_block(buckets[k])
                print(f"    {k:<22} n={s['n']:>4}  mean={fmt(s['mean'])}  "
                      f"median={fmt(s['median'])}  p10={fmt(s['p10'])}  "
                      f"WR={s['wr']:>5.1f}%  cat={s['cat_rate']:>4.1f}%{n_flag(s['n'])}")

        panel("coarse_session (ASIA/LDN/NY)", lambda r: r.get("coarse_session", "?"),
              order=["ASIA", "LDN", "NY"])
        panel("session_bucket", lambda r: r.get("session_bucket", "?"))
        panel("direction", lambda r: r.get("direction", "?"), order=["up", "down"])
        panel("asset", lambda r: r.get("asset", "?"), order=["BTC", "ETH", "SOL"])

        # BNC 5m quartile
        bnc_vals = [float(r.get("bnc_5m_pct", 0.0) or 0.0) for r in rs]
        bnc_cuts = quartile_bins(bnc_vals)
        for r in rs:
            r["_bnc_q"] = assign_quartile(float(r.get("bnc_5m_pct", 0.0) or 0.0), bnc_cuts)
        print(f"\n  By BNC 5m quartile (cuts: {bnc_cuts[0]:+.3f}, {bnc_cuts[1]:+.3f}, {bnc_cuts[2]:+.3f}%):")
        for q in range(4):
            sub = [r for r in rs if r["_bnc_q"] == q]
            s = stats_block(sub)
            print(f"    Q{q+1:<19}  n={s['n']:>4}  mean={fmt(s['mean'])}  "
                  f"cat={s['cat_rate']:>4.1f}%{n_flag(s['n'])}")

        # snap30 quartile
        s30_vals = [float(r.get("snap30", 0.0) or 0.0) for r in rs]
        s30_cuts = quartile_bins(s30_vals)
        for r in rs:
            r["_s30_q"] = assign_quartile(float(r.get("snap30", 0.0) or 0.0), s30_cuts)
        print(f"\n  By snap30 quartile (cuts: {s30_cuts[0]:.2f}, {s30_cuts[1]:.2f}, {s30_cuts[2]:.2f}):")
        for q in range(4):
            sub = [r for r in rs if r["_s30_q"] == q]
            s = stats_block(sub)
            print(f"    Q{q+1:<19}  n={s['n']:>4}  mean={fmt(s['mean'])}  "
                  f"cat={s['cat_rate']:>4.1f}%{n_flag(s['n'])}")

        # Kline outcome (where joined)
        joined = [r for r in rs if "resolved_yes" in r]
        if joined:
            print(f"\n  By kline outcome (n_joined={len(joined)}/{len(rs)}):")
            for label, pred in (
                ("resolved_yes=True",  lambda r: r.get("resolved_yes") is True),
                ("resolved_yes=False", lambda r: r.get("resolved_yes") is False),
            ):
                sub = [r for r in joined if pred(r)]
                s = stats_block(sub)
                print(f"    {label:<22} n={s['n']:>4}  mean={fmt(s['mean'])}  "
                      f"cat={s['cat_rate']:>4.1f}%{n_flag(s['n'])}")
    print()


# ── Section 3: Post-hoc entry-tightening sensitivity ──────────────────────────

def section_post_hoc(by_policy: Dict[str, List[dict]], policy_id: str) -> None:
    print("=" * 84)
    print(f"SECTION 3 — POST-HOC ENTRY-TIGHTENING SENSITIVITY ({policy_id})")
    print("=" * 84)
    rs = by_policy.get(policy_id, [])
    rs_with_gate = [r for r in rs if "entry_ask" in r]
    print(f"Population: {len(rs)} rows ({len(rs_with_gate)} joined to gate_trace).")
    if not rs_with_gate:
        print("(no gate_trace joins — cannot run post-hoc filters)")
        print()
        return

    filters = [
        ("baseline (shadow-passive-v1)",       lambda r: True),
        ("ask >= 0.80 (live equiv)",           lambda r: r.get("entry_ask", 0) >= 0.80),
        ("ask >= 0.82",                        lambda r: r.get("entry_ask", 0) >= 0.82),
        ("ask >= 0.84",                        lambda r: r.get("entry_ask", 0) >= 0.84),
        ("snap30 >= 5",                        lambda r: r.get("snap30", 0) >= 5.0),
        ("snap30 >= 15",                       lambda r: r.get("snap30", 0) >= 15.0),
        ("snap30 >= 20",                       lambda r: r.get("snap30", 0) >= 20.0),
        ("rem 25-90s (TERMINAL band)",         lambda r: 25.0 <= r.get("sec_to_res_at_fire", 0) <= 90.0),
        ("rem 15-90s (Balanced cand.)",        lambda r: 15.0 <= r.get("sec_to_res_at_fire", 0) <= 90.0),
        ("ask>=0.80 AND snap30>=15",           lambda r: r.get("entry_ask", 0) >= 0.80 and r.get("snap30", 0) >= 15.0),
        ("ask>=0.80 AND rem 25-90",            lambda r: r.get("entry_ask", 0) >= 0.80 and 25.0 <= r.get("sec_to_res_at_fire", 0) <= 90.0),
        ("ask>=0.80 AND snap30>=5 AND rem15-90", lambda r: r.get("entry_ask", 0) >= 0.80 and r.get("snap30", 0) >= 5.0 and 15.0 <= r.get("sec_to_res_at_fire", 0) <= 90.0),
    ]
    n_total = len(rs_with_gate)
    print(f"\n{'filter':<42} {'n':>5} {'%':>6}  {'mean':>9}  {'p10':>9}  {'WR%':>6}  {'cat%':>6}")
    print("-" * 96)
    for name, fn in filters:
        sub = [r for r in rs_with_gate if fn(r)]
        s = stats_block(sub)
        pct = 100.0 * s["n"] / max(1, n_total)
        if s["n"] == 0:
            print(f"{name:<42} {s['n']:>5} {pct:>5.1f}%  {'—':>9}  {'—':>9}  {'—':>6}  {'—':>6}")
            continue
        print(f"{name:<42} {s['n']:>5} {pct:>5.1f}%  {fmt(s['mean']):>9}  "
              f"{fmt(s['p10']):>9}  {s['wr']:>5.1f}%  {s['cat_rate']:>5.1f}%{n_flag(s['n'])}")
    print()


# ── Section 4: Vs-live cross-check ────────────────────────────────────────────

def section_vs_live(rows: List[dict], policy_id: str, trades_path: str,
                    join_window_s: float = 5.0) -> None:
    print("=" * 84)
    print(f"SECTION 4 — VS-LIVE CROSS-CHECK ({policy_id})")
    print(f"  Join: shadow.token_id == trades.token_id AND |fire_ts_s − ts_open| <= {join_window_s}s")
    print(f"  Compare: realistic_pnl_pct (sim) vs net_pnl/stake*100 (live)")
    print("=" * 84)
    if not os.path.exists(trades_path):
        print(f"(trades.jsonl not found at {trades_path}; skipping)")
        print()
        return
    eps_rows = [r for r in rows if r.get("policy_id") == policy_id]
    if not eps_rows:
        print("(no shadow rows for this policy)")
        return

    fire_by_token: Dict[str, List[Tuple[float, dict]]] = defaultdict(list)
    for r in eps_rows:
        try:
            fire_by_token[r["token_id"]].append((float(r["fire_ts_s"]), r))
        except (KeyError, TypeError, ValueError):
            continue

    pairs = []
    with open(trades_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            if t.get("record_type"):
                continue
            if not t.get("is_live"):
                continue
            tid = t.get("token_id")
            tso = t.get("ts_open")
            if not tid or not tso:
                continue
            cands = fire_by_token.get(tid, [])
            for fts, r in cands:
                if abs(fts - float(tso)) <= join_window_s:
                    pairs.append((t, r))
                    break

    if not pairs:
        print("(no live trades joined to shadow first-fires for this policy)")
        print()
        return

    sim_pnl = [float(r.get("realistic_pnl_pct", 0.0)) for _, r in pairs]
    live_pnl = []
    for t, _ in pairs:
        stake = float(t.get("stake", 0.0))
        net = float(t.get("net_pnl", 0.0))
        live_pnl.append(100.0 * net / stake if stake > 0 else 0.0)

    n = len(pairs)
    sim_mean = sum(sim_pnl) / n
    live_mean = sum(live_pnl) / n
    delta = sim_mean - live_mean
    n_sim_better = sum(1 for s, l in zip(sim_pnl, live_pnl) if s > l)
    print(f"\n  Joined pairs: n={n}{n_flag(n)}")
    print(f"  Live mean:   {live_mean:>+7.2f}%")
    print(f"  Sim  mean:   {sim_mean:>+7.2f}%   (Δ {delta:>+6.2f}pp vs live)")
    print(f"  Sim better:  {n_sim_better}/{n} ({100.0 * n_sim_better / n:>4.1f}%)")
    if n >= 5:
        print(f"\n  Per-trade detail (last 10):")
        print(f"    {'trade_id':<28} {'live_exit':<22} {'live%':>8} {'sim_trig':<14} {'sim%':>8} {'Δpp':>7}")
        for t, r in pairs[-10:]:
            stake = float(t.get("stake", 0.0))
            net = float(t.get("net_pnl", 0.0))
            lpnl = 100.0 * net / stake if stake > 0 else 0.0
            spnl = float(r.get("realistic_pnl_pct", 0.0))
            print(f"    {str(t.get('trade_id',''))[:27]:<28} "
                  f"{str(t.get('exit_reason',''))[:21]:<22} "
                  f"{lpnl:>+7.2f}% "
                  f"{str(r.get('exit_trigger',''))[:13]:<14} "
                  f"{spnl:>+7.2f}% "
                  f"{spnl-lpnl:>+6.2f}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7, help="Look back N days (default 7)")
    ap.add_argument("--shadow-root", default="logs/shadow", help="Shadow root (default logs/shadow)")
    ap.add_argument("--policy", default=None, help="Filter to one policy_id (default: all)")
    ap.add_argument("--trades", default="logs/trades.jsonl", help="Live trades file for vs-live join")
    ap.add_argument("--no-vs-live", action="store_true", help="Skip Section 4")
    args = ap.parse_args()

    dates = find_dates(args.shadow_root, args.days)
    if not dates:
        print(f"No shadow data found under {args.shadow_root}/hot/")
        return 1

    print(f"# exit_policy_validate")
    print(f"# Dates scanned: {dates[0]} → {dates[-1]} ({len(dates)} days)")
    print(f"# Shadow root:   {args.shadow_root}")
    print()

    rows = join_shadow(dates, args.shadow_root)
    print(f"Total exit_policy_shadow rows: {len(rows)}")
    if not rows:
        return 0
    n_with_gate = sum(1 for r in rows if "entry_ask" in r)
    n_with_res = sum(1 for r in rows if "resolved_yes" in r)
    print(f"  joined to gate_trace:        {n_with_gate}/{len(rows)} ({100*n_with_gate/len(rows):.0f}%)")
    print(f"  joined to window_resolution: {n_with_res}/{len(rows)} ({100*n_with_res/len(rows):.0f}%)")
    print()

    by_policy: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        by_policy[r.get("policy_id", "?")].append(r)

    policies = [args.policy] if args.policy else POLICIES

    section_validation(by_policy, policies)
    section_regimes(by_policy, policies)
    section_post_hoc(by_policy, "PT0.95+30s")
    if not args.no_vs_live:
        section_vs_live(rows, "PT0.95+30s", args.trades)

    return 0


if __name__ == "__main__":
    sys.exit(main())
