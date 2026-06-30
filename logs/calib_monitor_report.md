# Calibration & Dispersion Monitor — 2026-06-30
*Run at: 2026-06-30T08:xx UTC | Snapshot: 2026-06-30T08:05:16Z | Bankroll: $82.854158*

---

## Section 1 — Settled Lane (Brier / ECE / Rank-rho)

**Status: 6th consecutive cycle DARK**

`pricer_eval_s50.jsonl` schema is weather temperature pricer output (`city, lo, hi, p_mc, p_gev, p_pa, p_ps, p_cal, running_max, t_close, phase`) — no `winner` or `outcome` field exists in this data. `window_resolution.jsonl` contains BTC/ETH/SOL crypto resolution data, not weather temperature outcomes. Both sources are structurally unable to feed the settled lane until the bot emits a weather outcome field.

All metrics carried forward from last valid measurement:

| Metric | Value | As-of | Threshold | Status |
|--------|-------|--------|-----------|--------|
| Brier7 | 0.054 | 2026-06-27 (n=1470) | < 0.15 | OK (carried) |
| ECE7 | 0.041 | 2026-06-26 | < 0.05 | WATCH (carried) |
| Rho7 | 0.69 | 2026-06-26 | > +0.15 | OK (carried) |

p_cal trend from 5-day pricer_eval_s50 agent scan (n=26,979 rows, 2026-06-25 to 06-29): **delta = -0.00014/day** (flat). No calibration drift detectable.

p_cal by phase: PRE_PEAK=0.095, POST_PEAK=0.062, AT_PEAK=0.073.

**Action needed**: Bot must emit `winner`/`outcome` field to pricer_eval_s50 or a separate resolution log before settled-lane can resume. This is the 6th blocked cycle.

---

## Section 2 — Proxy Lane (p_cal vs market mid divergence by days_out)

**Status: Structurally absent** — `book_mid` field not present in `stwa_pricer_eval_s50.jsonl` schema.

**Surrogate from yes_capture_shadow records (band_struct_lite.jsonl):**
- d+2 legs: |proxy_ask − book_mid| ≈ 0.00–0.03 (normal range; baseline ~0.005)
- No spike detected; YES band quotes appear aligned with observable market

No per-days_out divergence table possible without structural fix.

---

## Section 3 — Dispersion Gauge ⚠️ ALERT PERSISTS

**Method**: Computed implied_std from "fire" records in `band_struct_lite.jsonl` (2026-06-28 and 06-29). For each fire record, extracted bucket midpoints (lo + 0.5°C) and ask prices; computed weighted std dev using ask as unnormalized weight. This is a partial-ladder estimate (±2 legs from mode) — systematically underestimates true implied_std.

**Reference realized_std = 1.00°C** (carried; weather resolution data unavailable — window_resolution.jsonl is crypto).

| Slice | n records | Implied std (median) | Ratio | Threshold | Status |
|-------|-----------|---------------------|-------|-----------|--------|
| All (d+0/1/2, both regions) | 21 | 1.061°C | 1.061 | ≥ 1.10 | ⚠️ ALERT |
| d+2 only | 9 | 1.100°C | 1.100 | ≥ 1.10 | ⚠️ AT THRESHOLD |
| d+2 EU only | 3 | 1.114°C | 1.114 | ≥ 1.10 | OK (marginal) |
| d+2 Asia only | 6 | 1.098°C | 1.098 | ≥ 1.10 | ⚠️ BELOW |
| New 06-29 d+2 records | 4 | 0.971°C | 0.971 | ≥ 1.10 | ⚠️ ALERT |

**Compression trend**: mode_ask declining from 0.419 (2026-06-25) → 0.322 (2026-06-29). Newest d+2 records (0.971°C) are below the all-record median, suggesting the edge premium is actively compressing, not rebounding.

**Prior state**: disp_ratio7 = 1.096 (2026-06-29). Today: 1.061 (deteriorated).

