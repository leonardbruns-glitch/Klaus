#!/usr/bin/env python3
"""
Klaus — 3-hour activity check (data primacy protocol).
Run via cron: 0 */3 * * * /root/Klaus/check_activity.py >> /root/Klaus/logs/activity_checks.log 2>&1
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TRADES_FILE  = Path(__file__).parent / "logs" / "trades.jsonl"
OUTPUT_FILE  = Path(__file__).parent / "logs" / "activity_checks.log"
BOT_LOG      = Path(__file__).parent / "logs" / "bot.log"

RUIN_FLOOR   = 100.0
DAILY_HALT   = 20.0
BANKROLL_START = 200.0

def load_trades():
    if not TRADES_FILE.exists():
        return []
    trades = []
    with open(TRADES_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return trades

def run_check():
    now_utc = datetime.now(timezone.utc)
    ts = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append("=" * 60)
    lines.append(f"ACTIVITY CHECK — {ts}")
    lines.append("=" * 60)

    trades = load_trades()

    # ── 1. Split live vs dry-run ───────────────────────────────
    live   = [t for t in trades if t.get("is_live") and t.get("entry_price", 0) > 0]
    dry    = [t for t in trades if not t.get("is_live")]
    orphan = [t for t in trades if t.get("is_live") and t.get("entry_price", 0) <= 0]

    lines.append(f"Trades: {len(live)} live | {len(dry)} dry-run | {len(orphan)} orphan/corrupt")

    if len(live) == 0:
        lines.append("⚠  NO LIVE TRADES — data collection mode, no analysis possible")
        lines.append("")
        _write(lines)
        return

    # ── 2. Core metrics ───────────────────────────────────────
    wins   = [t for t in live if t.get("net_pnl", 0) > 0]
    losses = [t for t in live if t.get("net_pnl", 0) <= 0]
    wr     = len(wins) / len(live) * 100

    gross_wins  = sum(t.get("net_pnl", 0) for t in wins)
    gross_loss  = abs(sum(t.get("net_pnl", 0) for t in losses))
    pf          = gross_wins / gross_loss if gross_loss > 0 else float("inf")
    avg_win     = gross_wins / len(wins) if wins else 0.0
    avg_loss    = gross_loss / len(losses) if losses else 0.0
    total_pnl   = sum(t.get("net_pnl", 0) for t in live)
    total_fees  = sum(t.get("fee_paid", 0) for t in live)
    fee_bleed   = total_fees / gross_wins * 100 if gross_wins > 0 else 0.0

    lines.append(f"")
    lines.append(f"PERFORMANCE (n={len(live)})")
    lines.append(f"  WR:           {wr:.1f}%  (wins={len(wins)} losses={len(losses)})")
    lines.append(f"  Profit factor:{pf:.2f}")
    lines.append(f"  Avg win:      ${avg_win:.3f}")
    lines.append(f"  Avg loss:     ${avg_loss:.3f}")
    lines.append(f"  Total PnL:    ${total_pnl:+.2f}")
    lines.append(f"  Fee bleed:    {fee_bleed:.1f}% of gross wins")

    # ── 3. Kill switch checks ─────────────────────────────────
    capital_est = BANKROLL_START + total_pnl
    lines.append(f"")
    lines.append(f"CAPITAL")
    lines.append(f"  Estimated:    ${capital_est:.2f}  (start=${BANKROLL_START:.0f} + PnL=${total_pnl:+.2f})")

    kill_triggered = False
    if capital_est < RUIN_FLOOR:
        lines.append(f"  🚨 RUIN FLOOR HIT: ${capital_est:.2f} < ${RUIN_FLOOR:.0f} — BOT SHOULD BE HALTED")
        kill_triggered = True

    # Daily PnL
    today_str = now_utc.strftime("%Y-%m-%d")
    today_trades = [t for t in live if
                    datetime.fromtimestamp(t.get("ts_close", 0), tz=timezone.utc).strftime("%Y-%m-%d") == today_str]
    daily_pnl = sum(t.get("net_pnl", 0) for t in today_trades)
    lines.append(f"  Today's PnL:  ${daily_pnl:+.2f}  ({len(today_trades)} trades today)")
    if daily_pnl <= -DAILY_HALT:
        lines.append(f"  🚨 DAILY HALT: ${daily_pnl:.2f} <= -${DAILY_HALT:.0f} — BOT SHOULD BE HALTED")
        kill_triggered = True

    if not kill_triggered:
        lines.append(f"  ✓ Kill switches: OK")

    # ── 4. WR by asset ───────────────────────────────────────
    lines.append(f"")
    lines.append(f"WR BY ASSET")
    for asset in ["BTC", "ETH", "SOL"]:
        at = [t for t in live if t.get("asset") == asset]
        if not at:
            lines.append(f"  {asset}: no trades")
            continue
        aw = [t for t in at if t.get("net_pnl", 0) > 0]
        lines.append(f"  {asset}: {len(aw)}/{len(at)} = {len(aw)/len(at)*100:.0f}% WR  PnL=${sum(t.get('net_pnl',0) for t in at):+.2f}")

    # ── 5. WR by hour UTC ────────────────────────────────────
    lines.append(f"")
    lines.append(f"WR BY HOUR UTC (top 5 by volume)")
    hour_buckets = {}
    for t in live:
        h = t.get("hour_utc", -1)
        hour_buckets.setdefault(h, []).append(t)
    sorted_hours = sorted(hour_buckets.items(), key=lambda x: -len(x[1]))[:5]
    for h, ht in sorted_hours:
        hw = [t for t in ht if t.get("net_pnl", 0) > 0]
        lines.append(f"  {h:02d}UTC: {len(hw)}/{len(ht)} = {len(hw)/len(ht)*100:.0f}% WR")

    # ── 6. WR by window size ─────────────────────────────────
    lines.append(f"")
    lines.append(f"WR BY WINDOW")
    for wsize, label in [(300, "5m"), (900, "15m")]:
        wt = [t for t in live if t.get("window_size_s", 0) == wsize]
        if not wt:
            continue
        ww = [t for t in wt if t.get("net_pnl", 0) > 0]
        lines.append(f"  {label}: {len(ww)}/{len(wt)} = {len(ww)/len(wt)*100:.0f}% WR  PnL=${sum(t.get('net_pnl',0) for t in wt):+.2f}")

    # ── 7. Data sufficiency warning ──────────────────────────
    lines.append(f"")
    if len(live) < 20:
        lines.append(f"⚠  n={len(live)} < 20 — DATA COLLECTION MODE. No strategy changes justified.")
    elif wr < 35 and len(live) >= 20:
        lines.append(f"🚨 WR={wr:.1f}% < 35% over n={len(live)} — KILL SWITCH THRESHOLD. Review required.")
    elif pf < 0.8 and len(live) >= 20:
        lines.append(f"🚨 Profit factor={pf:.2f} < 0.8 — KILL SWITCH THRESHOLD. Review required.")
    else:
        lines.append(f"✓ Sufficient data for analysis (n={len(live)})")

    # ── 8. Recent bot activity (last bot.log lines) ──────────
    lines.append(f"")
    lines.append(f"RECENT BOT ACTIVITY (last 5 log lines)")
    if BOT_LOG.exists():
        with open(BOT_LOG) as f:
            recent = f.readlines()[-5:]
        for l in recent:
            lines.append(f"  {l.rstrip()}")
    else:
        lines.append(f"  bot.log not found")

    lines.append("")
    _write(lines)

def _write(lines):
    output = "\n".join(lines) + "\n"
    print(output, end="")
    # Also append to dedicated log file
    with open(OUTPUT_FILE, "a") as f:
        f.write(output)

if __name__ == "__main__":
    run_check()
