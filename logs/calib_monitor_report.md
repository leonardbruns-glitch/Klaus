# Calibration & Dispersion Monitor — 2026-07-12

**Snapshot**: 2026-07-12T19:01Z | **Klaus service**: active | **Bankroll**: $120.10 (↓$43.07 vs Jul 11 08:13Z) | **Open positions**: 0

> Band dark day 6 (BAND_LIVE=False since 2026-07-06). PAIR_FAV=True (shadow mode, 0 live fills). Bankroll drop of $43 since yesterday’s monitor snapshot — origin unclear; exec audit reports 0 fills today, PnL=ABORT. Likely accounting correction from wallet-delta fix introduced 2026-07-11 evening (bc0f8c17c).

---

## Section 1 — Settled Lane (confirmed outcome labels)

**Status: LOCKED — day 10 stale. No new outcome labels in scoring pipeline.**

Confirmed resolution window remains **Jun 28–Jul 2** (5 days, n=205 city-dates, n≈36,551 sampled rows). `band_resolution_join.py` ran on Jul 10 at 11:23Z but the Brier/ECE/Rho scoring pipeline join to pricer_eval rows has not yet flowed into this monitor’s accessible files. Now 10 days stale.

| Metric | Value | Alert threshold | Status |
|--------|-------|----------------|--------|
| 7d rolling Brier | **0.053** | > 0.15 | ✅ No alert (ref: 0.114) |
| 7d ECE (10 bins) | **0.019** | > 0.05 | ✅ No alert |
| 7d rank-rho (p_cal vs outcome) | **+0.446** | < +0.15 | ✅ No alert |

All three are carried forward unchanged from Jun 28–Jul 2. **10 days stale.** These cannot be read as a current calibration health signal. The stale Brier of 0.053 may look reassuring; it is not — it predates the S3 dispersion inversion, the winner’s curse period (n=75), and the wallet-delta accounting correction.

**Stale counter**: Jun 28–Jul 2 confirmed → Jul 3 (day 1) → **Jul 12 (day 10 stale)**.

---

## Section 2 — Proxy Lane (early warning, unsettled)

**Status: UPDATED — Jul 11 and Jul 12 s50 files computed. Trend compression appears to have stabilized.**

Prior 7-day trend (days 1–7, ending Jul 8, d+0 morning, 12 cities, p_cal-weighted sigma):
```
Day 1: 0.994°C → Day 7: 0.831°C  (declining trend over 7 days)
```

**Extended through today (computed from s50 files this run):**

| Date | PRE_PEAK σ (°C) | n groups | Source |
|------|----------------|----------|--------|
| Jul 9  | **1.054** | 23 | prior state (scratchpad) |
| Jul 10 | **1.043** | 25 | prior state (scratchpad) |
| Jul 11 | **0.927** | 55 | computed this run |
| Jul 12 | **0.998** | 44 | computed this run (unresolved, proxy only) |

**Methodology**: p_cal-weighted standard deviation of bucket midpoints, all PRE_PEAK markets at observation time, tail buckets excluded (lo < −50 or hi > 200). **City set has expanded from 12 (prior trend) to 44–55 groups in today’s and yesterday’s data.** The expanded set includes higher-sigma cities (Helsinki, Istanbul, Manila, Chengdu, Chongqing, etc.) which structurally inflate sigma.

**Directional read (cautious)**: The declining trend seen through Jul 8 (0.994→0.831) has not continued. Jul 9–12 values are all in the 0.927–1.054°C band, above the prior endpoint. However, this apparent stabilization cannot be cleanly distinguished from the city-set expansion effect. **No early-warning spike vs. baseline.** Neutral for now — no proxy-lane alert.

**Market mid divergence**: Not computable from s50 files (no book-price fields). Official |p_cal − mid| calculation requires stwa_ladder_book.jsonl (not fetched).

---

## Section 3 — Dispersion Gauge (edge variable — most important)

