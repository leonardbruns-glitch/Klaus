"""Offline gate for UPDOWN-SNIPER: grade policy-v1-eligible shadow windows on TRUE labels.

Mirrors strategy/updown_sniper.py policy constants exactly (incl. SIG_FLOOR).
Truth sources:
  1. res records in logs/shadow/updown_sniper/snap_*.jsonl with ts >= FIX_TS
     (settle-bug fix deploy 2026-07-13 22:04:43Z; earlier labels are VOID)
  2. --refetch: Gamma post-resolution outcomePrices for void/missing slugs
     (accept only exact sorted([0,1]) — same rule as the fixed service)
Grades are rails-free (per-window eligibility; live rails cap capital, not edge).
Run nightly; accumulates toward the n>=100 gate in experiments.jsonl.
"""
import glob, json, math, sys, urllib.request

FIX_TS = 1783980283.0
T_MAX = {900: 120, 300: 60}  # mirror live 2026-07-15
T_MIN = 5.0
ASK_MIN = 0.90
ASK_MAX = {900: 0.97, 300: 0.99}
P_MIN = 0.99
MOVE_FLOOR = 0.0004  # mirror live 2026-07-15
SIG_FLOOR = 0.00005
EDGE_MIN = 0.010
CLIP_USD = 5.0
# CROSSING slice (added 2026-07-19 after the PF-rail cut): the live candidate fires
# the moment p_model CROSSES 0.995 inside the final window, but first_fire records a
# window at its FIRST p>=0.99 snap — so windows whose first snap is 0.99<=p<0.995 and
# later drift over 0.995 are fired live yet EXCLUDED from the p>=0.995 first-fire
# slice. The 07-19 -$22.09 loss (first snap p=0.9902, live fire p=0.9953 at t_left
# 17.3s) was invisible to the slice at WR 1.0000. Re-enable gate reads CROSSING rows.
CROSS_P_MIN = 0.995
CUT_TS = 1784460372.0  # 2026-07-19T11:26:12Z UPDOWN_STOP (PF rail); kernel re-entry
                       # gate counts post-halt shadow only
GAMMA = "https://gamma-api.polymarket.com"
CACHE = "/root/Klaus/logs/shadow/updown_sniper/regrade_cache.json"


def refetch_winner(slug):
    url = f"{GAMMA}/markets?slug={slug}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
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


