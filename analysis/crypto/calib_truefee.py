"""Calibration with official fee = 0.07 * p * (1-p) per share, takers only."""
import json, collections
rows = [json.loads(l) for l in open("/root/Klaus/analysis/crypto/updown_audit/trades.jsonl")]
TB = [(0,15),(15,30),(30,60),(60,120),(120,300),(300,600),(600,900)]
PB = [(0.50,0.55),(0.55,0.60),(0.60,0.70),(0.70,0.80),(0.80,0.90),(0.90,0.95),(0.95,0.99),(0.99,1.0)]
agg = collections.defaultdict(lambda: [0,0,0.0,0.0])
day_span = (max(r["timestamp"] for r in rows) - min(r["timestamp"] for r in rows))/86400
for t in rows:
    slug = t["_slug"]
    if "-15m-" not in slug or t["side"] != "BUY": continue
    end = int(slug.rsplit("-",1)[1]) + 900
    trel = end - t["timestamp"]
    if trel < 0: continue
    p, s = float(t["price"]), float(t["size"])
    if p < 0.50: continue
    win = 1 if t["outcome"] == t["_winner"] else 0
    fee = 0.07 * p * (1-p)
    ev = (win - p - fee) * s
    for lo,hi in TB:
        if lo <= trel < hi:
            for plo,phi in PB:
                if plo <= p < phi:
                    a = agg[(lo,hi,plo,phi)]; a[0]+=1; a[1]+=win; a[2]+=p*s; a[3]+=ev
print(f"span {day_span:.1f}d | 15m BUY p>=0.50, TRUE fee 0.07*p*(1-p)")
print(f"{'t_rel':>9} {'price':>11} {'n':>6} {'WR':>6} {'$vol':>9} {'netEV/$':>8} {'$EV/day':>8}")
tot=0
for (lo,hi,plo,phi),(n,w,vol,ev) in sorted(agg.items()):
    if n >= 15:
        print(f"{lo:>4}-{hi:<4} {plo:.2f}-{phi:.2f}  {n:>6} {w/n:>6.3f} {vol:>9.0f} {ev/vol:>8.3f} {ev/day_span:>8.1f}")
        if ev>0 and hi<=300: tot += ev
print(f"\nsum positive-EV cells with t_rel<300s: ${tot:.0f} over {day_span:.1f}d = ${tot/day_span:.0f}/day (BTC 15m only)")
