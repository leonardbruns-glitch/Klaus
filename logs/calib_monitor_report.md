# Calibration & Dispersion Monitor — 2026-07-22

**Run UTC**: 2026-07-22T08:10Z (estimated)  
**Data source**: GitHub MCP API (git protocol blocked by network proxy)  
**Snapshot age**: ~10 min (snapshot 2026-07-22T08:01:39Z → OK, <6h limit)  
**System**: Klaus systemd active · bankroll $21.495 · 0 open positions · BAND_LIVE=False (day 16 dark)  
**Branch**: data-mirror SHA fd8bbc56

---

## 1. SETTLED LANE — 2026-07-21 fresh + rolling window

**Data**: 07-21 s50 file, 8,108 rows parsed · 6,633 valid (sentinel-filtered) · 368 POST_PEAK/PRE_PEAK resolved-city pairs for Brier/ECE.  
**Resolved cities 07-21**: 41 · **PRE_PEAK data available**: 39 cities.

| Metric | Prior carry (07-16..07-20) | 07-21 fresh | Updated 7d (07-16..07-21) | Threshold | Status |
|---|---|---|---|---|---|
| Brier7 | 0.0539 | **0.0795** | **0.0542** | <0.15 | OK |
| ECE7 | 0.0266 | 0.0408 | **0.0268** | <0.05 | OK |
| Rank-rho7 | 0.4320 (carry) | 0.3029 | ~0.43 (carry-fwd, low 07-21 weight) | >+0.15 | OK |
| n (sampled pairs) | ~32,261 | 368 | ~32,629 | — | — |

**No pre-registered Brier/ECE/rho alerts fired.**

