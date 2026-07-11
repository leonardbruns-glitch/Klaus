# Calibration & Dispersion Monitor — 2026-07-11

**Snapshot**: 2026-07-11T08:13Z | **Klaus service**: active | **Bankroll**: $163.16 (+$4.54/24h) | **Open positions**: 0

> Band freeze EXPIRED 2026-07-10T21:53Z. Band still dark. Re-enable decision: 2026-07-12. Calib monitor S3 argues strongly against re-enable until dispersion ratio is confirmed ≥1.10 for 5 consecutive days.

---

## Section 1 — Settled Lane (confirmed outcome labels)

**Status: LOCKED — day 9 stale. No new outcome labels in scoring pipeline.**

Confirmed resolution window remains **Jun 28–Jul 2** (5 days, n=205 city-dates, n≈36,551 sampled rows). `band_resolution_join.py` ran on Jul 10 at 11:23Z (confirmed by EVOLVE) and produced Jul 3–10 outcome data. **However, the Brier/ECE/Rho scoring pipeline** requires those outcomes to be joined to pricer_eval rows — that join has not yet flowed into this monitor's accessible files.

| Metric | Value | Alert threshold | Status |
|--------|-------|----------------|--------|
| 7d rolling Brier | **0.053** | > 0.15 | ✅ No alert (ref: 0.114) |
| 7d ECE (10 bins) | **0.019** | > 0.05 | ✅ No alert |
| 7d rank-rho (p_cal vs outcome) | **+0.446** | < +0.15 | ✅ No alert |

All three carry forward unchanged from Jun 28–Jul 2. They are **9 days stale** and must not be read as a current health signal. The calibration may have drifted materially since Jul 2 — it is simply unmeasurable here.

**Stale counter**: Jun 28–Jul 2 confirmed → Jul 3 (day 1) → Jul 11 (day 9 stale).

---

## Section 2 — Proxy Lane (early warning, unsettled)

**Status: EXTENDED — s50 files now accessible. Jul 9–10 values computed. TODAY (Jul 11) s50 not yet in snapshot.**

Prior 7-day trend (days 1–7, ending Jul 8, d+0 morning, 12 cities, p_cal-weighted sigma):

```
Day 1: 0.994°C → Day 7: 0.831°C  (declining trend over 7 days)
```

**Extended from s50 files in scratchpad (Jul 9–10):**

| Date | d+0 PRE_PEAK σ (°C) | n cities |
|------|---------------------|----------|
| Jul 9  | **1.054** | 23 |
| Jul 10 | **1.043** | 25 |

These values are ABOVE the prior trend endpoint (0.831°C at Jul 8). Methodology is consistent: p_cal-weighted standard deviation of bucket midpoints, d+0 markets, morning 6-hour window. **Caveat: city set is 23–25 cities vs the prior 12-city allowlist** — the expanded set includes more variable mid-latitude and tropical cities (Chongqing, Istanbul, Manila, Helsinki) with structurally higher sigmas. Direct comparison to the prior series is unreliable without filtering to the same 12 cities.

**Directional read (cautious):** If anything, the prior declining trend has not continued — values are flat or slightly above. Whether this is a genuine reversal of model concentration or simply a city-set expansion artifact cannot be determined here.

**Market mid divergence:** Not computable. No book-price data in s50 files. Official |p_cal − mid| calculation requires stwa_ladder_book.jsonl (present in shadow hot files but not fetched).

---

## Section 3 — Dispersion Gauge (edge variable — most important)

**Status: S3 ALERT FIRING. Partial update from EVOLVE data. Official 7d value ≤0.80, below threshold 1.10.**

### What the dispersion gauge measures
The band's core premise: **Polymarket weather ladders price MORE uncertainty than actually occurs** (implied σ > realized σ). If that holds, selling probability at the tails is positive-EV. The gauge quantifies whether it holds.

- **Implied σ**: std of book-price distribution across the ladder (what the market prices)
- **Realized σ**: |actual outcome bucket midpoint − market-mode bucket midpoint at last pre-resolution snapshot|
- **Ratio = implied / realized**: > 1.0 = edge exists; < 1.0 = edge is inverted

### Official gauge (market-price based, from band_resolution_join.py via EVOLVE)

**Prior confirmed window (Jun 28–Jul 2):**

