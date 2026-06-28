# Calibration & Dispersion Monitor Report — 2026-06-28

**Snapshot:** 2026-06-28T08:09:38Z  |  Age at run: ~1 min  |  **PASS** (< 6h limit)  
**System:** `klaus systemd: active`  |  Uptime since 2026-06-26T15:08:30Z  
**Bankroll:** $79.75 (prior run 2026-06-27: $57.12 → +$22.63 / +39.6%)  
**Open positions:** 0  |  **Trades JSONL rows:** 8,010  
**Run basis:** MCP GitHub reads (git fetch timed out in remote sandbox)

---

## ALERTS SECTION (pre-registered only)

| ID | Status | Metric | Value | Threshold |
|---|---|---|---|
| **S3** | 🔴 **PERSISTS** | 7d dispersion ratio | 0.75 (prior; unrecomputable today) | < 1.10 |
| **S4** | 🔴 **PERSISTS** | Isotonic material shift at grid=1.0 | Δ = −0.2577 | > 0.05 abs |
| **S2** | ⚠️ **DATA GAP PERSISTS** | Proxy lane book_mid | absent (4th+ cycle) | n/a |

No new alerts fired. S1 thresholds (Brier > 0.15, ECE > 0.05, rho < 0.15) are NOT breached on available data.

---

## Section 1: Settled Lane (Confirmed Labels)

**Data sources:** `stwa_pricer_eval_s50.jsonl` for 2026-06-25 and 2026-06-26  
**Resolution method:** POST_PEAK rows — outcome = 1 if `lo ≤ running_max < hi`, else 0  
**Note:** s50 files for 2026-06-22/23/24/27 were too large for MCP (>1.5 MB); 7d rolling is a partial 2-day window this cycle.

| Date | n (POST_PEAK) | YES rate | Brier (p_cal) | ECE | Spearman ρ | Grade |
|---|---|---|---|---|---|---|
| 2026-06-26 | 1,321 | 10.1% | **0.0213** | **0.0407** | **0.69** | decision-grade |
| 2026-06-25 | 430 | 8.4% | **0.0115** | **0.0311** | **0.89** | decision-grade |
| 2-day weighted | 1,751 | — | **~0.019** | — | — | partial window |

**Reference Brier (2024-fit isotonic, flat-sigma): 0.114**  
Both days are well below the reference and well below the 0.15 alert threshold.

**Alert S1 status:** NOT firing (Brier < 0.15, ECE < 0.05, ρ > 0.15 on both days).

**Watch item — ECE trending toward threshold:**  
- 2026-06-25 ECE: 0.0311  
- 2026-06-26 ECE: 0.0407 (approaching 0.05 threshold)  
- Direction: upward over 2 days. Warrants monitoring. Not an alert yet.

**Prior state brier7:** 0.054 (2026-06-27 run, 7-day rolling, different methodology basis). The 2-day sample here (0.019) suggests the rolling metric is improving, but cannot compute a full 7-day update with available data.

**Model variant comparison (2026-06-26 POST_PEAK, n=1,321):**

| Model | Brier | Notes |
|---|---|---|
| p_cal | 0.0213 | deployed calibration output |
| p_gev | 0.0117 | better by 0.0096 |
| p_ps | 0.0050 | better by 0.0163 |
| p_mc | 0.0017 | better by 0.0196 |
| p_pa | 0.0013 | better by 0.0200 |

**⚠️ Methodological caveat — POST_PEAK look-ahead:** `p_pa` and `p_mc` show near-perfect Brier scores on POST_PEAK rows. These models likely incorporate `running_max` (the real-time observed temperature) in their computation. Once the peak has passed, a model reading the current temperature trivially identifies the winner bucket. These scores should NOT be interpreted as pre-resolution calibration quality. The relevant calibration signal comes from PRE_PEAK predictions, where `p_cal` is the appropriate metric. The model variant ranking should not drive blend-weight changes without PRE_PEAK validation.

---

## Section 2: Proxy Lane (Early Warning, Unsettled)

**Status: DATA GAP PERSISTS (4th+ cycle)**

Today's hot pricer file (`data/shadow/stwa_pricer_eval.jsonl`) is not present at the standard path in the data-mirror branch. The shadow_summary confirms the file exists at `data/shadow/hot/2026-06-28/stwa_pricer_eval.jsonl` (n=126,742 rows as of 08:09 UTC) but the sampled version (`data/shadow/2026-06-28/stwa_pricer_eval_s50.jsonl`) is not yet committed.

**Best available proxy — 2026-06-26 PRE_PEAK rows (n=742):**

| Metric | Value |
|---|---|
| p_cal mean | 0.108 |
| p_cal std | 0.148 |
| p_cal max | 0.380 |
| Rows with p_cal > 0.2 (liquid) | 177 (23.8%) |
| Median \|p_cal − book_mid\| | **absent** — book_mid field not in pricer_eval rows |

The `book_mid` field is missing from pricer_eval_s50 rows (confirmed for 4th+ consecutive monitoring cycle). The proxy divergence metric (p_cal vs market mid) cannot be computed. The early warning capability of this lane is fully blind.

