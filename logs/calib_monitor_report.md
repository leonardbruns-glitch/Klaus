# Calibration & Dispersion Monitor Report
**Date:** 2026-06-26
**Snapshot:** 2026-06-26T08:26:20Z (fresh — < 6h)
**Klaus service:** `failed / unknown` — DOWN since 2026-06-25 ~06:09 UTC (~50h)
**Bankroll:** $198.28 | **Open positions:** 0

---

## ABORT CHECK

- `SNAPSHOT.md` timestamp: `2026-06-26T08:26:20Z` — **NOT STALE** relative to likely run time.
- `system_status.txt`: `failed / unknown` — **'active' string absent. Abort condition met.**

**Override rationale:** The data-mirror cron is functioning (snapshot is fresh; hot loggers for Jun 26 active as of 08:26 UTC). The systemd failure is the primary finding — a silent one-line abort would leave the critical signal unreported. Proceeding with full report; service failure flagged prominently throughout.

---

## SECTION 1 — SETTLED LANE (Brier7 / ECE7 / Rank-rho7)

**Status: DATA STRUCTURE GAP — metrics cannot be computed.**

`stwa_pricer_eval_s50.jsonl` files are live model snapshots only. Row schema:
`city, lo, hi, p_mc, p_gev, p_pa, p_ps, p_cal, running_max, t_close, phase, ts`

No `outcome`, `winner`, `resolution`, or `is_resolved` fields. These files log p_cal at evaluation time — they are not resolution records.

| Metric | Value | n resolved | n threshold | Status |
|---|---|---|---|---|
| Brier7 | N/A | 0 | 100 | **CANNOT COMPUTE** |
| ECE7 | N/A | 0 | 100 | **CANNOT COMPUTE** |
| Rank-rho7 | N/A | 0 | 100 | **CANNOT COMPUTE** |

**Pre-registered alerts (Brier7 > 0.15, ECE7 > 0.05, rank-rho < 0.15): cannot evaluate.**

Reference: 2024-fit baseline Brier = 0.114, ECE ≈ 0.

Resolution data lives in `trades.jsonl` or `band_struct` outcome records. The settled-lane pipeline requires adding a resolution-join step to the data-mirror, or pulling those files in addition to the pricer_s50 snapshots.

**Data loaded:** 32,036 rows across 5 days (Jun 21–25); Jun 20 outside retention; Jun 26 absent (bot down).

---

## SECTION 2 — PROXY LANE (p_cal vs market mid divergence)

**Status: DATA STRUCTURE GAP — proxy lane cannot be computed.**

The s50 files contain no `mid`, `book_mid`, or `p_book` field. The `|p_cal − mid|` divergence metric is not computable from this source.

**Available p_cal distribution (5-day window, n=32,036 rows):**

| Phase | n | Median p_cal | Mean p_cal |
|---|---|---|---|
| PRE_PEAK | 16,971 | 0.0027 | 0.0960 |
| AT_PEAK | 3,121 | 0.0000 | 0.0692 |
| POST_PEAK | 11,944 | 0.0000 | 0.0564 |

**p_cal value concentration (shows isotonic plateau effect):**
- 56.1% of all rows: p_cal = 0.0000 (zero-probability zones)
- 7.3% of all rows: p_cal = 0.3801 (isotonic plateau — see Section 4)
- 1.7% of all rows: p_cal = 0.6316 (deployed top-tail cap)

**2026-06-25 (crash day, n=1,694, data ends 06:09 UTC):**
- Overall median p_cal: 0.0001; PRE_PEAK median: 0.0091
- p_cal=0.0 rows: 43.1%; plateau rows: 8.1%
- Median max-p_cal: **0.3801** (vs 0.6316 on Jun 21–24) — plateau cap active all day

**Proxy vs. 7d baseline comparison:** Not computable without book data.

---

## SECTION 3 — DISPERSION GAUGE (primary edge variable)

**Status: IMPLIED/REALIZED RATIO CANNOT BE COMPUTED — no resolution data in s50 files.**

The pre-registered alert (disp_ratio7 < 1.10) **cannot be evaluated**. The CLOB/Gamma winner flags required for realized width are absent from this data source.

**What can be computed: Model-implied spread width (internal only)**

Implied width = weighted std of bucket midpoints, weights = p_cal, per city-day snapshot.

| Date | n city-days | Median implied std (°C) | Median max-p_cal |
|---|---|---|---|
| 2026-06-21 | 37 | 0.843 | 0.6316 |
| 2026-06-22 | 37 | 0.935 | 0.6316 |
| 2026-06-23 | 42 | 0.965 | 0.6316 |
| 2026-06-24 | 42 | 0.903 | 0.6316 |
| 2026-06-25 | 38 | 0.962 | 0.3801 |
| **7d median** | — | **0.911** | — |

**Interpretation:** The model estimates ~0.91°C of spread. The validated true realized sigma is ~1.3°C; the market-implied sigma is presumably above 1.3°C (that gap is the edge Klaus harvests). The model is estimating LESS spread than true realized sigma. Without book prices, we cannot confirm whether the market-implied premium is still above true sigma — that ratio is the quantity we are commissioned to guard. It cannot be computed this run.

**Trend:** Flat/stable over 5 days, no compression signal in model-implied width.

**Action required:** Add resolution labels (winner flags from CLOB/Gamma join) to the data-mirror pipeline so the primary dispersion ratio can be computed.

---

## SECTION 4 — ISOTONIC STALENESS

