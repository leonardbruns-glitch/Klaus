# Calibration & Dispersion Monitor — 2026-07-08

**Snapshot**: 2026-07-08T08:12Z | **Klaus service**: active | **Bankroll**: $136.77 | **Open positions**: 0

> ⚠ BAND_LIVE=False (charter rail halt since 2026-07-06). All band fires are shadow-only.

---

## Section 1 — Settled Lane (confirmed outcome labels)

**Status: LOCKED — day 6 stale. No new outcome labels available.**

The confirmed resolution window remains **Jun 28–Jul 2** (5 days, n=205 city-dates, n≈36,551 sampled rows at 1-in-50). The s50 files contain no condition_ids and no winner flags; a Gamma/CLOB join (via `band_resolution_join.py`) cannot be performed from this environment. Days Jul 3–7 are resolved in reality but remain unlabeled in this pipeline.

| Metric | Value | Alert threshold | Status |
|--------|-------|----------------|--------|
| 7d rolling Brier | **0.053** | > 0.15 | ✅ No alert (ref: 0.114) |
| 7d ECE (10 bins) | **0.019** | > 0.05 | ✅ No alert |
| 7d rank-rho (p_cal vs outcome) | **+0.446** | < +0.15 | ✅ No alert |

All three settled-lane metrics carry forward unchanged from the Jul 7 state. They are **6 days stale** and reflect the Jun 28–Jul 2 window only.

**Note on stale metrics**: Low Brier (0.053) and positive rho (+0.446) indicate the model was well-calibrated and directionally correct on the Jun 28–Jul 2 window. This does not reflect whether calibration has held in Jul 3–8.

---

## Section 2 — Proxy Lane (early warning, unsettled)

Today's snapshot: **2026-07-08, up to 08:06Z** (all-morning PRE_PEAK/AT_PEAK data).

**Method**: median p_cal per bucket across all morning rows; sentinel fix lo<0→mid=hi−0.5, hi>100→mid=lo+0.5; p_cal-weighted implied sigma per city.

| | Today (Jul 8) | Prior state (Jul 7) |
|---|---|---|
| All-city median σ | **0.831°C** | 0.822°C (prior state live snapshot) |
| Plateau-filtered median σ | 0.813°C | n/a (different methodology) |
| Cities present | 12/12 | 11/12 (missing singapore) |
| Delta vs 7d baseline (0.994) | **−16.4%** | −17.3% |

**Day 7 reading: 0.831°C** — a fractional uptick (+1.1%) from the prior state's day-6 value of 0.822. This is within methodology noise (different timing, different missing cities). The trend has **not confirmed a reversal**.

**Per-city sigmas today** (median p_cal method):

| City | σ (°C) | Plateau? |
|------|--------|----------|
| amsterdam | 0.807 | YES |
| ankara | 1.419 | YES |
| beijing | 1.387 | YES |
| chengdu | 1.481 | — |
| istanbul | 0.863 | YES |
| kuala-lumpur | 0.831 | — |
| london | 0.831 | YES |
| munich | 0.813 | — |
| paris | 1.097 | YES |
| singapore | 0.666 | — |
| taipei | 0.749 | YES |
| wuhan | 0.725 | — |

