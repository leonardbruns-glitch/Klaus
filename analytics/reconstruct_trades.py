#!/usr/bin/env python3
"""
Reconstruct trades.jsonl from bot.log for the period when log_trade() was
silently failing (TypeError from invalid kwargs).

Parses actual bot.log line types:
  - "TERMINAL ENTRY SOL/YES [5m] | ask=0.8700 rem=44s | stake=$4.35"
  - "EXIT SOL BUY_YES | reason=BOND_TRAIL_TP | PnL=$+0.205 | capital=$15.41 | streak=1"
  - "PATH_CLASS SOL/BUY_YES [SMOOTH_RUNNER] | conf=3 | ..."

Correlates ENTRY→EXIT pairs by asset+side within the same 5m window,
reconstructs minimal trade records and writes to logs/trades_recovered.jsonl.

Usage:
    python3 analytics/reconstruct_trades.py [--dry-run] [--since "2026-04-25 11:44"]

After reviewing:
    cat logs/trades_recovered.jsonl >> logs/trades.jsonl
"""

import re, json, sys, os, datetime, time

DRY_RUN   = "--dry-run" in sys.argv
SINCE_ARG = None
for i, a in enumerate(sys.argv):
    if a == "--since" and i + 1 < len(sys.argv):
        SINCE_ARG = sys.argv[i + 1]

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, "logs", "bot.log")
OUT_PATH = os.path.join(ROOT, "logs", "trades_recovered.jsonl")
TRD_PATH = os.path.join(ROOT, "logs", "trades.jsonl")

# ── load already-logged trade timestamps to avoid duplicates ─────────────────
existing_ts = set()
if os.path.exists(TRD_PATH):
    with open(TRD_PATH) as f:
        for l in f:
            if l.strip():
                try:
                    r = json.loads(l)
                    existing_ts.add(round(float(r.get("ts_open", 0)), 0))
                except Exception:
                    pass

