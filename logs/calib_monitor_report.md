# Calibration & Dispersion Monitor — 2026-07-02

**Snapshot:** 2026-07-02T11:23:06Z | **Klaus:** active | **Bankroll:** $76.31 | **Branch:** claude/find-lag-parameter-rFQ0N  
**Band live:** YES-only (BAND_LIVE=True, BAND_NO_ENABLED=False — EVOLVE halt since 2026-07-02)  
**Prior state:** 2026-07-01 | brier7=0.0139 | ece7=0.0361 | rho7=0.83 | disp_ratio7=0.470

---

## ALERTS

**A1 — PERSISTS S3:** Dispersion ratio 0.470 → **0.408** (d+2: 0.550 → **0.340**). Edge decay worsening second consecutive cycle.

**A2 — PERSISTS S4:** Isotonic material shift at grid=1.0 deployed=0.6316 vs candidate=0.3739. **DO NOT DEPLOY.**

---

## 1. Settled Lane (Brier / ECE / Rank-rho)

**Source:** Resolved market-days Jun 27–Jul 1, POST_PEAK running_max inference.  
**n = 2,091 buckets, 196 (city, date) pairs (all cities).** Decision-grade (>=100 rows).

| Metric | This Cycle | Prior (07-01) | Threshold | Status |
|---|---|---|---|---|
| Brier 7d | **0.0189** | 0.0139 | >0.15 | OK |
| ECE 7d | **0.0382** | 0.0361 | >0.05 | OK |
| Rank-rho (Spearman) | **0.9165** | 0.83 | <0.15 | OK |

ECE bin detail:

| Bin | n | mean_p | mean_o | abs delta |
|---|---|---|---|---|
| [0.0, 0.1) | 1,892 | 0.000 | 0.004 | 0.004 |
| [0.1, 0.2) | 4 | 0.154 | 0.000 | 0.154 |
| [0.2, 0.3) | 2 | 0.255 | 0.500 | 0.245 |
| [0.3, 0.4) | 22 | 0.373 | 0.727 | **0.354** |
| [0.4, 0.5) | 1 | 0.407 | 1.000 | 0.593 |
| [0.5, 0.6) | 6 | 0.560 | 1.000 | 0.440 |
| [0.6, 0.7) | 164 | 0.631 | 1.000 | 0.369 |

**Notes:**
- Scope change vs prior: prior covered 5 BAND_CITY_ALLOW cities (n~253); this cycle covers all 44 cities (n=2,091). Brier/rho comparisons are directional only.
- The [0.3,0.4) bin (n=22, mean_o=0.727) reflects the isotonic plateau at 0.3801: mode buckets collapse to this value, yielding apparent ECE underconfidence. Not a calibration defect — structural artifact.
- No pre-registered alert in the settled lane this cycle.

---

## 2. Proxy Lane (Today's Unsettled Markets)

**Source:** 2026-07-02 stwa_pricer_eval_s50.jsonl, PRE_PEAK buckets.  
**n = 244 PRE_PEAK buckets, 26 cities.** Early warning only (markets not settled).

| Metric | Value |
|---|---|
| PRE_PEAK buckets | 244 |
| POST_PEAK buckets | 156 (early-settling markets) |
| Max p_cal (PRE_PEAK) | 0.5433 (Istanbul) |
| Mean p_cal (PRE_PEAK) | 0.0919 |

Notable: Istanbul p_cal=0.5433 is above the usual 0.3801 plateau — strong concentrated model signal. Chengdu p_cal=0.000 today (minimal market presence, limited d+2 opportunity).

No book_mid in s50 schema (structural) — cannot compute |p_cal - mid| divergence. No 7d baseline available for this metric yet.

---

## 3. Dispersion Gauge — ALERT PERSISTS

**The band's load-bearing quantity: market-implied dispersion > true dispersion.**

