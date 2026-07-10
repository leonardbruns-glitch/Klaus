# Calibration & Dispersion Monitor — 2026-07-10

**Snapshot**: 2026-07-10T07:59Z | **Klaus service**: active | **Bankroll**: $158.63 | **Open positions**: 0

> ⚠ BAND_LIVE=False (charter rail breach halt since 2026-07-06). All band fires shadow-only. Rails cleared 2026-07-09T21:53Z; freeze ends tonight 21:53Z; band re-enable decision deferred to 2026-07-12 weekly review.

---

## Section 1 — Settled Lane (confirmed outcome labels)

**Status: LOCKED — day 8 stale. No new outcome labels.**

The confirmed resolution window remains **Jun 28–Jul 2** (5 days, n=205 city-dates, n≈36,551 sampled rows). Days Jul 3–9 are resolved in the real world but remain unlabeled in this pipeline (no band_resolution_join.py output available at run time). The scheduled resolution join is set for **11:23Z today** — if it runs, the next calib monitor run will have updated labels.

| Metric | Value | Alert threshold | Status |
|--------|-------|----------------|--------|
| 7d rolling Brier | **0.053** | > 0.15 | ✅ No alert (ref: 0.114) |
| 7d ECE (10 bins) | **0.019** | > 0.05 | ✅ No alert |
| 7d rank-rho (p_cal vs outcome) | **+0.446** | < +0.15 | ✅ No alert |

All three metrics carry forward unchanged from the Jul 7–8 state (Jun 28–Jul 2 window). They are **8 days stale** and should not be interpreted as a current health signal.

**Stale counter**: Jun 28–Jul 2 confirmed → Jul 3 (day 1 stale) → Jul 10 (day 8 stale).

---

## Section 2 — Proxy Lane (early warning, unsettled)

**Status: PARTIALLY COMPUTABLE — methodology substitution required.**

The prior proxy method (p_cal from pricer_eval_s50 files, 12 allowlist cities, d+0 morning window) cannot be reproduced today: the s50 files are 1.8MB per day and exceed GitHub API retrieval limits in this environment. A substituted proxy using **band_struct fire-record and yes_capture_shadow YES ask prices** is reported below with explicit caveats.

### Substituted Proxy: today (Jul 10, data through 07:56Z)

**D+2 fire-record sigmas** (band pair-fav quoted legs, p_cal weighted, 5 cities):

| City | σ (°C) |
|------|--------|
| beijing | 1.18 |
| chengdu | 1.23 |
| london | 0.85 |
| taipei | 1.18 |
| wuhan | 1.22 |
| **Median** | **1.18** |

**D+2 yes_capture_shadow sigmas** (individual bucket market prices, p_cal weighted, 5 cities excl. London¹):

| City | σ (°C) | n buckets |
|------|--------|----------|
| beijing | 1.27 | 5 |
| chengdu | 1.60 | 6 |
| munich | 1.86 | 7 |
| taipei | 1.70 | 6 |
| wuhan | 1.84 | 7 |
| **Median** | **1.70** | |

¹London excluded: all 8 buckets priced uniformly at 0.37 (BAND_QUOTE_FRAC proxy fallback, degenerate for sigma computation).

**D+1 fire-record sigmas** (2 cities only):
| City | σ (°C) |
|------|--------|
| beijing | 1.16 |
| taipei | 1.08 |
| **Median** | **1.12** |

### Methodology caveat

The prior proxy used p_cal from the full 9-bucket interior distribution across 12 cities for **d+0** markets (same-day forecasts, morning window before local temperature peak). Today's substituted proxy uses **d+1/d+2** markets and only 5–6 cities with active fire records. These are at a different forecast horizon and a different subset of the allowlist.

**The prior 7-day declining trend [0.994, 0.950, 0.906, 0.885, 0.862, 0.822, 0.831] (days 1–7, ending Jul 8) cannot be extended from today's data.** D+1/D+2 sigmas are structurally higher than D+0 (longer horizon = more uncertainty). The values here (1.12–1.70°C) do not indicate recovery or continuation of the prior trend — they are simply a different measurement.

**Early-warning assessment**: Directionally ambiguous. Insufficient data to determine whether the prior below-baseline d+0 run has continued, reversed, or stalled. Restoring pricer_eval_s50 access is needed to resume this indicator.

---

## Section 3 — Dispersion Gauge (edge variable — most important)

