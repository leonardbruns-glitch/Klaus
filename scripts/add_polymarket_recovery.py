"""
Manually recover 3 confirmed live trades from Polymarket UI data.
These trades were executed by the bot but not logged due to the
STAGE2_RESOLVED / NOOB_EXTERNALLY_SOLD bugs (now fixed).

Source: Polymarket activity feed, 2026-04-03 4:30-5:00 AM ET
Run once on the MacBook: python3 scripts/add_polymarket_recovery.py
"""
import json
import os
import sys

TRADE_LOG = "logs/trades.jsonl"

# ---------------------------------------------------------------------------
# Source: Polymarket UI screenshots, 2026-04-03
# All amounts are authoritative USDC from the Polymarket activity feed.
# Entry/exit prices are computed as amount / shares.
# Net PnL = sum(sell amounts) - buy amount (fees already reflected in amounts).
# ---------------------------------------------------------------------------

TRADES = [
    {
        # ETH Down 4:30-4:45 AM ET (08:30-08:45 UTC)
        # Bought 4.8 shares for $2.55; sold 4.5 @ $0.61 (+$2.76) + 0.3 @ $0.70 (+$0.22)
        "token_id":    "ui_recovery_ethno_20260403_0830",
        "asset":       "ETH",
        "direction":   "BUY_NO",
        "market_type": "updown",
        "signal_source": "SNIPER",
        "exit_reason": "STAGE2_RESOLVED",
        "ts_open":     1775205060,   # 08:31 UTC (approx entry)
        "ts_close":    1775205840,   # 08:44 UTC (approx final sell)
        "entry_price": round(2.55 / 4.8, 4),   # 0.5313
        "exit_price":  round(2.98 / 4.8, 4),   # 0.6208  (2.76+0.22 = 2.98 received)
        "stake":       2.55,
        "shares":      4.8,
        "gross_pnl":   round(2.98 - 2.55, 4),  # 0.43
        "fee_paid":    0.0,   # fees already embedded in Polymarket amounts
        "net_pnl":     0.43,  # authoritative: sum(sells) - buy = 2.98 - 2.55
        "slippage_entry": 0.0,
        "slippage_exit":  0.0,
        "hold_seconds": 780,
        "hour_utc":    8,
        "window_size_s": 900,    # 15-minute window
        "is_live":     True,
        "sniper_side": "NO",
        "note": "UI recovery: bot executed but STAGE2_RESOLVED bug suppressed record. "
                "Amounts from Polymarket activity feed 2026-04-03.",
    },
    {
        # SOL Down 4:30-4:45 AM ET (08:30-08:45 UTC)
        # Bought 6.7 shares for $2.59; sold 6.5 @ $0.45 (+$2.94) + 0.2 @ $0.51 (+$0.08)
        "token_id":    "ui_recovery_solno_20260403_0830",
        "asset":       "SOL",
        "direction":   "BUY_NO",
        "market_type": "updown",
        "signal_source": "SNIPER",
        "exit_reason": "STAGE2_RESOLVED",
        "ts_open":     1775205120,   # 08:32 UTC
        "ts_close":    1775205780,   # 08:43 UTC
        "entry_price": round(2.59 / 6.7, 4),   # 0.3866
        "exit_price":  round(3.02 / 6.7, 4),   # 0.4507  (2.94+0.08 = 3.02 received)
        "stake":       2.59,
        "shares":      6.7,
        "gross_pnl":   round(3.02 - 2.59, 4),  # 0.43
        "fee_paid":    0.0,
        "net_pnl":     0.43,
        "slippage_entry": 0.0,
        "slippage_exit":  0.0,
        "hold_seconds": 660,
        "hour_utc":    8,
        "window_size_s": 900,
        "is_live":     True,
        "sniper_side": "NO",
        "note": "UI recovery: bot executed but STAGE2_RESOLVED bug suppressed record. "
                "Amounts from Polymarket activity feed 2026-04-03.",
    },
    {
        # ETH Down 4:45-5:00 AM ET (08:45-09:00 UTC)
        # Bought 5.8 shares for $3.00; sold 3.5 @ $0.66 (+$2.33) + 2.0 @ $0.72 (+$1.43) + 0.3 @ $0.79 (+$0.20)
        "token_id":    "ui_recovery_ethno_20260403_0845",
        "asset":       "ETH",
        "direction":   "BUY_NO",
        "market_type": "updown",
        "signal_source": "SNIPER",
        "exit_reason": "STAGE2_RESOLVED",
        "ts_open":     1775205960,   # 08:46 UTC
        "ts_close":    1775206680,   # 08:58 UTC
        "entry_price": round(3.00 / 5.8, 4),   # 0.5172
        "exit_price":  round(3.96 / 5.8, 4),   # 0.6828  (2.33+1.43+0.20 = 3.96 received)
        "stake":       3.00,
        "shares":      5.8,
        "gross_pnl":   round(3.96 - 3.00, 4),  # 0.96
        "fee_paid":    0.0,
        "net_pnl":     0.96,
        "slippage_entry": 0.0,
        "slippage_exit":  0.0,
        "hold_seconds": 720,
        "hour_utc":    8,
        "window_size_s": 900,
        "is_live":     True,
        "sniper_side": "NO",
        "note": "UI recovery: bot executed but STAGE2_RESOLVED bug suppressed record. "
                "Amounts from Polymarket activity feed 2026-04-03.",
    },
    {
        # SOL Down 7:30-7:45 AM ET (11:30-11:45 UTC) — STOP LOSS
        # Bought 4.8 shares for $2.65; sold 4.0 @ $0.46 (+$1.85) + 0.5 @ $0.26 (+$0.13) + 0.3 @ $0.20 (+$0.06)
        "token_id":    "ui_recovery_solno_20260403_1130",
        "asset":       "SOL",
        "direction":   "BUY_NO",
        "market_type": "updown",
        "signal_source": "SNIPER",
        "exit_reason": "STOP_LOSS",
        "ts_open":     1775216400,   # 11:40 UTC (approx entry)
        "ts_close":    1775216580,   # 11:43 UTC (approx final sell)
        "entry_price": round(2.65 / 4.8, 4),   # 0.5521
        "exit_price":  round(2.04 / 4.8, 4),   # 0.4250  (1.85+0.13+0.06 = 2.04 received)
        "stake":       2.65,
        "shares":      4.8,
        "gross_pnl":   round(2.04 - 2.65, 4),  # -0.61
        "fee_paid":    0.0,
        "net_pnl":     -0.61,
        "slippage_entry": 0.0,
        "slippage_exit":  0.0,
        "hold_seconds": 180,
        "hour_utc":    11,
        "window_size_s": 900,
        "is_live":     True,
        "sniper_side": "NO",
        "note": "UI recovery: EXTERNALLY_SOLD path had KeyError('bankroll') bug — record_trade crashed. "
                "Amounts from Polymarket activity feed 2026-04-03.",
    },
]

