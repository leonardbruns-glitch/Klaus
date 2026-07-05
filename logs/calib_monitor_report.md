# Calibration & Dispersion Monitor — 2026-07-05

**Snapshot**: 2026-07-05T08:05:48Z (age ~5 min ✓)  
**System**: `active` ✓ | **Bankroll**: $44.92 cash (↑$3.97 vs yesterday $40.96) | **Open positions**: 0

**Trading mode**: Standalone YES **PAUSED** (BAND_YES_LIVE_MIN_DOUT=9) | BAND_NO **disabled** | PAIR_FAV **shadow** (BAND_PAIR_SHADOW=True) | 4 shadow posts logged today (Taipei d+0 + Wuhan d+0 pairs)

---

## 1. SETTLED LANE (confirmed labels)

**Status: 7d window LOCKED at Jun 28–Jul 2 — third consecutive stale day.**

The window has not advanced in three days:
- **Jul 3**: s50 file 1.26 MB, still exceeds environment limit
- **Jul 4**: 10 POST_PEAK city-days resolved before snapshot, all non-allowlist, 0 finite ratio pairs
- **Jul 5**: 16 POST_PEAK cities resolved before 08:10 UTC, all non-allowlist or partial; same degeneration

The 7d Brier/ECE/rho metrics carry forward unchanged:

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Brier7 | **0.053** | < 0.15 | ✅ OK |
| ECE7 | **0.019** | < 0.05 | ✅ OK |
| Rank-rho (Spearman) | **0.446** | > 0.15 | ✅ OK |

No alert thresholds crossed. These numbers represent Jun 28–Jul 2; they are now 3–10 days old. Do not treat them as a live health signal.

**Jul 5 POST_PEAK detail (informational, non-allowlist, n=16 city-days):**

15/16 city-days degenerate: n_nz=1 with p_cal=0.6316 (isotonic grid=1.0 output for winner bucket). Qingdao partial: n_nz=2, implied sigma 0.500°C, non-allowlist. Pattern is structurally identical to Jul 4: the isotonic plateau collapses all non-winning-bucket probability to zero in POST_PEAK data.

---

## 2. PROXY LANE (early warning — today's PRE_PEAK, unsettled)

**Method**: Latest-snapshot-per-bucket p_cal-weighted std of bucket midpoints per allowlist city (overflow bucket excluded). Baseline: 0.994°C (7d median, carried forward from prior window).

**Allowlist cities PRE_PEAK at 08:10 UTC:**

| City | n buckets | n nonzero | σ_cal | σ_mc | Note |
|---|---|---|---|---|---|
| ~~ankara~~ | ~~10~~ | ~~9~~ | ~~173.1°C~~ | — | **EXCLUDED — artifact** (n_nz=9/10 plateau) |
| amsterdam | 6 | 4 | **0.787°C** | 0.347°C | 2 plateau hits (21–22°C); genuine |
| beijing | 10 | 2 | **0.499°C** | 0.422°C | n_nz=2 (33°C + 34°C), high-confidence; **INCLUDED** (contrast: artifact yesterday 35.8°C was a different market) |
| chengdu | 10 | 4 | **0.910°C** | 1.036°C | 2 plateau hits (35–36°C); genuine |
| london | 10 | 7 | **0.859°C** | 0.476°C | 1 plateau hit (29°C); clean distribution |
| munich | 10 | 9 | **1.795°C** | 0.628°C | 1 plateau hit (26°C); **NOT artifact** (diverse p_cal values); genuine wide July uncertainty |
| ~~paris~~ | — | — | — | — | **ABSENT** — no PRE_PEAK rows in today's data |
| wuhan | 10 | 6 | **1.213°C** | 0.533°C | 3 plateau hits (28–30°C each); plateau-limited but sigma plausible |

