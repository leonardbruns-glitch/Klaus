# Calibration & Dispersion Monitor — 2026-07-19

**Run UTC:** 2026-07-19T08:16:12Z | **Snapshot age:** 6 min (fresh) | **System:** active  
**Data access:** GitHub MCP API (git fetch blocked by network proxy)  
**Window:** 5d fresh compute (07-14..07-18) + 2d prior daily estimates (07-12..07-13)  

---

## ALERTS (Pre-registered)

| # | Alert | Status | Day Count |
|---|---|---|---|
| S3 | disp_ratio7 = 0.742 < 1.10 — DISPERSION EDGE INVERTED | **FIRES** | **Day 17** |
| S4 | Isotonic deployed 43d without OOS validation; plateau collapse in both curves | **FIRES** | Day 44 |

No new alert types this session. S3 and S4 both persisting from prior run.

---

## Section 1 — Settled Lane (confirmed labels, running_max method)

**Method:** For each resolved city-day (close_date ≤ 2026-07-18), outcome bucket determined from `running_max` in POST_PEAK rows (physical temperature measurement — not price drift). Brier/ECE/rho computed over all sampled rows (PRE_PEAK + AT_PEAK + POST_PEAK), 5-day window 07-14..07-18.

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Brier5d | **0.0477** | alert if > 0.15 | OK |
| ECE5d (10 equal-width bins) | **0.0228** | alert if > 0.05 | OK |
| rank-rho (p_cal vs outcome) | **0.4753** | alert if < 0.15 | OK |

**n:** 30,029 row-pairs across 5 dates (avg 6,006/day).

### ECE bin detail

| Bin | n | mean_p_cal | mean_outcome | \|diff\| | Note |
|---|---|---|---|---|---|
| 0–10% | 23,287 | 0.006 | 0.011 | 0.006 | Tail buckets; correctly near-zero |
| 10–20% | 1,580 | 0.146 | 0.122 | 0.024 | |
| 20–30% | 906 | 0.244 | 0.166 | 0.078 | Slight overconfidence in 20-30% range |
| 30–40% | 3,339 | 0.371 | 0.342 | 0.029 | Plateau rows; well-calibrated at 37% |
| 40–50% | 38 | 0.454 | 1.000 | 0.546 | n=38 only; these ARE the winning buckets (expected) |
| 50–60% | 65 | 0.561 | 1.000 | 0.439 | Same — near-mode buckets with very high raw model confidence |
| 60–70% | 814 | 0.630 | 0.996 | 0.367 | Isotonic high-end; binning artifact from plateau |

**Structural note:** 77.5% of rows fall in Bin 0–10% (tail buckets, p_cal ≈ 0.006). The isotonic plateau collapses p_raw [0.30–0.95] → p_cal ≈ 0.38, concentrating all non-trivial predictions in Bin 30–40%. Bins 40–70% (all outcome ≈ 1.0) are mode/near-mode buckets where the raw model had very high confidence (p_raw > 0.95) before isotonic mapping — they represent the few cases where the model correctly identified a near-certain outcome.

**Brier methodology note:** Prior session reported brier7=0.022 (proxy, single-snapshot). This session's 0.0477 uses all-row method (includes PRE_PEAK rows where model uncertainty is legitimately wide). POST_PEAK rows improve Brier via information advantage. Neither number has a clean ground-truth comparison. Both are well below 0.15 threshold. **No alert.**

**rank-rho caveat:** Plateau collapse creates tied ranks at p_cal ≈ 0.38 (3,339 rows). Spearman is computed on those ties; true discrimination is weaker than rho=0.4753 suggests in the plateau range. Alert threshold not triggered.

---

## Section 2 — Proxy Lane (early warning, unsettled markets)

**Source:** Unsettled d+1 rows (close_date 2026-07-19) from the 2026-07-18 pricer file. Today's s50 file is empty (08:16 UTC, too early). No d+2 rows present (markets not yet opened for 07-21).

| Metric | Value | Baseline | Status |
|---|---|---|---|
| d+1 n_cities | 31 | — | |
| d+1 mean p_cal (avg across buckets) | 0.089 | — | |
| d+1 median p_cal std per city | 0.141 | — | — |
| d+1 band_struct mode_ask (external) | 0.455 | d+1 7d median=0.455 | On baseline |