**Seven-day trend** (all-computable median, prior state method for days 1–6; today's method for day 7):

| Day | Date | σ median | vs baseline |
|-----|------|---------|------------|
| 1 | ~Jul 2 | 0.994 | baseline |
| 2 | ~Jul 3 | 0.950 | −4.4% |
| 3 | ~Jul 4 | 0.906 | −8.9% |
| 4 | ~Jul 5 | 0.885 | −11.0% |
| 5 | ~Jul 6 | 0.862 | −13.3% |
| 6 | Jul 7 | 0.822 | −17.3% |
| **7** | **Jul 8** | **0.831** | **−16.4%** |

The proxy lane remains well below baseline for a seventh consecutive day. The marginal uptick is not conclusive given methodology differences across runs.

**Early-warning assessment**: NOT a standalone alert, but consistent with the confirmed S3 dispersion decay. No baseline recovery detected.

---

## Section 3 — Dispersion Gauge (edge variable — most important)

**Status: LOCKED. disp_ratio7 = 0.817 — ALERT FIRING (day 6 stale).**

The dispersion premium is the band strategy's load-bearing quantity. The condition is: implied width (p_cal-weighted std across bucket ladder) > realized width (|resolved bucket − mode bucket|). This edge **does not exist** when ratio < 1.10.

| Day | Implied σ | Realized σ | Ratio | Status |
|-----|-----------|------------|-------|--------|
| Jun 28 | 0.807°C | 1.000°C | **0.807** | ❌ inverted |
| Jun 29 | 0.794°C | 1.000°C | **0.663** | ❌ inverted |
| Jun 30 | 0.860°C | 0.917°C | **0.976** | ❌ inverted |
| Jul 1 | 0.807°C | 0.656°C | **0.866** | ❌ inverted |
| Jul 2 | 0.817°C | 1.000°C | **0.858** | ❌ inverted |
| Jul 3–7 | — | — | **null** | No labels |

**7d median ratio: 0.817** (ALERT FIRES: threshold 1.10).

**The edge is inverted across all 5 confirmed days.** The market is pricing less dispersion than actually realized — the band's theoretical premise (market overprices dispersion = we capture it) is **not holding**. The June 2026 finding of true sigma ~1.3°C < implied has reversed: the realized deviation now exceeds the implied width on every confirmed date.

**Regional breakdown**: All 5 confirmed dates share the same inverted signal; insufficient data to separate US/EU/Asia (weather city markets, not regional by geography of the city for this metric).

**Trend vs prior reports**: Ratio has been locked at 0.817 for 5 reports (data stale since Jun 28–Jul 2 window). The 7-day window would slide to Jul 2–8 if labels become available, but today no new data enters.

**Critical note**: BAND_LIVE was set to False on 2026-07-06 due to the charter equity rail breach — not the dispersion ratio. The dispersion alert is independent and older. Even if the equity rail were resolved, this alert would argue for continued suspension of the band until ratio returns above 1.10 for 5 consecutive confirmed days.

---

## Section 4 — Isotonic Staleness

| | Deployed | Candidate |
|---|---|---|
| File | `config/stwa_isotonic.json` | `config/stwa_isotonic_candidate.json` |
| Refit date | 2026-06-06 | 2026-06-09 |
| Age | **32 days** | **29 days** |

**Grid comparison** (showing points with delta > 0.01):

| Grid point | Deployed | Candidate | Delta | Material? |
|-----------|---------|-----------|-------|----------|
| 0.00 | 0.0000 | 0.0175 | +0.018 | No |
| 0.05 | 0.0695 | 0.0758 | +0.006 | No |
| 0.10 | 0.1340 | 0.1408 | +0.007 | No |
| 0.15 | 0.1828 | 0.1828 | 0.000 | No |
| 0.20 | 0.2663 | 0.2588 | −0.008 | No |
| 0.25 | 0.3557 | 0.3535 | −0.002 | No |
| 0.30–0.90 | 0.3801 | 0.3739 | −0.006 | No |
| 0.95 | 0.3822 | 0.3739 | −0.008 | No |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **YES** |

**One material point**: grid=1.00 only. Candidate substantially lower at the extreme (0.374 vs 0.632). Direction of shift: candidate would LOWER p_cal for market prices near 1.0.

**Both maps are degenerate**: calibrated value is flat at ~0.380 (deployed) / 0.374 (candidate) for any market price between 0.30 and 0.90. This means the model assigns identical ~38% probability regardless of whether the market says 30%, 50%, or 90%. The isotonic is not providing meaningful calibration across the mid-range.

**Recommendation** (report-only): DO NOT DEPLOY candidate. Material shift at grid=1.0 would lower p_cal on high-confidence fills — net direction is conservative/safer, but the degenerate midrange plateau is a systemic problem that a fresh refit should fix, not partial deployment. The live-refit cron has been inactive since Jun 9. A fresh VPS refit against all available Jul data is needed.

---

## Section 5 — State Transitions (diff vs prior 2026-07-07)

| Field | Prior (Jul 7) | Today (Jul 8) | Change |
|-------|--------------|--------------|--------|
| brier7 | 0.053 | 0.053 | No change (locked) |
| ece7 | 0.0194 | 0.0194 | No change (locked) |
| rho7 | 0.4458 | 0.4458 | No change (locked) |
| disp_ratio7 | 0.817 | 0.817 | No change (locked) |
| proxy σ today | 0.822 (day 6) | 0.831 (day 7) | +0.009 fractional uptick |
| Alert count | 3 | 3 | All persist, no new |
| Bankroll | $42.02 | $136.77 | +$94.75 (unexplained outside scope) |
| Isotonic deployed age | 31d | **32d** | +1d, still inactive |
| Isotonic candidate age | 28d | **29d** | +1d, still inactive |

**No new alerts fired. No existing alerts cleared.**

---

## ALERTS

**S3 — DISPERSION RATIO ALERT (PERSISTS)**
> 7d median dispersion ratio = **0.817 < 1.10** (threshold). Day 6 stale (locked Jun 28–Jul 2).
> Edge inverted on all 5 confirmed days. Proxy lane day 7 (σ=0.831) is the seventh consecutive below-baseline reading. The band's core premise — that implied dispersion exceeds realized — is **not holding**. This edge is decaying.
> Re-enable condition: disp_ratio ≥ 1.10 for 5 consecutive confirmed days. Not measurable without outcome labels.

**S4 — ISOTONIC STALENESS (PERSISTS)**
> Deployed isotonic **32 days old** (refit Jun 6), candidate **29 days old** (refit Jun 9). Material shift at grid=1.0 only (delta=−0.258). DO NOT DEPLOY candidate. Both maps have a degenerate flat plateau at ~0.38 across 0.30–0.90 market price range. Live-refit cron inactive since Jun 9.

**S5 — PROXY LANE BELOW BASELINE (PERSISTS)**
> Day 7 of below-baseline implied sigma. Seven consecutive readings: [0.994, 0.950, 0.906, 0.885, 0.862, 0.822, **0.831**]. Today −16.4% vs baseline. Fractional uptick (+1.1%) does not constitute a confirmed reversal — within methodology noise.

---

*Report generated 2026-07-08T08:12Z. Source: data-mirror snapshot ab613add (2026-07-08T08:07Z). Settled lane locked Jun 28–Jul 2; no new outcome labels. REPORT-ONLY — no config changes.*
