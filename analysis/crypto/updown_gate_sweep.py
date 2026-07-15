"""Gate-relaxation sweep for UPDOWN-SNIPER frequency.

Question: which single gate relaxation adds the most fires/day, and do the
ADDED fires (qualify under relaxed gate, not under live v1) win on true labels?

Same sim as shadow_grade.py (first qualifying snap per window, rails-free,
$5 clip, true fee 0.07*p*(1-p)); truth = post-fix res records + regrade cache
+ Gamma refetch (exact sorted([0,1]) only).
"""
import glob, json, math, sys, urllib.request

FIX_TS = 1783980283.0
GAMMA = "https://gamma-api.polymarket.com"
CACHE = "/root/Klaus/logs/shadow/updown_sniper/regrade_cache.json"
CLIP_USD = 5.0

V1 = dict(t_max={900: 120, 300: 30}, t_min=5.0, ask_min=0.90,
          ask_max={900: 0.97, 300: 0.99}, p_min=0.99,
          move_floor=0.0006, sig_floor=0.00005, edge_min=0.010)

VARIANTS = {
    "v1 (live)":        {},
    "A p_min 0.98":     dict(p_min=0.98),
    "B 5m t_max 60s":   dict(t_max={900: 120, 300: 60}),
    "C move 4bp":       dict(move_floor=0.0004),
    "D edge_min 0.5%":  dict(edge_min=0.005),
    "E A+B combo":      dict(p_min=0.98, t_max={900: 120, 300: 60}),
}


def sim(snaps, g):
    ff = {}
    for d in snaps:
        slug = d["slug"]
        if slug in ff:
            continue
        step = d.get("step")
        if step not in g["t_max"]:
            continue
        t_left = d.get("t_left") or 0.0
        if not (g["t_min"] <= t_left <= g["t_max"][step]):
            continue
        move = d.get("move") or 0.0
        if abs(move) < g["move_floor"]:
            continue
        sig = max(d.get("sigma1s") or 0.0, g["sig_floor"])
        z = move / (sig * math.sqrt(max(t_left, 0.5)))
        p_up = 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
        side, p_model = ("Up", p_up) if move > 0 else ("Down", 1.0 - p_up)
        if p_model < g["p_min"]:
            continue
        b = d.get("up" if side == "Up" else "down") or {}
        ask, ask_sz = b.get("ask"), b.get("ask_sz") or 0.0
        if ask is None or not (g["ask_min"] <= ask <= g["ask_max"][step]):
            continue
        if p_model - ask - 0.07 * ask * (1 - ask) < g["edge_min"]:
            continue
        if ask_sz * ask < CLIP_USD:
            continue
        ff[slug] = dict(side=side, ask=ask, p=p_model, ts=d["ts"], step=step)
    return ff


def refetch_winner(slug):
    try:
        with urllib.request.urlopen(f"{GAMMA}/markets?slug={slug}", timeout=10) as r:
            mkts = json.load(r)
        if not mkts:
            return None
        m = mkts[0]
        op = [float(x) for x in json.loads(m["outcomePrices"])]
        outs = json.loads(m["outcomes"])
        if sorted(op) != [0.0, 1.0]:
            return None
        return outs[op.index(1.0)]
    except Exception:
        return None


def grade(ff, truth):
    n = w = 0
    pnl = 0.0
    for slug, f in ff.items():
        win = truth.get(slug)
        if win is None:
            continue
        n += 1
        sh = CLIP_USD / f["ask"]
        fee = 0.07 * f["ask"] * (1 - f["ask"]) * sh
        if win == f["side"]:
            w += 1
            pnl += sh * (1 - f["ask"]) - fee
        else:
            pnl -= CLIP_USD + fee
    return n, w, pnl


def wilson(w, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = w / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (c - hw, c + hw)


def main():
    snaps, truth = [], {}
    for fn in sorted(glob.glob("/root/Klaus/logs/shadow/updown_sniper/snap_*.jsonl")):
        for line in open(fn):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") == "snap":
                snaps.append(d)
            elif d.get("type") == "res" and d["ts"] >= FIX_TS:
                truth[d["slug"]] = d["winner"]
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}
    for s, w in cache.items():
        if w and s not in truth:
            truth[s] = w

    days = len(set(d["slug"].rsplit("-", 1)[0] + "|" +
                   __import__("datetime").datetime.utcfromtimestamp(d["ts"]).strftime("%Y%m%d")
                   for d in snaps))  # unused; day count below from snap files
    ndays = len(glob.glob("/root/Klaus/logs/shadow/updown_sniper/snap_*.jsonl"))

    fires = {name: sim(snaps, {**V1, **ov}) for name, ov in VARIANTS.items()}
    base = fires["v1 (live)"]

    if "--refetch" in sys.argv:
        need = sorted({s for ff in fires.values() for s in ff} - set(truth))
        need = [s for s in need if cache.get(s) is None or s not in cache]
        print(f"refetching {len(need)} slugs from Gamma...", file=sys.stderr)
        for i, s in enumerate(need):
            w = refetch_winner(s)
            cache[s] = w
            if w:
                truth[s] = w
            if (i + 1) % 50 == 0:
                json.dump(cache, open(CACHE, "w"))
                print(f"  {i+1}/{len(need)}", file=sys.stderr)
        json.dump(cache, open(CACHE, "w"))

    print(f"snap days={ndays}, windows seen={len(set(d['slug'] for d in snaps))}, truth labels={len(truth)}")
    print(f"{'variant':18s} {'fires':>5s} {'/day':>5s} | {'graded':>6s} {'WR':>6s} {'CI95':>15s} {'pnl$':>7s} | added-only: n/W/pnl")
    for name, ff in fires.items():
        n, w, pnl = grade(ff, truth)
        lo, hi = wilson(w, n)
        added = {s: f for s, f in ff.items() if s not in base}
        an, aw, apnl = grade(added, truth)
        wr = f"{w/n*100:5.1f}%" if n else "    --"
        print(f"{name:18s} {len(ff):5d} {len(ff)/ndays:5.1f} | {n:6d} {wr} [{lo*100:5.1f},{hi*100:5.1f}] {pnl:+7.2f} | {an}/{aw}/{apnl:+.2f}")


if __name__ == "__main__":
    main()
