# Calibration & Dispersion Monitor — 2026-07-06

**Snapshot**: 2026-07-06T07:58:16Z (age ~0 min ✓)  
**System**: `active` ✓ | **Bankroll**: $123.32 (exec-audit scope; +$78.40 vs prior calib snapshot) | **Open positions**: 0

**Trading mode**: Standalone YES **PAUSED** (BAND_YES_LIVE_MIN_DOUT=9) | BAND_NO **disabled** | PAIR_FAV **shadow** (BAND_PAIR_SHADOW=True)

---

## 1. SETTLED LANE (confirmed labels)

**Status: 7d window LOCKED at Jun 28–Jul 2 — fourth consecutive stale day.**

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Brier7 | **0.053** | < 0.15 | ✅ OK (stale) |
| ECE7 | **0.019** | < 0.05 | ✅ OK (stale) |
| Rank-rho (Spearman) | **0.446** | > 0.15 | ✅ OK (stale) |

These values are unchanged from 2026-07-02. They represent Jun 28–Jul 2 and are now 4–11 days old. **Do not treat them as a live health signal.**

**Why the window cannot advance:** Brier/ECE/rank-rho require outcome labels per (city, date, bucket). The s50 pricer eval file contains no condition_ids; joining to Gamma API resolution requires a batch of condition_ids not derivable from the s50 alone. This was solvable in earlier monitors via band_struct fire logs; that path is currently not replicated in this agent's scope.

**Jul 3 data (previously blocked — now partially available):**  
The Jul 3 s50 file (1.26 MB) was inaccessible to yesterday's monitor. It is accessible today. Brier computation requires outcome labels and remains blocked, but the dispersion gauge can use the implied_sigma portion. See Section 3.

---

## 2. PROXY LANE (early warning — today's PRE_PEAK, unsettled)

**Method**: Latest-snapshot-per-bucket p_cal-weighted std of bucket midpoints per allowlist city (overflow bucket excluded). Baseline: 0.994°C (7d carried forward).

**Today's PRE_PEAK allowlist cities (12 cities at 07:58 UTC):**

| City | n buckets | n nonzero | σ_cal | σ_mc | Note |
|---|---|---|---|---|---|
| amsterdam | 9 | 4 | **0.603°C** | 0.572°C | 2 plateau hits; genuine |
| ankara | 9 | 9 | **1.331°C** | 1.245°C | 0 plateau hits; genuine (contrast: artifact 173°C yesterday — different market) |
| beijing | 9 | 7 | **1.291°C** | 1.256°C | 0 plateau hits; genuine high uncertainty |
| chengdu | 9 | 8 | **1.347°C** | 1.679°C | 1 plateau hit; genuine |
| istanbul | 9 | 4 | **0.422°C** | 0.523°C | 0 plateau hits; genuine |
| kuala-lumpur | 9 | 3 | **0.269°C** | 0.162°C | σ_cal/σ_mc ratio 1.66 — slight inflation but included |
| london | 9 | 6 | **0.832°C** | 0.683°C | Mode **32°C** (heat-wave; up from 29°C yesterday), 2 plateau hits |
| munich | 9 | 6 | **0.878°C** | 0.974°C | Mode 27°C; reverted from 1.795°C spike yesterday (expected) |
| paris | 9 | 8 | **0.989°C** | 0.825°C | Present today (absent yesterday); 2 plateau hits |
| singapore | 6 | 3 | **0.501°C** | 0.636°C | 2 plateau hits; genuine |
| taipei | 9 | 5 | **1.089°C** | 1.103°C | 2 plateau hits; genuine |
| wuhan | 9 | 5 | **0.847°C** | 0.637°C | 2 plateau hits; genuine |

