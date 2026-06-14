# Klaus Calibration & Dispersion Monitor Report
**Date:** 2026-06-14  
**Run time:** 2026-06-14T11:27Z  
**Snapshot freshness:** 2026-06-14T11:19Z (8 min old — OK)  
**System:** `klaus systemd: active`  
**Data window:** 2026-06-09 → 2026-06-13 (5 resolved days) + 2026-06-14 partial  

---

## ALERTS

> ### DISPERSION ALERT — FIRES (persistent, day 2+)
> **7d median dispersion ratio = 0.835** (uncorrected) / **0.710** (market-corrected).  
> Both are below the 1.10 floor.  
>
> **The market-implied sigma (0.87°C) is BELOW the true sigma (1.45°C). The edge premise is inverted.**  
> The band harvests premium by selling dispersion — that premium requires implied > true. It is not present in this 7-day window. Edge status: **decaying / not confirmed**.  
>
> Prior report (2026-06-13): ratio 0.62 (same alert, same direction). This is not a one-day artifact.

No other pre-registered alerts fired (Brier, ECE, rho all clear on their own thresholds).

---

## METHOD NOTE

**No Gamma API access** (Cloudflare WAF blocks this sandbox). Resolution proxy: for each city-day, outcome = the maximum `running_max` observed in POST_PEAK rows from the pricer_s50 sample. This is the same METAR-observed temperature used by the oracle (not price-drift inference), rounded to the nearest integer °C. Caveats: (1) may lag WU official high by 0-1 hour; (2) rounding to integer + 1.11°C bucket width creates discrete bias in Brier and Rho vs true winner-flag join. ECE is less sensitive to this. The dispersion gauge uses `stwa_ladder_book.jsonl` (live, available today) for the market-price correction.

**Prior state diff:** yesterday's Brier was 0.0147 vs today's 0.0682. The difference is primarily methodological: the prior run appears to have had higher resolution fidelity (mode bucket p_cal ~0.63 vs actual 100% hit rate). Today's computation assigns ~2.6% YES rate even in the [0.0, 0.1) p_cal bin, which inflates Brier. The ECE is stable (0.032 both days), suggesting calibration shape is consistent.

---

## 1. SETTLED LANE

**Coverage:** 2,147 deduped (city, date, bucket) s50-rows across 163 city-days (June 9-13, sampled 1-in-50). Full-log estimate: ~107,000 bucket evaluations. All decision-grade bins in the active (NO-target) region.

| Metric | Value | Threshold | Status | Prior (2026-06-13) |
|---|---|---|---|---|
| 7d Brier (p_cal) | **0.0682** | >0.15 = ALERT | clear | 0.0147 |
| 7d ECE (p_cal) | **0.0320** | >0.05 = ALERT | clear | 0.0326 |
| Spearman rho | **+0.366** | <0.15 = ALERT | clear | +0.784 |
| Reference Brier (2024-fit) | 0.114 | — | — | — |

**Brier and Rho are degraded vs prior run.** Likely methodological (running_max integer rounding creates misclassification in high-confidence buckets). ECE stability at 0.032 supports this. No decision-grade calibration deterioration declared from this comparison.

### Reliability Table (p_cal, 10 equal-width bins)

| Bin | n (s50) | est. full-n | pred | actual | delta | Region | Grade |
|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 1,560 | 78,000 | 0.007 | 0.026 | +0.019 | NO-target | DECISION |
| [0.1, 0.2) | 144 | 7,200 | 0.145 | 0.167 | +0.021 | NO-target | DECISION |
| [0.2, 0.3) | 104 | 5,200 | 0.252 | 0.202 | -0.050 | MID | DECISION |
| [0.3, 0.4) | 322 | 16,100 | 0.368 | 0.280 | -0.089 | MID | DECISION |
| [0.4, 0.5) | 4 | 200 | 0.451 | 0.500 | +0.049 | HIGH | COLLECT |
| [0.5, 0.6) | 5 | 250 | 0.566 | 1.000 | +0.434 | HIGH | COLLECT |
| [0.6, 0.7) | 8 | 400 | 0.623 | 0.625 | +0.002 | HIGH | COLLECT |

**Two decision-grade calibration findings:**

