#!/usr/bin/env python3
"""
Daily-MINIMUM lockout capacity probe (READ-ONLY, external data only).

The lockout edge is currently harvested ONLY on daily-MAX markets (late-afternoon
lock). Daily-MIN markets exist on Polymarket and the bot ingests ZERO of them. The
min is set near dawn; once temp rises away from it the running-MIN is locked and all
buckets ABOVE it go NO-certain — in the MORNING, the dead window for max-lockout.

This probe measures the real opportunity BEFORE any build:
  • surface: how many open min-markets / cities / buckets
  • timing: when today's running-min was set (confirm the morning lock window)
  • lock state NOW: # buckets already NO-locked (running_min margin ≥0.5°C, mirror of max)
  • depth: fillable NO-ask $ on those locked buckets (the harvestable capacity)

Data: Gamma (markets/books) + Open-Meteo hourly (today's observed temp path).
No bot state touched, no orders.
"""
import json, re, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARAMS = json.load(open(ROOT / "config/stwa_params.json"))["stations"]
ORACLE_BLOCK_CITIES = {"hong-kong", "tokyo", "shenzhen", "singapore"}  # wrong-oracle (mirror M1β)
MARGIN = 0.5
UA = {"User-Agent": "Mozilla/5.0 (probe)"}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def _slug(city_title):
    s = city_title.strip().lower().replace(" ", "-")
    return {"nyc": "nyc", "hong-kong": "hong-kong"}.get(s, s)


def parse_bucket(q, is_f):
    """Return (lo, hi) in the market's native unit from a min-market question."""
    ql = q.lower()
    nums = [float(x) for x in re.findall(r'-?\d+\.?\d*', q)]
    # drop the trailing date numbers by keeping only temp-context numbers
    m_below = re.search(r'(-?\d+\.?\d*)\s*°?[cf]?\s*or below', ql)
    m_above = re.search(r'(-?\d+\.?\d*)\s*°?[cf]?\s*or above', ql)
    m_range = re.search(r'(-?\d+\.?\d*)\s*(?:-|to)\s*(-?\d+\.?\d*)\s*°?[cf]', ql)
    if m_below:  return (-999.0, float(m_below.group(1)))
    if m_above:  return (float(m_above.group(1)), 999.0)
    if m_range:  return (float(m_range.group(1)), float(m_range.group(2)))
    return None


def obs_today(lat, lon):
    """hourly temp (°C) for today UTC up to now -> list of (hour, temp)."""
    u = (f"https://api.open-meteo.com/v1/forecast?latitude={lat:.3f}&longitude={lon:.3f}"
         f"&hourly=temperature_2m&temperature_unit=celsius&forecast_days=1&timezone=UTC")
    d = _get(u)
    h = d.get("hourly", {})
    out = []
    now_h = time.gmtime().tm_hour
    for t, v in zip(h.get("time", []), h.get("temperature_2m", [])):
        hr = int(t[11:13])
        if v is not None and hr <= now_h:
            out.append((hr, float(v)))
    return out


def book_depth(token_id, side="asks"):
    """$ depth on the NO ask within 5c of best (fillable capacity)."""
    try:
        b = _get(f"https://clob.polymarket.com/book?token_id={token_id}")
    except Exception:
        return None, 0.0
    levels = b.get(side, []) or []
    if not levels:
        return None, 0.0
    px = sorted(float(l["price"]) for l in levels)
    best = px[0] if side == "asks" else max(float(l["price"]) for l in levels)
    usd = sum(float(l["price"]) * float(l["size"]) for l in levels
              if abs(float(l["price"]) - best) <= 0.05)
    return best, usd


def main():
    ev = _get("https://gamma-api.polymarket.com/public-search?q=lowest+temperature&limit_per_type=40")
    events = [e for e in ev.get("events", []) if not e.get("closed")]
    print(f"open daily-MIN events: {len(events)}  "
          f"(cities: {sorted(set(_slug(e['title'].split(' in ')[1].split(' on ')[0]) for e in events))})\n")

    tot_locked = tot_depth = 0
    n_probed = 0
    for e in events:
        title = e.get("title", "")
        try:
            city = _slug(title.split(" in ")[1].split(" on ")[0])
        except Exception:
            continue
        if "june 8" not in title.lower():       # probe TODAY only (in-flight)
            continue
        st = PARAMS.get(city)
        if not st:
            print(f"  {title:<45} — no station coords, skip"); continue
        blocked = city in ORACLE_BLOCK_CITIES
        is_f = st.get("unit", "C") == "F"
        try:
            obs = obs_today(st["lat"], st["lon"])
        except Exception as ex:
            print(f"  {title:<45} — obs fetch failed {ex}"); continue
        if not obs:
            print(f"  {title:<45} — no obs yet"); continue
        rmin_c = min(t for _, t in obs)
        rmin_hr = min(obs, key=lambda x: x[1])[0]
        # convert running min to native unit for bucket compare
        rmin = (rmin_c * 9 / 5 + 32) if is_f else rmin_c
        n_probed += 1

        locked = []
        for m in (e.get("markets", []) or []):
            bk = parse_bucket(m.get("question", ""), is_f)
            if not bk:
                continue
            lo, hi = bk
            # NO-locked when bucket sits ABOVE the running min by margin (min already below it)
            if lo - rmin >= MARGIN:
                toks = m.get("clobTokenIds")
                toks = json.loads(toks) if isinstance(toks, str) else (toks or [])
                no_tok = toks[1] if len(toks) > 1 else None
                no_ask, usd = book_depth(no_tok) if no_tok else (None, 0.0)
                locked.append((lo, hi, no_ask, usd))
        ldepth = sum(u for *_, u in locked)
        flag = " [ORACLE-BLOCKED]" if blocked else ""
        print(f"  {title:<45}{flag}")
        print(f"      running_min={rmin_c:.1f}°C set @ {rmin_hr:02d}h UTC | "
              f"NO-locked buckets={len(locked)}  fillable NO depth=${ldepth:.0f}")
        if not blocked:
            tot_locked += len(locked); tot_depth += ldepth

    print(f"\n  TODAY (June 8), oracle-clean cities probed: {n_probed}")
    print(f"  total NO-locked min buckets RIGHT NOW: {tot_locked}   "
          f"total fillable NO depth: ${tot_depth:.0f}")
    print("  (compare: max-lockout yields ~3-8 distinct positions/day. Min adds a")
    print("   MORNING window — combined ~2× the daily lock surface.)")


if __name__ == "__main__":
    main()
