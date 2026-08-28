"""
Backfill LDA trade PnL in trades.jsonl.

Bugs fixed:
  1. BOND_SETTLED (exit=0.0): Redeemer didn't track LDA → all wins logged as losses.
     Fix: fetch Binance kline for window, determine true outcome.
  2. LDA_KLINE_WIN (exit=0.99): token auto-redeems at $1.00 not $0.99.
     Fix: exit_price=1.0, recalculate gross/net_pnl.

Run on VPS where trades.jsonl lives.
FEE_RATE: Polymarket charges entry fee only on auto-redemptions (no exit fee).
"""

import json
import math
import os
import shutil
import time
import urllib.request
from pathlib import Path

TRADES_FILE = Path("/root/Klaus/logs/trades.jsonl")
FEE_RATE = 0.02  # entry-side only for auto-redemptions

def fetch_kline(asset: str, window_end_ts: float, window_s: int = 300) -> tuple[bool | None, float, float]:
    """Return (kline_went_up, kline_open, kline_close) or (None, 0, 0) on error."""
    sym_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
    sym = sym_map.get(asset.upper())
    if not sym:
        return None, 0.0, 0.0
    interval = "5m" if window_s == 300 else "15m"
    wstart_ms = int((window_end_ts - window_s) * 1000)
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={sym}&interval={interval}&startTime={wstart_ms}&limit=1")
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            kl = json.loads(r.read())
        if kl and len(kl[0]) >= 5:
            kl_open  = float(kl[0][1])
            kl_close = float(kl[0][4])
            return kl_close >= kl_open, kl_open, kl_close
    except Exception as e:
        print(f"  kline fetch failed for {asset} wend={window_end_ts}: {e}")
    return None, 0.0, 0.0

def window_end_from_ts_open(ts_open: float, window_s: int = 300) -> float:
    """Compute window_end_ts from entry timestamp (next window boundary)."""
    return math.ceil(ts_open / window_s) * window_s

