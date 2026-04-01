"""
Klaus — Shadow Block Logger

When the Window Sniper blocks a candidate trade, this module records what
actually happened to the token price afterward. Used to validate whether
block decisions are correct or are leaving profitable trades on the table.

Output: logs/shadow_blocks.jsonl
Each line is a JSON record with:
  - Block state at the moment of block (ask, FV, edge, lag_remaining, reason)
  - Ask snapshots at +30s, +60s, +120s, and at window close
  - Simulated P&L if we had entered at block_ask
  - Whether a +20% or +25% profit target would have been hit

Analysis workflow (after 50+ blocks):
  python3 -c "
  import json
  rows = [json.loads(l) for l in open('logs/shadow_blocks.jsonl')]
  wins = [r for r in rows if r.get('would_win_20pct')]
  print(f'{len(wins)}/{len(rows)} blocked trades would have won +20%')
  by_reason = {}
  for r in rows:
      by_reason.setdefault(r['block_reason'], []).append(r.get('would_win_20pct', False))
  for reason, results in by_reason.items():
      wr = sum(results)/len(results)
      print(f'  {reason}: {wr:.0%} WR over {len(results)} blocks')
  "
"""
from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING, Optional

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from strategy.window_sniper import SniperBlock

_SHADOW_LOG = "logs/shadow_blocks.jsonl"


def log_shadow_result(
    block: SniperBlock,
    ask_at_30s: Optional[float],
    ask_at_60s: Optional[float],
    ask_at_120s: Optional[float],
    ask_at_window_end: Optional[float],
) -> None:
    """
    Write a completed shadow block record to logs/shadow_blocks.jsonl.

    ask_at_* fields are None if the token disappeared from the OB before that
    checkpoint (e.g. window expired or feed dropped).
    """
    asks = [a for a in [ask_at_30s, ask_at_60s, ask_at_120s] if a is not None]
    max_ask = max(asks) if asks else None

    entry_ask = block.token_ask
    pnl_at_window_end = (
        round((ask_at_window_end - entry_ask) / entry_ask, 4)
        if ask_at_window_end is not None and entry_ask > 0
        else None
    )
    would_win_20pct = (
        max_ask >= entry_ask * 1.20
        if max_ask is not None and entry_ask > 0
        else None
    )
    would_win_25pct = (
        max_ask >= entry_ask * 1.25
        if max_ask is not None and entry_ask > 0
        else None
    )

    record = {
        # -- block state --
        "ts": block.ts,
        "asset": block.asset,
        "side": block.side,
        "token_id": block.token_id,
        "window_end_ts": block.window_end_ts,
        "window_seconds": block.window_seconds,
        "block_reason": block.block_reason,
        "token_ask": block.token_ask,
        "fair_value": round(block.fair_value, 4),
        "edge": round(block.edge, 4),
        "lag_remaining_pct": round(block.lag_remaining_pct, 3),
        "delta_pct": round(block.delta_pct, 4),
        "elapsed_pct": round(block.elapsed_pct, 3),
        "vpin": round(block.vpin, 3),
        # -- counterfactual outcome --
        "ask_at_30s": ask_at_30s,
        "ask_at_60s": ask_at_60s,
        "ask_at_120s": ask_at_120s,
        "ask_at_window_end": ask_at_window_end,
        "max_ask_seen": round(max_ask, 4) if max_ask is not None else None,
        "pnl_if_entered": pnl_at_window_end,
        "would_win_20pct": would_win_20pct,
        "would_win_25pct": would_win_25pct,
    }

    os.makedirs("logs", exist_ok=True)
    with open(_SHADOW_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    import sys
    from datetime import datetime, timezone

    log_file = _SHADOW_LOG
    if not os.path.exists(log_file):
        print(f"No shadow log yet: {log_file}")
        print("Run the bot — blocks are recorded automatically.")
        sys.exit(0)

    rows = [json.loads(l) for l in open(log_file) if l.strip()]
    if not rows:
        print("Shadow log is empty.")
        sys.exit(0)

    rated = [r for r in rows if r.get("would_win_20pct") is not None]
    unrated = len(rows) - len(rated)

    print(f"\n{'='*60}")
    print(f"  SHADOW BLOCK ANALYSIS  ({len(rows)} blocks, {unrated} still pending)")
    print(f"{'='*60}")

    if rated:
        overall_wr = sum(r["would_win_20pct"] for r in rated) / len(rated)
        avg_pnl = sum(r["pnl_if_entered"] for r in rated if r.get("pnl_if_entered") is not None) / len(rated)
        print(f"\n  Overall WR (would +20%): {overall_wr:.0%} over {len(rated)} completed blocks")
        print(f"  Avg P&L if entered:      {avg_pnl:+.1%}")

        print(f"\n  By block reason:")
        by_reason: dict = {}
        for r in rated:
            by_reason.setdefault(r["block_reason"], []).append(r)
        for reason, group in sorted(by_reason.items()):
            wr = sum(r["would_win_20pct"] for r in group) / len(group)
            pnls = [r["pnl_if_entered"] for r in group if r.get("pnl_if_entered") is not None]
            avg = sum(pnls) / len(pnls) if pnls else 0.0
            print(f"    {reason:<22} WR={wr:.0%}  avg_pnl={avg:+.1%}  n={len(group)}")

        print(f"\n  By asset:")
        by_asset: dict = {}
        for r in rated:
            by_asset.setdefault(r["asset"], []).append(r)
        for asset, group in sorted(by_asset.items()):
            wr = sum(r["would_win_20pct"] for r in group) / len(group)
            print(f"    {asset:<6}  WR={wr:.0%}  n={len(group)}")

        print(f"\n  Lag remaining vs WR:")
        buckets = {"0-20%": [], "20-40%": [], "40-60%": [], "60-80%": [], "80-100%": []}
        for r in rated:
            lag = r.get("lag_remaining_pct", 0) * 100
            if lag < 20:   buckets["0-20%"].append(r)
            elif lag < 40: buckets["20-40%"].append(r)
            elif lag < 60: buckets["40-60%"].append(r)
            elif lag < 80: buckets["60-80%"].append(r)
            else:           buckets["80-100%"].append(r)
        for bucket, group in buckets.items():
            if group:
                wr = sum(r["would_win_20pct"] for r in group) / len(group)
                print(f"    lag {bucket:<10}  WR={wr:.0%}  n={len(group)}")

        print(f"\n  Recent blocks (last 10):")
        print(f"  {'time':<8} {'asset':<6} {'side':<4} {'reason':<22} {'ask':<6} {'fv':<6} {'lag':<6} {'outcome'}")
        for r in rows[-10:]:
            ts = datetime.fromtimestamp(r["ts"], tz=timezone.utc).strftime("%H:%M:%S")
            outcome = (
                f"+{r['pnl_if_entered']:+.0%}" if r.get("pnl_if_entered") is not None
                else "pending"
            )
            win_flag = " WIN" if r.get("would_win_20pct") else (" LOSS" if r.get("would_win_20pct") is False else "")
            print(f"  {ts:<8} {r['asset']:<6} {r['side']:<4} {r['block_reason']:<22} "
                  f"{r['token_ask']:.3f}  {r['fair_value']:.3f}  {r.get('lag_remaining_pct',0):.0%}   "
                  f"{outcome}{win_flag}")
    else:
        print("  No completed blocks yet (monitors still running or no data).")

    print()