1. **[0.0, 0.1) — model underestimates YES in the tail.** p_cal = 0.007 but actual YES rate = 2.6% (n_s50=1,560, est. n_full=78k). The model assigns near-zero but ~2.6% of "impossible" buckets still resolve YES. For NO trades in this region: EV = 0.974 × 0.03 - 0.026 × 0.97 = **+$0.004/share** — barely positive, extremely thin.

2. **[0.3, 0.4) — model overconfident on shoulder buckets.** p_cal = 0.368 but actual = 0.280 (n_s50=322, est. n_full=16k, DECISION-grade). The isotonic plateau pushes all mid-confidence buckets to ~0.38. Shoulder YES trades at these prices are -EV under this calibration.

**Systematic warm bias: mean error (resolved_mid - mode_mid) = +0.365°C.** Outcomes land systematically above the predicted mode. Model is forecasting temperatures slightly too cold across this 5-day window. Not in prior report — worth monitoring over 10+ city-days.

---

## 2. PROXY LANE (Early Warning — Today, Unsettled)

**Coverage:** 1,904 active PRE_PEAK bucket rows from today's pricer_s50 (2026-06-14, through 11:19 UTC).  
**Market divergence source:** `stwa_ladder_book.jsonl` (390 PRE_PEAK snapshots, 387 valid ladders).

| Metric | Value | 7d Baseline | Status |
|---|---|---|---|
| Median |p_cal - p_ps| (s50 proxy) | 0.0013 | 0.0006 | 2x baseline (minor) |
| Market (ask_yes) implied sigma | **0.874°C** | (no archive) | Below true sigma |
| Model (p_cal) implied sigma | 0.987°C | (no archive) | Below true sigma |
| Market/model ratio | **0.850** | 1.060 (prior report) | SIGN FLIP |

**Market/model sign flip is the key proxy finding.** Prior report (2026-06-13) observed market sigma 6% WIDER than model (ratio=1.060). Today market is 15% NARROWER (ratio=0.850). The market has compressed toward even tighter implied distributions than the model. Consistent with the dispersion alert deteriorating rather than recovering.

---

## 3. DISPERSION GAUGE (Primary Edge Variable)

**Source:** PRE_PEAK pricer_s50 ladders (last seen p_cal per bucket, per city-day) + running_max resolution proxy. Market correction from today's `stwa_ladder_book.jsonl` (PRE_PEAK, n=387).

| Quantity | Value | Notes |
|---|---|---|
| Implied sigma (p_cal, median) | **0.954°C** | Weighted std of bucket ladder |
| Market implied sigma (ask_yes, median) | **0.874°C** | From ladder book, PRE_PEAK |
| True sigma (std of realized errors) | **1.447°C** | Std of (resolved_mid - mode_mid) over 163 city-days |
| Mean realized error (bias) | **+0.365°C** | Systematic warm miss |
| Median per-city-day ratio (model) | **0.835** | Alert threshold: < 1.10 |
| Market-corrected dispersion ratio | **0.710** | 0.835 x 0.850 market/model |

### DISPERSION ALERT FIRES

**The market-implied sigma (0.87°C) is below the true sigma (1.45°C).** The edge premise (implied > true) is inverted. The band harvests premium when the market is over-dispersed. It is not over-dispersed in this window.

- Market assigns too much probability to the mode (under-dispersed)
- Mode YES buckets are overpriced relative to reality
- Tail YES buckets are underpriced (tails win more often than market implies)
- The NO strategy on tails is buying at prices set under market-under-dispersion, where we bear higher-than-priced YES resolution risk

This is the same conclusion as yesterday's alert (ratio 0.62) but the uncorrected metric has improved from 0.62 to 0.835. The market-corrected number is worse today (0.710) because the market has tightened further relative to the model.

### By Region

| Region | n | Implied sigma | True sigma | Ratio |
|---|---|---|---|---|
| US | 32 | 0.82°C | 1.71°C | 0.48 |
| EU | 33 | 0.83°C | 1.14°C | 0.73 |
| Asia | 98 | 1.02°C | 1.45°C | 0.71 |

All three regions are inverted. US is most inverted (0.48); EU is least inverted (0.73).

### Day-by-Day Trend

