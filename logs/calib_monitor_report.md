# Calibration & Dispersion Monitor — 2026-07-07

**Snapshot**: 2026-07-07T08:02:06Z (age ~8 min ✓)
**System**: `active` ✓ | **Bankroll**: $42.02 (drop from $123.32 prior snapshot — PnL-monitor scope) | **Open positions**: 0

**Trading mode**: BAND_LIVE=**False** (charter drawdown rail: equity $108.35 < 50%·HW $222.90 at wind-down) | BAND_NO=**False** (rail-halt Jul 2) | BAND_YES standalone **PAUSED** (min_dout=9) | PAIR_FAV **shadow** | BAND_PAIR_SHADOW=True

---

## 1. SETTLED LANE (confirmed labels)

**Status: 7d window LOCKED at Jun 28–Jul 2 — FIFTH consecutive stale day.**

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Brier7 | **0.053** | < 0.15 | ✅ OK (stale day 5) |
| ECE7 | **0.019** | < 0.05 | ✅ OK (stale day 5) |
| Rank-rho (Spearman) | **0.446** | > 0.15 | ✅ OK (stale day 5) |

These values are unchanged since 2026-07-02. They represent Jun 28–Jul 2 resolved market-days (n=36,551 sampled rows at 1-in-50, ~1.83M underlying events). The 30d reference baseline is Brier=0.114, ECE≈0.

**Root cause of stale window**: The `stwa_pricer_eval_s50.jsonl` contains no `condition_id` or outcome labels. The Gamma API join (`analysis/weather/band_resolution_join.py`) runs on the VPS, not in this agent. Jul 3–Jul 7 pricer data has been ingested but cannot be matched to resolution outcomes here.

**Risk**: These metrics remain healthy on stale data. Calibration could have degraded since Jul 2 without detection. The path to resolution requires the VPS join or a `condition_id` field added to the s50 log.

---

## 2. PROXY LANE (early warning — unsettled days)

Analysis of 2026-07-07 `stwa_pricer_eval_s50` (2,059 rows, 08:10 UTC snapshot, PRE_PEAK phase for most allowlist cities).

**Method**: Accumulate all rows per city; keep latest `p_cal` per bucket (lo, hi); compute implied sigma = sqrt(Σ p_cal·(mid−μ)²/Σ p_cal). Sentinel handling: lo<0 → mid=hi−0.5; hi≥500 → mid=lo+0.5. Plateau exclusion: cities with ≥2 buckets at exactly p_cal=0.3801 flagged (isotonic plateau artifact).

| City | σ_cal | σ_mc | plat_hits | phase | Status |
|---|---|---|---|---|---|
| amsterdam | 0.822 | 0.640 | 1 | PRE_PEAK | CLEAN |
| ankara | 1.409 | 1.132 | 0 | PRE_PEAK | CLEAN |
| beijing | 0.562 | 0.643 | 1 | AT_PEAK | CLEAN |
| chengdu | 0.778 | 0.675 | 1 | PRE_PEAK | CLEAN |
| istanbul | 0.793 | 0.800 | 2 | PRE_PEAK | EXCL(plat) |
| kuala-lumpur | 0.235 | 0.175 | 0 | AT_PEAK | CLEAN |
| london | 0.818 | 0.701 | 2 | PRE_PEAK | EXCL(plat) |
| munich | 0.923 | 0.976 | 2 | PRE_PEAK | EXCL(plat) |
| paris | 0.988 | 0.743 | 2 | PRE_PEAK | EXCL(plat) |
| singapore | — | — | — | MISSING | — |
| taipei | 1.215 | 1.279 | 1 | PRE_PEAK | CLEAN |
| wuhan | 1.098 | 0.969 | 1 | AT_PEAK | CLEAN |

**Plateau filter note**: Istanbul, London, Munich, Paris excluded today due to ≥2 plateau hits. Prior state (Jul 6) included all 12 cities using a looser method. Singapore absent from Jul 7 s50 (was present Jul 6 at 0.501). The median is 0.822 both with (n=7) and without (n=11) the plateau filter — the result is robust.

**Result**: median σ_cal = **0.822** (n=7 plateau-filtered; n=11 all-computable — same value)

### 6-day declining trend

| Date | median σ_cal | vs baseline |
|---|---|---|
| Jul 2 | 0.994 | baseline |
| Jul 3 | 0.950 | −4.4% |
| Jul 4 | 0.906 | −8.8% |
| Jul 5 | 0.885 | −11.0% |
| Jul 6 | 0.862 | −13.3% (prior state 12-city method) |
| **Jul 7** | **0.822** | **−17.3%** |

**Day 6 consecutive below-baseline.** Trend not arrested; steepening.

---

## 3. DISPERSION GAUGE (edge variable — most important)

**Status: ALERT PERSISTS — 7d median ratio = 0.817 — DAY 5 STALE.**

### Resolved days (Jun 28–Jul 2 — the locked window)

| Date | n_finite | ratio (impl/realized) | impl σ (°C) | realized σ (°C) |
|---|---|---|---|---|
| Jun 28 | 17 | **0.807** | 0.807 | 1.000 |
| Jun 29 | 19 | **0.663** | 0.794 | 1.000 |
| Jun 30 | 14 | **0.976** | 0.860 | 0.917 |
| Jul 1 | 17 | **0.866** | 0.807 | 0.656 |
| Jul 2 | 12 | **0.858** | 0.817 | 1.000 |

**7-day median ratio: 0.817** — BELOW 1.10 alert threshold.

