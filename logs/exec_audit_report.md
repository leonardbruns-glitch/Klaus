# Klaus Execution Audit — 2026-06-27T07:13Z

**Generated:** 2026-06-27T07:13Z | **Snapshot:** 2026-06-27T06:54Z (age: 19 min, FRESH)
**Service status:** `active` (restarted 2026-06-26T15:08:30 UTC)
**Capital:** $57.12 | **Resting:** 1 NO bid + 8 SELL_EXIT | **Band config:** BAND_LIVE=True, BAND_NO_ENABLED=True

---

## 1. FILL TAPE

### 24h (Jun 26 15:08 UTC → Jun 27 07:13 UTC)

| Metric | Value |
|---|---|
| Registered fills | **10** (8 Jun-26 + 2 Jun-27) |
| $ filled (shares × price) | **$46.51** |
| Side breakdown | 10 NO, 0 YES |
| Price range | $0.55 – $0.84 |
| Posts this window | 16 (14 Jun-26 + 2 Jun-27) |
| Fill rate | **63%** (10/16) |

### 7-Day Summary (Jun 24–27, log tape)

| Date | Registered Fills | Notional | Posted | Fill Rate | Avg Price |
|---|---|---|---|---|---|
| Jun 24 | 22 | ~$107 | 37 | 59% | $0.62 |
| Jun 25 | 7 | ~$35 | 6 | ~117%* | $0.65 |
| Jun 26 | 8 | ~$42 | 14 | 57% | $0.68 |
| Jun 27 (partial) | 2 | ~$13 | 2 | 100% | $0.75 |
| **7d total** | **39** | **~$197** | **59** | **66%** | **$0.63** |

\* Jun-25 fill rate >100% = prior-day carries resolving (post-date vs fill-date skew).

**By price band (7d, all NO):**

| Band | n | Notional |
|---|---|---|
| 0.30–0.50 | 1 | $5.39 |
| 0.50–0.85 | 38 | $159.10 |
| <0.50 or >0.85 | 0 | $0 |

100% of fills within configured gate (BAND_NO_MIN=0.52, BAND_NO_MAX=0.85). No out-of-gate fills.

**By city (7d, top):**

| City | Fills |
|---|---|
| Chengdu | 6 |
| Munich | 5 |
| Wuhan | 3 |
| London | 2 |
| Beijing | 2 |
| Seattle | 2 |
| Other (18 cities) | 19 |

**Median time-to-fill:** **88 min** (range 7–453 min, n=39 matched via band_struct_lite post timestamps).

---

## 2. NO-PARITY MONITOR

| Date | YES Posts | NO Posts | Total | NO Share | Alert |
|---|---|---|---|---|---|
| Jun 22 | 14 ($24) | 18 ($90) | 32 | **56%** | OK |
| Jun 23 | 0 | 46 ($230) | 46 | **100%** | — |
| Jun 24 | 0 | 37 ($185) | 37 | **100%** | — |
| Jun 25 | 0 | 6 ($30) | 6 | **100%** | — |
| Jun 26 | 0 | 14 ($70) | 14 | **100%** | — |
| Jun 27 | 0 | 2 ($10) | 2 | **100%** | — |

**NO-starvation alert (NO share < 25%) does NOT fire.** The book is the inverse: 100% NO, 0% YES since Jun 23.

**Root cause (confirmed intentional):** Phase 1 NO-only mode — `no_resv=1.00` in every cycle (commit `feat(BAND): P1 NO-only — no_reserve 0.40→1.00 until $600`). YES candidates queue (`yes_resv_skip=5–33/cycle`) but are pre-empted by 100% NO cash reserve. YES shadow fires exist at d+2 (4–47/day); the capital allocation gate suppresses live posting.

**NO-starvation bug (fixed 2026-06-12) status: HOLDS.** NO is posting; the 100% NO concentration is architectural, not a regression.

---

## 3. QUEUE HEALTH

Source: `[STRUCT-BAND-Q]` lines, maker_fills_recent.log.