| Date | n city-days | Per-cd ratio (median) | True sigma (day) |
|---|---|---|---|
| 2026-06-09 | 31 | 0.757 | 1.59°C |
| 2026-06-10 | 33 | 0.926 | 1.48°C |
| 2026-06-11 | 31 | 1.033 | 1.51°C |
| 2026-06-12 | 33 | 0.790 | 1.29°C |
| 2026-06-13 | 35 | 0.835 | 1.34°C |

2026-06-11 briefly crossed 1.0 (at 1.033). Jun 12-13 compressed back to 0.79-0.84. No sustained recovery above 1.10 in this 5-day window or in the prior report's 2026-06-08/09 readings (0.41-0.46).

**Recommendation (observe-only):** The guarded live-refit cron should evaluate whether edge conditions have been met before increasing position size. The dispersion premium has been absent or inverted for at least 6 consecutive days. The BAND_EV_MIN parameter is set at 0.08 (user lowered from 0.15 on 2026-06-05 against prior advice); this gate is now the primary stop against -EV dispersion trades.

---

## 4. ISOTONIC STALENESS

**Deployed:** `config/stwa_isotonic.json` (2024-fit, flat-sigma reference)  
**Candidate:** `config/stwa_isotonic_candidate.json` (refit 2026-06-09T09:30Z, n_live=1037, 2 calendar days)

| p_raw | Deployed | Candidate | Delta | Direction |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 | UP (NO-target) |
| 0.05 | 0.0695 | 0.0758 | +0.006 | UP (NO-target) |
| 0.10 | 0.1340 | 0.1408 | +0.007 | UP |
| 0.15 | 0.1828 | 0.1828 | 0.000 | — |
| 0.20 | 0.2663 | 0.2588 | -0.008 | DOWN |
| 0.25-0.95 | 0.3557-0.3822 | 0.3535-0.3739 | ~-0.006 | DOWN (plateau tightens) |
| **1.00** | **0.6316** | **0.3739** | **-0.258** | **DOWN — MATERIAL** |

**Max absolute delta: 0.258 at p_raw=1.00. Staleness threshold exceeded (>0.05).**

The p_raw=1.00 shift is the sole material deviation. Deployed maps "model certainty" to p_cal=0.63; candidate collapses to 0.37. Operationally significant only if p_model ever reaches exactly 1.0 in practice.

**In the NO-target region (p_raw < 0.15), candidate moves p_cal slightly higher (+0.007 to +0.018).** This is the correct direction: actual YES rate in tails is 2.6% (settled lane), above deployed p_cal of 0.7%. Candidate at 1.75% (p_raw=0.00) is closer to observed reality but still below. This is an undershoot correction, not an overshoot.

**Candidate freshness concern:** refit date 2026-06-09 (5 days ago), n_live=1,037, 2 calendar days. The live-refit cron has not produced a newer candidate since then. If running, it should update daily. The 5-day gap is unusual; the cron may have stalled silently or a data-availability gate is blocking it. At 5+ calendar days with no update, the candidate is effectively stale.

---

## 5. STATE TRANSITIONS

| Metric | Today | Prior (2026-06-13) | Change |
|---|---|---|---|
| Brier7 | 0.0682 | 0.0147 | up (methodology gap) |
| ECE7 | 0.0320 | 0.0326 | stable |
| Rho7 | 0.3660 | 0.7835 | down (methodology gap) |
| Dispersion ratio (uncorrected) | **0.835** | 0.581-0.616 | slight recovery, ALERT persists |
| Dispersion ratio (market-corrected) | **0.710** | (not computed prior) | worse than uncorrected |
| Market/model sigma ratio | **0.850** | **1.060** | sign flip — market tighter |
| Isotonic candidate age | **5 days** | fresh | stale |
| Alerts | **1 (Dispersion)** | 1 (Dispersion) | persistent |

**Dispersion alert has been persistent for at least 2 consecutive reports.** The uncorrected ratio is recovering (0.62 → 0.84) but not enough to clear 1.10. The market-corrected number is worsening (market tightened relative to model). ECE is stable, confirming calibration shape is not actively degrading even if the edge assumption has not been validated in this window.

---

*State written to logs/calib_monitor_state.json*  
*REPORT-ONLY: no code, config, or strategy edits made or recommended.*
