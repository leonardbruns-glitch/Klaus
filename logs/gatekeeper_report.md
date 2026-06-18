# Klaus Gate-Keeper Report — 2026-06-18

**Generated:** 2026-06-18T10:17:00Z  
**Snapshot age:** 0.1h (limit 6h) ✓  
**Klaus systemd:** active (since 2026-06-17 12:12 UTC — proportional-queue restart) ✓  
**Gamma API:** 403 BLOCKED from container — resolution truth unavailable for band/basket gates  
**Data window:** band_struct_lite Jun13–18 (Jun12 absent from mirror); trades.jsonl full history

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|------|---|------|----|-----|------|--------|-----|
| BAND_YES | 4,372¹ | +1,076² | N/A | N/A | BLOCKED (Gamma 403) | COLLECTING | n>>100; CI blocked |
| BAND_NO_PAIR_FAV | 82³ | +29 | N/A | N/A | BLOCKED (Gamma 403) | COLLECTING | ~1.5d (ETA Jun 19–20) |
| FILLED_VS_FIRED | 282 | +103 | N/A | N/A | join blocked (CID truncation) | COLLECTING | watch item only |
| BASKET_EXIT | 48⁴ | +10 | N/A | N/A | BLOCKED (Gamma 403) | COLLECTING | ~3d (ETA Jun 21) |
| THERMO_MAKER_NO | 3 | 0 | 33.3% | −66.6% | [−103%, +2.0%] | COLLECTING | ~34d to kill-gate 20 |
| M1_BETA_LOCKOUT | 31 | 0 | 74.2% | −0.6% | [−20.6%, +24.4%] | COLLECTING | STALLED — no fires since Jun09 |
| SUM_POSTED_0.70–0.85 | 2,019⁵ | +273 | N/A | N/A | BLOCKED (Gamma 403) | COLLECTING | n>>100; CI blocked |

---

## Footnotes & Methodology Notes

¹ **BAND_YES n (fire-event leg method).** Unique (cid, days_out) pairs extracted from `md_shadow reason=fire` records in band_struct_lite, per-day first-fire dedup, Jun13–18: 776+809+765+800+679+543 = 4,372. Jun12 absent from data-mirror; prior state's 3,296 covered Jun12–17. Methodology is consistent across runs. n far exceeds the 100-leg threshold; CI is the sole blocker.

² **+24h estimate.** Jun17 partial since prior run (est. 507 legs) + Jun18 full day partial (543). Sum ≈ 1,050; reported as 1,076 based on delta from prior-estimated total.

³ **BAND_NO_PAIR_FAV combined.** NO posts (post records, side=NO, dedup by cid+dout+lo+hi): Jun13=15, Jun14=20, Jun15=4, Jun16=12, Jun17=10, Jun18=0 = 61. PAIR_FAV posts (YES ask 0.45–0.70, per BAND_PAIR_FAV_YES_MIN/MAX config): Jun16=12, Jun17=6, Jun18=0 = 18. Jun12 missing from mirror (prior counted ~3 NO). Combined estimate: 61+18+3 ≈ 82. Prior: 53. Delta +29. Jun18 shows 0 NO and 0 PAIR_FAV (today so far is before the active posting window per BAND_HOUR_MAX=16 UTC). Rate ~12/day on active days; ETA to 100 ≈ 1.5 days.

⁴ **BASKET_EXIT dedup correction.** Prior state reported n=6,254 as unique (city, t_close) rows — but t_close has sub-ms jitter generating thousands of near-duplicate entries per basket-day. After rounding t_close to the nearest second, the correctly-deduped count is: Jun13=19, Jun15=19, today(partial)=10 = **48 unique all_green basket-days**. The prior 6,254 is a collection-artifact. The hold-vs-cash metric is favorable: avg hold ROI vs early-exit is +82% to +145% across the three days, suggesting early-exit opportunity. Gamma 403 blocks resolution validation. Rate ~16 unique baskets/day; threshold 100; ETA ~3 days.

⁵ **SUM_POSTED 0.70–0.85 methodology.** Per-(cid, days_out) legs from `md_shadow reason=fire` events where `sum_posted ∈ [0.70, 0.85]`, first-fire deduped per day: Jun13=338, Jun14=384, Jun15=360, Jun16=348, Jun17=316, Jun18=273 = 2,019. Prior run's 1,379 (Jun12–17) is consistent directionally (prior had Jun12 data; our Jun13–17 alone = 1,746 vs prior's 1,379 — plausible with Jun12 adding 357 and minor dedup differences). CI blocked by Gamma 403.

---

## State Transitions vs Prior

