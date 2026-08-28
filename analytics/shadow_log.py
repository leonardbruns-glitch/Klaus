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



# ---------------------------------------------------------------------------
# Simulate actual bot exit logic on a price sequence
# ---------------------------------------------------------------------------

# Bot exit parameters — keep in sync with config.py / risk/manager.py
_SL_EARLY = 0.35          # -35% SL for first 150s of hold
_SL_LATE = 0.10           # -10% SL after 150s (tightens near window end)
_TP_STAGE1 = 0.20         # +20% TP triggers stage-1 (60% sold)
_HARD_EXIT_S = 180        # hard exit at 180s regardless of PnL
_STAKE = 3.0              # base stake — used only for fee calculation
_FEE_EXTREME = 0.0142     # round-trip fee rate for extreme odds (<0.30 or >0.70)
_FEE_MIDDLE = 0.0312      # round-trip fee rate for fat-middle (0.30–0.70)


def _simulate_exit(
    entry_ask: float,
    checkpoints: list,   # list of (hold_seconds: float, ask: float | None)
    window_seconds: int = 300,
    elapsed_pct: float = 0.0,
) -> dict:
    """
    Walk the price checkpoints and apply real bot exit logic:
      - SL: -35% for first 150s, -10% after that (mirrors dynamic_sl in risk/manager.py)
      - TP: +20% fires stage-1 (sells 60% at that price, 40% hard-exits at 180s)
      - Hard exit: 180s max hold, exits at whatever price exists then

    Returns dict with simulated_exit_reason, simulated_exit_price, simulated_net_pnl,
    would_win_with_sl (bool).

    NOTE: snapshots are sparse (30s, 60s, 120s, 180s). Between checkpoints we don't
    know if SL was briefly hit. This gives an optimistic bias — the real bot would
    stop-loss on intraperiod dips the shadow monitor misses. Accept this limitation;
    it still beats the old "did price ever touch +20%?" measure.
    """
    if entry_ask <= 0:
        return {
            "simulated_exit_reason": None,
            "simulated_exit_price": None,
            "simulated_net_pnl": None,
            "would_win_with_sl": None,
        }

    tp_price = entry_ask * (1 + _TP_STAGE1)
    stage1_exit_price = None
    stage1_hold_s = None

    for hold_s, ask in checkpoints:
        if ask is None:
            continue

        # Which SL applies at this hold time?
        sl_pct = _SL_LATE if hold_s > 150 else _SL_EARLY
        sl_price = entry_ask * (1 - sl_pct)

        if stage1_exit_price is None:
            # Pre-stage-1: check TP first, then SL
            if ask >= tp_price:
                stage1_exit_price = ask
                stage1_hold_s = hold_s
                # Stage-1 fills 60% here; 40% rides to hard exit at 180s.
                # Continue loop to find 180s price for the remaining 40%.
            elif ask <= sl_price:
                # SL hit before TP — full loss
                exit_price = ask
                reason = f"STOP_LOSS_{int(sl_pct*100)}pct_at_{int(hold_s)}s"
                net_pnl = _calc_net_pnl(entry_ask, exit_price)
                return {
                    "simulated_exit_reason": reason,
                    "simulated_exit_price": round(exit_price, 4),
                    "simulated_net_pnl": round(net_pnl, 4),
                    "would_win_with_sl": False,
                }

        if hold_s >= _HARD_EXIT_S:
            # Hard exit reached
            if stage1_exit_price is not None:
                # Stage-1 already done (60% @ stage1_exit_price, 40% @ hard-exit price)
                gross_s1 = (stage1_exit_price - entry_ask) * 0.60
                gross_s2 = (ask - entry_ask) * 0.40
                gross = gross_s1 + gross_s2
                fee_rate = _FEE_EXTREME if (entry_ask < 0.30 or entry_ask > 0.70) else _FEE_MIDDLE
                exit_notional_s1 = stage1_exit_price * 0.60
                exit_notional_s2 = ask * 0.40
                fee_est = (entry_ask + exit_notional_s1 + exit_notional_s2) * fee_rate
                net_pnl = (gross - fee_est) * (_STAKE / entry_ask) if entry_ask > 0 else 0.0
                reason = f"PROFIT1_HARD_EXIT (s1@{int(stage1_hold_s)}s s2@{int(hold_s)}s)"
                return {
                    "simulated_exit_reason": reason,
                    "simulated_exit_price": round(stage1_exit_price * 0.60 + ask * 0.40, 4),
                    "simulated_net_pnl": round(net_pnl, 4),
                    "would_win_with_sl": net_pnl > 0,
                }
            else:
                # Hard exit, no TP hit — exit at current price
                exit_price = ask
                net_pnl = _calc_net_pnl(entry_ask, exit_price)
                won = net_pnl > 0
                return {
                    "simulated_exit_reason": f"HARD_EXIT_180s",
                    "simulated_exit_price": round(exit_price, 4),
                    "simulated_net_pnl": round(net_pnl, 4),
                    "would_win_with_sl": won,
                }

    # Ran out of checkpoints without hitting 180s or SL
    if stage1_exit_price is not None:
        # TP was hit but we don't have a 180s snapshot for the remaining 40%
        # Conservative: assume 40% exits at stage1_exit_price (no further gain/loss)
        net_pnl = _calc_net_pnl(entry_ask, stage1_exit_price)
        return {
            "simulated_exit_reason": f"PROFIT1_NO180S (s1@{int(stage1_hold_s)}s)",
            "simulated_exit_price": round(stage1_exit_price, 4),
            "simulated_net_pnl": round(net_pnl, 4),
            "would_win_with_sl": net_pnl > 0,
        }

    return {
        "simulated_exit_reason": "INCOMPLETE",
        "simulated_exit_price": None,
        "simulated_net_pnl": None,
        "would_win_with_sl": None,
    }


