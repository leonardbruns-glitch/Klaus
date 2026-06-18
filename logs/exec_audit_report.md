# Execution & Markout Audit — 2026-06-18

**Snapshot:** 2026-06-18T10:32:06Z (age: 16 min at audit time) | **System:** active  
**Capital:** $243.50 | **Data window:** 2026-06-16 to 2026-06-18T10:28 UTC  
**Total fill records (7d tape):** 284 fills across 210 unique tokens

---

## Section 1 — Fill Tape

### 24h Summary (2026-06-17 10:49 UTC → 2026-06-18 10:49 UTC)

| Metric | Value |
|---|---|
| Total fills | 164 (YES=160, NO=4) |
| $ filled YES | $158.13 |
| $ filled NO | $15.89 |
| $ filled total | $174.02 |
| NO share | **2.4%** |

### Daily Breakdown

| Date | Fills | YES | NO | NO% | $ Total |
|---|---|---|---|---|---|
| 2026-06-16 | 77 | 72 | 5 | 6.5% | $93.54 |
| 2026-06-17 | 126 | 120 | 6 | 4.8% | $154.40 |
| 2026-06-18 (to 10:28) | 81 | 81 | 0 | 0.0% | $73.09 |

### By Price Band (24h fills)

| Band | Fills | YES | NO | $ |
|---|---|---|---|---|
| <0.10 | 20 | 20 | 0 | $10.24 |
| 0.10–0.30 | 94 | 94 | 0 | $85.50 |
| 0.30–0.50 | 44 | 44 | 0 | $54.99 |
| 0.50–0.85 | 6 | 2 | 4 | $23.30 |

All NO fills land in the 0.50–0.85 band. YES fills dominate the 0.10–0.30 band (57% of volume by count).

### Time-to-First-Fill (n=202 tokens, 3-day window)

Cross-referenced band_struct_lite post timestamps vs first fill timestamp per token (12-digit token prefix match):

| Percentile | TTF |
|---|---|
| Min | 0.2 min |
| P25 | 38.9 min |
| Median | 116 min |
| P75 | 282 min |
| Max | 2,115 min (35h) |
| Mean | 248 min |

Median TTF of ~2h is consistent with passive maker quoting at a 5–12¢ discount to ask. Long tail (35h) suggests some bids are stale or behind the book. Fill rate per day: 64.4% (Jun 16), 79.0% (Jun 17), 57.6% (Jun 18 partial).

### Top Cities by Fill Count (24h)

Taipei 11, Helsinki 8, Istanbul 7, Shenzhen 7, Chongqing 7, Guangzhou 7, Mexico City 7, London 6, Shanghai 6, Beijing 6, Wuhan 6.

---

## Section 2 — NO-Parity Monitor

**Target: ~50% NO share (badatmath parity). Alert threshold: NO% < 25% on any day with ≥10 posts.**

### New Posts by Side (band_struct_lite)

| Date | YES Posts | NO Posts | NO% | Alert |
|---|---|---|---|---|
| 2026-06-16 | 109 | 12 | **9.9%** | ALERT: NO<25% |
| 2026-06-17 | 169 | 10 | **5.6%** | ALERT: NO<25% |
| 2026-06-18 (to 10:28) | 93 | 0 | **0.0%** | ALERT: NO<25% |

**Three consecutive days below the 25% threshold.** All three days have ≥10 posts.

### Resting Book (maker_resting_state.json)

| Category | Orders | Resting $ |
|---|---|---|
| YES (open bids) | 35 | $29.18 |
| NO (open bids) | 0 | $0.00 |
| SELL_EXIT (0.99 exits) | 146 | — |

NO share of active bids: **0.0%**

### Root-Cause Signal

The no-starvation fix (commit 2026-06-12 `fix(BAND): NO-starvation`) produced some NO posts (9.9% on Jun 16, 5.6% on Jun 17) but the fix is degrading: Jun 18 shows 0 NO posts through 10:28 UTC.

Of 55 pair_shadow records today:
- **no_fillable=False: 51** (92.7%) — bot determines NO quote too far behind book
- **no_fillable=True: 4** (7.3%) — appeared in shadow log before 10:28 UTC but produced 0 actual NO posts

Typical unfillable case: `yes_q=0.26, no_bid=0.73, no_ask=0.74, no_quote=0.66` — bot prices NO 7–14¢ below bid. Fillable cases occur only when `no_quote == no_bid` (wide-spread markets with pair_sum ≤ 0.89).

The standalone NO overlay (`BAND_NO_ENABLED=True`, `BAND_NO_MIN=0.52`) generated 12/10 posts on Jun 16/17 but 0 today despite 76 NO-related shadow records. This is the primary starvation channel failing.

Note: `no_cands=132–148` every cycle confirms NO candidate pool is full — the block is in the posting logic, not candidate discovery.

---

## Section 3 — Queue Health

Source: 549 `[STRUCT-BAND-Q]` lines.

### Per-Day Summary

| Date | Cycles | cash_preskip | books/80 | yes_bks/50 | posted/c | no_cands | Alert |
|---|---|---|---|---|---|---|---|
| 2026-06-16 | 147 | 217 | 1.0 | 0.4 | 0.53 | 133 | ok |
| 2026-06-17 | 281 | 130 | 1.3 | 0.6 | 2.66 | 112 | ok |
| 2026-06-18 | 121 | 119 | 1.5 | 0.8 | 0.77 | 148 | ok |