**Status: LOCKED. disp_ratio7 = 0.817 — ALERT FIRING (day 8 stale).**

The dispersion premium is the band strategy's single load-bearing quantity. The edge condition requires: implied width (p_cal-weighted std across bucket ladder) > realized width (|resolved bucket − mode bucket| at last pre-resolution snapshot). **This condition has not held on any confirmed day since Jun 28.**

| Day | Implied σ | Realized σ | Ratio | Status |
|-----|-----------|------------|-------|--------|
| Jun 28 | 0.807°C | 1.000°C | **0.807** | ❌ inverted |
| Jun 29 | 0.794°C | 1.000°C | **0.663** | ❌ inverted |
| Jun 30 | 0.860°C | 0.917°C | **0.976** | ❌ inverted |
| Jul 1 | 0.807°C | 0.656°C | **0.866** | ❌ inverted |
| Jul 2 | 0.817°C | 1.000°C | **0.858** | ❌ inverted |
| Jul 3–9 | — | — | **null** | No outcome labels |

**7d median ratio: 0.817** (ALERT threshold: < 1.10).

The band's premise — that Polymarket weather ladders overprice dispersion relative to realized outcomes — is **not holding** on the confirmed data window. The market has been pricing LESS dispersion than actually realized on all 5 confirmed days. The Jun 2026 observation of true sigma ~1.3°C < implied has reversed: realized deviation now exceeds implied width every confirmed date.

**Re-enable condition**: disp_ratio ≥ 1.10 for 5 consecutive confirmed days. This is **unmeasurable while the band is dark** (no new fills = no fill_join records with outcomes for our positions). The band_resolution_join.py scheduled for 11:23Z today may generate Jul 3–9 labels and update this metric.

**Regional breakdown**: All 5 confirmed dates share the inverted signal. Insufficient sample to break down by region (US/EU/Asia) within the temperature-city classification.

**Band re-enable note**: The Jul 12 structural decision about re-enabling the band should weigh the fact that this gauge has been firing continuously since Jun 2026, with the last confirmed window showing inversion across all 5 days. Even if the equity rail clears, **this alert argues for continued shadow-only operation until the ratio is confirmed ≥ 1.10 for 5 consecutive days.**

---

## Section 4 — Isotonic Staleness

**CORRECTION from prior reports (Jul 7–8):** The isotonic refit cron is **NOT inactive**. It runs daily at 09:30Z (confirmed by Jul 9 evening EVOLVE log). The prior reports' claim of "cron inactive since Jun 9" was incorrect — the Jun 9 timestamp in the committed candidate file reflects the last *committed* candidate, not the last refit.

### Current status

| | Deployed | Committed candidate | Live VPS candidate |
|---|---|---|---|
| File | `config/stwa_isotonic.json` | `config/stwa_isotonic_candidate.json` | (not committed) |
| Refit date | 2026-06-06 | 2026-06-09 | Daily 09:30Z |
| Age | **34 days** | **31 days (committed)** | Current |

### Grid comparison (points with |delta| > 0.01)

| Grid point | Deployed | Committed candidate | Delta | Material? |
|-----------|---------|-----------|-------|----------|
| 0.00 | 0.0000 | 0.0175 | +0.018 | No |
| 1.00 | **0.6316** | **0.3739** | **−0.258** | **YES** |
| All others | plateau 0.3801 | plateau 0.3739 | −0.006 | No |

**One material point**: grid=1.00 only. The candidate substantially lowers p_cal at extreme-high market prices. This would reduce confidence on near-certain buckets.

### Plateau: structural, not stale

The deployed and all recent refit candidates show a flat calibrated value (~0.376–0.380) for any market price between 0.30 and 0.90. This plateau is **confirmed structural** by the Jul 9 isotonic PA-1 audit (closed no-defect). The fresh July-data VPS candidate is still flat at g≈0.376 for p∈[0.35,0.85]. This is a property of how Polymarket weather ladders are priced (most active buckets cluster in the 0.35–0.85 range), not a calibration failure that more data will resolve.

**Implication**: p_cal provides no discrimination between market prices of 0.30, 0.50, and 0.90 — all map to p_cal ≈ 0.38. The isotonic is performing calibration at the extremes only.

**Auto-promote condition**: The daily cron will auto-promote the candidate when OOS Brier improves vs. the deployed. Expected window: ~2026-07-12 as more July live data accumulates. **Do not manually promote.**

