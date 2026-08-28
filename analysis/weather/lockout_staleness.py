"""
LOCKOUT staleness DYNAMICS (ad-hoc, read-only) — the entry-timing companion to
lockout_capacity.py (which only looks at FIRST capture per event).

Motivated by the MM fingerprint ([[project_mm_fingerprint_metagame]]): the makers on
locked-out buckets are slow, deterministic tail quoters. This quantifies HOW slow —
i.e. after a bucket physically locks out (running_max past ceiling), how long does the
mispriced cheap NO-ask PERSIST before the MM updates it, and how much depth is fillable
over that window? That window = our entry-timing budget; the depth = our size budget.

Uses ALL ~60s snapshots per (token, day), with seconds_since_first_lockout as the time
axis. Splits pre/post the 2026-05-27 M1β provenance fix (asos 1-min spikes caused FALSE
lockouts pre-fix) and by safety margin (running_max - bucket_hi).

edge = 1 - fillable_no_ask  (profit/share if NO wins; locked-out buckets resolve NO
~always when provenance-clean). CRUCIAL: we use FILLABLE NO asks only (real no_book
asks / no_ask_clob) — NOT the 1-yes_bid fallback. In genuine lockouts the NO book is
often empty on the ask side and the only stale quote is a tiny residual YES bid, which
is NOT directly buyable as NO. So we report (a) how OFTEN a fillable cheap NO exists and
(b) among those, its edge/depth/persistence. "Window" = last seconds_since_first_lockout
at which a FILLABLE edge>=1% exists.

Usage: python3 analysis/weather/lockout_staleness.py
"""
from __future__ import annotations
import glob, json
from collections import defaultdict

FILES = sorted(glob.glob("logs/shadow/hot/2026-05-2*/metar_lockout.jsonl"))
FIX_DATE = "2026-05-27"   # M1β official-METAR provenance fix
EDGE_MIN = 0.01           # "actionable" edge threshold


def fillable_no_ask(rec):
    """Lowest price we could actually BUY NO at (real book ask / CLOB ask). None if
    nothing is offered — the 1-yes_bid 'implied' price is NOT fillable as NO."""
    nb = rec.get("no_book") or {}
    prices = [a["price"] for a in (nb.get("asks") or []) if a.get("size", 0) > 0]
    clob = rec.get("no_ask_clob")
    if clob:
        prices.append(clob)
    return min(prices) if prices else None


def no_depth_usd(rec, max_price=0.99):
    nb = rec.get("no_book") or {}
    return sum(a.get("usd", a["price"] * a["size"])
               for a in (nb.get("asks") or [])
               if a.get("price", 1.0) <= max_price and a.get("size", 0) > 0)


def pct(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100 * len(xs)))]


