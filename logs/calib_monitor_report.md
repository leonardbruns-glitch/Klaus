# Klaus Calibration & Dispersion Monitor — 2026-07-16

**Run UTC:** 2026-07-16T~08:30Z (automated)  
**Snapshot:** 2026-07-16T08:04:40Z — `active` (passes abort check, <6h old)  
**Data access:** DEGRADED (git protocol blocked; GitHub MCP API used throughout; pricer_eval_s50 too large for MCP, brier7/ECE7/rho7 uncomputable)  
**Bankroll:** $31.07 | **Open positions:** 0 | **Band:** DARK (BAND_LIVE=False, 10+ days)

---

## 1. SETTLED LANE — Brier / ECE / Rank-Rho (7-day rolling)

**Status: UNCOMPUTABLE — carry-forward**

`stwa_pricer_eval_s50.jsonl` files are 1.4–1.7 MB each and exceed MCP inline limits. No resolution outcome data is accessible via the band_struct_lite path (obs_receipt.jsonl contains raw METAR readings, not market resolution flags; window_resolution.jsonl covers updown BTC/ETH/SOL only). This constraint has persisted for multiple consecutive sessions.

| Metric | Value | Source |
|---|---|---|
| brier7 | **0.053** | carry-forward from 2026-07-14 chain |
| ECE7 | null | uncomputable |
| rank-rho7 | null | uncomputable |

Reference: 2024-fit isotonic baseline Brier = 0.114. Carried 0.053 is below reference, but this number is stale and not trustworthy — it is a chain-carried estimate from a period when OOS data was briefly accessible and has not been refreshed in multiple sessions.

**No pre-registered alerts triggered in this lane** (n<40 resolved rows accessible; no decision-grade numbers available to fire thresholds).

---

## 2. PROXY LANE — p_cal vs Market Mid (early warning, unsettled)

**Status: PARTIAL — structural observation only**

From the band_struct_lite fire rows (n=15 for 2026-07-15 snapshot), the market's ask price for the **mode bucket** (offset=0) averages **0.255** (range 0.185–0.385). The deployed isotonic maps all p_raw ≥ 0.30 to p_cal = 0.3801. The divergence p_cal − market_mid ≈ **+0.12** for mode-bucket quotes.

Interpretation: the model is persistently pricing YES ~12 percentage points above where the market actually trades the mode. This directional overconfidence on the mode bucket has not closed in 5+ days of shadow quotes. This is consistent with the flat isotonic plateau: the model treats "most-likely outcome" as having a 38% YES probability, but the market prices it at ~26%.

No baseline computed (first measurement in this proxy lane format); cannot assess spike vs 7-day baseline.

---

## 3. DISPERSION GAUGE — Edge Health (most important) 🔴 ALERT FIRING

### Methodology
For each resolved-market snapshot, implied dispersion width is computed as the price-weighted standard deviation of bucket midpoints using the `ask` price distribution from `band_struct_lite` fire rows. True sigma = **1.3°C** (validated 2026-06, isothermal baseline).

**Dispersion ratio = implied_sigma / true_sigma**. Alert threshold: ratio < 1.10.

### Results — 5-day shadow measurement (2026-07-11 through 2026-07-15)

**n = 68 fire-row observations across 5 snapshot dates.**  
*n is below 100-grade threshold; trend-grade (40–99). No decision-grade conclusion, but directional finding is unambiguous.*

| Date | Median ratio | Fire rows | Note |
|---|---|---|---|
| 2026-07-11 | 0.814 | 18 | |
| 2026-07-12 | 0.736 | 14 | daily low |
| 2026-07-13 | 0.795 | 11 | |
| 2026-07-14 | 0.709 | 10 | daily low |
| 2026-07-15 | 0.817 | 15 | |
| **5-day median** | **0.765** | 68 | **ALL below 1.10** |

- **65 / 68 observations** have implied_sigma < true_sigma (edge is inverted, not merely compressed)
- **68 / 68 observations** are below the 1.10 alert threshold
- Minimum ratio observed: **0.611** (London d+2, 2026-07-12)
- Maximum ratio observed: **1.062** (single outlier only)

### By Days-Out

| Days-out | n | Implied sigma med | Ratio |
|---|---|---|---|
| d+0 | 3 | 1.042°C | 0.802 |
| d+1 | 23 | 0.954°C | 0.734 |
| d+2 | 42 | 1.116°C | 0.859 |

Near-term (d+1) is more compressed than d+2. d+0 sample too small (n=3).

### By Region

| Region | n | Ratio |
|---|---|---|
| EU (London, Munich) | 10 | 0.769 |
| Asia (Beijing, Shanghai, Seoul, Taipei, Chengdu, Wuhan, Chongqing) | 58 | 0.765 |

No regional divergence. Both regions equally inverted.

### Trend

First-half mean (Jul 11–12): 0.775 | Second-half mean (Jul 13–15): 0.774  
**Trend: flat / oscillating. No recovery signal whatsoever.**

### Interpretation

The band's load-bearing quantity — **market-implied dispersion exceeds true dispersion** — is not just compressed, it is **inverted**. The market is pricing temperature buckets with LESS spread than the actual temperature distribution warrants. A position-weighted YES band cannot extract premium from a market that is under-dispersed relative to truth. The edge the band was built on (validated 2026-06: true sigma ~1.3°C < implied) has flipped.

