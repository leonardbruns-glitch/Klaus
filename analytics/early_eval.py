"""
Klaus — EARLY-zone evaluation report (analytics only)

Tracks the new EARLY entry path in the BOND scanner. Reports:
  1. EARLY-A (edge-driven) vs EARLY-B (ignition-driven) PnL split
  2. delta_penalty impact distribution (how often / how strongly applied)
  3. weak_vel_penalty activation frequency

No new gates or thresholds — pure post-hoc evaluation of whether the
delta and weak-vel penalties improve realized expectancy.

Usage:
    python3 -m analytics.early_eval
    python3 -m analytics.early_eval --since 2026-04-20
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

DEFAULT_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "trades.jsonl")


def _load(log_path: str, since_ts: float) -> list[dict]:
    if not os.path.exists(log_path):
        print(f"trade log not found: {log_path}", file=sys.stderr)
        return []
    out: list[dict] = []
    with open(log_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("signal_source") != "BOND":
                continue
            if rec.get("token_id", "").startswith("stub_"):
                continue
            if rec.get("exit_reason") == "ORPHAN_SELL":
                continue
            if since_ts and float(rec.get("ts_open", 0)) < since_ts:
                continue
            out.append(rec)
    return out


def _split_class(cls: str) -> str:
    """Return the canonical zone label from `bond_entry_class`."""
    if not cls:
        return "UNKNOWN"
    head = cls.split("/", 1)[0]
    return head  # e.g. "EARLY-A-EDGE", "EARLY-B-IGN", "CORE", "LATE", "IMPULSE"


def _stats(records: Iterable[dict]) -> dict:
    pnl = [float(r.get("net_pnl", 0.0)) for r in records]
    if not pnl:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "sum": 0.0, "avg": 0.0, "med": 0.0}
    wins = [p for p in pnl if p > 0]
    losses = [-p for p in pnl if p < 0]
    return {
        "n": len(pnl),
        "wr": (len(wins) / len(pnl)) * 100.0,
        "pf": (sum(wins) / sum(losses)) if losses else float("inf") if wins else 0.0,
        "sum": sum(pnl),
        "avg": statistics.mean(pnl),
        "med": statistics.median(pnl),
    }


def _bucket_penalty(value: float, edges: list[float]) -> str:
    if value <= 0:
        return "0.000 (none)"
    for hi in edges:
        if value < hi:
            return f"<{hi:.3f}"
    return f">={edges[-1]:.3f}"


def report(records: list[dict]) -> None:
    if not records:
        print("No BOND trades found in window.")
        return

    print(f"\n=== EARLY-zone evaluation report ===")
    print(f"BOND trades analyzed: {len(records)}")
    print(f"Date range: {datetime.utcfromtimestamp(min(r['ts_open'] for r in records)):%Y-%m-%d %H:%M} UTC "
          f"→ {datetime.utcfromtimestamp(max(r['ts_open'] for r in records)):%Y-%m-%d %H:%M} UTC")

    # ── 1. PnL split by entry class ──────────────────────────────────────────
    by_zone: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_zone[_split_class(r.get("bond_entry_class", ""))].append(r)

    print("\n── PnL by BOND entry zone ──")
    print(f"{'zone':<18} {'n':>4} {'wr%':>6} {'pf':>6} {'sum$':>9} {'avg$':>8} {'med$':>8}")
    print("-" * 65)
    # Highlight EARLY-A and EARLY-B explicitly + show others for context
    priority = ["EARLY-A-EDGE", "EARLY-B-IGN", "EARLY", "CORE", "LATE", "IMPULSE"]
    seen = set()
    for z in priority + sorted(by_zone.keys()):
        if z in seen or z not in by_zone:
            continue
        seen.add(z)
        s = _stats(by_zone[z])
        pf_str = f"{s['pf']:.2f}" if s['pf'] != float("inf") else "inf"
        print(f"{z:<18} {s['n']:>4} {s['wr']:>6.1f} {pf_str:>6} "
              f"{s['sum']:>9.2f} {s['avg']:>8.3f} {s['med']:>8.3f}")

    # ── 2. delta_penalty distribution ────────────────────────────────────────
    early_a_records = by_zone.get("EARLY-A-EDGE", [])
    early_b_records = by_zone.get("EARLY-B-IGN", [])
    early_all = early_a_records + early_b_records

    print("\n── delta_penalty distribution (EARLY-A + EARLY-B) ──")
    if not early_all:
        print("  (no EARLY trades yet)")
    else:
        edges = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
        buckets: dict[str, list[dict]] = defaultdict(list)
        for r in early_all:
            buckets[_bucket_penalty(float(r.get("bond_delta_penalty", 0.0)), edges)].append(r)
        print(f"{'penalty':<14} {'n':>4} {'pct':>6} {'wr%':>6} {'pf':>6} {'sum$':>9}")
        print("-" * 52)
        order = ["0.000 (none)", "<0.050", "<0.100", "<0.150", "<0.200", "<0.250", "<0.300", ">=0.300"]
        total_n = len(early_all)
        for b in order:
            if b not in buckets:
                continue
            s = _stats(buckets[b])
            pf_str = f"{s['pf']:.2f}" if s['pf'] != float("inf") else "inf"
            pct = (s['n'] / total_n) * 100.0
            print(f"{b:<14} {s['n']:>4} {pct:>5.1f}% {s['wr']:>6.1f} {pf_str:>6} {s['sum']:>9.2f}")
        # Activation summary
        applied = sum(1 for r in early_all if float(r.get("bond_delta_penalty", 0.0)) > 0)
        print(f"  → activated on {applied}/{len(early_all)} EARLY trades "
              f"({applied / len(early_all) * 100:.1f}%)")

    # ── 3. weak_vel_penalty activation frequency ─────────────────────────────
    print("\n── weak_vel_penalty activation (EARLY-A + EARLY-B) ──")
    if not early_all:
        print("  (no EARLY trades yet)")
    else:
        active = [r for r in early_all if float(r.get("bond_weak_vel_penalty", 0.0)) > 0]
        inactive = [r for r in early_all if float(r.get("bond_weak_vel_penalty", 0.0)) == 0]
        print(f"  activated: {len(active)}/{len(early_all)} "
              f"({len(active) / len(early_all) * 100:.1f}%)")

        if active:
            s_active = _stats(active)
            pf_a = f"{s_active['pf']:.2f}" if s_active['pf'] != float("inf") else "inf"
            print(f"    when active   → n={s_active['n']:>3} "
                  f"wr={s_active['wr']:>5.1f}% pf={pf_a:>5} "
                  f"sum=${s_active['sum']:>7.2f} avg=${s_active['avg']:>6.3f}")
        if inactive:
            s_inactive = _stats(inactive)
            pf_i = f"{s_inactive['pf']:.2f}" if s_inactive['pf'] != float("inf") else "inf"
            print(f"    when inactive → n={s_inactive['n']:>3} "
                  f"wr={s_inactive['wr']:>5.1f}% pf={pf_i:>5} "
                  f"sum=${s_inactive['sum']:>7.2f} avg=${s_inactive['avg']:>6.3f}")
        if active:
            avg_p = statistics.mean(float(r.get("bond_weak_vel_penalty", 0.0)) for r in active)
            print(f"    avg penalty when active: {avg_p:.4f}")

    print()


def main() -> None:
    p = argparse.ArgumentParser(description="EARLY-zone evaluation report.")
    p.add_argument("--log", default=DEFAULT_LOG, help="Path to trades.jsonl")
    p.add_argument("--since", default="", help="ISO date (YYYY-MM-DD) — only trades on/after this date")
    args = p.parse_args()

    since_ts = 0.0
    if args.since:
        try:
            since_ts = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            print(f"invalid --since date: {args.since!r} (expected YYYY-MM-DD)", file=sys.stderr)
            sys.exit(1)

    recs = _load(args.log, since_ts)
    report(recs)


if __name__ == "__main__":
    main()