**London bucket detail (band's key trading horizon, pair_fav universe):**

| Bucket | p_cal | p_mc |
|---|---|---|
| [27.0, 28.0) | 0.0246 | 0.0239 |
| **[28.0, 29.0)** | **0.3617** | **0.2278** |
| **[29.0, 30.0)** | **0.3801** | **0.4793** |
| [30.0, 31.0) | 0.2561 | 0.1815 |
| [31.0, 32.0) | 0.0153 | 0.0105 |

Mode [29.0, 30.0). Three-bucket spread, implied sigma 0.859°C. p_mc places more weight at 29°C (mode agrees). Clean distribution, no artifact.

**Cleaned proxy lane** (exclude ankara; include all others including beijing):

σ values: [0.499, 0.787, 0.859, 0.910, 1.213, 1.795]°C | **Median = 0.885°C** | 7d baseline = 0.994°C | **Delta = −10.9%**

**4-day below-baseline trend** (baseline → Jul 3 → Jul 4 → Jul 5):

| Date | Cleaned σ | vs baseline |
|---|---|---|
| baseline | 0.994°C | — |
| 2026-07-03 | 0.950°C | −4.4% |
| 2026-07-04 | 0.906°C | −8.9% |
| **2026-07-05** | **0.885°C** | **−10.9%** |

The declining trend is continuing, not arrested. Four consecutive readings below baseline. Note day-over-day changes: Munich 0.946→1.795°C (genuine; wide July heat-wave uncertainty), Beijing re-enters as genuine (was excluded yesterday as 35.8°C artifact from a different market day), Paris absent today.

This is not a pre-registered alert on its own. The threshold for escalation: 5 confirmed consecutive below-baseline days. Next reading is day 5.

---

## 3. DISPERSION GAUGE ⚠ ALERT PERSISTS — WINDOW NOW STALE

**This is the load-bearing section. The trading pause flows from this gauge.**

### 3a. Headline metric

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Disp ratio 7d median | **0.817** (Jun 28–Jul 2, locked) | ≥ 1.10 | 🔴 ALERT |
| Operative d+2 estimate | **~0.34** (last known, Jun) | ≥ 1.10 | 🔴 ALERT |

### 3b. Resolved-date log (all available data)

| Date | n pairs | n finite | Ratio | Impl σ | Real dev |
|---|---|---|---|---|---|
| 2026-06-28 | 25 | 17 | 0.807 | 0.807°C | 1.000°C |
| 2026-06-29 | 28 | 19 | 0.663 | 0.794°C | 1.000°C |
| 2026-06-30 | 22 | 14 | 0.976 | 0.860°C | 0.917°C |
| 2026-07-01 | 26 | 17 | 0.866 | 0.807°C | 0.656°C |
| 2026-07-02 | 24 | 12 | 0.858 | 0.817°C | 1.000°C |
| 2026-07-03 | — | — | **unavailable** | — | — |
| 2026-07-04 | 10 | **0** | **degenerate** | — | — |
| **2026-07-05** | **16** | **0** | **degenerate** | — | — |

5 measured points, all below 1.10. 3 consecutive unmeasurable points. The **most recent non-degenerate measurement is Jul 2 — now 3 days ago**. The 7d window is effectively frozen.

### 3c. Edge state — plainly stated

**The edge is decaying and the gauge is broken. Both need the same fix.**

The five measured points (Jun 28–Jul 2) uniformly show implied σ < realized σ. The band sells probability wings; when markets correctly price uncertainty, the wings are not mispriced and the band donates to liquidity. Ratio 0.817 means the market's implied spread is 82% of what temperatures actually do — the overpricing that created the edge has compressed.

Three consecutive degenerate days (Jul 3–5) mean this monitor cannot confirm whether the ratio has recovered or worsened since Jul 2. The re-enable condition (≥1.10 for 5 days) requires not just recovery but also a working measurement instrument. Neither is confirmed.

**State as of this report**: No standalone YES, no standalone NO, pair_fav in shadow. This is the correct posture given the information available.

---

## 4. ISOTONIC STALENESS ⚠ ALERT PERSISTS

Both configs one day older than yesterday. No refit activity.

| | Deployed | Candidate |
|---|---|---|
| Refit date | 2026-06-06 | 2026-06-09 |
| **Age today** | **29 days** | **26 days** |
| n_hist | 76,617 | 76,617 |
| n_live | 0 | 1,037 (unchanged since Jun 9) |
| near_identity_maxdev | 0.568 | 0.626 |

**Grid comparison:**

| grid | deployed | candidate | Δ | flag |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 | |
| 0.30–0.90 | **0.3801** | **0.3739** | −0.006 | plateau in both |
| 0.95 | 0.3822 | 0.3739 | −0.008 | |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **MATERIAL — candidate worse** |

**DO NOT DEPLOY candidate.** The candidate removes the 0.6316 high-confidence signal at grid=1.0. Deployed retains the only functional discriminative region.

**Structural note (unchanged)**: The plateau (0.30–0.90 → 0.3801) in both configs causes:
1. Proxy-lane artifacts in ankara (and formerly beijing when spread is wide)
2. POST_PEAK d+0 dispersion gauge degeneration (n_nz=1 per city-day, 3 consecutive days)
3. Inability to measure gauge recovery or worsening

The live-refit cron has been inactive for 26 days (n_live candidate=1,037 frozen). ECE=0.019 means no active calibration crisis, but restoring the gauge requires a plateau-breaking refit — a full live-data isotonic that can discriminate among the 0.30–0.90 raw score range.

---

## 5. STATE TRANSITIONS

| Metric | 2026-07-04 | 2026-07-05 | Change |
|---|---|---|---|
| Brier7 | 0.053 | **0.053** | Unchanged |
| ECE7 | 0.019 | **0.019** | Unchanged |
| Rank-rho | 0.446 | **0.446** | Unchanged |
| Disp ratio7 (d+0) | 0.817 | **0.817** | Unchanged — 3rd degenerate day |
| Disp ratio (d+2) | ~0.34 | **~0.34** | No new d+2 data |
| Window staleness | 2 days no advance | **3 days no advance** | Worsening |
| Proxy σ (cleaned) | 0.906°C | **0.885°C** | −2.3% day-over-day; 4th below-baseline |
| Munich proxy σ | 0.946°C | **1.795°C** | ↑ significantly; genuine wide uncertainty |
| Beijing proxy σ | excluded (artifact) | **0.499°C** (genuine) | Market changed; included today |
| Paris proxy σ | 1.006°C | **absent** | No PRE_PEAK rows |
| POST_PEAK degenerate | Jul 4: 0/10 finite | **Jul 5: 0/16 finite** | Persists; broader city set |
| Bankroll (cash) | $40.96 | **$44.92** | +$3.97 (+9.7%); source outside scope |
| BAND_PAIR_SHADOW | (not recorded) | **True** | Shadow-only pair_fav |
| Isotonic deployed age | 28d | **29d** | +1 day stale |
| Isotonic candidate age | 25d | **26d** | +1 day stale |
| Alerts | S3, S4 | **S3, S4** | Both persist |

---

## ALERTS (pre-registered only)

### 🔴 ALERT S3 PERSISTS — Dispersion ratio < 1.10 (8+ consecutive days)

**7d median ratio = 0.817 (locked Jun 28–Jul 2). Three consecutive degenerate days (Jul 3–5). Window now 3 days without new measurement.**

The gauge is no longer measuring; it is reporting a stale historical reading. The 0.817 is not wrong — it was correctly computed from Jun 28–Jul 2 — but it cannot confirm the ratio today. Continued degeneration means any "recovery" would be invisible to this monitor.

Re-enable condition (from state_log 2026-07-03): disp_ratio ≥ 1.10 × 5 consecutive days. This condition cannot be evaluated until the gauge is restored.

**New this cycle**: Window staleness is the dominant risk now. A re-enable decision made without a working gauge would be flying blind on the primary edge variable.

### 🔴 ALERT S4 PERSISTS — Isotonic material shift; both configs stale 26–29 days

At grid=1.0: deployed=0.6316, candidate=0.3739, delta=−0.2577. DO NOT DEPLOY candidate.

Both configs share n_hist=76,617, no new live data since Jun 9. The isotonic plateau (0.30–0.90 → 0.3801) is the root cause of dispersion gauge degeneration now running 3 days. Without a plateau-breaking refit, this monitor will continue producing degenerate results for POST_PEAK allowlist data.

Recommended action (VPS owner): verify live-refit cron health; run manual plateau-breaking refit with current live data; validate on held-out resolved data before deploying.

---

*calib-agent@klaus | 2026-07-05T08:10Z | Branch: claude/find-lag-parameter-rFQ0N*