**London bucket detail (band's key trading horizon):**

| Bucket | p_cal | p_mc |
|---|---|---|
| [29.5, 30.5) | 0.0007 | 0.0001 |
| [30.5, 31.5) | 0.0436 | 0.0195 |
| **[31.5, 32.5)** | **0.3801** | **0.2150** |
| **[32.5, 33.5)** | **0.3801** | **0.5690** |
| [33.5, 34.5) | 0.1739 | 0.1200 |
| [34.5, 35.5) | 0.0070 | 0.0090 |

Mode [31.5, 32.5) by p_cal (tied by plateau); p_mc places highest mass at [32.5, 33.5) (0.569). Heat-wave conditions. Three non-trivial buckets. σ_cal=0.832°C is genuine.

**Cleaned proxy lane (all 12 included, no artifacts flagged):**

σ values: [0.269, 0.422, 0.501, 0.603, 0.832, 0.847, 0.878, 0.989, 1.089, 1.291, 1.331, 1.347]°C | **Median = 0.862°C** | 7d baseline = 0.994°C | **Delta = −13.2%**

### ⚠ Proxy lane — escalation threshold crossed (day 5)

| Date | Cleaned σ | vs baseline |
|---|---|---|
| baseline | 0.994°C | — |
| 2026-07-03 | 0.950°C | −4.4% |
| 2026-07-04 | 0.906°C | −8.9% |
| 2026-07-05 | 0.885°C | −10.9% |
| **2026-07-06** | **0.862°C** | **−13.2%** |

**This is the fifth consecutive below-baseline reading.** The prior report noted: *"No standalone pre-registered alert on its own. The threshold for escalation: 5 confirmed consecutive below-baseline days. Next reading is day 5."* Today's reading crosses that threshold. The trend has not arrested; it continues declining at ~2–3% per day.

This is an **observation-grade escalation flag**, not a pre-registered ALERT. The proxy lane measures implied uncertainty in live PRE_PEAK markets, which correlates with (but does not equal) the dispersion ratio. The ratio itself cannot be confirmed without a working gauge.

**Notable city changes today:**
- **Munich**: reverted 1.795°C → 0.878°C as expected (yesterday was genuine but anomalous July heat-spike)
- **Paris**: returned after absence yesterday; σ=0.989°C consistent with prior readings
- **Ankara**: σ=1.331°C (genuine; 0 plateau hits); yesterday was the 173°C artifact from a wide-range market
- **London**: mode shifted 29°C → 32°C (heat-wave regime; σ stable at 0.832°C)

---

## 3. DISPERSION GAUGE ⚠ ALERT PERSISTS — DAY 4 STALE; NEW DATA CONFIRMS COMPRESSION

**This is the load-bearing section. The trading pause flows from this gauge.**

### 3a. Headline metric

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Disp ratio 7d median | **0.817** (Jun 28–Jul 2, locked) | ≥ 1.10 | 🔴 ALERT |
| Operative d+2 estimate | **~0.34** (last known, June) | ≥ 1.10 | 🔴 ALERT |

### 3b. Resolved-date log (updated with Jul 3 data)

| Date | n cities | n finite | Ratio | Impl σ (median) | Real dev | Notes |
|---|---|---|---|---|---|---|
| 2026-06-28 | 25 | 17 | 0.807 | 0.807°C | 1.000°C | Prior monitor full methodology |
| 2026-06-29 | 28 | 19 | 0.663 | 0.794°C | 1.000°C | Prior monitor |
| 2026-06-30 | 22 | 14 | 0.976 | 0.860°C | 0.917°C | Prior monitor |
| 2026-07-01 | 26 | 17 | 0.866 | 0.807°C | 0.656°C | Prior monitor |
| 2026-07-02 | 24 | 12 | 0.858 | 0.817°C | 1.000°C | Prior monitor |
| **2026-07-03** | **6** | **6** | **n/c** | **0.521°C** | **n/c** | **NEW — s50 processed; ratio needs outcome labels** |
| 2026-07-04 | 3 | 3 | n/c | 0.199°C | n/c | Partial; 3 allowlist cities only |
| 2026-07-05 | 3 | 3 | n/c | 0.030°C | n/c | End-of-day near-resolution snapshots |

**Jul 3 detail (6 non-degenerate allowlist cities from POST_PEAK data):**

| City | σ_cal (POST_PEAK) | Note |
|---|---|---|
| amsterdam | 0.046°C | 2/9 nz; narrow |
| ankara | 0.683°C | 2/5 nz; plausible |
| chengdu | 0.323°C | 2/6 nz |
| istanbul | 0.205°C | 3/8 nz |
| singapore | 0.521°C | 3/9 nz |
| **wuhan** | **0.946°C** | **6/9 nz; most informative** |

Median = **0.521°C** — below all five Jun 28–Jul 2 measured values (0.794–0.860°C).

**Methodological caveat**: these POST_PEAK implied_sigmas use the last-snapshot-per-bucket aggregated from the s50 sample. This mixes different timestamps; the prior monitor used full pricer_eval with a single-snapshot approach. The Jul 3 values should be treated as directional (compression confirmed) not authoritative (cannot replace the ratio computation).

### 3c. Edge state — plainly stated

**The dispersion edge is decaying. The gauge cannot measure how far it has decayed since Jul 2.**

The five measured points (Jun 28–Jul 2) uniformly show implied σ < realized σ (ratios 0.663–0.976). The new Jul 3 partial data shows implied σ declining to 0.521°C (median), consistent with continued compression. The Jun 2026 validated premise — *"market-implied dispersion exceeds true dispersion"* — was already violated in the Jun 28–Jul 2 window. Jul 3 does not show recovery.

The re-enable condition (disp_ratio ≥ 1.10 × 5 consecutive days) requires:
1. A working dispersion gauge (needs isotonic refit)
2. Five consecutive days of confirmed ratio ≥ 1.10

Neither is available. The current posture (no standalone YES, no standalone NO, pair_fav in shadow) remains correct given information available.

---

## 4. ISOTONIC STALENESS ⚠ ALERT PERSISTS — DEPLOYED NOW 30 DAYS OLD

Both configs one day older than yesterday. No refit activity.

| | Deployed | Candidate |
|---|---|---|
| Refit date | 2026-06-06 | 2026-06-09 |
| **Age today** | **30 days** | **27 days** |
| n_hist | 76,617 | 76,617 |
| n_live | 0 | 1,037 (frozen since Jun 9) |
| near_identity_maxdev | 0.568 | 0.626 |

**Grid comparison:**

| grid | deployed | candidate | Δ | flag |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 | |
| 0.05–0.25 | 0.0695–0.3557 | 0.0758–0.3535 | ~0 | Small, consistent |
| **0.30–0.90** | **0.3801** | **0.3739** | **−0.006** | **Plateau in both** |
| 0.95 | 0.3822 | 0.3739 | −0.008 | |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **MATERIAL — candidate much worse** |

**DO NOT DEPLOY candidate.** At grid=1.0, candidate outputs 0.3739 vs deployed 0.6316. The deployed config retains the only functional discriminative region (high-confidence POST_PEAK buckets at p_mc→1.0 map to 0.6316 rather than 0.3739). Deploying the candidate would collapse high-confidence signals.

**Structural note (unchanged)**: The plateau (0.30–0.90 → 0.3801) in both configs causes:
1. Proxy-lane artifacts when nearly all buckets hit the plateau (e.g., ankara yesterday)
2. POST_PEAK dispersion gauge degeneration (n_nz=1 when only winner maps above plateau)
3. Inability to measure gauge recovery without a working instrument

The live-refit cron has been inactive 27+ days (candidate n_live=1,037, frozen). The research audit (2026-07-05 10:45Z) identified "VPS isotonic refit cron diagnosis" as the highest-priority action. No change observed as of this snapshot.

---

## 5. STATE TRANSITIONS

| Metric | 2026-07-05 | **2026-07-06** | Change |
|---|---|---|---|
| Brier7 | 0.053 | **0.053** | Unchanged — day 4 stale window |
| ECE7 | 0.019 | **0.019** | Unchanged |
| Rank-rho | 0.446 | **0.446** | Unchanged |
| Disp ratio7 | 0.817 | **0.817** | Unchanged — locked Jun 28–Jul 2 |
| Jul 3 disp data | unavailable | **0.521°C median impl σ (NEW)** | First data point post-lock window |
| Jul 4 disp data | degenerate/partial | **0.199°C (3 cities)** | Confirms compression |
| Jul 5 disp data | degenerate/partial | **0.030°C (3 cities)** | Near-zero end-of-day |
| Window staleness | 3 days | **4 days** | Worsening |
| Proxy σ (cleaned) | 0.885°C (6 cities) | **0.862°C (12 cities)** | −2.3% d/d; 5th below-baseline |
| Proxy below-baseline streak | 4 | **5** | **Escalation threshold crossed** |
| London mode | 29°C | **32°C** | Heat-wave shift |
| Munich proxy σ | 1.795°C (spike) | **0.878°C** | Reverted as predicted |
| Paris | absent | **0.989°C** | Present today |
| Ankara | excluded (artifact) | **1.331°C (genuine)** | Different market today; 0 plateau hits |
| Bankroll (cash) | $44.92 | **$123.32** | +$78.40 (exec-audit scope) |
| Isotonic deployed age | 29d | **30d** | +1 day stale |
| Isotonic candidate age | 26d | **27d** | +1 day stale |
| Alerts | S3, S4 | **S3, S4** | Both persist |

---

## ALERTS (pre-registered only)

### 🔴 ALERT S3 PERSISTS — Dispersion ratio < 1.10 (9+ consecutive days)

**7d median ratio = 0.817 (locked Jun 28–Jul 2). Day 4 without new measurement. NEW: Jul 3 data confirms compression extends past the locked window (6 cities, median implied σ = 0.521°C — below all Jun 28–Jul 2 values).**

The 0.817 value was already below the 1.10 threshold. The new Jul 3 data does not show recovery. The gauge remains broken (ratio non-computable without outcome labels and a working isotonic). The re-enable condition cannot be evaluated.

**Compression trend summary** (implied σ median, POST_PEAK allowlist):
- Jun 28–Jul 2: 0.794–0.860°C → ratio 0.663–0.976
- Jul 3 (new): 0.521°C → ratio unknown
- Jul 4–5: 0.030–0.199°C → ratio unknown (severe compression or near-resolution artifacts)

The edge premise (market overprices uncertainty) is no longer confirmed. Until the gauge recovers and shows ratio ≥ 1.10 for 5 days, no return to live BAND firing is justified.

### 🔴 ALERT S4 PERSISTS — Isotonic material shift; both configs stale 27–30 days

At grid=1.0: deployed=0.6316, candidate=0.3739, delta=−0.2577. DO NOT DEPLOY candidate.

Deployed config now **30 days** since last refit; candidate **27 days** (n_live frozen at 1,037 since Jun 9). The VPS isotonic refit cron diagnosis (highest-priority research action as of 2026-07-05 10:45Z commit) has not produced a new candidate as of this snapshot.

The isotonic plateau is the **structural root cause** of all gauge degeneration. Without a plateau-breaking refit, this monitor will continue producing locked/partial dispersion gauge readings indefinitely.

---

*calib-agent@klaus | 2026-07-06T07:58Z | Branch: claude/find-lag-parameter-rFQ0N*
