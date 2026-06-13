# Klaus Calibration & Dispersion Monitor Report
**Date:** 2026-06-13  
**Run time:** 2026-06-13T08:09Z  
**Snapshot freshness:** 2026-06-13T08:03Z (6 min old — OK)  
**System:** `klaus systemd: active`  
**Data window:** 2026-06-08 → 2026-06-12 (5 resolved days, 1-in-50 sample)

---

## ALERTS

> **DISPERSION RATIO — ALERT FIRES**  
> 7d median implied/realized ratio = **0.62** (model-corrected). Below the 1.10 floor.  
> The model-implied distribution is narrower than realized displacements. The dispersion edge is not confirmed in this 5-day window. See Section 3 for detail.

No other pre-registered alerts fired (Brier, ECE, rho all clear).

---

## METHOD NOTE

**No Gamma API access** (HTTP 403 — Cloudflare WAF blocks this sandbox). Resolution truth uses the pricer_s50 `running_max` field as the outcome proxy: for POST_PEAK rows where `t_close < now`, outcome = 1 if `running_max` falls in the bucket [lo, hi), else 0. This is the same physical value used by the oracle for resolution (observed daily maximum from METAR stations), so it is a valid ground-truth proxy, not a price-drift inference. For the dispersion gauge, the implied distribution is computed from PRE_PEAK p_cal values (last snapshot before peak detection) with a 1.06× market-premium correction derived from today's stwa_ladder_book (392 PRE_PEAK snapshots, market_sigma / model_sigma median = 1.060).

---

## 1. SETTLED LANE

**Coverage:** 2,033 deduped (city, date, bucket) cells across 188 unique city-days (June 8–12). All n above decision-grade threshold (>100 sampled).

| Metric | Value | Threshold | Status |
|---|---|---|---|
| 7d Brier | **0.0147** | >0.15 = ALERT | ✓ clear |
| 7d ECE | **0.0326** | >0.05 = ALERT | ✓ clear |
| Spearman ρ (rank-corr) | **+0.784** | <0.15 = ALERT | ✓ clear |
| Reference Brier (2024-fit) | 0.114 | — | — |

The aggregate numbers look good, but the distribution structure is highly skewed and worth inspecting.

### ECE Bin Detail

| Bin | n | mean p_cal | mean outcome | \|Δ\| | n-grade |
|---|---|---|---|---|---|
| [0.0, 0.1) | 1,839 | 0.0008 | 0.0011 | 0.0003 | decision |
| [0.1, 0.2) | 9 | 0.1432 | 0.1111 | 0.0321 | **collect** |
| [0.2, 0.3) | 5 | 0.2447 | 0.0000 | 0.2447 | **collect** |
| [0.3, 0.4) | 13 | 0.3783 | 0.5385 | 0.1602 | **collect** |
| [0.4, 0.5) | 0 | — | — | — | — |
| [0.5, 0.6) | 7 | 0.5537 | 1.0000 | 0.4463 | **collect** |
| [0.6, 0.7) | 160 | 0.6309 | 1.0000 | 0.3691 | decision |
| [0.7, 1.0) | 0 | — | — | — | — |

**Interpretation:** 90.5% of all cells sit in the [0.0, 0.1) bin and are correctly assigned near-zero probability — this dominates the low ECE and Brier. The actual calibration of the mode bucket region ([0.6, 0.7), n=160, decision-grade) shows p_cal substantially underestimating outcome rate: when p_cal ≈ 0.63, the bucket wins 100% of the time. This is not a calibration *failure* — it reflects the isotonic map's plateau structure collapsing all high-model-confidence cells to ~0.38–0.63 — but the underconfidence is real and large at this quantile.

Bins [0.2, 0.3), [0.3, 0.4), [0.5, 0.6) are all n < 40 (collect-only); no action conclusions possible from them.

### Per-Day Brier

| Date | n cells | Brier | Hits |
|---|---|---|---|
| 2026-06-08 | 336 | 0.0168 | 29 |
| 2026-06-09 | 381 | 0.0135 | 33 |
| 2026-06-10 | 441 | 0.0127 | 38 |
| 2026-06-11 | 414 | 0.0129 | 36 |
| 2026-06-12 | 461 | 0.0177 | 41 |

