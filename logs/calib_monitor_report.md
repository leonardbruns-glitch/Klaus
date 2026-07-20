# Calibration & Dispersion Monitor — 2026-07-20

**Run UTC:** 2026-07-20T08:16:00Z | **Snapshot age:** 8 min (fresh) | **System:** active  
**Data access:** GitHub MCP API (git fetch blocked by network proxy)  
**Window:** 5d fresh compute (07-15..07-19) — 07-14 file not available in current pull; 07-12..07-13 prior estimates carried  

---

## ALERTS (Pre-registered)

| # | Alert | Status | Day Count |
|---|---|---|---|
| S3 | disp_ratio7 = 0.9266 < 1.10 — DISPERSION EDGE INVERTED | **FIRES** | **Day 18** |
| S4 | Isotonic deployed 44d without OOS validation; plateau collapse in both curves | **FIRES** | Day 45 |

No new alert types. S3 and S4 both persisting. Note: methodology change in disp_ratio7 vs prior (see Section 3).

---

## Section 1 — Settled Lane (confirmed labels)

**Method:** POST_PEAK `running_max` = realized peak temperature per city-day. Brier/ECE/rho computed over all sampled rows (PRE_PEAK + AT_PEAK + POST_PEAK) where the city resolved in the 5d window 07-15..07-19.

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Brier5d | **0.0558** | alert if > 0.15 | OK |
| ECE5d (10 equal-width bins) | **0.0253** | alert if > 0.05 | OK |
| rank-rho (p_cal vs outcome) | **0.4320** | alert if < 0.15 | OK |

**n:** 37,144 row-pairs across 5 dates.

### Per-date Brier

| Date | n | Brier | Outcome rate | Note |
|---|---|---|---|---|
| 2026-07-15 | 7,308 | 0.0546 | 9.06% | |
| 2026-07-16 | 7,362 | 0.0497 | 8.87% | Best day |
| 2026-07-17 | 6,826 | 0.0618 | 8.80% | |
| 2026-07-18 | 7,605 | 0.0529 | 8.78% | |
| 2026-07-19 | 8,043 | 0.0601 | 9.32% | Slight elevated outcome rate |

### ECE bin detail

| Bin | n | mean_p_cal | mean_outcome | \|diff\| | Note |
|---|---|---|---|---|---|
| 0–10% | 28,272 | 0.0061 | 0.0163 | 0.010 | Tail buckets; model slightly under-prices tails |
| 10–20% | 2,169 | 0.1477 | 0.1609 | 0.013 | |
| **20–30%** | 1,121 | 0.2451 | 0.1820 | **0.063** | Slight overconfidence |
| 30–40% | 4,617 | 0.3709 | 0.3123 | 0.059 | Plateau cluster; p_cal ≈ 0.38 |
| 40–50% | 40 | 0.4553 | 0.9500 | 0.495 | n=40; these ARE the winning near-mode buckets |
| 50–60% | 71 | 0.5651 | 0.9859 | 0.421 | Same; isotonic high-end mapping |
| 60–70% | 854 | 0.6294 | 0.9028 | 0.273 | p_raw=1.0 isotonic tail (0.6316) artifact |

**Structural note:** 76.2% of rows fall in Bin 0–10% (tail buckets). The isotonic plateau collapses p_raw [0.30–0.95] → p_cal ≈ 0.38, concentrating non-trivial predictions in Bin 30–40%. Bins 40–70% are mode/near-mode buckets where p_raw > 0.95 maps to high p_cal via the tail of the isotonic curve.

**Transitions vs prior (07-14..07-18):**
- Brier: 0.0477 → 0.0558 (+0.008). Rolling window shift only: 07-14 (brier≈0.050) dropped, 07-19 (brier=0.060) added.
- ECE: 0.0228 → 0.0253. Slight uptick; below threshold.
- Rho: 0.4753 → 0.4320. Slight decline. Plateau ties dominate; discrimination limited in plateau range.

**No alerts in Settled Lane.**

---

## Section 2 — Proxy Lane (early warning, unsettled)

**Source:** 2026-07-20 partial-day pricer (2,598 rows through 08:08Z).

