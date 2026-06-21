# Gate-Keeper Report — 2026-06-21

**Snapshot**: 2026-06-21T08:59:16Z (< 6h old ✓) | **System**: active ✓ | **Bankroll**: $283.52

---

## Gate Ledger

| Gate | n | +since prior | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| 1. BAND_YES | 5,154 | +240 | — | — | [Gamma 403] | COLLECTING | n>>100; CI blocked |
| 2. BAND_NO_PAIR_FAV | 128 | +23 | — | — | [Gamma 403] | COLLECTING ★n≥100 | CI blocked; VPS join needed |
| 3. FILLED_VS_FIRED | 108† | +8 | — | — | [CID join blocked] | COLLECTING | n>>40; join blocked |
| 4. BASKET_EXIT | ≈72‡ | +8 conf. | 100% | +22.7% | [+11.5%, +34.0%] n=16 | COLLECTING | ≈3.5d |
| 5. THERMO_MAKER_NO | 3 | +0 | 33.3% | −66.0% | [−132.6%, +0.7%] | COLLECTING | **STALLED** (0 fills Jun12–Jun21) |
| 6. M1_BETA_LOCKOUT | 31§ | +0 | 74.2% | −0.6% | [−20.6%, +24.4%]§ | COLLECTING | **STALLED** (0 thin-margin fires) |
| 7. SUM_POSTED_0.70_0.85 | 2,473 | +142 | — | — | [Gamma 403] | COLLECTING | n>>100; CI blocked |

†Gate 3: 7d rolling window, 108 registered fills (Jun18=13, Jun19=38, Jun20=38, Jun21=19). YES=60 (55.6%), NO=48 (44.4%). NO fill rate improved to 44% from 29% at prior run — favNO TOP priority (Jun19T00:30) effect visible.

‡Gate 4: 8 confirmed closed all_green baskets from Jun20 post-prior-run; prior 64 was unverified estimate. Best combined: ≈72. CI95 computed on verified n=16 confirmed subset only (lower bound +11.5% > 0). Per-day archive gap Jun16–19 persists.

§Gate 6: n=31 carries provenance flag — basis unverifiable from container. Only 1 confirmed M1 trade in trades.jsonl. CI95 from prior state, reproduced verbatim. Stalled day 11.

**No READY. No REJECTED. No status transitions from prior run.**

---

## Gate Detail

### Gate 1: BAND_YES per-slice legs

- **Data source**: band_struct_lite.jsonl (6-day window Jun16–Jun21), first-fire dedup per (cid, days_out)
- **Counts by day**: Jun16=800, Jun17=679, Jun18=629, Jun19=230, Jun20=260, Jun21=206 (09:20 UTC)
- **Cumulative n**: Prior 4,914 (Jun20T12:27) + Jun20 remainder ~34 + Jun21 206 = **≈5,154**
- **By days_out (6-day window)**: d+0=555, d+1=690, d+2=1056
- **Sum_posted [0.70,0.85] fraction**: 44% Jun16, 47% Jun17, 45% Jun18, 64% Jun19, 66% Jun20, 61% Jun21 (rising after Jun18 config changes)
- **Rate**: ~230 legs/day
- **Resolution**: Gamma API returns 403 from container. band_resolution_join.py requires CLOB winner flags. VPS must execute. Clean-window boundary = Jun19T00:30 UTC (post-config-freeze); post-boundary legs ≈701 (clean, no contamination from Jun18 churn).
- **Note**: Significant config churn Jun16–18 (6+ commits per state_log 11:30–22:30 Jun18) may contaminate pre-Jun19 data for ROI purposes. Per-slice threshold (days_out × offset × price_band) may not be met on individual slices despite aggregate n>>100.

### Gate 2: BAND_NO + PAIR_FAV legs

- **Data source**: band_struct_lite.jsonl, reason ∈ {fire_no, pair_fav, pair_samebucket}, dedup per (cid, days_out)
- **Counts by day**: Jun16=11, Jun17=10, Jun18=22, Jun19=15, Jun20=13, Jun21=17
- **Cumulative n**: Prior 105 (Jun20T12:27, threshold crossed) + Jun20 remaining ~6 + Jun21 17 = **≈128**
- **Breakdown (6-day window)**: fire_no=65, pair_fav=17, pair_samebucket=6 = 88; plus ~40 legacy Jun12–15
- **Rate**: ~14–15 NO-side fires/day
- **Resolution**: Blocked (Gamma 403). n≥100 crossed at prior run — threshold has been cleared for over 24h. CI cannot be computed from this container. VPS resolution join is **urgently needed**: BAND_NO_ENABLED=True, BAND_NO_STAKE=$5 currently LIVE. Cannot affirm or kill without resolution truth.
- **Note**: NO fill rate in maker_fills_recent.log now 44% of 108 registered fills — up from 29% at prior run. This is fill-rate signal only, not an outcome indicator.

### Gate 3: Filled-vs-Fired Divergence