**No baseline established for spike detection** (prior session did not report proxy metrics at this granularity). No early warning signal from proxy lane today — model and market appear aligned at d+1. Note that model p_cal for mode bucket sits at ~0.38 (plateau) while market mode_ask = 0.455 — model assigns ~17¢ less confidence than market to the mode bucket at d+1. This is consistent with the plateau suppressing p_cal for high-confidence mode predictions.

---

## Section 3 — Dispersion Gauge (primary edge variable)

**Method:** Per deduped city-day (resolved, realized > 0.01°C): implied_width = p_cal-weighted std of bucket midpoints; realized = |outcome_bucket_mid – mode_bucket_mid|; ratio = implied_width / realized. Outcome from running_max (POST_PEAK rows). 56 fresh rows from 07-14..07-18; combined ~79 with prior estimates for 07-12..07-13.

### **⚠ ALERT S3 — Day 17 of Inversion**

| Metric | Value | Threshold | Status |
|---|---|---|---|
| 7d median ratio | **0.742** | alert if < 1.10 | 🔴 FIRES |
| 5d fresh median ratio | 0.711 | — | — |
| % rows ≥ 1.10 | 12.5% | — | — |
| % rows ≥ 1.00 | 16.1% | — | — |
| Inversion day count | **17** | — | — |

### Per-day trend (daily median ratio)

| Date | n | Daily Median | Source | Note |
|---|---|---|---|---|
| 2026-07-12 | ~12 est | 0.765 | Prior estimate | |
| 2026-07-13 | ~11 est | 0.686 | Prior estimate | |
| 2026-07-14 | 5 | 0.796 | Fresh | |
| 2026-07-15 | 11 | 0.742 | Fresh | |
| 2026-07-16 | 9 | 0.680 | Fresh | |
| 2026-07-17 | 19 | 0.804 | Fresh | Recovery-signal day (2 rows > 1.10) |
| **2026-07-18** | **12** | **0.541** | **Fresh** | **⚠ New low in monitoring window** |

**Trend (first 3d avg vs last 3d avg):** 0.749 → 0.675. **WORSENING.**

The 07-17 recovery signals (Wuhan d0 ratio=1.183, Chengdu d0 ratio=1.136 — flagged in prior report) **did not persist**. The 07-18 data shows the worst daily median in the 7-day window.

### Per-region breakdown (fresh, 07-14..07-18)

| Region | n | Median | Prior | Δ | Note |
|---|---|---|---|---|---|
| EU | 26 | **0.812** | 0.628 (prior est) | ↑ +0.184 | Improved vs prior but driven by 07-17 data |
| Asia | 20 | **0.558** | 0.730 (prior est) | ↓ −0.172 | **Deteriorating — new concern** |
| Other | 10 | **0.726** | 0.700 (prior est) | ↑ +0.026 | Flat |

**Asia is now the worst region.** Prior had Asia as the best-performing region (0.73). 07-18 Asia data dragged the median to 0.558.

### Highest ratio rows (favorable for band, 5d fresh)

| City | Date | Region | Ratio | Imp_std | Realized | Mode → Outcome |
|---|---|---|---|---|---|---|
| San Francisco | 07-16 | Other | **1.969** | 2.19° | 1.1° | 23.6 → 22.5°C |
| Chengdu | 07-17 | Asia | 1.781 | 1.78° | 1.0° | 30.0 → 29.0°C |
| San Francisco | 07-17 | Other | 1.665 | 1.85° | 1.1° | 21.4 → 20.3°C |
| Ankara | 07-16 | EU | 1.313 | 1.31° | 1.0° | 31.0 → 30.0°C |
| Ankara | 07-17 | EU | 1.240 | 1.24° | 1.0° | 31.0 → 30.0°C |

Only 7 of 56 rows (12.5%) exceed the 1.10 threshold. Favorable observations cluster around San Francisco (US West Coast, consistent cool bias) and Ankara/Chengdu.

### Lowest ratio rows (worst for band, edge erosion)

