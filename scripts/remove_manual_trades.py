#!/usr/bin/env python3
"""
Remove manually-added fake trade records from trades.jsonl.
Targets records with token_id starting with 'manual_recovery_' — these were
added by add_missing_trades.py but have fabricated entry/exit/edge data.

Run from Klaus root:
    python3 scripts/remove_manual_trades.py
"""
import json
import os

TRADES_FILE = "logs/trades.jsonl"

if not os.path.exists(TRADES_FILE):
    print(f"Not found: {TRADES_FILE}")
    raise SystemExit(1)

kept, removed = [], []
with open(TRADES_FILE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            if d.get("token_id", "").startswith("manual_recovery_"):
                removed.append(d.get("trade_id", "?"))
            else:
                kept.append(line)
        except Exception:
            kept.append(line)

if not removed:
    print("Nothing to remove.")
    raise SystemExit(0)

with open(TRADES_FILE, "w") as f:
    for line in kept:
        f.write(line + "\n")

for tid in removed:
    print(f"REMOVED {tid}")
print(f"\nDone — removed {len(removed)} record(s), kept {len(kept)}.")