**The edge premise requires implied > realized (ratio > 1.10). On all 5 resolved days in the locked window, implied sigma was below or barely above realized. The dispersion premium is inverted or flat, not merely thin. The 2024-validated edge (true σ ~1.3°C < implied) has collapsed.**

### Unresolved days (Jul 3–Jul 7) — implied sigma only, ratio non-computable

| Date | n_cities | median impl σ | Note |
|---|---|---|---|
| Jul 3 | 6 | 0.521 | POST_PEAK snapshot, prior state (all below Jun28–Jul2 range) |
| Jul 4 | 3 | 0.199 | Near-resolution snapshots, prior state |
| Jul 5 | 3 | 0.030 | Near-resolution, end-of-day |
| Jul 6 | 12 | 0.862 | PRE_PEAK 08:02 UTC, prior state |
| **Jul 7** | **7–11** | **0.822** | PRE_PEAK 08:10 UTC, today |

Jul 3–5 near-zero sigmas reflect near-resolution snapshots (market approaching certainty), not daybreak compression. The Jul 6–7 PRE_PEAK values show genuine pre-peak uncertainty on a declining trend.

**⚠ ALERT S3 (PERSISTS, day 5 stale)**: Dispersion ratio 0.817 < 1.10. Edge is decaying. Cannot update for Jul 3–7 — no outcome labels in this pipeline. Re-enable condition: ratio ≥ 1.10 for 5 consecutive days — currently unmeasurable.

---

## 4. ISOTONIC STALENESS

| | Deployed | Candidate |
|---|---|---|
| File | `config/stwa_isotonic.json` | `config/stwa_isotonic_candidate.json` |
| Fit date | 2026-06-06 | 2026-06-09 |
| Age (today) | **31 days** | **28 days** |
| n_live incorporated | 0 | 1,037 |
| Live-refit cron | inactive since Jun 9 | — |

### Grid-point comparison

| grid | deployed | candidate | delta |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 |
| 0.05–0.15 | 0.0695–0.1828 | 0.0758–0.1828 | +0.001 to +0.007 |
| 0.20–0.25 | 0.2663–0.3557 | 0.2588–0.3535 | −0.002 to −0.008 |
| 0.30–0.90 | 0.3801 (plateau) | 0.3739 (plateau) | −0.006 |
| 0.95 | 0.3822 | 0.3739 | −0.008 |
| **1.00** | **0.6316** | **0.3739** | **−0.258** ⚠ |

**Material shift**: grid=1.0, delta=−0.258 (threshold: 0.05 absolute). Candidate compresses the top-end p_cal from 0.6316 to 0.3739 — a 26 pp reduction for near-certain YES outcomes.

**Direction**: Candidate lowers p_cal at the extreme high end and across the mid-range plateau, suppressing model confidence everywhere. This would systematically understate YES probability for near-resolved markets.

**⚠ ALERT S4 (PERSISTS)**: Candidate materially worse at grid=1.0. DO NOT DEPLOY. Both files 28–31 days stale. Refit cron inactive since Jun 9. A fresh live-fit refit is required — not deployment of the existing candidate.

---

## 5. STATE TRANSITIONS

### vs prior report (2026-07-06)

| Metric | Jul 6 | Jul 7 | Direction |
|---|---|---|---|
| brier7 | 0.053 | 0.053 | ↔ (stale day 4→5) |
| ece7 | 0.019 | 0.019 | ↔ |
| rho7 | 0.446 | 0.446 | ↔ |
| disp_ratio7 | 0.817 | 0.817 | ↔ (locked) |
| proxy_median_sigma | 0.862 | 0.822 | ↓ −4.6% |
| proxy consecutive below-baseline days | 5 | 6 | ↑ escalation |
| active alerts | 3 | 3 | ↔ |
| bankroll | $123.32 | $42.02 | ↓ −$81.30 (PnL scope) |
| BAND_LIVE | False | False | ↔ |

**No alert transitions.** All 3 alerts carry forward. The proxy lane continues a monotone 6-day compression that has not flattened.

**Bankroll observation** (out-of-scope): The bankroll fell from $123.32 (Jul 6 08:05 UTC) to $42.02 (Jul 7 08:02 UTC). BAND_LIVE=False since ~22:08 UTC Jul 6. The mechanism for this drop is outside this monitor's scope — PnL ledger / exec audit should diagnose.

---

## ALERTS (pre-registered only)

### ⚠ S3 — DISPERSION RATIO BELOW 1.10 [PERSISTS, window stale day 5]

7d median = **0.817** vs threshold 1.10. Window locked Jun 28–Jul 2, day 5 stale. The edge (implied > realized temperature dispersion) is inverted: on every confirmed resolved day, the market underpriced temperature uncertainty relative to what actually occurred. The proxy lane (6-day consecutive below-baseline) extends this signal into unsettled days.

**This is the primary edge-decay alarm. The band strategy's loadbearing assumption — market implied σ exceeds true σ by ≥10% — is not supported by recent data.**

### ⚠ S4 — ISOTONIC MATERIAL SHIFT + STALENESS [PERSISTS]

Deployed isotonic 31 days stale. Candidate 28 days stale. Critical shift at grid=1.0: candidate delta=−0.258. Candidate is worse. Live-refit cron inactive since Jun 9.

### ⚠ S5 — PROXY LANE ESCALATION [PERSISTS, day 6]

6 consecutive below-baseline sigma readings (0.994 → 0.822, −17.3%). Day 6 of unbroken decline. This early-warning signal is consistent with and extends the confirmed S3 dispersion decay.

---

*Note*: BAND_LIVE=False since Jul 6 22:08 UTC. Live trading is halted — the edge decay is not currently causing live losses. But this condition must be resolved before any re-arm.
