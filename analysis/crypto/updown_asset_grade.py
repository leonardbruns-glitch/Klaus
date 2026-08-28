"""Per-asset shadow gate grade for UPDOWN-SNIPER capacity cells (eth/sol/xrp/btc).

Each asset is its own cell with its own n>=100 gate (daily_prompt STEP 2).
Same sim as updown_gate_sweep.py (first qualifying snap per window, rails-free,
$5 clip, true fee 0.07*p*(1-p)); truth = post-fix res records + regrade cache
+ optional --refetch via Gamma. Slugs are per-asset (eth-updown-15m-...), so
cells cannot cross-contaminate; the live BTC gate ledger (shadow_grade.py)
stays btc-only by its own filter.

Usage: PYTHONPATH=/root/Klaus python3 analysis/crypto/updown_asset_grade.py [--refetch]
"""
import glob, json, math, sys

from updown_gate_sweep import V1, sim, grade, wilson, refetch_winner, FIX_TS, CACHE

SNAP_GLOB = "/root/Klaus/logs/shadow/updown_sniper/snap_*.jsonl"


def main():
    snaps_by_asset, truth = {}, {}
    for fn in sorted(glob.glob(SNAP_GLOB)):
        for line in open(fn):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") == "snap":
                asset = d.get("asset") or d["slug"].split("-", 1)[0]
                snaps_by_asset.setdefault(asset, []).append(d)
            elif d.get("type") == "res" and d["ts"] >= FIX_TS:
                truth[d["slug"]] = d["winner"]
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}
    for s, w in cache.items():
        if w and s not in truth:
            truth[s] = w

    fires = {a: sim(sn, V1) for a, sn in sorted(snaps_by_asset.items())}

    if "--refetch" in sys.argv:
        need = sorted({s for ff in fires.values() for s in ff} - set(truth))
        fetched = 0
        for s in need:
            w = refetch_winner(s)
            cache[s] = w
            if w:
                truth[s] = w
                fetched += 1
        json.dump(cache, open(CACHE, "w"))
        print(f"refetched {fetched}/{len(need)} missing winners")

    for asset, ff in fires.items():
        n, w, pnl = grade(ff, truth)
        graded = {s: f for s, f in ff.items() if s in truth}
        if n == 0:
            print(f"{asset:4s} fires={len(ff):4d} graded=0 — no truth yet")
            continue
        avg_ask = sum(f["ask"] for f in graded.values()) / n
        be = avg_ask + 0.07 * avg_ask * (1 - avg_ask)  # incl. sim fee
        lo, hi = wilson(w, n)
        stake = 5.0 * n
        verdict = ("READY" if n >= 100 and lo > be
                   else "REJECTED" if n >= 100 and lo < be and w / n < be
                   else "COLLECTING")
        # p>=0.995 sub-slice (candidate-policy analogue)
        sub = {s: f for s, f in graded.items() if f["p"] >= 0.995}
        sn_, sw_, spnl = grade(sub, truth)
        sub_str = ""
        if sn_:
            slo, _ = wilson(sw_, sn_)
            sask = sum(f["ask"] for f in sub.values()) / sn_
            sbe = sask + 0.07 * sask * (1 - sask)
            sub_str = (f" | p>=.995: n={sn_} WR={sw_ / sn_:.3f} CI-lo={slo:.3f}"
                       f" BE={sbe:.3f} pnl=${spnl:+.2f}")
        print(f"{asset:4s} fires={len(ff):4d} graded={n:4d} WR={w / n:.3f} "
              f"CI[{lo:.3f},{hi:.3f}] avg_ask={avg_ask:.3f} BE={be:.3f} "
              f"pnl=${pnl:+.2f}/{stake:.0f} -> {verdict}{sub_str}")


if __name__ == "__main__":
    main()
