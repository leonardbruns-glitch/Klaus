# Klaus Calibration & Dispersion Monitor
**Date**: 2026-06-27  
**Snapshot**: 2026-06-27T07:54:29Z (age: ~0h, within 6h gate)  
**Service**: active (restarted 2026-06-26T15:08:30Z after ~33h outage)  
**Bankroll**: $57.12 (prior report: $198.28 — large discrepancy; prior report was taken while service was failed, that figure may have been stale/unreliable)  
**Data coverage**: pricer_eval_s50 available for 2026-06-22 through 2026-06-27; 28,166 total rows across 6 days  

---

## S1 — SETTLED LANE

Resolution inferred via `phase == POST_PEAK` and `running_max` sentinel logic (lo=-999 / hi=999 for tail buckets). No explicit `outcome` / `winner` field exists in `stwa_pricer_eval_s50.jsonl`.

| Metric | Value | Alert threshold | Status |
|---|---|---|---|
| Brier7 | **0.054** | >0.15 | OK |
| ECE7 (10 bins) | **0.015** | >0.05 | OK |
| rho7 (Spearman) | **0.433** | <0.15 | OK |
| n_resolved | 1,470 rows / 149 city-days | — | decision-grade (>100) |

**Interpretation**: Calibration is healthy. Brier of 0.054 is significantly better than the 0.114 reference (2024-fit isotonic, flat-sigma). ECE of 0.015 indicates minimal systematic under/over-shooting. Rank correlation of 0.433 is well above the 0.15 floor, confirming p_cal carries genuine information. No settled-lane alerts fire.

Note: 18 city-days were excluded from the settled lane computation (captured only in POST_PEAK with no PRE_PEAK snapshots to establish model predictions before resolution).

---

## S2 — PROXY LANE

**CANNOT COMPUTE.** The `book_mid` / `market_mid` field is absent from all pricer_eval_s50 rows in all six available daily files. The schema carries only model-side quantities (`p_mc`, `p_gev`, `p_pa`, `p_ps`, `p_cal`, `phase`, `running_max`, `t_close`). No market quote is logged in the pricer shadow.

As a partial substitute, p_cal statistics by market phase:

| Phase | n | Median p_cal | Mean p_cal |
|---|---|---|---|
| PRE_PEAK | 3,365 | 0.011 | 0.108 |
| AT_PEAK | 312 | 0.000 | 0.070 |
| POST_PEAK | 2,022 | 0.000 | 0.067 |

The drop in mean p_cal from PRE_PEAK → POST/AT_PEAK is consistent with markets distributing across buckets once the outcome is near-certain. No divergence anomaly detectable without market price data.

**Action**: The proxy lane requires logging `book_mid` (best_bid + best_ask)/2 at each pricer eval snapshot. Absent for at least two consecutive report cycles. Recommend adding `book_mid` to the pricer shadow logger (report-only; not a code edit by this agent).

---

## S3 — DISPERSION GAUGE ⚠️ ALERT

**This is the load-bearing metric. The alert fires.**

Resolution source: same as S1 (POST_PEAK running_max inference, 1-in-50 row sample).  
Implied width computed from: p_cal-weighted std of bucket midpoint distribution per city-day.  
Realized width computed from: |resolved_bucket_midpoint – market-mode_bucket_midpoint| for city-days where mode ≠ resolved (n=59; the 71 city-days where mode == resolved bucket are excluded per spec).

| Metric | Value |
|---|---|
| n city-days resolved | 130 |
| n city-days with nonzero realized width | 59 |
| implied_std 7d median | **0.84°C** |
| realized_abs 7d median (miss-only) | **1.00°C** |
| **ratio_7d_median** | **0.75** |
| alert threshold | <1.10 |
| **ALERT FIRES** | **YES** |

**By region:**

| Region | n city-days (nonzero) | median ratio |
|---|---|---|
| US | 12 | **0.65** |
| EU | 18 | **0.80** |
| Asia | 29 | **0.79** |

**What this means for the edge**: The model's probability distribution is systematically narrower than the realized spread when it misses. Implied_std of 0.84°C is 16% below the 1.00°C median realized error. For the band strategy to harvest a dispersion premium, the market-implied distribution must exceed true realized sigma (~1.3°C per 2026-06 validation). The current measurement, using p_cal as the implied-distribution proxy, shows the opposite — the model is overconfident about which bucket wins.

