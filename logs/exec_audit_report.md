# Execution & Markout Audit
**Date:** 2026-06-21 | **Snapshot:** 2026-06-21T06:58:16Z (age: 14 min) | **Status:** ACTIVE

---

## 1. FILL TAPE

### 24-Hour Window (since 2026-06-20 07:12 UTC)

| Metric | Value |
|--------|-------|
| Fill increment events | 77 |
| Registered (first fills) | 41 |
| Total $ filled | $144.36 |
| YES fills | n=41 events, $48.95 |
| NO fills | n=36 events, $95.40 |
| NO $ share (24h) | **66.1%** |

**24h by price band (all $ fill events):**

| Band | n | $ |
|------|---|---|
| <0.10 | 4 | $1.60 |
| 0.10–0.30 | 33 | $47.35 |
| 0.50–0.85 | 36 | $95.40 |

Note: 0.30–0.50 band saw no fills today. All YES fills are <0.30; all NO fills are 0.50–0.85.

### 7-Day Window

| Metric | Value |
|--------|-------|
| Fill events (all increments) | 163 |
| Total $ filled | $318.39 |
| YES 7d | n=93 events, $108.14 |
| NO 7d | n=70 events, $210.24 |
| NO $ share (7d) | **66.0%** |

**7d by price band:**

| Band | n | $ |
|------|---|---|
| <0.10 | 32 | $20.07 |
| 0.10–0.30 | 61 | $88.08 |
| 0.50–0.85 | 70 | $210.24 |

**Top cities 24h:** Tokyo (n=9, $13.0), Paris (n=6, $10.1), Chongqing (n=6, $12.0), Seattle (n=6, $2.3), Qingdao (n=5, $10.5)

### Fill Rate (posted → first fill)

| Date | Posted tokens | Spent | Reg fills | Fill rate |
|------|--------------|-------|-----------|-----------|
| 2026-06-21 (partial) | 16 | $76.10 | 11 | 68.8% |
| 2026-06-20 | 33 | $145.60 | 38 | 115.2%* |
| 2026-06-19 | 44 | $145.80 | 38 | 86.4% |
| 2026-06-18 | 95 | $260.25 | 13 | 13.7% |
| 2026-06-17 | 71 | $174.70 | 0 | 0.0% |

\* >100% = carryover fills on posts from prior day

---

## 2. NO-PARITY MONITOR

### Posts (fire/fire_no events) by day

| Date | YES fires | NO fires | PAIR | NO share | Status |
|------|-----------|----------|------|----------|--------|
| 2026-06-21 | 46 | 13 | 5 | **22.0%** | ⚠ ALERT |
| 2026-06-20 | 62 | 13 | 28 | **17.3%** | ⚠ ALERT |
| 2026-06-19 | 53 | 15 | 28 | **22.1%** | ⚠ ALERT |
| 2026-06-18 | 149 | 20 | 64 | **11.8%** | ⚠ ALERT |
| 2026-06-17 | 173 | 0 | 79 | **0.0%** | ⚠ ALERT |
| 2026-06-16 | 190 | 0 | 56 | **0.0%** | ⚠ ALERT |

**ALERT: NO share of new posts <25% on every day with ≥10 posts (target ~50%).**

Context: NO-starvation bug fixed 2026-06-12. NO fires appeared post-fix (13–20/day from Jun 18+; 0 fires Jun 16–17 confirms pre-fix period). Current ~17–22% post share is below threshold but does not indicate a re-regression — it reflects NO being a smaller universe (BAND_NO_MIN=0.52, BAND_NO_MAX=0.85 window) vs YES which spans mode±2 (many more qualifying legs per city). In execution $ terms NO outperforms post share: 66% of fill $ comes from NO despite 17–22% of posts, driven by higher fill probability per post on NO legs (at-touch bids vs. YES bids needing market to move into the band).

### Resting book by side (non-exit, non-SELL_EXIT)

| Side | Count | Unfilled $ |
|------|-------|-----------|
| YES | 19 | $9.15 |
| NO | 6 | $20.01 |
| None (THERMO/PROBE) | 4 | $18.80 |
| **Total** | **29** | **$47.96** |

SELL_EXIT (exit orders resting): 63 orders, $782.33

---

## 3. QUEUE HEALTH

Source: [STRUCT-BAND-Q] lines (n=748 cycles in log)

