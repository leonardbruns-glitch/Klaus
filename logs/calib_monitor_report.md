# Klaus Calibration & Dispersion Monitor Report
**Date:** 2026-06-21
**Run time:** 2026-06-21T08:20Z
**Snapshot freshness:** data-mirror snapshot_ts 2026-06-21T07:58:39Z — 22 min old — OK
**System:** `klaus systemd: active` (from system_status.txt; bot running since 2026-06-19T00:17Z)
**Data window:** 2026-06-16 → 2026-06-20 (5 resolved days, 186 city-days) + 2026-06-21 partial (proxy lane)
**s50 dataset:** 27,579 rows across 186 city-days (1-in-50 sample from stwa_pricer_eval_s50.jsonl)
**Bankroll:** not read this run (see prior reports)

---

## ALERTS

> ### DISPERSION ALERT — FIRES (persistent, 7th consecutive report)
> **7d median dispersion ratio = 0.671** (model-implied σ / |actual − mode|, n=119 ratios from 169 city-days — DECISION-grade).
> This is below the 1.10 floor.
>
> **Model-implied sigma (0.882°C median) is 67% of the empirical crossing-distance (true sigma ~1.373°C). The edge premise — that market-implied dispersion exceeds true dispersion — remains inverted.**
>
> Report history: 06-13: 0.620 → 06-14: 0.835 (brief spike) → 06-16: 0.589 → 06-19: 0.556 → 06-20: 0.584 → **06-21: 0.671 (+0.087 vs prior — largest single-session improvement in 5 reports, excluding the Jun 14 spike).**
>
> One data point does not confirm recovery. Trend is improving but the ratio must **sustain** above 1.10 before any edge declaration.

No other pre-registered alerts fired. Brier (0.0597), ECE (0.0310), and rho (0.392) are all within normal range.

---

## METHOD NOTE

**No Gamma API access** (sandbox blocked by Cloudflare WAF). Resolution proxy: maximum `running_max` in POST_PEAK pricer rows per city per date folder. Outcome = final_rm in bucket `(lo, hi)`. Sentinel buckets `lo ≤ -100` or `hi ≥ 900` excluded from all dispersion calculations.

**Dispersion methodology (unchanged from prior reports):** Implied sigma per city-day uses the LAST PRE_PEAK pricer record per interior bucket. PRE_PEAK-only is critical — POST_PEAK rows collapse p_cal to near-0/1, compressing sigma to zero. True sigma is estimated as the cross-city stdev of (final_rm − mode_mid) across all 169 resolved city-days = 1.373°C (prior: 1.461°C). Consistent with the validated range (1.3–1.5°C across prior reports). Per-city-day dispersion ratio = implied_sigma / |final_rm − mode_mid|; median of n=119 ratios (50 city-days excluded where |final_rm − mode_mid| ≤ 0.1°C, mostly EU exact-mode resolutions).

---

## 1. SETTLED LANE

**Coverage:** 27,579 s50-rows across 186 city-days (2026-06-16 to 2026-06-20). Full-log estimate: ~1.4M bucket evaluations.

| Metric | Value | Threshold | Status | Prior (2026-06-20) | Delta |
|---|---|---|---|---|---|
| 7d Brier (p_cal) | **0.0597** | >0.15 = ALERT | clear | 0.0516 | +0.008 |
| 7d ECE (p_cal) | **0.0310** | >0.05 = ALERT | clear | 0.0333 | −0.002 |
| Spearman rho | **+0.392** | <0.15 = ALERT | clear | +0.419 | −0.027 |
| Reference Brier (2024-fit) | 0.114 | — | — | — | — |

Brier degraded modestly (+0.008). This is notable — largest single-session Brier rise in the 7-day window — but still well below the 0.15 alert threshold. ECE improved (−0.002). Rho slightly lower (−0.027), still solidly positive. The Brier rise warrants watching for one more session: if it continues toward 0.08+, investigate whether the 2026-06-20 data introduced a harder market-day.

**Model variant Brier:**

| Model | Brier | vs p_cal |
|---|---|---|
| p_mc | **0.0494 (BEST)** | −0.010 |
| p_pa | 0.0528 | −0.007 |
| p_ps | 0.0546 | −0.005 |
| p_gev | 0.0599 | −0.000 |
| p_cal | 0.0597 | — |

`p_mc` (Monte Carlo ensemble) remains the best raw model; isotonic calibration still adds no measurable value over raw p_mc. This has been consistent across all recent reports. p_gev (GEV) now matches p_cal almost exactly — first time these have converged.