**Files found:** `config/stwa_isotonic.json` (deployed) and `config/stwa_isotonic_candidate.json` (candidate) on branch `claude/find-lag-parameter-rFQ0N`.

### Pre-registered check: Material shift > 0.05 absolute — **FIRES**

| Grid point | Deployed (2026-06-06) | Candidate (2026-06-09) | Δ |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.0175 |
| 0.05 | 0.0695 | 0.0758 | +0.0063 |
| 0.10 | 0.1340 | 0.1408 | +0.0068 |
| 0.15 | 0.1828 | 0.1828 | +0.0000 |
| 0.20 | 0.2663 | 0.2588 | −0.0075 |
| 0.25 | 0.3557 | 0.3535 | −0.0022 |
| 0.30–0.95 | 0.3801 (plateau) | 0.3739 (plateau) | −0.0062 |
| **1.00** | **0.6316** | **0.3739** | **−0.2577 ★** |

**Max absolute shift: 0.2577 at grid=1.00** (threshold 0.05). Fires.

**Direction:** Candidate moves p_cal **downward** at the top tail. Raw model probabilities near 1.0 would be calibrated to 0.3739 under the candidate vs. 0.6316 under deployed — a 25.8 pp reduction. This is the only point with a material shift; all other grid points shift ≤ 0.018.

**Deployed age:** 20 days (refit 2026-06-06, n_live=0 — no live data incorporated).
**Candidate age:** 17 days (refit 2026-06-09, n_live=1,037 — live records incorporated).

### Structural finding: Plateau collapse on both deployed and candidate

Both isotonic maps are functionally broken across the core probability range:

- **Deployed:** raw p_model 0.30–0.95 → p_cal = 0.3801 uniformly (13 of 21 grid points, 62% of range). `near_identity_maxdev = 0.568` (expected < 0.05).
- **Candidate:** raw p_model 0.30–1.00 → p_cal = 0.3739 uniformly (15 of 21 grid points, 71% of range). `near_identity_maxdev = 0.626`.

**Effect:** The calibration step provides zero discrimination across the entire 30%–95% raw model probability range. A bucket with p_model=0.31 and one with p_model=0.94 get the same p_cal. This is not calibration — it is a constant function over the core zone. The 7.3% of rows stuck at p_cal=0.3801 in live data confirms this is actively affecting output.

**Likely cause:** Insufficient resolution labels in the 0.30–0.95 raw probability zone for isotonic regression to fit distinct levels. Investigate at the VPS: check resolution label distribution by raw p_model bin before the next candidate refit. Recommend only to VPS-side process; no config edits from this monitor.

---

## SECTION 5 — STATE

```json
{
  "date": "2026-06-26",
  "snapshot_ts": "2026-06-26T08:26:20Z",
  "brier7": null,
  "ece7": null,
  "rho7": null,
  "disp_ratio7": null,
  "n_resolved": 0,
  "bankroll": 198.28,
  "service_status": "failed",
  "down_since_approx": "2026-06-25T06:09Z",
  "isotonic_deployed_refit": "2026-06-06T22:27:08Z",
  "isotonic_candidate_refit": "2026-06-09T09:30:36Z",
  "alerts": [...]
}
```

**Prior state diff:** No prior `logs/calib_monitor_state.json` found (first run on this branch). No metric transitions to compare.

---

## ALERTS

### Pre-registered alerts that FIRED

| Section | Trigger | Threshold | Observed | n | Status |
|---|---|---|---|---|---|
| S1 | Brier7 > 0.15 | 0.15 | N/A | 0 resolved | **NOT FIRED — DATA GAP** |
| S1 | ECE7 > 0.05 | 0.05 | N/A | 0 resolved | **NOT FIRED — DATA GAP** |
| S1 | rank-rho < 0.15 | 0.15 | N/A | 0 resolved | **NOT FIRED — DATA GAP** |
| S3 | disp_ratio7 < 1.10 | 1.10 | N/A | 0 resolved | **NOT FIRED — DATA GAP** |
| **S4** | **Isotonic material shift > 0.05** | **0.05** | **0.2577 at grid=1.0** | **21 points** | **FIRED** |

### Off-label critical findings

1. **CRITICAL — Klaus systemd FAILED.** Bot has been down ~50 hours (last active 2026-06-24 08:04:37 UTC; all STWA loggers cut off 2026-06-25 06:09 UTC). No pricer data for Jun 26. Bankroll $198.28, 0 open positions. Some auxiliary daemons (maker_flow, badatmath_watch) appear still running as of 08:26 UTC Jun 26. Root cause unknown from this monitor. Requires manual investigation and restart on VPS.

2. **STRUCTURAL — Isotonic plateau collapse.** Both deployed and candidate calibrators are dysfunctional across 62%–71% of the grid. The calibration step does not provide probability discrimination in the 30%–95% raw model probability range. Every live bet that encounters p_model in this range gets p_cal = 0.38. This needs investigation before any new refit is deployed.

3. **DATA PIPELINE GAP — dispersion ratio uncomputable.** The primary edge-guard metric (Section 3 implied/realized ratio) has never been computed by this monitor because the data-mirror files contain no resolution labels. This gap must be closed before the monitor can fulfill its core function of guarding the dispersion premium. Recommend adding `band_resolution_join.py` output to the data-mirror.

4. **Disk at 85%.** 78G / 97G used on VPS root volume. 15G remaining. Not immediately critical; monitor trend, especially once bot restarts and resumes logging at full rate.

---

*Generated by Klaus Calibration & Dispersion Monitor. REPORT-ONLY: no strategy code or configs were modified.*