**Method:** 31 fire records (md_shadow, reason=fire) from band_struct_lite for BAND_CITY_ALLOW cities with resolved target dates Jun 27–Jul 1. Implied sigma = weighted std of bucket mids (ask prices as weights). Realized dev = |running_max - mode_bucket_mid|.

### Rolling 7d Summary

| Metric | This Cycle | Prior (07-01) | 07-01 prior | Trend |
|---|---|---|---|---|
| Median implied sigma | 0.969 C | 0.939 C | — | flat |
| Median realized dev | 2.000 C | 2.000 C | — | unchanged |
| **Ratio (all days_out)** | **0.408** | **0.470** | 1.061 | **WORSENING** |
| **Ratio (d+2 only)** | **0.340** | **0.550** | 1.100 | **WORSENING** |
| n fires (finite ratio) | 31 (25) | 23 | — | — |
| Alert threshold | <1.10 | <1.10 | — | TRIGGERED |

**The dispersion premium is inverted and deteriorating.** The market implies ~0.97 C of uncertainty; reality delivers 2.0 C of error from the mode. Three cycles of ratio data: 1.06 (baseline) → 0.47 → 0.41. Not noise — structural.

### By City

| City | n fires | Med implied | Med realized | Med ratio |
|---|---|---|---|---|
| **Chengdu** | 12 (8 finite) | 0.89 C | 3.50 C | **0.222** |
| **Beijing** | 5 (4 finite) | 0.96 C | 3.00 C | **0.311** |
| London | 1 | 0.82 C | 2.00 C | 0.408 |
| Munich | 7 (5 finite) | 0.94 C | 1.00 C | 0.736 |
| **Wuhan** | 6 (6 finite) | 1.05 C | 1.00 C | **1.015** |

### d+2 Fire Records (Live YES Posting Slice)

BAND_YES_LIVE_MIN_DOUT=2 means ALL live YES orders are placed at d+2. This slice is most operationally relevant.

| City | Target date | Mode | Rmax | Impl sigma | Real dev | Ratio |
|---|---|---|---|---|---|---|
| Beijing | 2026-06-29 | 24.0 C | 27.0 C | 0.82 C | 3.0 C | 0.272 |
| Chengdu | 2026-06-29 | 27.0 C | 33.0 C | 1.12 C | 6.0 C | 0.186 |
| Wuhan | 2026-06-30 | 30.0 C | 29.0 C | 1.20 C | 1.0 C | 1.199 |
| London | 2026-06-30 | 22.0 C | 24.0 C | 0.82 C | 2.0 C | 0.408 |
| Munich | 2026-06-30 | 26.0 C | 28.0 C | 1.11 C | 2.0 C | 0.557 |
| Chengdu | 2026-06-30 | 28.0 C | 32.0 C | 1.10 C | 4.0 C | 0.275 |
| Beijing | 2026-06-30 | 26.0 C | 30.0 C | 1.36 C | 4.0 C | 0.340 |
| Wuhan | 2026-07-01 | 26.0 C | 31.0 C | 0.85 C | 5.0 C | **0.169** |
| Chengdu | 2026-07-01 | 26.0 C | 32.0 C | 0.82 C | 6.0 C | **0.136** |
| Munich | 2026-07-01 | 22.0 C | 22.0 C | 1.19 C | 0.0 C | inf |
| Beijing | 2026-07-01 | 31.0 C | 31.0 C | 1.10 C | 0.0 C | inf |

**d+2 median ratio (finite): 0.340.**

### Diagnosis

**Chengdu systematic cold bias (most severe):** Model forecasts 26–29 C; actual maxima run 32–33 C across 5 consecutive fire dates. Miss of 3–6 C. Central forecast wrong by 3–6 bucket widths. The band repeatedly fires on buckets centered 3–6 C below where the temperature actually lands.

**Beijing cold bias (second worst):** Forecasts 24–26 C; actual 27–34 C. Persistent 3–4 C underestimate on d+2 fires. Two perfect hits (Jul 1 d+1 and d+2) are notable — may be transient.