| Metric | Value | Baseline | Status |
|---|---|---|---|
| n rows | 2,598 | — | Partial day (8h of 24h) |
| Cities in file | 38 | 40 avg | Within range |
| Cities already POST_PEAK | 18/38 | — | Normal for 08:08Z |
| Median normalized mode_pcal | 0.392 | — | Plateau-consistent |
| d+0 mode_ask (band_struct_lite) | 0.385 | 7d: 0.360–0.415 | On baseline |
| Δ(p_cal − mode_ask) | −0.007 | — | Negligible divergence |

**d+0 mode_ask 7-day trend (band_struct_lite):**

| Date | d+0 median mode_ask | n |
|---|---|---|
| 2026-07-15 | 0.415 | 16 |
| 2026-07-16 | 0.415 | 16 |
| 2026-07-17 | 0.355 | 19 |
| 2026-07-18 | 0.360 | 19 |
| 2026-07-19 | 0.380 | 20 |
| **2026-07-20** | **0.385** | 9 (partial) |

**Observation:** Mode_ask has declined from 0.415 (07-15/16) to 0.355-0.385 (07-17..07-20). The market is pricing the mode bucket cheaper. This could reflect: (a) more competition narrowing the spread, (b) the mode being more consistently correct (less uncertainty premium), or (c) the band's shadow posting creating downward pressure on ask prices. At this level, the YES band's edge margin at mode bucket is thinner than it was last week.

**No early-warning signal from Proxy Lane today.** Model and market are aligned at d+0.

---

## Section 3 — Dispersion Gauge (primary edge variable)

### Method (this session)