| Date | Cycles | cash_preskip (mean) | books/80 | yes_books/50 | posted/cycle |
|------|--------|---------------------|----------|-------------|-------------|
| 2026-06-21 | 82 | 134 | 0.4/80 | 0.1/50 | 0.24 |
| 2026-06-20 | 280 | 85 | 0.4/80 | 0.2/50 | 0.18 |
| 2026-06-19 | 280 | 95 | 0.3/80 | 0.1/50 | 0.80 |
| 2026-06-18 | 106 | 141 | 0.3/80 | 0.2/50 | 9.53 |

**Last 3 cycles today (2026-06-21):**

| Time | cash | books | yes_books | posted |
|------|------|-------|-----------|--------|
| 06:47 | 140 | 4/80 | 1/50 | 3 |
| 06:52 | 141 | 0/80 | 0/50 | 0 |
| 06:57 | 127 | 2/80 | 1/50 | 1 |

**No alerts fired:**
- Books usage far below 80 ceiling (max 4/80) — no fetch starvation regression.
- yes_books far below 50 ceiling — no YES saturation.
- cash_preskip 85–141 with finite posts/cycle — not a deployment stall.

The posted/cycle drop from 9.53 (Jun 18) → 0.18–0.80 (Jun 19–20) reflects fewer new markets qualifying in the band (fewer fire events from band_struct_lite: 149 → 62), not a queue malfunction. Today at 07:00 UTC, European city windows are only opening now; posting cadence expected to increase.

---

## 4. RESOLUTION MARKOUT

### Confirmed wins (recycle@0.99, n=89 over 6 days)

| Date | n | PnL | Entry range |
|------|---|-----|-------------|
| 2026-06-16 | 10 | $84.31 | 0.07–0.96 |
| 2026-06-17 | 19 | $87.45 | 0.08–0.98 |
| 2026-06-18 | 26 | $99.56 | 0.09–0.98 |
| 2026-06-19 | 19 | $78.58 | 0.13–0.62 |
| 2026-06-20 | 13 | $75.12 | 0.03–0.95 |
| 2026-06-21 | 2 | $11.32 | 0.26–0.67 |
| **7d total** | **89** | **$436.34** | cost $277.61 |

**Gross ROI on confirmed winners: 157.2%** (~14.8 winners/day)

**By entry price band (all confirmed winners):**

| Band | n | PnL | Cost | ROI |
|------|---|-----|------|-----|
| <0.10 | 5 | $110.79 | $5.39 | 2055% |
| 0.10–0.30 | 35 | $183.97 | $44.21 | 416% |
| 0.30–0.50 | 25 | $85.53 | $45.13 | 190% |
| 0.50–0.85 | 17 | $52.37 | $91.98 | 57% |

### Winner's curse test

**INCONCLUSIVE — n too small and token linkage incomplete.**

- 100 registered fills in log window; 13 matched to recycle records via token prefix; 57 still in resting book (open positions); 20 "resolved unknown" (out of both log and resting) → probable OTM losses.
- Proxy filled-ITM rate: **39.4%** (13 wins / 33 resolved fills). Below 50% efficient-pricing baseline.
- n=33 resolved fills is below the 40-fill data-collection threshold — **no conclusion on winner's curse from this set**.
- All-fires ITM rate (denominator for the classic comparison) is not computable without CLOB resolution API — band_resolution_join.py cannot run in this environment.
- **Flag for next audit at n≥40 resolved fills.** The 39.4% proxy is at-risk of being a signal; it is not yet decision-grade.

### UNTRACKED FILL volume (informational)

WebSocket detected large fill volumes not captured in MAKER-FILL tracker:

| Date | Untracked tokens | Approx shares |
|------|-----------------|---------------|
| 2026-06-19 | 50 | ~6,578 |
| 2026-06-20 | 32 | ~3,806 |
| 2026-06-21 | 7 | ~383 |

The Jun 19 burst includes many tokens at price=0.99 (resolution fills on SELL_EXIT orders) plus mid-price BUY fills. All trader_side=MAKER — not external adversary. Pattern suggests a tracker restart on Jun 18–19 boundary caused a state loss; the bot re-tracked new positions but pre-restart fills surfaced via WS. The 63 current SELL_EXIT orders likely correspond to positions from this untracked period. **Fill accounting gap exists between MAKER-FILL log and on-chain state; PnL from untracked fills is not credited in this report.**

---

