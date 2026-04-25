#!/usr/bin/env python3
"""
Reconstruct trades.jsonl from bot.log for the period when log_trade() was
silently failing (TypeError from invalid kwargs).

Usage:
    python3 analytics/reconstruct_trades.py [--dry-run] [--since "2026-04-25 11:44"]

Writes recovered records to logs/trades_recovered.jsonl (never touches trades.jsonl
directly). After reviewing, manually append:
    cat logs/trades_recovered.jsonl >> logs/trades.jsonl
"""

import re, json, sys, os, datetime, time

DRY_RUN  = "--dry-run" in sys.argv
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
def _f(s):
    """Parse float or return 0.0 for — / None / empty."""
    if not s or s in ("—", "?", "None", ""):
        return 0.0
    try:
        return float(s.replace("$", "").replace("%", "").replace("+", ""))
    except Exception:
        return 0.0

def _pct(s):
    """Parse a value like '+91.6%@55s' → (91.6, 55)."""
    if not s or s in ("—", "?"):
        return 0.0, 0.0
    m = re.match(r'([+-]?\d+\.?\d*)%(?:@(\d+)s)?', s)
    if m:
        return float(m.group(1)), float(m.group(2) or 0)
    return 0.0, 0.0

def _ts(date_str, time_str):
    """Convert '04-25' + '11:44' → unix timestamp (year 2026)."""
    try:
        month, day = date_str.split("-")
        hour, minute = time_str.split(":")
        dt = datetime.datetime(2026, int(month), int(day),
                               int(hour), int(minute), 0,
                               tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0

# ── trade line regex ─────────────────────────────────────────────────────────
# Matches lines like:
# W 04-25 11:44 SOL YES 5m BON | ep=0.8898 xp=0.9108 | ...
TRADE_RE = re.compile(
    r'([WL])\s+(\d{2}-\d{2})\s+(\d{2}:\d{2})\s+'
    r'(\w+)\s+(YES|NO)\s+(\d+m)\s+(\w+)\s+\|'
    r'.*?ep=([0-9.]+).*?xp=([0-9.]+)'
)

# Field extractors (applied to the full line)
def _get(line, key):
    m = re.search(rf'{re.escape(key)}=([^\s|]+)', line)
    return m.group(1) if m else "—"

def _get_snap(line, label):
    """Extract from_entry +30s=-98.8% style."""
    m = re.search(rf'\+30s=([+-]?[\d.]+)%', line[line.find(label):] if label in line else "")
    return float(m.group(1)) if m else 0.0

# ── parse ────────────────────────────────────────────────────────────────────
since_ts = 0.0
if SINCE_ARG:
    try:
        since_ts = datetime.datetime.strptime(SINCE_ARG, "%Y-%m-%d %H:%M") \
                        .replace(tzinfo=datetime.timezone.utc).timestamp()
    except Exception:
        pass

recovered = []
counter   = 90000  # start trade IDs high to avoid collision

with open(LOG_PATH) as f:
    for raw in f:
        line = raw.strip()
        # strip logger prefix if present
        m_prefix = re.search(r'\]\s+([WL]\s+\d{2}-\d{2}\s+\d{2}:\d{2}\s+\w+)', line)
        if m_prefix:
            line = line[m_prefix.start(1):]

        m = TRADE_RE.search(line)
        if not m:
            continue

        wl, date_s, time_s, asset, side, window, src = (
            m.group(1), m.group(2), m.group(3),
            m.group(4), m.group(5), m.group(6), m.group(7),
        )
        ep = float(m.group(8))
        xp = float(m.group(9))

        ts_open  = _ts(date_s, time_s)
        if ts_open == 0.0:
            continue
        if since_ts and ts_open < since_ts:
            continue
        if round(ts_open, 0) in existing_ts:
            continue  # already in trades.jsonl

        hold_s   = _f(_get(line, "hold").replace("s",""))
        ts_close = ts_open + hold_s

        stake   = _f(_get(line, "stake"))
        fee     = _f(_get(line, "fee"))
        gross   = _f(_get(line, "gross").replace("$",""))
        net     = _f(_get(line, "net"))
        cap_after = _f(_get(line, "cap"))

        # shares = stake / ep
        shares = round(stake / ep, 4) if ep > 0 else 0.0

        adv_s   = _get(line, "adv")
        fav_s   = _get(line, "fav")
        adv_pct, t_adv = _pct(adv_s)
        fav_pct, t_fav = _pct(fav_s)
        bounce  = _f(_get(line, "bounce10").replace("%",""))

        # from_entry snaps
        fe_section = line[line.find("from_entry:"):] if "from_entry:" in line else ""
        snap30 = 0.0; snap60 = 0.0
        m30 = re.search(r'\+30s=([+-]?[\d.]+)%', fe_section)
        m60 = re.search(r'\+60s=([+-]?[\d.]+)%', fe_section)
        if m30: snap30 = float(m30.group(1))
        if m60: snap60 = float(m60.group(1))

        exit_reason = line.split("|")[-1].strip().split()[-1] if "|" in line else ""
        hr_utc  = int(time_s.split(":")[0])
        pc      = _get(line, "pc")
        zone    = _get(line, "zone")
        slip_e  = _f(_get(line, "slip_e"))
        vel     = _f(_get(line, "vel").replace("%",""))
        cwin    = int(_f(_get(line, "cwin")))

        # max_price and min_price from ep + pcts
        max_price = round(ep * (1 + fav_pct / 100), 4) if fav_pct else ep
        min_price = round(ep * (1 - adv_pct / 100), 4) if adv_pct else ep

        counter += 1
        record = {
            "trade_id":          f"REC{counter:05d}_{asset}_{int(ts_open)}",
            "token_id":          f"recovered_{asset}_{side}_{int(ts_open)}",
            "asset":             asset,
            "direction":         f"BUY_{side}",
            "market_type":       "updown",
            "signal_source":     "BOND",
            "ts_open":           round(ts_open, 3),
            "ts_close":          round(ts_close, 3),
            "entry_price":       ep,
            "exit_price":        xp,
            "stake":             stake,
            "shares":            shares,
            "gross_pnl":         gross,
            "fee_paid":          fee,
            "net_pnl":           net,
            "slippage_entry":    slip_e,
            "slippage_exit":     0.0,
            "exit_reason":       exit_reason,
            "hold_seconds":      hold_s,
            "hour_utc":          hr_utc,
            "max_price_seen":    max_price,
            "min_price_seen":    min_price,
            "max_favourable_pct": round(fav_pct, 2),
            "max_adverse_pct":   round(adv_pct, 2),
            "t_fav_s":           t_fav,
            "t_adv_s":           t_adv,
            "mae_bounce_10s_pct": bounce,
            "entry_snap_30s_pct": snap30,
            "entry_snap_60s_pct": snap60,
            "path_class":        pc if pc != "—" else "",
            "bond_entry_class":  zone if zone != "—" else "",
            "window_size_s":     int(window.replace("m","")) * 60,
            "capital_after":     cap_after,
            "capital_before":    round(cap_after - net, 2),
            "is_live":           True,
            "consecutive_wins_at_entry": cwin,
            "_recovered":        True,
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

if not DRY_RUN and recovered:
    with open(OUT_PATH, "w") as f:
        for r in recovered:
            f.write(json.dumps(r) + "\n")
    print(f"\nWritten to {OUT_PATH}")
    print(f"Review, then run:  cat {OUT_PATH} >> {TRD_PATH}")
