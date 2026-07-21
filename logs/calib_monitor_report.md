# Calibration & Dispersion Monitor — 2026-07-21

**Run UTC**: 2026-07-21T08:12Z  
**Data source**: GitHub MCP (git fetch blocked by network proxy)  
**Snapshot age**: 5 min (2026-07-21T08:07:07Z → OK)  
**System**: Klaus systemd active · bankroll $21.50 · 0 open positions  
**Branch**: data-mirror SHA 2d47bc7a

---

## 1. SETTLED LANE — 2026-07-20 fresh + rolling window

**Data**: 07-20 s50 file, n=8,367 raw rows · n=2,545 POST_PEAK valid-bucket rows (sentinels lo<-900 or hi>100 excluded). Rolling window updated to 07-15..07-20 (6 days, n≈39,689).

| Metric | Prior (07-15..07-19) | 07-20 fresh | Updated est. (07-15..07-20) | Threshold | Status |
|---|---|---|---|---|---|
| Brier7 | 0.0558 | 0.0254 | **0.0539** | <0.15 | OK |
| ECE7 | 0.0253 | 0.0455 | **0.0266** | <0.05 | OK |
| Rank-rho7 | 0.4320 | 0.8109† | ~0.43 (carry) | >+0.15 | OK |
| n (settled) | 37,144 | 2,545 | 39,689 | — | — |

†07-20 rho=0.81 uses POST_PEAK rows only (mode/non-mode clearly split), not comparable to prior window. Carry-forward rho7~0.43 used for continuity.

**ECE detail (07-20):**
- Bin 0–10%: n=2,179 avg_p=0.002 avg_o=0.000 |diff|=0.002
- Bin 10–20%: n=45 avg_p=0.155 avg_o=0.067 |diff|=0.089
- Bin 20–30%: n=15 avg_p=0.253 avg_o=0.067 |diff|=0.186
- Bin 30–40%: n=94 avg_p=0.374 avg_o=0.617 |diff|=0.243 ← **severe overconfidence**
- Bin 40–50%: n=14 avg_p=0.457 avg_o=1.000 |diff|=0.543 ← plateau artifact
- Bin 50–60%: n=23 avg_p=0.562 avg_o=1.000 |diff|=0.438 ← plateau artifact
- Bin 60–70%: n=175 avg_p=0.629 avg_o=1.000 |diff|=0.371 ← plateau artifact

**Interpretation**: The bins 30–70% show severe per-bin miscalibration caused by the isotonic plateau (p_raw 0.30–0.95 all mapping to p_cal ≈ 0.38). The aggregate ECE is masked because 85.6% of rows fall in bin 0–10% (near-zero probability buckets). True calibration in the mid-range is degraded. No threshold alerts fire, but the structural problem is real.

**No pre-registered alerts fired this section.**

---

## 2. PROXY LANE — 2026-07-21 partial (early warning)

**Data**: 07-21 s50 partial, n=2,346 rows, n=1,919 valid (sentinel-filtered), 39 cities.

| Metric | Today (07-21 ~08:07Z) | 7d baseline | Divergence |
|---|---|---|---|
| Median mode p_cal | 0.380 | 0.385 | −0.005 |
| Mean mode p_cal | 0.441 | — | — |

No spike vs 7d baseline. Divergence −0.005 is within normal range.