This is the **14th consecutive day** of inversion (S3 alert, now day 14).

**🔴 PRE-REGISTERED ALERT S3 FIRES — 14th consecutive day — ratio = 0.765 << 1.10 — no recovery signal — this is a FRESH DIRECT MEASUREMENT (not carry-forward)**

---

## 4. ISOTONIC CALIBRATION STALENESS 🔴 ALERT FIRING

### Deployed (`config/stwa_isotonic.json`, refit 2026-06-06 — **40 days ago**)

| p_raw range | p_cal | Shape |
|---|---|---|
| 0.00 | 0.0000 | — |
| 0.05–0.10 | 0.07–0.13 | rising |
| 0.15–0.25 | 0.18–0.36 | rising |
| **0.30–0.90** | **0.3801** | **FLAT PLATEAU** |
| 0.95 | 0.3822 | plateau |
| **1.00** | **0.6316** | **SPIKE** |

The deployed model has a near-identity relation below p_raw=0.30, then a hard ceiling at ~38%, then a single-point spike at p_raw=1.0 (certainty spike to 63%). `near_identity_maxdev` = 0.568 — extreme deviation from the identity map.

### Candidate (`config/stwa_isotonic_candidate.json`, refit 2026-06-09 — **37 days ago**)

n_live = 1,037 rows over 2 calendar days. All `brier_live_oos_*` = null (no OOS validation).

The candidate **removes the certainty spike entirely**: p_raw=1.0 → p_cal=0.3739 (same as the plateau). The plateau itself is slightly lower (0.3739 vs 0.3801 deployed). A low-end floor is added (p_raw=0 → p_cal=0.0175 vs deployed 0.0).

**Max absolute diff: 0.2577 at p_raw=1.0 (deployed 0.6316 → candidate 0.3739).**  
Direction: candidate LOWERS p_cal for any market scoring p_raw ≥ 0.30 (−0.0062 across plateau, −0.2577 at p_raw=1.0).

### Staleness Assessment

| | Deployed | Candidate |
|---|---|---|
| Refit date | 2026-06-06 | 2026-06-09 |
| Days since refit | **40** | **37** |
| n_live rows | 0 | 1,037 |
| n_hist | 76,617 | 76,617 |
| OOS validation | null | null |
| near_identity_maxdev | 0.568 | 0.626 |

Neither version has OOS Brier validation. The candidate adds 1,037 live rows but is itself 37 days old — not recently refit. The `near_identity_maxdev=0.626` for the candidate (worse than deployed 0.568) reflects the candidate's even flatter shape.

**The material structural difference (0.2577) and absence of any deployment decision in 37 days: pre-registered S4 alert fires.**

**🔴 PRE-REGISTERED ALERT S4 FIRES — candidate max_dev=0.2577 at p_raw=1.0 — removes certainty spike 0.6316→0.3739 — 37 days without deployment review — candidate itself 37 days stale with no OOS validation**

---

## 5. STATE — Transitions vs Prior (2026-07-15)

| Metric | Prior (2026-07-15) | Today (2026-07-16) | Change |
|---|---|---|---|
| brier7 | 0.053 (carry) | 0.053 (carry) | no change |
| ECE7 | null | null | no change |
| rho7 | null | null | no change |
| disp_ratio7 | ≤0.80 (carry-forward estimate) | **0.765 (FRESH, n=68)** | first direct measurement |
| disp_inversion_days | 13 | **14** | +1 |
| S3 alert | firing (d13) | **firing (d14)** | persisting |
| S4 alert | firing (37d) | **firing (37d → 40d deployed)** | persisting |
| band dark days | 9+ | **10+** | +1 |
| data_access | DEGRADED | DEGRADED | no change |

**Key transition today:** `disp_ratio7` upgraded from `≤0.80 carry-forward` to **0.765 direct measurement** — first time this has been computed directly (not inferred) since the band went dark. This is a stronger basis for S3 than prior carry-forward estimates.

---

## ALERTS

| ID | Condition | Status | Days active |
|---|---|---|---|
| S3 | disp_ratio7 < 1.10 | **FIRES — ratio = 0.765** | **Day 14** |
| S4 | isotonic candidate max_dev > 0.05 | **FIRES — max_dev = 0.2577** | **37+ days** |

---

## Recommendations (monitor-only; no code edits)

1. **S3 — Dispersion edge is inverted.** The guarded live-refit cron on VPS should evaluate whether the market pricing regime has structurally shifted since the 2026-06 validation. If implied dispersion has inverted, the band's statistical edge is gone regardless of calibration quality.

2. **S4 — Isotonic candidate is also stale.** The candidate (n_live=1,037, 2 calendar days, 37 days ago) was not recently refit and lacks OOS validation. Deploying it eliminates the certainty spike but produces an even flatter calibration curve (near_identity_maxdev=0.626). A fresh refit with current live data is recommended before any deployment decision.

3. **Brier7 gap** — brier7 has been carried forward for multiple sessions and is no longer a reliable signal. It should be refreshed with a direct resolution-join computation when pricer_eval_s50 files become accessible (requires larger MCP payload support or a direct SSH data pull path).
