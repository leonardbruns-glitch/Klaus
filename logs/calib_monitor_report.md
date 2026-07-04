# Calibration & Dispersion Monitor — 2026-07-04

**Snapshot**: 2026-07-04T08:01:06Z (age < 6h ✓)  
**System**: active ✓ | **Bankroll**: $40.96 (cash; down from prior combined estimate $79.57 — see note) | **BAND_YES_LIVE_MIN_DOUT**: 9 (standalone YES **PAUSED** per 07-03 19:25 state_log) | **BAND_NO_ENABLED**: False (halted 2026-07-02) | **PAIR_FAV**: active

**Bankroll note**: Cash $40.96 vs prior $79.57 combined mark (cash $62.38 + d+2 YES leg marks). Overnight delta reflects sprint_ladder Asia shots (sleeve started $60, $20 hard reserve) + MAKER_CASH_FRAC change 0.90→0.40. Full-equity context is outside calib-monitor scope but flagged for owner awareness.

**Data access limitation**: `git fetch origin data-mirror` timed out twice (single-branch fetch of claude/find-lag-parameter-rFQ0N succeeded). The 2026-07-03 s50 file (1.26 MB) exceeded MCP display limits — the 7d rolling window cannot advance past Jul 2. This is stated explicitly wherever it affects the analysis.

---

## 1. SETTLED LANE (resolved market-days)

**7d window status**: Prior report covered Jun 28 – Jul 2 (n=36,551 rows, 205 city-date pairs). Jul 3 s50 file unavailable (1.26 MB). Jul 4 POST_PEAK data (471 rows, 10 city-days) is available but all 10 cities are **non-allowlist** — they resolve before 08:00 UTC while allowlist cities (Chengdu, Wuhan, Beijing, Munich, London, etc.) close 16:00–23:00 UTC. The 7d rolling metrics carry forward from the prior report without update.

**7d metrics (Jun 28 – Jul 2, carried forward):**

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Brier7 | **0.053** | < 0.15 | ✅ OK |
| ECE7 | **0.019** | < 0.05 | ✅ OK |
| Rank-rho (Spearman) | **0.446** | > 0.15 | ✅ OK |

No threshold crossings. No alerts fire in the settled lane.

**Today's non-allowlist signal (informational, not rolled into 7d window):**

10 POST_PEAK city-days resolved before snapshot (Austin, Buenos Aires, Dallas, Houston, Los Angeles, Miami, Qingdao, San Francisco, Seattle, Toronto). n=471 rows.

| Metric | Value |
|---|---|
| Brier | 0.0147 |
| ECE | 0.0379 |
| Rank-rho | 0.9490 |

ECE bin detail: 425 rows in [0.0, 0.1) correctly assigned near-zero probability; 42 rows in [0.6, 0.7) with mean_o=1.00 (all high-confidence predictions correct); 3 rows in [0.3, 0.4) with mean_o=1.00 (plateau underconfidence, structural). The model is performing well on this non-allowlist sample, but these cities are not the band's trading universe.

**Plateau note (structural, unchanged)**: Deployed isotonic maps grid 0.30–0.90 uniformly to p_cal=0.3801. Every bucket with raw score 0.30–0.90 receives identical p_cal regardless of order. This carries material consequences for the dispersion gauge (see §3).

---

## 2. PROXY LANE (early warning — today 2026-07-04, unsettled)

**Method**: PRE_PEAK p_cal-weighted std of bucket midpoints per city-day, overflow bucket (hi=999) excluded. Prior 7d baseline: 0.994°C median.

**Allowlist cities (d+0 PRE_PEAK, closes today 16:00–23:00 UTC):**

| City | n buckets | n nonzero | Impl sigma | Note |
|---|---|---|---|---|
| amsterdam | 10 | 7 | **0.838°C** | |
| ~~ankara~~ | ~~10~~ | ~~10~~ | ~~75.2°C~~ | **ARTIFACT — excluded** (see below) |
| ~~beijing~~ | ~~10~~ | ~~9~~ | ~~35.8°C~~ | **ARTIFACT — excluded** (see below) |
| chengdu | 10 | 4 | **0.768°C** | |
| munich | 10 | 7 | **0.946°C** | |
| paris | 10 | 8 | **1.006°C** | |
| wuhan | 10 | 7 | **1.112°C** | Wuhan gap **RESOLVED** (0 rows yesterday → 88 today) |
| london (d+1) | 10 | 7 | **0.865°C** | Closes 2026-07-05 00:00 UTC |

**Ankara/Beijing artifact**: The isotonic plateau assigns p_cal=0.3801 to every bucket whose raw score exceeds ~0.30. When 9–10 buckets spanning a 10°C+ temperature range all carry p_cal=0.38, the weighted std is dominated by the bucket spread, not genuine uncertainty. These are calibration degeneration artifacts, not real market uncertainty estimates.

**Cleaned proxy lane** (exclude ankara/beijing): [0.768, 0.838, 0.865, 0.946, 1.006, 1.112]°C. Median = **0.906°C** vs 7d baseline 0.994°C → delta = **−8.9%**.