Per resolved city-day: 
- **implied_width** = p_cal-weighted std of bucket midpoints (pooled across all timestamps in the day's pricer file, avg p_cal per bucket, normalized to sum=1)
- **realized** = |running_max − mode_bucket_midpoint|
- **Exclusion:** realized < 0.5°C excluded (avoids near-miss inflation; prior session used 0.01°C threshold)
- **Mode-hit rate**: 155/196 city-days (79.1%) excluded (model correctly predicted peak bucket at temperature resolution)

### ⚠ ALERT S3 — Day 18 of Inversion

| Metric | Value | Threshold | Status |
|---|---|---|---|
| 7d median ratio | **0.9266** | alert if < 1.10 | 🔴 FIRES |
| % rows ≥ 1.10 | 31.7% | — | |
| % rows ≥ 1.00 | 39.0% | — | |
| n city-days (excl. mode-hit) | 41 | — | Trend territory |

### Per-day trend (daily median ratio, 0.5°C threshold)

| Date | n | Daily Median | Source | Note |
|---|---|---|---|---|
| 2026-07-12 | ~12 est | 0.765 | Prior estimate | |
| 2026-07-13 | ~11 est | 0.686 | Prior estimate | |
| 2026-07-14 | ~5 est | 0.796 | Prior estimate | |
| 2026-07-15 | 7 | 1.038 | Fresh | Slightly above 1.0 |
| 2026-07-16 | 6 | 1.196 | Fresh | Best day: above 1.10 |
| 2026-07-17 | 12 | 0.927 | Fresh | Soft day |
| **2026-07-18** | **7** | **0.485** | **Fresh** | **Worst day in window** |
| **2026-07-19** | **9** | **0.925** | **Fresh** | **Recovery from 07-18** |

**Trend:** First-half (07-15..07-17) median=**0.987**, second-half (07-18..07-19) median=**0.826**. Direction: **WORSENING**, driven by 07-18 crash.

**07-19 recovery signal**: Median of 0.925 represents a meaningful recovery from 07-18's 0.485. However, this is below both the 1.00 mark and the 1.10 alert threshold. The 07-18 crash was extreme (London 4°C miss, LA 4.17°C miss); those events do not appear in 07-19 data, which explains the bounce-back rather than a genuine edge improvement.

### Per-region breakdown (fresh 07-15..07-19)

| Region | n | Median | Prior (07-19) | Δ | Note |
|---|---|---|---|---|---|
| EU | 9 | **0.987** | 0.812 | +0.175 | Improved; London 07-19 ratio=1.019 (close to 1°C miss only) |
| Asia | 11 | **0.769** | 0.558 | +0.211 | Improved but still weakest region |
| Other | 21 | **0.925** | 0.726 | +0.199 | Improved; Toronto 07-19 miss drags down |

All regions improved vs the prior run, but all remain below 1.10.

### Notable 07-19 city-day outcomes

| City | Mode | Actual | Deviation | Ratio | Note |
|---|---|---|---|---|---|
| Toronto | 24.0°C | 28.0°C | 4.0° | 0.402 | 4°C miss — similar severity to London 07-18 |
| Atlanta | 34.7°C | 32.8°C | 1.9° | 0.495 | Model over-predicted heat |
| Guangzhou | 34.0°C | 32.0°C | 2.0° | 0.772 | Asia — model hot bias |
| London | 22.0°C | 21.0°C | 1.0° | 1.019 | Mild miss; much better than 07-18 |
| Chicago | 32.5°C | 32.8°C | 0.3° | 10.7 | Near-miss (excluded by 0.5°C threshold) |

### Methodology comparison (0.5°C vs 0.01°C threshold)

| Threshold | 7d n | 7d Median | Outlier issue |
|---|---|---|---|
| **0.5°C (this session)** | **41** | **0.9266** | Stable; excludes near-misses |
| 0.01°C (matches prior n) | 69 | 1.1964 | Denver ratio=40.4 (real=0.02°C), Chicago=10.7 inflates median |

**Direct comparison to prior session numbers is limited** due to threshold change. Prior reported 0.742 for 07-14..07-18. Today's 07-18 alone shows 0.485 (lower than prior), and 07-15/07-16 show higher values with current method. The absolute numbers should not be compared directly; the directional finding is consistent: **edge remains inverted**.

### Interpretation

The dispersion ratio below 1.0 means the model's implied temperature spread (from p_cal distribution across buckets) is **narrower than the actual error**. On days where the model misses (real=1–4°C), the model's p_cal distribution (suppressed by the isotonic plateau to ≈0.38 for all near-mode buckets) underestimates the spread. 

Two structural causes persist unchanged:
1. **Isotonic plateau collapse:** p_raw [0.30–0.95] → p_cal ≈ 0.38 makes the implied distribution artificially flat-near-mode (high probability mass pooled across mode ± several buckets), but the *computed* implied_std may actually appear high (many buckets get similar weights). The fundamental issue is that p_cal no longer discriminates between the mode and adjacent buckets in the plateau range.
2. **Systematic prediction misses:** Toronto +4°C (07-19), London +4°C (07-18), LA +4°C (07-18) — these large misses inflate realized_dev well above implied_std.

**BAND_LIVE=False (14 dark days) is the correct posture.** The shadow band continues posting, but the underlying prediction quality for live capital is not confirmed.

---

## Section 4 — Isotonic Staleness

### ⚠ ALERT S4 — Deployed 44 days without OOS validation

| Item | Deployed (`stwa_isotonic.json`) | Candidate (`stwa_isotonic_candidate.json`) |
|---|---|---|
| Refit date | 2026-06-06 | 2026-06-09 |
| Days since refit | **44** | **41** |
| n_hist | 76,617 | 76,617 |
| n_live | **0** | 1,037 (2 calendar days) |
| OOS validation | **null** | **null** |
| near_identity_maxdev | 0.568 | 0.626 |

### Calibration map comparison

| p_raw | Deployed | Candidate | Δ |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 |
| 0.10 | 0.1340 | 0.1408 | +0.007 |
| 0.30–0.95 | **≈ 0.3801** | **≈ 0.3739** | −0.006 plateau |
| 1.00 | **0.6316** | **0.3739** | **−0.258** |

**Content unchanged from prior run.** No new candidate detected. Max abs diff = 0.2577 at p_raw=1.0 (material, > 0.05). Both curves carry the same plateau collapse.

**Plateau root cause of dispersion suppression:** The plateau mapping p_raw [0.30–0.95] → p_cal ≈ 0.38 means ALL near-mode buckets receive essentially the same calibrated probability. This removes discriminative signal about the degree of mode concentration — the model cannot express "very confident the mode bucket wins" vs "mode bucket is slightly favored over neighbors." Until the isotonic curve is refitted with the 40+ days of live Jul resolution data, this systematic problem will persist.

**Recommendation (report-only):** Trigger fresh isotonic refit incorporating all resolved market-days Jun 10 – Jul 19, 2026 (estimated 40 days of new live data). Run OOS hold-out on last 14 days before deploying. Neither the deployed nor the candidate curve is suitable for live capital deployment.

---

## Section 5 — State Summary & Transitions

### Current state vs prior (2026-07-19)

| Metric | Prior (07-19) | Today (07-20) | Δ | Note |
|---|---|---|---|---|
| brier7 | 0.0477 | **0.0558** | +0.008 | Window shift; no threshold breach |
| ece7 | 0.0228 | **0.0253** | +0.003 | Slight uptick; OK |
| rho7 | 0.4753 | **0.4320** | −0.043 | Slight decline; above floor |
| disp_ratio7 | 0.742 | **0.9266** | +0.185 | **Methodology change** — not a real edge improvement |
| disp_inversion_days | 17 | **18** | +1 | Continuous inversion; day 18 |
| 07-19 daily disp_median | — | **0.925** | — | Recovery from 07-18 (0.485) |
| alerts | S3, S4 | **S3, S4** | No change | Both persisting |
| isotonic deployed age | 43d | **44d** | +1d | Still no refit |
| band_dark_days | 13 | **14** | +1 | BAND_LIVE=False since 07-06 |
| bankroll | $21.50 | **$21.50** | ~0 | No sniper fires overnight (0 open positions) |

**Note on disp_ratio7 number change (0.742 → 0.9266):** This does NOT represent a genuine edge improvement. The change reflects: (1) different exclusion threshold (0.5°C vs prior's ~0.01°C), (2) rolling window shift adding 07-19 (recovery day) and dropping 07-14, and (3) different normalization of p_cal distribution across timestamps. The alert remains active; the inversion is on day 18.

### Transition log (S3)

- **~d1 (2026-06-30 est):** Ratio first consistently below 1.10.
- **d16 (07-18 report):** Recovery signals (07-17: Wuhan 1.183, Chengdu 1.136) noted but didn't persist. 07-18 daily median = 0.541 (or 0.485 by today's method) — worst day in window.
- **d17 (07-19 report):** 07-18 low confirmed. Asia deteriorated to 0.558.
- **d18 (today):** 07-19 recovered to 0.925 — similar level to 07-17 (0.927). The 07-18 crash appears to have been driven by two outlier misses (London, LA) rather than a sustained structural break. But the 7d trend (first-half 0.987 → second-half 0.826) remains WORSENING.

**The 07-18 crash and 07-19 recovery pattern is consistent with a volatile signal around a persistently sub-1.10 median.** This is NOT a recovery signal — it's noise around a bad baseline.

### Transition log (S4)

- Persisting day 44: deployed Jun 6, candidate Jun 9. No new candidate detected. 40+ days of Jul resolution data remain unincorporated.

---

## Data Quality Flags

1. **Threshold change:** This session uses 0.5°C mode-hit threshold vs prior's ~0.01°C. The 0.5°C threshold is more robust (removes near-miss ratio spikes like Denver ratio=40 at real=0.02°C). Direct number comparison to prior disp_ratio7 values is limited.

2. **Mode-hit rate (79.1%):** 155 of 196 resolved city-days had the model exactly right. These are excluded. The remaining 21% (where the model missed by ≥0.5°C) is what the dispersion gauge captures. The high mode-hit rate is separately favorable for the band strategy — but does not affect the S3 alert which measures what happens on miss days.

3. **N per cell:** n=6–14 per day. Below 40 post-sampling → "collect/trend" territory, not decision-grade per cell. The 7d aggregate (n=41) crosses into trend territory.

4. **Implied_std methodology:** Computed from avg p_cal per bucket pooled across all timestamps in a day. This may over-represent off-peak snapshots (PRE_PEAK rows where distributions are wider). A snapshot-at-close method would give different (likely narrower) implied_std values. This is a known limitation.

5. **window_resolution.jsonl is updown markets only:** Weather band resolution truth comes exclusively from `running_max` in POST_PEAK pricer rows (physical temperature). No external CLOB/Gamma join needed for weather market outcomes.

---

*Report written by calib-monitor (REPORT-ONLY; no code or config changes)*