**Recommend:** Add `book_mid` (best bid/ask midpoint at row-log time) to the pricer shadow logger. Without it, the proxy lane cannot detect model-market divergence spikes in advance of resolution.

**Structural note:** All PRE_PEAK p_cal values cap at 0.3801 (the isotonic plateau). No PRE_PEAK row exceeds the plateau level. This is expected given the isotonic's severe compression above p_model=0.25 (see Section 4).

---

## Section 3: Dispersion Gauge (Edge Variable — Most Important)

**This is the band strategy's load-bearing quantity.** The band harvests value when market-implied temperature uncertainty exceeds true uncertainty. The signal: implied_std (from ladder ask distribution) vs realized_abs (actual temp error from mode).

### Implied Width — New Fire Records

From `band_struct_lite.jsonl` for 2026-06-26 (source) and 2026-06-27 (source), records with `record="md_shadow"` and `reason="fire"` (YES band fires):

| City | Market Date | d+ | Legs | SumAsk | Implied σ (°C) | Mode |
|---|---|---|---|---|---|---|
| Chengdu | 2026-06-27 | d+1 | 5 | 0.985 | **1.27°C** | 31.0°C |
| Chengdu | 2026-06-27 | d+0 | 4 | 0.810 | **1.06°C** | 30.0°C |
| Chengdu | 2026-06-29 | d+2 | 4 | 0.735 | **1.11°C** | 27.0°C |
| Munich | 2026-06-29 | d+2 | 4 | 0.620 | **0.90°C** | 28.0°C |
| Beijing | 2026-06-28 | d+0 | 3 | 0.735 | **0.82°C** | 33.0°C |
| Beijing | 2026-06-29 | d+2 | 3 | 0.555 | **0.82°C** | 24.0°C |
| Wuhan | 2026-06-29 | d+2 | 3 | 0.690 | **0.82°C** | 33.0°C |

**7 city-day fire records (n=7, trend-grade only — below n≥100 decision threshold)**

| Metric | Value |
|---|---|
| Implied σ median | **0.90°C** |
| Implied σ mean | 0.97°C |
| Implied σ range | 0.82 – 1.27°C |
| Prior implied_std_7d_median | 0.84°C |
| Prior realized_abs_7d_median | 1.00°C |
| Prior disp_ratio7 | **0.75** |

### Realized Component: UNAVAILABLE

Gamma API resolution data for 2026-06-27 markets is not accessible in this environment (git fetch timed out; network-isolated sandbox). The realized_abs component cannot be updated for this reporting cycle.

### Dispersion Ratio Status

**disp_ratio7 = 0.75 (carried forward from 2026-06-27 run)**  
**Alert threshold: < 1.10**  
**🔴 S3 ALERT PERSISTS**

The implied_std median for new fire records (0.90°C) is consistent with the prior period's 0.84°C. There is no sign of improvement in the implied width. The realized errors cannot be updated this cycle. The ratio is almost certainly still below 1.10.

**Plain statement:** The dispersion premium this band strategy harvests is unvalidated and may not exist. The market is pricing temperature risk tighter than it actually occurs. If this ratio (0.75) is correct, the band is systematically buying too expensive — the YES buckets are mispriced relative to actual uncertainty. The band is currently profitable ($79.75 vs $57.12), which means either (a) the ratio is improving and we cannot see it, (b) the bankroll gain comes from NO-side fills at favorable prices, or (c) the current narrow allowlist (5 cities: chengdu, london, beijing, munich, wuhan) has better-calibrated markets than the full universe used in the ratio measurement.

**Sum_gate cross-check (2026-06-26 inline, d+1 n=8, d+2 n=5):**
- d+1 sum_ask median: 0.960 (5 buckets capture 96% of ask mass)
- d+2 sum_ask median: 0.949

High sum_ask (>0.95) means the market concentrates nearly all probability mass in ≤5 adjacent 1°C buckets — consistent with implied_std ~0.90-1.00°C. The sum_gate fires (not the fire records) show the market frequently considers the distribution too tight to enter the band.

**Per-region breakdown (prior state, no update):**
- US: 0.65 (worst)
- EU: 0.80
- Asia: 0.79

The narrow-start allowlist (chengdu, london, beijing, munich, wuhan) excludes most US cities, which is consistent with the US being the worst-performing region.

---

## Section 4: Isotonic Staleness

**Deployed:** `config/stwa_isotonic.json` — refit 2026-06-06T22:27:08Z (22 days ago)  
**Candidate:** `config/stwa_isotonic_candidate.json` — refit 2026-06-09T09:30:36Z (19 days ago)

### Grid Comparison