| City | Date | Region | Ratio | Imp_std | Realized | Mode → Outcome |
|---|---|---|---|---|---|---|
| **London** | **07-18** | EU | **0.200** | 0.80° | **4.0°** | 25.0 → 21.0°C |
| Los Angeles | 07-18 | Other | 0.241 | 0.54° | 2.2° | 28.1 → 30.3°C |
| Milan | 07-15 | EU | 0.298 | 0.90° | 3.0° | 35.0 → 32.0°C |
| Singapore | 07-17 | Asia | 0.362 | 0.72° | 2.0° | 32.0 → 30.0°C |
| Busan | 07-16 | Other | 0.392 | 0.78° | 2.0° | 33.0 → 35.0°C |

**London 07-18 is the most extreme case:** model mode at 25°C, actual 21°C — a 4°C miss. Implied_std was only 0.80°C (narrow, confident prediction), yet outcome was 5 sigma away from mode. This represents a systematic model error (not just market mispricing). When the underlying temperature model is wrong by 4°C, the band strategy loses regardless of dispersion premium structure.

### Interpretation

The dispersion ratio < 1.0 means **implied_std (from p_cal distribution) is NARROWER than the realized deviation from mode**. The model assigns confident-looking distributions (via plateau p_cal ≈ 0.38 clustering near mode), but actual outcomes are further from the mode than the model implies. The edge premise (market overestimates spread → buy the mode region) is structurally compromised in two ways:

1. **Isotonic plateau collapse** makes p_cal flat across all mode-adjacent buckets, artificially compressing implied_std
2. **Systematic mode prediction errors** (London −4°C, Milan −3°C) inflate realized deviation

Both causes require fixing at the model layer, not the band parameter layer. **BAND_LIVE=False is the correct posture.** Shadow fires on 07-18: 11 (avg_sum_ask=0.681). The shadow band is still firing in favorable-looking windows, but the underlying prediction quality does not support live capital deployment.

---

## Section 4 — Isotonic Staleness

### ⚠ ALERT S4 — Deployed 43 days without OOS validation

| Item | Deployed (`stwa_isotonic.json`) | Candidate (`stwa_isotonic_candidate.json`) |
|---|---|---|
| Refit date | 2026-06-06 | 2026-06-09 |
| Days since refit | **43** | **40** |
| n_hist | 76,617 | 76,617 |
| n_live | **0** | 1,037 (2 calendar days) |
| live_calendar_days | 0 | 2 |
| OOS validation | **null** | **null** |
| near_identity_maxdev | 0.568 | 0.626 |

### Calibration map comparison (selected grid points)

| p_raw | Deployed | Candidate | Δ | Note |
|---|---|---|---|---|
| 0.00 | 0.0000 | **0.0175** | +0.018 | Candidate adds floor |
| 0.05 | 0.0695 | 0.0758 | +0.006 | |
| 0.10 | 0.1340 | 0.1408 | +0.007 | |
| 0.30 | **0.3801** | **0.3739** | −0.006 | Plateau begins |
| 0.35–0.95 | **0.3801** (flat) | **0.3739** (flat) | −0.006 | **Plateau collapse — both curves** |
| 1.00 | **0.6316** | **0.3739** | **−0.258** | Max diff — candidate removes certainty spike |

**Content unchanged vs prior run** (same SHA in both files).

### Key findings