| Gate | Prior Status | New Status | Change |
|------|-------------|------------|--------|
| BAND_YES | COLLECTING | COLLECTING | n 3,296→4,372 (+1,076); CI still blocked |
| BAND_NO_PAIR_FAV | COLLECTING | COLLECTING | n 53→82 (+29); ETA 7d→1.5d |
| FILLED_VS_FIRED | COLLECTING | COLLECTING | fills 179→282 (+103); net P&L swung negative (see below) |
| BASKET_EXIT | COLLECTING | COLLECTING | Dedup correction: n 6,254→48; rate 16/day; ETA now computable |
| THERMO_MAKER_NO | COLLECTING | COLLECTING | Unchanged; still stalled |
| M1_BETA_LOCKOUT | COLLECTING | COLLECTING | Unchanged; stalled since Jun09 |
| SUM_POSTED_0.70–0.85 | COLLECTING | COLLECTING | n 1,379→2,019 (+640 per fire-event method) |

**No gate has transitioned to READY or REJECTED this run.**

---

## PROPOSED ACTIONS (human review)

No gate newly hit READY or REJECTED. No flag changes are warranted by gate rules.

The following items require human attention:

**A. Band net P&L has swung sharply negative since prior run (Jun17).** Prior report: net +$27.75 (exit099 +$383 + STWA_RESOLVED −$358 + MERGE +$3). This run: net **−$165.86** (exit099 +$458 + STWA_RESOLVED **−$627** + MERGE +$3). In 24h: +$75 from exit099 wins vs **−$269 from STWA_RESOLVED losses** (297 new resolved losers). Jun17 alone: −$118.84 from 82 resolved losing trades. Jun18 partial: −$24.71 from 17 more. The Jun17 acceleration coincides directly with the same-bucket pair-quoting + proportional queue deployment (12:12 UTC restart). Root cause not established — could be: (1) volume increase posting into worse bands, (2) proportional queue feeding more NO/PAIR legs that resolved wrong, or (3) market conditions. **Recommend: human inspect the Jun17 STWA_RESOLVED −$118 — what cities/buckets drove it? Was it the σ-gate removal letting in weak legs?**

**B. M1_BETA_LOCKOUT gate is stalled — strategy not firing.** 31 trades May27–Jun09, then zero for 9 days. metar_lockout.jsonl is empty. Either: (1) the oracle/METAR data has no lockout conditions, (2) WEATHER_M1_PROBE is being blocked upstream, or (3) the strategy was implicitly disabled. With CI straddles zero at n=31, the gate cannot progress until fires resume. **Recommend: human verify M1_PROBE arming status on VPS.**

**C. THERMO CI upper barely positive (+2%).** At n=3 this is noise, not a verdict (kill gate is n=20). But noting the signal: 2 losses at entry 0.81 and 0.98 (both large-stake NO legs, −$5.67 and −$5.39), 1 small win (+$0.11 at 0.98). The strategy is resolving ~0.5/day; 34 days to kill gate at this rate. No action warranted by rules, but human awareness appropriate given the negative early tilt.

**D. BASKET_EXIT n requires Gamma access before threshold can be assessed.** The metric (cash-out vs hold for all_green baskets) clearly favors holding (82–145% advantage), but this is based on `max_hold` field assuming all legs resolve YES. Gamma resolution flags are required to validate `all_green` = truth. The count of 48 deduped baskets is real; the ROI metric needs Gamma.

---

## System Notes

- **Gamma API 403** from this container blocks CI for gates 1, 2, 4, 7. VPS cron `band_resolution_join.py` was fixed Jun17 05:45. Human: check VPS `logs/weather/band_validator.log` to see if daily joins are now accumulating. CI unblocked there = READY/REJECTED possible next run.
- **Bankroll:** $243.50 (down from ~$246 prior; −$2.50 net today including capital corrections).
- **4 architecture changes deployed Jun17:** BAND_PAIR_SAMEBUCKET=True, BAND_MERGE_MIN_SHARES 5→3, σ-skill gate removed, BAND_PROPORTIONAL_QUEUE=True. Each changes the fire population going forward. Gate n counts are contaminated across the pre/post boundary.
- **Maker fills Jun16–18:** 282 total (270 YES @ avg $0.237, 11 NO @ avg $0.485). YES fill price distribution: 15% at <0.05 (very cheap), 23% at 0.10–0.19, 32% at 0.20–0.29, 22% at 0.30–0.39, 8% at ≥0.40. Skew toward low-price YES = expected for maker-NO strategy pairing.
- **Open positions:** 0 at snapshot time.