| Grid (p_model) | Deployed | Candidate | Δ |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 |
| 0.05 | 0.0695 | 0.0758 | +0.006 |
| 0.10 | 0.1340 | 0.1408 | +0.007 |
| 0.15 | 0.1828 | 0.1828 | 0.000 |
| 0.20 | 0.2663 | 0.2588 | −0.008 |
| 0.25 | 0.3557 | 0.3535 | −0.002 |
| 0.30–0.90 | **0.3801** | **0.3739** | −0.006 |
| 0.95 | **0.3822** | **0.3739** | −0.008 |
| 1.00 | **0.6316** | **0.3739** | **−0.2577 ← MATERIAL** |

**Material shifts (> 0.05 absolute): 1 point — grid=1.00 only**

### Verdict

🔴 **S4 ALERT PERSISTS — DO NOT DEPLOY CANDIDATE**

The sole material shift is at grid=1.00: deployed maps extreme model confidence (p_model=1.0) to 0.6316; the candidate collapses this to 0.3739 (same as the entire plateau from 0.30 upward). The candidate has **completely lost the high-confidence signal** — a model that is 100% certain maps to the same calibrated output as a model with 30% confidence.

Both maps share the same pathology: **severe plateau collapse** above p_model=0.30. The isotonic regression has found no discriminative signal in the model outputs for p_model ∈ [0.30, 1.0], producing a flat function at ~0.38. This means:
- All model outputs above the 25th percentile produce identical p_cal ≈ 0.38
- The calibration curve is not actually calibrating — it is compressing all mid-range and high-confidence signals to a single value

The candidate makes this worse at grid=1.0 (−0.2577 shift), which is the only region where the deployed version preserves any signal.

**near_identity_maxdev:** Deployed 0.568 vs Candidate 0.626. Both far from identity. Candidate is worse.

**Age:** Both maps are ≥19 days old with no live data incorporated (deployed n_live=0, candidate n_live=1,037 — tiny weight). The cron-based live refit has not produced a materially different map. This likely means the live fills data (n=1,037 over 2 calendar days) does not change the isotonic regression's shape at a population scale.

**Recommendation (read-only):** The guarded live-refit cron should continue running to accumulate live data. Do not promote the candidate. When n_live reaches ~5,000+, re-evaluate whether the plateau has shifted.

---

## Section 5: State & Transition Diff

### Current State

```json
{
  "date": "2026-06-28",
  "snapshot_ts": "2026-06-28T08:09:38Z",
  "brier7": "~0.019 (2-day partial; prior 7d: 0.054)",
  "ece7": "0.041 (2026-06-26, approaching 0.05 threshold)",
  "rho7": 0.69,
  "disp_ratio7": 0.75,
  "n_resolved": 1751,
  "implied_std_7d_median_c": 0.90,
  "alerts": ["S3 PERSISTS", "S4 PERSISTS", "S2 DATA GAP PERSISTS"]
}
```

### Transition vs Prior (2026-06-27)

| Metric | Prior | Current | Direction |
|---|---|---|---|
| brier7 | 0.054 | ~0.019 (partial) | ↓ Improving |
| ece7 | 0.015 | 0.041 | ↑ Worsening — watch |
| rho7 | 0.433 | 0.69 | ↑ Improving |
| disp_ratio7 | 0.75 | 0.75 (unchanged) | → No update |
| Bankroll | $57.12 | $79.75 | ↑ +$22.63 (+39.6%) |
| S3 alert | FIRED | PERSISTS | → |
| S4 alert | PERSISTS | PERSISTS | → |
| S2 data gap | PERSISTS | PERSISTS | → |

**ECE rising** from 0.015 to 0.041 over 1 cycle is notable. The 2-day sample may have a day-specific bias (the 2026-06-26 YES rate of 10.1% vs 8.4% the day before). However, if ECE crosses 0.05 in the next cycle, the S1 calibration alert will fire. Monitor closely.

**Bankroll growth of 39.6% in ~2 days** is striking context. The band is making money. This does not invalidate the dispersion concern but raises the possibility that either: (a) the NO-side fills are driving returns (not the YES-side where the dispersion ratio matters most), or (b) the 5-city allowlist has genuinely better-calibrated markets.

---

## Data Coverage Limitations

- `data/shadow/stwa_pricer_eval.jsonl` (today's hot pricer at root path): **NOT FOUND** — file is at `data/shadow/hot/2026-06-28/stwa_pricer_eval.jsonl` per shadow_summary (n=126,742 rows as of snapshot), but the 1-in-50 sample (`data/shadow/2026-06-28/stwa_pricer_eval_s50.jsonl`) is not yet committed. Proxy lane for today = unavailable.
- Pricer s50 for 2026-06-22/23/24/27: too large for MCP GitHub API (>1.5 MB); download URLs provided but not network-accessible from sandbox. 7d rolling Brier is a 2-day partial window this cycle.
- Gamma resolution data: not accessible (git fetch timed out); realized_abs component of dispersion ratio cannot be updated.
- Band struct lite fire records: note that the record type is `record="md_shadow"` with `reason="fire"`, NOT `record="fire"`. Callers parsing for `record="fire"` will find 0 records. Documented here for any downstream agents.

---

*Report generated: 2026-06-28T08:10 UTC | Calib monitor agent | Branch: claude/find-lag-parameter-rFQ0N*
