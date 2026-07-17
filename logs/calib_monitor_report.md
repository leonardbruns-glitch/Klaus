# Calibration & Dispersion Monitor — 2026-07-17

**Run:** 2026-07-17T08:21Z | **Snapshot:** 2026-07-17T08:09Z (12 min old — OK)  
**System:** `active` | Bankroll: $31.76 | Open positions: 0 | Band: DARK (day 11)  
**Data access:** DIRECT (curl to raw.githubusercontent.com) — pricer_s50 downloaded successfully  
**Prior state:** 2026-07-16 — brier7=0.053(carry), disp_ratio=0.765(n=68,trend-grade), 2 alerts

---

## SECTION 1 — SETTLED LANE (confirmed resolution labels)

> **CAVEAT (pre-registered limitation):** No ground-truth resolution labels are accessible in this environment. Outcomes below are INFERRED from POST_PEAK price convergence (highest final p_cal per city-market is treated as winner). This creates partial circularity. Metrics are proxy-grade, not alert-grade on their own. Alert thresholds suppressed for this section unless the proxy is clearly directional.

**Method:** 4 resolved dates (2026-07-12..2026-07-15); last-snapshot per (city, bucket) in pricer_s50 (1-in-50 sample); winner = bucket with highest POST_PEAK p_cal; Brier and ECE computed across all city-bucket pairs.

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Brier7 (proxy) | **0.0200** | >0.15 = alert | OK — but proxy is too optimistic (see note) |
| ECE7 (proxy) | **0.0448** | >0.05 = alert | Below threshold — but n is sparse in key bins |
| Rank rho7 (proxy) | **0.8343** | <0.15 = alert | OK — circular, not independent |

**Structural finding — isotonic plateau collapse:** The deployed isotonic maps ALL p_raw in [0.30, 0.95] → p_cal = 0.3801 (a flat plateau covering 65% of the probability range). This means the model has zero discriminative power between a 30% and 90% raw-probability prediction. In the ECE bins: the [0.3–0.4) bin has pred=0.375, obs=0.650 (n=20 sampled rows) — the model is severely underconfident for these "plateau" rows. The winner p_cal=0.380 pattern in worst-performing cities (Buenos Aires, Karachi, Manila) confirms this: the model knew these were winners but could only assign 38% because the isotonic maps them all to the plateau. This is the dominant calibration pathology and deserves a direct fix.

**Per-date Brier (proxy):**
- 2026-07-12: Brier=0.022, n=321 rows, 37 cities
- 2026-07-13: Brier=0.020, n=307 rows, 35 cities  
- 2026-07-14: Brier=0.020, n=327 rows, 37 cities
- 2026-07-15: Brier=0.019, n=337 rows, 38 cities

No alert fires (proxy Brier well below 0.15). ECE below 0.05. No settled-lane alerts.

---

## SECTION 2 — PROXY LANE (early warning, p_cal vs mid divergence)

**Market mid not available in pricer_s50 schema** (schema: city, lo, hi, p_mc, p_gev, p_pa, p_ps, p_cal, running_max, t_close, phase, ts — no book prices). Direct |p_cal − mid| computation is not possible.

**Alternative proxy — p_cal stability check:** Median p_cal and distribution shape are stable across the 5-day window. No anomalous spikes in %nonzero or %high-confidence rows. The distribution is uniformly sparse (median p_cal ≈ 0 across all dates, as expected for per-bucket rows in 9-20 bucket markets).

| Date | n rows | %non-zero | %high-conf (>0.50) |
|---|---|---|---|
| 2026-07-12 | 7,486 | 33.7% | 2.6% |
| 2026-07-13 | 6,454 | 35.1% | 2.0% |
| 2026-07-14 | 7,202 | 36.2% | 2.3% |
| 2026-07-15 | 7,501 | 34.0% | 2.6% |
| 2026-07-16 | 7,455 | 33.3% | 3.0% |

Distribution stable. No divergence spike detected. Early-warning note: slight increase in %high-conf on 07-16 (3.0% vs 2.0–2.6% prior days) — one day, not a trend, watch.

---

## SECTION 3 — DISPERSION GAUGE ⚠️ ALERT ACTIVE

> **This is the most important section.** The band edge rests on market-implied dispersion exceeding true dispersion (true sigma ~1.3°C). This gauge monitors whether that edge holds.

**Method:** band_struct_lite `md_shadow` records where `reason=converged` (fire rows). For each: `sigma_implied = 1°C / (2√2 × erfinv(mode_ask))`. Ratio = sigma_implied / 1.3°C.

**7-day result (2026-07-12..2026-07-16, n=110):**

| Metric | Value | Threshold | Status |
|---|---|---|---|
| **7d median disp_ratio** | **0.704** | <1.10 = ALERT | 🚨 ALERT |
| % rows below 1.10 | 100.0% | — | All inverted |
| % rows below 1.00 | 99.1% | — | Near-total inversion |
| n fire rows | 110 | 100 = decision-grade | **DECISION-GRADE** |

**This is the first session with n≥100 (decision-grade).** Prior sessions were trend-grade (n=68).

**The edge is inverted. Market-implied sigma < true sigma 1.3°C on virtually every observed market.** The band harvests the spread between implied and true dispersion; with implied < true, the band is buying into mis-priced narrow confidence — paying for frequency the market hasn't inflated.

**Trend (daily medians):**
| Date | n fire | Median ratio |
|---|---|---|
| 2026-07-12 | 21 | 0.765 |
| 2026-07-13 | 25 | 0.686 |
| 2026-07-14 | 25 | 0.714 |
| 2026-07-15 | 21 | 0.652 |
| 2026-07-16 | 18 | 0.704 |
| **7d median** | **110** | **0.704** |