def main():
    print("Loading trades.jsonl ...", flush=True)
    lines = TRADES_FILE.read_text().splitlines()
    trades = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            trades.append(json.loads(line))
        except Exception:
            trades.append({"_raw": line})

    print(f"  {len(trades)} records total")

    lda_live = [t for t in trades if isinstance(t, dict) and
                t.get("is_live") and t.get("signal_source") == "LDA" and "trade_id" in t]
    print(f"  {len(lda_live)} LDA live trades")

    from collections import Counter
    reasons = Counter(t.get("exit_reason") for t in lda_live)
    print("  Exit reasons:", dict(reasons))

    # Trades to backfill
    bond_settled = [t for t in lda_live if t.get("exit_reason") == "BOND_SETTLED"]
    kline_wins   = [t for t in lda_live if t.get("exit_reason") == "LDA_KLINE_WIN"]
    ghost_pos    = [t for t in lda_live if t.get("exit_reason") == "GHOST_POSITION"]
    print(f"\nTo process: BOND_SETTLED={len(bond_settled)}, LDA_KLINE_WIN={len(kline_wins)}, GHOST_POSITION={len(ghost_pos)}")

    # Build index for fast lookup
    trade_index = {t.get("trade_id"): i for i, t in enumerate(trades)
                   if isinstance(t, dict) and "trade_id" in t}

    fixed_count = 0
    win_flip = 0
    kline_fix = 0

    print("\n--- Fixing BOND_SETTLED (kline check) ---", flush=True)
    for t in bond_settled:
        tid = t.get("trade_id")
        asset = t.get("asset", "")
        direction = t.get("bond_outcome_direction", "up")
        ep = float(t.get("entry_price", 0))
        shares = float(t.get("shares", 0))
        stake = float(t.get("stake", 0))
        fee_paid = float(t.get("fee_paid", stake * FEE_RATE))
        ts_open = float(t.get("ts_open", 0))
        window_s = int(t.get("window_size_s", 300) or 300)

        # Compute window_end_ts
        wend = window_end_from_ts_open(ts_open, window_s)

        kl_up, kl_open, kl_close = fetch_kline(asset, wend, window_s)
        if kl_up is None:
            print(f"  SKIP {tid} — kline unavailable")
            continue

        bet_up = (direction == "up")
        is_win = (bet_up == kl_up)

        if is_win:
            new_exit_price = 1.0
            new_gross = (1.0 - ep) * shares
            new_net   = new_gross - fee_paid
            new_reason = "LDA_KLINE_WIN"
            win_flip += 1
            print(f"  WIN {tid} {asset} bet={direction} kl={kl_open:.2f}->{kl_close:.2f} "
                  f"ep={ep:.4f} net: {t.get('net_pnl'):.4f} → {new_net:.4f}")
        else:
            # Confirm loss is correctly recorded
            new_exit_price = 0.0
            new_gross = -stake
            new_net   = -stake - fee_paid
            new_reason = "BOND_SETTLED"

        idx = trade_index.get(tid)
        if idx is not None:
            trades[idx]["exit_price"] = new_exit_price
            trades[idx]["gross_pnl"]  = round(new_gross, 4)
            trades[idx]["net_pnl"]    = round(new_net, 4)
            trades[idx]["exit_reason"] = new_reason
            fixed_count += 1
        time.sleep(0.05)  # rate-limit Binance API

    print(f"\n  BOND_SETTLED: {win_flip} flipped to WIN, {len(bond_settled)-win_flip} confirmed losses")

    print("\n--- Fixing LDA_KLINE_WIN exit_price (0.99 → 1.0) ---", flush=True)
    for t in kline_wins:
        tid = t.get("trade_id")
        ep = float(t.get("entry_price", 0))
        shares = float(t.get("shares", 0))
        old_exit = float(t.get("exit_price", 0.99))
        if abs(old_exit - 1.0) < 0.001:
            continue  # already correct
        fee_paid = float(t.get("fee_paid", t.get("stake", 0) * FEE_RATE))
        new_gross = (1.0 - ep) * shares
        new_net   = new_gross - fee_paid
        idx = trade_index.get(tid)
        if idx is not None:
            trades[idx]["exit_price"] = 1.0
            trades[idx]["gross_pnl"]  = round(new_gross, 4)
            trades[idx]["net_pnl"]    = round(new_net, 4)
            kline_fix += 1
            fixed_count += 1
    print(f"  {kline_fix} LDA_KLINE_WIN records corrected (exit 0.99→1.0)")

    print("\n--- Fixing GHOST_POSITION (kline check) ---", flush=True)
    ghost_fixed = 0
    for t in ghost_pos:
        tid = t.get("trade_id")
        asset = t.get("asset", "")
        direction = t.get("bond_outcome_direction", "up")
        ep = float(t.get("entry_price", 0))
        shares = float(t.get("shares", 0))
        stake = float(t.get("stake", 0))
        fee_paid = float(t.get("fee_paid", stake * FEE_RATE))
        ts_open = float(t.get("ts_open", 0))
        window_s = int(t.get("window_size_s", 300) or 300)
        wend = window_end_from_ts_open(ts_open, window_s)

        kl_up, kl_open, kl_close = fetch_kline(asset, wend, window_s)
        if kl_up is None:
            continue

        bet_up = (direction == "up")
        is_win = (bet_up == kl_up)

        if is_win:
            new_exit_price = 1.0
            new_gross = (1.0 - ep) * shares
            new_net   = new_gross - fee_paid
            new_reason = "LDA_KLINE_WIN"
            ghost_fixed += 1
            print(f"  WIN {tid} {asset} bet={direction} kl={kl_open:.2f}->{kl_close:.2f} "
                  f"ep={ep:.4f} net: {t.get('net_pnl'):.4f} → {new_net:.4f}")
        else:
            new_exit_price = 0.0
            new_gross = -stake
            new_net   = -stake - fee_paid
            new_reason = "GHOST_RESOLVED_NO"

        idx = trade_index.get(tid)
        if idx is not None:
            trades[idx]["exit_price"] = new_exit_price
            trades[idx]["gross_pnl"]  = round(new_gross, 4)
            trades[idx]["net_pnl"]    = round(new_net, 4)
            trades[idx]["exit_reason"] = new_reason
            fixed_count += 1
        time.sleep(0.05)

    print(f"  GHOST_POSITION: {ghost_fixed} flipped to WIN")

    print(f"\nTotal records fixed: {fixed_count}")

    # Backup + write
    backup = str(TRADES_FILE) + ".bak_pre_lda_fix"
    shutil.copy(str(TRADES_FILE), backup)
    print(f"Backup written to {backup}")

    with open(str(TRADES_FILE), "w") as fh:
        for t in trades:
            if isinstance(t, dict) and "_raw" not in t:
                fh.write(json.dumps(t) + "\n")
            elif isinstance(t, dict) and "_raw" in t:
                fh.write(t["_raw"] + "\n")
    print(f"Fixed trades.jsonl written.")

    # Summary
    print("\n=== SUMMARY ===")
    fixed_trades = [t for t in trades if isinstance(t, dict) and
                    t.get("is_live") and t.get("signal_source") == "LDA" and "trade_id" in t]
    wins = [t for t in fixed_trades if float(t.get("net_pnl", 0)) > 0]
    losses = [t for t in fixed_trades if float(t.get("net_pnl", 0)) <= 0]
    total_net = sum(float(t.get("net_pnl", 0)) for t in fixed_trades)
    wr = len(wins) / len(fixed_trades) if fixed_trades else 0
    print(f"LDA live trades: {len(fixed_trades)}")
    print(f"WR: {wr:.1%}  ({len(wins)} wins / {len(losses)} losses)")
    print(f"Total net PnL: ${total_net:.2f}")
    reasons_after = Counter(t.get("exit_reason") for t in fixed_trades)
    print("Exit reasons after fix:", dict(reasons_after))

if __name__ == "__main__":
    main()