**Critical caveat**: implied_std is measured from p_cal, not from market ask prices. Due to the isotonic plateau collapse (see S4), p_cal is clamped to ~0.38 for all raw model probabilities in the 0.30–0.90 range. This makes the p_cal distribution artificially flat in the mid-range, potentially understating implied_std. The true market-implied spread (from book asks) is not measurable from current data. A ratio of 0.75 from model probabilities is a finding that warrants tracking; it is not safe to dismiss.

**Trend**: First real measurement (prior report: None). No trend direction available.

**Partial cross-check from band_struct_lite fire records** (±2 bucket window, 2026-06-26/27):
- Chengdu d+1: 1.265°C, Munich d+2: 0.900°C, Wuhan d+2: 0.816°C, Beijing d+2: 0.816°C, Chengdu d+2: 1.115°C
- Median from band window: **0.900°C** — broadly consistent with s50 estimate of 0.84°C
- Both below the ~1.3°C true realized sigma benchmark, consistent with the alert

---

## S4 — ISOTONIC STALENESS

### Deployed (`config/stwa_isotonic.json`, refit 2026-06-06, age: 21 days)

`near_identity_maxdev = 0.568` (expected <0.05 for a functional calibration map).

Plateau: grid 0.30–0.90 all map to p_cal = 0.3801 (13 of 21 grid points identical). Grid 1.00 → 0.6316 (single non-plateau high-end anchor).

### Candidate (`config/stwa_isotonic_candidate.json`, refit 2026-06-09, age: 18 days, n_live=1,037)

`near_identity_maxdev = 0.626` — structurally worse than deployed.

| grid | deployed | candidate | delta | flag |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 | |
| 0.05–0.10 | 0.069–0.134 | 0.076–0.141 | +0.006–0.007 | |
| 0.15 | 0.1828 | 0.1828 | 0.000 | |
| 0.20–0.25 | 0.266–0.356 | 0.259–0.354 | −0.008–0.002 | |
| 0.30–0.95 | 0.3801 | 0.3739 | −0.006 | plateau |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **MATERIAL *** |

Material shift alert fires: grid=1.0 delta=−0.258 exceeds ±0.05 threshold. Unchanged from prior report.

**Direction of shift**: Candidate would LOWER p_cal for near-certain events by 0.258. It removes the only non-plateau anchor (0.6316 at grid=1.0), collapsing everything with p_model > 0.30 to p_cal ≈ 0.37. This makes the candidate strictly worse than the deployed map.

**Structural root cause**: Both maps reflect a training corpus dominated by NO outcomes. Few YES resolutions exist with high model probability, so isotonic regression cannot fit the upper probability range, producing the plateau. A new refit with balanced YES/NO outcomes or with explicit regularization is required.

**Do NOT deploy the candidate.**

---

## S5 — STATE & TRANSITIONS

| Field | Prior (2026-06-26) | Today (2026-06-27) | Change |
|---|---|---|---|
| service_status | failed | **active** | restored |
| brier7 | null | 0.054 | first measurement |
| ece7 | null | 0.015 | first measurement |
| rho7 | null | 0.433 | first measurement |
| disp_ratio7 | null | **0.75** | first measurement, ALERT |
| n_resolved | 0 | 1,470 | resolved data available |
| bankroll | $198.28 | $57.12 | discrepancy (prior stale?) |

---

## ALERTS

### ⚠️ ALERT 1 (NEW): DISPERSION RATIO < 1.10 — EDGE VARIABLE UNVALIDATED
- **Fired**: 2026-06-27 (first measurement)
- **Value**: ratio_7d_median = 0.75 (threshold ≥ 1.10)
- **Regions**: US=0.65, EU=0.80, Asia=0.79 — all below threshold
- **Risk**: The band strategy's load-bearing assumption (market-implied dispersion > true realized) is not confirmed by model-implied metrics. The model is systematically overconfident (implied_std=0.84°C < realized_error=1.00°C in miss cases).
- **Caveat**: Measurement uses p_cal not book ask prices. Book-price-based ratio unavailable until `book_mid` is logged in the pricer shadow.
- **Recommendation (report-only)**: Log `book_mid` to obtain a direct market-implied dispersion measurement before concluding edge is compromised. Do not alter band parameters on this signal alone.

### ℹ️ ALERT 2 (PERSISTS): ISOTONIC MATERIAL SHIFT AT GRID=1.0
- **Fired**: 2026-06-26 (persists unchanged)
- **Value**: grid=1.0 delta=−0.258 (candidate vs deployed)
- **Status**: Candidate unchanged (last refit 2026-06-09, 18 days ago). Structural plateau persists in both maps.
- **Do NOT deploy candidate.**

---

*Report generated by calib-agent@klaus. REPORT-ONLY: no code or config edits were made.*
