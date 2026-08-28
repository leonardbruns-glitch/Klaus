#!/usr/bin/env python3
"""Sprint-30 ground-truth equity scoreboard (2026-07-03 → 2026-08-02).

Appends one JSON line/day to logs/sprint30_equity.jsonl:
  cash        — latest BANKROLL SYNC real cash (CLOB balance), NOT bankroll.json
  pos_value   — live position value from the Polymarket data-api (mark, not cost)
  equity      — cash + pos_value
  target      — the $10k/30d trajectory point for today (85 * (10085/85)^(d/30))

Mechanical only: no decisions, no LLM. The EVOLVE daily actuator and cloud
analysts read the ledger; humans read the trend. Cron: 23:50 UTC daily.
"""
import json, re, sys, time, urllib.request
from datetime import datetime, timezone

ROOT = "/root/Klaus"
WALLET = "0x21fBa7a743155A9cBE0e04b2C815bC954459842c"
SPRINT_START = datetime(2026, 7, 3, tzinfo=timezone.utc)
BASE_EQUITY = 85.0          # measured 2026-07-03 (cash 62.38 + positions)
TARGET_END = BASE_EQUITY + 10_000.0

def latest_cash() -> float | None:
    """Last free-USDC balance the keeper logged to bot.log."""
    # 2026-07-04 EVOLVE fix: the original "BANKROLL SYNC: ... cash=" pattern
    # matches no line bot.log has ever emitted — first run logged cash=null.
    # The keeper logs free USDC every ~60s as
    # "Polymarket USDC balance (actual): $74.4489"; parse that instead.
    pat = re.compile(r"Polymarket USDC balance \(actual\): \$([0-9.]+)")
    cash = None
    try:
        with open(f"{ROOT}/logs/bot.log", "rb") as f:
            f.seek(max(0, f.seek(0, 2) - 4_000_000))
            for line in f.read().decode(errors="replace").splitlines():
                m = pat.search(line)
                if m:
                    cash = float(m.group(1))
    except OSError:
        pass
    return cash

def live_position_value() -> float | None:
    total, off = 0.0, 0
    try:
        while True:
            url = (f"https://data-api.polymarket.com/positions?user={WALLET}"
                   f"&limit=500&offset={off}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            page = json.load(urllib.request.urlopen(req, timeout=30))
            for p in page:
                if not p.get("redeemable"):
                    total += float(p.get("currentValue") or 0.0)
                elif (p.get("currentValue") or 0) > 0.01:
                    total += float(p["currentValue"])   # unredeemed winner
            if len(page) < 500:
                break
            off += 500
    except Exception:
        return None
    return round(total, 2)

def main() -> None:
    now = datetime.now(timezone.utc)
    day = (now - SPRINT_START).total_seconds() / 86400.0
    growth = (TARGET_END / BASE_EQUITY) ** (min(day, 30.0) / 30.0)
    cash = latest_cash()
    pos = live_position_value()
    equity = round(cash + pos, 2) if (cash is not None and pos is not None) else None
    rec = {
        "ts_utc": now.isoformat(timespec="seconds"),
        "sprint_day": round(day, 2),
        "cash": cash,
        "pos_value": pos,
        "equity": equity,
        "target": round(BASE_EQUITY * growth, 2),
        "gap": (round(equity - BASE_EQUITY * growth, 2) if equity is not None else None),
    }
    with open(f"{ROOT}/logs/sprint30_equity.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))

if __name__ == "__main__":
    sys.exit(main())