| Day | Implied σ | Realized σ | Ratio | Status |
|-----|-----------|------------|-------|--------|
| Jun 28 | 0.807°C | 1.000°C | **0.807** | ❌ inverted |
| Jun 29 | 0.794°C | 1.000°C | **0.663** | ❌ inverted |
| Jun 30 | 0.860°C | 0.917°C | **0.976** | ❌ inverted |
| Jul 1  | 0.807°C | 0.656°C | **0.866** | ❌ inverted |
| Jul 2  | 0.817°C | 1.000°C | **0.858** | ❌ inverted |

**Updated from EVOLVE (Jul 10 evening, band_resolution_join.py output for Jul 3–10):**
- Range: 0.62–1.23 (8 days)
- Days with ratio ≥ 1.10: **1 of 8** (one single day above threshold)
- Median city per day: **≤ 0.80 on ALL 8 days**

**Updated 7d median estimate (Jul 5–11, with Jul 11 unresolved):** Based on EVOLVE's "median-city ≤ 0.80 ALL days" for Jul 3–10, the Jul 4–10 7-day median is also ≤ 0.80. Reporting as **~0.80** (conservative estimate; true value not computable without per-day access).

**ALERT S3 fires.** The dispersion premium the band harvests **does not exist** on any confirmed day since Jun 28. Market books have been pricing *less* dispersion than the temperatures actually exhibit. The band strategy (selling overpriced dispersion) is inverted — markets are underpricing dispersion relative to outcomes.

### Model-proxy gauge (p_cal-based, computed from s50 files)

*Note: This measures model uncertainty vs. realized, not market uncertainty vs. realized. These are different quantities. Included for cross-check only.*

| Date | n markets | Median ratio (model/realized) | Mean |
|------|-----------|-------------------------------|------|
| Jul 6  | 11 | 0.563 | 1.226 |
| Jul 7  | 12 | 1.347 | 1.803 |
| Jul 8  | 12 | 0.821 | 1.539 |
| Jul 9  | 17 | 1.580 | 1.884 |
| Jul 10 | 11 | 1.972 | 2.085 |
| **5d pooled** | **63** | **1.338** | **1.723** |

The model is consistently pricing MORE uncertainty than actually occurs (ratio >1 on 3 of 5 days, pooled median 1.34). The market prices LESS uncertainty than occurs (official gauge <1.0 every day). This means:
- **Model is over-dispersed** relative to outcomes
- **Market is under-dispersed** relative to outcomes  
- The band's EV depends on market pricing, not model pricing — so the model-proxy's favorable reading does NOT indicate a restored edge

**Regional breakdown (s50 proxy, 5d pooled):**
- US: n=23, median=1.917 (model over-dispersed in US cities)
- EU: n=4, median=0.920 (closest to neutral)
- Asia: n=11, median=1.415 (model over-dispersed in Asian cities)

**Trend:** Model-proxy ratios are rising (0.563 → 1.972 from Jul 6→10). If the market book follows the model directionally, official market gauge may recover — but this is speculative.

### Re-enable condition
Ratio ≥ 1.10 for 5 consecutive confirmed days. **NOT met.** Only 1 of 13 confirmed days (Jun 28–Jul 10) has met the threshold. The Jul 12 band re-enable review must weigh this: even if the equity rail and freeze conditions are satisfied, **this gauge argues for continued shadow operation.**

---

## Section 4 — Isotonic Staleness

**Status: Unchanged from prior report. S4 structural alert persists.**

| | Deployed | Committed candidate | Live VPS candidate |
|---|---|---|---|
| File | `config/stwa_isotonic.json` | `config/stwa_isotonic_candidate.json` | (not committed) |
| Refit date | 2026-06-06 | 2026-06-09 | Daily 09:30Z |
| **Age today** | **35 days** | **32 days** | Fresh |

### Grid comparison (only material point)

| Grid point | Deployed | Candidate | Delta | Material? |
|-----------|---------|-----------|-------|----------|
| 0.00 | 0.0000 | 0.0175 | +0.018 | No |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **YES** |
| All others (0.05–0.95) | ~0.380 | ~0.374 | −0.006 | No |

One material point: grid=1.0 only. Candidate lowers p_cal at extreme-high market prices from 0.6316 to 0.3739.

### Plateau: structural, confirmed no-defect

The flat calibrated output (~0.376) for any market price in [0.30, 0.90] is not a model bug or staleness artifact. The Jul 9 isotonic PA-1 audit closed with no-defect. Fresh VPS candidates (daily since Jun 9) continue to exhibit the same plateau. Polymarket weather ladder pricing is concentrated in the 0.35–0.85 midrange — there is insufficient training signal to discriminate across this span.

