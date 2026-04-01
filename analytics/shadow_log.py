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
import time
from dataclasses import asdict
from typing import Optional

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
