# Calibration & Dispersion Monitor — 2026-06-29

**Run time:** 2026-06-29T08:10Z  
**Snapshot:** 2026-06-29T08:04:36Z (6 min old — FRESH)  
**Service:** `klaus systemd: active` since 2026-06-26T15:08:30Z (~2.9 days)  
**Bankroll:** $80.98 (prev $79.75, net +$1.23 in 24h)

---

## PRE-CHECKS

| Check | Result |
|---|---|
| Snapshot age | 6 min — OK |
| Service status | `active` — OK |
| Data-mirror sync | Last push 15 min cadence — fresh |

---

## SECTION 1 — SETTLED LANE (Brier, ECE, rank-rho)

**STATUS: BLOCKED — 5th consecutive cycle without outcome data.**

`pricer_eval_s50.jsonl` schema for 2026-06-27 and 2026-06-28 (both freshly downloaded and verified):

```
keys: city, lo, hi, p_mc, p_gev, p_pa, p_ps, p_cal, running_max, t_close, phase, ts
```

Neither `outcome` nor `book_mid`/`mid` is present in any row across all three available days (06-27: 7,295 rows; 06-28: 7,718 rows; 06-29 partial: 2,648 rows). This is a **structural gap** in the shadow logger — the pricer eval shadow does not capture resolution truth. The settled-lane calibration monitor has been effectively dark since 06-24/25.

**All settled-lane metrics carried forward:**

| Metric | Value | Last Measured | Source |
|---|---|---|---|
| Brier7 | 0.019 | 06-28 (2-day partial window) | carried fwd |
| Brier7 true 7d | 0.054 | 06-27 (n=1,470, full) | last valid |
| ECE7 | 0.041 | 06-26 | carried fwd |
| rho7 | 0.69 | 06-26 | carried fwd |
| n_resolved | 1,751 | 06-28 (2-day partial) | carried fwd |

**ECE trend (watch — not yet alert):** 0.031 (06-25) → 0.041 (06-26). Two-day upward trend. Threshold 0.05. Cannot update.

**rho7 trend (deterioration):** 0.89 (06-25) → 0.69 (06-26). Significant 1-day drop. Cannot update. If degradation has continued, a rho < +0.15 alert may already be warranted but is invisible without outcome data.

**Structural root cause:** The live pricer shadow logger (`stwa_pricer_eval.jsonl`) evaluates model outputs in real time but does not join to resolution truth. The join requires `analysis/weather/band_resolution_join.py` which calls the Gamma API — inaccessible in this sandbox environment. This architecture means the settled-lane monitor will remain blocked every cycle this agent runs.

**Model output stability (06-27 → 06-29, active rows only):**
- p_cal mean: 0.262 → 0.241 → 0.239 (slight downward drift but within noise; 06-29 is morning-only)
- All component models (p_mc, p_gev, p_pa, p_ps) moving together — no single model diverging
- p_cal max = 0.6316 (deployed isotonic grid[1.0] ceiling) seen daily; today: Sao Paulo + Miami POST_PEAK buckets hitting this ceiling

---

## SECTION 2 — PROXY LANE (early warning, unsettled)

**STATUS: PARTIAL — pricer_eval_s50 blocked, but band_struct_lite offers a surrogate.**