Flat across the window; June 12 marginally higher (0.0177) driven by slightly more miss-rate variation, not a trend.

---

## 2. PROXY LANE (Early Warning — Today, Unsettled)

**Coverage:** 1,888 active PRE_PEAK bucket rows from today's stwa_ladder_book.jsonl (June 13, 2026-06-13T00:00 – 08:03 UTC). 7-day baseline **not available** (stwa_ladder_book not archived per-day in data-mirror).

| Metric | Value |
|---|---|
| Median \|p_cal − mkt_mid\| | **0.119** (12 pp) |
| Mean \|p_cal − mkt_mid\| | 0.153 |
| p25 / p75 | 0.047 / 0.267 |
| Buckets with \|diff\| > 0.05 | 1,376 / 1,888 (73%) |

**Cities with largest median divergence today:** lucknow (0.305), qingdao (0.271), jeddah (0.262), helsinki (0.262), madrid (0.236).

**Assessment:** Without a 7-day baseline this cannot be flagged as a spike vs normal. The median 12 pp divergence is large in absolute terms and suggests the model's p_cal systematically differs from market pricing for a significant share of active buckets. Whether this represents stale model calibration vs market-specific information (weather events, active traders) is not separable from this data alone. Recommend archiving stwa_ladder_book daily (or including it in the per-day data-mirror) to build the 7d baseline this lane needs.

---

## 3. DISPERSION GAUGE ⚠️

**This is the load-bearing section.**

Background: The band strategy's edge rests on the claim that *market-implied temperature dispersion exceeds true dispersion*. If the ratio collapses below 1.10, the market is no longer overpricing uncertainty and the band's expected premium erodes.

### Methodology