### Reliability Table (p_cal, 10 equal-width bins)

| Bin | n (s50) | conf | acc | delta | Grade |
|---|---|---|---|---|---|
| [0.0, 0.1) | 20,537 | 0.007 | 0.020 | −0.013 (UNDER) | DECISION |
| [0.1, 0.2) | 1,487 | 0.148 | 0.125 | +0.023 (OVER) | DECISION |
| [0.2, 0.3) | 933 | 0.252 | 0.150 | +0.102 (OVER) | DECISION |
| [0.3, 0.4) | 3,661 | 0.369 | 0.323 | +0.046 (OVER) | DECISION |
| [0.4, 0.5) | 78 | 0.461 | 0.795 | −0.334 (UNDER) | TREND |
| [0.5, 0.6) | 92 | 0.563 | 0.902 | −0.340 (UNDER) | TREND |
| [0.6, 0.7) | 791 | 0.629 | 0.942 | −0.313 (UNDER) | DECISION |

**Structural calibration findings (all persistent, all decision-grade where n≥100):**

1. **Deep tail [0.0, 0.1) — systematic underestimate of YES (structural).** p_cal=0.007 vs actual=0.020, delta −0.013, n=20,537. Dominant bin by volume; stably miscalibrated for 7+ sessions. The isotonic flat plateau at ~0.38 for p_raw ≥ 0.25 means low-p_raw buckets cluster here. Unchanged in direction and magnitude from prior reports.

2. **Shoulder [0.2, 0.4) — overconfidence (structural).** [0.2,0.3): +0.102 (n=933); [0.3,0.4): +0.046 (n=3,661). The [0.2,0.3) shoulder is the sharpest overconfidence region. The [0.3,0.4) overconfidence improved vs prior (+0.046 vs +0.080) — first session below +0.05 for that bin, TREND-grade improvement given the prior n was higher. Watch.

3. **Upper plateau [0.6, 0.7) — extreme underconfidence (structural artifact).** n=791, conf=0.629, actual=0.942, delta −0.313. Buckets assigned p_cal ≥ 0.60 resolve at 94.2% — similar to Jun 20 (97.5%). The deployed isotonic ceiling (p_raw=1.0 → p_cal=0.6316) creates this structural floor. Until isotonic is updated, this artifact persists. Note: the candidate isotonic lowers this ceiling to 0.3739, which would eliminate the [0.6, 0.7) bin entirely — the effect on the [0.3, 0.4) bin would need evaluation.

---

## 2. PROXY LANE (Early Warning — Today, Unsettled)

**Coverage:** 2,153 PRE_PEAK bucket rows from today's pricer_s50 (2026-06-21, through ~08:00 UTC).

| Metric | Today | 7d baseline | Ratio | Flag |
|---|---|---|---|---|
| Median \|p_cal − 0.5\| | 0.4967 | 0.4958 | 1.002 | OK |

Today's model confidence distribution is within 0.2% of the 7d baseline. No divergence. Normal market state at 08:00 UTC. ~30+ cities active in PRE_PEAK. Informational only.

---

## 3. DISPERSION GAUGE (Primary Edge Variable — Most Important)

**Source:** Last PRE_PEAK pricer_s50 record per interior bucket per city-day. Market-book σ not computed (stwa_ladder_book available in full from this snapshot, but prior methodology uses model σ / cross-city realization for consistency).

### Overall

| Metric | Value | Prior (06-20) | Delta | 7d Trend |
|---|---|---|---|---|
| Median dispersion ratio (implied σ / true err) | **0.671** | 0.584 | **+0.087** | Improving |
| Median implied σ (°C, per city-day) | 0.882°C | 0.854°C | +0.028 | Widening |
| Cross-city true σ (stdev of final_rm − mode) | 1.373°C | 1.461°C | −0.088 | Compressing |
| n city-days (dispersion) | 169 | 147 | +22 | Growing |
| n ratio pairs (true_err > 0.1°C) | 119 | — | — | — |

The improvement in ratio (+0.087) is the largest single-session positive move since Jun 13→14 (0.620→0.835). Two drivers: implied sigma widened slightly (model assigned more spread) AND true sigma compressed modestly (realized outcomes were closer to mode this window). Neither alone would explain +0.087 — it's both.

**The edge remains inverted.** The ratio is 0.671, not 1.10. The full recovery required is +0.429 from here.

### 7-Day History

| Date | Ratio | Delta |
|---|---|---|
| 2026-06-13 | 0.620 | — |
| 2026-06-14 | 0.835 | +0.215 |
| 2026-06-16 | 0.589 | −0.246 |
| 2026-06-19 | 0.556 | −0.033 |
| 2026-06-20 | 0.584 | +0.028 |
| **2026-06-21** | **0.671** | **+0.087** |

