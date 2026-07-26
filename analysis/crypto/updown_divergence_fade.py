"""Divergence-fade grade: buy the CHEAP side where model certainty meets market doubt.

Inverse of the killed certainty-taker class (updown_crossing_reenable_gate KILLED
2026-07-26, pooled 5-asset n=469 point WR < BE). The kill evidence showed losses
concentrate where p_model>=0.995 but the certainty ask <=0.95 — i.e. the market's
residual doubt at model certainty is informed. This grader measures the inverse
trade: at the FIRST divergence snap per 5m window (p_model>=0.995, certainty ask
<=DIV_ASK_MAX), buy the OPPOSITE token at its ask, hold to resolution.

HYPOTHESIS-FORMING on history (population chosen after seeing losses cluster at
low asks — circular); the experiment gate (updown_divergence_fade, registered
2026-07-26) counts ONLY windows with first-divergence ts after registration.
Truth = Gamma refetch exact [0,1], same cache as updown_margin_strata.py.
"""
import glob, json, math, urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CACHE = "/root/Klaus/logs/shadow/updown_sniper/gamma_truth_cache.json"
G = dict(t_max=120.0, t_min=5.0, p_min=0.995, div_ask_max=0.95,
         cheap_min=0.02, cheap_max=0.25, min_notional=5.0,
         move_floor=0.0004, sig_floor=0.00005)
REG_TS = 1785150000  # 2026-07-26 registration boundary for the prospective gate


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
        cert, p = ("Up", p_up) if move > 0 else ("Down", 1.0 - p_up)
        if p < G["p_min"]:
            continue
        cb = d.get("up" if cert == "Up" else "down") or {}
        cert_ask = cb.get("ask")
        if cert_ask is None or cert_ask > G["div_ask_max"]:
            continue
        cheap_side = "Down" if cert == "Up" else "Up"
        xb = d.get("up" if cheap_side == "Up" else "down") or {}
        ask, ask_sz = xb.get("ask"), xb.get("ask_sz") or 0.0
        if ask is None or not (G["cheap_min"] <= ask <= G["cheap_max"]):
            continue
        if ask_sz * ask < G["min_notional"]:
            continue
        ff[slug] = dict(side=cheap_side, ask=ask, cert_ask=cert_ask, p=p,
                        ts=d["ts"], t_left=t_left, asset=d.get("asset") or "btc",
                        mv_bp=abs(move) * 1e4,
                        sig_floored=raw_sig < G["sig_floor"])
    return ff


def wilson(w, n, zc=1.96):
    if n == 0:
        return (0.0, 0.0)
    ph = w / n
    den = 1 + zc * zc / n
    ctr = ph + zc * zc / (2 * n)
    rad = zc * math.sqrt(ph * (1 - ph) / n + zc * zc / (4 * n * n))
    return ((ctr - rad) / den, (ctr + rad) / den)


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
    lo, hi = wilson(w, n)
    print(f"{name:>26}: n={n:>3} W={w:>3} WR={w/n:.3f} CI[{lo:.3f},{hi:.3f}] "
          f"BE={be:.3f} ROI/$={roi*100:+.1f}% [{'CLEARS' if lo > be else 'no'}]")


def main():
    ff = sim()
    try:
        tcache = json.load(open(CACHE))
    except Exception:
        tcache = {}
    need = [s for s in ff if not tcache.get(s)]
    print(f"divergence windows: {len(ff)}  refetching {len(need)}")
    for s in need:
        tcache[s] = refetch_winner(s)
    json.dump(tcache, open(CACHE, "w"))
    g = [(f, tcache[s]) for s, f in ff.items() if tcache.get(s)]
    print(f"graded {len(g)}/{len(ff)}")
    cell("ALL divergence-fade", g)
    cell("PROSPECTIVE (post-reg)", [r for r in g if r[0]["ts"] >= REG_TS])
    for name, lo_, hi_ in [("0.02-0.06", 0.02, 0.06), ("0.06-0.12", 0.06, 0.12),
                           ("0.12-0.25", 0.12, 0.25)]:
        cell(f"cheap ask {name}", [r for r in g if lo_ <= r[0]["ask"] < hi_])
    for name, lo_, hi_ in [("cert 0.90-0.93", 0.90, 0.93),
                           ("cert 0.93-0.95", 0.93, 0.951)]:
        cell(name, [r for r in g if lo_ <= r[0]["cert_ask"] < hi_])
    cell("sig FLOORED", [r for r in g if r[0]["sig_floored"]])
    cell("sig real", [r for r in g if not r[0]["sig_floored"]])
    for a in sorted(set(f["asset"] for f, _ in g)):
        cell(f"asset {a}", [r for r in g if r[0]["asset"] == a])
    days = (max(f["ts"] for f in ff.values()) -
            min(f["ts"] for f in ff.values())) / 86400 if ff else 0
    print(f"capacity: {len(ff)/max(days,0.01):.1f} divergence windows/day "
          f"over {days:.1f}d")


if __name__ == "__main__":
    main()