# ── helpers ──────────────────────────────────────────────────────────────────
def _parse_line_ts(prefix: str) -> float:
    """Parse the log timestamp prefix '2026-04-25 11:44:32' → unix ts."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)', prefix)
        if m:
            try:
                return datetime.datetime.strptime(m.group(1), fmt) \
                    .replace(tzinfo=datetime.timezone.utc).timestamp()
            except ValueError:
                continue
    return 0.0

def _f(s):
    if not s or s in ("—", "?", "None", ""):
        return 0.0
    try:
        return float(s.replace("$", "").replace("%", "").replace("+", ""))
    except Exception:
        return 0.0

since_ts = 0.0
if SINCE_ARG:
    try:
        since_ts = datetime.datetime.strptime(SINCE_ARG, "%Y-%m-%d %H:%M") \
                        .replace(tzinfo=datetime.timezone.utc).timestamp()
    except Exception:
        pass

# ── regexes ──────────────────────────────────────────────────────────────────
# TERMINAL ENTRY SOL/YES [5m] | ask=0.8700 rem=44s | stake=$4.35
RE_ENTRY = re.compile(
    r'TERMINAL ENTRY (\w+)/(YES|NO) \[(\d+m)\] \| ask=([0-9.]+) rem=([0-9.]+)s \| stake=\$([0-9.]+)'
)
# EXIT SOL BUY_YES | reason=BOND_TRAIL_TP | PnL=$+0.205 | capital=$15.41 | streak=1
RE_EXIT = re.compile(
    r'EXIT (\w+) (BUY_YES|BUY_NO) \| reason=(\S+) \| PnL=\$([+-]?[0-9.]+) \| capital=\$([0-9.]+)'
)
# PATH_CLASS SOL/BUY_YES [SMOOTH_RUNNER] | conf=3 | ...
RE_PATH = re.compile(
    r'PATH_CLASS (\w+)/(BUY_YES|BUY_NO) \[([A-Z_]+)\] \| conf=(\d+)'
)

# ── parse log ────────────────────────────────────────────────────────────────
# Pending entries: (asset, side) → list of entry dicts (multiple positions possible)
pending: dict = {}   # key=(asset,side) → [entry_dict, ...]
path_map: dict = {}  # key=(asset,direction) → path_class (overwritten, keep last)
recovered: list = []
counter = 90000

with open(LOG_PATH) as f:
    for raw in f:
        line = raw.strip()
        ts = _parse_line_ts(line)

        m = RE_ENTRY.search(line)
        if m:
            asset, side, wlabel, ask_s, rem_s, stake_s = m.groups()
            ask = float(ask_s)
            rem = float(rem_s)
            stake = float(stake_s)
            key = (asset, side)
            pending.setdefault(key, []).append({
                "ts_open": ts,
                "asset": asset,
                "side": side,
                "wlabel": wlabel,
                "ask": ask,
                "rem": rem,
                "stake": stake,
            })
            continue

        m = RE_PATH.search(line)
        if m:
            asset, direction, pc, conf = m.groups()
            path_map[(asset, direction)] = pc
            continue

        m = RE_EXIT.search(line)
        if m:
            asset, direction, reason, pnl_s, cap_s = m.groups()
            side = "YES" if direction == "BUY_YES" else "NO"
            key = (asset, side)
            entries = pending.get(key, [])
            if not entries:
                continue  # no matching open TERMINAL entry

            # Pop the oldest matching entry (FIFO)
            entry = entries.pop(0)
            if not entries:
                pending.pop(key, None)

            net_pnl = float(pnl_s)
            cap_after = float(cap_s)
            ep = entry["ask"]
            ts_open = entry["ts_open"]
            stake = entry["stake"]

            if ts_open == 0.0:
                continue
            if since_ts and ts_open < since_ts:
                continue
            if round(ts_open, 0) in existing_ts:
                continue

            shares = round(stake / ep, 4) if ep > 0 else 0.0
            # Estimate fee: gross - net. We don't have gross directly.
            # Estimate exit_price from net_pnl: net ≈ gross - fee ≈ (xp-ep)*shares - fee
            # Use a rough 2% round-trip fee on stake as fallback
            fee_est = round(stake * 0.02, 4)
            gross_est = round(net_pnl + fee_est, 4)
            xp_est = round(ep + gross_est / shares, 4) if shares > 0 else ep

            pc = path_map.get((asset, direction), "")
            hold_s = round(ts - ts_open, 1) if ts > ts_open else 0.0

            counter += 1
            record = {
                "trade_id":          f"REC{counter:05d}_{asset}_{int(ts_open)}",
                "token_id":          f"recovered_{asset}_{side}_{int(ts_open)}",
                "asset":             asset,
                "direction":         direction,
                "market_type":       "updown",
                "signal_source":     "BOND",
                "ts_open":           round(ts_open, 3),
                "ts_close":          round(ts, 3),
                "entry_price":       ep,
                "exit_price":        xp_est,
                "stake":             stake,
                "shares":            shares,
                "gross_pnl":         gross_est,
                "fee_paid":          fee_est,
                "net_pnl":           net_pnl,
                "slippage_entry":    0.04,
                "slippage_exit":     0.0,
                "exit_reason":       reason,
                "hold_seconds":      hold_s,
                "hour_utc":          int(datetime.datetime.utcfromtimestamp(ts_open).hour),
                "max_price_seen":    0.0,
                "min_price_seen":    0.0,
                "max_favourable_pct": 0.0,
                "max_adverse_pct":   0.0,
                "t_fav_s":           0.0,
                "t_adv_s":           0.0,
                "mae_bounce_10s_pct": 0.0,
                "entry_snap_30s_pct": 0.0,
                "entry_snap_60s_pct": 0.0,
                "path_class":        pc,
                "bond_entry_class":  "TERMINAL",
                "bond_macro_regime": "TERMINAL",
                "window_size_s":     int(entry["wlabel"].replace("m","")) * 60,
                "capital_after":     cap_after,
                "capital_before":    round(cap_after - net_pnl, 2),
                "is_live":           True,
                "consecutive_wins_at_entry": 0,
                "_recovered":        True,
                "_exit_price_estimated": True,
            }
            recovered.append(record)

# ── output ───────────────────────────────────────────────────────────────────
print(f"Found {len(recovered)} recoverable trades "
      f"({'DRY RUN — not writing' if DRY_RUN else f'writing to {OUT_PATH}'})")

wins  = sum(1 for r in recovered if r["net_pnl"] > 0)
total = len(recovered)
pnl   = sum(r["net_pnl"] for r in recovered)
print(f"WR={wins/max(1,total)*100:.1f}%  net=${pnl:+.2f}  n={total}")

by_asset = {}
for r in recovered:
    a = r["asset"]
    by_asset.setdefault(a, []).append(r["net_pnl"])
for a, pnls in sorted(by_asset.items()):
    w = sum(1 for p in pnls if p > 0)
    print(f"  {a}: n={len(pnls)} WR={w/len(pnls)*100:.0f}% sum=${sum(pnls):+.2f}")

if pending:
    print(f"\n[warn] {sum(len(v) for v in pending.values())} TERMINAL ENTRY lines had no matching EXIT:")
    for (asset, side), entries in pending.items():
        print(f"  {asset}/{side}: {len(entries)} unmatched")

if not DRY_RUN and recovered:
    with open(OUT_PATH, "w") as f:
        for r in recovered:
            f.write(json.dumps(r) + "\n")
    print(f"\nWritten to {OUT_PATH}")
    print("NOTE: exit_price and fees are ESTIMATED (fee ~2% round-trip of stake).")
    print(f"Review, then run:  cat {OUT_PATH} >> {TRD_PATH}")
