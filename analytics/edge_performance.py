#!/usr/bin/env python3
"""
Edge-effectiveness report — read-only analytics over logs/trades.jsonl.

Measures three breakdowns to validate entry/sizing logic:
  1. Edge bucket vs net result      (does our edge-scoring predict PnL?)
  2. Exit reason distribution       (which exits produce wins vs losses?)
  3. Hold time vs net result        (when does PnL crystallise?)

Run:  python3 analytics/edge_performance.py
"""
import json, os, sys
from collections import defaultdict

_ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_PATH  = os.path.join(_ROOT, "logs", "trades.jsonl")


def _load_trades(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


def _stats(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0, "pf": 0.0,
                "wins": 0, "losses": 0, "avg_win": 0.0, "avg_loss": 0.0}
    wins    = [r for r in rows if (r.get("net_pnl") or 0) > 0]
    losses  = [r for r in rows if (r.get("net_pnl") or 0) < 0]
    tot_win = sum(r.get("net_pnl", 0) or 0 for r in wins)
    tot_los = sum(r.get("net_pnl", 0) or 0 for r in losses)
    total   = tot_win + tot_los
    pf      = (tot_win / abs(tot_los)) if tot_los < 0 else (float("inf") if tot_win > 0 else 0.0)
    return {
        "n":        n,
        "wr":       len(wins) / n * 100,
        "avg":      total / n,
        "total":    total,
        "pf":       pf,
        "wins":     len(wins),
        "losses":   len(losses),
        "avg_win":  (tot_win / len(wins)) if wins else 0.0,
        "avg_loss": (tot_los / len(losses)) if losses else 0.0,
    }


def _print_table(title: str, rows: list[tuple[str, dict]]) -> None:
    print(f"\n=== {title} ===")
    print(f"{'bucket':<22} {'n':>4} {'WR%':>6} {'avg$':>8} {'total$':>9} {'PF':>6} {'avg_w':>7} {'avg_l':>7}")
    print("-" * 78)
    for label, s in rows:
        pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
        print(f"{label:<22} {s['n']:>4d} {s['wr']:>5.1f}% "
              f"{s['avg']:>+8.3f} {s['total']:>+9.3f} {pf_s:>6} "
              f"{s['avg_win']:>+7.3f} {s['avg_loss']:>+7.3f}")


def _edge_bucket(e: float) -> str:
    if e is None:
        return "edge=?"
    if e < 0.04:   return "edge<0.04 (blocked)"
    if e < 0.05:   return "edge 0.04-0.05 (WEAK)"
    if e < 0.07:   return "edge 0.05-0.07 (MOD)"
    if e < 0.10:   return "edge 0.07-0.10 (FULL)"
    return          "edge>=0.10 (EXTREME)"


def _hold_bucket(h: float) -> str:
    if h is None or h <= 0:
        return "hold=?"
    if h < 10:     return "hold <10s"
    if h < 20:     return "hold 10-20s"
    if h < 30:     return "hold 20-30s"
    if h < 45:     return "hold 30-45s"
    if h < 60:     return "hold 45-60s"
    if h < 90:     return "hold 60-90s"
    if h < 120:    return "hold 90-120s"
    return          "hold 120s+"


_EDGE_ORDER = [
    "edge<0.04 (blocked)",
    "edge 0.04-0.05 (WEAK)",
    "edge 0.05-0.07 (MOD)",
    "edge 0.07-0.10 (FULL)",
    "edge>=0.10 (EXTREME)",
    "edge=?",
]

_HOLD_ORDER = [
    "hold <10s", "hold 10-20s", "hold 20-30s", "hold 30-45s",
    "hold 45-60s", "hold 60-90s", "hold 90-120s", "hold 120s+", "hold=?",
]


def main() -> None:
    trades = _load_trades(TRADES_PATH)
    if not trades:
        print(f"no trades in {TRADES_PATH}")
        sys.exit(0)

    # Only include trades with meaningful PnL (skip ghosts/orphans at $0)
    live = [t for t in trades if t.get("exit_reason") not in ("ORPHAN_SELL", "GHOST_POSITION")]

    print(f"loaded {len(trades)} trades ({len(live)} live, "
          f"{len(trades) - len(live)} ghost/orphan excluded)")

    overall = _stats(live)
    _print_table("OVERALL", [("all trades", overall)])

    # 1. Edge bucket vs net result
    by_edge: dict[str, list[dict]] = defaultdict(list)
    for t in live:
        by_edge[_edge_bucket(t.get("sniper_edge"))].append(t)
    _print_table(
        "EDGE BUCKET vs NET RESULT",
        [(k, _stats(by_edge[k])) for k in _EDGE_ORDER if by_edge[k]],
    )

    # 2. Exit reason distribution
    by_reason: dict[str, list[dict]] = defaultdict(list)
    for t in live:
        by_reason[t.get("exit_reason", "?") or "?"].append(t)
    ordered = sorted(by_reason.items(), key=lambda kv: -sum(r.get("net_pnl", 0) or 0 for r in kv[1]))
    _print_table(
        "EXIT REASON DISTRIBUTION (sorted by total $)",
        [(k, _stats(v)) for k, v in ordered],
    )

    # 3. Hold time vs net result
    by_hold: dict[str, list[dict]] = defaultdict(list)
    for t in live:
        by_hold[_hold_bucket(t.get("hold_seconds"))].append(t)
    _print_table(
        "HOLD TIME vs NET RESULT",
        [(k, _stats(by_hold[k])) for k in _HOLD_ORDER if by_hold[k]],
    )


if __name__ == "__main__":
    main()
