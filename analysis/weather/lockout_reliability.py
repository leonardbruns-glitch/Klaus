"""
Lockout RELIABILITY discriminator (read-only) — "reliable crossing vs spike".

The metar_lockout shadow logs a candidate whenever the SPIKE-PRONE running_max_c
crosses a bucket ceiling. M1β lost on the ones where that crossing was a SYNOP/
sub-hourly spike the official METAR never honored (false lockout → NO loses).

This joins every candidate to ACTUAL Gamma resolution and asks: which features
predict a RELIABLE lockout (NO wins) vs a SPIKE (NO loses), BEFORE the official
METAR confirms? Features tested:

  asos_margin = asos_running_max_c - bucket_hi_padded   (official-quality margin)
  raw_margin  = running_max_c      - bucket_hi_padded   (spike-prone margin; old gate)
  raw_gap     = running_max_c - asos_running_max_c       (the SPIKE SIZE)

asos_running_max_c is only populated from 2026-05-28, so the scored window starts
there. Goal: a live gate that keeps WR >=~98% at high retained n — letting us act
on the sub-hourly feed early while rejecting the spikes.

Run: python3 analysis/weather/lockout_reliability.py
"""
from __future__ import annotations
import glob
import json
import sys
from collections import defaultdict

sys.path.insert(0, "/root/Klaus")
from analytics.backfill_weather_resolution import parse_weather_question, fetch_weather_events

DATE_MIN = "2026-05-28"        # first day asos_running_max_c is populated
CUTOFF   = "2026-06-04"        # last fully-closed local day to score
SHADOW_GLOB = "logs/shadow/hot/2026-*/metar_lockout.jsonl"
# Known non-WU / wrong-oracle stations (from prior D1 mismatch analysis)
KNOWN_BAD = {"hong-kong", "moscow", "istanbul", "tel-aviv"}


