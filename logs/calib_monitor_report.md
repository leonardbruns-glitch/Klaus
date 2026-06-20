# Klaus Calibration & Dispersion Monitor Report
**Date:** 2026-06-20
**Run time:** 2026-06-20T08:10Z
**Snapshot freshness:** data-mirror snapshot_ts 2026-06-20T07:59:16Z — 11 min old — OK
**System:** `klaus systemd: active` (from system_status.txt)
**Data window:** 2026-06-15 → 2026-06-19 (5 resolved days) + 2026-06-20 partial (proxy lane)
**s50 dataset:** 33,359 rows across 175 city-days (1-in-50 sample from stwa_pricer_eval_s50.jsonl)
**Bankroll:** $218.78

---

## ALERTS

> ### DISPERSION ALERT — FIRES (persistent, 6+ consecutive reports)
> **7d median dispersion ratio = 0.584** (model-implied σ / true σ, n=147 city-days — DECISION-grade).
> This is below the 1.10 floor.
>
> **Model-implied sigma (0.854°C) is 58% of empirical true sigma (1.461°C). The edge premise — that market-implied dispersion exceeds true dispersion — remains inverted.**
>
> Report history: 06-13: 0.620 → 06-14: 0.835 (brief partial recovery) → 06-16: 0.589 → 06-19: 0.556 → **06-20: 0.584 (+0.028 vs prior — marginal improvement, first positive move in 4 reports).**
>
> The trend is still below threshold and no recovery is confirmed. One session of marginal improvement is not a signal; the ratio must sustain above 1.10 before any edge declaration.

No other pre-registered alerts fired. Brier (0.0516), ECE (0.0333), and rho (0.419) are all clear.

---

## METHOD NOTE

**No Gamma API access** (sandbox blocked by Cloudflare WAF). Resolution proxy: maximum `running_max` in POST_PEAK/AT_PEAK pricer rows per city-market, matching the Chainlink oracle snapshot behavior. Outcome = final_rm in bucket `(lo, hi)`. Sentinel buckets `lo ≤ -100` and `hi ≥ 900` excluded from dispersion and midpoint calculations.

**Dispersion methodology (unchanged from prior reports):** Implied sigma per city-day uses the LAST PRE_PEAK pricer record per interior bucket (not per snapshot). PRE_PEAK-only is critical — POST_PEAK rows collapse p_cal → 0/1 causing sigma to compress to zero. True sigma = stdev(running_max − mode_mid) across all 147 resolved city-days = 1.461°C, consistent with prior report (1.515°C). This match validates the methodology.

**Brier/ECE/rho:** All rows from resolved markets (including POST_PEAK), n=30,209 s50 rows.

---

## 1. SETTLED LANE

**Coverage:** 30,209 s50-rows across 175 city-days (June 15–19). Full-log estimate: ~1.5M bucket evaluations.

| Metric | Value | Threshold | Status | Prior (2026-06-19) |
|---|---|---|---|---|
| 7d Brier (p_cal) | **0.0516** | >0.15 = ALERT | clear | 0.0521 |
| 7d ECE (p_cal) | **0.0333** | >0.05 = ALERT | clear | 0.0320 |
| Spearman rho | **+0.419** | <0.15 = ALERT | clear | +0.431 |
| Reference Brier (2024-fit) | 0.114 | — | — | — |

All three metrics within normal range. Brier marginally improved (−0.0005). ECE marginally worse (+0.0013) — noise level. Rho marginally lower (−0.012) — noise level. No threshold crossings.

**Model variant Brier:**

| Model | Brier | vs p_cal |
|---|---|---|
| p_mc | **0.0426 (BEST)** | −0.009 |
| p_pa | 0.0444 | −0.007 |
| p_ps | 0.0458 | −0.006 |
| p_gev | 0.0508 | −0.001 |
| p_cal | 0.0516 | — |

`p_mc` (Monte Carlo ensemble) remains the best raw model variant; isotonic calibration adds no value over raw p_mc at current data volume — consistent with prior reports.

### Reliability Table (p_cal, 10 equal-width bins)

