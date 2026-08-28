"""
Backfill entered_correctly + kline_pnl in trades.jsonl using Binance 5m/15m klines.

Why: BOND_RESOLVED_NO and LDA_KLINE_WIN exits historically did NOT schedule
_track_post_exit (fixed in main.py 2026-05-16). Those rows have
kline_pnl == 0 and entered_correctly is None, which is undefined behavior
in analytics — many scripts mis-interpret kline_pnl=0 as "flat outcome"
and underreport real losses.

This script:
  1. Loads /root/Klaus/logs/trades.jsonl
  2. Identifies rows missing resolution (entered_correctly is None OR
     kline_pnl is None/0 AND exit_reason in unsold-set)
  3. For each, fetches the corresponding Binance 5m kline (cached per
     (asset, window_end)) and computes entered_correctly + kline_pnl
  4. Rewrites trades.jsonl in place with a .bak alongside

kline_pnl semantics match main.py _track_post_exit (line ~5791):
  entered_correctly  →  kline_pnl = shares * (1.0 - entry_price) - fee_paid
  not entered_correctly → kline_pnl = -stake - fee_paid

For SOLD exits (LDA_PT95, BOND_TIME_EXIT, etc) we still patch
entered_correctly from the kline (useful for analysis) but leave kline_pnl
to match the unsold semantics so the field is comparable across rows.

Usage:  python3 analytics/backfill_kline_resolution.py [--dry-run]
"""

import json
import math
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_PATH = os.path.join(_REPO_ROOT, "logs", "trades.jsonl")
DRY_RUN = "--dry-run" in sys.argv

_SYMBOL = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}


def fetch_klines_range(symbol, interval, start_ms, end_ms):
    out = {}
    cur = start_ms
    while cur < end_ms:
        params = urllib.parse.urlencode(
            {"symbol": symbol, "interval": interval,
             "startTime": cur, "endTime": end_ms, "limit": 1000}
        )
        url = f"https://api.binance.com/api/v3/klines?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "klaus-backfill"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        if not data:
            break
        for row in data:
            ot = row[0] // 1000
            step = 300 if interval == "5m" else 900
            we = ot + step
            out[we] = {"open": float(row[1]), "close": float(row[4])}
        cur = data[-1][0] + (300_000 if interval == "5m" else 900_000)
        if len(data) < 1000:
            break
        time.sleep(0.1)  # be polite
    return out


def main() -> None:
    if not os.path.exists(TRADES_PATH):
        print(f"trades.jsonl not found at {TRADES_PATH}")
        return

    with open(TRADES_PATH) as f:
        lines = f.readlines()

    parsed = []
    for ln in lines:
        try:
            parsed.append(json.loads(ln))
        except Exception:
            parsed.append(None)

    # Identify rows that need patching
    needed = defaultdict(set)  # (asset, ws) -> set(window_end_ts)
    candidate_idx = []
    now = time.time()
    for i, t in enumerate(parsed):
        if t is None:
            continue
        if t.get("is_live") is not True:
            continue
        ts = t.get("ts_open")
        if not isinstance(ts, (int, float)) or ts <= 0:
            continue
        # need patch if entered_correctly is missing/None
        if t.get("entered_correctly") is not None:
            continue
        ws = int(t.get("window_size_s") or 300)
        we = int(math.ceil(ts / ws) * ws)
        if we <= 0 or we > now + 60:
            continue  # invalid or window still open
        needed[(t.get("asset"), ws)].add(we)
        candidate_idx.append((i, ws, we))

    print(f"candidates needing resolution: {len(candidate_idx)}")
    if not candidate_idx:
        return

    # Fetch klines per (asset, interval)
    kcache = {}
    for (asset, ws), weset in needed.items():
        sym = _SYMBOL.get(asset)
        if not sym:
            continue
        interval = "5m" if ws == 300 else ("15m" if ws == 900 else None)
        if interval is None:
            print(f"unsupported ws={ws} for {asset}, skipping {len(weset)} rows")
            continue
        wlist = sorted(weset)
        start_ms = (wlist[0] - ws - 60) * 1000
        end_ms = (wlist[-1] + 60) * 1000
        print(f"fetching {asset}/{interval} klines for {len(weset)} windows "
              f"[{wlist[0]} → {wlist[-1]}]...")
        kcache[(asset, ws)] = fetch_klines_range(sym, interval, start_ms, end_ms)
        print(f"  got {len(kcache[(asset, ws)])} klines")

    patched = 0
    unresolved = 0
    unsold_set = {"BOND_RESOLVED_NO", "LDA_KLINE_WIN", "BOND_EXPIRED_UNSOLD"}
    for i, ws, we in candidate_idx:
        t = parsed[i]
        kmap = kcache.get((t["asset"], ws), {})
        k = kmap.get(we)
        if not k:
            unresolved += 1
            continue
        kline_dir = "up" if k["close"] > k["open"] else (
            "down" if k["close"] < k["open"] else "flat")
        bet = t.get("bond_outcome_direction")
        if not bet:  # None or empty string — unknowable direction
            unresolved += 1
            continue
        correct = (bet == kline_dir)
        t["entered_correctly"] = bool(correct)
        t["window_outcome_price"] = 1.0 if (
            (bet == "up" and kline_dir == "up")
            or (bet == "down" and kline_dir == "down")
        ) else 0.0
        shares = t.get("shares") or 0.0
        ep = t.get("entry_price") or 0.0
        stake = t.get("stake") or (ep * shares)
        fee = t.get("fee_paid") or 0.0
        if correct:
            t["kline_pnl"] = round(shares * (1.0 - ep) - fee, 4)
        else:
            t["kline_pnl"] = round(-stake - fee, 4)
        # For unsold exits, the bot booked net_pnl as a loss at exit_price=0;
        # the real economic outcome is kline_pnl. Annotate for analysis clarity.
        if t.get("exit_reason") in unsold_set:
            t["unsold_resolution_source"] = "kline_backfill_2026-05-16"
        patched += 1

    print(f"patched: {patched}  unresolved: {unresolved}  total candidates: "
          f"{len(candidate_idx)}")

    if DRY_RUN:
        print("DRY RUN — not writing")
        return

    bak = TRADES_PATH + ".bak"
    shutil.copy2(TRADES_PATH, bak)
    print(f"backup written: {bak}")

    # Atomic rewrite: bot may be appending. Read trailing lines after our
    # initial slurp, append them unchanged, then rename into place.
    initial_size = os.path.getsize(bak)
    tmp = TRADES_PATH + ".tmp"
    with open(tmp, "w") as f:
        for i, t in enumerate(parsed):
            if t is None:
                f.write(lines[i])
            else:
                f.write(json.dumps(t) + "\n")
        # Append any new lines the bot wrote while we were processing
        current_size = os.path.getsize(TRADES_PATH)
        if current_size > initial_size:
            with open(TRADES_PATH, "rb") as src:
                src.seek(initial_size)
                tail = src.read()
                f.write(tail.decode("utf-8", errors="replace"))
                print(f"appended {len(tail)} bytes written during backfill")
    os.replace(tmp, TRADES_PATH)
    print(f"rewrote {TRADES_PATH}")


if __name__ == "__main__":
    main()