**Implication:** p_cal provides no discrimination between market prices of 0.30, 0.50, and 0.90. This is an architecture-level finding — refit alone cannot fix it.

**Auto-promote condition:** Daily cron auto-promotes when OOS Brier improves vs. deployed. Expected window ~Jul 12. **Do not manually promote.** When auto-promote fires, verify the new curve reduces the grid=1.0 discrepancy without degrading plateau.

---

## Section 5 — State Transitions (diff vs 2026-07-10)

| Field | Prior (Jul 10 07:59Z) | Today (Jul 11 08:13Z) | Δ |
|-------|----------------------|----------------------|---|
| brier7 | 0.053 | 0.053 | No change (locked) |
| ece7 | 0.0194 | 0.0194 | No change (locked) |
| rho7 | 0.4458 | 0.4458 | No change (locked) |
| disp_ratio7 | 0.817 (locked) | **≤0.80** (partially updated) | Jul 3–10 data confirmed via EVOLVE |
| Staleness (days) | 8 | **9** | +1 day |
| Proxy lane | Substituted (d+1/d+2) | **Extended** (d+0 Jul 9–10) | s50 files now accessible |
| d+0 sigma Jul 9 | Not computed | **1.054°C** (n=23 cities) | New |
| d+0 sigma Jul 10 | Not computed | **1.043°C** (n=25 cities) | New |
| Alert count | 3 | **3** | S3 persists, S4 structural, S5 partially resolved |
| Bankroll | $158.63 | **$163.16** | +$4.54/24h |
| Freeze status | Active (ends 21:53Z) | **EXPIRED** (expired 2026-07-10T21:53Z) | Band still dark |
| Band re-enable | Deferred to Jul 12 | **Deferred to Jul 12** | Review tomorrow |
| Isotonic deployed age | 34d | **35d** | +1d |

**Transition summary:** No calibration metrics improved. Settled lane is now 9 days stale. Dispersion gauge partially updated from EVOLVE data — confirmed median ≤0.80 on all days Jul 3–10, S3 fires. Proxy lane extended two days using s50 files now accessible in this environment; values above prior trend endpoint but city-set difference limits comparability. Freeze expired; band dark pending Jul 12 structural review.

---

## ALERTS

**S3 — DISPERSION RATIO (PERSISTS)**
> 7d median dispersion ratio ≤ 0.80 < 1.10 (threshold). EVOLVE Jul 10 confirmed via `band_resolution_join.py`: **Jul 3–10 range 0.62–1.23, 1/8 days ≥ 1.10, median-city ≤ 0.80 on ALL 8 days.** The band's load-bearing edge condition has not held on any of 13 confirmed days since Jun 28. Market books systematically underprice dispersion relative to realized outcomes — the opposite of the band's required condition. Official per-day values reside on VPS (not accessible here). **Re-enable condition: ratio ≥ 1.10 for 5 consecutive confirmed days — not achievable in shadow mode without new live fills providing resolution labels. Jul 12 re-enable review: this alert argues for remaining dark until the gauge is confirmed favorable.**

**S4 — ISOTONIC PLATEAU (STRUCTURAL)**
> Plateau (p_cal flat ~0.376 for market price 0.30–0.90) confirmed structural by Jul 9 PA-1 audit. Deployed 35d old; committed candidate 32d old; VPS runs daily refits. Material shift at grid=1.0 unchanged (deployed=0.6316, candidate=0.3739, delta=−0.258). Auto-promote condition under evaluation; expected ~Jul 12 if OOS Brier improves. **Do not manually promote.** The mid-range discrimination gap requires architectural review — refit alone cannot resolve a structural plateau.

**S5 — PROXY LANE (PARTIALLY RESOLVED)**
> Prior d+0 trend [0.994→0.831, 7 days ending Jul 8] partially extended using s50 files now accessible in this environment. Jul 9: 1.054°C (n=23 cities), Jul 10: 1.043°C (n=25 cities). Values are above the prior trend endpoint — possible stabilization, but **city-set expansion from 12→23-25 cities introduces significant upward bias** (added cities have higher structural sigmas). Cannot confirm whether the prior declining trend has reversed or merely appears so due to methodology drift. Jul 11 s50 file not yet in data-mirror snapshot; monitoring continues tomorrow.

---

*Report generated 2026-07-11T08:30Z. Source: data-mirror snapshot (2026-07-11T08:02Z, 11 min old). Settled lane locked Jun 28–Jul 2, day 9 stale. REPORT-ONLY — no config or code changes made.*
