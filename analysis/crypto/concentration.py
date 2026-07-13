"""Wallet concentration + census in the certainty cells on fresh tape."""
import json, collections
rows = [json.loads(l) for l in open("/root/Klaus/analysis/crypto/updown_audit/trades_fresh.jsonl")]

# target cells: 15m t_rel<=120 p in [0.90,0.99); 5m t_rel<=30 p in [0.90,0.995)
cell = []
for t in rows:
    if t["side"] != "BUY": continue
    slug = t["_slug"]; step = 300 if "-5m-" in slug else 900
    end = int(slug.rsplit("-",1)[1]) + step
    trel = end - t["timestamp"]
    p = float(t["price"])
    if step == 900 and 0 <= trel <= 120 and 0.90 <= p < 0.99: cell.append(t)
    elif step == 300 and 0 <= trel <= 30 and 0.90 <= p < 0.995: cell.append(t)
print(f"certainty-cell fills: {len(cell)}")
W = collections.defaultdict(lambda: [0,0.0,0.0])  # n, $vol, ev$
for t in cell:
    p, s = float(t["price"]), float(t["size"])
    win = 1 if t["outcome"] == t["_winner"] else 0
    fee = 0.07*p*(1-p)
    w = W[t["proxyWallet"]]
    w[0]+=1; w[1]+=p*s; w[2]+=(win-p-fee)*s
top = sorted(W.items(), key=lambda kv: -kv[1][1])
tot = sum(v[1] for v in W.values())
print(f"wallets in cells: {len(W)}, $vol {tot:,.0f}")
cum = 0
print(f"{'rank':>4} {'$vol':>9} {'share':>6} {'cum':>6} {'n':>6} {'ev$':>8}  wallet")
for i,(addr,(n,vol,ev)) in enumerate(top[:15]):
    cum += vol
    print(f"{i+1:>4} {vol:>9.0f} {vol/tot:>6.1%} {cum/tot:>6.1%} {n:>6} {ev:>8.0f}  {addr[:20]}")
# how many wallets to reach 80%?
cum=0; k=0
for addr,(n,vol,ev) in top:
    cum+=vol; k+=1
    if cum/tot>=0.8: break
print(f"wallets for 80% of certainty-cell volume: {k}")
# fresh overall census top 10 (all fills, all prices)
W2 = collections.defaultdict(lambda: {"cash":0.0,"pos":collections.defaultdict(float),"n":0})
for t in rows:
    p, s = float(t["price"]), float(t["size"])
    fee = 0.07*p*(1-p)*s
    w = W2[t["proxyWallet"]]
    key=(t["_slug"],t["outcome"],t["_winner"])
    if t["side"]=="BUY": w["cash"]-=p*s+fee; w["pos"][key]+=s
    else: w["cash"]+=p*s-fee; w["pos"][key]-=s
    w["n"]+=1
res=[]
for addr,w in W2.items():
    pnl=w["cash"]
    for (slug,outc,winn),pos in w["pos"].items():
        if outc==winn: pnl+=max(pos,0.0)
    res.append((pnl,addr,w["n"]))
res.sort(reverse=True)
print("\nfresh census top 10 (taker flows, ~2d):")
for pnl,addr,n in res[:10]: print(f"  {pnl:>9.0f} {n:>6}  {addr}")