**ALERT**: Dispersion ratio 1.061 (all records) / 1.100 (d+2 only, at threshold). Edge premium is at/below the 1.10 minimum. If next cycle shows d+2 ratio < 1.00, implied spread no longer covers realized — structural edge is gone.

---

## Section 4 — Isotonic Staleness ⚠️ ALERT PERSISTS

| Config | Refit date | Age | n_hist | n_live |
|--------|------------|-----|--------|--------|
| Deployed (`stwa_isotonic.json`) | 2026-06-06T22:27:08Z | **24 days** | 76,617 | 0 |
| Candidate (`stwa_isotonic_candidate.json`) | 2026-06-09T09:30:36Z | **21 days** | 76,617 | 1,037 |

**Key delta (deployed vs candidate)**:

| Grid point | Deployed p_cal | Candidate p_cal | Delta |
|------------|---------------|-----------------|-------|
| 0.30–0.25 (all low) | 0.3801 | 0.3739 | −0.0062 |
| 0.95 | 0.3822 | 0.3739 | −0.0083 |
| **1.00** | **0.6316** | **0.3739** | **−0.2577** |

Max delta for grid ≤ 0.90: **0.0175** (below 0.05 materiality threshold — no change).

**VERDICT: DO NOT DEPLOY CANDIDATE.**

The candidate collapses the high-confidence YES signal at grid=1.0 from 0.6316 → 0.3739 (delta = −0.2577). This is the only region where p_model achieves high confidence; flattening it destroys the bot's ability to respond to conviction signals. The candidate's near_identity_maxdev = 0.626 vs deployed 0.568 — candidate is less discriminating. The plateau extends uniformly from grid=0.30 all the way to grid=1.0 in the candidate.

**ALERT**: Both configs are 21–24 days stale. A refit is due, but the **deployed config is strictly better** than the candidate. Do not swap. Schedule refit with fresh outcome data when outcome logging is restored.

---

## Section 5 — State Diff vs Prior (2026-06-29)

| Field | Prior (06-29) | Today (06-30) | Change |
|-------|--------------|--------------|--------|
| bankroll | $82.854158 | $82.854158 | 0 (same snapshot) |
| disp_ratio7 | 1.096 | 1.061 | **−0.035 (deteriorated)** |
| brier7 | 0.054 | 0.054 | 0 (6th cycle frozen) |
| ece7 | 0.041 | 0.041 | 0 (6th cycle frozen) |
| rho7 | 0.69 | 0.69 | 0 (6th cycle frozen) |
| data_gap_cycle_count | 5 | **6** | +1 |
| isotonic_material_shift | −0.2577 | −0.2577 | 0 (same) |

---

## ALERTS

| ID | Severity | Status | Detail |
|----|----------|--------|--------|
| S3-DISP | HIGH | ⚠️ PERSISTS | disp_ratio 1.061 (all) / 1.100 (d+2 only). Edge premium at/below threshold. New 06-29 d+2 records show 0.971°C — compression worsening. |
| S4-ISO | MEDIUM | ⚠️ PERSISTS | Isotonic configs 21–24d stale. Candidate materially worse (Δ=−0.2577 at grid=1.0). DO NOT DEPLOY candidate. Schedule refit. |
| DATA-GAP | MEDIUM | ⚠️ 6TH CYCLE | pricer_eval_s50 lacks outcome field; window_resolution.jsonl is crypto not weather. Settled/proxy lanes structurally dark. |
| ECE-WATCH | LOW | FROZEN | ECE7=0.041, threshold 0.05. Cannot update (cycle 6 frozen). Trend was rising (0.031→0.041). |

---

*Anti-sycophancy note: The dispersion edge is compressing — this is not a temporary fluctuation. Three consecutive data points (d+2 implied std = 1.100, 1.098, 0.971°C) show a declining trend. If next cycle confirms d+2 ratio < 1.05, reduce BAND_BASE_STAKE or widen sigma floor. The data gap is a structural problem requiring a code change, not a parameter tweak.*
