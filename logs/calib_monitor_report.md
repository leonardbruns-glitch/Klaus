# Klaus Calibration & Dispersion Monitor Report
**Date:** 2026-06-16
**Run time:** 2026-06-16T08:16Z
**Snapshot freshness:** 2026-06-16T08:00:21Z (16 min old — OK)
**System:** `klaus systemd: active`, 0 open positions, bankroll $236.24
**Data window:** 2026-06-11 → 2026-06-15 (5 resolved days) + 2026-06-16 partial (proxy lane)

---

## ALERTS

> ### DISPERSION ALERT — FIRES (persistent, now 3+ consecutive reports)
> **7d median dispersion ratio = 0.589** (model-implied) / **0.478** (market-corrected, n=80, trend-only).
> Both are below the 1.10 floor — and both are **worse** than the last report (2026-06-14: 0.835 model / 0.710 market-corrected).
>
> **The market/model-implied sigma (~0.96°C / ~0.73°C) is below the true sigma (1.55°C). The edge premise (implied dispersion > true dispersion) remains inverted.** The band sells dispersion premium that, on this evidence, is not there. Edge status: **decaying further, not recovering.**
>
> Trend across reports: 06-13 ratio 0.62 → 06-14 ratio 0.835 (brief partial recovery) → **06-16 ratio 0.589** (the window now includes 06-14 and 06-15, both of which print at 0.50-0.52 individually — the recovery seen on 06-14 did not hold).

No other pre-registered alerts fired (Brier, ECE, rho all clear on their own thresholds).

---

## METHOD NOTE

**No Gamma API access** (Cloudflare WAF returns HTTP 403 to this sandbox, confirmed again this run). Resolution proxy unchanged from prior reports: for each city-day, outcome = the maximum `running_max` observed in `POST_PEAK` pricer rows (the same METAR-observed running high the oracle uses), and the winning bucket is whichever `(lo,hi)` interval contains it. **Bug fix this run:** the top open-ended bucket uses `hi=999` as a sentinel (mirroring the `lo=-999` bottom bucket) — an earlier draft of this run's script only special-cased the bottom sentinel, which corrupted bucket-midpoint math for any city-day whose outcome or mode landed in the top bucket (true_sigma exploded to ~95°C before the fix). Caught via outlier inspection before committing; final numbers below use the corrected midpoint logic for both ends.

**Market-side correction** uses `band_struct_lite.jsonl` "fire" rows (live maker quotes: `lo,hi,ask` per leg) instead of `stwa_ladder_book.jsonl` (not present in this session's data pull — only the files listed in this routine's SETUP block were fetched). This changes the market-corrected sample to city-days where the band actually quoted (n=80, conditioned on `BAND_LIVE` firing), vs the full ladder book in prior reports. Selection bias caveat: city-days with a live band fire are not a random subsample — treat the market-corrected figure as **trend-only (40-99)**, not decision-grade, this run.

---

## 1. SETTLED LANE

**Coverage:** 2,068 deduped (city, date, bucket) s50-rows across 181 city-days (June 11-15, sampled 1-in-50). Full-log estimate: ~103,000 bucket evaluations.

| Metric | Value | Threshold | Status | Prior (2026-06-14) |
|---|---|---|---|---|
| 7d Brier (p_cal) | **0.0707** | >0.15 = ALERT | clear | 0.0682 |
| 7d ECE (p_cal) | **0.0364** | >0.05 = ALERT | clear | 0.0320 |
| Spearman rho | **+0.349** | <0.15 = ALERT | clear | +0.366 |
| Reference Brier (2024-fit) | 0.114 | — | — | — |

Brier, ECE, rho are all stable vs the prior report (within noise). No calibration-shape alert.

### Reliability Table (p_cal, 10 equal-width bins)