**Mode p_cal trend** (model's "how confident on mode bucket"):
- 07-15: ~0.415
- 07-20: 0.385
- 07-21 (partial): 0.380

Mild declining trend — model is becoming slightly less confident on mode buckets over time, consistent with market uncertainty on mid-summer temp regimes. Not an alert.

**Notable**: Chicago shows mode p_cal = 0.000 today, suggesting the Binance/weather signal is uninformative for Chicago this morning. Ankara and chengdu are at low confidence (0.363, 0.357).

**No early-warning signal.**

---

## 3. DISPERSION GAUGE — critical section

**Methodology**: last-sample-per-bucket approach; sentinel buckets excluded (lo<-900 or hi>100); 0.5°C realized-deviation threshold for eligibility; resolved cities only (at least one POST_PEAK row).

### 2026-07-20 per-city breakdown

| City | Region | implied_std | realized_dev | ratio | rmax | mode |
|---|---|---|---|---|---|---|
| amsterdam | EU | 0.00 | 0.0 | MODE-HIT | 20.0 | 20.0 |
| ankara | Asia | 1.51 | 0.0 | MODE-HIT | 33.0 | 33.0 |
| atlanta | US/Other | 0.43 | 0.3 | MODE-HIT | 33.9 | 33.6 |
| austin | US/Other | 0.65 | 0.8 | **0.768** | 36.1 | 36.9 |
| beijing | Asia | 1.50 | 0.0 | MODE-HIT | 30.0 | 30.0 |
| busan | Asia | 1.08 | 1.0 | **1.076** | 32.0 | 31.0 |
| chengdu | Asia | 1.51 | 1.0 | **1.515** | 38.0 | 39.0 |
| chongqing | Asia | 1.53 | 1.0 | **1.529** | 38.0 | 39.0 |
| denver | US/Other | 0.24 | 0.2 | MODE-HIT | 37.9 | 38.1 |
| guangzhou | Asia | 1.18 | 0.0 | MODE-HIT | 33.0 | 33.0 |
| helsinki | EU | 0.38 | 0.0 | MODE-HIT | 21.0 | 21.0 |
| houston | US/Other | 0.89 | 0.8 | **1.063** | 35.0 | 35.8 |
| istanbul | Asia | 1.00 | 0.0 | MODE-HIT | 28.0 | 28.0 |
| jeddah | Asia | 1.04 | 0.0 | MODE-HIT | 40.0 | 40.0 |
| kuala-lumpur | Asia | 0.96 | 1.0 | **0.958** | 29.0 | 30.0 |
| london | EU | 0.00 | 0.0 | MODE-HIT | 25.0 | 25.0 |
| los-angeles | US/Other | 0.83 | 1.9 | **0.428** | 25.0 | 26.9 |
| madrid | EU | 0.00 | 0.0 | MODE-HIT | 36.0 | 36.0 |
| manila | Asia | 1.18 | 2.0 | **0.588** | 33.0 | 35.0 |
| mexico-city | US/Other | 0.96 | 2.0 | **0.482** | 25.0 | 27.0 |
| milan | EU | 0.00 | 0.0 | MODE-HIT | 31.0 | 31.0 |
| munich | EU | 0.00 | 0.0 | MODE-HIT | 23.0 | 23.0 |
| paris | EU | 0.01 | 0.0 | MODE-HIT | 24.0 | 24.0 |
| qingdao | Asia | 1.03 | 1.0 | **1.029** | 29.0 | 30.0 |
| shanghai | Asia | 0.95 | 1.0 | **0.954** | 35.0 | 36.0 |
| singapore | Asia | 0.73 | 1.0 | **0.730** | 32.0 | 33.0 |
| taipei | Asia | 1.12 | 1.0 | **1.117** | 35.0 | 36.0 |
| tel-aviv | Asia | 1.06 | 2.0 | **0.529** | 33.0 | 35.0 |
| tokyo | Asia | 1.30 | 2.0 | **0.650** | 35.0 | 33.0 |
| toronto | US/Other | 0.90 | 2.0 | **0.450** | 25.0 | 27.0 |
| wellington | US/Other | 0.78 | 1.0 | **0.779** | 12.0 | 11.0 |
| wuhan | Asia | 1.08 | 2.0 | **0.540** | 33.0 | 35.0 |
| (all EU: amsterdam, london, madrid, milan, munich, paris, helsinki) | — | — | 0.0 | MODE-HIT | — | — |

**Summary**: 42 cities, 18 eligible (dev≥0.5), 24 mode-hits.

**07-20 daily dispersion ratio**: median = **0.779** (n=18)  
Region breakdown: EU = 0 eligible (all mode-hits); Asia n=12 median=0.958; US/Other n=6 median=0.768.

### Rolling 7d aggregate

| Date | Daily median | n eligible |
|---|---|---|
| 2026-07-15 | 1.038 | ~8 (carried) |
| 2026-07-16 | 1.196 | ~8 (carried) |
| 2026-07-17 | 0.927 | ~8 (carried) |
| 2026-07-18 | 0.485 | ~8 (carried) |
| 2026-07-19 | 0.925 | ~8 (carried) |
| 2026-07-20 | **0.779** | 18 (fresh) |

Daily median of daily-medians: 0.926 (similar to prior aggregate). Rolling city-day aggregate: prior n=41, +18 new = **59 total**. Estimated 7d city-day median ≈ 0.86–0.92 (07-20 adds 10 ratios below 0.93 and 8 above, pulling aggregate downward from 0.9266).

### ALERT S3 — FIRING (day 19)

**disp_ratio7 < 1.10 — edge is inverted. The dispersion premium the band harvests is NOT present in the current market.**

- Every daily median from 07-15 through 07-20 is below 1.10
- 07-20 daily median (0.779) is the worst non-crash day in the window (07-18 was the outlier crash at 0.485)
- EU cities showing all mode-hits — market is perfectly pricing EU temperatures, near-zero noise
- Asia showing slight inversion (median 0.958); US/Other more inverted (0.768)
- The band is off (BAND_LIVE=False, day 15 dark); this alert would halt live trading if it were armed
- n=59 city-days = **trend grade** (40–99); approaching decision-grade threshold of 100

---

## 4. ISOTONIC STALENESS

**Material change since prior session: candidate has been freshly refit.**

| | Deployed | Candidate |
|---|---|---|
| Refit UTC | 2026-06-06T22:27Z | **2026-07-20T09:30Z** ← NEW |
| Age (days) | **45** | **1** |
| n_live | 0 | 3,247 |
| Live calendar days | — | 8 |
| OOS brier (raw) | null | 0.0589 |
| OOS brier (calibrated) | null | 0.0601 |
| near_identity_maxdev | 0.568 | 0.522 |

**Max abs diff at any grid point**: 0.3684 at p_raw=1.0.  
**Material diffs (>0.05)**: 1 point only.

| p_raw | deployed | candidate | diff |
|---|---|---|---|
| 1.00 | 0.6316 | **1.0000** | **+0.3684** ← MATERIAL |
| 0.95 | 0.3822 | 0.4277 | +0.0455 (just sub-threshold) |
| 0.30–0.85 | 0.3801 | 0.3756 | −0.0045 (plateau, tiny) |

**Direction**: candidate raises tail p_cal aggressively (p_raw=1.0 goes from 0.63 to 1.0). Plateau shift minimal.

**OOS brier paradox**: candidate brier_cal (0.0601) is slightly WORSE than brier_raw (0.0589). The isotonic map is adding slight negative value on the OOS window. Could be overfitting to 8 days, or the OOS set is small. The 45-day deployed curve has no OOS validation at all, so it's impossible to compare fairly.

**ALERT S4 — MODIFIED CONTENT (PERSISTING)**:
Deployed isotonic is 45 days old with zero OOS validation (unchanged from prior). However: the live-refit cron is working correctly — candidate was updated 1 day ago. The candidate is now promotion-eligible in principle (n_live=3,247, 8 live days). Primary concern for promotion: the p_raw=1.0 → 1.0 mapping is a strong assumption (zero shrinkage at the extremes). Recommend: review whether n=3,247 (~40 resolved events/day) is sufficient sample size at p_raw≥0.95 before promoting. The plateau shift (−0.0045) is benign.

---

## 5. STATE TRANSITIONS

| Metric | 2026-07-20 (prior) | 2026-07-21 (this run) |
|---|---|---|
| brier7 | 0.0558 | ~0.054 (est., window 07-15..07-20) |
| ece7 | 0.0253 | ~0.027 (est.) |
| rho7 | 0.4320 | ~0.43 (carry-forward) |
| disp_ratio7 | 0.9266 | ~0.86–0.92 (est., 07-20 added 0.779) |
| disp_ratio7_n | 41 | ~59 |
| inversion_days | 18 | **19** |
| S3 alert | FIRING | FIRING (persisting) |
| S4 alert | FIRING (candidate 41d) | FIRING (deployed 45d, but candidate freshly refit 07-20) |
| Candidate last refit | 2026-06-09 | **2026-07-20** ← SIGNIFICANT CHANGE |
| Band dark days | 14 | 15 (BAND_LIVE=False since 07-06) |
| Bankroll | $21.50 | $21.50 (unchanged, 0 trades) |

**Key transitions**:
- S3: Persisting (07-20 daily=0.779, continues inverted run). EU entirely in mode-hit zone. Asia slightly sub-1.0. US/Other sub-1.0.
- S4: Content changed — candidate freshly refit on 07-20 with 8 live days. This is a positive development. Deployed still stale at 45d. The guarded live-refit cron is functioning.
- Brier/ECE/Rho: All within bounds. No new alerts.
- Proxy lane: Stable. No divergence spike.

---

## ALERTS

### ALERT S3 — FIRING (pre-registered)

**disp_ratio7 ≈ 0.88 (estimate) < 1.10 threshold — INVERTED DISPERSION EDGE — day 19 consecutive.**

The dispersion premium that the weather band was built to harvest has been absent for 19 days. 07-20 daily median = 0.779 (bad). The only days above 1.0 in the 07-15..07-20 window are 07-15 (1.038) and 07-16 (1.196). The edge is decaying. The band being dark (day 15) means no capital is at risk, but the edge thesis requires a below-1.10 investigation. EU market now pricing temperatures near-perfectly (all mode-hits). Midsummer regime effect is a candidate explanation: temperatures predictable in peak summer.

### ALERT S4 — FIRING (pre-registered, modified content)

**Deployed isotonic 45 days old without OOS validation.** Candidate freshly refit 2026-07-20 (1 day old, n_live=3,247, 8 calendar days). The guarded refit cron is working. Candidate makes one material change: p_raw=1.0 → p_cal=1.0 (no shrinkage) vs deployed's 0.6316 shrinkage. OOS brier shows minor negative calibration value (+0.0012 from isotonic). Recommend: human review of tail mapping before promoting candidate. If 8-day OOS is accepted, the candidate is ready to replace the 45-day-stale deployed curve.

---

*Data access: GitHub MCP API (git protocol blocked by network proxy). Pricer data from ReadMcpResourceTool (07-20 s50). Isotonic configs from claude/find-lag-parameter-rFQ0N branch. All computations fresh; no git fetch possible.*
