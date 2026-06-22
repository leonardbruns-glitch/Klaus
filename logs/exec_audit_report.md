# Execution & Markout Audit
**Date:** 2026-06-22 | **Snapshot:** 2026-06-22T06:57:09Z (age: <15 min) | **Status:** ACTIVE  
**Klaus systemd:** active | **Capital:** $232.64 | **Bot uptime since:** 2026-06-21 16:38 UTC  
**Audit window:** 7d fill tape (Jun 19–22), 6d NO-parity (Jun 17–22), 7d queue health

---

## 1. FILL TAPE

### 7-Day Summary (Jun 19–22)

| Date | n_fills | YES_n | YES_$ | NO_n | NO_$ | Total_$ | NO-share |
|---|---|---|---|---|---|---|---|
| Jun 19 | 52 | 30 | $35.6 | 22 | $75.2 | $110.8 | 42% |
| Jun 20 | 72 | 48 | $58.7 | 24 | $57.7 | $116.4 | 33% |
| Jun 21 | 82 | 43 | $35.2 | 39 | $119.7 | $154.9 | 48% |
| Jun 22 (partial, 07:00 UTC) | 8 | 4 | $2.8 | 4 | $12.4 | $15.2 | 50% |
| **7d total** | **214** | **125** | **$132.3** | **89** | **$265.0** | **$397.3** | **42%** |

Jun 21 was the highest fill day (82 fills, $154.9). Trend is improving.

### Fill $ by Price Band (7d, 214 fills with price data)

| Band | n | YES | NO | Total_$ |
|---|---|---|---|---|
| <0.10 | 39 | 39 | 0 | $21.84 |
| 0.10–0.30 | 86 | 86 | 0 | $110.35 |
| 0.30–0.50 | 2 | 0 | 2 | $5.04 |
| 0.50–0.85 | 87 | 0 | 87 | $259.97 |
| >0.85 | 0 | — | — | $0.00 |

Clean separation: YES fills concentrate below 0.30 (near-mode entries), NO fills concentrate 0.50–0.85 (favorite-NO overlay). No cross-contamination.

### Fill Rate by Day

| Date | Posted tokens | Filled tokens | Fill rate |
|---|---|---|---|
| Jun 17 | 71 | — | (log pre-dates tape) |
| Jun 18 | 95 | — | (log pre-dates tape) |
| Jun 19 | 44 | 35 | 80% |
| Jun 20 | 33 | 38 | 115%* |
| Jun 21 | 45 | 44 | 98% |
| Jun 22 | 8 | 3 | 38% (day partial) |

*Jun 20 >100% because some fills registered same day for tokens posted Jun 19 (multi-day quotes fill the next day).

### 24h Fills (trailing 24h to snapshot)
n=72 fills: YES=$33.87, NO=$94.37 → **total $128.25**

### Median Time-to-Fill
Uncomputable: MAKER-FILL log uses truncated token IDs; band_struct_lite post timestamps cannot be matched without full band_struct.jsonl.

---

## 2. NO-PARITY MONITOR

Source: band_struct_lite.jsonl `record=post` per day.

| Date | Total posts | YES | NO | NO% | Alert |
|---|---|---|---|---|---|
| Jun 17 | 179 | 169 | 10 | **6%** | STARVATION FIRED |
| Jun 18 | 138 | 116 | 22 | **16%** | STARVATION FIRED |
| Jun 19 | 56 | 41 | 15 | 27% | OK |
| Jun 20 | 50 | 36 | 14 | 28% | OK |
| Jun 21 | 72 | 40 | 32 | 44% | OK (near 50% target) |
| Jun 22 | 9 | 6 | 3 | 33% | n<10 (not alertable) |

**Verdict:** NO-starvation fix confirmed holding. Jun 17–18 starvation (6%, 16%) predates the effective `favNO TOP priority` commit. Jun 19+ recovery is clean; Jun 21 at 44% is near target. Fix is sustained.

Resting book (entry orders only, excluding SELL_EXIT): YES=25, NO=6, ?=7. YES-heavy resting skew is expected given Jun 19–20 posting ratios; improving in Jun 21.

