# badatmath — definitive 31-day teardown (2026-05-17 → 06-17)

Wallet `0x8fbd7cf5f806f563080864694415829f7229a959` "badatmath."
Fresh pull: 47,352 weather events / 42,470 buys / 7,955 resolved buckets.
Portfolio value $12,384 (open positions) + cash; realized cumPnL spine $194 → $13,289.
Scripts: fetch_31d.py, build_winners.py (CLOB tokens[].winner — gamma condition_ids query is dead),
teardown_31d.py.

## THE ONE-LINE THESIS
He has NO forecast skill. He **agrees with the market on WHERE the mode is** and bets the market
**over-disperses** the daily-high (true σ≈1.3° < implied). Decision variable = **PRICE**, not weather:
near-mode buckets underpriced → buy YES 0.05–0.45; favorite buckets' NO underpriced → buy NO 0.52–0.95.
Same bucket often gets both (pair → merge $1). 98.6% MAKER. Growth = ~1 equity-turn/day × ~100% daily
recycle × steady +11% ROI/turn, compounding $200 → $13k+ in ~4 weeks.

## DECOMPOSITION (every question)
1. **Decision maker** = the ASK PRICE relative to the market mode. No nowcast. Buys every city every
   day, never cuts losers, doesn't bet more on better events (corr spend↔ROI ≈ 0).
2. **Legs/event**: median 4 YES + 3 NO buckets per city-day (p90 7). 83% of events two-sided.
   (We post mode±1 = ≤3 YES — narrower.)
3. **Entry prices**: YES median 0.130, meat 0.05–0.40 (each 0.05-wide band ~15-18% of $), hard cap ~0.45,
   cheap <0.05 wings = 3.3%. NO median 0.650, meat 0.52–0.95.
4. **Maker mechanics**: 98.6% maker (603 taker / 42,544). Rests bids and lets them fill — p90 fill-span
   11.4h at one price, up to 110 fills on a single resting bid. BUT he is NOT pure set-and-forget: median
   2 distinct fill-prices per bucket (mean 2.9, p90 6) — ~45% single resting bid, ~55% laddered/repriced
   across the ~1.5-day market life.
5. **YES vs NO**: pure price-band rule. ask∈[~0.03,0.45] near mode → YES; NO ask∈[0.52,0.95] on
   favorites → NO. Switch is the price, not a signal.
6. **Sizing**: $-bell, share-U. YES $/fill 2.65(off0)→1.10(off4) but shares 17→73 (wings = cheap lottery
   with huge payout). NO flat ~$5-6/fill. Per-event ~$40 YES + $30 NO. Per-fill tiny (~$1.15 YES median)
   — sizing scales by BREADTH, not bet size.
7. **Recycle**: MERGE $41.3k (2,504×) + REDEEM $86.1k (2,304×) = recycles ~90–107% of daily buy$ SAME DAY.
   This is the engine that lets a $200 base deploy $12k/day.
8. **Queue/priority**: blankets all of d+0/d+1/d+2 simultaneously (no selection); pair-legs co-posted
   (median NO−YES lag +0.4h) with a lockout-NO tail (p75 +24h).
9. **d0 vs d1/d2**: spend ~40/40/20 across d+0/d+1/d+2. ROI rises with horizon: YES d+0 +12% / d+1 +19% /
   d+2 +19%; NO d+0 +0.3% / d+1 +6% / d+2 +7%. He doesn't "choose" — he quotes all three early.
10. **YES→NO switch**: mostly simultaneous pair-quote (median +0.4h); ~25% added a full day later
    (lockout-style favorite-NO).
11. **Merge**: when YES+NO co-fill on a bucket for Σ<$1 he merges → $1 risk-free; 40% of buckets are
    two-sided ⇒ industrial merge flow = the same-day cash velocity.

## EDGE SIGNATURE (over-dispersion, n=thousands, decision-grade)
YES: 0.10-0.15 WR 14.6 vs impl 11.8 (+2.8pp, ROI +24%); 0.30-0.40 WR 40.7 vs 34.2 (+6.5pp, +19%);
>0.55 NEGATIVE (-17%). NO: 0.45-0.85 all +2.7 to +4.0pp; >0.95 ~fair. Resolved total ROI **+11.4%**.

## GROWTH (200 → 13k+ realized, ~12-15k value)
- Phase 1 (5/17-26): breadth ramp 41→45 cities, 69→117 events/day; +10-15%/day; equity $267→$2,560.
- Phase 2 (5/27-6/3): NO-heavy plateau, choppy (several -EV days); ~$2,600-2,800.
- Phase 3 (6/4-16): vertical. 6/4 +$2,593 (121% day, heat-anomaly YES tail) then steady +$500-1,800/day;
  deploy $2.6k→$12.7k/day; equity $5,246→$13,289.
- Lever = TURNOVER not edge: ~1 full-equity turn/day (deploy/value 0.5-1.5) × ~100% recycle ×
  steady +11% ROI/turn. Breadth saturated by late May; the ramp is pure compounding + one fat tail.