The Jun 14 spike reversed quickly. The current improvement from the 0.556 trough (+0.115 over two sessions) is more sustained but shallow. The trend is ambiguous — two positive sessions, but no consecutive sessions above 0.65 before Jun 14. No signal of confirmed recovery.

### By Region

| Region | n city-days | n ratios | Median ratio | Grade |
|---|---|---|---|---|
| US | 28 | 28 | 0.717 | TREND (approaching decision) |
| EU | 44 | 20 | 0.830 | TREND (best region; many exact-mode resolutions excluded) |
| Asia | 31 | 22 | 0.655 | TREND |
| Other | 66 | 49 | 0.612 | DECISION |

EU is the best-performing region (0.830) — note that 24 of 44 EU city-days had |actual − mode| ≤ 0.1°C (exact-mode resolution), suggesting high model accuracy in EU or tighter bucket quantization. If EU accuracy is genuinely high, the strategy's EU band efficiency may differ from Other/Asia. US (0.717) is also above the global median. "Other" (0.612, n=49) is the decision-grade region and the weakest — likely South American and Middle Eastern cities.

**No region is above 1.10.** Even EU (best) at 0.830 is 0.27 below threshold.

---

## 4. ISOTONIC STALENESS

| Field | Deployed | Candidate |
|---|---|---|
| Fit timestamp | 2026-06-06T22:27Z | 2026-06-09T09:30Z |
| Age (from 2026-06-21T08:00Z) | **15 days** | **12 days** |
| n_hist | 76,617 | 76,617 |
| n_live | 0 | 1,037 |
| live_calendar_days | 0 | 2 |
| near_identity_maxdev | 0.568 | 0.626 |

**Max absolute shift: 0.2577** (material threshold: >0.05 → YES, material).

The only material difference is at p_raw=1.0: deployed maps to 0.6316, candidate maps to 0.3739 (delta −0.2577). All other grid points differ by < 0.025 (non-material).

**What this means:** The candidate's ceiling (0.3739) would entirely flatten the upper probability region. The [0.6, 0.7) reliability bin (n=791, actual acc=0.942) would likely collapse into the [0.3, 0.4) bin — meaning p_cal would be assigned ~0.374 to buckets that currently resolve at 94%. This would worsen overconfidence in the shoulder ([0.3, 0.4)) and likely raise Brier. The candidate isotonic refit direction moves p_cal in the WRONG direction for the upper plateau finding.

**Candidate status: unchanged since Jun 9 (12 days stale, identical to prior report).** The live-refit cron has not generated a new candidate. This is notable: the cron runs on the VPS and appears not to have generated a fresher candidate in the past 12 days. No code action from this agent; flag for operator.

**Recommendation (operator, not this agent):** The deployed isotonic requires manual review before promotion of the candidate. The candidate's ceiling reduction contradicts the observed calibration finding that p_raw=1.0 buckets resolve at 94%+ — the ceiling should be raised, not lowered. A targeted refit incorporating the live data from Jun 16–21 would be more informative. The live-refit cron may need a manual trigger.

---

## 5. STATE TRANSITION

Prior state (2026-06-20) → Current state (2026-06-21):

| Metric | Prior | Current | Direction |
|---|---|---|---|
| brier7 | 0.0516 | **0.0597** | ▲ worsened |
| ece7 | 0.0333 | **0.0310** | ▼ improved |
| rho7 | 0.419 | **0.392** | ▼ slightly lower |
| disp_ratio7 | 0.584 | **0.671** | ▲ improved |
| Alerts active | 1 (DISP) | 1 (DISP) | → unchanged |

The dispersion alert has fired continuously since at least 2026-06-12. State file written to logs/calib_monitor_state.json.

---

## SUMMARY

The calibration model is performing adequately (no Brier/ECE/Rho threshold breaches) with persistent structural miscalibration in three bins — all present since the monitor began, all attributable to the isotonic plateau architecture. The edge variable (dispersion ratio) improved materially today (+0.087), the largest gain in 5 reports. The ratio is still 0.671, nearly 40% below the required 1.10 floor. The alert continues. Two more sessions of similar improvement would be required to approach threshold; the prior Jun 14 spike showed that a single-session improvement can reverse immediately.

**The edge premise remains unvalidated for live capital deployment in the band.** This monitor does not recommend halting (that is above its remit and a risk/capital decision), but cannot confirm the edge exists.