- **Data source**: maker_fills_recent.log (7d rolling)
- **Current window**: 108 registered fills (Jun18=13, Jun19=38, Jun20=38, Jun21=19 to 09:20 UTC)
- **Delta since prior**: +8 (prior n=100 at Jun20T09:01)
- **Side split**: YES=60 (55.6%), NO=48 (44.4%)
- **Prior fill split**: YES=71%, NO=29% → substantial improvement in NO fill rate after favNO TOP priority
- **Markout context** (state_log Jun18 23:30–23:59): YES fills adversely selected at −0.05¢/sh vs badatmath's +1.19¢/sh. Root cause: stale orders (>6h old) run over by informed drift, NOT queue position. 2h directional reclaim is PROTECTIVE. Gap is structural (paired/merge-hedged book at ~$2k phase).
- **CID join**: Blocked from container. VPS must execute filled-vs-fired comparison per slice to test winner's-curse hypothesis before Jun18 fills age out (~4 days).

### Gate 4: Basket Exit (cash-green baskets)

- **Data source**: basket_exit_shadow.jsonl (Jun20 archive = 14,513 rows; Jun21 today = 4,732 rows)
- **Unique baskets tracked**: 59 total (52 from Jun20 archive + 7 net new today)
- **All_green=True closed**: **16 confirmed** (8 from Jun20 closed before prior run; 8 new since prior run)
  - Jun20 closures post-prior (t_close after Jun20T12:27): beijing (+509%), hong-kong (+68%), moscow (+5%), warsaw (+48%), amsterdam (+52%), paris (+6%), london (+42%), denver (+3087%)
- **Today (Jun21)**: 10 all_green baskets identified, all t_close ≥ 15:00 UTC today → still pending
- **ROI on n=16 confirmed closed**: WR=100%, mean ROI=+22.7%, median ≈+18–22%
- **CI95 (t-test, t(0.025,15)=2.131)**: **[+11.5%, +34.0%]** — lower bound above zero
- **Prior estimate**: 64 (unverified, Jun15–19 archive absent). Best combined: ≈72.
- **Threshold**: n=100. **COLLECTING** at n≈72. At 8 confirmed/day ≈ 3.5 days to threshold IF Jun21+ archives created consistently on VPS.
- **Anti-sycophancy**: n=16 CI is on the confirmed subset only. Prior's 56 (Jun15–19 estimated) are unverified and may include adverse outcomes not archived. Do not declare READY at n=72. Hold for n=100 verified.

### Gate 5: THERMO Maker-NO (upper-tail, pre-kill gate)

- **Data source**: thermo_maker.jsonl (shadow candidates only), trades.jsonl (STWA_RESOLVED)
- **Status**: **STALLED 9+ days** — no new fills since Jun12T22:53 UTC
- **n=3 resolved** (gate registration: Jun11T22:40 UTC):
  - +$0.11 @ $0.98 (Jun12T00:00, 5.5sh) → stake=$5.39, ROI=+2.04%
  - −$5.67 @ $0.81 (Jun12T00:15, 7.0sh) → stake=$5.67, ROI=−100.0%
  - −$5.39 @ $0.98 (Jun12T22:53, 5.5sh) → stake=$5.39, ROI=−100.0%
- **WR**: 1/3=33.3% | **Mean ROI**: −66.0% | **CI95 (z-approx)**: [−132.6%, +0.7%]
- **CI upper**: +0.7% — barely straddles zero. One additional adverse fill at n≥20 pushes CI fully negative → REJECTED territory.
- **Current pipeline**: thermo_maker.jsonl has 25,818 candidate rows (8,890 today) but record_type=thermo_maker_candidate ONLY — zero fire records. maker_fills_recent.log: max NO fill = $0.79, nothing above BAND_NO_MAX=0.85. Engine scanning but NOT firing.
- **Paris NO claim cleared**: Prior state flagged "Paris NO +5.5sh@0.98" as possible thermo n=4. This was a [USER-WS] UNTRACKED FILL for a TAKER SELL by another participant, NOT a maker-NO entry by Klaus — correctly excluded.
- **Kill gate**: 20 resolved required. At 0 fires/day: ETA=INFINITE.

### Gate 6: M1 Beta Lockout (thin-margin [0.2,0.5)°C slice)

- **Data source**: metar_min_lockout.jsonl (candidates), trades.jsonl (WEATHER_M1_PROBE)
- **Status**: **STALLED 11+ days**
- **n=31** (provenance flag: unverifiable from container)
- **Current data**: metar_min_lockout.jsonl = 16,611 candidate rows (all metar_min_lockout_candidate), zero fires. metar_lockout.jsonl = 0 lines in all per-day archives (Jun16–Jun21).
- **Only verified trade**: Moscow May-26 WEATHER/BUY_NO (net_pnl=−$1.65). n=1 verifiable.
- **WR**: 74.2% (prior, unverified) | **ROI**: −0.6% (prior) | **CI95**: [−20.6%, +24.4%] (prior, maintained)
- **Standing rule** (Jun09): once n≥100, WR≥95% AND +EV = keep thin-margin slice; else REVERT to 0.5°C floors.
- **ETA**: INFINITE. No thin-margin [0.2,0.5)°C fires in 11+ days.