Within the range of daily variation (prior cycle was −4.4%), but the direction is consistent: three consecutive below-baseline readings (0.994 → 0.950 → 0.906°C). Not an alert by itself; worth watching over 3–5 more days for a trend signal.

**London d+1 bucket detail** (band's actual market horizon, pair_fav universe):

| Bucket | p_cal | p_mc |
|---|---|---|
| [26.5, 27.5) | 0.0002 | 0.0000 |
| [27.5, 28.5) | 0.2823 | 0.2120 |
| **[28.5, 29.5)** | **0.3801** | **0.5766** |
| [29.5, 30.5) | 0.3111 | 0.2062 |
| [30.5, 31.5) | 0.0204 | 0.0105 |

Implied sigma 0.865°C. Mode at [28.5, 29.5). Three-bucket spread is the cleanest dispersion signal available today from the band's universe.

---

## 3. DISPERSION GAUGE ⚠ ALERT PERSISTS — NEW DEGENERATION FINDING

**This is the load-bearing section. The band pause on 2026-07-03 was directly triggered by this gauge.**

### 3a. Headline metric

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Disp ratio 7d median | **0.817** (d+0 method, Jun 28–Jul 2) | ≥ 1.10 | 🔴 ALERT |
| Operative d+2 estimate | **~0.34** (last known) | ≥ 1.10 | 🔴 ALERT |

**By date** (all below threshold, no upward trend):

| Date | n pairs | n finite | Ratio | Impl sigma | Real dev |
|---|---|---|---|---|---|
| 2026-06-28 | 25 | 17 | 0.807 | 0.807°C | 1.000°C |
| 2026-06-29 | 28 | 19 | 0.663 | 0.794°C | 1.000°C |
| 2026-06-30 | 22 | 14 | 0.976 | 0.860°C | 0.917°C |
| 2026-07-01 | 26 | 17 | 0.866 | 0.807°C | 0.656°C |
| 2026-07-02 | 24 | 12 | 0.858 | 0.817°C | 1.000°C |
| **2026-07-03** | — | — | **unavailable** | — | — |
| **2026-07-04** | 10 | **0** | **degenerate** | 0.000°C | — |

### 3b. Critical new finding — dispersion gauge degeneration in POST_PEAK d+0 data

Today's 10 resolved POST_PEAK city-days produce **zero finite ratio pairs**:

- **8 city-days**: n_nonzero=1 — only the winner bucket carries p_cal>0, all others are 0. impl_width=0°C.
- **2 city-days** (San Francisco, Qingdao): n_nonzero=2, but mode bucket = winner bucket → realized_dev=0°C.

**Root cause**: The deployed isotonic plateau (grid 0.30–0.90 → p_cal=0.3801) assigns p_cal=0 to every bucket below the winning probability level. After deduplication to the latest snapshot per bucket, only 1 bucket survives with non-zero p_cal in 8 of 10 city-days. The probability distribution has collapsed from a ladder to a single point.

This is not a new defect — the prior cycle noted "the plateau eliminates discriminative power across a wide model-score range." What is new is that it renders the dispersion gauge completely unmeasurable for POST_PEAK d+0 data. The prior cycle's 84 finite pairs came from PRE_PEAK data (multiple temporal snapshots of the same bucket across the 2h–12h pre-close window, before the mode bucket dominates completely). That methodology is not available in today's POST_PEAK analysis.

### 3c. Edge state — plainly stated

**The edge is decaying. The band is correctly paused.**

The market's ladder-implied uncertainty (≤0.82°C at d+0, ~0.34 at d+2) is consistently below realized temperature deviation (1.0°C median). The band earns by selling overpriced probability wings; when implied < realized, the wings are not overpriced — the market is correctly priced and the band is a liquidity donor.

State_log 2026-07-03 19:25 records YES tape: "−$137.08 on $303 staked (−45%), every day negative" and directly cited this monitor: "calib-monitor dispersion gauge implied/realized σ = 0.34 (d+2)…0.82 (d+0), ALERT 6 consecutive days no recovery."

**Re-enable criterion** (state_log): disp_ratio ≥ 1.10 × 5 consecutive days.

This criterion requires at minimum 5 measured days with ratio above threshold. Current gauge degeneration (0 finite pairs from today's data) means we cannot even confirm whether the ratio is recovering. The gauge needs either: (a) PRE_PEAK methodology access (requires retaining historical PRE_PEAK rows per city-day) or (b) restored d+2 fire records with book prices.

---

## 4. ISOTONIC STALENESS ⚠ MATERIAL SHIFT — ALERT PERSISTS

Both configs unchanged from prior report.

| | Deployed | Candidate |
|---|---|---|
| Refit date | 2026-06-06 | 2026-06-09 |
| **Age today** | **28 days** | **25 days** |
| n_hist | 76,617 | 76,617 |
| n_live | 0 | 1,037 (unchanged) |
| near_identity_maxdev | 0.568 | 0.626 |

**Grid comparison:**

| grid | deployed | candidate | |delta| | flag |
|---|---|---|---|---|
| 0.0 | 0.0000 | 0.0175 | 0.018 | |
| 0.30–0.90 | **0.3801** | **0.3739** | 0.006 | plateau in both |
| 0.95 | 0.3822 | 0.3739 | 0.008 | |
| **1.00** | **0.6316** | **0.3739** | **0.2577** | **← MATERIAL** |

**Recommendation: DO NOT DEPLOY candidate.** The candidate extends the plateau to grid=1.0 (0.6316→0.3739), eliminating the model's only high-confidence signal. Deployed is better.

**Structural finding**: The isotonic plateau (grid 0.30–0.90 → 0.3801 in both configs) is the proximate cause of three observable defects this cycle:
1. Ankara/Beijing proxy-lane artifacts (all 9–10 buckets get equal p_cal → spurious 35–75°C sigma)
2. POST_PEAK d+0 dispersion gauge degeneration (n_nonzero=1 per city-day)
3. Inability to detect ratio recovery or worsening going forward

This will not self-correct without a live-refit that distinguishes among probabilities in the 0.30–0.90 range. The candidate does not solve this.

**Live-refit cron**: Candidate's n_live=1,037 unchanged from the Jun 9 refit (2 calendar days of data). No new live data has been incorporated in 25 days. ECE is passing (0.019) so there is no active calibration harm, but the 28-day-stale isotonic is the structural blocker for gauge resolution.

---

## 5. STATE TRANSITIONS

| Metric | Prior (2026-07-03) | This (2026-07-04) | Note |
|---|---|---|---|
| Brier7 | 0.053 | **0.053** | Unchanged — 7d window locked at Jun 28–Jul 2 |
| ECE7 | 0.019 | **0.019** | Unchanged |
| Rank-rho | 0.446 | **0.446** | Unchanged |
| Disp ratio7 (d+0) | 0.817 | **0.817** | Unchanged — Jul 3 unavailable; Jul 4 degenerate |
| Disp ratio (d+2) | ~0.34 | **~0.34** | No new d+2 data |
| Proxy sigma (cleaned) | 0.950°C | **0.906°C** | −4.6% vs yesterday; −8.9% vs 7d baseline (0.994°C) |
| Wuhan gap | YES (0 rows) | **RESOLVED** (88 rows, sigma=1.112°C) | |
| Bankroll (cash) | $79.57 combined | **$40.96** | Sprint ladder + cash split |
| BAND_YES_LIVE_MIN_DOUT | 2 | **9 (paused)** | Triggered by this monitor's S3 alert |
| BAND_NO_ENABLED | False | **False** | Halted since Jul 2 |
| Isotonic deployed age | 27d | **28d** | Stale, no refit |
| Isotonic candidate age | 24d | **25d** | Stale, no refit |
| Alerts | S3, S4 | **S3, S4** | Both persist |

**Proxy sigma 3-day trend** (allowlist, cleaned): 0.994°C (baseline) → 0.950°C (Jul 3) → 0.906°C (Jul 4). Consistent decline but within historical range. Warrants watch for the next 3 days.

---

## ALERTS (pre-registered only)

### 🔴 ALERT S3 PERSISTS — Dispersion ratio < 1.10 (7+ consecutive days)

**7d median ratio = 0.817 (d+0 bound); operative d+2 estimate = 0.340.**

All 5 measured dates (Jun 28 – Jul 2) below 1.10. Jul 3 data unavailable. Jul 4 data degenerate (isotonic calibration collapse). No upward trend is detectable in available data.

The band correctly responded: standalone YES paused (BAND_YES_LIVE_MIN_DOUT=9) on 2026-07-03. PAIR_FAV continues (last known: 3/3 co-fills +$2.31 locked). Re-enable condition: disp_ratio ≥ 1.10 × 5 consecutive days.

**New this cycle**: The dispersion gauge methodology is producing 0 finite ratio pairs from today's d+0 POST_PEAK data due to isotonic plateau collapse. The gauge cannot currently measure whether the ratio is recovering. Restoring measurement requires either: (1) isotonic refit that breaks the 0.30–0.90 plateau, or (2) access to d+2 fire records with book prices via VPS-side analysis.

### 🔴 ALERT S4 PERSISTS — Isotonic material shift, candidate worse; both configs stale 25–28 days

At grid=1.0: deployed=0.6316, candidate=0.3739, delta=−0.2577. Candidate is worse. DO NOT DEPLOY.

Both configs share identical n_hist=76,617. Live-refit cron has incorporated no new data since Jun 9 (25 days). The isotonic plateau (grid 0.30–0.90 → 0.3801) is the proximate cause of dispersion gauge degeneration identified this cycle. ECE passing (0.019) means no immediate calibration crisis, but restoring gauge resolution requires a plateau-breaking refit. Recommend verifying live-refit cron health on VPS.

---

*calib-agent@klaus | 2026-07-04T08:01Z | Branch: claude/find-lag-parameter-rFQ0N*
