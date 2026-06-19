# Klaus Calibration & Dispersion Monitor Report
**Date:** 2026-06-19
**Run time:** 2026-06-19T08:03Z
**Snapshot freshness:** data-mirror commit e5f144f (2026-06-19T07:59Z — 4 min old — OK)
**System:** `klaus systemd: active` (from system_status.txt)
**Data window:** 2026-06-14 → 2026-06-18 (5 resolved days) + 2026-06-19 partial (proxy lane)
**s50 dataset:** 32,071 rows across 195 city-days (1-in-50 sample from stwa_pricer_eval_s50.jsonl)

---

## ALERTS

> ### DISPERSION ALERT — FIRES (persistent, 5+ consecutive reports)
> **7d median dispersion ratio = 0.556** (model-implied, n=156 city-days — DECISION-grade).
> This is below the 1.10 floor and **worse** than the last report (2026-06-16: 0.589).
>
> **Model-implied sigma (0.842°C) is 56% of empirical true sigma (1.515°C). The edge premise — that market-implied dispersion exceeds true dispersion — remains inverted. It has been inverted on every day in this 5-day window, with no day printing a ratio above 0.60.**
>
> Report history: 06-13: 0.62 → 06-14: 0.835 (brief partial recovery, did not hold) → 06-16: 0.589 → **06-19: 0.556 (new low)**. The trend is compressing, not recovering.

No other pre-registered alerts fired. Brier (0.0521), ECE (0.032), and rho (0.431) are all clear on their own thresholds — and all three improved vs the prior report.

---

## METHOD NOTE

**No Gamma API access** (this sandbox is blocked by Cloudflare WAF). Resolution proxy: for each city-day, the outcome temperature is the maximum `running_max` observed in POST_PEAK/AT_PEAK pricer rows, which matches what the Chainlink oracle snapshots. Winning bucket = the `(lo, hi)` interval containing that temperature. Bucket sentinels: `lo=-999` (below-all) and `hi=999` (open-top) are excluded from dispersion and midpoint calculations using the filter `lo > -100 and hi < 900`.

**Dispersion methodology (unchanged from 06-16 report):** Implied sigma per city-day is computed from the last PRE_PEAK pricer record per interior bucket. PRE_PEAK-only is critical — POST_PEAK records have p_cal → 0/1 (market has settled), causing implied sigma to collapse to zero. True sigma is computed empirically as `stdev(rmax − mode_mid)` across all 156 resolved city-days, yielding 1.515°C. This matches the prior report's empirical true sigma (1.550°C for the prior window) closely.

**Isotonic files:** Fetched from the `claude/find-lag-parameter-rFQ0N` branch (`config/stwa_isotonic.json` and `config/stwa_isotonic_candidate.json`).

---

## 1. SETTLED LANE

**Coverage:** 32,071 s50-rows across 195 city-days (June 14–18). Full-log estimate: ~1.6M bucket evaluations.

| Metric | Value | Threshold | Status | Prior (2026-06-16) |
|---|---|---|---|---|
| 7d Brier (p_cal) | **0.0521** | >0.15 = ALERT | clear | 0.0707 |
| 7d ECE (p_cal) | **0.0320** | >0.05 = ALERT | clear | 0.0364 |
| Spearman rho | **+0.431** | <0.15 = ALERT | clear | +0.349 |
| Reference Brier (2024-fit) | 0.114 | — | — | — |

All three calibration metrics improved vs the prior report. Brier dropped from 0.0707 to 0.0521 (+26% improvement). Rho improved from 0.35 to 0.43. The calibration *shape* is trending in the right direction.

Per-day Brier (p_cal):

| Date | n rows | Brier |
|---|---|---|
| 2026-06-14 | 6,684 | 0.0518 |
| 2026-06-15 | 6,606 | 0.0524 |
| 2026-06-16 | 7,124 | 0.0633 |
| 2026-06-17 | 6,238 | 0.0447 |
| 2026-06-18 | 5,419 | 0.0458 |

06-16 is elevated (0.0633) but not alarming. 06-17 and 06-18 are the cleanest days.

Model variant comparison (Brier):

| Model | Brier |
|---|---|
| p_mc | **0.0436 (BEST)** |
| p_pa | 0.0447 |
| p_ps | 0.0462 |
| p_gev | 0.0514 |
| p_cal | 0.0521 |

`p_mc` (Monte Carlo ensemble) scores best; `p_cal` (isotonic-calibrated) lags by 0.008 Brier points. The isotonic ceiling artifact (Section 4) likely accounts for most of this gap.

### Reliability Table (p_cal, 10 equal-width bins)