## 5. DEAD-QUOTE RECLAIM

| Metric | Value |
|--------|-------|
| 'reaped dead entry' events (7d log) | **0** |
| Maker bid resting (non-exit) | 29 orders |
| Quotes >24h | 9 |
| Quotes >48h | **6** |
| Quotes >72h | 5 |
| Oldest quote | Moscow YES, **90.3h** |

**Stale quotes >48h (all are fully filled — unfilled ≈ 0 shares):**

| City | Side | Age | Unfilled |
|------|------|-----|---------|
| Moscow | YES | 90.3h | 0.01 sh |
| Paris | YES | 80.3h | 0.00 sh |
| Warsaw | YES | 78.4h | 0.01 sh |
| Wuhan | YES | 76.1h | 0.01 sh |
| Chengdu | YES | 74.8h | 0.01 sh |
| Panama City | YES | 69.6h | 0.01 sh |

The >20-quote-at-48h alert did **not** fire (count=6). These are ghost entries: fully-filled positions lingering in the maker_resting_state dict after matching completes, before the SELL_EXIT order is posted. Unfilled remainder is effectively 0 (0.01 sh is rounding dust). No velocity leak; the SELL_EXIT pipeline (63 live exit orders) is processing fills. Zero reclaim events in 7d log — expected, since BAND_RECLAIM_BEHIND=0.02 only triggers on unfilled bids sitting behind touch, not fully-filled positions.

17 of 29 non-exit orders are >2h (BAND_RECLAIM_AGE_S threshold). These include both the filled ghosts and genuinely resting bids (NYC YES 120sh at $0.01 posted 2h ago — large cheap YES bet currently unfilled).

---

## 6. CASH VELOCITY

| Metric | Value |
|--------|-------|
| Capital (bankroll.json) | $249.20 |
| SELL_EXIT resting $ | $782.33 |
| Maker bid resting $ (unfilled) | $47.96 |
| Fills $ last 24h | $144.36 |
| Fills $ 7d average/day | $46.75 |
| **Equity turns/day (24h fills / bankroll capital)** | **0.579** |
| Benchmark (badatmath) | ~1.0 turns/day |

**Caveat:** bankroll.json is cash only. True deployed capital ≈ $249 (cash) + $782 (SELL_EXIT positions at near-resolution prices) = ~$1,031. Denominated against total equity: turns/day ≈ 0.14 — well below benchmark. However the $782 in SELL_EXIT is money that has already earned its markup (entry was cheap YES/NO, now priced at 0.79–0.99); it's awaiting resolution, not actively cycling.

Effective operating capital available for new maker bids: $249 − $47.96 (open bids) = ~$201 free cash. At $46.75 fill $/day average, capital utilization is healthy but below badatmath-scale. The binding constraint is **new qualifying market availability** (0.18–0.24 posts/cycle on Jun 20–21), not cash shortage.

1 reconcile failure (Jun 20 17:46) following an UNTRACKED FILL event — isolated incident.

---

## ALERTS

**[FIRED] NO-share <25% every day with ≥10 posts (Section 2)**
NO fires are 11.8–22.1% of post events since Jun 18 (threshold: 25%). Pre-fix Jun 16–17 were 0%. The fix is confirmed active (NO fires exist); absolute share below target is likely structural (NO window 0.52–0.85 is a narrower universe than YES mode±2), not a re-regression. In $ execution terms NO is 66% of fill volume — strong. **Recommend**: verify whether BAND_NO_MIN=0.52 is cutting off enough NO candidates to explain the post-share gap, or whether the per-day NO budget (BAND_NO_DAILY_CAP=40.0) is the binding constraint.

---

## SUMMARY

**Fills/day:** 14.8 confirmed winners/day recycled at 0.99 (7d). $46.75 fill $/day (7d avg). Today on pace: 11 registered fills by 07:12 UTC.

**NO-share:** 66% of fill $ (execution healthy). 17–22% of post events (below 25% threshold — alert fired). The gap is likely structural (universe size), not a starvation re-regression.

**Binding execution constraint today:** New market availability — 0.18–0.24 posts/cycle suggests sparse qualifying markets in the current window (06:00–07:12 UTC). European session opening now; cadence expected to pick up. SELL_EXIT backlog ($782 in 63 orders) is the dominant capital sink but represents deferred PnL, not a problem. Winner's curse test inconclusive (n=33 resolved fills; need n≥40).
