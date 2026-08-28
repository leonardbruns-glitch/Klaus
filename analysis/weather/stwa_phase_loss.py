#!/usr/bin/env python3
"""STWA loss attribution by entry-timing and side (YES/NO).

Joins open WEATHER_STWA positions to ACTUAL Gamma resolution via the proven
repo helper (fetch_weather_events). Splits realized win-rate + PnL by SIDE and
by hours-to-local-midnight-close at entry.

Daily-high markets peak ~8-10h before local midnight:
    >12h to close   -> MORNING (pre-peak)
    6-12h to close  -> AFTNOON (around peak)
    <6h to close     -> EVENING (post-peak; daily max already locked)

Run:  python3 analysis/weather/stwa_phase_loss.py
Read-only. outcomePrices = [YES, NO]; side from bond_outcome_direction.
"""
import json, datetime as dt, os, sys
sys.path.insert(0, "/root/Klaus")
from analytics.backfill_weather_resolution import fetch_weather_events, parse_weather_question

raw = json.load(open("/root/Klaus/logs/positions.json"))
cont = raw.get("open_positions", raw) if isinstance(raw, dict) else {}
stwa = [v for v in cont.values()
        if isinstance(v, dict) and v.get("bond_entry_class") == "WEATHER_STWA"]
print("WEATHER_STWA positions:", len(stwa))

ots = [v["open_ts"] for v in stwa if v.get("open_ts")]
dmin = dt.datetime.utcfromtimestamp(min(ots)).strftime("%Y-%m-%d")
dmax = (dt.datetime.utcfromtimestamp(max(ots)) + dt.timedelta(days=3)).strftime("%Y-%m-%d")
print("fetching Gamma weather events %s .. %s ..." % (dmin, dmax))
token_map, cond_map = fetch_weather_events(dmin, dmax)
print("  gamma: %d tokens, %d conditions" % (len(token_map), len(cond_map)))

def phase_of(hrs):
    if hrs is None: return "?"
    if hrs > 12:  return "MORNING"
    if hrs >= 6:  return "AFTNOON"
    return "EVENING"

cells = {}
city_side = {}              # (city, side) -> [wins, n, pnl]   for the loser hunt
unresolved = nomatch = noside = 0
for v in stwa:
    e = cond_map.get(v.get("condition_id")) or token_map.get(str(v.get("token_id")))
    if not e:
        nomatch += 1; continue
    p = e.get("outcomePrices") or []
    if not e.get("closed") or len(p) < 2:
        unresolved += 1; continue
    try:
        yes, no = float(p[0]), float(p[1])
    except Exception:
        unresolved += 1; continue
    if max(yes, no) < 0.99:
        unresolved += 1; continue
    raw_side = (v.get("bond_outcome_direction") or "").lower()
    side = {"up": "YES", "down": "NO"}.get(raw_side)
    if side is None:
        noside += 1; continue
    win = (yes >= 0.99) if side == "YES" else (no >= 0.99)
    px = float(v.get("entry_price") or 0)
    sh = float(v.get("shares") or v.get("remaining_shares") or 0)
    pnl = sh * ((1.0 if win else 0.0) - px)

    meta = parse_weather_question(e.get("question", ""))
    city = meta.get("weather_city") or "?"
    d = meta.get("weather_date")
    hrs = None
    if d and v.get("open_ts"):
        try:
            end = dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()
            hrs = (end - v["open_ts"]) / 3600.0
        except Exception:
            hrs = None
    ph = phase_of(hrs)

    for key in [(ph, side), (ph, "ALL"), ("ALL", side), ("ALL", "ALL")]:
        c = cells.setdefault(key, [0, 0, 0.0])
        c[0] += 1 if win else 0; c[1] += 1; c[2] += pnl
    cs = city_side.setdefault((city, side), [0, 0, 0.0])
    cs[0] += 1 if win else 0; cs[1] += 1; cs[2] += pnl

print("\n=== STWA resolved attribution: timing-to-close x side ===")
print("(MORNING >12h pre-close | AFTNOON 6-12h | EVENING <6h post-peak)")
print("%-8s %-4s %11s %6s %11s" % ("phase", "side", "wins/n", "WR%", "pnl$"))
order = {"MORNING": 0, "AFTNOON": 1, "EVENING": 2, "?": 3, "ALL": 4}
for key in sorted(cells.keys(), key=lambda k: (order.get(k[0], 9), k[1])):
    w, n, pl = cells[key]
    print("%-8s %-4s %7d/%-4d %5.0f%% %+11.2f" % (key[0], key[1], w, n, 100*w/max(n,1), pl))

tot = cells.get(("ALL", "ALL"), [0, 0, 0])
print("\nresolved:%d  unresolved/open:%d  no_gamma_match:%d  no_side:%d"
      % (tot[1], unresolved, nomatch, noside))

print("\n=== worst city x side cells by PnL (resolved) ===")
print("%-16s %-4s %9s %6s %10s" % ("city", "side", "wins/n", "WR%", "pnl$"))
for (city, side), (w, n, pl) in sorted(city_side.items(), key=lambda x: x[1][2])[:12]:
    print("%-16s %-4s %5d/%-3d %5.0f%% %+10.2f" % (city, side, w, n, 100*w/max(n,1), pl))
print("\nNOTE: cells with n<100 are trend-only, not a decision (CLAUDE.md).")
