# Calibration & Dispersion Monitor — 2026-07-24

**Run UTC**: 2026-07-24T08:13Z  
**Data window**: 07-18..07-23 settled + 07-24 partial proxy  
**Snapshot**: 2026-07-24T07:59:36Z (14 min old — FRESH)  
**System**: active | Bankroll: $21.495 | BAND_LIVE: False (day 18)

---

## ALERTS (2 firing)

| # | Code | Condition | Value | Threshold | Day |
|---|------|-----------|-------|-----------|-----|
| 1 | **S3** | disp_ratio7 < 1.10 | **0.781** | 1.10 | 22 consecutive |
| 2 | **S4** | Isotonic deployed > 30d stale | **48d** | 30d | cron recovered |

**S3 ESCALATION**: Asia collapsed 1.215→0.743 on 07-23 — last near-neutral region gone. All 3 regions (EU/Asia/US-Other) now below 1.0 for the first time in monitoring period. n~105 crosses decision-grade threshold (≥100 resolved city-days) — inversion is statistically robust, not a small-sample artifact.

---

## Section 1 — Settled Lane (07-23)

**Source**: `data/shadow/2026-07-23/stwa_pricer_eval_s50.jsonl` (1.68 MB, 1-in-50 sample)

| Metric | Today (07-23) | 7d Rolling | Prior 7d | Δ | Alert? |
|--------|--------------|------------|----------|---|--------|
| Brier | 0.0848 | **0.0548** | 0.0545 | +0.0003 | No (< 0.15) |
| ECE | 0.0972 | **0.0277** | 0.0269 | +0.0008 | No (< 0.05) |
| Spearman ρ | 0.0656 | **0.4260** | 0.430 | −0.004 | No (> 0.15) |

**n (07-23)**: ~360 sampled rows (s50 extract)  
**n_carry**: 33,363 (prior 33,003 + 360 fresh)

### Observations

- **Brier**: 07-23 per-day = 0.0848 — third consecutive day above 0.07 (07-21=0.0795, 07-22=0.0784, 07-23=0.0848). Carry-dominated (33,003 vs 360); 7d estimate creeps: 0.0542→0.0545→0.0548. No alert but trend building.

- **ECE**: 07-23 per-day = 0.0972 — highest standalone reading in monitoring period. Still below 0.05 aggregate threshold due to carry dilution. Pre-plateau isotonic miscalibration persists.

- **Spearman ρ**: 07-23 standalone = 0.0656 — worst standalone reading in monitoring period. Sequential standalone decline: 07-21=0.303 → 07-22=0.213 → 07-23=0.0656. Carry saves 7d estimate (0.430→0.426) but directional collapse is accelerating. **Flag for next session** — if standalone ρ remains < 0.15, begins dragging 7d estimate toward alert territory within 5–7 sessions.

---

## Section 2 — Proxy Lane (07-24 partial)

**Source**: `data/shadow/2026-07-24/stwa_pricer_eval_s50.jsonl` (531 KB, rows through 08:13 UTC)

| Metric | 07-24 @ 08:13 | 7d Baseline | Divergence | Early Warning? |
|--------|--------------|-------------|------------|----------------|
| Median mode p_cal | 0.3801 | 0.380 | +0.0001 | **No** |
| n cities PRE_PEAK | 27 | — | — | — |
| n sampled rows | 2,369 | — | — | — |

**No early-warning signal.** Plateau dominance continues — median mode p_cal stable at 0.38. Partial-day only (through 08:13 UTC); EU morning session covered. Asia already past PRE_PEAK window. US not yet open.

---

## Section 3 — Dispersion Gauge

### 7d Rolling Summary

| Window | Daily Values (sorted) | Median | n | Grade |
|--------|----------------------|--------|---|-------|
| 07-18..07-23 | [0.485, 0.762, 0.779, 0.783, 0.851, 0.925] | **0.781** | ~105 | **decision-grade** |

**Prior (07-17..07-22)**: median = 0.817 (n~98, trend-grade)  
**Change**: −0.036 | **S3 DAY 22** | n crosses 100 threshold

### Daily Trend

| Date | Daily Median | vs 1.10 | Note |
|------|-------------|---------|------|
| 2026-07-18 | 0.485 | −0.615 | Severe inversion |
| 2026-07-19 | 0.925 | −0.175 | Best recent reading |
| 2026-07-20 | 0.779 | −0.321 | |
| 2026-07-21 | 0.783 | −0.317 | |
| 2026-07-22 | 0.851 | −0.249 | |
| **2026-07-23** | **0.762** | **−0.338** | **Asia collapse** |

0/6 days above 1.10. Second consecutive window with 0/6.

