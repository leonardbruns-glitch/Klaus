# Calibration & Dispersion Monitor — 2026-07-23

**Run UTC**: 2026-07-23T08:20Z (estimated)
**Data source**: GitHub MCP API + raw GitHub download (git fetch targeted single-branch)
**Snapshot age**: 20 min (snapshot 2026-07-23T08:00:18Z → OK, <6h limit)
**System**: Klaus systemd active · bankroll $21.495 · 0 open positions · BAND_LIVE=False (day 17 dark)
**Branch**: data-mirror SHA d63a5381 (snapshot), analysis branch d50376f0

---

## 1. SETTLED LANE — 2026-07-22 fresh + rolling window

**Data**: 07-22 s50 file (1.976 MB), 8,875 rows parsed · 374 valid last-PRE_PEAK rows (sentinel-filtered, resolved cities only) · 43 resolved cities (rmax from AT_PEAK/POST_PEAK running_max) · 12 mode-hits excluded from dispersion · 2 no-PRE_PEAK (atlanta, lucknow).

| Metric | Prior carry (07-16..07-21) | 07-22 fresh | Updated 7d (07-17..07-22) | Threshold | Status |
|---|---|---|---|---|---|
| Brier7 | 0.0542 | **0.0784** | **0.0545** | <0.15 | OK |
| ECE7 | 0.0268 | 0.0334 | **0.0269** | <0.05 | OK |
| Rank-rho7 | 0.432 (carry) | 0.213 | **0.430** | >+0.15 | OK |
| n (sampled pairs) | ~32,629 | 374 | ~33,003 | — | — |

**No pre-registered Brier/ECE/rho alerts fired.**

**07-22 per-day Brier (0.0784)** is essentially the same as 07-21 (0.0795). Both are materially worse than the 7d aggregate (~0.054). The 7d estimate is dominated by the accumulated carry (n=32,629 vs 374 fresh). Two consecutive days of elevated per-day Brier is a trend to watch.

**ECE bin breakdown (07-22):**
- [0.0–0.1): n=244 (65.2%) mean_p=0.012 mean_o=0.033 |diff|=0.021
- [0.1–0.2): n=38 (10.2%) mean_p=0.148 mean_o=0.079 |diff|=0.069 ← moderate overconfidence
- [0.2–0.3): n=19 (5.1%) mean_p=0.247 mean_o=0.053 |diff|=0.195 ← **severe overconfidence**
- [0.3–0.4): n=72 (19.3%) mean_p=0.370 mean_o=0.361 |diff|=0.009 ← near-calibrated (plateau zone)
- [0.6–0.7): n=1 (0.3%) mean_p=0.632 mean_o=1.000 — n=1, ignore

**Structural finding (persistent, [0.2–0.3) bin worsening)**: The [0.2–0.3) bin shows severe overconfidence (mean_p=0.247 vs mean_o=0.053 — 4.7× overstated). This is the isotonic transition zone below the plateau. On 07-21 this bin showed |diff|=0.036; today it is 0.195 — a sharp deterioration. The plateau zone [0.3–0.4) is ironically the best-calibrated bin (|diff|=0.009). The dominant [0.0–0.1) bin suppresses aggregate ECE.

**Rank-rho (07-22 standalone): 0.213** — above the 0.15 floor (no alert), but the worst standalone reading so far. Sequential trend: 07-21=0.303, 07-22=0.213. Both materially below the 7d carry (0.430). Slow downward pressure on 7d rho from each fresh daily addition.

---

## 2. PROXY LANE — 2026-07-23 early warning (~08:14 UTC)

**Data**: 07-23 s50 partial, 2,329 rows (latest ts 08:14:33Z) · 28 cities PRE_PEAK · 24 cities already AT_PEAK/POST_PEAK at snapshot time (Asian and early US cities).

| Metric | Today (07-23 ~08:14Z) | 7d baseline | Divergence |
|---|---|---|---|
| Median mode p_cal | 0.3801 | 0.380 | **0.000** |
| Mean mode p_cal | 0.3449 | — | — |

No spike vs 7d baseline. Proxy lane locked by isotonic plateau (virtually all cities at mode p_cal=0.3801; mean pulled lower by tokyo=0.118, qingdao=0.093, moscow=0.227, jeddah=0.000 — anomalous cities where p_raw falls below plateau entry). No book price fields in s50 schema; p_cal vs market divergence cannot be computed. Proxy lane remains insensitive to real forecast shifts.

**Anomalies today**: tokyo mode_pcal=0.118 (after resolving at 34°C yesterday, mode is pointing to a different bucket today — possible model recalibration or distribution shift). jeddah=0.000 suggests all probability mass in sentinel buckets. These warrant monitoring but do not constitute pre-registered alerts.