For each city-day in June 8–12 that has both PRE_PEAK and POST_PEAK pricer rows:
- **Implied sigma**: std of bucket midpoints weighted by the last PRE_PEAK p_cal snapshot (before peak detection). Corrected upward by factor 1.060 (today's PRE_PEAK market_sigma / model_sigma median, n=392).
- **Realized displacement**: |winning_bucket_midpoint − mode_bucket_midpoint at last PRE_PEAK snapshot|. Mode = highest p_cal bucket.
- **Ratio**: implied_sigma / realized_displacement. Excluded if realized_displacement < 0.001°C (exact mode hit).

**Limitation:** p_cal is used as market price proxy for historical days (stwa_ladder_book not archived). The 1.06 correction factor is a point estimate from today; historical market-premium may vary. The true market-implied ratio is likely marginally higher than reported — but not by enough to change the conclusion.

### Results

| Metric | Value |
|---|---|
| City-days analyzed | 149 |
| Exact mode hits (excluded) | 76 (51%) |
| Non-zero displacement (used for ratio) | 73 |
| **7d median ratio (model-based)** | **0.581** |
| **7d median ratio (market-corrected ×1.060)** | **0.616** |
| Alert threshold | 1.10 |
| **ALERT STATUS** | **🔴 FIRES** |

### By Region

| Region | n valid | Model median | Market-corrected |
|---|---|---|---|
| US | 28 | 0.581 | 0.616 |
| EU | 12 | 0.783 | 0.830 |
| Asia | 33 | 0.561 | 0.595 |

EU is the least bad region; Asia and US are the most compressed.

### Day Trend

| Date | n valid | Model median | Market-corrected |
|---|---|---|---|
| 2026-06-08 | 16 | 0.432 | 0.458 |
| 2026-06-09 | 15 | 0.386 | 0.409 |
| 2026-06-10 | 16 | 0.736 | 0.781 |
| 2026-06-11 | 12 | 0.794 | 0.842 |
| 2026-06-12 | 14 | 0.809 | 0.857 |

**Trend:** June 8–9 were worst (ratio 0.41–0.46). June 10–12 show recovery (0.78–0.86). The 7d median is pulled down heavily by the early-window collapse. If the June 10–12 level holds, the ratio may cross 1.10 within ~5 days of additional data. This is not a reason to declare the edge restored — it's a reason to watch carefully.

### Interpretation — Plain Language

The median corrected ratio is **0.62**. That means: when the model's mode prediction was wrong, the realized displacement was on average **1/0.62 = 1.6× larger** than the model's pre-peak implied distribution width. The market-implied distribution is too narrow for the actual temperature outcomes observed this week.

**The edge stated in CLAUDE.md ("true sigma ~1.3°C < implied") is not confirmed by this data window.** The model-implied sigma (median 0.86°C) is itself narrower than the typical realized displacement in the miss cases. Whether this reflects the isotonic plateau compressing p_cal (suppressing implied width) rather than a genuine market-level compression is not distinguishable with p_cal as the market proxy. The safest reading: the premium is compressed or negative in this period, and the recent improvement in June 10–12 is encouraging but does not yet clear the 1.10 threshold.

---

## 4. ISOTONIC STALENESS

**Deployed:** `config/stwa_isotonic.json` — refit 2026-06-06T22:27Z, n_hist=76,617, **n_live=0** (no live data incorporated).  
**Candidate:** `config/stwa_isotonic_candidate.json` — refit 2026-06-09T09:30Z, n_hist=76,617, **n_live=1,037** (2 calendar days of live data).

### Map Comparison (material shifts only — >0.05)

| raw_p | Deployed | Candidate | Δ | Direction |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 | slightly higher |
| 0.30–0.90 (plateau) | 0.3801 | 0.3739 | −0.006 | marginally lower |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **⚠️ MUCH LOWER** |

**One material shift**: at the raw_p = 1.00 knot, the candidate collapses 0.63 → 0.37 (Δ = −0.258). This is large. The deployed map reserved this extreme knot for the highest-model-confidence bucket predictions (typically the mode bucket at peak detection), mapping them to p_cal ≈ 0.63. The candidate, after incorporating 1,037 live rows, maps them to p_cal ≈ 0.37 — exactly the same as the mid-probability plateau.

**What this means for trading:** If deployed, the candidate would reduce the mode bucket's quoted p_cal from ~0.63 to ~0.38 for the highest-confidence model outputs. Given that our settled-lane data shows the mode bucket wins 100% of the time when p_cal ∈ [0.6, 0.7) (n=160), deploying the candidate would move these cells into the underconfident regime, potentially causing the band to underprice its core edge leg.

**Recommendation (observe only):** The candidate direction is concerning relative to live observed outcome rates. The guarded live-refit cron should hold; human review of why n_live=1,037 rows produced such a large downward shift at the extreme knot is warranted before deploying.

---

## 5. STATE

```json
{
  "date": "2026-06-13",
  "brier7": 0.0147,
  "ece7": 0.0326,
  "rho7": 0.7835,
  "disp_ratio7_model": 0.581,
  "disp_ratio7_market_corrected": 0.616,
  "disp_ratio_trend": {
    "2026-06-08": 0.458,
    "2026-06-09": 0.409,
    "2026-06-10": 0.781,
    "2026-06-11": 0.842,
    "2026-06-12": 0.857
  },
  "n_settled_cells": 2033,
  "n_city_days_dispersion": 149,
  "alerts": [
    "DISPERSION_RATIO_7D_0.62_below_1.10"
  ],
  "isotonic_candidate_maxdev": 0.258,
  "isotonic_candidate_direction": "LOWER_at_top_knot",
  "proxy_lane_median_divergence_today": 0.119,
  "prior_state": null
}
```

**Transitions vs prior:** No prior state file — this is the first run.

---

## SUMMARY

| Check | Status |
|---|---|
| Snapshot fresh | ✓ 6 min |
| System active | ✓ |
| Brier7 = 0.0147 | ✓ OK |
| ECE7 = 0.0326 | ✓ OK |
| Rho7 = 0.784 | ✓ OK |
| **Disp ratio 0.62** | **🔴 ALERT — below 1.10** |
| Isotonic candidate material shift | ⚠️ Note — hold on deploying |
| Proxy lane baseline | ⚠️ No 7d baseline yet |

**The edge premise is under stress.** The dispersion ratio alert fires at 0.62. The trend since June 10 is recovering (0.78–0.86 corrected), so this is not a permanent collapse, but the 7-day median is well below threshold. The guarded live-refit cron should NOT deploy the isotonic candidate until the extreme-knot collapse is reviewed. No code edits — recommendations only.