### 07-23 Region Breakdown

| Region | 07-23 Median | Prior (07-22) | Δ | vs 1.10 |
|--------|-------------|--------------|---|---------|
| EU | 0.789 | 0.851 | −0.062 | Inverted |
| Asia | **0.743** | **1.215** | **−0.472** | **COLLAPSED** |
| US/Other | 0.789 | 0.462 | +0.327 | Inverted (improving) |

**Critical**: Asia was the sole region above 1.0 on 07-22 (last buffer). Asia collapse on 07-23 eliminates the final near-neutral region. All 3 regions simultaneously below 1.0 for the first time in the monitoring period.

### Interpretation

The implied volatility spread (market-implied spread > realized spread) has inverted. At decision-grade (n~105), this is now a statistically robust finding, not noise. The edge thesis — that market prices contain excess uncertainty vs realized temperature outcomes — does not hold in the current data window.

**Structural check**: 5-day median excluding 07-18 anomaly: sorted [0.762, 0.779, 0.783, 0.851, 0.925] → median = 0.783. Still sub-1.10. The inversion is not driven by the 07-18 outlier.

---

## Section 4 — Isotonic Calibration Staleness

| | Deployed | Candidate |
|---|---|---|
| Refit UTC | 2026-06-06T22:27:08Z | **2026-07-23T09:30:44Z** |
| Days since refit | **48d** (alert) | 1d |
| n_live | 0 | 3,392 |
| Live calendar days | — | 8 |
| OOS Brier (raw) | — | 0.0637 |
| OOS Brier (cal) | — | 0.0638 |

**Cron status: RECOVERED** — candidate was updated 2026-07-23T09:30:44Z. Prior session feared cron had missed 07-22 (n_live frozen at 3,733). Confirmed recovered: n_live decrease 3,733→3,392 is expected rolloff of older rows from rolling window.

### Calibration Map Diffs (candidate vs deployed)

| p_raw | Deployed | Candidate | Diff | Material? |
|-------|----------|-----------|------|-----------|
| 0.00 | 0.0000 | 0.0042 | +0.0042 | No |
| 0.15 | — | — | +0.0003 | **No** (concern from prior session eliminated) |
| 0.95 | 0.3822 | 0.4374 | **+0.0552** | **Yes** (crossed 0.05 threshold; was 0.0483 prior) |
| 1.00 | 0.6316 | 0.8000 | **+0.1684** | **Yes** |

Material diffs (>0.05): **2** (was 1 prior session)

**Tail behavior**: Candidate maps p_raw=1.0 → 0.8 (appropriate shrinkage). Prior candidate mapped 1.0→1.0 (no shrinkage — corrected). Deployed maps 1.0→0.6316 (heavier shrinkage).

**OOS verdict**: brier_cal (0.0638) ≥ brier_raw (0.0637) — isotonic calibration adds marginal negative OOS value. Stable finding across both candidate versions.

**Promotion recommendation**: NOT recommended. (1) OOS brier_cal ≥ brier_raw; (2) 2 material tail diffs at p_raw=0.95 and 1.0 require human review; (3) Deployed curve 48d stale but tail differences mean promotion changes live behavior at extreme probabilities.

---

## Section 5 — State Summary

| Metric | Current | Prior | Δ | Alert |
|--------|---------|-------|---|-------|
| brier7 | 0.0548 | 0.0545 | +0.0003 | No |
| ece7 | 0.0277 | 0.0269 | +0.0008 | No |
| rho7 | 0.4260 | 0.430 | −0.004 | No |
| disp_ratio7 | **0.781** | 0.817 | **−0.036** | **S3** |
| disp_ratio7_n | ~105 | ~98 | +7 | decision-grade |
| disp_inversion_days | **22** | 21 | +1 | S3 |
| Isotonic deployed age | **48d** | 47d | +1d | S4 |
| BAND_LIVE | False | False | — | — |
| Band dark days | 18 | 17 | +1 | — |
| Bankroll | $21.495 | $21.495 | $0.00 | — |

---

## Rho Trend Flag (no alert, watch)

Standalone Spearman ρ declining sharply: 07-21=0.303 → 07-22=0.213 → 07-23=0.0656. If this continues, 7d estimate will cross 0.15 alert threshold within ~5 sessions (carry n=33,363 diluting ~360/day new). Possible causes: (a) signal rank-ordering degrading as settled markets narrow near resolution; (b) model systematic bias in specific city clusters; (c) coincidental 3-day sample. Monitor next 3 sessions before escalating.

---

*Report generated by calib-monitor routine. REPORT-ONLY — no strategy code or configs modified.*