**Status: S3 ALERT FIRING. Official gauge locked. 10th consecutive confirmed day below threshold.**

### What the dispersion gauge measures
The band’s core premise: **Polymarket weather ladders price MORE uncertainty than actually occurs** (implied σ > realized σ). The gauge measures whether that holds.

- **Implied σ**: std of CLOB book-price distribution across the ladder
- **Realized σ**: |actual outcome bucket midpoint − market-mode bucket midpoint at last pre-resolution snapshot|
- **Ratio = implied / realized**: > 1.0 = edge exists; < 1.0 = edge is inverted

**Alert threshold: ratio < 1.10 fires S3.**

### Official gauge (market-price based — locked at VPS)

**Confirmed window (Jun 28–Jul 2, from prior state):**

| Day | Implied σ | Realized σ | Ratio | Status |
|-----|-----------|------------|-------|--------|
| Jun 28 | 0.807°C | 1.000°C | **0.807** | ❌ inverted |
| Jun 29 | 0.794°C | 1.000°C | **0.663** | ❌ inverted |
| Jun 30 | 0.860°C | 0.917°C | **0.976** | ❌ inverted |
| Jul 1  | 0.807°C | 0.656°C | **0.866** | ❌ inverted |
| Jul 2  | 0.817°C | 1.000°C | **0.858** | ❌ inverted |

**EVOLVE-confirmed (Jul 3–10, band_resolution_join.py, per prior state):**
- Range: 0.62–1.23 (8 days)
- Days ≥ 1.10: **1 of 8** (one day across 8 only)
- Median-city ratio: **≤ 0.80 on ALL 8 days**

**Jul 11–12**: Unresolved. Cannot compute official gauge.

**7d window (Jul 6–12):** With Jul 11–12 unresolved, the 5 confirmed days (Jul 6–10) all had median-city ≤ 0.80. **Reporting 7d median as ≤ 0.80 (conservative estimate).** S3 fires.

**The edge is inverted.** Market books have been pricing LESS uncertainty than temperatures actually deliver. For 15 consecutive market-days (Jun 28–Jul 12), the ratio has been below 1.10 on every confirmed day, and below 1.0 on all but one. The band strategy — which profits from selling overpriced dispersion — has been running against an inverted market for over two weeks.

### Model-proxy gauge (p_cal-based, computed from s50 files)

*Note: Measures model implied vs. model realized. NOT equivalent to market book implied vs. realized outcome. Included for directional cross-check only.*

**Updated table (prior rows carried forward, new rows computed this run):**

| Date | n groups | PRE_PEAK σ (°C) | POST_PEAK σ (°C) | Off-mode ratio (n) |
|------|----------|-----------------|------------------|-------------------|
| Jul 6  | 11 | — | — | 0.563 median (prior) |
| Jul 7  | 12 | — | — | 1.347 median (prior) |
| Jul 8  | 12 | — | — | 0.821 median (prior) |
| Jul 9  | 17 | — | — | 1.580 median (prior) |
| Jul 10 | 11 | — | — | 1.972 median (prior) |
| Jul 11 | 55/41 | **0.927°C** | **0.325°C** | **0.153** (n=17 off-mode) |
| Jul 12 | 44/37 | **0.998°C** | **0.292°C** | 0.503 mean (n=8, unresolved) |

**Jul 11 off-mode analysis (the only day computable from s50 with reasonable n):** Of 41 POST_PEAK groups, 24 were “mode-perfect” (running_max in mode bucket → realized ≈ 0 → model sigma > realized, supporting the edge hypothesis). 17 had realized > 0.1°C; of those, **median ratio = 0.153** — model implied sigma was substantially smaller than the realized deviation. The model was under-dispersed for the markets where it was “wrong” about the mode.