Trend: no recovery signal. Values oscillate in 0.65–0.77 range, all far below 1.10 threshold. Prior session carried 0.765 (n=68, trend-grade); fresh 5-day measurement 0.704 (n=110, decision-grade) — **worsening**.

**By region:**
| Region | n | Median ratio |
|---|---|---|
| EU | 22 | 0.628 |
| Asia | 65 | 0.714 |
| Other (Americas etc.) | 23 | 0.733 |

EU is the weakest region. Asia is the most active (65 of 110 fire rows).

**By days-out:**
| days_out | n | Median ratio |
|---|---|---|
| d+0 | 82 | 0.744 |
| d+1 | 18 | 0.635 |
| d+2 | 10 | 0.594 |

d+1 and d+2 markets are even more inverted. The band's multi-day positions face the largest inversion in the forward curve.

**Mode-ask distribution across all fire rows:**
min=0.275, p10=0.350, median=0.415, p90=0.535, max=0.725

Mode_ask=0.415 → sigma_implied ≈ 0.88°C (vs true 1.3°C → ratio 0.677). Mode_ask=0.725 → sigma_implied ≈ 0.44°C (ratio 0.34 — severely inverted).

**Inversion day count: 15 consecutive days** (prior state had 14, +1 today). No recovery signal.

**ALERT S3-d15: disp_ratio7=0.704 < 1.10 — INVERTED DISPERSION EDGE — 15th consecutive day — DECISION-GRADE (n=110) — no recovery signal — EU=0.628 Asia=0.714 d+1=0.635 d+2=0.594 — trend WORSENING vs prior (0.765→0.704)**

---

## SECTION 4 — ISOTONIC STALENESS ⚠️ ALERT ACTIVE

| | Deployed | Candidate |
|---|---|---|
| Fit date | 2026-06-06 | 2026-06-09 |
| Days since refit | **41d** | 38d |
| n_live | 0 | 1,037 |
| live_calendar_days | 0 | 2 |
| OOS brier | null | null |

**Material difference >0.05:** 1 (at p_raw=1.0 only)  
**Max |diff|:** 0.2577 at p_raw=1.0 (deployed=0.6316, candidate=0.3739)

**Direction:** Candidate REMOVES the certainty spike at p_raw=1.0 (0.6316→0.3739) and adds a small floor at p_raw=0 (+0.0175). Plateau shift: −0.0062 (0.3801→0.3739, minimal).

**Structural observation:** BOTH deployed and candidate maintain a flat plateau mapping all p_raw∈[0.30, 0.95] → p_cal≈0.38. This means neither curve resolves the dominant calibration pathology (loss of discrimination across 65% of the probability range). The candidate's main change is removing the spike at p_raw=1.0, not fixing the plateau. This is a meaningful but narrow change.

**OOS validation status:** Neither deployed nor candidate has OOS brier validation (brier_live_oos_raw/cal both null). Deploying the candidate would substitute one unvalidated curve for another. The plateau collapse needs a full re-fit with more live data, not just a curve swap.

**ALERT S4: deployed isotonic 41d old (refit 2026-06-06), no OOS validation, max diff 0.2577 — candidate removes p_raw=1.0 certainty spike — recommend collecting OOS labels before any swap — plateau collapse [0.30-0.95]→0.38 persists in both curves**

---

## SECTION 5 — STATE

**Alerts this run:** 2 (S3, S4 — same as prior session; S3 upgraded to decision-grade)

**Transitions from 2026-07-16:**
- S3: persistent (d14→d15); disp_ratio upgraded 0.765(n=68,trend) → 0.704(n=110,**decision-grade**); value worsening
- S4: persistent; deployed now 41d old (was 40d); no new OOS data
- Brier7: carried 0.053 (multi-session stale) → fresh proxy 0.0200 (4d, inferred outcomes, proxy-grade not alert-grade)
- ECE7: null (prior) → 0.0448 proxy (below 0.05 threshold, no alert)
- Rho7: null (prior) → 0.8343 proxy (circular, above 0.15 floor)
- Band: dark day 10 → dark day 11 (BAND_LIVE=False since 2026-07-06)
- Disk: 96% full, 4GB remaining — **approaching critical**; note for VPS operator

**Recommendations (report only — live-refit cron governs deployment):**
1. **Dispersion edge:** The decision-grade inversion (n=110, 15d) means the band's core assumption is demonstrably wrong in current market conditions. If band were live, a market-regime review would be mandatory before re-activation. The band is correctly dark; this is the right posture.
2. **Isotonic plateau:** Both curves collapse [0.30, 0.95] → ~0.38. A new isotonic fit with larger live_n and actual OOS brier validation is warranted before any deployment decision.
3. **Disk:** 4GB remaining at 96% used. If large log files are accumulating, rotate or prune before hitting capacity.

---

## ALERTS — Pre-registered fires only

### 🚨 S3-d15 — DISPERSION EDGE DECAYING (DECISION-GRADE)
**disp_ratio7=0.704 < threshold 1.10**  
15th consecutive day of inversion. n=110 (decision-grade, first time). EU=0.628, Asia=0.714. d+1=0.635, d+2=0.594. Value worsened from prior (0.765→0.704). No recovery signal. The band market-making edge against temperature dispersion is not present in current market conditions.

### ⚠️ S4 — ISOTONIC STALENESS
**max_diff=0.2577 at p_raw=1.0; deployed 41d, no OOS validation**  
Candidate removes certainty spike (0.6316→0.3739 at p_raw=1.0). Plateau collapse [0.30-0.95]→0.38 present in both. No OOS brier for either curve. Recommend new full refit + OOS validation before any swap.
