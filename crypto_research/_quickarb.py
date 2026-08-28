"""60-second gut-check: cross-leg dutch book on cached BTC.
UP_ask + DOWN_ask < 1  => buy both legs, locked $1 payout (model-free arb).
peer_ask on each timeline row = the OTHER leg's ask, so we can compute per-row."""
import pickle
import numpy as np

panels = pickle.load(open('/root/Klaus/data/_era_BTC_300_2026-05-26_2026-05-31.pkl', 'rb'))
sums, sizes, s2r = [], [], []
rows = 0
for p in panels:
    for r in p.timeline:
        a = r.best_ask
        pa = r.peer_ask
        if a is None or pa is None or not (0 < a < 1) or not (0 < pa < 1):
            continue
        rows += 1
        sums.append(a + pa)
        sizes.append(r.ob_top1_ask_size or 0.0)
        s2r.append(r.seconds_to_resolution if r.seconds_to_resolution is not None else -1)
sums = np.array(sums); sizes = np.array(sizes); s2r = np.array(s2r)
print(f"rows with both asks: {rows:,}")
print(f"UP_ask+DOWN_ask  min={sums.min():.3f}  p1={np.percentile(sums,1):.3f}  "
      f"median={np.median(sums):.3f}  mean={sums.mean():.3f}")
for thr in (1.00, 0.99, 0.98, 0.96, 0.95, 0.90):
    m = sums < thr
    n = int(m.sum())
    pct = 100 * n / rows
    avg_edge = (1 - sums[m]).mean() if n else 0
    med_sz = np.median(sizes[m]) if n else 0
    fillable = int((sizes[m] >= 5).sum()) if n else 0
    print(f"  sum<{thr:.2f}: n={n:<6} ({pct:5.2f}%)  avg_locked_edge=${avg_edge:.3f}  "
          f"median_ask_size={med_sz:6.1f}  with_size>=5: {fillable}")
# fee reality: buying both legs pays ~fee each; net arb needs sum + 2*fee*notional < 1.
# at p~0.5 fee ~0.9c/leg, +slippage ~1.6c/leg => need sum < ~0.95 to clear after costs.
m = sums < 0.95
print(f"\nAFTER-COST survivors (sum<0.95, the rough net-profit threshold): "
      f"n={int(m.sum())}  ({100*m.sum()/rows:.3f}% of rows)")
if m.sum():
    print(f"  of those, with ask_size>=5 shares: {int((sizes[m]>=5).sum())}")
    print(f"  timing: median seconds_to_resolution = {np.median(s2r[m]):.0f}s")