---

## 3. DISPERSION GAUGE — critical section

**Methodology**: last PRE_PEAK sample per (city, bucket); sentinel buckets excluded (lo<−100 or hi>100); implied_std = sqrt(p_cal-weighted variance of bucket midpoints); realized_dev = |rmax − mode_bucket_mid|; mode-hit threshold 0.5°C; resolved cities only.

### 2026-07-22 full-day dispersion (29 eligible cities)

| City | Region | implied_std | realized_dev | ratio |
|---|---|---|---|---|
| ankara | EU | 1.456 | 1.00 | 1.456 |
| beijing | Asia | 1.937 | 1.00 | **1.937** |
| buenos-aires | US/Other | 0.812 | 1.00 | 0.812 |
| busan | Asia | 1.077 | 1.00 | 1.077 |
| chengdu | Asia | 1.488 | 1.00 | 1.488 |
| chicago | US/Other | 0.813 | 2.53 | 0.321 |
| chongqing | Asia | 1.505 | 1.00 | **1.505** |
| denver | US/Other | 0.121 | 2.49 | 0.049 |
| guangzhou | Asia | 1.217 | 1.00 | 1.217 |
| helsinki | EU | 1.305 | 2.00 | 0.653 |
| istanbul | EU | 0.383 | 4.00 | 0.096 |
| jeddah | US/Other | 0.928 | 1.00 | 0.928 |
| london | EU | 0.836 | 1.00 | 0.836 |
| los-angeles | US/Other | 0.713 | 1.94 | 0.367 |
| madrid | EU | 0.773 | 1.00 | 0.773 |
| manila | Asia | 1.100 | 2.00 | 0.550 |
| mexico-city | US/Other | 1.115 | 2.00 | 0.557 |
| milan | EU | 1.000 | 1.00 | 1.000 |
| munich | EU | 0.851 | 1.00 | 0.851 |
| paris | EU | 0.949 | 1.00 | 0.949 |
| qingdao | Asia | 1.077 | 1.00 | 1.077 |
| san-francisco | US/Other | 1.466 | 5.26 | 0.279 |
| sao-paulo | US/Other | 1.092 | 6.00 | 0.182 |
| seattle | US/Other | 0.563 | 0.80 | 0.704 |
| shanghai | Asia | 1.213 | 1.00 | 1.213 |
| tel-aviv | Asia | 1.043 | 2.00 | 0.521 |
| tokyo | Asia | 1.227 | 1.00 | **1.227** |
| warsaw | EU | 0.933 | 1.00 | 0.933 |
| wuhan | US/Other | 1.165 | 1.00 | 1.165 |
| *Mode-hits (12)*: amsterdam, austin, dallas, houston, karachi, kuala-lumpur, miami, moscow, shenzhen, taipei, toronto, wellington | — | — | — | — |
| *No PRE_PEAK (2)*: atlanta, lucknow | — | — | — | — |

**Region summary (07-22):**

| Region | n eligible | Daily median | Note |
|---|---|---|---|
| EU | 9 | 0.851 | Range: 0.096 (istanbul) to 1.456 (ankara); istanbul severe outlier (model 0.38°C spread, realized 4°C miss) |
| Asia | 10 | **1.215** | Only region above 1.0; beijing 1.937, chongqing 1.505, chengdu 1.488; tel-aviv 0.521 drags down |
| US/Other | 10 | 0.462 | Severely inverted: denver 0.049, sao-paulo 0.182, san-francisco 0.279, chicago 0.321 |
| **All 07-22** | **29** | **0.851** | — |

### Rolling 7d dispersion (settled window 07-17..07-22)

| Date | Daily median | n eligible | Note |
|---|---|---|---|
| 2026-07-17 | 0.927 | ~8 | carried from prior state |
| 2026-07-18 | 0.485 | ~8 | carried |
| 2026-07-19 | 0.925 | ~8 | carried |
| 2026-07-20 | 0.779 | ~18 | carried (prior session fresh) |
| 2026-07-21 | 0.783 | 27 | carried (prior session fresh) |
| **2026-07-22** | **0.851** | **29** | **fresh (this session)** |

**7d median of daily medians (07-17..07-22): 0.817**
Sorted: [0.485, 0.779, 0.783, 0.851, 0.925, 0.927] → median = (0.783+0.851)/2 = **0.817**

**n city-days total**: prior ~77 + 29 new − ~8 (07-16 drop) ≈ **~98** (trend grade, threshold=100).

**Critical transition**: 07-16 (daily=1.196) dropped out of the window — it was the **only day above 1.10** in the prior 7d window. The new window has **0 of 6 settled days above 1.10** for the first time. The 7d median declines from 0.854 to **0.817**.