| Bin | n (s50) | est. full-n | pred | actual | delta | Grade |
|---|---|---|---|---|---|---|
| [0.0, 0.1) | 1,511 | 75,550 | 0.008 | 0.029 | +0.021 | DECISION |
| [0.1, 0.2) | 137 | 6,850 | 0.144 | 0.197 | +0.053 | DECISION |
| [0.2, 0.3) | 88 | 4,400 | 0.253 | 0.148 | -0.105 | TREND |
| [0.3, 0.4) | 316 | 15,800 | 0.368 | 0.288 | -0.080 | DECISION |
| [0.4, 0.5) | 4 | 200 | 0.451 | 0.500 | +0.049 | COLLECT |
| [0.5, 0.6) | 6 | 300 | 0.549 | 0.500 | -0.049 | COLLECT |
| [0.6, 0.7) | 6 | 300 | 0.630 | 0.500 | -0.130 | COLLECT |

**Two decision-grade findings, consistent with prior report:**

1. **[0.0, 0.1) tail — model still underestimates YES.** p_cal=0.008 vs actual=0.029 (n_s50=1,511, DECISION). Same direction and similar magnitude as last report (+0.019). Persistent, thin tail edge.
2. **[0.3, 0.4) shoulder — model still overconfident.** p_cal=0.368 vs actual=0.288 (n_s50=316, DECISION). The isotonic plateau (see Section 4) pushes mid-confidence buckets to ~0.37-0.38 regardless of true rate; this delta (-0.080) is essentially unchanged from the prior report's -0.089. **This is now a stable, repeated miscalibration across two consecutive decision-grade reports, not noise.**

---

## 2. PROXY LANE (Early Warning — Today, Unsettled)

**Coverage:** 1,778 active PRE_PEAK bucket rows from today's pricer_s50 (2026-06-16, through ~08:00 UTC).
**Market divergence source:** `band_struct_lite.jsonl` "fire" quotes (matched by city + exact bucket + days_out), not the ladder-book archive used previously — **methodology change, not directly comparable to the 06-14 baseline.**

| days_out | n | median \|p_cal − ask\| |
|---|---|---|
| 0 | 299 | 0.1565 |
| 1 | 184 | 0.1450 |
| 2 | 193 | 0.1639 |

