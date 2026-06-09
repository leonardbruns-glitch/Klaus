# badatmath audit — recent ramp + beat-plan (2026-06-09, ground-truth)
Wallet 0x8fbd7cf5f806f563080864694415829f7229a959 — value $6,645.
Pulled 34,777 activity events (04-23→06-09) + 5,861 Gamma resolutions. Scripts: analyze.py, /tmp/buckets.py.

## LEDGER (resolved tokens, n=7,610)
- Deployed $64,359 → realized +$7,436 = **11.6% ROI**.
- YES leg: $30,419 → +$5,541 = **18.2% ROI**, WR 18.0% (low-WR/high-payout band).
- NO  leg: $33,142 → +$1,941 =  5.9% ROI, WR 68.0% (favorites ballast).

## THE RAMP = SCALE, NOT A BETTER EDGE
Weekly ROI was already ~19% in mid-May. Week of **Jun 1: deployment ~2x to $23.4k**, held 19.1% ROI,
+$4,476 in one week. Trade count: ~500/d (May) → 1.8k–4.2k/d (Jun 4–6). Pivoted YES-heavy: YES share of
buy$ 25–40% (May) → 65–78% (Jun 4–9). Per-fill shrank ($3 → $1–2). Growth = breadth × bankroll recycle
(~11x turnover/mo), NOT higher per-bet edge, NOT Kelly.

## EDGE SIGNATURE (last ~28d, WR vs implied) — the over-dispersion harvest
YES (20.8% ROI/$28k): 0.10-0.15 WR15.2 vs impl11.8 (+30%); 0.15-0.22 22.6 vs17.5 (+29%);
  0.30-0.40 43.6 vs34.2 (+28%); <0.05 wings +35% (lottery); WEAK 0.05-0.10 (+4%).
NO (6.6% ROI/$26k): 0.50-0.85 favorites steady +5-6%; TROUGH 0.40-0.50 (-1.3%); rest noise.

## EXECUTION = MAKER (decisive)
Recent 14d: 18,760/18,907 fills = **99.2% maker**. Only 147 taker (144 BUY). He POSTS bids, the FLB
lottery-YES buyers + panic sellers fill him BELOW ask. A taker copy pays the ask → +29% buckets compress.

## BEAT-PLAN (confidence-labelled) — UPDATED after n>=100 join (pcal_join.py)
1. [FALSIFIED at n>=100] p_cal SELECTION does NOT beat blind band. Join his YES °C fills x Klaus PRE_PEAK
   p_cal x Gamma (n=3,044 band): p_cal>mkt n=553 ROI +5.5% vs p_cal<=mkt n=2,491 ROI +27.6% — ANTI-PREDICTIVE
   (reverses the teardown's 34%-vs-12% n=105/65 noise). Model floored to ~0 on 72% of band buckets = no
   positive signal. ONLY usable form: NEGATIVE filter (skip p_cal>mkt) -> band 24.7%->27.6% (+2.9pp, modest,
   robust across price-thirds). => cannot beat his YES ROI via forecast; only match the structural edge.
2. [GATE] Maker execution mandatory — without it you can't even MATCH (his edge lives at maker prices).
   Biggest Klaus gap; band executor not yet wired (BAND_LIVE=False, shadow only).
3. [STRUCTURAL] Absolute $ NOT beatable at $70 capital — his $7.4k/mo is a BANKROLL function (11x recycle),
   not skill. ROI% is the only honest "beat" target until equity grows.
4. [ALREADY-BETTER] Klaus lockout-NO (M1β, 98%+ physical certainty) dominates his probabilistic 68%-WR NO.
5. [MATCHED] Multi-day d/d+1/d+2 band — shadow fixed today (was NameError-dead).
