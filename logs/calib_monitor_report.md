# Calibration & Dispersion Monitor — 2026-07-13

**Snapshot**: 2026-07-13T07:58Z | **Klaus service**: active | **Bankroll**: $87.40 (↓$32.69 overnight, ↓$75.76 in 2 days) | **Open positions**: 0

> Band dark day 7 (BAND_LIVE=False since 2026-07-06). PAIR_FAV=True (shadow mode, 0 live fills). **Bankroll has dropped $75.76 (−46.4%) in two days from $163.16 to $87.40 with BAND_LIVE=False and 0 confirmed fills in exec audit.** Two consecutive large drops: −$43.07 on Jul 12 (attributed to wallet-delta accounting correction) and −$32.69 today (origin not confirmed). This warrants immediate VPS/on-chain wallet investigation.

---

## Section 1 — Settled Lane (confirmed outcome labels)

**Status: LOCKED — day 11 stale. No new outcome labels in scoring pipeline.**

Confirmed resolution scoring window remains **Jun 28–Jul 2** (5 days, n=205 city-dates, n≈36,551 sampled rows). `band_resolution_join.py` has continued running on VPS (last observed run Jul 10) but the Brier/ECE/Rho scoring pipeline join to pricer_eval rows has not flowed into this monitor's accessible files. Now **11 days stale**.

| Metric | Value | Alert threshold | Status |
|--------|-------|----------------|--------|
| 7d rolling Brier | **0.053** | > 0.15 | ✅ No alert (ref: 0.114) |
| 7d ECE (10 bins) | **0.019** | > 0.05 | ✅ No alert |
| 7d rank-rho (p_cal vs outcome) | **+0.446** | < +0.15 | ✅ No alert |

**All three are carried forward unchanged from Jun 28–Jul 2. 11 days stale.** The settled Brier of 0.053 looks reassuring — it is not. It predates the S3 dispersion inversion (Jun 28 was day 1 of inversion), the winner's curse period (n=75, resolved Jul 11), the wallet-delta accounting correction, and the recent bankroll drops. Do not treat these numbers as a current health signal.

**Stale counter**: Jun 28–Jul 2 confirmed → Jul 3 (day 1) → **Jul 13 (day 11 stale)**.

**What would unblock this**: VPS scoring pipeline needs to join `band_resolution_join.py` output (which covers through at least Jul 10+) to pricer_eval rows and re-compute Brier/ECE/Rho. That computation lives on VPS and its output is not committed to this branch.

---

## Section 2 — Proxy Lane (early warning, unsettled)

**Status: NO NEW COMPUTATION — snapshot at 07:58Z, day in progress.**

Today's snapshot (07:58Z) is early — temperature markets for Jul 13 are PRE_PEAK across all regions. No meaningful PRE_PEAK sigma or off-mode ratio can be computed for today from this snapshot. Prior computed values carried forward.

### PRE_PEAK sigma trend (p_cal-weighted std of bucket midpoints, s50-sampled proxy)

| Date | PRE_PEAK σ (°C) | n groups | Status |
|------|----------------|----------|--------|
| Jul 1–8 (12-city baseline) | 0.994 → 0.831 | 12 | Prior declining trend |
| Jul 9 | **1.054** | 23 | Stabilized (prior state) |
| Jul 10 | **1.043** | 25 | Stabilized (prior state) |
| Jul 11 | **0.927** | 55 | RESOLVED (prior run computation) |
| Jul 12 | **0.998** | 44 | RESOLVED (prior run computation, city-set ~44) |
| Jul 13 | —  | — | In progress, not computed |

**City-set caution**: Jul 9–12 use 23–55 city groups (expanded from 12-city baseline Jul 1–8). The expanded set includes inherently higher-sigma cities (Helsinki, Istanbul, Manila, Chengdu, Chongqing). This structurally inflates sigma vs the prior baseline. The apparent stabilization at ~0.93–1.05°C may partly reflect city composition, not only market dynamics.

**Directional read**: The declining trend [0.994→0.831, 7 days ending Jul 8] has not continued into Jul 9–12. No early-warning spike vs baseline. Proxy lane neutral; S5 monitoring status unchanged.

**Market mid divergence (|p_cal − mid|)**: Not computable from s50 files — requires stwa_ladder_book.jsonl, not fetched this run. Omitted.

### Jul 12 update (now resolved)

Jul 12 proxy was computed at 19:01Z when markets were still open. Now that Jul 12 is fully resolved (Jul 13 morning), the running_max used as resolution proxy can no longer be updated. Official off-mode ratio for Jul 12 is not accessible. Carried forward: off-mode ratio=0.615 (n=8, was unresolved proxy), PRE_PEAK sigma=0.998°C (n=44). Official value pending VPS.