### 24h Queue (275 cycles)

- avg cash_preskip: **$117** — no deployment stall
- avg books used: **1.6/80** — far from fetch starvation
- avg yes_books: **0.8/50** — well below pin
- avg posted/cycle: **1.89** (Jun 17 was 2.66; Jun 18 has dropped to 0.77 today)
- max yes_resv_skip: **157** — YES reserve skipping is the active in-cycle gate

No books-pinned or yes_books-pinned alerts. No deployment stall (cash_preskip < 200 with posted > 0). **No queue health alerts triggered.**

---

## Section 4 — Resolution Markout (Fill Quality)

**n=23 resolved fills** (cross-referenced maker_fills_recent.log short tokens vs exit099_live.jsonl via 12-digit prefix). **Below n=40 threshold — trend only, no conclusions.**

### Resolved Fill ROI

| Slice | n | Avg ROI | Median ROI | Win Rate |
|---|---|---|---|---|
| YES resolved | 21 | +295% | +230% | 100% |
| NO resolved | 2 | +1% | +2% | 50% |
| ALL resolved | 23 | +269% | +230% | 95.7% |

### By Price Band (resolved fills)

| Band | n | Avg ROI | Win Rate |
|---|---|---|---|
| 0.10–0.30 | 10 | +440% | 100% |
| 0.30–0.50 | 9 | +181% | 100% |
| 0.50–0.85 | 4 | +41% | 75% |

All resolutions appear via `record=recycle099` (sold at 0.99 = resolution winner). ROI is consistent with buying YES at 0.10–0.45 and resolving to 1.0 (e.g., entry 0.23 → exit 0.99 = +330%).

**Winner's curse verdict:** No adverse selection detected at n=23. Filled-leg median ROI (+230%) is directionally positive. Full test (filled-leg ROI vs all-fires simulated ROI) requires `band_resolution_join.py` + CLOB API resolution lookup — not available from this environment. Revisit at n≥40.

All-fires shadow ask distribution (n=2,026 legs, Jun 16–18): median=0.210, P75=0.300. The observed entry price distribution of filled legs is consistent — no systematic adverse selection signal at this sample size.

---

## Section 5 — Dead-Quote Reclaim

- **Reaped dead entry lines in tape:** 0
- **Reclaim-related log lines:** 0

`BAND_RECLAIM_AGE_S=2h`, `BAND_RECLAIM_PER_CYCLE=10` configured, but no reclaim events appear in the 7d log. Reclaim may be silent on no-action cycles or log at a different level.

### YES Resting Order Ages

| Threshold | Count |
|---|---|
| >2h (RECLAIM_AGE_S) | 24 of 35 |
| >24h | 2 of 35 |
| >48h | 1 of 35 |

**Oldest resting quote:** Moscow YES @ $0.20, age **52.2h** (posted ~2026-06-16 06:00 UTC).

Alert threshold (>20 quotes older than 48h): **NOT triggered** (only 1 quote >48h).

The Moscow $0.20 bid resting 52h is a marginal velocity leak. With `BAND_RECLAIM_BEHIND=0.02`, it may still be within 2¢ of touch and therefore not flagged for reclaim.

---

## Section 6 — Cash Velocity

| Metric | Value |
|---|---|
| Capital | $243.50 |
| YES resting bids | $29.18 (35 orders) |
| NO resting bids | $0.00 (0 orders) |
| SELL_EXIT positions | 958 shares, 146 orders |
| 24h fills $ | $174.02 |
| 7d tape fills $ | $321.03 (2.5-day window) |
| **Turns/day** | **0.715** |
| Benchmark (badatmath) | ~1.0 |

Cash velocity at **0.715 turns/day** is 28.5% below benchmark. The structural cause is the NO-empty book: the strategy is running YES-only, so each posted dollar cycles in one direction rather than as a YES+NO pair. At parity, the same capital would support ~2× the active book depth.

Posted $ per day: Jun 17 $174.70, Jun 18 $111.85 (to 10:28 UTC, ~$270/day annualized pace if extrapolated — above current capital but consistent with high-turnover maker).

---

## ALERTS

| # | Alert | Severity | Detail |
|---|---|---|---|
| 1 | **NO-SHARE BELOW 25%** | HIGH | NO% = 9.9% (Jun 16), 5.6% (Jun 17), 0.0% (Jun 18). Three consecutive days breach alert threshold. Fix 2026-06-12 insufficient — NO degraded to 0 posts/0 fills today. |
| 2 | **NO RESTING BIDS = $0** | HIGH | Active resting book is 100% YES (35 orders/$29.18). Zero NO exposure. |

---

## 3-Line Summary

**Fills/day:** 77–126 fills/day (164 in 24h, $174 total); YES accounts for 97.6% of fills and 90.9% of $ filled; median time-to-fill 116 min; fill rate 64–79%.

**NO-share:** 0–9.9% across all three measured days; today at 0% posts and 0 fills through 10:28 UTC; resting book is 100% YES; 51/55 pair_shadow records fail the no_fillable gate (NO quote 7–14¢ behind book); fix from 2026-06-12 is not holding.

**Binding execution constraint:** NO starvation — the bot is running a pure YES book, suppressing cash velocity to 0.72 turns/day (vs 1.0 benchmark) and leaving the NO half of the paired-maker strategy undeployed for the third consecutive day.