| Bin | n (s50) | est. full-n | conf | acc | delta | Grade |
|---|---|---|---|---|---|---|
| [0.0, 0.1) | 25,094 | 1,254,700 | 0.005 | 0.018 | +0.012 (UNDER) | DECISION |
| [0.1, 0.2) | 1,522 | 76,100 | 0.148 | 0.156 | +0.008 | DECISION |
| [0.2, 0.3) | 812 | 40,600 | 0.250 | 0.121 | -0.130 (OVER) | DECISION |
| [0.3, 0.4) | 3,608 | 180,400 | 0.370 | 0.303 | -0.067 (OVER) | DECISION |
| [0.4, 0.5) | 77 | 3,850 | 0.457 | 0.766 | +0.309 (UNDER) | TREND |
| [0.5, 0.6) | 84 | 4,200 | 0.557 | 0.893 | +0.336 (UNDER) | TREND |
| [0.6, 0.7) | 874 | 43,700 | 0.630 | 0.977 | +0.348 (UNDER) | DECISION |
| [0.7, 1.0) | 0 | — | — | — | — | — |

**Three consistent, decision-grade findings:**

1. **Deep tail [0.0, 0.1) — systematic underestimate of YES.** p_cal=0.005 vs actual=0.018, delta +0.012, n_s50=25,094. This is the dominant bucket by volume and is stably miscalibrated. Persistent across all recent reports. Magnitude similar to 06-16 (+0.021 there), slightly smaller here — marginal improvement.

2. **Shoulder [0.2, 0.4) — systematic overconfidence.** Two adjacent decision-grade bins both over-predict: [0.2,0.3) at -0.130 (n=812) and [0.3,0.4) at -0.067 (n=3608). The isotonic map creates a plateau at ~0.38 for p_raw in [0.25, 0.95], pushing real rates of ~0.12–0.30 to apparent confidence of 0.25–0.37. This is the same finding as the 06-16 report (-0.089 at [0.3,0.4)).

