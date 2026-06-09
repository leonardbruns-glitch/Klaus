"""
Settlement-lock validators (read-only; no capital, no trades.jsonl writes).

Joins the metar_lockout shadow events to ACTUAL Gamma resolution to answer the
two questions the whole settlement-lock thesis rests on:

  D2  RESOLUTION-JOIN WR : for buckets we flagged as physically locked out
       (running_max already past the ceiling) and would BUY_NO — did NO
       actually win at resolution? Overall + by safety-margin band + by edge
       band. This replaces the INFERRED WR with a measured one.

  D1  ORACLE-EXACT RULE  : for each resolved (city, day), which bucket won
       (Gamma YES=1)? Does the bot's observed official running_max land inside
       that winning bucket? Agreement rate + signed error when it doesn't.
       This tests whether "max of official hourly METAR" (our signal source)
       reproduces the oracle's resolution — the moat / contamination check.

Only city-days with end_date <= CUTOFF (markets closed) are scored.

Run: python3 analysis/weather/lockout_resolution_join.py
"""
from __future__ import annotations
import glob
import json
import sys
from collections import defaultdict

sys.path.insert(0, "/root/Klaus")
from analytics.backfill_weather_resolution import (
    parse_weather_question, fetch_weather_events,
)

CUTOFF = "2026-05-28"          # last fully-closed local day to score
DATE_MIN = "2026-05-23"
SHADOW_GLOB = "logs/shadow/hot/2026-05-2*/metar_lockout.jsonl"


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


def load_shadow():
    """first-seen per (no_token_id, end_date); + observed daily running_max per (city,date)."""
    first = {}
    run_max = defaultdict(lambda: -999.0)   # (city_norm, date) -> max running_max_c seen
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
            key = (r.get("no_token_id"), ed)
            cur = first.get(key)
            if cur is None or r.get("ts_s", 1e18) < cur.get("ts_s", 1e18):
                first[key] = r
            rmk = (norm_city(r.get("city")), ed)
            rm = r.get("running_max_c")
            if rm is not None and rm > run_max[rmk]:
                run_max[rmk] = rm
    return list(first.values()), dict(run_max)