def _calc_net_pnl(entry_ask: float, exit_price: float) -> float:
    """Net PnL per $1 of stake at given entry/exit, after round-trip fees."""
    gross_pct = (exit_price - entry_ask) / entry_ask
    fee_rate = _FEE_EXTREME if (entry_ask < 0.30 or entry_ask > 0.70) else _FEE_MIDDLE
    exit_notional_pct = exit_price / entry_ask  # exit_notional relative to entry
    fee_pct = (1.0 + exit_notional_pct) * fee_rate
    return gross_pct - fee_pct


def log_shadow_result(
    block: SniperBlock,
    ask_at_30s: Optional[float],
    ask_at_60s: Optional[float],
    ask_at_120s: Optional[float],
    ask_at_window_end: Optional[float],
    llm_boost: float = 0.0,
    ask_at_180s: Optional[float] = None,
) -> None:
    """
    Write a completed shadow block record to logs/shadow_blocks.jsonl.

    ask_at_* fields are None if the token disappeared from the OB before that
    checkpoint (e.g. window expired or feed dropped).

    Simulates actual bot exit logic (TP/SL/hard-exit) on the price sequence rather
    than the old "did price ever touch +20%?" measure which ignored stop losses.
    """
    asks = [a for a in [ask_at_30s, ask_at_60s, ask_at_120s, ask_at_180s] if a is not None]
    max_ask = max(asks) if asks else None

    entry_ask = block.token_ask
    pnl_at_window_end = (
        round((ask_at_window_end - entry_ask) / entry_ask, 4)
        if ask_at_window_end is not None and entry_ask > 0
        else None
    )
    # Legacy signal — kept for backwards compatibility with existing analysis scripts
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

    # Realistic simulation: apply actual TP/SL/hard-exit logic to price sequence.
    # This is what the bot would actually have earned — not the peak price fantasy.
    checkpoints = []
    for hold_s, ask in [(30.0, ask_at_30s), (60.0, ask_at_60s),
                        (120.0, ask_at_120s), (180.0, ask_at_180s)]:
        if ask is not None:
            checkpoints.append((hold_s, ask))
    sim = _simulate_exit(
        entry_ask=entry_ask,
        checkpoints=checkpoints,
        window_seconds=block.window_seconds,
        elapsed_pct=block.elapsed_pct,
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
        "regime": block.regime,
        "token_ask": block.token_ask,
        "fair_value": round(block.fair_value, 4),
        "edge": round(block.edge, 4),
        "lag_remaining_pct": round(block.lag_remaining_pct, 3),
        "delta_pct": round(block.delta_pct, 4),
        "elapsed_pct": round(block.elapsed_pct, 3),
        "vpin": round(block.vpin, 3),
        # -- LLM opinion at block time (no API call — uses cached macro signal) --
        "llm_boost": round(llm_boost, 4),
        "llm_agrees": (
            (llm_boost > 0.02 and block.side == "YES")
            or (llm_boost < -0.02 and block.side == "NO")
            if llm_boost != 0.0 else None
        ),
        # -- raw price snapshots --
        "ask_at_30s": ask_at_30s,
        "ask_at_60s": ask_at_60s,
        "ask_at_120s": ask_at_120s,
        "ask_at_180s": ask_at_180s,
        "ask_at_window_end": ask_at_window_end,
        "max_ask_seen": round(max_ask, 4) if max_ask is not None else None,
        "pnl_if_entered": pnl_at_window_end,
        # -- legacy signals (kept for backwards compat) --
        "would_win_20pct": would_win_20pct,
        "would_win_25pct": would_win_25pct,
        # -- realistic simulation with actual exit logic --
        "would_win_with_sl": sim["would_win_with_sl"],
        "simulated_exit_reason": sim["simulated_exit_reason"],
        "simulated_exit_price": sim["simulated_exit_price"],
        "simulated_net_pnl": sim["simulated_net_pnl"],
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
        pnl_records = [r for r in rated if r.get("pnl_if_entered") is not None]
        avg_pnl = sum(r["pnl_if_entered"] for r in pnl_records) / len(pnl_records) if pnl_records else None
        print(f"\n  Overall WR (would +20%): {overall_wr:.0%} over {len(rated)} completed blocks")
        if avg_pnl is not None:
            print(f"  Avg P&L at window-end:   {avg_pnl:+.1%}  (n={len(pnl_records)} resolved)")
        else:
            print(f"  Avg P&L at window-end:   n/a (no resolved windows yet)")

        print(f"\n  By block reason:")
        by_reason: dict = {}
        for r in rated:
            by_reason.setdefault(r["block_reason"], []).append(r)
        for reason, group in sorted(by_reason.items()):
            wr = sum(r["would_win_20pct"] for r in group) / len(group)
            pnls = [r["pnl_if_entered"] for r in group if r.get("pnl_if_entered") is not None]
            avg = sum(pnls) / len(pnls) if pnls else None
            avg_str = f"{avg:+.1%}" if avg is not None else "n/a"
            print(f"    {reason:<22} WR={wr:.0%}  avg_pnl={avg_str}  n={len(group)}")

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
        print(f"  {'time':<8} {'asset':<6} {'side':<4} {'reason':<22} {'entry':<7} {'end':<7} {'pnl':<9} {'result'}")
        for r in rows[-10:]:
            ts = datetime.fromtimestamp(r["ts"], tz=timezone.utc).strftime("%H:%M:%S")
            entry_ask = r["token_ask"]
            end_ask   = r.get("ask_at_window_end")
            max_ask   = r.get("max_ask_seen")
            if end_ask is not None:
                pnl_str = f"{(end_ask - entry_ask) / entry_ask:+.1%}"
                end_str = f"{end_ask:.3f}"
            else:
                pnl_str = "pending"
                end_str = "---"
            if max_ask is not None and entry_ask > 0:
                peak_pnl = (max_ask - entry_ask) / entry_ask
                peak_str = f" (peak {peak_pnl:+.1%})"
            else:
                peak_str = ""
            result = (
                "WIN" if r.get("would_win_20pct") is True
                else "LOSS" if r.get("would_win_20pct") is False
                else "..."
            )
            print(f"  {ts:<8} {r['asset']:<6} {r['side']:<4} {r['block_reason']:<22} "
                  f"{entry_ask:.3f}  {end_str:<7} {pnl_str:<9}{peak_str}  {result}")
    else:
        print("  No completed blocks yet (monitors still running or no data).")

    print()