def norm_city(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-").replace("_", "-")


def best_no_ask(r):
    nb = r.get("no_book") or {}
    ps = [a["price"] for a in nb.get("asks") or [] if a.get("size", 0) > 0]
    if r.get("no_ask_clob"):
        ps.append(r["no_ask_clob"])
    if ps:
        return min(ps)
    yb = r.get("yes_bid")
    return (1.0 - yb) if yb is not None else None


def load_events():
    """Per (no_token_id, end_date): aggregate raw/asos running-max + meta + capacity."""
    ev = {}
    for fp in sorted(glob.glob(SHADOW_GLOB)):
        for line in open(fp):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("record_type") != "metar_lockout_candidate":
                continue
            ed = r.get("end_date")
            if not ed or ed > CUTOFF or ed < DATE_MIN:
                continue
            if "highest" not in (r.get("question", "") or "").lower():
                continue  # running_max semantics → MAX markets only
            key = (r.get("no_token_id"), ed)
            e = ev.get(key)
            if e is None:
                e = ev[key] = {
                    "city": r.get("city"), "end_date": ed,
                    "condition_id": r.get("condition_id"),
                    "question": r.get("question", ""),
                    "hi": r.get("bucket_hi_c_padded"),
                    "lo": r.get("bucket_lo_c_padded"),
                    "raw_max": -999.0, "asos_max": -999.0,
                    "min_no_ask": None, "first_ts": r.get("ts_s", 1e18),
                    "max_secs_locked": 0,
                }
            rm = r.get("running_max_c")
            if rm is not None and rm > e["raw_max"]:
                e["raw_max"] = rm
            am = r.get("asos_running_max_c")
            if am is not None and am > e["asos_max"]:
                e["asos_max"] = am
            na = best_no_ask(r)
            if na is not None and (e["min_no_ask"] is None or na < e["min_no_ask"]):
                e["min_no_ask"] = na
            sl = r.get("seconds_since_first_lockout")
            if sl is not None and sl > e["max_secs_locked"]:
                e["max_secs_locked"] = sl
    return list(ev.values())


def wr(rows, pred):
    nn = [r for r in rows if pred(r)]
    ww = sum(1 for r in nn if r["win"])
    return ww, len(nn)


def band_table(rows, feat, bands, label):
    print(f"\nby {label}:")
    print(f"  {'band':>10s}  {'WR':>10s}  {'n':>4s}")
    for name, lo, hi in bands:
        sub = [r for r in rows if r[feat] is not None and lo <= r[feat] < hi]
        if not sub:
            continue
        w = sum(1 for r in sub if r["win"])
        print(f"  {name:>10s}  {w:>4}/{len(sub):<4} {100*w/len(sub):5.1f}%")


def main():
    events = load_events()
    print(f"lockout events (MAX markets, asos-clean {DATE_MIN}..{CUTOFF}): {len(events)}")
    print(f"days: {sorted({e['end_date'] for e in events})}")

    print(f"\nfetching Gamma resolution {DATE_MIN}..2026-06-05 ...")
    _, cond_map = fetch_weather_events(DATE_MIN, "2026-06-05")
    print(f"  gamma: {len(cond_map)} conditions")

    def no_won(cid):
        e = cond_map.get(cid)
        if not e or not e.get("closed"):
            return None
        p = e.get("outcomePrices") or []
        try:
            no = float(p[1])
        except Exception:
            return None
        if no >= 0.99:
            return True
        if no <= 0.01:
            return False
        return None

    rows = []
    matched = unresolved = nomatch = 0
    for e in events:
        cid = e.get("condition_id")
        if cid not in cond_map:
            nomatch += 1
            continue
        w = no_won(cid)
        if w is None:
            unresolved += 1
            continue
        matched += 1
        hi = e["hi"]
        raw_max = e["raw_max"] if e["raw_max"] > -900 else None
        asos_max = e["asos_max"] if e["asos_max"] > -900 else None
        raw_margin = (raw_max - hi) if (hi is not None and raw_max is not None) else None
        asos_margin = (asos_max - hi) if (hi is not None and asos_max is not None) else None
        raw_gap = (raw_max - asos_max) if (raw_max is not None and asos_max is not None) else None
        edge = (1.0 - e["min_no_ask"]) if e["min_no_ask"] is not None else None
        rows.append({
            "city": norm_city(e["city"]), "date": e["end_date"], "q": e["question"][:50],
            "raw_margin": raw_margin, "asos_margin": asos_margin, "raw_gap": raw_gap,
            "edge": edge, "secs_locked": e["max_secs_locked"], "win": w,
        })

    print(f"\nmatched={matched}  unresolved/ambiguous={unresolved}  no_gamma_match={nomatch}")
    if not rows:
        print("no scored rows"); return
    base_w = sum(1 for r in rows if r["win"])
    print(f"\n*** BASELINE WR (raw-triggered lockouts) = {base_w}/{len(rows)} = {100*base_w/len(rows):.1f}% ***")
    print(f"    false lockouts (NO lost) = {len(rows)-base_w}")

    # ── discriminator bands ───────────────────────────────────────────────────
    band_table(rows, "raw_margin",
               [("<0", -99, 0), ("0-0.5", 0, .5), ("0.5-1", .5, 1), ("1-2", 1, 2), (">=2", 2, 99)],
               "raw_margin (running_max_c - ceiling)  [OLD spike-prone gate]")
    band_table(rows, "asos_margin",
               [("<0", -99, 0), ("0-0.5", 0, .5), ("0.5-1", .5, 1), ("1-2", 1, 2), (">=2", 2, 99)],
               "asos_margin (asos_running_max_c - ceiling)  [OFFICIAL-quality]")
    band_table(rows, "raw_gap",
               [("<=0", -99, .001), ("0-0.5", .001, .5), ("0.5-1", .5, 1), ("1-2", 1, 2), (">=2", 2, 99)],
               "raw_gap (running_max_c - asos_running_max_c)  [SPIKE SIZE]")

    # ── the false lockouts: what did the discriminators say? ──────────────────
    fl = [r for r in rows if not r["win"]]
    print(f"\nFALSE LOCKOUTS ({len(fl)}) — raw said locked, NO still LOST:")
    print(f"  {'city':<13s}{'date':<11s}{'raw_m':>6s}{'asos_m':>7s}{'gap':>6s}{'edge':>6s} | question")
    for r in sorted(fl, key=lambda r: (r["asos_margin"] is None, r["asos_margin"] or 9)):
        am = f"{r['asos_margin']:+.2f}" if r["asos_margin"] is not None else "  NA"
        rm = f"{r['raw_margin']:+.2f}" if r["raw_margin"] is not None else "  NA"
        gp = f"{r['raw_gap']:.2f}" if r["raw_gap"] is not None else " NA"
        ed = f"{r['edge']:.2f}" if r["edge"] is not None else " NA"
        print(f"  {r['city']:<13s}{r['date']:<11s}{rm:>6s}{am:>7s}{gp:>6s}{ed:>6s} | {r['q']}")

    # ── gate scenarios: WR + retained n ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("GATE SCENARIOS  (want WR >= ~98% AND high retained n)")
    print("=" * 70)
    def show(name, pred):
        w, n = wr(rows, pred)
        print(f"  {name:<52s} {w:>3}/{n:<3} = {100*w/n if n else float('nan'):5.1f}%")
    show("baseline (all raw-triggered)", lambda r: True)
    show("OLD gate: raw_margin >= 0.5", lambda r: (r["raw_margin"] or -9) >= 0.5)
    show("asos_margin >= 0  (official confirms crossing)", lambda r: (r["asos_margin"] or -9) >= 0)
    show("asos_margin >= 0.5", lambda r: (r["asos_margin"] or -9) >= 0.5)
    show("asos_margin >= 1.0", lambda r: (r["asos_margin"] or -9) >= 1.0)
    show("raw_gap <= 0.5 (small spike)", lambda r: (r["raw_gap"] if r["raw_gap"] is not None else 9) <= 0.5)
    show("asos_margin>=0.5 AND raw_gap<=0.5", lambda r: (r["asos_margin"] or -9) >= 0.5 and (r["raw_gap"] if r["raw_gap"] is not None else 9) <= 0.5)
    show("exclude KNOWN_BAD + asos_margin>=0.5", lambda r: r["city"] not in KNOWN_BAD and (r["asos_margin"] or -9) >= 0.5)
    show("exclude KNOWN_BAD + asos_margin>=0.5 + raw_gap<=1.0",
         lambda r: r["city"] not in KNOWN_BAD and (r["asos_margin"] or -9) >= 0.5 and (r["raw_gap"] if r["raw_gap"] is not None else 9) <= 1.0)


if __name__ == "__main__":
    main()