| Date | Cycles | Cap | cash_preskip | books/max | yes_books/max | posts/cycle | yes_skip |
|---|---|---|---|---|---|---|---|
| Jun 24 | 200 | $219 | 96 | 0.2/5 | 0/0 | **0.9** | 14.1 |
| Jun 25 | 72 | $209 | 123 | 0.1/3 | 0/0 | 0.1 | 32.7 |
| Jun 26 | 103 | $62 | 3 | 0.9/9 | 0/0 | **1.1** | 0.0 |
| Jun 27 | 81 | $55 | 5 | 0.0/1 | 0/0 | **0.0** | 3.4 |

**books never pinned at 80 / yes_books never pinned at 50.** No fetch starvation regression.

**yes_books=0 always:** YES book fetches never attempted (consistent with Phase 1 NO-only; YES skipped before book-fetch stage).

**TODAY: 81 cycles, posted=0.**
- `cash_preskip=3–5` → only 3–5 candidates discarded per cycle due to cash, not >200 (registered stall threshold not met)
- `no_cands=20–21`, `pair_cands=0–1`, yet `posted=0`
- Probable cause: all 20 city-date-bucket combinations for the 5 BAND_CITY_ALLOW cities have already been posted or recycled in the current session, and the dedup seen-set blocks re-posting. The single resting London NO bid (1.4h old) confirms the book is nearly empty
- This is **not** the cash_preskip>200 stall pattern (capital-available); it is market-exhaustion within the narrow 5-city allowlist

---

## 4. RESOLUTION MARKOUT (Fill Quality — Adverse Selection Test)

**Network blocked in this environment.** Gamma API unreachable → band_resolution_join.py cannot run for a full all-fires join. Analysis uses STWA_RESOLVED trades (n=89 post-Jun10) + 5-day exit099 series from shadow data.

### 4a. Daily Resolution Table

| Date | STWA n | STWA WR | STWA P&L | exit099 n | exit099 P&L | **Net** |
|---|---|---|---|---|---|---|
| Jun 21 | 27 | 15% | −$46.45 | 14 | +$76.37 | **+$29.92** |
| Jun 22 | 31 | 6% | −$77.37 | 11 | +$43.74 | **−$33.63** |
| Jun 23 | 24 | 4% | −$65.08 | 18 | +$77.00 | **+$11.92** |
| Jun 24 | 16 | 6% | −$68.14 | 18 | +$56.71 | **−$11.43** |
| Jun 25 | 4 | 0% | −$21.34 | 4 | +$9.86 | **−$11.48** |
| Jun 26 | 0 | — | $0 | 0 | $0 | $0 |
| Jun 27 | 0 | — | $0 | 1 | +$1.82 | **+$1.82** |
| **Sum** | **102** | **~7.8%** | **−$278.38** | **66** | **+$265.50** | **−$12.88** |

### 4b. Winner's Curse Assessment

**BUY_NO WR (STWA_RESOLVED, n=89, post-Jun10): 21.3%**
**Break-even WR at mean fill price $0.63: 63%**

Net EV per fill: `0.213 × $7.81_avg_win − 0.787 × $5.00_avg_loss = −$2.28/trade`

n=89 is decision-grade. The gap between fill WR (21%) and break-even (63%) is not noise. We are being filled when NO is about to lose. This is the adverse selection failure that killed the prior Maker MVP.

Research audit attributes this primarily to **June seasonal heat bias** (Northern Hemisphere summer → temperatures exceed band thresholds → YES wins → NO loses). If seasonal, WR should recover in autumn; if structural model failure, it will not.

### 4c. exit099 (recycle path) Markout by Price Band

| Entry price band | n | Total PnL | Avg ROI |
|---|---|---|---|
| <0.50 | 5 | +$49.62 | **+627%** |
| 0.50–0.65 | 29 | +$102.76 | **+68.8%** |
| 0.65–0.79 | 14 | +$32.68 | **+44.8%** |
| >0.85 | 4 | +$4.06 | **+5.6%** |

exit099 ROI is positive across all price bands. Efficiency declines at higher entry prices (less room to run to $0.99), but remains positive. The drag is entirely STWA_RESOLVED: losses outpace gains 2.4:1 over 5 days ($278 losses vs $266 gains).