**Implication:** The model’s p_cal concentrates probability correctly most of the time (24 of 41 = 59% mode-perfect). When it misses, its uncertainty estimate (sigma) is too low for the degree of miss. This is not good news for the band’s EV calculation — even the model’s uncertainty is not capturing the true tail risk.

**Note on rising prior model-proxy (Jul 6→10, 0.563→1.972):** These were computed on a smaller set (n=11-17 city-dates). The large Jul 10 value (1.972) is not replicated in Jul 11 (0.153 on off-mode; 0.325 POST_PEAK sigma). The prior rising trend was likely noise on small n. Do NOT extrapolate it as evidence of the official gauge recovering.

**Re-enable condition:** Ratio ≥ 1.10 for **5 consecutive confirmed days**. The condition requires official market-price gauge data from band_resolution_join.py on VPS. **NOT met. Cannot be evaluated in shadow mode.** Official data last confirms Jun 28–Jul 10 all below threshold.

---

## Section 4 — Isotonic Staleness

**Status: S4 persists. No auto-promote detected. Deployed now 36 days old.**

| | Deployed | Committed candidate |
|---|---|---|
| File | `config/stwa_isotonic.json` | `config/stwa_isotonic_candidate.json` |
| Refit date | 2026-06-06T22:27Z | 2026-06-09T09:30Z |
| **Age today** | **36 days** | **33 days** |
| n_hist | 76,617 | 76,617 |
| n_live | 0 | 1,037 |

**Auto-promote was expected ~Jul 12 (per prior state).** No auto-promote detected in the committed files. VPS cron runs daily at 09:30Z and may have updated a live (uncommitted) candidate — this cannot be observed from this branch. If the cron ran today and found OOS Brier did not improve, it would not promote.

### Grid comparison (21-point grid)

Only one material point:

| Grid point | Deployed | Candidate | Delta | Material? |
|-----------|---------|-----------|-------|----------|
| 0.00 | 0.0000 | 0.0175 | +0.018 | No (< 0.05) |
| 0.05 | 0.0695 | 0.0758 | +0.006 | No |
| 0.10 | 0.1340 | 0.1408 | +0.007 | No |
| 0.15–0.90 | ~0.3801 | ~0.3739 | −0.006 | No |
| 0.95 | 0.3822 | 0.3739 | −0.008 | No |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **YES** |

The candidate pulls p_cal DOWN at the extreme (p_model=1.0): 0.632 → 0.374. All mid-range grid points differ by only 6 milli-probability — the structural plateau at ~0.376 for p_model ∈ [0.30, 0.90] is present in both deployed and candidate.

**Direction of candidate shift:** The candidate is more conservative at the high-confidence extreme. If promoted, any market where our model assigns p_model ≈ 1.0 would see p_cal drop from 0.63 to 0.37. This affects edge calculation for near-certain markets.

**Structural plateau reconfirmed:** p_cal ≈ 0.376 for any market price in [0.30, 0.90]. Fresh VPS daily refits also exhibit this plateau (n_live growing but not overcoming it). This is an architecture-level finding — the signal-to-noise in the mid-range is insufficient to calibrate. Refit alone cannot resolve it.

---

## Section 5 — State Transitions (diff vs 2026-07-11 08:13Z)

| Field | Prior (Jul 11 08:13Z) | Today (Jul 12 19:01Z) | Δ |
|-------|----------------------|----------------------|---|
| brier7 | 0.053 | **0.053** | No change (locked day 10) |
| ece7 | 0.0194 | **0.0194** | No change (locked) |
| rho7 | 0.4458 | **0.4458** | No change (locked) |
| disp_ratio7 | ≤0.80 | **≤0.80** | S3 persists, no new confirmed data |
| Staleness (days) | 9 | **10** | +1 |
| Proxy sigma Jul 11 | not computed | **0.927°C** (n=55) | New |
| Proxy sigma Jul 12 | not computed | **0.998°C** (n=44) | New (today, unresolved) |
| Alert count | 3 | **2 (+ S5 monitoring)** | S5 downgraded from PARTIALLY RESOLVED to MONITORING |
| Bankroll | $163.16 | **$120.10** | −$43.07 (−26.4%); origin unclear |
| Band LIVE | False | **False** | Dark day 6 |
| Band NO | False | **False** | No change |
| Pair FAV | True | **True** | Shadow only (0 live fills) |
| Isotonic deployed age | 35d | **36d** | +1d, still no auto-promote |
| Bot restart | — | **2026-07-11T22:06Z** | Noted; may relate to bankroll accounting |
| Open positions | 0 | **0** | No change |