**Trend vs prior reports:**
- 07-15..07-20 window median: ~0.88 (prior state estimate)
- 07-16..07-21 window median: 0.854 (yesterday's run)
- **07-17..07-22 window median: 0.817 (this run)**
- Three consecutive declines; each session dropping a historical high and adding a sub-1.0 day

**EVOLVE cross-check**: The EVOLVE evening slot (07-22T21:56Z) reported "07-22 partial = 1.105" for its band re-enable trigger. The calib monitor's full-day computation gives 0.851. Reconciliation: at 21:56 UTC, the EVOLVE reads Asia-dominated partial data (24 resolved cities vs full-day 43). Asia 07-22 median=1.215 in the full-day computation — consistent with the EVOLVE's higher partial reading. Both methodologies are internally consistent.

### ⚠️ ALERT S3 — FIRING (pre-registered) — Day 21

**disp_ratio7 = 0.817 < 1.10 — INVERTED DISPERSION EDGE — 21 consecutive days.**

The edge is decaying. The dispersion ratio has declined for 3 consecutive sessions (0.88 → 0.854 → 0.817). The current 7d window contains **zero days above 1.10** — the prior anchor day (07-16=1.196) has exited. Five of six settled days are below 1.0. At n~98, the finding is one session from decision-grade.

The band's core premise is not supported by any day in the current 7d window. The band is dark (BAND_LIVE=False since 07-06, day 17), so no capital is at risk — but this alert conditions any re-enable decision.

Regional finding: Asia is the sole near-neutral region (07-22 median 1.215). If re-enable is reconsidered, Asian markets are the only sub-region where the dispersion edge is not explicitly contradicted by recent data.

---

## 4. ISOTONIC STALENESS

**No refit since 2026-07-21.** The candidate (config/stwa_isotonic_candidate.json) shows refit_utc=07-21T09:30Z and n_live=3,733, **unchanged from the prior session**. Scanning the analysis branch commit history from 07-21T10:00Z to 07-23T08:20Z reveals no isotonic refit commit. If the cron runs at ~09:30 UTC, a new refit may occur later today. Possible disruption: VPS disk hit 94% mid-07-22 before reclaim; cron window may have coincided with heavy disk pressure.

| | Deployed | Candidate |
|---|---|---|
| Refit UTC | 2026-06-06T22:27Z | 2026-07-21T09:30Z |
| Days since refit | **47** | **2** (cron missed 07-22) |
| n_hist | 76,617 | 76,617 |
| n_live | 0 | **3,733** (unchanged, no new live data added) |
| Live calendar days | — | 8 |
| OOS brier (raw) | null | 0.0595 |
| OOS brier (calibrated) | null | 0.0603 |
| near_identity_maxdev | 0.568 | 0.520 |

**Isotonic map comparison (unchanged from prior session):**

| p_raw | deployed | candidate | diff |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0039 | +0.0039 |
| 0.05 | 0.0695 | 0.0741 | +0.0046 |
| 0.10 | 0.1340 | 0.1317 | −0.0023 |
| 0.15 | 0.1828 | 0.2057 | **+0.0229** |
| 0.20 | 0.2663 | 0.2619 | −0.0044 |
| 0.25 | 0.3557 | 0.3508 | −0.0049 |
| 0.30–0.85 | 0.3801 | 0.3744 | −0.0057 (plateau persists in both) |
| 0.90 | 0.3801 | 0.3919 | +0.0118 |
| 0.95 | 0.3822 | 0.4305 | +0.0483 (near-threshold) |
| 1.00 | 0.6316 | **1.0000** | **+0.3684 ← MATERIAL** |

Max abs diff: 0.3684 at p_raw=1.0 → exceeds 0.05 threshold → S4 alert fires.

**New concern**: ECE [0.2–0.3) bin severity jumped from |diff|=0.036 (07-21) to 0.195 (07-22). The candidate raises p_raw=0.15 by +0.023 (deployed 0.1828 → candidate 0.2057). If the pre-plateau transition zone (p_raw 0.10–0.25) is already producing overconfidence, a candidate that nudges p_cal higher in that range would worsen it. The OOS test window is too short (8 days) to detect this.

### ⚠️ ALERT S4 — FIRING (pre-registered)

**Deployed isotonic 47 days old. Candidate refitted 2026-07-21 (2 days stale; cron missed 07-22). n_live=3,733 unchanged.** Material diff at p_raw=1.0 (+0.3684 — candidate removes all shrinkage). OOS brier_cal (0.0603) > brier_raw (0.0595). Near-threshold diff at p_raw=0.95 (+0.0483). New concern: candidate raises the pre-plateau transition zone (p_raw=0.15 +0.023) in the same zone showing worsening ECE overconfidence. Recommend checking cron health before next expected refit (~09:30 UTC today) and human review of tail and pre-plateau behavior before promotion.

---

## 5. STATE TRANSITIONS

| Metric | Prior (2026-07-22 run) | This run (2026-07-23) | Change |
|---|---|---|---|
| brier7 | 0.054 | **0.055** | +0.0003 (carry-dominated; 07-22 per-day 0.078 adding slow upward pressure) |
| ece7 | 0.027 | **0.027** | essentially flat (+0.0001) |
| rho7 | 0.432 | **0.430** | −0.002 (negligible; 07-22 standalone 0.213 adding slow downward pressure) |
| disp_ratio7 | 0.854 | **0.817** | **−0.037 — declining; 07-16=1.196 dropped; 0/6 days above 1.10** |
| disp_ratio7_n | ~77 | **~98** | approaching decision-grade (n=100) |
| disp_inversion_days | 20 | **21** | 07-22 daily=0.851 confirms sub-1.10 |
| S3 alert | FIRING (d20) | **FIRING (d21)** | ratio declining; 0/6 above threshold in window |
| S4 alert | FIRING | **FIRING** | candidate stale 2d (cron missed); material diff unchanged; new ECE concern |
| candidate refit_utc | 2026-07-21 | **2026-07-21** | no update |
| band_dark_days | 16 | **17** | BAND_LIVE=False since 07-06 |
| bankroll | $21.495 | $21.495 | unchanged |

**Key transitions:**
- **S3 worsening**: disp_ratio7 falls to 0.817 (lowest 7d median in the monitoring window). The window now contains 0/6 days above 1.10. The prior window's only above-threshold anchor (07-16=1.196) has exited. At ~98 city-days, the next session should reach decision-grade n=100.
- **S4 update**: Candidate cron missed 07-22 (no commit in branch history; n_live frozen at 3,733). New concern: candidate raises pre-plateau zone (p_raw=0.15 +0.023) in the region where ECE overconfidence is now 0.195.
- **Rho trend**: sequential standalone readings 0.303 (07-21) → 0.213 (07-22) suggest directional degradation, though both remain above the 0.15 floor. Watch next 2-3 sessions.
- **ECE [0.2–0.3) worsening**: |diff| jumped from 0.036 to 0.195 in one day. Not a pre-registered alert, but the pattern warrants tracking.

---

## ALERTS

### ⚠️ ALERT S3 — FIRING (pre-registered)

**disp_ratio7 = 0.817 < 1.10 — INVERTED DISPERSION EDGE — day 21 consecutive.**

The edge is decaying. Three consecutive sessions of declining 7d median (0.88 → 0.854 → 0.817). The current 7d window contains zero days above 1.10. Five of six settled days are below 1.0. The band's core premise — that markets overestimate temperature dispersion relative to what Chainlink resolves — is not supported by any settled day in the current window. One session from decision-grade n≥100.

The band is dark (BAND_LIVE=False), so this serves as a thesis integrity check. If BAND_LIVE were True, this would require immediate halt and full review. Any re-enable decision for the weather band must account for this finding. The only sub-region where the edge is not explicitly contradicted: Asia (07-22 median 1.215, though still below 1.10 on a single-day basis this is the direction the thesis requires).

### ⚠️ ALERT S4 — FIRING (pre-registered)

**Deployed isotonic 47 days stale. Candidate (07-21 refit) now 2 days stale — cron missed 07-22 (no commit in branch history; possible VPS disk disruption). n_live=3,733 frozen.** Material diff at p_raw=1.0 (+0.3684 — candidate removes all shrinkage, deployed applies 0.369 correction). OOS brier_cal (0.0603) > brier_raw (0.0595) — isotonic calibration adding marginal negative OOS value. Near-threshold diff at p_raw=0.95 (+0.0483). New S4 sub-finding: candidate raises pre-plateau zone (p_raw=0.15, +0.023) in the same region showing today's worst ECE overconfidence (|diff|=0.195 in [0.2–0.3) bin). Recommend verifying cron health, checking whether 07-22 refit landed on VPS but wasn't committed, and human review of tail and pre-plateau behavior before any promotion.

---

*Data access: targeted git fetch (single-branch, 20s) + raw GitHub download via curl + GitHub MCP API. 07-22 full s50: 8,875 rows, 43 resolved cities (rmax from AT_PEAK/POST_PEAK running_max), 374 valid Brier pairs, 29 dispersion-eligible cities, 12 mode-hits. 07-23 partial s50: 2,329 rows, 28 PRE_PEAK cities (08:14 UTC). Isotonic configs: branch HEAD d50376f0. All computations in-session Python.*
