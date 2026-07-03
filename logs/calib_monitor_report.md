# Calibration & Dispersion Monitor — 2026-07-03

**Snapshot**: 2026-07-03T08:09:16Z (age < 6h ✓)  
**System**: active ✓ | **Bankroll**: $79.57 (+$3.26 vs prior $76.31) | **BAND_LIVE**: True | **BAND_NO_ENABLED**: False (halted 2026-07-02, 7d WR rail)

---

## 1. SETTLED LANE (resolved market-days: Jun 28 – Jul 2)

**Method**: POST_PEAK/AT_PEAK `running_max` used as resolved outcome (inference; no direct CLOB labels in sandbox). 205 resolved city-date pairs, n=36,551 sampled rows (s50, 1-in-50).

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Brier7 | **0.053** | < 0.15 | ✅ OK |
| ECE7 | **0.019** | < 0.05 | ✅ OK |
| Rank-rho (Spearman) | **0.446** | > 0.15 | ✅ OK |

**Brier by date** (stable, no trend):

| Date | n rows | Brier |
|---|---|---|
| 2026-06-28 | 7,648 | 0.053 |
| 2026-06-29 | 7,918 | 0.054 |
| 2026-06-30 | 8,123 | 0.051 |
| 2026-07-01 | 6,123 | 0.056 |
| 2026-07-02 | 6,739 | 0.052 |

**ECE bin detail**:

| Bin | n | mean_p | mean_o | |delta| |
|---|---|---|---|---|
| [0.0, 0.1) | 28,451 | 0.006 | 0.016 | 0.010 |
| [0.1, 0.2) | 1,784 | 0.147 | 0.108 | 0.040 |
| [0.2, 0.3) | 1,105 | 0.247 | 0.178 | 0.069 |
| [0.3, 0.4) | 4,105 | 0.372 | 0.366 | 0.005 |
| [0.4, 0.5) | 36 | 0.445 | 0.944 | — (structural: these are mode-bucket rows) |
| [0.5, 0.6) | 132 | 0.556 | 0.909 | — (structural) |
| [0.6, 0.7) | 938 | 0.630 | 0.828 | — (structural) |

**Plateau note**: The deployed isotonic maps all grid 0.30–0.90 to p_cal=0.3801. Rows in this plateau (n=3,168) have actual win rate 0.411 — slight underconfidence (+0.031). Structurally expected. The plateau eliminates discriminative power across a wide model-score range; any bucket scored 0.30–0.90 by the raw model gets identical p_cal.

High-confidence bins ([0.4–0.7)): apparent win rates of 0.83–0.94 are structurally correct — these rows are overwhelmingly the mode/winner bucket at post-peak, which by definition is the winner. Not a calibration artifact.

---

## 2. PROXY LANE (early warning — today 2026-07-03, unsettled)

**Method**: PRE_PEAK p_cal-weighted std of bucket midpoints per city. No direct CLOB book-price comparison available in s50.

**7-day PRE_PEAK implied sigma trend** (all cities):

| Date | n cities | Median sigma | Mean sigma |
|---|---|---|---|
| 2026-06-28 | 37 | 0.988°C | 1.046°C |
| 2026-06-29 | 43 | 0.973°C | 1.025°C |
| 2026-06-30 | 39 | 0.987°C | 1.043°C |
| 2026-07-01 | 38 | 1.000°C | 1.040°C |
| 2026-07-02 | 39 | 1.003°C | 1.027°C |
| **2026-07-03** | **34** | **0.950°C** | **0.959°C** |

Today's sigma is ~5% below the 5-day baseline (~0.994°C). Within normal daily variation. **No proxy-lane alert.**

**5-city allowlist today**:

| City | Rows | Phase (PRE/POST) | Mode bucket | p_cal | Implied sigma |
|---|---|---|---|---|---|
| beijing | 99 | 83 / 16 | (33.5, 34.5) | 0.361 | 1.437°C |
| chengdu | 68 | 67 / 1 | (29.5, 30.5) | 0.380 | 1.354°C |
| london | 111 | 111 / 0 | (26.5, 27.5) | 0.380 | 0.856°C |
| munich | 70 | 70 / 0 | (25.5, 26.5) | 0.380 | 0.842°C |
| **wuhan** | **0** | **—** | **—** | **—** | **—** |