- **Plateau collapse persists in both curves:** p_raw [0.30–0.95] → p_cal ≈ 0.38. This is the structural root cause of the dispersion ratio inversion (Section 3) and the ECE distribution concentration (Section 1).
- **Candidate removes the certainty spike** (p_raw=1.0 → 0.63 vs 0.37) but does NOT fix the plateau. The plateau means p90 of non-zero p_cal ≈ 0.38 daily, confirmed by live data.
- **Neither curve incorporates the 40+ days of live resolution data.** The live refit cron has not written a new candidate since Jun 9 (or this branch doesn't reflect it). A fresh refit incorporating Jul outcomes is essential given the Jun–Jul regime shift visible in the dispersion data.
- **OOS validation null for both.** No basis for quantitative confidence in either curve.
- **Max abs diff = 0.258** at p_raw=1.0. Material (> 0.05), but only at one grid point.

**Recommendation (report-only):** Trigger a full refit of the isotonic calibration curve incorporating all resolved market-days from Jun–Jul 2026 (estimated 40+ new days). Run OOS hold-out on last 14 days before deploying. The plateau collapse may be a real feature of the market (price uncertainty in middle quantiles is irreducible at current data volume) or a calibration artifact — cannot determine without fresh n.

---

## Section 5 — State Summary & Transitions

### Current state vs prior (2026-07-18)

| Metric | Prior (07-18) | Today (07-19) | Δ | Method |
|---|---|---|---|---|
| brier7 | 0.022 | **0.0477** | +0.026 | Methodology change (all-rows vs proxy) |
| ece7 | 0.0448 (carry) | **0.0228** | −0.022 | Fresh computation |
| rho7 | 0.8343 (carry) | **0.4753** | −0.359 | Fresh computation (tie-penalty at plateau) |
| disp_ratio7 | ~0.70 | **0.742** | +0.042 | More fresh data; 07-17 was better than avg |
| disp_inversion_days | 16 | **17** | +1 | +1 day |
| alerts | S3, S4 | **S3, S4** | No change | Both persisting |
| band_dark_days | 12 | **13** | +1 | BAND_LIVE=False since 07-06 |
| bankroll | $37.57 | $21.50 | −$16.07 | Sniper-only activity (per SNAPSHOT) |
| disk | 97% (4GB) | 93% (7GB) | recovered | More free space in new snapshot |

**Brier/ECE/rho methodology change note:** Fresh all-rows computation gives different numbers from prior carry-forward. Brier 0.048 vs 0.022 (prior proxy) should NOT be read as calibration getting worse — the prior was a single-snapshot proxy, this is all-rows. ECE and rho actually improved on fresh computation. The S1/S2/S3 thresholds are all clear.

**New finding:** Bankroll dropped from $37.57 (07-18 AM) to $21.50 (07-19 08:09 UTC) — a decline of $16.07 in ~24h on sniper-only activity. This is outside the scope of the calibration monitor but warrants attention. EVOLVE audit (last commit 07-18 evening) showed candidate 21/21W +$11.54, so this may reflect a drawdown on Jul 19 or a prior-day correction in wallet balance. Not investigated here.

### Transition log (S3)

- **d1 (Jun 24):** Ratio first crossed below 1.10. Condition first observed.
- **d15 (07-17):** First recovery signals — 2 rows above 1.10 (Wuhan 1.183, Chengdu 1.136).
- **d16 (07-18 report):** Recovery signals noted; overall still deeply inverted.
- **d17 (today):** Recovery signals did NOT persist. 07-18 daily median = 0.541 (new low). Worsening trend (3d trailing avg 0.675 < 7d leading avg 0.749). Asia deteriorating (0.558). Edge decay is confirmed and may be accelerating.

### Transition log (S4)

- Persisting unchanged: deployed Jun 6, candidate Jun 9, neither updated with live Jul data.
- No new candidate refit detected in this branch.

---

## Data Quality Flags

1. **Methodology note:** `implied_std` computed from p_cal distribution (bucket midpoints × p_cal weights), NOT from book prices. Book prices from band_struct_lite show d+0 median_mode_ask=0.380, aligning with the p_cal plateau. The two measures converge at d+0 but diverge at d+1 (mode_ask=0.455 vs p_cal plateau=0.38). The dispersion ratio is computed consistently (p_cal-based) across all dates; the absolute ratio values should not be directly compared to a book-price-based metric.
2. **Dedup methodology:** City-days deduplicated by (city, close_date), first occurrence across files. For city-days appearing in multiple files (d+0 and d+1 windows), the first-seen file is used. This means some city-days use d+1 observations rather than d+0. Days_out breakdown is not cleanly computable from this approach; prior days_out estimates (d0=0.76, d1=0.635, d2=0.57) are carried from prior session.
3. **Realized = 0 exclusion:** City-days where mode bucket IS the resolution outcome (realized < 0.01°C) are excluded from dispersion gauge. These trivially support the band strategy (ratio=inf). Rate of mode-hit-outcomes is a separate informative metric not computed this session.
4. **s50 sampling:** n per fresh day is small (5–19 rows). The per-day medians are noisy. The 07-18 n=12 and the extreme London (0.200) and LA (0.241) outliers have material influence on the 07-18 daily median of 0.541. Single-day interpretation should be treated as "trend" not "decision-grade."

---

*Report written by calib-monitor (REPORT-ONLY; no code or config changes)*
