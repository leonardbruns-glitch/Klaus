# Execution Audit Report — 2026-06-17T07:11 UTC

**Snapshot age:** 11 min (fresh)  **System:** `klaus systemd: active` (restarted 06:45 UTC)  
**Data window:** 7-day fill tape (2026-06-14 → 2026-06-17T07:11)  
**CLOB API:** 403 Forbidden from this environment — resolution outcomes sourced from `trades.jsonl` (STWA_RESOLVED records) instead.

---

## 1. FILL TAPE

### 24-Hour Window (2026-06-16T07:11 → 2026-06-17T07:11)

| Metric | Value |
|---|---|
| Registered fills | **65** initial + 77 increment events |
| YES fills | 62 (95.4%) — $84.82 |
| NO fills | 3 (4.6%) — $2.65 |
| Total fill $ | **$87.47** |

**Price-band breakdown (24h):**

| Band | Count | $ | Notes |
|---|---|---|---|
| < 0.10 | 6 | $2.57 | Deep wing YES, near-zero EV |
| 0.10–0.30 | 38 | $39.88 | Core YES band, 58% of fills |
| 0.30–0.50 | 16 | $27.08 | Shoulder YES |
| 0.50–0.85 | 5 | $17.94 | NO overlay (0.52–0.85 per config) |

**Top cities by fill count (24h):** Beijing 5, Taipei 4, Tokyo 4, Qingdao 4, Chengdu 4, Chicago 3, Busan 3, Chongqing 3, Seoul 3, Wuhan 3.

### 7-Day Fill Summary

| Date | Total | YES | NO | NO% | $ |
|---|---|---|---|---|---|
| 2026-06-14 | 13 | 11 | 2 | 15.4% | $27.27 |
| 2026-06-15 | 69 | 66 | 3 | 4.3% | $84.58 |
| 2026-06-16 | 62 | 59 | 3 | 4.8% | $83.31 |
| 2026-06-17 (partial, 07h) | 17 | 17 | 0 | 0.0% | $21.02 |
| **7-day total** | **161** | **153** | **8** | **5.0%** | **$216.18** |

**Median time-to-fill:** 4,123 s (~69 min) from post to first registered fill (159 matched pairs). p90 = 356 min.  
YES median TTF = 69 min; NO median TTF = 104 min.

**Fill rate from `band_posted_state.json`:**

| Date | Posted | Filled | Fill Rate | $ Deployed |
|---|---|---|---|---|
| 2026-06-14 | 49 | 17 | 35% | $254.07 |
| 2026-06-15 | 81 | 71 | 88% | $257.34 |
| 2026-06-16 | 74 | 64 | 86% | $187.36 |
| 2026-06-17 (partial) | 21 | 9 | 43% | $38.12 |

Fill rate of 86–88% on Jun 15–16 is high and consistent. Today's 43% reflects partial day (7h elapsed).

### UNTRACKED Fills (WS-registered, not in bot tracker)
342 UNTRACKED FILL lines across 4 days (49 MINED events in last 24h, $3,397 notional). All are high-price BUYs ($0.50–$0.87), inconsistent with the YES band strategy — these appear to be **user's manual/external positions**. Not included in fill metrics above.

---

## 2. NO-PARITY MONITOR

### New Posts by Side per Day (from `band_struct_lite` `record=post`)

| Date | Total Posts | YES | NO | NO% | Status |
|---|---|---|---|---|---|
| 2026-06-12 | 85 | 82 | 3 | 3.5% | **ALERT** |
| 2026-06-13 | 59 | 43 | 16 | 27.1% | ok |
| 2026-06-14 | 87 | 67 | 20 | 23.0% | **ALERT** |
| 2026-06-15 | 182 | 178 | 4 | 2.2% | **ALERT** |
| 2026-06-16 | 121 | 109 | 12 | 9.9% | **ALERT** |
| 2026-06-17 (partial) | 27 | 26 | 1 | 3.7% | **ALERT** |

The 2026-06-12 fix commit ("fix(BAND): NO-starvation") has **not resolved the structural imbalance**. 5 of 6 days show NO% < 25%. The one passing day (Jun 13, 27.1%) immediately reverted. Resting book NOW: 38 YES / 5 NO = **11.6% NO**. `BAND_NO_ENABLED=True`, `BAND_NO_STAKE=4.5`, `BAND_NO_DAILY_CAP=40.0` are all configured; the failure is in market selection or gate logic, not config.

---

## 3. QUEUE HEALTH

### Per-Day Cycle Statistics

| Date | Cycles | avg_cash_preskip | avg_books/80 | avg_yes_books/50 | avg_posted/cy |
|---|---|---|---|---|---|
| 2026-06-14 | 55 | 10 | 0.3 | 0.3 | 0.25 |
| 2026-06-15 | 280 | 233 | 1.2 | 0.6 | 1.82 |
| 2026-06-16 | 279 | 235 | 0.8 | 0.4 | 1.29 |
| 2026-06-17 | 82 | 137 | 0.7 | 0.3 | 0.33 |

**No fetch starvation:** books never approach 80-pin or 50-pin. CLOB fetch pool healthy.

**cash_preskip 230+ on Jun 15–16:** Large capital is skipped before posting each cycle — tokens fail downstream gates (sum_gate, ev_min, etc.) before triggering a book fetch. Posting rate is gate-limited, not fetch-limited.

### Today's Deployment Lull (06:11–06:57 UTC)
10 consecutive zero-post cycles since 06:11 UTC:
- `yes_cap` = 0.36–0.44 → YES staking quota nearly exhausted at this point in the day
- `cash_preskip` = 127–133 (with `BAND_NO_CASH_RESERVE=0.25` reserving 25% of capital for NO)
- books = 0/80: nothing passing sum_gate/ev_min to trigger a book fetch
- Queue draining: 185 → 172 tokens (cycling out, not replenishing)