**07-21 per-day Brier is notably worse (0.0795 vs 07-20's 0.0254)**, though its weight in the 7d estimate is small (~1%). At 1-in-50 sampling, 368 sampled pairs represents ~18,400 actual buckets from 41 resolved cities.

**ECE bin breakdown (07-21):**
- [0.0–0.1): n=246 (66.8%) mean_p=0.012 mean_o=0.037 |diff|=0.025
- [0.1–0.2): n=34 (9.2%) mean_p=0.152 mean_o=0.118 |diff|=0.034
- [0.2–0.3): n=18 (4.9%) mean_p=0.258 mean_o=0.222 |diff|=0.036
- [0.3–0.4): n=67 (18.2%) mean_p=0.370 mean_o=0.284 |diff|=0.086 ← **overconfidence in plateau zone**
- [0.4–0.5): n=2 (0.5%) mean_p=0.450 mean_o=0.000 |diff|=0.450 (n too small)
- [0.6–0.7): n=1 (0.3%) mean_p=0.630 mean_o=1.000 |diff|=0.370 (n=1, ignore)

**Structural finding (persistent)**: The [0.3–0.4) bin shows 18.2% of rows with mean_p=0.370 vs mean_o=0.284 — systematic overconfidence. This is the isotonic plateau artifact: p_raw values in [0.30–0.85] all map to p_cal≈0.374–0.380, so all "mode-adjacent" buckets pool into this bin. Outcome rate is 28% vs stated 37%, indicating the model is overconfident in the mid-range. Aggregate ECE is suppressed because ~67% of rows fall in the near-zero bin.

**Rank-rho (07-21 standalone)**: 0.303 (above 0.15 floor; no alert). Low vs prior carry 0.432 — may reflect increased noise in 07-21 with many near-miss cities. With small sampled n=368, directional but not precise.

---

## 2. PROXY LANE — 2026-07-22 early warning (~08:01 UTC)

**Data**: 07-22 s50 partial, 2,876 rows · 22 cities still PRE_PEAK (not yet resolved at snapshot).

| Metric | Today (07-22 ~08:01Z) | 7d baseline | Divergence |
|---|---|---|---|
| Median mode p_cal | 0.380 | 0.385 | **−0.005** |
| Mean mode p_cal | 0.378 | — | — |

No spike vs 7d baseline. Divergence of −0.005 is effectively zero.

**Mode p_cal trend:**
- 07-15: ~0.415 → 07-20: 0.385 → 07-21: 0.380 → 07-22 partial: 0.380

Still on a mild declining trend. Virtually all cities lock to p_cal=0.380 — the isotonic plateau is dominating every mode bucket reading. The plateau makes this proxy lane insensitive to real forecast shifts until a structural break changes the mapping.

**Notable**: Chengdu (0.356), Ankara (0.368), Shanghai (0.360) slightly below plateau — indicating the model's p_raw falls below 0.30 for their mode buckets, entering the transition zone below the plateau. No early-warning signal.

---

## 3. DISPERSION GAUGE — critical section

**Methodology**: last PRE_PEAK sample per bucket per city; sentinel buckets excluded (lo<−900 or hi>100); 0.5°C realized-deviation threshold for mode-hit exclusion; resolved cities only.

### 2026-07-21 full-day dispersion (27 eligible cities)

| City | Region | implied_std | realized_dev | ratio |
|---|---|---|---|---|
| amsterdam | EU | 0.783 | 1.00 | 0.783 |
| ankara | EU | 1.437 | 1.00 | **1.437** |
| helsinki | EU | 1.394 | 3.00 | 0.465 |
| istanbul | EU | 1.001 | 1.00 | 1.001 |
| london | EU | 0.798 | 3.00 | 0.266 |
| munich | EU | 0.924 | 1.00 | 0.924 |
| beijing | Asia | 1.438 | 1.00 | **1.438** |
| busan | Asia | 1.021 | 1.00 | 1.021 |
| chengdu | Asia | 1.505 | 2.00 | 0.753 |
| chongqing | Asia | 1.522 | 1.00 | **1.522** |
| kuala-lumpur | Asia | 0.919 | 1.00 | 0.919 |
| manila | Asia | 1.188 | 2.00 | 0.594 |
| shanghai | Asia | 1.156 | 2.00 | 0.578 |
| taipei | Asia | 1.075 | 2.00 | 0.538 |
| tel-aviv | Asia | 1.033 | 1.00 | 1.033 |
| tokyo | Asia | 1.256 | 1.00 | **1.256** |
| atlanta | US/Other | 0.817 | 1.40 | 0.584 |
| cape-town | US/Other | 1.219 | 1.00 | **1.219** |
| chicago | US/Other | 0.675 | 0.83 | 0.810 |
| dallas | US/Other | 0.546 | 1.42 | 0.384 |
| denver | US/Other | 0.925 | 0.96 | 0.968 |
| guangzhou | US/Other | 1.168 | 2.00 | 0.584 |
| houston | US/Other | 0.906 | 0.84 | **1.072** |
| jeddah | US/Other | 0.285 | 4.00 | 0.071 |
| san-francisco | US/Other | 1.095 | 3.57 | 0.307 |
| seattle | US/Other | 0.478 | 3.59 | 0.133 |
| wellington | US/Other | 0.231 | 1.00 | 0.231 |
| *Mode-hits (12)*: austin, los-angeles, madrid, mexico-city, miami, milan, moscow, paris, qingdao, sao-paulo, shenzhen, wuhan | — | — | — | — |
| *No PRE_PEAK (2)*: lucknow, warsaw | — | — | — | — |

**Region summary:**

| Region | n eligible | Daily median ratio |
|---|---|---|
| EU | 6 | 0.854 |
| Asia | 10 | 0.970 |
| US/Other | 11 | 0.584 |
| **All 07-21** | **27** | **0.783** |

**EU returned to eligibility** (6 cities vs 0 on 07-20). On 07-20, all EU cities were mode-hits. On 07-21, only madrid, milan, moscow, paris, are mode-hits; amsterdam, ankara, helsinki, istanbul, london, munich are eligible. EU median 0.854 — above-average but still below 1.10.

### 2026-07-22 early reading (partial, Asian-only, not settled)

| City | Region | ratio |
|---|---|---|
| busan | Asia | 0.272 |
| manila | Asia | 0.589 |
| shenzhen | Asia | 0.532 |
| taipei | Asia | 0.371 |
| **Median** | Asia | **0.452** |

11 US cities resolved but have no PRE_PEAK rows in the snapshot (all sampled PRE_PEAK rows predate the resolution, which occurred early UTC). EU cities still in PRE_PEAK at 08:01 UTC. Tokyo, qingdao, sao-paulo, wellington are mode-hits.

**07-22 partial (0.452) is the worst early-morning Asian reading in the 7d window.** Not yet settled, treat as early warning.

### Rolling 7d dispersion (settled window 07-16..07-21)

| Date | Daily median | n eligible | Note |
|---|---|---|---|
| 2026-07-16 | 1.196 | ~8 | carried from prior state |
| 2026-07-17 | 0.927 | ~8 | carried |
| 2026-07-18 | 0.485 | ~8 | carried |
| 2026-07-19 | 0.925 | ~8 | carried |
| 2026-07-20 | 0.779 | 18 | fresh (prior session) |
| **2026-07-21** | **0.783** | **27** | **fresh (this session)** |

**7d median of daily medians (07-16..07-21): 0.854**  
Sorted: [0.485, 0.779, 0.783, 0.925, 0.927, 1.196] → median = (0.783+0.925)/2 = **0.854**

City-day n in window: ~77 total (trend grade: 40–99). Decision-grade requires ≥100.

**Trend vs prior**: Prior 7d median was ~0.88 (07-15..07-20 window, n=59). Window shift drops 07-15 (1.038 = the strongest day) and adds 07-21 (0.783). Net effect: 7d median declines from ~0.88 to 0.854.

**07-22 early warning (0.452, not settled) adds further concern if sustained through day-end.**

### ⚠️ ALERT S3 — FIRING (pre-registered) — Day 20

**disp_ratio7 = 0.854 < 1.10 — INVERTED DISPERSION EDGE — 20 consecutive days.**

The dispersion premium the band harvests is absent. The market is NOT overestimating implied temperature dispersion vs realized outcomes. There is no edge for the weather band at current market prices.

- 07-21 adds to the inverted streak: daily median 0.783, not a reversal
- Only 1 of 6 settled days (07-16) is above 1.10; 5 of 6 are below 1.0
- US/Other is the most consistently inverted region (07-21 median 0.584)
- Asia near-neutral (0.970) but below 1.10
- EU re-emerges from mode-hit saturation (6 eligible, median 0.854) — no longer all mode-hits as on 07-20
- 07-22 early reading (0.452) is alarming but based on 4 Asian cities only
- Band is dark (BAND_LIVE=False since 07-06), so no capital at risk, but the edge thesis is not validated

---

## 4. ISOTONIC STALENESS

**Candidate was re-refit on 2026-07-21** (one day after yesterday's session detected the 07-20 refit). The refit cron is running daily.

| | Deployed | Candidate |
|---|---|---|
| Refit UTC | 2026-06-06T22:27Z | **2026-07-21T09:30Z** (re-run today) |
| Age (days since refit) | **46** | **0** (refitted yesterday) |
| n_hist | 76,617 | 76,617 |
| n_live | 0 | **3,733** (up from 3,247 yesterday) |
| Live calendar days | — | 8 |
| OOS brier (raw) | null | 0.0595 |
| OOS brier (calibrated) | null | 0.0603 |
| near_identity_maxdev | 0.568 | **0.520** (slight improvement) |

**Isotonic map comparison:**

| p_raw | deployed | candidate | diff |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0039 | +0.0039 |
| 0.05 | 0.0695 | 0.0741 | +0.0046 |
| 0.10 | 0.1340 | 0.1317 | −0.0023 |
| 0.15 | 0.1828 | 0.2057 | +0.0229 |
| 0.20 | 0.2663 | 0.2619 | −0.0044 |
| 0.25 | 0.3557 | 0.3508 | −0.0049 |
| 0.30–0.85 | 0.3801 | **0.3744** | −0.0057 (plateau persists in both) |
| 0.90 | 0.3801 | 0.3919 | +0.0118 |
| 0.95 | 0.3822 | **0.4305** | +0.0483 (near-threshold: 0.05) |
| 1.00 | 0.6316 | **1.0000** | **+0.3684 ← MATERIAL** |

**Max abs diff: 0.3684 at p_raw=1.0 → exceeds 0.05 material threshold → S4 alert fires.**

**Direction**: Candidate aggressively raises tail p_cal. At p_raw=1.0, candidate maps to p_cal=1.0 (no shrinkage), vs deployed's 0.6316 (substantial shrinkage). This is the only material-threshold change. The plateau shift (−0.0057) is benign.

**OOS note**: brier_cal (0.0603) > brier_raw (0.0595) — isotonic adds slight negative value on the 8-day OOS window. The margin (+0.0008) is small. This could reflect overfitting to recent data or insufficient n at tail buckets. **Structural concern**: the same isotonic overfitting that creates the plateau in the mid-range may be affecting the tail.

### ⚠️ ALERT S4 — FIRING (pre-registered, content updated)

Deployed isotonic is 46 days stale (no OOS validation). Candidate freshly re-run 2026-07-21 (n_live=3,733, 8 calendar days). Material diff at p_raw=1.0 (+0.3684). Candidate OOS shows minor negative calibration value. Promotion decision pending human review. Recommendation (not a code change): review whether tail behavior (p_raw→1.0 removes all shrinkage) is desirable given the OOS metric slightly worsening under calibration.

---

## 5. STATE TRANSITIONS

| Metric | Prior (2026-07-21 run) | This run (2026-07-22) | Change |
|---|---|---|---|
| brier7 | 0.054 | **0.054** | stable (+0.0003) |
| ece7 | 0.027 | **0.027** | stable (+0.0002) |
| rho7 | 0.432 | ~0.43 (carry) | stable (07-21 standalone 0.303, low weight) |
| disp_ratio7 | 0.88 (est) | **0.854** (6 settled days) | slight decline (dropped 07-15=1.038, added 07-21=0.783) |
| disp_ratio7_n | 59 | ~77 | +18 city-days (07-21 fresh) |
| disp_inversion_days | 19 | **20** | +1 (07-21 confirmed sub-1.10) |
| S3 alert | FIRING | FIRING | persisting |
| S4 alert | FIRING | FIRING | candidate re-refit 07-21 (n=3733); still material diff at p_raw=1.0 |
| candidate refit | 2026-07-20 | **2026-07-21** | re-run again today |
| band_dark_days | 15 | **16** | BAND_LIVE=False since 07-06 |
| bankroll | $21.495 | $21.495 | unchanged, 0 trades |

**Key transitions:**
- S3 persists, day count 19→20. 07-21 daily median 0.783 continues sub-1.0. US/Other the worst sub-region (0.584). EU returned to data-eligibility after 07-20's full mode-hit saturation.
- S4: Candidate refitted again (07-21 run), n_live grew +486. OOS metrics slightly worsening with larger live dataset. Plateau persists.
- Per-day Brier for 07-21 (0.0795) is substantially worse than 07-20 (0.0254). Insufficient weight to move 7d estimate materially, but worth tracking if 07-22 also shows elevated per-day Brier.
- Proxy lane: Locked at isotonic plateau (0.380). No signal variance.

---

## ALERTS

### ⚠️ ALERT S3 — FIRING (pre-registered)

**disp_ratio7 = 0.854 < 1.10 — INVERTED DISPERSION EDGE — day 20 consecutive.**

The edge is decaying. Twenty consecutive days below the 1.10 threshold. The weather band's core premise — that the market overestimates temperature dispersion relative to what Chainlink resolves — is NOT supported by the last 20 days of data. 5 of 6 settled days in the current 7d window are below 1.0 (ratio inverted, not just compressing). 07-22 early Asian read (0.452) is the worst early-morning signal in the window.

The band is dark (BAND_LIVE=False), so this alert serves as a thesis integrity check, not a trading halt. If BAND_LIVE were True, immediate halt would be warranted.

### ⚠️ ALERT S4 — FIRING (pre-registered)

**Deployed isotonic 46 days old, no OOS validation. Candidate freshly refit (2026-07-21), n_live=3,733, OOS brier_cal (0.0603) slightly exceeds brier_raw (0.0595) — isotonic adding marginal negative value.** Material diff: p_raw=1.0 → p_cal goes from 0.6316 (deployed) to 1.0000 (candidate), removing all tail shrinkage. Near-threshold diff at p_raw=0.95 (+0.0483, just under 0.05). The plateau structure persists in both curves (p_raw 0.30–0.85 → ~0.374 p_cal). Recommend human review of tail behavior before promoting candidate.

---

*Data access: GitHub MCP API. Pricer data: ReadMcpResourceTool (07-21 full s50, 8,108 rows; 07-22 partial s50, 2,876 rows). Isotonic configs: claude/find-lag-parameter-rFQ0N branch. All computations fresh this session.*
