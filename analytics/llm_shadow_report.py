"""
LLM Independent Trader — Shadow P&L Report

Reads logs/llm_shadow.jsonl and computes the LLM's standalone performance:
- Its own WR, net P&L, avg win/loss (using its own TP/SL exits)
- Comparison vs rule system on same candidates
- Breakdown by asset, zone, decision type

Run:  python3 analytics/llm_shadow_report.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

LOG = Path("logs/llm_shadow.jsonl")


def _fmt(v: float) -> str:
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"


def main():
    if not LOG.exists():
        print("No llm_shadow.jsonl found — deploy and run the bot first.")
        return

    entries: dict = {}   # token_id → entry record
    exits:   dict = {}   # token_id → exit record

    with open(LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid = r.get("token_id", "")
            if r.get("record_type") == "llm_entry":
                entries[tid] = r
            elif r.get("record_type") == "llm_exit":
                exits[tid] = r

    if not entries:
        print("No LLM entry records yet.")
        return

    # Join entry + exit
    closed = []
    open_pos = []
    skipped = []

    for tid, e in entries.items():
        if e.get("llm_decision") == "SKIP":
            skipped.append(e)
            continue
        if tid in exits:
            x = exits[tid]
            closed.append({**e, **x})
        else:
            open_pos.append(e)

    total_candidates = len(entries)
    n_take = sum(1 for e in entries.values() if e.get("llm_decision") == "TAKE")
    n_skip = len(skipped)
    n_closed = len(closed)
    n_open = len(open_pos)

    print(f"\n{'='*70}")
    print(f"  LLM INDEPENDENT TRADER — SHADOW PERFORMANCE")
    print(f"{'='*70}")
    print(f"  Candidates evaluated: {total_candidates}")
    print(f"  TAKE: {n_take}  |  SKIP: {n_skip}  |  Closed: {n_closed}  |  Open: {n_open}")

    if not closed:
        print("\n  No closed shadow trades yet — positions still open or no exits logged.")
        if open_pos:
            print(f"\n  Open shadow positions ({len(open_pos)}):")
            for p in open_pos[-5:]:
                print(f"    {p['asset']}/{p['direction']} entry={p['entry_price']:.3f} "
                      f"TP=+{p['llm_tp_pct']:.0f}% SL=-{p['llm_sl_pct']:.0f}% "
                      f"zone={p.get('zone','?')} | {p.get('llm_reason','')[:50]}")
        return

    # Overall stats
    pnls = [t["shadow_gross_pnl"] for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / len(closed) * 100
    total_pnl = sum(pnls)
    avg_w = sum(wins) / len(wins) if wins else 0
    avg_l = sum(losses) / len(losses) if losses else 0
    pf = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float("inf")
    avg_hold = sum(t.get("hold_seconds", 0) for t in closed) / len(closed)

    print(f"\n── OVERALL (n={n_closed} closed) {'─'*44}")
    print(f"  WR:          {wr:.1f}%")
    print(f"  Net P&L:     {_fmt(total_pnl)}  (gross, no fees)")
    print(f"  Profit factor: {pf:.2f}")
    print(f"  Avg win:     {_fmt(avg_w)}    Avg loss: {_fmt(avg_l)}")
    print(f"  Avg hold:    {avg_hold:.0f}s")
    avg_conf = sum(t.get("llm_conf", 0) for t in closed) / len(closed)
    print(f"  Avg conf:    {avg_conf:.2f}")

    # By exit reason
    by_exit: dict = defaultdict(list)
    for t in closed:
        by_exit[t.get("exit_reason", "?")].append(t["shadow_gross_pnl"])
    print(f"\n── BY EXIT REASON {'─'*52}")
    for reason, vals in sorted(by_exit.items()):
        w = sum(1 for v in vals if v > 0)
        print(f"  {reason:<12} n={len(vals):>3}  WR={w/len(vals)*100:>4.0f}%  "
              f"sum={_fmt(sum(vals))}  avg={_fmt(sum(vals)/len(vals))}")

    # By asset
    by_asset: dict = defaultdict(list)
    for t in closed:
        by_asset[t.get("asset", "?")].append(t["shadow_gross_pnl"])
    print(f"\n── BY ASSET {'─'*58}")
    for asset in sorted(by_asset):
        vals = by_asset[asset]
        w = sum(1 for v in vals if v > 0)
        print(f"  {asset:<4} n={len(vals):>3}  WR={w/len(vals)*100:>4.0f}%  "
              f"sum={_fmt(sum(vals))}  avg={_fmt(sum(vals)/len(vals))}")

    # By zone
    by_zone: dict = defaultdict(list)
    for t in closed:
        by_zone[t.get("zone", "?")].append(t["shadow_gross_pnl"])
    print(f"\n── BY ZONE {'─'*59}")
    for zone in ("EARLY", "CORE", "LATE", "IMPULSE"):
        vals = by_zone.get(zone, [])
        if not vals:
            continue
        w = sum(1 for v in vals if v > 0)
        print(f"  {zone:<8} n={len(vals):>3}  WR={w/len(vals)*100:>4.0f}%  "
              f"sum={_fmt(sum(vals))}  avg={_fmt(sum(vals)/len(vals))}")

    # Confidence correlation
    hi_conf = [t for t in closed if t.get("llm_conf", 0) >= 0.75]
    lo_conf = [t for t in closed if t.get("llm_conf", 0) < 0.75]
    if hi_conf and lo_conf:
        print(f"\n── BY CONFIDENCE {'─'*53}")
        for label, rows in [("≥0.75 (high)", hi_conf), ("<0.75 (low)", lo_conf)]:
            vals = [t["shadow_gross_pnl"] for t in rows]
            w = sum(1 for v in vals if v > 0)
            print(f"  {label:<14} n={len(rows):>3}  WR={w/len(rows)*100:>4.0f}%  "
                  f"sum={_fmt(sum(vals))}")

    # Recent trades
    recent = sorted(closed, key=lambda t: t.get("ts", 0))[-10:]
    print(f"\n── RECENT TRADES (last {len(recent)}) {'─'*44}")
    print(f"  {'':2} {'asset':<4} {'dir':<3}  {'entry':>5}  {'exit':>5}  "
          f"{'pnl':>7}  {'hold':>4}  {'why':<10}  reason")
    for t in recent:
        pnl = t["shadow_gross_pnl"]
        mark = "✓" if pnl > 0 else "✗"
        print(f"  {mark} {t.get('asset','?'):<4} {t.get('direction','?')[:3]:<3}  "
              f"{t.get('entry_price',0):.3f}  {t.get('exit_price',0):.3f}  "
              f"{_fmt(pnl):>7}  {t.get('hold_seconds',0):>4.0f}s  "
              f"{t.get('exit_reason','?'):<10}  "
              f"{(t.get('llm_reason','') or '')[:40]}")

    # SKIP quality: what was the actual outcome on trades LLM skipped?
    # We can estimate: if skip + entry in same zone had bad WR, LLM was right
    if skipped:
        print(f"\n── LLM SKIPPED (n={len(skipped)}) — candidates LLM rejected {'─'*25}")
        print(f"  These are opportunities the LLM passed on.")
        print(f"  No outcome data (rule system may or may not have traded them).")
        by_skip_asset: dict = defaultdict(int)
        by_skip_zone: dict = defaultdict(int)
        for s in skipped:
            by_skip_asset[s.get("asset", "?")] += 1
            by_skip_zone[s.get("zone", "?")] += 1
        skip_confs = [s.get("llm_conf", 0) for s in skipped]
        print(f"  Avg conf: {sum(skip_confs)/len(skip_confs):.2f}")
        print(f"  By asset: " + "  ".join(f"{a}={n}" for a, n in sorted(by_skip_asset.items())))
        print(f"  By zone:  " + "  ".join(f"{z}={n}" for z, n in sorted(by_skip_zone.items())))
        recent_skip = sorted(skipped, key=lambda s: s.get("ts", 0))[-5:]
        print(f"  Recent skips:")
        for s in recent_skip:
            print(f"    {s.get('asset','?')}/{s.get('direction','?')[:3]} "
                  f"entry={s.get('entry_price',0):.3f} zone={s.get('zone','?')} "
                  f"conf={s.get('llm_conf',0):.2f} | {(s.get('llm_reason','') or '')[:50]}")

    print()


if __name__ == "__main__":
    main()