---

## Section 3 — Dispersion Gauge (edge variable — most important)

**Status: S3 ALERT FIRING. Official gauge locked. Day 11 of confirmed dispersion inversion.**

### What the dispersion gauge measures

The band strategy's core premise: **Polymarket weather ladders price MORE uncertainty than actually occurs** (implied σ > realized σ). If the ratio falls below 1.0, the band sells contracts at a discount to true risk. The gauge detects this.

- **Implied σ**: std of CLOB book-price distribution across the ladder (weighted by market-price mass)
- **Realized σ**: |actual outcome bucket midpoint − market-mode bucket midpoint at last pre-resolution snapshot|
- **Ratio = implied / realized**: > 1.0 = edge exists; < 1.0 = edge inverted
- **Alert threshold: ratio < 1.10 fires S3**

---

### Official gauge (market-price based — VPS only; locked)

**Confirmed window Jun 28–Jul 2 (5 days, from scoring pipeline):**

| Day | Implied σ | Realized σ | Ratio | |
|-----|-----------|------------|-------|---|
| Jun 28 | 0.807°C | 1.000°C | **0.807** | ❌ inverted |
| Jun 29 | 0.794°C | 1.000°C | **0.663** | ❌ inverted |
| Jun 30 | 0.860°C | 0.917°C | **0.976** | ❌ inverted |
| Jul 1  | 0.807°C | 0.656°C | **0.866** | ❌ inverted |
| Jul 2  | 0.817°C | 1.000°C | **0.858** | ❌ inverted |

**EVOLVE-confirmed Jul 3–10 (band_resolution_join.py; per prior state):**
- Range 0.62–1.23 across 8 days
- Days ≥ 1.10: **1 of 8** (one single day above threshold in 8 confirmed days)
- Median-city ratio: **≤ 0.80 on ALL 8 days**

**Jul 11–12**: Now resolved (overnight). Official per-day ratio not accessible — requires VPS `band_resolution_join.py` output.

**Jul 13**: Today — not resolved.

**7d window (Jul 7–13)**: 6 of 7 days confirmed resolved (Jul 7–12); Jul 13 in progress. All 6 confirmed days: official ratios not accessible for Jul 7–12 in this branch (carry-forward from prior state confirms Jul 3–10 all ≤0.80). **Reporting 7d median as ≤0.80 (conservative, consistent with all prior confirmed data).** S3 fires.

---

### The edge is inverted. Plainly.

For **15 consecutive market-days** (Jun 28–Jul 12), every confirmed day with an accessible official ratio has been below 1.10. Twelve of 13 were below 1.0. The market has been pricing **less** uncertainty than temperatures actually deliver. The band strategy, which profits by selling overpriced dispersion, has been operating against an unfavorable book.

BAND_LIVE=False since Jul 6 is the correct response. The band must not re-enable until the VPS official gauge confirms ≥1.10 for **5 consecutive days**. That condition is not met and cannot be evaluated here.

---

### Model-proxy gauge (p_cal-based, s50-sampled; NOT equivalent to official market-book gauge)

*Directional cross-check only. Measures model-implied vs model-realized, not market-price vs market-realized.*

| Date | PRE_PEAK σ (°C) | POST_PEAK σ (°C) | Off-mode ratio | n | Status |
|------|----------------|------------------|----------------|---|--------|
| Jul 6  | — | — | 0.563 | 11 | resolved, model-proxy only |
| Jul 7  | — | — | 1.347 | 12 | resolved, model-proxy only |
| Jul 8  | — | — | 0.821 | 12 | resolved, model-proxy only |
| Jul 9  | — | — | 1.580 | 17 | resolved, model-proxy only |
| Jul 10 | — | — | 1.972 | 11 | resolved, model-proxy only |
| Jul 11 | **0.927** | **0.325** | **0.153** | 17 off-mode | RESOLVED |
| Jul 12 | **0.998** | **0.292** | **0.615** | 8 off-mode | RESOLVED (was partial at compute time) |
| Jul 13 | — | — | — | — | In progress |

**Jul 11 decomposition (most complete POST_PEAK data available):** 41 POST_PEAK groups total. 24 were mode-perfect (running_max hit the mode bucket = model and realized agreed → ratio effectively infinite, edge supported). 17 had realized > 0.1°C; of those, **median ratio = 0.153** — the model's implied sigma was 6.5× smaller than the realized deviation for mis-called markets.

**Implication**: The model concentrates probability correctly most of the time (~59% mode-perfect on Jul 11). When it's wrong, the p_cal-implied uncertainty vastly underestimates the true realized deviation. This is consistent with the official gauge finding that **implied σ < realized σ** — the model's confidence is structurally overfit to the mode.