# ---------------------------------------------------------------------------

def load_max_counter(path):
    if not os.path.exists(path):
        return 0
    max_n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                tid = d.get("trade_id", "")
                if tid.startswith("T") and len(tid) >= 6:
                    try:
                        n = int(tid[1:6])
                        max_n = max(max_n, n)
                    except ValueError:
                        pass
            except json.JSONDecodeError:
                pass
    return max_n


def check_already_added(path):
    if not os.path.exists(path):
        return set()
    existing = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                existing.add(d.get("token_id", ""))
            except json.JSONDecodeError:
                pass
    return existing


def main():
    if not os.path.exists("logs"):
        print("ERROR: run from the Klaus project root (logs/ directory not found)")
        sys.exit(1)

    existing_token_ids = check_already_added(TRADE_LOG)
    counter = load_max_counter(TRADE_LOG)

    added = 0
    for trade in TRADES:
        if trade["token_id"] in existing_token_ids:
            print(f"SKIP (already present): {trade['token_id']}")
            continue

        counter += 1
        ts_open_int = int(trade["ts_open"])
        trade["trade_id"] = f"T{counter:05d}_{trade['asset']}_{ts_open_int}_UIREC"
        trade["capital_before"] = 0.0
        trade["capital_after"] = 0.0
        trade["heat_check_active"] = False
        trade["consecutive_wins_at_entry"] = 0

        with open(TRADE_LOG, "a") as f:
            f.write(json.dumps(trade) + "\n")

        print(f"ADDED {trade['trade_id']}: {trade['asset']} {trade['direction']} "
              f"entry={trade['entry_price']:.4f} exit={trade['exit_price']:.4f} "
              f"net_pnl=+${trade['net_pnl']:.2f}")
        added += 1

    print(f"\nDone: {added} trade(s) added to {TRADE_LOG}")
    if added > 0:
        print("Restart the bot to reload trades.jsonl into the report.")


if __name__ == "__main__":
    main()