def main():
    # group all snapshots per (token, day)
    snaps = defaultdict(list)
    for fp in FILES:
        for line in open(fp):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("record_type") != "metar_lockout_candidate":
                continue
            snaps[(r.get("token_id"), r.get("end_date"))].append(r)
    for k in snaps:
        snaps[k].sort(key=lambda r: r.get("ts_s", 0))
    print(f"locked (token,day) events: {len(snaps):,}  | total snapshots: {sum(len(v) for v in snaps.values()):,}\n")

    # ---- per-event trajectory: persistence window, edge decay, depth ----
    TBUCKETS = [(0, 30), (30, 60), (60, 120), (120, 300), (300, 900),
                (900, 3600), (3600, 10**9)]
    TLABEL = ["0-30s", "30-60s", "1-2m", "2-5m", "5-15m", "15-60m", ">60m"]

    def analyze(events, tag):
        # decay curve over all snapshots. Track fillable fraction explicitly.
        bucket_tot = defaultdict(int)          # all snapshots in bucket
        bucket_fill = defaultdict(int)         # snapshots with a FILLABLE NO ask
        bucket_edges = defaultdict(list)       # edges among fillable
        bucket_depth = defaultdict(list)       # depth among fillable (edge>=1% price)
        bucket_act = defaultdict(int)          # fillable AND edge>=MIN
        windows = []          # per-event last ssfl with FILLABLE edge>=MIN
        n_events_fillable = 0  # events that EVER had a fillable cheap NO
        n_multi = 0
        spans = []
        for ev in events:
            had_fillable = False
            last_ok = None
            n = 0
            for r in ev:
                ssfl = r.get("seconds_since_first_lockout")
                if ssfl is None:
                    continue
                n += 1
                lab = next((L for (lo, hi), L in zip(TBUCKETS, TLABEL) if lo <= ssfl < hi), None)
                if lab is None:
                    continue
                bucket_tot[lab] += 1
                na = fillable_no_ask(r)
                if na is None:
                    continue
                edge = 1.0 - na
                bucket_fill[lab] += 1
                bucket_edges[lab].append(edge)
                bucket_depth[lab].append(no_depth_usd(r))
                if edge >= EDGE_MIN:
                    bucket_act[lab] += 1
                    had_fillable = True
                    last_ok = ssfl
            if n:
                spans.append(ev[-1].get("seconds_since_first_lockout", 0))
                if n > 1:
                    n_multi += 1
            if had_fillable:
                n_events_fillable += 1
                windows.append(last_ok)
        print(f"=== {tag}: {len(events)} events ({n_multi} multi-snapshot) ===")
        print(f"  events that EVER offered a fillable cheap NO (edge>=1%): "
              f"{n_events_fillable}/{len(events)} = {100*n_events_fillable/max(1,len(events)):.0f}%")
        print(f"  observed locked span/event: med={pct(spans,50):.0f}s  p90={pct(spans,90):.0f}s")
        if windows:
            print(f"  fillable edge>=1% persists until (per event): med={pct(windows,50):.0f}s  p75={pct(windows,75):.0f}s  p90={pct(windows,90):.0f}s")
        print(f"  {'t-since-lockout':>15} {'n_snap':>7} {'%fillable':>10} {'med_edge':>9} {'%edge>=1%':>10} {'med_depth$':>11}")
        for lab in TLABEL:
            tot = bucket_tot[lab]
            if not tot:
                continue
            fl = bucket_fill[lab]
            es = bucket_edges[lab]
            mededge = pct(es, 50) if es else float("nan")
            meddep = pct(bucket_depth[lab], 50) if bucket_depth[lab] else float("nan")
            pctact = 100 * bucket_act[lab] / tot
            print(f"  {lab:>15} {tot:>7} {100*fl/tot:>9.0f}% {mededge:>9.3f} {pctact:>9.0f}% {meddep:>11.1f}")
        print()

    allev = list(snaps.values())
    pre = [v for k, v in snaps.items() if (k[1] or "") < FIX_DATE]
    post = [v for k, v in snaps.items() if (k[1] or "") >= FIX_DATE]
    analyze(allev, "ALL DAYS")
    analyze(post, f"POST-FIX (>= {FIX_DATE}, provenance-clean)")
    analyze(pre, f"PRE-FIX (< {FIX_DATE}, asos-contaminated)")

    # ---- staleness by safety margin (robust lockouts persist; thin ones may flip) ----
    print("=== edge>=1% persistence (median window seconds) by safety margin band, POST-FIX ===")
    mb = [(-99, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 99)]
    for lo, hi in mb:
        win = []
        for ev in post:
            last_ok = None
            for r in ev:
                rm, hb = r.get("running_max_c"), r.get("bucket_hi_c_padded")
                if rm is None or hb is None or not (lo <= rm - hb < hi):
                    continue
                na = fillable_no_ask(r)
                if na is None:
                    continue
                if 1.0 - na >= EDGE_MIN:
                    last_ok = r.get("seconds_since_first_lockout")
            if last_ok is not None:
                win.append(last_ok)
        if win:
            print(f"  margin {lo:>5.1f}-{hi:<5.1f}C  n={len(win):4d}  med_window={pct(win,50):.0f}s  p90={pct(win,90):.0f}s")


if __name__ == "__main__":
    main()