**Wuhan gap**: Zero pricer rows today. Market may not have opened, or pricer skipped it. Wuhan is in the 5-city ALLOW list — worth checking VPS logs.

Beijing and Chengdu show elevated sigma (1.4°C / 1.35°C) — consistent with being in peak hours at the 08:09 snapshot (real uncertainty before the day's max is set). London and Munich are at the isotonic plateau (0.380), moderate sigma.

---

## 3. DISPERSION GAUGE ⚠ ALERT PERSISTS

**This is the load-bearing quantity. The entire band edge rests on market-implied dispersion > realized dispersion.**

### Methodology note (critical)

The prior cycle computed dispersion from **d+2 fire records** with actual CLOB book prices. The s50 pricer data in the sandbox contains **only d+0 (same-day) markets** — all PRE_PEAK rows have t_close within < 1 day of ts. No d+1/d+2 pricer rows are present in s50.

This cycle computes from **d+0 PRE_PEAK data at T−2h to T−12h before close**:
- Closer to resolution → running_max is further along → mode bucket is usually correct → realized deviation is smaller (median 1.0°C vs prior's 2.0°C)
- **The d+0 ratio of 0.817 is an optimistic bound.** The prior's d+2 estimate of 0.340 is the operative figure for the YES positions currently active (BAND_YES_LIVE_MIN_DOUT=2).

Both methodologies confirm sub-1.10. The alert fires on all available data.

### Results (d+0, PRE_PEAK, T−2h to T−12h)

| Metric | Value |
|---|---|
| n city-date pairs | 125 |
| n finite ratios | 84 |
| Implied sigma (median) | 0.818°C |
| Realized deviation (median) | 1.000°C |
| **Disp ratio 7d median** | **0.817** |
| Alert threshold | 1.10 |
| **Status** | **🔴 ALERT** |

**By date** (no upward trend):

| Date | n | n_finite | Ratio | Impl sigma | Real dev |
|---|---|---|---|---|---|
| 2026-06-28 | 25 | 17 | 0.807 | 0.807°C | 1.000°C |
| 2026-06-29 | 28 | 19 | 0.663 | 0.794°C | 1.000°C |
| 2026-06-30 | 22 | 14 | 0.976 | 0.860°C | 0.917°C |
| 2026-07-01 | 26 | 17 | 0.866 | 0.807°C | 0.656°C |
| 2026-07-02 | 24 | 12 | 0.858 | 0.817°C | 1.000°C |

No day reaches 1.10. Oscillates 0.663–0.976. Jun 29 was the worst day. No recovery trend.

**5-city allowlist (d+0; n_finite per city is 2–3, collect-grade only)**:

| City | n | n_finite | Ratio | Impl sigma | Real dev |
|---|---|---|---|---|---|
| beijing | 5 | 2 | 0.157 | 0.738°C | (low n) |
| chengdu | 4 | 3 | 0.885 | 0.875°C | 1.000°C |
| london | 5 | 2 | 0.915 | 0.818°C | (low n) |
| munich | 5 | 3 | 0.614 | 0.903°C | 1.000°C |
| wuhan | 5 | 2 | 0.948 | 0.989°C | (low n) |

Beijing and Munich worst. Wuhan near break-even. City n is below 40 — collect, not trend-grade.

### Edge decay summary

| Cycle | Method | Ratio (all) | Ratio (d+2) |
|---|---|---|---|
| Prior (2026-07-02) | d+2 fire records + book prices | 0.408 | 0.340 |
| **This (2026-07-03)** | **d+0 PRE_PEAK p_cal** | **0.817** | **n/a** |

**The edge is decaying.** The market's ladder-implied uncertainty is consistently narrower than realized temperature variability. The band earns margin by selling overpriced wings — but sub-1.0 ratio means the wings are not overpriced; realized moves exceed implied spread. BAND_NO_ENABLED=False correctly removed NO exposure. YES-only at d+2 continues but faces the same structural headwind on the d+2 horizon (last known: 0.340).

---

## 4. ISOTONIC STALENESS ⚠ MATERIAL SHIFT (unchanged from prior)

| | Deployed | Candidate |
|---|---|---|
| Refit date | 2026-06-06 | 2026-06-09 |
| Age | 27 days | 24 days |
| n_hist | 76,617 | 76,617 |
| near_identity_maxdev | 0.568 | 0.626 |

**Grid comparison (key rows)**:

| grid | deployed | candidate | delta | flag |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 | |
| 0.05–0.10 | 0.070–0.134 | 0.076–0.141 | +0.006–0.007 | |
| 0.15–0.25 | 0.183–0.266 | 0.183–0.259 | < 0.008 | |
| 0.30–0.90 | 0.3801 | 0.3739 | −0.006 | (plateau, both stale) |
| 0.95 | 0.3822 | 0.3739 | −0.008 | |
| **1.00** | **0.6316** | **0.3739** | **−0.2577** | **← MATERIAL** |

Max |delta| = 0.2577 at grid=1.0. Candidate extends the plateau to the top of the confidence scale, collapsing the high-confidence signal from 0.632 → 0.374. All other deltas are below 0.05.

**Recommendation: DO NOT DEPLOY candidate** (unchanged). Deployed config is better despite age.

**Staleness concern (new this cycle)**: Both configs share identical n_hist=76,617, meaning the live-refit cron has not incorporated any live data since 2026-06-09. The cron may be stalled. ECE is passing (0.019), so this is not causing active harm — but a 27-day-old isotonic with zero live weight is operating in model drift territory. Recommend checking cron health on VPS (`journalctl -u isotonic-refit` or equivalent).

---

## 5. STATE TRANSITIONS

| Metric | Prior (2026-07-02) | This (2026-07-03) | Delta / Note |
|---|---|---|---|
| Brier7 | 0.0189 | 0.053 | ↑ (scope change: prior used broader city set; both OK) |
| ECE7 | 0.0382 | 0.019 | ↓ improved |
| Rank-rho | 0.9165 | 0.446 | ↓ (method change; both above threshold) |
| Disp ratio (all) | 0.408 (d+2 fires) | 0.817 (d+0 PRE_PEAK) | Not comparable — methodologies differ |
| Disp ratio (d+2) | 0.340 | n/a | No d+2 data in s50 |
| Bankroll | $76.31 | $79.57 | +$3.26 (+4.3%) |
| Consecutive wins | — | 5 | |
| BAND_NO_ENABLED | False | False | Unchanged |
| Alerts | S3, S4 | S3, S4 | Unchanged |

**Brier/rho changes are methodology artifacts, not calibration degradation.** Both metrics remain well inside thresholds on the same data.

---

## ALERTS (pre-registered only)

### 🔴 ALERT S3 PERSISTS — Dispersion ratio < 1.10

**7d median ratio = 0.817 (d+0); prior d+2 estimate = 0.340 (more relevant for active YES positions)**

The dispersion premium that the band harvests does not exist in this data window. Realized temperature variability (1.0°C median) exceeds the market's implied spread (0.818°C implied sigma). On the d+2 horizon the discrepancy is worse. No day in the 5-day window shows ratio ≥ 1.10. BAND_NO_ENABLED=False correctly removed NO exposure on 2026-07-02. YES-only at d+2 continues with an edge that is unvalidated in this data window.

Guarded live-refit cron owns any capital/parameter response. Do not edit strategy code.

### 🔴 ALERT S4 PERSISTS — Isotonic material shift, candidate worse

Candidate collapses p_cal at grid=1.0 from 0.632 → 0.374 (delta=−0.258). Extending the plateau to the top of the confidence range suppresses fire probability for the model's most confident predictions. Deployed is better.

Secondary: Both configs are 24–27 days stale with no live data incorporated. Live-refit cron appears inactive. ECE passing; no immediate crisis but refit cron health should be checked.

---

*calib-agent@klaus | 2026-07-03T08:xx UTC | Branch: claude/find-lag-parameter-rFQ0N*
