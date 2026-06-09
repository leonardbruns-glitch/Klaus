import json, time
from collections import defaultdict
rows=[json.loads(l) for l in open("analysis/weather/badatmath_audit/activity_raw.jsonl")]
res=json.load(open("analysis/weather/badatmath_audit/resolutions.json"))
def winner(cid):
    v=res.get(cid)
    if not v or not v.get('closed'): return None
    try:
        p=json.loads(v['outcomePrices']); 
        if float(p[0])>0.5: return 0
        if float(p[1])>0.5: return 1
    except: pass
    return None
def day(ts): return time.strftime("%Y-%m-%d", time.gmtime(ts))
def wk(ts):  # week label
    return time.strftime("%Y-%m-%d", time.gmtime(ts - (time.gmtime(ts).tm_wday)*86400))

# group trades by asset(token)
tok=defaultdict(lambda:{"buyS":0.0,"buyU":0.0,"sellS":0.0,"sellU":0.0,"cid":None,"oidx":None,"out":None,"first":1e11,"last":0})
for x in rows:
    if x['type']!="TRADE": continue
    a=x['asset']; t=tok[a]; sz=float(x.get('size',0) or 0); u=float(x.get('usdcSize',0) or 0)
    t["cid"]=x['conditionId']; t["oidx"]=x.get('outcomeIndex'); t["out"]=x.get('outcome')
    t["first"]=min(t["first"],x['timestamp']); t["last"]=max(t["last"],x['timestamp'])
    if x.get('side')=="BUY": t["buyS"]+=sz; t["buyU"]+=u
    else: t["sellS"]+=sz; t["sellU"]+=u

# realized pnl per token (resolved only)
tot=defaultdict(float); cnt=defaultdict(int)
by_wk=defaultdict(lambda:{"pnl":0.0,"cost":0.0,"n":0,"yes_pnl":0.0,"yes_cost":0.0,"no_pnl":0.0,"no_cost":0.0})
by_side={"Yes":{"pnl":0.0,"cost":0.0,"n":0,"win":0},"No":{"pnl":0.0,"cost":0.0,"n":0,"win":0}}
resolved_cost=0.0; resolved_pnl=0.0
for a,t in tok.items():
    w=winner(t["cid"])
    if w is None: continue
    net_sh=t["buyS"]-t["sellS"]; net_cost=t["buyU"]-t["sellU"]
    if net_sh<=1e-6 and net_cost<=0: continue
    won = (t["oidx"]==w)
    payoff = net_sh*(1.0 if won else 0.0)
    pnl = payoff - net_cost
    side=t["out"]; W=wk(t["first"])
    by_wk[W]["pnl"]+=pnl; by_wk[W]["cost"]+=max(net_cost,0); by_wk[W]["n"]+=1
    by_wk[W][("yes" if side=="Yes" else "no")+"_pnl"]+=pnl
    by_wk[W][("yes" if side=="Yes" else "no")+"_cost"]+=max(net_cost,0)
    if side in by_side:
        s=by_side[side]; s["pnl"]+=pnl; s["cost"]+=max(net_cost,0); s["n"]+=1; s["win"]+= (1 if won else 0)
    resolved_cost+=max(net_cost,0); resolved_pnl+=pnl

print("="*70)
print(f"RESOLVED LEDGER: tokens={sum(1 for a,t in tok.items() if winner(t['cid']) is not None)}")
print(f"  total cost deployed (resolved) = ${resolved_cost:,.0f}")
print(f"  total realized PnL             = ${resolved_pnl:,.0f}   ROI={100*resolved_pnl/resolved_cost:.1f}%")
print("="*70)
print("BY SIDE:")
for s,v in by_side.items():
    if v['n']: print(f"  {s:3}: n={v['n']:5d} cost=${v['cost']:8,.0f} pnl=${v['pnl']:8,.0f} ROI={100*v['pnl']/v['cost']:6.1f}%  WR={100*v['win']/v['n']:.1f}%")
print("="*70)
print("WEEKLY (by entry week) — THE RAMP:")
print(f"{'week':11} {'n':>5} {'cost$':>8} {'pnl$':>8} {'ROI%':>6} {'YESroi':>7} {'NOroi':>7}")
for W in sorted(by_wk):
    v=by_wk[W]; roi=100*v['pnl']/v['cost'] if v['cost'] else 0
    yroi=100*v['yes_pnl']/v['yes_cost'] if v['yes_cost'] else 0
    nroi=100*v['no_pnl']/v['no_cost'] if v['no_cost'] else 0
    print(f"{W:11} {v['n']:5d} {v['cost']:8,.0f} {v['pnl']:8,.0f} {roi:6.1f} {yroi:7.1f} {nroi:7.1f}")