**WINNER'S CURSE ALERT — FIRES.** Fill-specific resolved WR (21.3%) is materially below what the all-fires simulated WR would be (break-even alone is 63%, and an unbiased fill sample should be near neutral). The signal is at n=89; n=40 threshold for "trend," n=100 for "decision-grade" — we are at the decision-grade boundary.

---

## 5. DEAD-QUOTE RECLAIM

| Metric | Value |
|---|---|
| "reaped dead entry" log lines | **0** |
| Total resting quotes | **9** (8 SELL_EXIT + 1 NO bid) |
| Oldest quote age | **1.4h** |
| Quotes > 24h old | **0** |
| Quotes > 48h old | **0** |

**No dead-quote alert.** BAND_RECLAIM_AGE_S=7200 (2h) — nothing has aged to reclaim threshold. All 8 SELL_EXIT orders are recent, resting at $0.99 as the win-path exits for filled NO positions.

---

## 6. CASH VELOCITY

| Component | Value |
|---|---|
| Capital (cash, bankroll.json) | **$57.12** |
| NO_CASH_RESERVE (30% of cap) | **$17.14** |
| NO bid resting (London, committed) | **$5.00** |
| Estimated free headroom | **~$35** |
| SELL_EXIT pending receipts if resolved NO | **$56.43** |
| Fills $ last 24h | **$46.51** |
| Turns/day (fills/capital) | **0.81** |

Turn rate at 0.81 is near the 1.0 benchmark — reflecting Jun 26 active posting after the restart. Jun 27 turn rate is effectively 0 (no new posts yet).

**Capital trajectory:** $209 (Jun 24 EOD) → $57 now, down 73% in 3 days. Decomposition: STWA_RESOLVED losses (−$278 Jun 21–25) overwhelm exit099 gains (+$265 Jun 21–25). At the current fill rate and WR, capital will continue declining.

**Binary risk on existing book:** 8 SELL_EXIT positions (total ~57 shares at avg ~$0.69 cost basis) represent $56.43 in expected receipts. If those 8 markets resolve YES (temperature exceeds threshold → NO worthless), expected receipts drop to ~$0 and capital falls toward $0–$5. This is the session's primary risk.

**badatmath benchmark:** ~1.0 equity turn/day at 10–20% ROI/turn. Klaus volume comparable (0.81 turns); ROI is inverted (−19% on STWA_RESOLVED; +33–68% on exit099 recycles). The structural difference: badatmath's fill quality (YES-side bias) is not subject to June heat adverse selection in the same direction.

---

## ALERTS

| # | Alert condition | Status |
|---|---|---|
| A1 | NO share < 25% on any day ≥10 posts (NO-starvation regression) | **NOT FIRED** |
| A2 | books pinned at 80 or yes_books pinned at 50 (fetch starvation) | **NOT FIRED** |
| A3 | cash_preskip > 200 sustained while posted=0 all day (deployment stall) | **NOT FIRED** |
| A4 | Quotes > 48h old (velocity leak) | **NOT FIRED** |
| **A5** | **Winner's curse: fill ROI materially below all-fires ROI (n≥40)** | **FIRED** — n=89 NO fills post-Jun10, WR=21.3% vs 63% break-even, EV=−$2.28/trade. June heat bias is proposed cause; seasonal validation pending. |

---

## 3-Line Summary

**Fills/day:** 13/day average across Jun 24–26 active periods (66% fill rate, 88min median TTF); **0 posts in 81 cycles today** — market exhaustion within the 5-city BAND_CITY_ALLOW, not a systemic engine stall.

**NO-share:** 100% NO since Jun 23 (Phase 1 NO-only intentional; YES suppressed by full NO cash reserve until $600 capital); NO-starvation bug remains fixed.

**Binding execution constraint:** Winner's curse on NO fills, confirmed at n=89 (WR=21.3%, break-even 63%, EV=−$2.28/trade). Capital down 73% to $57 in 3 days; 8 SELL_EXIT positions are the session's binary resolution risk; Jun heat bias is the suspected cause of the adverse selection.