Consistent with d+1/d+2 token pool exhausted and `BAND_SAMEDAY_LIVE=False` blocking d+0. Not a deployment stall (cash_preskip ≤ 200 today with posted > 0 earlier); this is natural mid-morning quiet before new d+1 windows open.

---

## 4. RESOLUTION MARKOUT

**Source:** `trades.jsonl`, `bond_entry_class=WEATHER_STRUCT_BAND`, `exit_reason=STWA_RESOLVED`  
**n = 156 resolved band fills** (153 in last 7 days). **Decision-grade (n ≥ 100).**

### WINNER'S CURSE — CONFIRMED, SEVERE

| Metric | YES fills | NO fills | Overall |
|---|---|---|---|
| n (resolved) | 137 | 19 | 156 |
| Win rate (actual) | **4.4%** | 21.1% | 6.4% |
| Avg entry price | 0.231 | 0.553 | — |
| Breakeven WR needed | 23.1% | 55.3% | — |
| Gap to breakeven | **−18.7 pp** | −34.2 pp | — |
| Actual ROI | **−91.2%** | −76.6% | **−88.6%** |
| Total net PnL (7d) | — | — | **−$338.63** |

**All-fires comparison (Jun 15–16 fire records, n=1,856 leg quotes):**  
Avg fire ask = 26.2% (badatmath's estimated fair P(YES in band)). At our quoted bid ≈24.9%, expected ROI if fills were unselected = **+5.3%**. Actual filled-leg ROI = **−81%**. Adverse selection gap = **86 percentage points**.

**By fill price band:**

| Price | n | Win Rate | ROI |
|---|---|---|---|
| < 0.10 | 6 | 0% | −100% |
| 0.10–0.30 | 101 | 4% | −89.5% |
| 0.30–0.50 | 30 | 7% | −95.3% |
| > 0.50 (NO) | 19 | 21% | −76.3% |

All price bands loss-making. Near-zero win rates confirm the fill population is heavily adverse-selected, not a calibration error: takers who lift our bids know the temperature is diverging from the mode. Our bid rests visible on the CLOB; they pick selectively.

---

## 5. DEAD-QUOTE RECLAIM

**Reclaim events in 7-day tape:** 0 (no `reaped dead entry` or reclaim lines in `maker_fills_recent.log`)

### Resting Quote Ages

| Metric | Value |
|---|---|
| Active resting entries (non-SELL_EXIT) | 45 (38 YES, 5 NO, 2 side-unknown) |
| SELL_EXIT entries | 137 |
| Quotes > 24h old | 25 |
| Quotes > 48h old | **17** |
| Oldest: Seattle NO | 131 h (5.5 days), $2.60 unfilled |
| Oldest: Seoul NO | 131 h (5.5 days), $2.60 unfilled |

17 quotes older than 48h — just below the ALERT threshold of 20. Most >48h YES quotes show $0.00 unfilled (filled but resting-state entry not cleaned up). The two oldest NO quotes (Seattle, Seoul, both 131h) are genuinely unfilled and represent velocity leakage. `BAND_RECLAIM_AGE_S=2h` should be catching these; either the reclaim is logging elsewhere or it is not firing on these tokens. No hard ALERT fires.

---

## 6. CASH VELOCITY

| Metric | Value |
|---|---|
| Capital (bankroll.json) | $239.22 *(CAVEAT: user manual sells distort; do not infer PnL/ruin)* |
| Active resting $ (unfilled) | $28.06 (YES=$16.23, NO=$11.83) |
| Fills $ last 24h | $87.47 |
| Capital turns/day | **0.37** |
| Benchmark (badatmath) | ~1.0 turn/day |
| Our ratio to benchmark | **37%** |

37% of badatmath's velocity. Primary cause: NO fills are 5% of volume instead of ~50%. Each NO post carries `BAND_NO_STAKE=4.5` vs YES ~$1 — so NO fills should drive 4.5× the dollar per event. With NO fills near zero, the high-value side of the book is almost entirely unworked. Secondary cause: `BAND_STAKE_FRAC_YES=0.005` caps each YES post at ~$1.20 given $239 capital, keeping YES at minimum size.

---

## ALERTS

### ALERT A — NO-STARVATION REGRESSION (CRITICAL)
**Trigger:** NO share of new posts < 25% on any day with ≥10 posts.  
**Fired:** 5 of 6 days since the Jun-12 fix commit (Jun 12, 14, 15, 16, 17). Jun 15 worst: 2.2%.  
The fix commit did not hold. `BAND_NO_ENABLED=True` is set but NO orders are not reaching the CLOB at scale. Resting book: 11.6% NO.

### ALERT B — WINNER'S CURSE (CRITICAL, n=156, decision-grade)
**Trigger:** ROI(filled) materially below ROI(all-fires) on same slice at n≥40.  
**Fired:** All slices. YES WR 4.4% vs breakeven 23.1% (−18.7 pp). All-fires expected ROI +5.3%; filled ROI −81%. Adverse selection gap = 86 pp.  
7-day net PnL from resolved band legs: **−$338.63** on $384.77 staked.

---

## Summary

**Fills/day:** ~40/day (161 fills ÷ 4 active days); 24h count = 65, almost entirely YES.  
**NO-share:** 5.0% (7-day), 4.6% (24h) — chronic starvation; fix commit has not held.  
**Binding execution constraint:** Winner's curse. The band is generating fills but resolving at −88.6% ROI. Capital velocity (37% of benchmark) is a symptom, not the root cause. Until adverse selection is addressed — tighter spread, faster reclaim on fills that go against us, or information-conditioned quoting — posting faster accelerates losses.