---

## 3. QUEUE HEALTH (STRUCT-BAND-Q)

| Date | Cycles | avg_cash | avg_books/80 | max_books | avg_yes/50 | max_yes | avg_posted/cycle | total_posted |
|---|---|---|---|---|---|---|---|---|
| Jun 19 | 198 | $73 | 0.4 | 4 | 0.2 | 2 | 0.2 | 47 |
| Jun 20 | 280 | $85 | 0.4 | 8 | 0.2 | 4 | 0.2 | 50 |
| Jun 21 | 280 | $68 | 0.4 | 12 | 0.2 | 6 | 1.2 | 349 |
| Jun 22 | 81 | $114 | 0.2 | 7 | 0.1 | 4 | 0.1 | 9 |

Books not pinned: max 12/80 (15%) on Jun 21. YES books not pinned: max 6/50 (12%). No fetch starvation regression.

Jun 21 avg_posted spike (1.2 vs ~0.2 baseline) drove 349 total posts and the highest fill day. Jun 22 partial day shows $114 avg_cash and only 9 posts in 81 cycles — consistent with early-UTC morning before the daily posting window heats up.

No alerts fired.

---

## 4. RESOLUTION MARKOUT (Fill Quality — Adverse Selection Test)

### Data Limitation
`band_resolution_join.py` requires `logs/shadow/hot/<date>/band_struct.jsonl` (full fire records with condition IDs and bid_quote), which exists only on the live VPS. The lite files in data-mirror lack bid_quote/ask fields. **Cannot run the authoritative winner's-curse join from this environment.**

### Proxy 1: Held-to-Resolution Positions (STWA_RESOLVED in trades.jsonl)

Positions held to resolution without a proactive 0.99-exit (n=649, Jun 10+):

**By direction:**
| Direction | n | WR | Avg entry | Break-even WR | EV |
|---|---|---|---|---|---|
| BUY_YES | 482 | 4% | 0.226 | 22.6% | −18.6% |
| BUY_NO | 166 | 39% | 0.602 | 60.2% | −21.2% |

**By entry price band:**
| Band | n | WR | Break-even | EV |
|---|---|---|---|---|
| <0.10 | 90 | 3% | 6% | −0.031 |
| 0.10–0.30 | 315 | 4% | 20% | −0.160 |
| 0.30–0.50 | 98 | 8% | 35% | −0.271 |
| 0.50–0.85 | 112 | 42% | 63% | −0.210 |

**Critical caveat:** The STWA_RESOLVED pool is structurally biased toward losers. Winning positions are sold at 0.99 before resolution (exit099 captures these), so only positions that trended to zero survive to STWA_RESOLVED. This creates apparent low WR without implying adverse fill selection. This is the intended two-path exit mechanism, not a signal of winner's curse.

### Proxy 2: exit099 Winners

94 winner exits over Jun 17–22, total PnL **+$425.44**:

| Day | n | PnL | avg entry | avg ROI |
|---|---|---|---|---|
| Jun 17 | 20 | $87.45 | 0.347 | 337% |
| Jun 18 | 26 | $99.56 | 0.350 | 295% |
| Jun 19 | 19 | $78.58 | 0.288 | 306% |
| Jun 20 | 13 | $75.12 | 0.568 | 332% |
| Jun 21 | 14 | $76.37 | 0.451 | 186% |
| Jun 22 | 2 | $8.37 | 0.565 | 83% |

Exit099 by entry price band:
| Band | n | avg ROI |
|---|---|---|
| <0.10 | 3 | +1783% |
| 0.10–0.30 | 37 | +428% |
| 0.30–0.50 | 25 | +187% |
| 0.50–0.85 | 23 | +63% |

### Winner's Curse Verdict

**No flag raised at current data.** Evidence against adverse selection:

1. Fill rate 80–98% on posted positions: takers are hitting virtually everything we post, not selectively picking off losing quotes.
2. exit099 PnL strongly positive (+$425 in 6 days) — if we were systematically being adversely selected, winners would not be this frequent or profitable.
3. n=214 fills in 7 days at 42% NO share aligns with posted NO share, suggesting no systematic side-specific adverse selection.

