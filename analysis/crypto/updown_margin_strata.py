"""Margin-stratified grade of the UPDOWN crossing-fire population.

Sim = first qualifying snap per window (same as shadow_grade.py), candidate
gates {5m, p>=0.995, t_left 5-60, ask 0.90-0.99, move>=4bp, edge>=1%}.
Truth = Gamma /events refetch, exact sorted([0,1]) only (shadow res records
pre-FIX_TS mislabeled winners; 2026-07-19 regrade flipped 3 of 7 "losses").

Strata: |move| bp at fire, sigma-floored flag, asset. 2026-07-19 baseline
(btc-only, 7d, n=129): ALL WR 0.969 vs BE 0.963 ROI +0.6%/$ CI-lo 0.923;
mv 4-6bp -1.4%/$, mv>=8bp n=64 W=63 ROI +2.1%/$ CI-lo ~0.92 — NO cell
clears CI; pre-registered stratum for updown_crossing_reenable_gate review.
"""
import glob, json, math, os, urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CACHE = "/root/Klaus/logs/shadow/updown_sniper/gamma_truth_cache.json"
G = dict(t_max=60.0, t_min=5.0, ask_min=0.90, ask_max=0.99, p_min=0.995,
         move_floor=0.0004, sig_floor=0.00005, edge_min=0.010)


def refetch_winner(slug):
    try:
        req = urllib.request.Request(f"{GAMMA}/events?slug={slug}",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            evs = json.load(r)
        if not evs or not evs[0].get("markets"):
            return None
        m = evs[0]["markets"][0]
        op = [float(x) for x in json.loads(m["outcomePrices"])]
        outs = json.loads(m["outcomes"])
        if sorted(op) != [0.0, 1.0]:
            return None
        return outs[op.index(1.0)]
    except Exception:
        return None


def sim():
    snaps = []
    for f in sorted(glob.glob("/root/Klaus/logs/shadow/updown_sniper/snap_*.jsonl")):
        for l in open(f):
            try:
                d = json.loads(l)
            except Exception:
                continue
            if d.get("type") == "snap" and d.get("step") == 300:
                snaps.append(d)
    snaps.sort(key=lambda d: d["ts"])
    ff = {}
    for d in snaps:
        slug = d["slug"]
        if slug in ff:
            continue
        t_left = d.get("t_left") or 0.0
        if not (G["t_min"] <= t_left <= G["t_max"]):
            continue
        move = d.get("move") or 0.0
        if abs(move) < G["move_floor"]:
            continue
        raw_sig = d.get("sigma1s") or 0.0
        sig = max(raw_sig, G["sig_floor"])
        z = move / (sig * math.sqrt(max(t_left, 0.5)))
        p_up = 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
        side, p = ("Up", p_up) if move > 0 else ("Down", 1.0 - p_up)
        if p < G["p_min"]:
            continue
        b = d.get("up" if side == "Up" else "down") or {}
        ask, ask_sz = b.get("ask"), b.get("ask_sz") or 0.0
        if ask is None or not (G["ask_min"] <= ask <= G["ask_max"]):
            continue
        if p - ask - 0.07 * ask * (1 - ask) < G["edge_min"]:
            continue
        if ask_sz * ask < 5.0:
            continue
        ff[slug] = dict(side=side, ask=ask, p=p, ts=d["ts"], t_left=t_left,
                        asset=d.get("asset") or "btc",
                        mv_bp=abs(move) * 1e4, sig_floored=raw_sig < G["sig_floor"])
    return ff


def wilson_lo(w, n, zc=1.96):
    if n == 0:
        return 0.0
    ph = w / n
    den = 1 + zc * zc / n
    ctr = ph + zc * zc / (2 * n)
    rad = zc * math.sqrt(ph * (1 - ph) / n + zc * zc / (4 * n * n))
    return (ctr - rad) / den


def cell(name, rows):
    n = len(rows)
    if n == 0:
        print(f"{name:>26}: n=0")
        return
    w = sum(1 for f, win in rows if f["side"] == win)
    avg_ask = sum(f["ask"] for f, _ in rows) / n
    be = avg_ask + 0.07 * avg_ask * (1 - avg_ask)
    roi = sum((1 - f["ask"] - 0.07 * f["ask"] * (1 - f["ask"])) / f["ask"]
              if f["side"] == win else -1.0 for f, win in rows) / n
    lo = wilson_lo(w, n)
    print(f"{name:>26}: n={n:>3} W={w:>3} WR={w/n:.3f} CI-lo={lo:.3f} "
          f"BE={be:.3f} ROI/$={roi*100:+.1f}% [{'CLEARS' if lo > be else 'no'}]")


def main():
    ff = sim()
    try:
        tcache = json.load(open(CACHE))
    except Exception:
        tcache = {}
    need = [s for s in ff if not tcache.get(s)]
    print(f"sim fires: {len(ff)}  refetching {len(need)}")
    for s in need:
        tcache[s] = refetch_winner(s)
    json.dump(tcache, open(CACHE, "w"))
    g = [(f, tcache[s]) for s, f in ff.items() if tcache.get(s)]
    print(f"graded {len(g)}/{len(ff)}")
    cell("ALL 5m crossing", g)
    for name, lo_, hi_ in [("4-6bp", 4, 6), ("6-8bp", 6, 8),
                           ("8-12bp", 8, 12), (">=12bp", 12, 1e9)]:
        cell(f"mv {name}", [r for r in g if lo_ <= r[0]["mv_bp"] < hi_])
    cell("mv >=8bp", [r for r in g if r[0]["mv_bp"] >= 8])
    cell("sig FLOORED", [r for r in g if r[0]["sig_floored"]])
    cell("sig real", [r for r in g if not r[0]["sig_floored"]])
    for a in sorted(set(f["asset"] for f, _ in g)):
        cell(f"asset {a}", [r for r in g if r[0]["asset"] == a])
    print("losses:")
    for f, win in g:
        if f["side"] != win:
            print(f"  {f['asset']} ts={f['ts']:.0f} side={f['side']} "
                  f"mv={f['mv_bp']:.1f}bp ask={f['ask']:.2f} "
                  f"t_left={f['t_left']:.0f}s p={f['p']:.4f} "
                  f"floored={f['sig_floored']}")


if __name__ == "__main__":
    main()
