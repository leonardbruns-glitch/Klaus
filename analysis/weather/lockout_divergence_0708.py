"""
Lockout oracle-divergence study (pulled forward from the 07-13 slot) +
first MIN-lockout resolution validation. Read-only; no capital.

A) MAX family (metar_lockout shadow, 06-28..07-07):
   - WR of official-feed lockouts (official_running_max_c > bucket_hi_c_padded)
     by margin band x US/non-US. A locked bucket that resolved YES = oracle
     divergence event (the Moscow 07-06 class).
   - Executable subset: best NO ask in [0.50, 0.97] with depth > $1.

B) MIN family (metar_min_lockout shadow, same window):
   - Lockout = margin_c >= threshold (running_min already below bucket floor).
   - WR at resolution + executable capacity (no_ask, no_depth_usd).

Run on VPS: python3 analysis/weather/lockout_divergence_0708.py
"""
from __future__ import annotations
import glob
import json
import sys
from collections import defaultdict

sys.path.insert(0, "/root/Klaus")
from analytics.backfill_weather_resolution import fetch_weather_events

DATE_MIN = "2026-06-28"
CUTOFF = "2026-07-07"          # last fully-closed day
MAX_GLOB = "/root/Klaus/logs/shadow/hot/*/metar_lockout.jsonl"
MIN_GLOB = "/root/Klaus/logs/shadow/hot/*/metar_min_lockout.jsonl"

US_PREFIXES = ("K", "PH", "PA")   # CONUS + Hawaii + Alaska


def is_us(icao: str) -> bool:
    icao = icao or ""
    return icao.startswith("K") or icao.startswith("PH") or icao.startswith("PA")


def best_no_ask(r):
    nb = r.get("no_book") or {}
    ps = [a["price"] for a in nb.get("asks") or [] if a.get("size", 0) > 0]
    if r.get("no_ask_clob"):
        ps.append(r["no_ask_clob"])
    return min(ps) if ps else None


def yes_lost(entry):
    """True if NO resolved, False if YES resolved, None unresolved/ambiguous."""
    if not entry or not entry.get("closed"):
        return None
    p = entry.get("outcomePrices") or []
    try:
        yes = float(p[0])
    except Exception:
        return None
    if yes <= 0.01:
        return True
    if yes >= 0.99:
        return False
    return None