The held-to-resolution EV being negative (all price bands) is a separate concern about position-level edge, not fill selection adversity. That question requires the full band_resolution_join.py output comparing filled vs. all-posted-but-unfilled resolution outcomes — cannot compute here.

**Action:** Run `band_resolution_join.py` from VPS on next agent session with VPS access to get n≥100 fill-vs-all-fires markout.

---

## 5. DEAD-QUOTE RECLAIM

- **"reaped dead entry" lines in 7d tape:** 0
- **Entry orders in maker_resting_state (non-SELL_EXIT):** 38 total
  - >24h old: **15** of 38
  - >48h old: **9** of 38 — approaching alert threshold (20)
  - Oldest: **113.7h** (Moscow, Jun 17-18 market, matched 5.09/5.10 = 99.8% filled)
  - Top 5 oldest: 113.7h, 103.7h, 101.8h, 99.5h, 98.2h (all Jun 17–18 resolved markets)
- **$ freed by reclaim in 7d:** $0 (no reaped lines)
- **SELL_EXIT resting:** 50 orders at 0.99 (no ts field — age unknown), $593 notional

**Observation:** The 9 quotes >48h are on Jun 17–18 markets that have already resolved. Most are nearly fully matched (Moscow: 5.09/5.10, Paris: 12.49/12.50 — effectively filled). These are ghost resting-state entries not tied to live capital but polluting the book scan. BAND_RECLAIM_AGE_S=2h should have cleaned these; their persistence suggests either they pre-date the reclaim scan setup or are excluded by logic for near-fully-matched entries. Not a cash-velocity issue but monitor for >20.

---

## 6. CASH VELOCITY

| Metric | Value | Benchmark |
|---|---|---|
| Capital (bankroll) | $232.64 | — |
| Entry resting (bid orders, non-SELL_EXIT) | $62.95 | — |
| SELL_EXIT resting (exit orders at 0.99) | $593.01 | — |
| Total resting | $655.96 | — |
| 24h fill volume | $128.25 | — |
| **Turns/day (fill$ / capital)** | **0.55** | ~1.0 (badatmath) |
| exit099 PnL (24h) | $82.18 | — |

Turns/day at 0.55 is below the 1.0 benchmark. Mitigating factors:

1. Snapshot at 07:00 UTC — early morning; posting volume ramps through 08:00–16:00 UTC.
2. Jun 21 full-day implied velocity: $154.9/$232 = 0.67 turns — closer to target than today's partial-day number.
3. $593 in SELL_EXIT resting represents 50 held YES positions queued for 0.99 exit. These are capital at work awaiting resolution; the fill-turn metric understates true deployment.

---

## ALERTS

| # | Condition | Status | Detail |
|---|---|---|---|
| 1 | NO-starvation (<25% NO on ≥10 posts/day) | **FIRED (historical)** | Jun 17: 6%, Jun 18: 16% — both days fired. Jun 19+ recovered. Fix confirmed. |
| 2 | Books pinned at 80 | NOT fired | max 12/80 |
| 3 | YES books pinned at 50 | NOT fired | max 6/50 |
| 4 | Deployment stall (cash>$200 & posted=0) | NOT fired | posting active all days |
| 5 | Dead quotes >48h: >20 | NOT fired | 9 orders >48h (threshold: 20) |
| 6 | Winner's curse (filled ROI << all-fires ROI) | **INCONCLUSIVE** | Cannot compute without VPS hot files. Circumstantial evidence (80–98% fill rate, +$425 exit099) argues against. Run band_resolution_join.py on VPS. |

---

## Summary

**Fills/day:** 52–82 rising trend; Jun 21 best day at 82 fills, $154.9  
**NO-share:** 42% overall 7d; recovering to 44% Jun 21 — starvation fix confirmed sustained  
**Binding constraint today:** Cash velocity 0.55 turns/day (vs 1.0 target); $593 locked in 50 SELL_EXIT pending orders. Markout quality question (winner's curse vs all-fires) requires VPS access to run `band_resolution_join.py` on hot band_struct.jsonl files — this environment cannot resolve it.