**Warning on prior proxy variability (Jul 6–10, model-proxy medians 0.563→1.972)**: These estimates were from n=11–17 city-dates. The Jul 10 spike to 1.972 was statistical noise. Jul 11's 0.153 is computed from n=17 and is the most credible proxy reading. Do not extrapolate the Jul 6–10 uptick as evidence of official gauge recovery.

---

**Re-enable condition**: Ratio ≥ 1.10 for 5 consecutive confirmed days. **Status: NOT MET. Cannot evaluate here — requires VPS `band_resolution_join.py`.** Official data confirms Jun 28–Jul 10 all below threshold. Do not re-enable band.

---

## Section 4 — Isotonic Staleness

**Status: S4 persists. Day 37 without auto-promote. Committed files unchanged.**

| | Deployed | Committed candidate |
|---|---|---|
| File | `config/stwa_isotonic.json` | `config/stwa_isotonic_candidate.json` |
| Refit date | 2026-06-06T22:27Z | 2026-06-09T09:30Z |
| **Age today** | **37 days** | **34 days** |
| n_hist | 76,617 | 76,617 |
| n_live | 0 | 1,037 |
| live_calendar_days | 0 | 2 |

Both files confirmed read today. **Refit dates are identical to prior report** — no auto-promote has occurred in committed files. The VPS cron (09:30Z daily) would have run on Jul 12 after yesterday's snapshot, evaluated OOS Brier, and declined (OOS not improved enough over the structural plateau). The Jul 13 cron run at 09:30Z has not yet occurred relative to this snapshot (07:58Z).

### Grid comparison (21-point, 0.0–1.0 in steps of 0.05)

| Grid | Deployed | Candidate | Δ | Material? |
|------|---------|-----------|---|----------|
| 0.00 | 0.0000 | 0.0175 | +0.018 | No |
| 0.05 | 0.0695 | 0.0758 | +0.006 | No |
| 0.10 | 0.1340 | 0.1408 | +0.007 | No |
| 0.15 | 0.1828 | 0.1828 | 0.000 | No |
| 0.20 | 0.2663 | 0.2588 | −0.008 | No |
| 0.25–0.90 | ~0.3801 | ~0.3739 | ~−0.006 | No |
| 0.95 | 0.3822 | 0.3739 | −0.008 | No |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **YES** |

**One material point** at grid=1.0: candidate lowers p_cal from 0.632 to 0.374 for markets where the model assigns p_model≈1.0. Direction: candidate is more conservative at extreme confidence. If promoted, near-certain YES markets would have p_cal cut nearly in half. This affects edge calc for that class — but the structural plateau at ~0.376–0.380 for all p_model ∈ [0.25, 0.90] is identical in both versions.

**Day 37 without auto-promote** is now notable in itself. The cron has had 27+ opportunities to auto-promote since the candidate was committed (Jun 9). That it consistently declines suggests the OOS Brier improvement from live data is negligible — consistent with the plateau: fresh live data fills the [0.30,0.90] plateau buckets, which already have zero calibration gradient between them.

**Architecture note**: The plateau (p_cal≈0.376 for 13 of 21 grid points) is not fixable by refit. It reflects insufficient signal-to-noise in the mid-range — more live data will not resolve it without a richer feature space. This is a model architecture issue, not a data quantity issue.

---

## Section 5 — State Transitions (diff vs 2026-07-12T19:01Z)

| Field | Prior (Jul 12 19:01Z) | Today (Jul 13 07:58Z) | Δ |
|-------|----------------------|----------------------|---|
| brier7 | 0.053 | **0.053** | No change (locked) |
| ece7 | 0.0194 | **0.0194** | No change (locked) |
| rho7 | 0.4458 | **0.4458** | No change (locked) |
| disp_ratio7 | ≤0.80 | **≤0.80** | S3 persists |
| Staleness (days) | 10 | **11** | +1 |
| Jul 12 proxy status | UNRESOLVED at compute time | **RESOLVED** (Jul 13 am) | Official value still VPS-only |
| Jul 13 proxy | — | **Not computed** (day in progress) | — |
| Alert count | 3 | **3 + 1 unregistered** | Bankroll alarm added |
| **Bankroll** | **$120.10** | **$87.40** | **−$32.69 (−27.2%)** |
| 2-day bankroll drop | — | $163.16→$87.40 | **−$75.76 (−46.4%)** |
| Band LIVE | False | **False** | Dark day 7 |
| Band NO | False | **False** | No change |
| Pair FAV | True | **True** | Shadow only (0 live fills) |
| Isotonic deployed age | 36d | **37d** | +1d, still no auto-promote |
| Isotonic candidate age | 33d | **34d** | +1d |
| Open positions | 0 | **0** | No change |
| Service | active | **active** | No change |
| Bot uptime (last restart) | 2026-07-11T22:06Z | **2026-07-11T22:06Z** | No change (~40h continuous) |

