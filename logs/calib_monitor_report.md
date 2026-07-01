# Calibration & Dispersion Monitor — 2026-07-01

**Run time:** 2026-07-01T08:05:18Z  
**Bankroll:** $86.59 (+$3.73 since yesterday's $82.85)  
**Service:** active  
**Data window:** Jun 26–30 resolved; Jul 01 partial (snapshot 08:05 UTC, Asian markets close 15:59 UTC)

---

## DATA GAP STATUS — RESOLVED

The settled lane has been **frozen for 7 cycles** (since Jun 24) due to missing outcome data. This cycle breaks the freeze.

**Method:** `phase=POST_PEAK` rows in `pricer_eval_s50` have `running_max` = actual daily high. Winner bucket inferred as bucket where `lo ≤ running_max < hi`. This is a proxy (assumes Chainlink uses same temperature sensor as pricer), not a direct CLOB resolution read.

**Coverage:** 25 resolved (city, date) pairs × 5 cities × Jun 26–30. 253 (city, date, bucket) rows used for settled-lane metrics.

---

## STEP 1 — SETTLED LANE

| Metric | This Cycle | Prior (frozen) | Status |
|---|---|---|---|
| Brier7 | **0.0139** | 0.054 (carried) | ✅ Updated; strong |
| ECE7 | **0.0361** | 0.041 (carried) | ✅ Updated; improving |
| Rank-rho7 | **0.83** | 0.69 (carried) | ✅ Updated; recovering |
| n | 253 buckets | 1470 (Jun 24) | — |

**ECE bin detail:**

| Bin | n | mean_p_cal | mean_outcome | \|diff\| |
|---|---|---|---|---|
| [0.0, 0.1) | 229 | 0.0001 | 0.0000 | 0.0001 |
| [0.4, 0.5) | 1 | 0.4073 | 1.0000 | 0.5927 |
| [0.6, 0.7) | 23 | 0.6295 | 1.0000 | 0.3705 |

All winner buckets have p_cal at the isotonic plateau (0.6316 deployed). 24 winner buckets correctly identified. One edge case: a bucket resolved at p_cal=0.41 (model slightly underconfident on that market).

**Interpretation:** Settled lane metrics look healthy. Brier 0.014 is excellent for a 1°C-bucket binary market. ECE 0.036 is below the 0.05 watch threshold (cleared). Rho 0.83 shows strong rank ordering despite isotonic plateau compressing the high-confidence range.

---

## STEP 2 — PROXY LANE

*Book prices absent from `pricer_eval_s50` schema (structural — persists). Cannot compute true p_cal vs market_mid divergence.*

**p_cal distribution (active cities, PRE_PEAK+AT_PEAK rows):**

| Horizon | n | mean_p_cal | median | high_conf (>0.5) |
|---|---|---|---|---|
| d+0 (<12h) | 1299 | 0.085 | 0.000 | 24 |
| d+1 (12–36h) | 2149 | 0.104 | 0.017 | 0 |

High-confidence d+0 rows: all 24 at isotonic plateau 0.6316. No high-confidence d+1 forecasts (max=0.420) — expected at that horizon.

**Mode_ask from converged records (active cities, n=48):**

| days_out | n | median_ask |
|---|---|---|
| d+0 | 38 | 0.348 |
| d+1 | 4 | 0.455 |
| d+2 | 6 | 0.493 |

Mode ask approaching 0.50 at d+2 (maximum uncertainty). d+0 median 0.348 is in the fee-efficient zone below the 0.35 extreme-odds threshold.

---

## STEP 3 — DISPERSION GAUGE ⚠️ ESCALATED ALERT

**This is the primary edge variable. Prior state was already AT threshold (1.061). Current state: 0.470 — collapsed.**

### All days_out (n=23 fire records with resolved markets, Jun 26–30):

| Metric | This Cycle | Prior (Jun 30) | Change |
|---|---|---|---|
| median implied_std | **0.939°C** | 1.061°C | −0.122°C |
| median realized_abs | **2.000°C** | 1.000°C | +1.000°C |
| **Dispersion ratio** | **0.470** | **1.061** | **−0.591** |

### d+2 only (n=9):

| Metric | This Cycle | Prior | Change |
|---|---|---|---|
| median implied_std | **1.100°C** | 1.100°C | flat |
| median realized_abs | **2.000°C** | 1.000°C | +1.000°C |
| Dispersion ratio | **0.550** | **1.100** | **−0.550** |

### ALERT: ratio 0.470 << 1.10 threshold

The band's implied spread (±0.94°C) is **less than half** the actual forecast error (median 2.0°C). The central temperature forecast (mode bucket) is regularly landing 2–4°C from the resolved temperature.

### By city:

| City | n | med_implied | med_realized | ratio | Status |
|---|---|---|---|---|---|
| Beijing | 4 | 0.97°C | 3.50°C | **0.278** | WORST |
| Chengdu | 8 | 0.93°C | 3.00°C | **0.310** | BAD |
| London | 1 | 0.82°C | 2.00°C | **0.408** | BAD (n=1) |
| Munich | 5 | 0.94°C | 1.00°C | **0.939** | Near break-even |
| Wuhan | 5 | 0.97°C | 1.00°C | **0.969** | Near break-even |

### Out-of-ladder resolutions: 12/23 fire records (52%)

The band's ladder covers only 3–5 buckets around the mode. In 12 of 23 cases, the resolved temperature fell **entirely outside** the quoted range.

**Systematic misses:**
- Chengdu Jun 29: band mode=27.0°C, resolved=33.0°C. 6°C error.
- Chengdu Jun 30: band mode=28–29°C (multiple fires), resolved=32.0°C. 3–4°C error.
- Beijing Jun 29: band mode=24.0°C, resolved=27.0°C. 3°C error.
- Beijing Jun 30: band mode=26°C, resolved=30°C. 4°C error.

**Root cause hypothesis:** Band temperature pricer is cold-biased for Beijing and Chengdu in late June. Likely underestimates the 2026 heat wave conditions. Munich and Wuhan track reality well (ratios near 1.0).

**Implication for edge:** The band's edge premise requires implied_std > true_sigma. True sigma is ~2°C for Beijing/Chengdu. Implied_std is only ~0.94°C. The band is selling too-narrow insurance centered on the wrong temperature.

---

## STEP 4 — ISOTONIC STALENESS

No change from prior cycle (same files on branch).

| Grid | Deployed | Candidate | Delta |
|---|---|---|---|
| 0.30–0.95 | 0.3801 (plateau) | 0.3739 (plateau) | −0.0062 |
| 1.00 | **0.6316** | **0.3739** | **−0.2577** |

- Max delta (grid ≤ 0.90): 0.0175 — below 0.05 threshold
- Delta at grid=1.0: −0.2577 — above 0.05 threshold → material shift

**Recommendation: DO NOT DEPLOY candidate.** Candidate collapses the high-confidence signal and has worse `near_identity_maxdev` (0.626 vs 0.568 deployed).

---

## STEP 5 — ALERTS SUMMARY

### ESCALATED S3: Dispersion collapse
- Prior: ratio=1.061 (at threshold)
- Current: ratio=0.470 (far below 1.10 threshold)
- d+2 ratio: 0.550 (prior was 1.100 at threshold)
- 52% of fire records resolved outside ladder range
- Beijing/Chengdu band central forecast systematically cold by 3–4°C
- ACTION REQUIRED: Review band temperature pricer for Beijing/Chengdu; investigate heat-wave climatology offset. Munich/Wuhan performing adequately.

### PERSISTS S4: Isotonic candidate divergence at high confidence
- DO NOT DEPLOY candidate
- No change from prior cycle

### DATA GAP RESOLVED
- 7 consecutive frozen cycles broken via POST_PEAK running_max inference
- n=253 buckets, 25 (city, date) resolved markets
- Caveat: proxy method, not direct CLOB resolution data

### ECE WATCH CLEARED
- ECE7 updated: 0.036 (was 0.041 carried forward)
- Below 0.05 threshold; improving trend

---

## BANKROLL NOTE

$86.59 (+$3.73 since yesterday). Positive P&L despite dispersion concerns. Band is firing and executing. The NO-share of 80% (from prior exec audit) suggests the band is finding value on wing buckets rather than mode buckets — partially consistent with mode being wrong. P&L impact of central-forecast miss may be partially offset by NO bets on non-mode legs.

---

*Report generated by calib_monitor routine | Branch: claude/find-lag-parameter-rFQ0N | Data: data-mirror branch*
