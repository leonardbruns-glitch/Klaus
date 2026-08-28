"""Calibration + wallet census on updown taker tape."""
import json, collections

OUT = "/root/Klaus/analysis/crypto/updown_audit"
rows = [json.loads(l) for l in open(f"{OUT}/trades.jsonl")]
print(f"rows: {len(rows)}")

def wend(slug):
    parts = slug.rsplit("-", 1)
    w = int(parts[1]); step = 300 if "-5m-" in slug else 900
    return w + step, step

# ---------- 1. BUY-fill calibration by (t_rel, price) ----------
# t_rel buckets (seconds before close), price buckets
TB = [(0,5),(5,15),(15,30),(30,60),(60,120),(120,300),(300,900)]
PB = [(0.50,0.60),(0.60,0.70),(0.70,0.80),(0.80,0.90),(0.90,0.95),(0.95,0.99),(0.99,1.0)]
for step_want, label in ((900, "15m"), (300, "5m")):
    agg = collections.defaultdict(lambda: [0,0,0.0,0.0])  # n, wins, $vol, ev$
    for t in rows:
        end, step = wend(t["_slug"])
        if step != step_want or t["side"] != "BUY":
            continue
        trel = end - t["timestamp"]
        if trel < 0:
            continue
        p, s = float(t["price"]), float(t["size"])
        if p < 0.50:
            continue  # focus: buying the favorite/decided side
        win = 1 if t["outcome"] == t["_winner"] else 0
        fee = 0.10 * min(p, 1-p)
        ev = (win - p - fee) * s      # $ pnl of this fill held to resolution
        for lo,hi in TB:
            if lo <= trel < hi:
                for plo,phi in PB:
                    if plo <= p < phi:
                        a = agg[(lo,hi,plo,phi)]
                        a[0]+=1; a[1]+=win; a[2]+=p*s; a[3]+=ev
    print(f"\n=== {label} BUY fills at p>=0.50: WR vs price by seconds-to-close (net-EV $/$ after 10% fee)")
    print(f"{'t_rel':>10} {'price':>12} {'n':>6} {'WR':>6} {'avg_p':>6} {'$vol':>9} {'netEV/$':>8}")
    for (lo,hi,plo,phi),(n,w,vol,ev) in sorted(agg.items()):
        if n >= 20:
            print(f"{lo:>4}-{hi:<5} {plo:.2f}-{phi:.2f}   {n:>6} {w/n:>6.3f} {vol/ (sum(float(r['size']) for r in [])+1e-9) if False else 0:>0.0f}{'':>0} {vol:>9.0f} {ev/vol:>8.3f}" if False else
                  f"{lo:>4}-{hi:<5} {plo:.2f}-{phi:.2f}   {n:>6} {w/n:>6.3f} {'':>6} {vol:>9.0f} {ev/vol:>8.3f}")

# ---------- 2. taker aggregate ----------
tot_ev = tot_vol = 0.0
for t in rows:
    p, s = float(t["price"]), float(t["size"])
    win = 1 if t["outcome"] == t["_winner"] else 0
    fee = 0.10 * min(p, 1-p)
    if t["side"] == "BUY":
        tot_ev += (win - p - fee) * s
    else:
        tot_ev += (p - win - fee) * s   # sold at p, gave up token worth win
    tot_vol += p * s
print(f"\nALL taker fills: net PnL ${tot_ev:,.0f} on ${tot_vol:,.0f} notional -> {100*tot_ev/tot_vol:.2f}%")

# ---------- 3. wallet census (taker flows + redemption) ----------
W = collections.defaultdict(lambda: {"cash":0.0,"n":0,"vol":0.0,
                                     "pos":collections.defaultdict(float),
                                     "neg":False,"mkts":set()})
for t in rows:
    w = W[t["proxyWallet"]]
    p, s = float(t["price"]), float(t["size"])
    fee = 0.10 * min(p, 1-p) * s
    key = (t["_slug"], t["outcome"], t["_winner"])
    if t["side"] == "BUY":
        w["cash"] -= p*s + fee; w["pos"][key] += s
    else:
        w["cash"] += p*s - fee; w["pos"][key] -= s
    w["n"] += 1; w["vol"] += p*s; w["mkts"].add(t["_slug"])
res = []
for addr, w in W.items():
    pnl = w["cash"]; neg = False
    for (slug, outcome, winner), pos in w["pos"].items():
        if pos < -0.01: neg = True
        if outcome == winner: pnl += max(pos, 0.0)
    res.append((pnl, addr, w["n"], w["vol"], len(w["mkts"]), neg))
res.sort(reverse=True)
print(f"\nwallets: {len(res)}  (neg=True means taker-SELLs exceed taker-BUYs somewhere -> maker fills invisible, PnL unreliable)")
print(f"{'pnl$':>10} {'fills':>6} {'vol$':>10} {'mkts':>5} {'neg':>5}  wallet")
for pnl, addr, n, vol, nm, neg in res[:15]:
    print(f"{pnl:>10.0f} {n:>6} {vol:>10.0f} {nm:>5} {str(neg):>5}  {addr}")
print("   ...bottom 5:")
for pnl, addr, n, vol, nm, neg in res[-5:]:
    print(f"{pnl:>10.0f} {n:>6} {vol:>10.0f} {nm:>5} {str(neg):>5}  {addr}")