| Bin | n (s50) | conf | acc | delta | Grade |
|---|---|---|---|---|---|
| [0.0, 0.1) | 23,702 | 0.006 | 0.019 | −0.013 (UNDER) | DECISION |
| [0.1, 0.2) | 1,362 | 0.145 | 0.139 | +0.007 | DECISION |
| [0.2, 0.3) | 794 | 0.252 | 0.135 | +0.117 (OVER) | DECISION |
| [0.3, 0.4) | 3,384 | 0.369 | 0.289 | +0.080 (OVER) | DECISION |
| [0.4, 0.5) | 81 | 0.458 | 0.778 | −0.319 (UNDER) | TREND |
| [0.5, 0.6) | 87 | 0.558 | 0.885 | −0.327 (UNDER) | TREND |
| [0.6, 0.7) | 799 | 0.629 | 0.975 | −0.346 (UNDER) | DECISION |

**Three persistent, decision-grade calibration findings (all consistent with prior reports):**

1. **Deep tail [0.0, 0.1) — systematic underestimate of YES.** p_cal=0.006 vs actual=0.019, delta −0.013, n_s50=23,702. Dominant bin by volume; stably miscalibrated at the tail. Slightly improved from prior (−0.013 vs prior report's data).

2. **Shoulder [0.2, 0.4) — systematic overconfidence.** Both bins over-predict: [0.2,0.3) at +0.117 (n=794) and [0.3,0.4) at +0.080 (n=3,384). Isotonic plateau at ~0.38 for p_raw in [0.25, 0.95] is the structural cause — unchanged from prior reports.

3. **Upper plateau [0.6, 0.7) — extreme underconfidence.** n_s50=799, conf=0.629, actual=0.975, delta −0.346. Buckets assigned p_cal ≥ 0.60 resolve at 97.5%. Deployed isotonic ceiling (p_raw=1.0 → p_cal=0.6316) creates this structural floor. Essentially identical to Jun 19 finding. Until isotonic is updated, this artifact persists.

---

## 2. PROXY LANE (Early Warning — Today, Unsettled)

**Coverage:** 2,056 active PRE_PEAK bucket rows from today's pricer_s50 (2026-06-20, through ~08:00 UTC).

| Metric | Today | 7d baseline | Ratio | Flag |
|---|---|---|---|---|
| Median \|p_cal − 0.5\| | 0.4911 | 0.4962 | 0.990 | ok |

Today's model confidence distribution is within 1% of the 7d baseline. No early-warning spike. 32 cities active in PRE_PEAK; distribution is normal. Informational only.

---

## 3. DISPERSION GAUGE (Primary Edge Variable)

**Source:** Last PRE_PEAK pricer_s50 record per interior bucket per city-day (model σ only). Market-book σ not available (stwa_ladder_book not in pre-extracted shadow data; band_struct_lite covers only mode±2 legs).

| Quantity | Value | Notes |
|---|---|---|
| Implied sigma (p_cal, median) | **0.854°C** | Last PRE_PEAK per bucket, interior only |
| Implied sigma (p_cal, mean) | **0.823°C** | Consistent with median |
| Empirical true sigma | **1.461°C** | stdev(running_max − mode_mid), n=147 city-days |
| Mean signed bias | **+0.404°C** | Persistent warm miss; model underestimates high-temp events |
| **7d median dispersion ratio** | **0.584** | n=147 city-days — DECISION-grade |
| Prior report ratio | 0.556 | Jun 19 — improvement of +0.028 |

### DISPERSION ALERT — FIRES, marginal improvement from prior low

**7d median ratio = 0.584 < 1.10 → ALERT FIRES.**

The model estimates σ = 0.854°C. True temperature variability is σ = 1.461°C. The model (and by proxy the market) is pricing a distribution 42% narrower than what actually resolves. The edge premise is inverted.

**Trend:** Jun 13: 0.620 → Jun 14: 0.835 → Jun 16: 0.589 → Jun 19: 0.556 (prior low) → **Jun 20: 0.584 (+0.028)**. First improvement in four reports. Not a recovery — the ratio must sustain above 1.10 to declare edge recovery.

**Per region:**

| Region | n | Implied σ | True σ | Ratio |
|---|---|---|---|---|
| EU/Asia | 65 | 0.812°C | 1.276°C | **0.637** |
| US/Americas | 26 | 0.824°C | 1.509°C | 0.546 |
| Other | 56 | 0.923°C | 1.648°C | 0.560 |

EU/Asia has the highest ratio (0.637) — closest to theoretical edge territory, still far from 1.10. US/Americas is the most inverted (0.546).

**Per date (within this 5-day window):**

| Date | n | Implied σ | True σ | Ratio |
|---|---|---|---|---|
| 2026-06-15 | 23 | 0.942°C | 1.936°C | 0.487 |
| 2026-06-16 | 31 | 0.844°C | 1.634°C | 0.516 |
| 2026-06-17 | 35 | 0.812°C | 1.527°C | 0.532 |
| 2026-06-18 | 34 | 0.815°C | 0.985°C | **0.827** |
| 2026-06-19 | 24 | 0.873°C | 1.142°C | **0.765** |

Jun 18 and Jun 19 show markedly higher within-day ratios (0.827, 0.765) driven by lower true σ on those days — actual temperatures were closer to model predictions on those two days. If this reflects a seasonal regime shift (temperatures becoming more predictable in mid-June), it could explain the marginal overall improvement. Sample too small (n<35/day) to confirm.

---

## 4. ISOTONIC STALENESS

| Quantity | Deployed | Candidate |
|---|---|---|
| Refit UTC | 2026-06-06T22:27:08Z | 2026-06-09T09:30:36Z |
| Days since refit | 14 days | 11 days |
| n_hist | 76,617 | 76,617 (same historical base) |
| n_live | 0 | 1,037 (2 calendar days) |
| Ceiling (p_raw=1.0) | **0.6316** | **0.3739** |
| Max diff vs deployed | — | **−0.2577 at p_raw=1.0 (MATERIAL)** |

**Material change detected.** The candidate collapses the isotonic ceiling from 0.63 to 0.37 at p_raw=1.0. For all other grid points (p_raw < 0.95), the two maps agree within 0.009 — effectively identical for the bulk of evaluations.

**Direction analysis:** Given the [0.6, 0.7) reliability finding (97.5% empirical accuracy vs 0.629 modeled), the deployed ceiling is already too low. The candidate ceiling of 0.374 would be even lower — worsening the underconfidence in the highest-confidence bucket. Deploying the candidate as-is would degrade the upper-confidence calibration further.

**Candidate not updated in 11 days** (same as Jun 19 report). The live-refit cron has not incorporated new data beyond the initial 1,037-row live window. Either the refit cron is inactive, or its n_live threshold has not been crossed. Warrants investigation on the VPS.

**Recommendation (report-only):** Do not deploy the candidate. Investigate the refit cron. When the next candidate is generated, it should aim to address the [0.2, 0.4) over-confidence and [0.6, 0.7) under-confidence artifacts, not just incorporate live data naively.

---

## 5. STATE SUMMARY

| Metric | Today (2026-06-20) | Prior (2026-06-19) | Direction |
|---|---|---|---|
| brier7 | 0.0516 | 0.0521 | improved |
| ece7 | 0.0333 | 0.0320 | marginal worse (noise) |
| rho7 | 0.419 | 0.431 | marginal worse (noise) |
| **disp_ratio7** | **0.584** | 0.556 | **improved +0.028** |
| disp_sigma7_median | 0.854°C | 0.842°C | +0.012°C |
| true_sigma | 1.461°C | 1.515°C | −0.054°C |
| mean_bias | +0.404°C | +0.321°C | warm miss slightly larger |
| alerts | DISPERSION_ALERT | DISPERSION_ALERT | persists |

**Alert status:** DISPERSION_ALERT persists for the 7th consecutive report. Brier, ECE, and rho remain clear.

---

## SUMMARY

Calibration is stable. The sole active alert is the dispersion ratio, which has been in alert territory continuously since at least Jun 13. The Jun 20 reading (0.584) is the first improvement in four sessions, driven by lower true σ on Jun 18–19 (temperatures were more predictable those days). The improvement is marginal and the band edge premise remains structurally inverted.

The isotonic candidate is 11 days stale, unchanged since prior report. Do not deploy it — it would worsen the high-confidence calibration artifact.

The warm bias (+0.40°C) is persistent and slightly growing. The model consistently underestimates peak temperatures. This contributes to the inverted dispersion: the model predicts the mode too low, the actual peak is higher, and the realized deviation (true σ) grows.