`book_mid`/`mid` absent from `pricer_eval_s50` (5th cycle). However, `band_struct_lite` `yes_capture_shadow` records contain both `proxy_ask` (pricer's YES-probability estimate) and `best_ask` / `best_bid` (live book).

**Surrogate proxy from yes_capture_shadow (d+2 only, n≈40 records):**

From 2026-06-28 and 2026-06-29 yes_capture_shadow records across all 5 allowed cities:
- Typical spread: best_bid ≈ 0.01–0.32, best_ask ≈ 0.27–0.39 → mid ≈ 0.15–0.36
- proxy_ask consistently in 0.185–0.215 range (model estimate)
- For liquid buckets (spread < 0.05): |proxy_ask − mid| ≈ 0.005–0.025 → model tracks market closely
- For illiquid buckets (spread > 0.20): mid can be anywhere → large but uninformative divergence

**Interpretation:** Where the d+2 market has genuine two-sided liquidity, the model's proxy_ask is within ≈2.5¢ of market mid. This is stable vs prior cycles.

**Supplementary agent finding (methodology: phase-inferred, not outcome-truth):** An analysis subagent using `yes_capture_shadow` records computed median |proxy_ask − mid| today = **0.025** vs 7d baseline **0.005**. Treat this as a **weak early-warning note only** — the agent may have been comparing different market regimes (liquid vs illiquid d+2 buckets) rather than true divergence. Not a formal proxy alert.

> **Data architecture note (repeating):** book_mid needs to be added to the pricer eval shadow logger output. Until this is fixed, the formal proxy lane remains dark.

---

## SECTION 3 — DISPERSION GAUGE ⚠️ (pre-registered alert — MOST IMPORTANT)

### Methodology this cycle

Gamma API inaccessible (3rd cycle) → realized component still unavailable. Implied width computed from `band_struct_lite.jsonl` fire records (record=fire, live=true). For each fire, bucket midpoints weighted by their ask prices → weighted-mean → weighted-std = implied width in °C.

**New data: 15 fire records (2026-06-28 full day + 2026-06-29 partial, 08:04 UTC)**

| City | Date | d_out | Implied σ | Region |
|---|---|---|---|---|
| London | 06-30 | d+2 | 0.82C | EU |
| Chengdu | 07-01 | d+2 | 0.82C | Asia |
| Wuhan | 07-01 | d+2 | 0.84C | Asia |
| Chengdu | 06-30 | d+1 | 0.77C | Asia |
| Munich | 06-30 | d+1 | 0.93C | EU |
| Wuhan | 06-29 | d+1 | 0.97C | Asia |
| Wuhan | 06-30 | d+1 | 1.06C | Asia |
| Chengdu | 06-30 | d+2 | 1.10C | Asia |
| Beijing | 07-01 | d+2 | 1.10C | Asia |
| Munich | 06-30 | d+2 | 1.11C | EU |
| Beijing | 06-30 | d+1 | 1.13C | Asia |
| Munich | 06-29 | d+1 | 1.16C | EU |
| Munich | 07-01 | d+2 | 1.19C | EU |
| Wuhan | 06-30 | d+2 | 1.20C | Asia |
| Beijing | 06-30 | d+2 | 1.36C | Asia |

**Summary:**

| Metric | Value | Prior (06-28) | Change |
|---|---|---|---|
| Implied σ (7d median) | **1.096C** | 0.90C | **+0.196C** |
| Realized abs (7d median) | 1.00C | 1.00C | none (carried fwd) |
| Implied/Realized ratio | **1.096** | 0.90 | **+0.196** |
| Alert threshold | 1.10 | 1.10 | — |
| Alert status | **⚠️ FIRING** | FIRING | persists (barely) |

**By region:**
- EU (5 records): median 1.114C — above threshold on its own
- Asia (10 records): median 1.079C — just below threshold

### Interpretation

The implied spread is meaningfully higher than last cycle's 0.90C. This is an encouraging signal: the band is posting on markets where prices span wider ladders (reflecting more genuine uncertainty from the book). However:

1. **Ratio is 1.096, 0.004 below the 1.10 alert threshold.** This is razor-thin. With only the Asian sub-median at 1.079, the aggregate doesn't clear.
2. **Realized denominator is stale (3 cycles, Gamma API unavailable).** If realized deviation has increased (model mode predictions less accurate lately), the true ratio may be lower than 1.096.
3. **Structural concern from the validation context:** The initial validation (2026-06) claimed "true sigma ~1.3C < implied." With implied now at 1.096C, the market has clearly compressed — it is now implying *less* than the claimed true sigma (1.3C). If that benchmark holds, implied < true sigma means the edge has **inverted**: the market is under-pricing uncertainty relative to what actually happens. The band would then be paying more for spread than it collects.
4. **EU implied (1.114C) vs Asia (1.079C):** Europe is the stronger sub-region. Asia has the most compression.

**Alert: PERSISTS (⚠️ S3, 8th consecutive day).** Ratio 1.096 < 1.10. Cannot clear without Gamma-joined realized data.

---

## SECTION 4 — ISOTONIC STALENESS

**Deployed:** `config/stwa_isotonic.json`, refit 2026-06-06 (23 days ago)  
**Candidate:** `config/stwa_isotonic_candidate.json`, refit 2026-06-09 (20 days ago)

Last commit touching the candidate: 2026-06-09 squash commit. No cron-generated update has been pushed to this branch since.

### Comparison (candidate − deployed):

| Grid | Deployed p_cal | Candidate p_cal | Δ | Material? |
|---|---|---|---|---|
| 0.00 | 0.000 | 0.018 | +0.018 | No |
| 0.05 | 0.070 | 0.076 | +0.006 | No |
| 0.10 | 0.134 | 0.141 | +0.007 | No |
| 0.15 | 0.183 | 0.183 | 0.000 | No |
| 0.20 | 0.266 | 0.259 | −0.008 | No |
| 0.25 | 0.356 | 0.354 | −0.002 | No |
| 0.30–0.90 | 0.380 (plateau) | 0.374 (plateau) | −0.006 | No |
| 0.95 | 0.382 | 0.374 | −0.008 | No |
| **1.00** | **0.632** | **0.374** | **−0.258** | **YES** |

**Single material shift: grid[1.0], delta = −0.2577.**

The candidate retains the same flat plateau (0.374) all the way to p_model=1.0, eliminating the deployed curve's jump to 0.632 at the top. This removes calibration signal for maximum-confidence model outputs. Today we see live p_cal=0.632 hitting Miami and Sao Paulo POST_PEAK buckets — those would be crushed to 0.374 under the candidate.

The candidate's `near_identity_maxdev` = 0.626 vs deployed's 0.568: the candidate is *further* from identity (more distorting) at the extremes, not less.

**Recommendation: DO NOT DEPLOY candidate (same as prior 5 cycles).** The deployed config's handling of extreme high-probability buckets is superior. Both are stale; a fresh refit with 20+ days of new live data would be valuable if the cron result could be brought into the branch.

**Alert: PERSISTS (⚠️ S4)** — material shift unchanged, candidate unchanged.

---

## SECTION 5 — STATE & TRANSITIONS

### Comparing to prior state (2026-06-28):

| Field | 06-28 state | 06-29 (today) | Transition |
|---|---|---|---|
| Brier7 | 0.019 (cf) | 0.019 (cf) | unchanged |
| ECE7 | 0.041 (cf) | 0.041 (cf) | unchanged |
| rho7 | 0.69 (cf) | 0.69 (cf) | unchanged |
| disp_ratio7 | 0.75 (cf from 06-27) | **1.096** (new calc) | **IMPROVED** |
| implied_std | 0.90C | **1.096C** | **+0.196C** |
| realized_abs | 1.00C (cf) | 1.00C (cf) | unchanged |
| bankroll | $79.75 | **$80.98** | +$1.23 |
| ECE watch | active | active | persists |
| S3 alert | FIRING | **FIRING** (1.096 < 1.10) | persists |
| S4 alert | FIRING | FIRING | persists |

### Dispersion ratio history (7-day):
```
06-24: 0.850  → ALERT (day 5)
06-25: 0.847  → ALERT (day 6)
06-26: null   → bot down, monitoring gap
06-27: 0.750  → ALERT (first recomputed w/ Gamma data)
06-28: 0.750  → ALERT (carried fwd)
06-29: 1.096  → ALERT (still below threshold; implied improved, realized stale)
```

---

## ALERTS (pre-registered only)

### ⚠️ ALERT S3 — DISPERSION RATIO < 1.10 (PERSISTS, 8th day)

> Disp ratio 1.096 < 1.10 threshold (−0.004 margin). Implied σ improved to 1.096C (15 fire records from band_struct_lite, EU=1.11C, Asia=1.08C) but realized component unavailable for 3rd consecutive cycle (Gamma API inaccessible). Alert cannot be cleared without confirmed realized data. Critically: if the original true-sigma baseline of ~1.3C still holds, implied (1.096C) < true sigma — meaning the market has fully compressed the dispersion premium and the edge is structurally absent. Operating on stale realized data is the primary risk here.

### ⚠️ ALERT S4 — ISOTONIC MATERIAL SHIFT (PERSISTS)

> Deployed vs candidate: delta = −0.2577 at grid[1.0]. Candidate collapses p_cal from 0.632 to 0.374 at maximum model confidence. Live system is generating p_cal=0.632 signals today (Miami, Sao Paulo POST_PEAK). Candidate must NOT be deployed. Both configs are 20-23 days stale; no cron-generated update has reached this branch in 20 days.

### ⚠️ DATA GAP — SETTLED & PROXY LANES DARK (5th cycle)

> pricer_eval_s50 lacks `outcome` and `book_mid` fields. Both settled-lane metrics (Brier/ECE/rho) and proxy-lane (|p_cal − mid|) are structurally blocked. ECE trend 0.031 → 0.041 (two measured points, approaching 0.05 threshold) and rho7 deterioration (0.89 → 0.69) cannot be monitored. This gap will persist until the shadow logger is modified to capture resolution truth, or a network path to the Gamma API is established in the monitoring environment.

### WATCH — ECE TRENDING (not yet alert)

> Last two measurements: 0.031 (06-25) → 0.041 (06-26). Threshold 0.05. Trend is toward the threshold. If two more points follow the same slope (+0.01/day), breach would occur in ~1 day of resumed data. Cannot monitor without outcome data.

---

## RECOMMENDATIONS (report-only)

1. **Dispersion gauge**: With ratio at 1.096 (barely below threshold) and realized denominator stale 3 cycles, this monitor cannot distinguish "edge recovered" from "implied improved but realized also increased." Priority fix: establish Gamma API access in monitoring environment or write a VPS-side script that performs the resolution join and pushes result to data-mirror.

2. **Outcome + book_mid logging**: Add `outcome` (at resolution) and book `mid` (at each eval tick) to `stwa_pricer_eval.jsonl`. Until this is done, calibration monitoring is structurally blind for its primary metrics.

3. **Isotonic refit cadence**: The cron refit runs on the VPS but results are not being pushed to `claude/find-lag-parameter-rFQ0N`. The candidate is 20 days stale. If refit results are being written to disk locally on the VPS, they should be synced to data-mirror alongside the other files.

4. **Dispersion edge concern**: If the original ~1.3C true-sigma benchmark is accurate, implied_std at 1.096C means the market is now under-pricing uncertainty. This deserves explicit verification via a fresh realized-vs-implied comparison, not a blind carry-forward.