**Recommendation (report-only)**: Do not deploy the committed candidate. Wait for the daily cron's auto-promote; it will fire when (and only when) OOS Brier actually improves. The structural plateau is a model-architecture finding that cannot be fixed by refit alone — it may require rethinking how the band uses p_cal in the mid-range.

---

## Section 5 — State Transitions (diff vs prior 2026-07-08)

| Field | Prior (Jul 8) | Today (Jul 10) | Change |
|-------|--------------|--------------|--------|
| brier7 | 0.053 | 0.053 | No change (locked day 6→8) |
| ece7 | 0.0194 | 0.0194 | No change (locked) |
| rho7 | 0.4458 | 0.4458 | No change (locked) |
| disp_ratio7 | 0.817 | 0.817 | No change (locked, +2 stale days) |
| Staleness (days) | 6 | **8** | +2 days stale |
| Proxy lane | 0.831 (day 7, d+0, 12 cities) | 1.18–1.70 (d+1/d+2, 5–6 cities) | Different methodology — not comparable |
| Alert count | 3 | 3 | S3 persists, S4 recalibrated, S5 unmonitorable |
| Bankroll | $136.77 | **$158.63** | +$21.86 (ladder fills, BAND_LIVE=False throughout) |
| Rails status | Breached | **CLEARED** (2026-07-09T21:53Z) | First clear since Jul 7 |
| Freeze | Active | **Ends 2026-07-10T21:53Z** | Expires tonight |
| Band re-enable | Deferred | **Deferred to 2026-07-12** | Weekly structural review |
| Isotonic cron | "Inactive since Jun 9" (WRONG) | **ACTIVE (daily 09:30Z)** | Correction |
| Isotonic plateau | Stale (prior framing) | **STRUCTURAL** | PA-1 audit no-defect Jul 9 |
| Isotonic deployed age | 32d | **34d** | +2d |

**Transition summary**: No metrics improved. The settled lane is now 8 days stale (was 6). The proxy lane signal is disrupted by methodology access. The S4 alert is recalibrated — the underlying finding (degenerate plateau, material shift at grid=1.0) is unchanged, but the framing shifts from "cron dead" to "plateau confirmed structural." Rails cleared but band remains dark pending Jul 12 decision.

---

## ALERTS

**S3 — DISPERSION RATIO ALERT (PERSISTS)**
> 7d median dispersion ratio = **0.817 < 1.10** (threshold). Now day 8 stale (locked Jun 28–Jul 2).
> Edge inverted on all 5 confirmed days. The band's core premise — that implied dispersion exceeds realized — **is not holding**. Ratio not updateable while dark (no fill outcomes). Resolution join scheduled 11:23Z today may provide Jul 3–9 data. Re-enable condition: disp_ratio ≥ 1.10 for 5 consecutive confirmed days — not achievable in shadow mode without resolution join data.

**S4 — ISOTONIC PLATEAU (RECALIBRATED)**
> The prior framing "cron inactive, candidate 31d stale" was incorrect. Cron runs daily at 09:30Z. **The plateau (p_cal flat ~0.38 for market price 0.30–0.90) is confirmed structural**, not a staleness artifact (Jul 9 PA-1 audit no-defect). Material shift at grid=1.0 unchanged (deployed=0.6316, candidate=0.3739, delta=−0.258). Auto-promote condition in evaluation; expected ~Jul 12 if OOS Brier improves. Do not manually deploy candidate. **Action**: when auto-promote fires, verify it reduces grid=1.0 discrepancy without degrading the plateau — mid-range discrimination may require architecture change, not just refit.

**S5 — PROXY LANE (UNMONITORABLE)**
> Prior d+0 trend [0.994, 0.950, 0.906, 0.885, 0.862, 0.822, 0.831] — 7 consecutive below-baseline days ending Jul 8 — **cannot be extended today**. Pricer_eval_s50 files (1.8MB/day) are not retrievable via GitHub API in this environment. The substituted d+1/d+2 fire-record proxy (1.12–1.70°C) is at a different horizon and not comparable. **Restoring pricer_eval_s50 access is needed to resume this indicator.** Until then, S5 is unmonitorable — neither confirmed persisting nor confirmed resolved.

---

*Report generated 2026-07-10T08:11Z. Source: data-mirror snapshot fb3780dc (2026-07-10T07:59Z). Settled lane locked Jun 28–Jul 2, day 8 stale. REPORT-ONLY — no config changes.*