3. **Upper plateau [0.6, 0.7) — extreme underconfidence.** n_s50=874, conf=0.630, actual WIN rate=0.977, delta +0.348. Buckets assigned p_cal ≥ 0.60 have a near-certain empirical resolution rate (97.7%). The model capping out at ~0.63 (isotonic ceiling for the deployed map: p_raw=1.00 → p_cal=0.6316) is the likely cause. Every bucket assigned to this bin should be paying out, and it nearly always does — the model is substantially underselling certainty in the high-confidence range. This is not an ECE alert (it's small by weight) but it is a structurally meaningful price mis-statement.

---

## 2. PROXY LANE (Early Warning — Today, Unsettled)

**Coverage:** 1,976 active PRE_PEAK bucket rows from today's pricer_s50 (2026-06-19, through ~08:00 UTC).

| days_out | n today | n baseline | today med |p_cal−0.5| | base med |p_cal−0.5| | ratio | flag |
|---|---|---|---|---|---|---|
| d+0 | 1,976 | 33,372 | 0.496 | 0.500 | 0.99 | ok |

Today's price distribution (d+0) looks consistent with baseline (ratio 0.99, "ok"). No early-warning spike detected. No pre-registered threshold crossed. Informational only.

---

## 3. DISPERSION GAUGE (Primary Edge Variable)

**Source:** Last PRE_PEAK pricer_s50 snapshot per bucket per city-day (model side only). No market-book data available this session — `stwa_ladder_book.jsonl` not in today's dated subdirectory snapshot; `band_struct_lite.jsonl` fires too sparse this window for the market-corrected computation.

| Quantity | Value | Notes |
|---|---|---|
| Implied sigma (p_cal, median) | **0.842°C** | Weighted std of interior bucket ladder, last PRE_PEAK state |
| Implied sigma (p_cal, mean) | **0.821°C** | Slightly lower than median; no high-sigma outliers |
| Empirical true sigma | **1.515°C** | std(rmax − mode_mid), n=156 city-days |
| Mean signed bias | **+0.321°C** | Warm miss; model persistently underestimates high temps |
| **7d median dispersion ratio (model)** | **0.556** | n=156 city-days — DECISION-grade |
| 7d median dispersion ratio (market-corrected) | n/a | No market quotes available this session |

### DISPERSION ALERT FIRES — WORSENING

**The dispersion ratio has compressed further from 0.589 (06-16) to 0.556 (06-19).** Every individual day in the window is below 0.60:

| Date | n city-days | Median implied σ | Median ratio | True σ |
|---|---|---|---|---|
| 2026-06-14 | 26 | 0.859°C | 0.567 | 1.515°C |
| 2026-06-15 | 32 | 0.895°C | 0.591 | 1.515°C |
| 2026-06-16 | 31 | 0.842°C | 0.556 | 1.515°C |
| 2026-06-17 | 34 | 0.853°C | 0.563 | 1.515°C |
| 2026-06-18 | 33 | 0.812°C | 0.536 | 1.515°C |

No day clears 0.60 on the model-implied side. 06-18 is the worst at 0.536.

### By Region (all DECISION-grade except US at TREND)

| Region | n city-days | Median ratio | Grade |
|---|---|---|---|
| US | 28 | 0.544 | TREND |
| EU | 44 | 0.569 | DECISION |
| ASIA | 84 | 0.575 | DECISION |

No region clears 1.10. ASIA is least-compressed but still at 0.58. All three regions show the same qualitative finding.

### What This Means

The band is selling implied temperature dispersion of ~0.84°C when realized dispersion is ~1.52°C. The theoretical edge is `(implied > true) → collect premium`. That sign is inverted. The band is *underpricing* dispersion vs the true outcome distribution, selling cheap and buying expensive relative to what resolves. This is not a measurement artifact — it persists across 5 consecutive resolved days, at decision-grade sample size (n=156), using two different agent sessions and a consistent methodology.

One structural contributor: the isotonic ceiling artifact (Section 4) caps high-confidence buckets at p_cal ≈ 0.38 when they should be closer to 1.0. This mechanically compresses the tails of the p_cal distribution → lower implied sigma. The stalled cron (Section 4) is preventing the candidate map (which partially corrects this) from reaching production.

---

## 4. ISOTONIC STALENESS

**Deployed:** `config/stwa_isotonic.json` — refit 2026-06-06T22:27Z (**12 days old**)
**Candidate:** `config/stwa_isotonic_candidate.json` — refit 2026-06-09T09:30Z (**9 days old, UNCHANGED since 06-16 report**)

The candidate file is byte-identical to the version read in the 06-16 report. The live-refit cron has produced **zero new candidates in the 10 days since 2026-06-09**. This cron is stalled. It is not generating new refits.

### Delta Table: Deployed vs Candidate

| p_raw | Deployed p_cal | Candidate p_cal | Delta |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.0175 |
| 0.05 | 0.0695 | 0.0758 | +0.0063 |
| 0.10 | 0.1340 | 0.1408 | +0.0068 |
| 0.15 | 0.1828 | 0.1828 | 0.0000 |
| 0.20 | 0.2663 | 0.2588 | -0.0075 |
| 0.25–0.95 | 0.3557–0.3822 | 0.3535–0.3739 | ~-0.006 |
| **1.00** | **0.6316** | **0.3739** | **-0.258 MATERIAL** |

Max absolute delta: **0.258 at p_raw=1.00.**

The deployed map sends p_raw=1.00 → p_cal=0.6316. The candidate map sends it → 0.3739. Both are severely below the empirical true rate of ~0.977 in the [0.6, 0.7) bin (Section 1). The candidate correction moves in the wrong direction at the extreme (reducing the ceiling further, from 0.63 to 0.37), but even the deployed ceiling is massively under-true.

**The stalled cron is the more urgent issue.** Without new live-data refits, the calibration map will continue diverging from the current data distribution. No SSH access from this sandbox to diagnose the cron directly — this is an observation-only flag.

---

## 5. STATE TRANSITIONS

| Metric | Today (06-19) | Prior (06-16) | Change |
|---|---|---|---|
| Brier7 | **0.0521** | 0.0707 | improved ↑ |
| ECE7 | **0.0320** | 0.0364 | improved ↑ |
| Rho7 | **+0.431** | +0.349 | improved ↑ |
| Dispersion ratio (model) | **0.556** | 0.589 | worse ↓ |
| True sigma | 1.515°C | 1.550°C | stable |
| Warm bias | +0.321°C | +0.307°C | stable |
| Isotonic candidate age | **9 days, unchanged** | 7 days | still stalled |
| Alerts | **1 (Dispersion)** | 1 (Dispersion) | persistent, deepening |

**Summary:** Calibration shape (Brier/ECE/rho) improved across the board — the model is scoring better against outcomes than two days ago. That's a positive signal but it doesn't change the load-bearing finding: the dispersion edge is absent and worsening. The model assigns a tighter distribution than what resolves in temperature outcomes, on every day, across all regions, at decision-grade sample size. Combined with a stalled isotonic-refit cron (10 days, no new candidate), the bot is trading on an aging calibration map against a market it is under-dispersing.

**The dispersion ratio needs to be above 1.10 for the edge premise to hold. It is at 0.556 and declining. The edge is not there.**

---

*State written to logs/calib_monitor_state.json*
*REPORT-ONLY: no code, config, or strategy edits made or recommended by this agent.*
