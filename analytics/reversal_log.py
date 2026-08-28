"""
Klaus — Reversal Candidate Logger

Shadow-observes late-window reversal opportunities: markets where a dominant
token (ask ≥ 0.70) has the underlying spot price moving *against* it in the
final 30–90 seconds. Tracks the underdog token price with no capital at risk.

Goal: accumulate n≥30 observations before considering live trades.

Output: logs/reversal_cands.jsonl

Analysis:
    python3 analytics/reversal_log.py

Key questions answered:
    - How often does the underdog actually flip (resolve ≥ 0.80)?
    - What delta magnitude predicts a flip?
    - What underdog entry price range has the best hypothetical PnL?
    - How quickly do flips manifest? (10s vs 30s price trajectory)
"""
from __future__ import annotations

import json
import os

_LOG = "logs/reversal_cands.jsonl"

_FEE_EXTREME = 0.0142   # round-trip fee at extreme odds (<0.30 or >0.70)


def log_reversal_cand(
    *,
    ts: float,
    asset: str,
    dominant_side: str,
    dominant_ask: float,
    underdog_token_id: str,
    underdog_ask: float,
    delta_pct: float,
    remaining_s: float,
    window_seconds: int,
    ask_at_10s: float | None = None,
    ask_at_20s: float | None = None,
    ask_at_30s: float | None = None,
    ask_at_window_end: float | None = None,
) -> None:
    """Append one reversal candidate observation to the log."""

    would_flip = (
        ask_at_window_end is not None and ask_at_window_end >= 0.80
    )

    # Hypothetical net PnL if we had entered at underdog_ask, held to window end
    hypothetical_pnl: float | None = None
    if ask_at_window_end is not None and underdog_ask > 0:
        gross_pct = (ask_at_window_end - underdog_ask) / underdog_ask
        # Fee: (entry_notional + exit_notional) * fee_rate per $1 stake
        exit_notional_pct = ask_at_window_end / underdog_ask
        fee_pct = (1.0 + exit_notional_pct) * _FEE_EXTREME
        hypothetical_pnl = round(gross_pct - fee_pct, 4)

    # Peak price seen across all snapshots (for "could we have TP'd early?" analysis)
    snaps = [a for a in [ask_at_10s, ask_at_20s, ask_at_30s, ask_at_window_end]
             if a is not None]
    peak_ask = max(snaps) if snaps else None
    peak_gain_pct = (
        round((peak_ask - underdog_ask) / underdog_ask, 4)
        if peak_ask is not None and underdog_ask > 0
        else None
    )

    record = {
        "ts": round(ts, 2),
        "asset": asset,
        "dominant_side": dominant_side,
        "dominant_ask": round(dominant_ask, 4),
        "underdog_token_id": underdog_token_id[:20],
        "underdog_ask": round(underdog_ask, 4),
        "delta_pct": round(delta_pct, 4),       # % move against dominant
        "remaining_s": round(remaining_s, 1),
        "window_seconds": window_seconds,
        # price trajectory after detection
        "ask_at_10s": ask_at_10s,
        "ask_at_20s": ask_at_20s,
        "ask_at_30s": ask_at_30s,
        "ask_at_window_end": ask_at_window_end,
        "peak_ask": round(peak_ask, 4) if peak_ask else None,
        "peak_gain_pct": peak_gain_pct,
        # outcome
        "would_flip": would_flip,
        "hypothetical_pnl": hypothetical_pnl,
    }

    os.makedirs("logs", exist_ok=True)
    with open(_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Analysis CLI  (python3 analytics/reversal_log.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from datetime import datetime, timezone

    if not os.path.exists(_LOG):
        print(f"No reversal log yet: {_LOG}")
        print("Run the bot — candidates are recorded automatically.")
        sys.exit(0)

    rows = [json.loads(l) for l in open(_LOG) if l.strip()]
    if not rows:
        print("Reversal log is empty.")
        sys.exit(0)

    resolved = [r for r in rows if r.get("ask_at_window_end") is not None]
    pending  = len(rows) - len(resolved)

    print(f"\n{'='*62}")
    print(f"  REVERSAL CANDIDATE ANALYSIS")
    print(f"  {len(rows)} total  |  {len(resolved)} resolved  |  {pending} pending")
    print(f"{'='*62}")

    if not resolved:
        print("  No resolved candidates yet.")
        sys.exit(0)

    flips = [r for r in resolved if r.get("would_flip")]
    flip_rate = len(flips) / len(resolved)
    pnls = [r["hypothetical_pnl"] for r in resolved if r.get("hypothetical_pnl") is not None]
    avg_pnl = sum(pnls) / len(pnls) if pnls else None

    print(f"\n  Flip rate (underdog→≥0.80):  {flip_rate:.0%}  ({len(flips)}/{len(resolved)})")
    if avg_pnl is not None:
        print(f"  Avg hypothetical PnL/unit:   {avg_pnl:+.2%}")

    # By asset
    print(f"\n  By asset:")
    by_asset: dict = {}
    for r in resolved:
        by_asset.setdefault(r["asset"], []).append(r)
    for asset, group in sorted(by_asset.items()):
        fr = sum(1 for r in group if r.get("would_flip")) / len(group)
        pnl_g = [r["hypothetical_pnl"] for r in group if r.get("hypothetical_pnl") is not None]
        avg_g = sum(pnl_g) / len(pnl_g) if pnl_g else None
        avg_str = f"{avg_g:+.2%}" if avg_g is not None else "n/a"
        print(f"    {asset:<6}  flip={fr:.0%}  avg_pnl={avg_str}  n={len(group)}")

    # By delta magnitude bucket
    print(f"\n  By |delta| vs dominant:")
    buckets = [
        ("0.05–0.10%", 0.05, 0.10),
        ("0.10–0.15%", 0.10, 0.15),
        ("0.15–0.25%", 0.15, 0.25),
        ("0.25%+",     0.25, 999),
    ]
    for label, lo, hi in buckets:
        g = [r for r in resolved if lo <= abs(r.get("delta_pct", 0)) < hi]
        if not g:
            continue
        fr = sum(1 for r in g if r.get("would_flip")) / len(g)
        pnl_g = [r["hypothetical_pnl"] for r in g if r.get("hypothetical_pnl") is not None]
        avg_g = sum(pnl_g) / len(pnl_g) if pnl_g else None
        avg_str = f"{avg_g:+.2%}" if avg_g is not None else "n/a"
        print(f"    δ {label:<12}  flip={fr:.0%}  avg_pnl={avg_str}  n={len(g)}")

    # By underdog entry price bucket
    print(f"\n  By underdog entry price:")
    price_buckets = [
        ("0.10–0.20", 0.10, 0.20),
        ("0.20–0.30", 0.20, 0.30),
        ("0.30–0.40", 0.30, 0.40),
    ]
    for label, lo, hi in price_buckets:
        g = [r for r in resolved if lo <= r.get("underdog_ask", 0) < hi]
        if not g:
            continue
        fr = sum(1 for r in g if r.get("would_flip")) / len(g)
        pnl_g = [r["hypothetical_pnl"] for r in g if r.get("hypothetical_pnl") is not None]
        avg_g = sum(pnl_g) / len(pnl_g) if pnl_g else None
        avg_str = f"{avg_g:+.2%}" if avg_g is not None else "n/a"
        print(f"    ask {label}  flip={fr:.0%}  avg_pnl={avg_str}  n={len(g)}")

    # By remaining time
    print(f"\n  By remaining time at detection:")
    time_buckets = [
        ("30–45s",  30,  45),
        ("45–60s",  45,  60),
        ("60–75s",  60,  75),
        ("75–90s",  75,  90),
    ]
    for label, lo, hi in time_buckets:
        g = [r for r in resolved if lo <= r.get("remaining_s", 0) < hi]
        if not g:
            continue
        fr = sum(1 for r in g if r.get("would_flip")) / len(g)
        print(f"    rem {label}  flip={fr:.0%}  n={len(g)}")

    # Recent observations
    print(f"\n  Recent candidates (last 10):")
    print(f"  {'time':<8} {'asset':<6} {'dom':<4} {'dom_ask':<8} {'udg_ask':<8} "
          f"{'δ%':<8} {'rem':<6} {'end_ask':<8} {'flip'}")
    for r in rows[-10:]:
        ts_str = datetime.fromtimestamp(r["ts"], tz=timezone.utc).strftime("%H:%M:%S")
        end_ask = r.get("ask_at_window_end")
        end_str = f"{end_ask:.3f}" if end_ask is not None else "---"
        flip = "YES" if r.get("would_flip") else ("NO" if end_ask is not None else "...")
        print(
            f"  {ts_str:<8} {r['asset']:<6} {r['dominant_side']:<4} "
            f"{r['dominant_ask']:.3f}   {r['underdog_ask']:.3f}   "
            f"{r['delta_pct']:+.3f}  {r['remaining_s']:.0f}s   "
            f"{end_str:<8} {flip}"
        )

    print()