No 7d baseline exists for this exact metric (different market-price source than prior reports' `p_cal - p_ps` comparison). Treating this run as the new baseline for this metric going forward. Nothing here crosses a pre-registered threshold — informational only, not an early-warning spike.

---

## 3. DISPERSION GAUGE (Primary Edge Variable)

**Source:** last PRE_PEAK pricer_s50 snapshot per bucket per city-day (model side); last `band_struct_lite` "fire" quote per city-day (market side, n=80 of 181 city-days — only where the band actually quoted).

| Quantity | Value | Notes |
|---|---|---|
| Implied sigma (p_cal, median) | **0.957°C** | Weighted std of bucket ladder, model side |
| Market implied sigma (ask, median) | **0.732°C** | n=80, conditioned on band firing — selection bias caveat above |
| True sigma (std of realized residuals) | **1.550°C** | std of (resolved_mid − mode_mid), n=181 city-days |
| Mean realized residual (bias) | **+0.307°C** | Systematic warm miss, consistent direction with prior report (+0.365) |
| **7d median dispersion ratio (model)** | **0.589** | n=115 city-days with nonzero realized error — DECISION-grade |
| 7d median dispersion ratio (market-corrected) | **0.478** | n=80 — TREND-grade only (selection bias, see Method Note) |

### DISPERSION ALERT FIRES — and has worsened

**Both the model-side and market-side dispersion ratios are below 1.10, and both are lower than the last report.** The market-implied sigma remains below the true sigma in every reading taken since this gauge was introduced. There is still no evidence of a recovered dispersion premium in this window.

### Per-Region (model ratio) — all sub-decision-grade, trend/collect only

| Region | n city-days | Median ratio |
|---|---|---|
| US | 33 (collect) | 0.532 |
| EU | 32 (collect) | 0.597 |
| ASIA | 43 (collect) | 0.631 |

No region clears 1.10. Asia is the least-compressed but still well under threshold; sample sizes are all below the 40-city-day trend floor, so no regional conclusion is decision-grade.

### Day-by-Day Trend (model ratio)

| Date | n city-days | Median ratio | True sigma (day) |
|---|---|---|---|
| 2026-06-11 | 19 | 0.728 | 1.64°C |
| 2026-06-12 | 29 | 0.592 | 1.52°C |
| 2026-06-13 | 20 | 0.667 | 1.36°C |
| 2026-06-14 | 22 | 0.516 | 1.42°C |
| 2026-06-15 | 25 | 0.504 | 1.75°C |

**The 06-14/06-15 readings (0.52, 0.50) are the two lowest in this window.** The brief partial recovery the 06-14 report saw at the start of its window (06-11 at 1.033 in that report's own day-by-day table) has not persisted — every day since has printed below 0.73 here, trending down rather than up. No day in the last 6 has cleared 1.10.

**Recommendation (observe-only):** the dispersion premium the band is built to harvest has now been absent or inverted for at least 6 consecutive resolved days, across two independent agent sessions, two different resolution methodologies, and (this run) a bug-fixed bucket-midpoint calculation. This is not a measurement artifact. `BAND_EV_MIN=0.08` is the only standing defense against firing into a market that is not actually over-dispersed; consider whether that gate alone is sufficient given the persistence of this signal. No config change made or implied by this report.

---

## 4. ISOTONIC STALENESS

**Deployed:** `config/stwa_isotonic.json` (refit 2026-06-06T22:27Z)
**Candidate:** `config/stwa_isotonic_candidate.json` (refit 2026-06-09T09:30Z, n_live=1037, 2 calendar days)

**The candidate file is byte-identical to the one read in the 2026-06-14 report.** The live-refit cron has produced *zero* new candidates in the 7 days since 2026-06-09 — up from the "5 days, unusual" flagged last report. This is no longer just unusual; a cron that hasn't fired in a week is stalled, not slow.

| p_raw | Deployed | Candidate | Delta | Direction |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 | UP (NO-target) |
| 0.05 | 0.0695 | 0.0758 | +0.006 | UP |
| 0.10 | 0.1340 | 0.1408 | +0.007 | UP |
| 0.15 | 0.1828 | 0.1828 | 0.000 | — |
| 0.20 | 0.2663 | 0.2588 | -0.008 | DOWN |
| 0.25–0.90 | 0.3557–0.3801 | 0.3535–0.3739 | ~-0.006 | DOWN (plateau tightens) |
| 0.95 | 0.3822 | 0.3739 | -0.008 | DOWN |
| **1.00** | **0.6316** | **0.3739** | **-0.258** | **DOWN — MATERIAL** |

**Max absolute delta: 0.258 at p_raw=1.00, same as last report (unchanged data).** The tail-correction direction (candidate > deployed for p_raw<0.15) still moves the right way given Section 1's finding that the deep tail under-predicts YES — but since the cron is stalled, this correction isn't reaching production regardless of whether it would help.

**This run's note:** the staleness clock is now the more urgent issue than the staleness direction. Recommend (observe-only) checking whether the live-refit cron process is actually running on the VPS — this report cannot SSH to confirm, only observe that its output hasn't changed in a week.

---

## 5. STATE TRANSITIONS

| Metric | Today (06-16) | Prior (06-14) | Change |
|---|---|---|---|
| Brier7 | 0.0707 | 0.0682 | stable |
| ECE7 | 0.0364 | 0.0320 | stable |
| Rho7 | 0.3490 | 0.3660 | stable |
| Dispersion ratio (model) | **0.589** | 0.835 | **worse** |
| Dispersion ratio (market-corrected) | **0.478** | 0.710 | **worse** (methodology also changed — see Method Note) |
| Isotonic candidate age | **7 days, unchanged** | 5 days | stale → stalled |
| Alerts | **1 (Dispersion)** | 1 (Dispersion) | persistent, deepening |

**Calibration shape (Brier/ECE/rho) is stable and not itself a concern.** The load-bearing quantity — dispersion ratio — is the one thing actively moving, and it is moving the wrong way: from an already-failing 0.835 down to 0.589 over two days. Combined with a stalled isotonic-refit cron, the bot is currently running on an aging calibration map against a market that is, on this data, not over-dispersed relative to true outcomes.

---

*State written to logs/calib_monitor_state.json*
*REPORT-ONLY: no code, config, or strategy edits made or recommended.*