**Wuhan near break-even (ratio 1.015):** The one city where the dispersion edge is approximately holding. d+1 fires mostly within 1 C. But Jul 1 d+2 was a 5 C miss (ratio 0.169) — the break-even may not hold.

**Munich moderate (ratio 0.736):** Most fires within 1–2 C. Better than China cities. Two perfect hits. Still below 1.10.

**London (insufficient data):** Only one resolved d+2 fire this week. Cannot characterize.

---

## 4. Isotonic Staleness

| | Deployed | Candidate |
|---|---|---|
| Refit UTC | 2026-06-06T22:27:08 | 2026-06-09T09:30:36 |
| Age (days) | 26 | 23 |
| n_live | 0 | 1,037 |
| near_identity_maxdev | 0.568 | 0.626 |
| n_hist | 76,617 | 76,617 |

**Grid comparison (selected nodes):**

| grid | deployed | candidate | delta |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 |
| 0.25 | 0.3557 | 0.3535 | −0.002 |
| 0.30–0.90 | 0.3801 | 0.3739 | −0.006 |
| **1.00** | **0.6316** | **0.3739** | **−0.258** |

**Material shift at grid=1.0: delta = −0.258 (well above 0.05 threshold).** Candidate collapses high-confidence predictions from 0.6316 → 0.3739 — identical to the plateau value. This would eliminate the gradient at the top of the isotonic curve and suppress all high-confidence YES postings.

**UNCHANGED from prior cycle.** Candidate is demonstrably worse. DO NOT DEPLOY. A new refit with substantially more live data (n_live >> 1,037) is needed before reconsideration.

---

## 5. State Transitions

| Metric | 2026-06-30 (est) | 2026-07-01 | **2026-07-02** | Direction |
|---|---|---|---|---|
| brier7 | — | 0.0139 | **0.0189** | +0.005 (scope change) |
| ece7 | — | 0.0361 | **0.0382** | +0.002 |
| rho7 | — | 0.83 | **0.9165** | +0.09 (scope change) |
| disp_ratio7 | 1.061 | 0.470 | **0.408** | WORSENING |
| disp_ratio7 d+2 | 1.100 | 0.550 | **0.340** | WORSENING |
| BAND_NO_ENABLED | True | True | **False** | halted (EVOLVE) |
| Bankroll | — | $86.59 | **$76.31** | −$10.28 / −11.9% |

**Alert transitions this cycle:** A1 (disp ratio) persists — 2nd consecutive cycle below 1.10, now worsening. A2 (isotonic) persists unchanged.

---

## 6. Recommendations (report-only; no code edits)

1. **Dispersion edge (A1):** Ratio has dropped for a second consecutive cycle (1.06 → 0.47 → 0.41) and the d+2 slice (live YES) is at 0.34. The edge is not just compressed — it is inverted. The guarded live-refit cron on the VPS should be given visibility on the China cold bias specifically. If the refit cron cannot address city-level temperature bias in the central forecast, a human decision is needed on whether to suspend Chengdu and Beijing from BAND_CITY_ALLOW until the bias is corrected.

2. **Isotonic (A2):** No change recommended. Deployed (2026-06-06) has n_live=0 but is better behaved at grid=1.0. Candidate (2026-06-09, n_live=1,037) must not be deployed. Fresh refit warranted when n_live reaches ~5,000 (estimate: ~2 weeks at current volume).

3. **Bankroll:** At $76.31, just above the charter's $75 weekly floor for $300 capital (25% drawdown = $75). If bankroll drops below $75 before next monitoring cycle, BAND_LIVE should be reviewed per charter rules.

4. **China central forecast bias:** The GEV/MC model's temperature climatology for Beijing and Chengdu is systematically 3–6 C below observed peaks in summer 2026. This is not a calibration issue — it is an input bias. Investigate whether the historical station data cutoff precedes recent warming trends in these cities.