def main():
    refetch = "--refetch" in sys.argv
    files = sorted(glob.glob("/root/Klaus/logs/shadow/updown_sniper/snap_*.jsonl"))
    truth, void_slugs, first_fire, cross_fire = {}, set(), {}, {}
    for fn in files:
        for line in open(fn):
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("type")
            if t == "res":
                if d["ts"] >= FIX_TS:
                    truth[d["slug"]] = d["winner"]
                else:
                    void_slugs.add(d["slug"])
            elif t == "snap":
                slug = d["slug"]
                # gate ledger is BTC-only: the live sniper trades btc-*; multi-asset
                # shadow (eth/sol/xrp 15m, recording since 2026-07-15) grades separately
                if not slug.startswith("btc-"):
                    continue
                if slug in first_fire and (slug in cross_fire or d.get("step") != 300):
                    continue
                step = d.get("step")
                if step not in T_MAX:
                    continue
                t_left = d.get("t_left") or 0.0
                if not (T_MIN <= t_left <= T_MAX[step]):
                    continue
                move = d.get("move") or 0.0
                if abs(move) < MOVE_FLOOR:
                    continue
                sig = max(d.get("sigma1s") or 0.0, SIG_FLOOR)
                z = move / (sig * math.sqrt(max(t_left, 0.5)))
                p_up = 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
                side, p_model = ("Up", p_up) if move > 0 else ("Down", 1.0 - p_up)
                if p_model < P_MIN:
                    continue
                b = d.get("up" if side == "Up" else "down") or {}
                ask, ask_sz = b.get("ask"), b.get("ask_sz") or 0.0
                if ask is None or not (ASK_MIN <= ask <= ASK_MAX[step]):
                    continue
                if p_model - ask - 0.07 * ask * (1 - ask) < EDGE_MIN:
                    continue
                if ask_sz * ask < CLIP_USD:
                    continue
                if slug not in first_fire:
                    first_fire[slug] = {"side": side, "ask": ask, "p_model": p_model,
                                        "t_left": t_left, "step": step, "ts": d["ts"]}
                if (slug not in cross_fire and step == 300
                        and p_model >= CROSS_P_MIN):
                    cross_fire[slug] = {"side": side, "ask": ask, "p_model": p_model,
                                        "t_left": t_left, "step": step, "ts": d["ts"]}

    if refetch:
        try:
            cache = json.load(open(CACHE))
        except Exception:
            cache = {}
        need = [s for s in first_fire if s not in truth]
        for s in need:
            if s in cache:
                if cache[s]:
                    truth[s] = cache[s]
                continue
            w = refetch_winner(s)
            cache[s] = w
            if w:
                truth[s] = w
        json.dump(cache, open(CACHE, "w"))

    graded, wins, pnl = 0, 0, 0.0
    rows = []
    for slug, f in sorted(first_fire.items(), key=lambda kv: kv[1]["ts"]):
        w = truth.get(slug)
        if w is None:
            continue
        graded += 1
        won = (w == f["side"])
        wins += won
        sh = CLIP_USD / f["ask"]
        fee = 0.07 * f["ask"] * (1 - f["ask"]) * sh
        p = sh * (1 - f["ask"]) - fee if won else -(CLIP_USD + fee)
        pnl += p
        rows.append((slug, f["side"], f["ask"], round(f["p_model"], 4),
                     round(f["t_left"], 1), w, won, round(p, 3)))

    n = graded
    wr = wins / n if n else 0.0
    if n:
        zc = 1.96
        den = 1 + zc * zc / n
        ctr = (wr + zc * zc / (2 * n)) / den
        hw = zc * math.sqrt(wr * (1 - wr) / n + zc * zc / (4 * n * n)) / den
        ci = (ctr - hw, ctr + hw)
    else:
        ci = (0.0, 0.0)
    spent = n * CLIP_USD
    print(f"policy-eligible windows: {len(first_fire)}  graded on true labels: {n} "
          f"(ungraded: {len(first_fire) - n}, void-prefix slugs seen: {len(void_slugs)})")
    print(f"WR {wr:.3f} [{ci[0]:.3f},{ci[1]:.3f}]  pnl ${pnl:+.2f} on ${spent:.0f} "
          f"= {100 * pnl / spent if spent else 0:+.2f}%/$")
    ba = sum(f["ask"] for f in first_fire.values()) / max(len(first_fire), 1)
    print(f"avg ask {ba:.3f}  breakeven WR ~{ba / (1 - 0.07 * ba * (1 - ba) * 0):.3f}")
    for step in (300, 900):
        sub = [r for s, f in first_fire.items() if f["step"] == step
               for r in rows if r[0] == s]
        if sub:
            sw = sum(1 for r in sub if r[6])
            sp = sum(r[7] for r in sub)
            print(f"  step {step}s: n={len(sub)} WR {sw / len(sub):.3f} pnl ${sp:+.2f}")
    # RE-ENABLE CANDIDATE slice (pre-registered 2026-07-16 ledger 11:33Z):
    # {p_model >= 0.995, 5m-only}; gate = total graded n>=150 AND this slice's
    # Wilson CI-lo > its own avg-ask breakeven (ask + taker fee)
    cand = [r for s, f in first_fire.items()
            if f["step"] == 300 and f["p_model"] >= 0.995
            for r in rows if r[0] == s]
    if cand:
        cn, cw = len(cand), sum(1 for r in cand if r[6])
        cwr = cw / cn
        den = 1 + 1.96 ** 2 / cn
        ctr = (cwr + 1.96 ** 2 / (2 * cn)) / den
        hw = 1.96 * math.sqrt(cwr * (1 - cwr) / cn + 1.96 ** 2 / (4 * cn * cn)) / den
        cask = sum(r[2] for r in cand) / cn
        cbe = cask + 0.07 * cask * (1 - cask)
        clo = ctr - hw
        print(f"CANDIDATE p>=0.995 5m-only: n={cn} WR {cwr:.4f} "
              f"CI-lo {clo:.4f} vs slice breakeven {cbe:.4f} "
              f"pnl ${sum(r[7] for r in cand):+.2f} -> "
              f"{'PASS' if (n >= 150 and clo > cbe) else 'COLLECTING'} "
              f"(total graded {n}/150)")
    # CROSSING slice = the slice the live candidate ACTUALLY trades (fire at first
    # snap with p>=0.995 passing all gates). Post-cut rows are the kernel re-entry
    # gate: n>=100 with Wilson CI-lo > slice breakeven, post-halt shadow only.
    for label, xf in (("all-history", cross_fire),
                      ("post-cut", {s: f for s, f in cross_fire.items()
                                    if f["ts"] >= CUT_TS})):
        xg = [(s, f, truth[s]) for s, f in xf.items() if truth.get(s) is not None]
        if not xg:
            print(f"CROSSING p>=0.995 5m ({label}): n=0")
            continue
        xn = len(xg)
        xw = sum(1 for s, f, w in xg if w == f["side"])
        xwr = xw / xn
        den = 1 + 1.96 ** 2 / xn
        xlo = ((xwr + 1.96 ** 2 / (2 * xn))
               - 1.96 * math.sqrt(xwr * (1 - xwr) / xn
                                  + 1.96 ** 2 / (4 * xn * xn))) / den
        xask = sum(f["ask"] for s, f, w in xg) / xn
        xbe = xask + 0.07 * xask * (1 - xask)
        xpnl = 0.0
        for s, f, w in xg:
            sh = CLIP_USD / f["ask"]
            fee = 0.07 * f["ask"] * (1 - f["ask"]) * sh
            xpnl += sh * (1 - f["ask"]) - fee if w == f["side"] else -(CLIP_USD + fee)
        verdict = ("PASS" if (label == "post-cut" and xn >= 100 and xlo > xbe)
                   else "COLLECTING")
        print(f"CROSSING p>=0.995 5m ({label}): n={xn} WR {xwr:.4f} "
              f"CI-lo {xlo:.4f} vs breakeven {xbe:.4f} pnl ${xpnl:+.2f} -> {verdict}")
    if "--rows" in sys.argv:
        for r in rows:
            print(r)


if __name__ == "__main__":
    main()
