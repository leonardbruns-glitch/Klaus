# onlylucknobrain teardown — 2026-06-26

Wallet `0x6a8d1709bfb718d8555d315a983c4816278350f9` ("OnlyLuckNoBrain"). Same domain as
badatmath: Polymarket daily-HIGH-temperature markets. Data: `act.jsonl` (106,689 rows,
genesis **2026-03-24** → 06-26), `trd.jsonl` (taker-only, 06-04→now window), `res.json`
(12,136 markets, 11,857 CLOB-winner resolved). Validation: MTM replay $9,351 == live
/value $9,298 (100.6%); net-growth $24,453 == resolved-PnL $24,582.

## STRATEGY (reverse-engineered)
- **Maker-heavy HYBRID:** ~78% maker / 22% taker (06-04→now window, n=15,919 buys). NOT a
  pure maker like badatmath (98.6%) — he crosses the spread on ~1 in 5 fills.
- **100% daily-HIGH temp**, 0 daily-min, 50 cities, 3,739 events. Non-weather = $182 (noise).
- **YES band 0.05–0.45, median 0.16** (mean 0.176). Mass 0.15–0.35 (56% of YES$). Dust
  <0.05 = 12% of fills but only 5% of $. Almost nothing >0.45.
- **NO band 0.62–0.85 (61% of NO$) + tail-NO 0.85–0.95 (10% of NO$), median 0.76.** Deeper
  favorite than badatmath (0.61). Tail-NO 0.85–0.95 is the slice our bot clips (NO_MAX 0.85).
- **YES/NO $ split 49/51**; but YES = many dust fills (median **$0.99**, n=65k), NO = chunkier
  (median **$6.19**, n=17k). Overall median fill $1.42, mean $4.05.
- **Per-event: median 2 YES + 1 NO buckets** (mean 2.1 / 1.6). Narrower than badatmath (4+3).
- **Days-out: d+1 47.5% / d+2 46.9%**, ~0 at d+0 (1%), little d+3+. Posts on next-day & 2-out.
- **ZERO MERGE events across 94 days.** Recycle = REDEEM ($248k) + SELL ($101k, median sell
  px 0.36 = active profit-taking on appreciated YES, NOT 0.99 winner-recycle). ~1 turn/day.
- Hold-to-resolution dominant; ~700–900 fills/day, buy$ ~$3–6k/day.

## EDGE (resolved n=12,097, cost $333,707)
- **Blended ROI +7.4%** ($24,582 pnl). YES-side +9.6%, NO-side +5.3%.
- By side × days-out:
  - **YES d+1: +26.7% ROI, WR 23%, +$10,326 (THE alpha)** — cheap near-mode YES the day before.
  - YES d+2 +4.3% (biggest cost $110k, thin), YES d+0 **−46.4%** (loser, tiny n).
  - NO d+2 **+5.6%, +$6,192** (workhorse), NO d+1 +4.3%, NO d+3+ +5.3%.
- Mirror of badatmath's edge map (his strongest = d+2 YES +30%; onlyluck = d+1 YES).

## CAPITAL / GROWTH — the $200 answer
- Genesis 03-24 ~$15. **Capital floor (max own cash sunk) = −$4,870, hit 2026-04-12** (week 3).
- He **front-loaded ~$2.5k–$4.9k** of seed capital over weeks 1–3 to build breadth (buy$ ramped
  $646→$4k/day in 2 weeks, 700–1,400 fills/day from the start). Self-funding (cum_cf sustained
  positive) only from ~04-28.
- **Total profit ~$24,453 over 94 days** on peak working capital ~$4.9k (~6× on capital, ~1.9%/day
  effective). Current equity ≈ $9.3k positions + ~$15k cash ≈ $24k.
- **He did NOT start from $200.** $200 is 1/10–1/25 of the seed he actually deployed.

## VERDICT vs $200
Reverse-engineering: DONE (and it's our existing BAND system, confirmed/refined). $200→profit
as a faithful replication: **NO** — the +7.4% edge is breadth-gated (realized only across
thousands of $1–6 buckets; per-bucket YES WR is 23–33% = huge variance) and execution-gated.
Our OWN live mirror at small capital already nets YES −4.9% (vs his +9.6%) — direct empirical
proof the edge does not survive our scale+execution. Merge is NOT the missing piece (he has
zero). The binding constraints are seed capital (~$5k for breadth) and YES fill quality.