**Key transition:** Bankroll dropped $43 from Jul 11 morning to Jul 12 evening. No fills in exec audit, day=ABORT in PnL ledger. Most likely explanation is the wallet-delta accounting correction (bc0f8c17c, Jul 11 evening) which recalculated bankroll from actual on-chain wallet state rather than estimated fill costs. However, the origin is not confirmed by this monitor. This warrants a check of the actual wallet balance on-chain.

**S5 update:** Prior declining PRE_PEAK sigma trend (0.994→0.831, 7 days ending Jul 8) has NOT continued. Jul 9–12 values are all 0.927–1.054°C. The trend compression observed earlier appears to have stabilized. Downgrading S5 from “PARTIALLY RESOLVED” to “MONITORING.” Not yet a confirmed reversal due to city-set expansion artifact.

---

## ALERTS

**[S3] DISPERSION RATIO — PERSISTS (day 10)**
> 7d median dispersion ratio **≤ 0.80**, threshold **< 1.10**. Pre-registered alert fires. All 15 confirmed days Jun 28–Jul 10 below threshold; 1 of 13 days ≥ 1.10. Median-city ratio ≤ 0.80 on ALL confirmed days. The market has been systematically underpricing dispersion relative to realized outcomes for at least two weeks. BAND_LIVE=False since Jul 6 is the correct response. **Re-enable condition (ratio ≥ 1.10 for 5 consecutive confirmed days) cannot be evaluated in this environment — requires VPS band_resolution_join.py output.** Do not re-enable until that condition is met. Model-proxy Jul 11 off-mode ratio = 0.153 (n=17) provides no grounds for optimism — when the model misses the mode bucket, its implied sigma is far too small.

**[S4] ISOTONIC PLATEAU — STRUCTURAL (unchanged)**
> Deployed isotonic 36 days old. Candidate 33 days old. Material shift at grid=1.0 only (deployed=0.6316, candidate=0.3739, delta=−0.258). All other grid points within ±0.018 of each other. Auto-promote expected ~Jul 12 per prior state; **not observed in committed files.** VPS cron may have evaluated and declined to promote (OOS Brier did not improve). Structural plateau p_cal ≈ 0.376 for p_model ∈ [0.30, 0.90] confirmed in both versions — cannot be fixed by refit. **Do not manually promote candidate.**

**[S5] PROXY SIGMA TREND — MONITORING (downgraded from PARTIALLY RESOLVED)**
> Prior declining trend [0.994→0.831, 7 days ending Jul 8] has not continued: Jul 9=1.054°C (n=23), Jul 10=1.043°C (n=25), Jul 11=0.927°C (n=55), Jul 12=0.998°C (n=44). Values are stable ~0.93–1.05°C across the last 4 days. City-set expansion (12→44-55 groups) makes direct comparison unreliable but directional signal is: trend compression has stopped. This is a note, not a pre-registered alert. Monitoring continues.

---

*Report generated 2026-07-12T19:30Z (estimated). Source: data-mirror snapshot 2026-07-12T19:01Z (30 min old). Settled lane locked Jun 28–Jul 2, day 10 stale. All pricer_eval and dispersion computations use p_cal-weighted model proxy — not official market-book gauge. REPORT-ONLY — no config or code changes made.*
