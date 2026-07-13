"""True-fee calibration on FRESH tape (Jul 11-13), 15m and 5m separately."""
import json, collections
rows = [json.loads(l) for l in open("/root/Klaus/analysis/crypto/updown_audit/trades_fresh.jsonl")]
mkts = set(r["_slug"] for r in rows)
print(f"rows {len(rows)} markets {len(mkts)}")
TB = [(0,15),(15,30),(30,60),(60,120),(120,300),(300,900)]
PB = [(0.50,0.55),(0.55,0.60),(0.60,0.70),(0.70,0.80),(0.80,0.90),(0.90,0.95),(0.95,0.99),(0.99,1.0)]
for tag, step in (("15m",900),("5m",300)):
    agg = collections.defaultdict(lambda: [0,0,0.0,0.0])
    tmin, tmax = 1e18, 0
    for t in rows:
        if f"-{tag}-" not in t["_slug"] or t["side"] != "BUY": continue
        end = int(t["_slug"].rsplit("-",1)[1]) + step
        trel = end - t["timestamp"]
        if trel < 0 or trel > step: continue   # inside window only
        p, s = float(t["price"]), float(t["size"])
        if p < 0.50: continue
        tmin, tmax = min(tmin,t["timestamp"]), max(tmax,t["timestamp"])
        win = 1 if t["outcome"] == t["_winner"] else 0
        fee = 0.07 * p * (1-p)
        ev = (win - p - fee) * s
        for lo,hi in TB:
            if lo <= trel < hi:
                for plo,phi in PB:
                    if plo <= p < phi:
                        a = agg[(lo,hi,plo,phi)]; a[0]+=1; a[1]+=win; a[2]+=p*s; a[3]+=ev
    days = (tmax-tmin)/86400
    tot = pos = 0.0
    print(f"\n=== {tag} in-window BUY p>=0.50 (fresh {days:.1f}d) ===")
    print(f"{'t_rel':>9} {'price':>11} {'n':>7} {'WR':>6} {'$vol':>10} {'netEV/$':>8} {'$EV/day':>9}")
    for (lo,hi,plo,phi),(n,w,vol,ev) in sorted(agg.items()):
        if n >= 30:
            print(f"{lo:>4}-{hi:<4} {plo:.2f}-{phi:.2f}  {n:>7} {w/n:>6.3f} {vol:>10.0f} {ev/vol:>8.3f} {ev/days:>9.1f}")
        tot += ev
        if ev > 0: pos += ev
    print(f"{tag}: all-cell net ${tot/days:,.0f}/day | positive-cells ${pos/days:,.0f}/day")