### Gate 7: SUM_POSTED [0.70,0.85] slice

- **Data source**: band_struct_lite.jsonl fire events where sum_posted ∈ [0.70,0.85], dedup per (cid, days_out)
- **Counts by day**: Jun16=348/800 (44%), Jun17=316/679 (47%), Jun18=282/629 (45%), Jun19=147/230 (64%), Jun20=172/260 (66%), Jun21=126/206 (61%)
- **Cumulative n**: Prior 2,331 (Jun20T12:27) + Jun20 remaining ~16 + Jun21 126 = **≈2,473**
- **Rate**: ~140/day (fraction rising Jun19–20: 64–66% after PX_CEIL 0.30 + strict-rank queue)
- **Context**: V3 gate extension was based on n=46 TREND. Gate exceeds 100 aggregate but CI blocked (no Gamma resolution). Same resolution join as Gate 1; same clean-window boundary (Jun19T00:30) applies.

---

## State Transitions vs Prior Run (2026-06-20T12:27:00Z)

| Gate | Prior Status | Current Status | Change |
|---|---|---|---|
| 1. BAND_YES | COLLECTING | COLLECTING | n: 4,914 → 5,154 (+240) |
| 2. BAND_NO_PAIR_FAV | COLLECTING ★n≥100 | COLLECTING ★n≥100 | n: 105 → 128 (+23) |
| 3. FILLED_VS_FIRED | COLLECTING | COLLECTING | n: 100 → 108 (+8); NO% 29→44% |
| 4. BASKET_EXIT | COLLECTING | COLLECTING | +8 confirmed new; **CI [+11.5%,+34%] on n=16** |
| 5. THERMO_MAKER_NO | COLLECTING STALLED | COLLECTING STALLED | n=3 unchanged (day 9+) |
| 6. M1_BETA_LOCKOUT | COLLECTING STALLED | COLLECTING STALLED | n=31 unchanged (day 11+) |
| 7. SUM_POSTED_0.70_0.85 | COLLECTING | COLLECTING | n: 2,331 → 2,473 (+142) |

**No gate reached READY or REJECTED.**

---

## PROPOSED ACTIONS (human review)

No gates newly hit READY or REJECTED this run. No flag or parameter changes are proposed. All COLLECTING.

### Informational flags for human attention:

**[ACTION NEEDED — VPS, P1] Gate 2 resolution join is overdue.**
Gate 2 (BAND_NO_PAIR_FAV) crossed n=100 at the prior run (Jun20). BAND_NO_ENABLED=True with BAND_NO_STAKE=$5 is LIVE. Gate 2 is the critical validation gate for the NO-side engine: the CI determines READY (scale), AMBIGUOUS (continue), or REJECTED (disable BAND_NO_ENABLED). Cannot be evaluated from this container. VPS operator: run band_resolution_join.py against fire_no/pair_fav/pair_samebucket legs in the post-clean-window window (Jun19T00:30 UTC onward). Every additional day at n=128 dilutes the clean window with un-resolvable legs from this container.

**[ACTION NEEDED — VPS, P2] Gates 1 and 7 resolution join.**
Both have been n>>100 for days. VPS: copy each day's band_struct_lite.jsonl to logs/shadow/hot/$D/band_struct.jsonl (lite format preserves first-fire dedup), then run band_resolution_join.py on post-Jun19T00:30 data only. Per-slice breakdown (days_out × offset × price_band) needed — individual slices at n=100+ may show divergent CIs.

**[WATCH — Gate 4] First confirmed positive CI signal.**
n=16 confirmed closed all_green baskets now show CI95=[+11.5%, +34.0%] with lower bound above zero. This is the first gate with a directionally positive CI from verified data. Not a decision (n=100 required), but a positive accumulating signal. Verify VPS is writing data/shadow/<date>/basket_exit_shadow.jsonl daily — Jun16–19 gap suggests archival cron was not running. At current 8/day confirmed rate, gate reaches n=100 in ≈3.5 days IF archive resumes.

**[WATCH — Gate 5] THERMO stall entering 10th day.**
At n=3 and CI barely straddling zero (upper=+0.7%), the thermo gate is effectively negative. The stall duration (9+ days, 25,818 candidates with zero fires) suggests the firing path may be disabled or gated by a condition no longer met in current weather regime. Recommend VPS operator inspect: whether the capped $15/day thermo budget is exhausted, or whether the no_ask floor is suppressing all current candidates.

---

*Generated: 2026-06-21T09:20 UTC | Data mirror: 2026-06-21T08:59:16Z | Container: Gamma 403 (resolution blocked)*