def main():
    events, run_max = load_shadow()
    print(f"shadow lockout events (closed, {DATE_MIN}..{CUTOFF}): {len(events)}")
    days = sorted({e.get("end_date") for e in events})
    print(f"days: {days}")

    print(f"\nfetching Gamma resolution {DATE_MIN}..{CUTOFF} (+buffer) ...")
    token_map, cond_map = fetch_weather_events(DATE_MIN, "2026-05-29")
    print(f"  gamma: {len(token_map)} tokens, {len(cond_map)} conditions")

    def no_won(cid):
        """True/False/None for whether NO resolved (we buy NO on lockouts)."""
        e = cond_map.get(cid)
        if not e or not e.get("closed"):
            return None
        p = e.get("outcomePrices") or []
        try:
            yes = float(p[0]); no = float(p[1])
        except Exception:
            return None
        if no >= 0.99:
            return True
        if no <= 0.01:
            return False
        return None  # ambiguous

    # ── D2: resolution-join WR ────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("D2  MEASURED WR ON LOCKOUT-NO (did NO actually win?)")
    print("=" * 64)
    scored = wins = 0
    losses = []
    by_margin = defaultdict(lambda: [0, 0])   # band -> [wins, scored]
    by_edge = defaultdict(lambda: [0, 0])
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
        scored += 1
        wins += 1 if w else 0
        hi = e.get("bucket_hi_c_padded"); rm = e.get("running_max_c")
        na = best_no_ask(e)
        margin = (rm - hi) if (hi is not None and rm is not None) else None
        edge = (1.0 - na) if na is not None else None
        if margin is not None:
            mb = "<0.5" if margin < 0.5 else "0.5-1" if margin < 1 else "1-2" if margin < 2 else ">=2"
            by_margin[mb][0] += 1 if w else 0
            by_margin[mb][1] += 1
        if edge is not None:
            eb = "<.02" if edge < .02 else ".02-.05" if edge < .05 else ".05-.15" if edge < .15 else ">=.15"
            by_edge[eb][0] += 1 if w else 0
            by_edge[eb][1] += 1
        if not w:
            losses.append((e.get("city"), e.get("end_date"), round(margin or -9, 2),
                           round(edge or 0, 3), e.get("question", "")[:55]))

    print(f"matched={matched}  unresolved/ambiguous={unresolved}  no_gamma_match={nomatch}")
    if scored:
        print(f"\n*** MEASURED WR = {wins}/{scored} = {100*wins/scored:.1f}% ***")

    # accumulate per-event rows + per-city WR for scenario analysis
    rows = []
    by_city = defaultdict(lambda: [0, 0])
    for e in events:
        cid = e.get("condition_id")
        w = no_won(cid)
        if w is None:
            continue
        hi = e.get("bucket_hi_c_padded"); rm = e.get("running_max_c")
        na = best_no_ask(e)
        m = (rm - hi) if (hi is not None and rm is not None) else None
        ed = (1.0 - na) if na is not None else None
        c = norm_city(e.get("city"))
        rows.append({"city": c, "date": e.get("end_date"), "margin": m, "edge": ed, "win": w})
        by_city[c][0] += 1 if w else 0
        by_city[c][1] += 1
    print("\nper-city WR (sorted worst-first):")
    for c, (w, n) in sorted(by_city.items(), key=lambda kv: kv[1][0]/max(1,kv[1][1])):
        if n >= 2 and w < n:
            print(f"  {c:<14s} {w:>2}/{n:<2} = {100*w/n:5.1f}%")
    print("\nby safety margin (running_max - bucket_hi, °C):")
    for b in ["<0.5", "0.5-1", "1-2", ">=2"]:
        w, n = by_margin[b]
        if n:
            print(f"  margin {b:>5s}: WR {w}/{n} = {100*w/n:5.1f}%")
    print("\nby gross edge (1 - no_ask):")
    for b in ["<.02", ".02-.05", ".05-.15", ">=.15"]:
        w, n = by_edge[b]
        if n:
            print(f"  edge {b:>7s}: WR {w}/{n} = {100*w/n:5.1f}%")
    if losses:
        print(f"\nLOSSES ({len(losses)}) — the buckets that locked out but NO still lost:")
        for c, d, m, ed, q in losses[:25]:
            print(f"  {c:<14s} {d} margin={m:>5}°C edge={ed:>5} | {q}")

    # ── D1: oracle-exact rule ─────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("D1  ORACLE RULE — does observed running_max land in the WINNING bucket?")
    print("=" * 64)
    # winning bucket per (city,date): the Gamma market whose YES resolved =1
    winners = {}   # (city_norm,date) -> (lo_c_padded, hi_c_padded, question, unit, btype)
    for cid, e in cond_map.items():
        if not e.get("closed"):
            continue
        p = e.get("outcomePrices") or []
        try:
            yes = float(p[0])
        except Exception:
            continue
        if yes < 0.99:
            continue
        meta = parse_weather_question(e.get("question", ""))
        c = norm_city(meta.get("weather_city", ""))
        d = meta.get("weather_date")
        if not c or not d or d > CUTOFF or d < DATE_MIN:
            continue
        if "highest" not in e.get("question", "").lower():
            continue  # D1 oracle check on MAX markets (running_max semantics)
        winners[(c, d)] = (meta.get("weather_threshold_lo_c_padded"),
                           meta.get("weather_threshold_hi_c_padded"),
                           e.get("question", "")[:55],
                           meta.get("weather_unit"), meta.get("weather_bucket_type"))

    agree = checked = 0
    errs = []
    d1_city = defaultdict(lambda: [0, 0, 0.0])   # city -> [agree, checked, max_abs_err]
    for (c, d), (lo, hi, q, unit, bt) in sorted(winners.items()):
        rm = run_max.get((c, d))
        if rm is None:
            continue   # no shadow running_max for this city-day
        checked += 1
        lo_ok = (lo is None) or (rm >= lo - 1e-6)
        hi_ok = (hi is None) or (rm <= hi + 1e-6)
        inside = lo_ok and hi_ok
        agree += 1 if inside else 0
        _err = 0.0
        if not inside:
            _err = (rm - hi) if (hi is not None and rm > hi) else (rm - lo) if (lo is not None and rm < lo) else 0.0
        dc = d1_city[c]
        dc[0] += 1 if inside else 0
        dc[1] += 1
        dc[2] = max(dc[2], abs(_err))
        if not inside:
            # signed error: how far running_max is outside the winning bucket
            if hi is not None and rm > hi:
                err = rm - hi
            elif lo is not None and rm < lo:
                err = rm - lo
            else:
                err = 0.0
            errs.append((c, d, round(rm, 2), lo, hi, round(err, 2), unit, q))

    if checked:
        print(f"\n*** running_max INSIDE winning bucket: {agree}/{checked} = {100*agree/checked:.1f}% ***")
        print("(checked = resolved MAX city-days that also had a shadow running_max)")
    if errs:
        print(f"\nMISMATCHES ({len(errs)}) — running_max vs oracle winning bucket:")
        for c, d, rm, lo, hi, err, unit, q in errs[:30]:
            print(f"  {c:<14s} {d} run_max={rm:>5}°C  bucket=[{lo},{hi}]  err={err:>+5}°C [{unit}] | {q}")

    # ── SCENARIOS: how high does the gated WR go, and at what retained volume? ──
    print("\n" + "=" * 64)
    print("GATED WR SCENARIOS  (WR=494%? we want >=95% AND enough n)")
    print("=" * 64)
    # known non-WU / wrong-station cities (from D1 mismatch + resolution_mapper notes)
    KNOWN_BAD = {"hong-kong", "moscow", "istanbul", "tel-aviv"}
    # data-driven: cities whose oracle agreement < 90% or max station error >= 1.5C
    suspect = set(KNOWN_BAD)
    for c, (a, n, mx) in d1_city.items():
        if n >= 2 and (a / n < 0.90 or mx >= 1.5):
            suspect.add(c)
    print(f"suspect/blocked stations (D1 agree<90% or |err|>=1.5°C, + known non-WU):")
    print(f"  {sorted(suspect)}")

    def scen(name, pred):
        w = sum(1 for r in rows if pred(r))
        n = sum(1 for r in rows if pred(r) and True)
        # win/scored under filter
        nn = [r for r in rows if pred(r)]
        ww = sum(1 for r in nn if r["win"])
        wr = 100 * ww / len(nn) if nn else float("nan")
        print(f"  {name:<46s} WR {ww:>3}/{len(nn):<3} = {wr:5.1f}%")

    print("\nscenario                                         measured WR")
    scen("all locked-out NO (baseline)", lambda r: True)
    scen("margin >= 0.5°C", lambda r: (r["margin"] or -9) >= 0.5)
    scen("margin >= 1.0°C", lambda r: (r["margin"] or -9) >= 1.0)
    scen("exclude suspect stations", lambda r: r["city"] not in suspect)
    scen("exclude suspect + margin >= 0.5°C",
         lambda r: r["city"] not in suspect and (r["margin"] or -9) >= 0.5)
    scen("exclude suspect + margin >= 1.0°C",
         lambda r: r["city"] not in suspect and (r["margin"] or -9) >= 1.0)
    scen("exclude suspect + margin>=0.5 + edge<0.15 (conservative)",
         lambda r: r["city"] not in suspect and (r["margin"] or -9) >= 0.5 and (r["edge"] or 9) < 0.15)
    scen("exclude suspect + margin>=0.5 + edge in [0.02,0.15]",
         lambda r: r["city"] not in suspect and (r["margin"] or -9) >= 0.5
                   and 0.02 <= (r["edge"] or 9) < 0.15)


if __name__ == "__main__":
    main()