def wr_ci(w, n):
    """Wilson 95% lower/upper."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (c - h, c + h)


def main():
    token_map, cond_map = fetch_weather_events(DATE_MIN, CUTOFF)
    print(f"gamma: {len(token_map)} tokens, {len(cond_map)} conditions\n")

    # ── A) MAX family ────────────────────────────────────────────────────────
    first = {}          # (no_token_id, end_date) -> first LOCKED row
    first_exec = {}     # same, first locked + executable row
    for fp in sorted(glob.glob(MAX_GLOB)):
        for line in open(fp):
            try:
                r = json.loads(line)
            except Exception:
                continue
            ed = r.get("end_date")
            if not ed or not (DATE_MIN <= ed <= CUTOFF):
                continue
            orm = r.get("official_running_max_c")
            hi = r.get("bucket_hi_c_padded")
            if orm is None or hi is None or orm <= hi:
                continue           # not locked on the OFFICIAL feed
            key = (r.get("no_token_id"), ed)
            if key not in first or r["ts_s"] < first[key]["ts_s"]:
                first[key] = r
            na = best_no_ask(r)
            depth = r.get("no_ask_usd_at_clob_implied") or r.get("no_ask_usd_at_implied") or 0
            if na is not None and 0.50 <= na <= 0.97 and depth > 1:
                if key not in first_exec or r["ts_s"] < first_exec[key]["ts_s"]:
                    first_exec[key] = r

    print("=" * 70)
    print(f"A) MAX lockouts (official feed) {DATE_MIN}..{CUTOFF}: "
          f"unique locked buckets={len(first)}, executable={len(first_exec)}")
    print("=" * 70)
    for label, pool in (("ALL LOCKED", first), ("EXECUTABLE", first_exec)):
        stats = defaultdict(lambda: [0, 0])   # (us, margin_band) -> [wins, n]
        div_losses = []
        cap_usd = 0.0
        for (tok, ed), r in pool.items():
            cid = r.get("condition_id")
            w = yes_lost(cond_map.get(cid))
            if w is None:
                continue
            m = r["official_running_max_c"] - r["bucket_hi_c_padded"]
            mb = "<0.5" if m < 0.5 else "0.5-1" if m < 1 else ">=1"
            us = "US " if is_us(r.get("icao")) else "INTL"
            stats[(us, mb)][0] += 1 if w else 0
            stats[(us, mb)][1] += 1
            stats[(us, "ALL")][0] += 1 if w else 0
            stats[(us, "ALL")][1] += 1
            if not w:
                div_losses.append((r.get("city"), ed, round(m, 2),
                                   r.get("icao"), r.get("question", "")[:50]))
            if label == "EXECUTABLE":
                cap_usd += min(r.get("no_ask_usd_at_clob_implied") or 0, 50)
        print(f"\n--- {label} ---")
        for (us, mb) in sorted(stats):
            w, n = stats[(us, mb)]
            lo, hi_ = wr_ci(w, n)
            print(f"  {us} margin {mb:5s}: WR {w}/{n} = {100*w/max(n,1):.1f}%  "
                  f"CI [{100*lo:.1f}, {100*hi_:.1f}]")
        if label == "EXECUTABLE":
            days = len({ed for (_, ed) in pool})
            print(f"  capacity: ${cap_usd:.0f} total fillable (capped $50/bucket) "
                  f"over {days} days = ${cap_usd/max(days,1):.1f}/day")
        print(f"  DIVERGENCE LOSSES ({len(div_losses)}):")
        for d in div_losses[:15]:
            print("   ", d)

    # ── B) MIN family ────────────────────────────────────────────────────────
    firstm = {}
    firstm_exec = {}
    for fp in sorted(glob.glob(MIN_GLOB)):
        for line in open(fp):
            try:
                r = json.loads(line)
            except Exception:
                continue
            ed = r.get("end_date")
            if not ed or not (DATE_MIN <= ed <= CUTOFF):
                continue
            m = r.get("margin_c")
            if m is None or m < 0:
                continue
            key = (r.get("token_id"), ed)
            if key not in firstm or r["ts_s"] < firstm[key]["ts_s"]:
                firstm[key] = r
            na = r.get("no_ask")
            if na is not None and 0.50 <= na <= 0.97 and (r.get("no_depth_usd") or 0) > 1:
                if key not in firstm_exec or r["ts_s"] < firstm_exec[key]["ts_s"]:
                    firstm_exec[key] = r

    print("\n" + "=" * 70)
    print(f"B) MIN lockouts {DATE_MIN}..{CUTOFF}: "
          f"unique locked buckets={len(firstm)}, executable={len(firstm_exec)}")
    print("=" * 70)
    for label, pool in (("ALL LOCKED", firstm), ("EXECUTABLE", firstm_exec)):
        stats = defaultdict(lambda: [0, 0])
        losses = []
        cap_usd = 0.0
        nomatch = 0
        for (tok, ed), r in pool.items():
            entry = token_map.get(tok)
            if entry is None:
                nomatch += 1
                continue
            w = yes_lost(entry)
            if w is None:
                continue
            m = r.get("margin_c", 0)
            mb = "<0.5" if m < 0.5 else "0.5-1" if m < 1 else ">=1"
            us = "US " if is_us(r.get("icao")) else "INTL"
            stats[(us, mb)][0] += 1 if w else 0
            stats[(us, mb)][1] += 1
            stats[(us, "ALL")][0] += 1 if w else 0
            stats[(us, "ALL")][1] += 1
            if not w:
                losses.append((r.get("city"), ed, round(m, 2), r.get("icao"),
                               r.get("question", "")[:50]))
            if label == "EXECUTABLE":
                cap_usd += min(r.get("no_depth_usd") or 0, 50)
        print(f"\n--- {label} ---  (no_gamma_match={nomatch})")
        for (us, mb) in sorted(stats):
            w, n = stats[(us, mb)]
            lo, hi_ = wr_ci(w, n)
            print(f"  {us} margin {mb:5s}: WR {w}/{n} = {100*w/max(n,1):.1f}%  "
                  f"CI [{100*lo:.1f}, {100*hi_:.1f}]")
        if label == "EXECUTABLE":
            days = len({ed for (_, ed) in pool})
            print(f"  capacity: ${cap_usd:.0f} fillable (capped $50/bucket) "
                  f"over {days} days = ${cap_usd/max(days,1):.1f}/day")
        print(f"  LOSSES ({len(losses)}):")
        for d in losses[:15]:
            print("   ", d)


if __name__ == "__main__":
    main()