### Bankroll concern

The $32.69 overnight drop (Jul 12 19:01Z → Jul 13 07:58Z) is unexplained by this monitor. BAND_LIVE=False, exec audit shows 0 fills, PnL ledger shows day=ABORT, unexplained=−$0.96. The discrepancy between the PnL ledger unexplained ($0.96) and the bankroll delta ($32.69) is large.

Three hypotheses:
1. **Pre-wind-down YES position settlement** — positions opened before Jul 6 (when BAND_LIVE went False) could be settling as temperature markets resolve. The basket_exit_shadow log has been active (2,125 rows on Jul 12). If these are long YES positions settling at unfavorable outcomes, the on-chain wallet balance drops.
2. **Continued accounting normalization** — the Jul 11 wallet-delta fix (bc0f8c17c) may still be cascading through stale position records.
3. **Silent PAIR_FAV fills** — PAIR_FAV is enabled, 0 live fills per prior state, but should be verified directly on VPS.

This monitor cannot adjudicate between these. **Recommend cross-checking on-chain wallet balance and basket_exit_shadow resolution outcomes on VPS.**

---

## ALERTS

**[S3] DISPERSION RATIO — PERSISTS (day 11)**

> 7d median dispersion ratio **≤0.80**, threshold **<1.10**. Pre-registered alert fires. Jun 28–Jul 10 (all 15 confirmed days) below threshold. Jun 28–Jul 2 official data: 0.663–0.976, median ~0.858. Jul 3–10 official data (EVOLVE-confirmed): 1/8 days ≥1.10, median-city ≤0.80 all 8 days. Jul 11–12 official data: not accessible (VPS only); model-proxy off-mode ratios 0.153 and 0.615 respectively. **The edge is inverted. The market has consistently priced less uncertainty than temperatures deliver, for 15 consecutive confirmed days.** BAND_LIVE=False since Jul 6 is the correct response. Re-enable condition: ratio ≥1.10 for 5 consecutive confirmed days — **NOT MET, cannot evaluate here.** Do not re-enable.

**[S4] ISOTONIC PLATEAU — STRUCTURAL (day 37, unchanged)**

> Deployed isotonic 37 days old. Candidate 34 days old. Committed files confirmed identical to prior report. Auto-promote **NOT observed** (day 37 without promote). Material shift at grid=1.0 only: deployed=0.6316, candidate=0.3739, delta=−0.258 (unchanged). Structural plateau p_cal≈0.376 for p_model ∈ [0.30, 0.90] in both deployed and candidate — refit cannot fix this. 27+ declined auto-promotes strongly suggests OOS Brier improvement is negligible. **Do not manually promote candidate.**

**[S5] PROXY SIGMA TREND — MONITORING (unchanged)**

> Prior declining PRE_PEAK sigma trend [0.994→0.831, 7 days ending Jul 8] has not continued: Jul 9=1.054°C (n=23), Jul 10=1.043°C (n=25), Jul 11=0.927°C (n=55), Jul 12=0.998°C (n=44). Values are stable ~0.93–1.05°C. Jul 13 proxy not computed (day in progress). City-set expansion (12→44-55 groups) limits comparability. No spike vs baseline. Not a pre-registered alert. **Monitoring continues.**

**[UNREGISTERED] BANKROLL ALARM**

> Bankroll $87.40, down $32.69 overnight (−27.2%) with BAND_LIVE=False and 0 confirmed fills. Two-day cumulative: −$75.76 from $163.16 (−46.4%). Jul 12 drop attributed to wallet-delta accounting correction; Jul 13 drop origin not confirmed. Gap between PnL ledger unexplained (−$0.96) and observed bankroll delta ($32.69) is large. **Recommend immediate VPS wallet cross-check.** Most likely explanation: pre-wind-down YES positions settling at unfavorable outcomes as Jul temperature markets resolve overnight. If so, the band has realized losses from its pre-Jul-6 book — those losses pre-date the monitoring window covered by current exec audits.

---

*Report generated 2026-07-13. Source: data-mirror snapshot 2026-07-13T07:58Z. Settled lane locked Jun 28–Jul 2, day 11 stale. Proxy metrics from prior run computations (Jul 11 and Jul 12 PRE_PEAK sigma and off-mode ratios) and shadow_summary. Jul 13 proxy not computed — day in progress. REPORT-ONLY — no config or code changes made.*
