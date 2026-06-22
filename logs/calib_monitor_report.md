# Klaus Calibration & Dispersion Monitor Report
**Date:** 2026-06-22
**Run time:** 2026-06-22T08:10Z
**Snapshot freshness:** data-mirror snapshot_ts 2026-06-22T07:57:24Z — 13 min old — OK
**System:** `klaus systemd: active` (bot uptime since 2026-06-21T16:38 UTC; 0 open positions)

---

## ALERTS (pre-registered only)

> **⚠ DISPERSION_ALERT [CONTINUOUS]:** PRE_PEAK ask_yes median implied sigma = **0.928°C** (ratio vs 1.3°C reference = **0.714**) — below threshold 1.10. Market is pricing narrower than true volatility. Alert fires for third consecutive day (prior: 0.671, delta +0.043 — slowly improving but still inverted). **No calibration alerts.**

---

## Section 1 — SETTLED LANE (confirmed resolution labels)

**Data:** pricer_eval_s50 from 2026-06-17 through 2026-06-21 (settled only; today excluded).

| Metric | Value | Prior (2026-06-21) | Δ | Alert? |
|---|---|---|---|---|
| 7d Brier | **0.0475** | 0.0597 | −0.012 ✓ | No (threshold >0.15) |
| 7d ECE | **0.0255** | 0.031 | −0.006 ✓ | No (threshold >0.05) |
| 7d Rank-rho (p_cal vs outcome) | **0.4625** | 0.392 | +0.071 ✓ | No (threshold <0.15) |

All calibration metrics improved. No alerts fire. Model retains genuine predictive power.

**Settled row counts:** 37,512 sampled rows total (6 days); 33,377 matched to resolved outcomes; 190 resolved city-days.

### ECE Bin Detail (10 equal-width bins)

| Bin | n | Mean p_cal | Mean outcome | |Δ| |
|---|---|---|---|---|
| [0.0, 0.1) | 26,179 | 0.0058 | 0.0129 | 0.0070 |
| [0.1, 0.2) | 1,506 | 0.1487 | 0.1129 | 0.0359 |
| [0.2, 0.3) | 933 | 0.2515 | 0.1629 | **0.0886** ← shoulder over-prediction |
| [0.3, 0.4) | 3,669 | 0.3693 | 0.3322 | 0.0371 |
| [0.4, 0.5) | 67 | 0.4643 | 0.7910 | 0.3268 |
| [0.5, 0.6) | 104 | 0.5649 | 0.9327 | 0.3677 |
| [0.6, 0.7) | 919 | 0.6292 | 0.9913 | 0.3621 |

**Structural ECE pattern — not a live miscalibration:**

Bins [0.4, 0.7) show apparent large gaps (mean_p ≈ 0.5–0.63, mean_outcome ≈ 0.79–0.99). This is structural, explained by the isotonic flat-top. The deployed isotonic maps all p_model > 0.30 to p_cal ≈ 0.38, capping there for the vast majority of evaluations. Only p_model = 1.0 breaks through to p_cal = 0.6316. Rows at p_cal ≈ 0.63 are exclusively at-resolution (ts ≈ t_close), when the mode bucket is effectively confirmed → win rate approaches 100%. The "bias" in those bins is the terminal signal artifact of the flat-top, not an exploitable live edge.

**[0.2, 0.3) shoulder over-prediction is real:** p_cal = 0.25 but actual win rate = 0.163. Shoulder buckets (off±1 from mode) are systematically overpriced by the model at ~8.5pp. Consistent with 2026-06-18 band_dispersion_test finding that shoulder calibration gap is near-zero in market prices but positive in model prices — model over-weights shoulder probability relative to the market.

### Brier by Region

| Region | n | Brier | Win rate |
|---|---|---|---|
| US | 18,830 | 0.0489 | 8.8% |
| EU | 7,343 | 0.0444 | 8.8% |
| Asia | 7,204 | 0.0468 | 8.9% |

Uniform across regions. Win rate ~8.8–8.9% is consistent with ~11 active buckets per city-day (1/11 ≈ 9.1%).

---

## Section 2 — PROXY LANE (early warning, today's unresolved markets)

**Today's pricer rows:** 2,185 sampled rows (partial day — run at 08:10 UTC).

**p_cal vs p_mc divergence by hours-to-close:**

| Horizon | n | Median |p_cal − p_mc| |
|---|---|---|
| 0–6h to close | 414 | 0.0000 |
| 6–12h to close | 518 | 0.0000 |
| 12–18h to close | 949 | 0.0104 |
| 18–24h to close | 304 | 0.0165 |

Longer-horizon rows show mild p_cal divergence from raw model output (0.017 at 18–24h horizon). No spike vs 7-day baseline. Proxy lane: **no early-warning signal.**

Note: book prices are not in pricer_eval_s50 — market mid comparison is done via the stwa_ladder_book.jsonl in Section 3.

---

## Section 3 — DISPERSION GAUGE (the load-bearing edge variable)

> **This is the most critical section. The alert has been continuous for 3+ sessions.**

### Methodology
Market ask_yes prices from `data/shadow/stwa_ladder_book.jsonl` (1,248 snapshots, 30 cities with latest-ts snapshots). Implied sigma = std of interior bucket midpoints weighted by normalized ask_yes. PRE_PEAK subset (n=16 cities) used as primary metric — methodologically clean, before intraday resolution compresses uncertainty.

### Spot check — 2026-06-22 PRE_PEAK markets (08:10 UTC)

| Metric | Value | Reference | Ratio |
|---|---|---|---|
| Market-implied sigma (ask_yes, all phases, n=30) | 0.761°C | — | — |
| Market-implied sigma (ask_yes, PRE_PEAK only, n=16) | **0.928°C** | 1.3°C (CLAUDE.md) | **0.714** |
| Data-derived true sigma (std of final_max − mode_center, n=149 settled city-days) | 0.961°C | — | — |

**PRE_PEAK cities (sorted by implied sigma):**

| City | sig_ask | Region |
|---|---|---|
| cape-town | 1.080°C | other |
| london | 1.051°C | EU |
| kuala-lumpur | 1.029°C | Asia |
| warsaw | 0.980°C | EU |
| jeddah | 0.967°C | other |
| moscow | 0.957°C | EU |
| paris | 0.928°C | EU |
| istanbul | 0.928°C | EU |
| beijing | 0.902°C | Asia |
| helsinki | 0.884°C | EU |
| manila | 0.872°C | Asia |
| ankara | 0.842°C | EU |
| munich | 0.809°C | EU |
| amsterdam | 0.761°C | EU |
| tel-aviv | 0.719°C | other |
| lucknow | 0.646°C | Asia |

No PRE_PEAK city exceeds the 1.3°C reference. The highest (cape-town, 1.08°C) is 17% below the reference. EU median ≈ 0.93°C.

### 7d Dispersion Ratio

**disp_ratio7 = 0.714** (ask_yes PRE_PEAK median / 1.3°C reference)

Below the 1.10 alert threshold → **ALERT FIRES.**

| Session | Ratio | Δ |
|---|---|---|
| 2026-06-20 | 0.584 | — |
| 2026-06-21 | 0.671 | +0.087 |
| **2026-06-22** | **0.714** | **+0.043** |

Direction: slowly improving, but rate of recovery (~0.04/day) would require ~10 more days to reach threshold. The dispersion edge remains inverted.

### Historical p_cal-based gauge (settled days, PRE_PEAK/AT_PEAK only)

| Metric | Value |
|---|---|
| City-days | 145 |
| Implied sigma (p_cal proxy), median | 0.645°C |
| By region — US | 0.724°C |
| By region — EU | 0.650°C |
| By region — Asia | 0.496°C |
| Trend early (17–19 Jun) | 0.606°C |
| Trend late (20–21 Jun) | 0.691°C |

p_cal-based sigma is lower than ask_yes-based (0.645 vs 0.928) because the isotonic flat-top makes the p_cal distribution appear artificially wide (all high-confidence buckets have same weight 0.38). Ask_yes is the reliable measure. The trend in p_cal proxy (0.606 → 0.691) is directionally consistent with ask_yes (improving slowly).

**What this means for strategy:**
The band's original premise was implied sigma > true sigma (market over-estimates dispersion → sell off-mode NO at a premium). With implied < true sigma, that edge is inverted on the NO-off-mode leg. Off-mode outcomes happen more than the market implies. The recent pivot to favNO-on-mode (rank 0, d+1) is directionally correct — mode is where the market over-prices probability at d+1 (2026-06-18 dispersion test, decision-grade). The edge reversal on OFF-mode NO is the reason YES-band performance was poor.

---

## Section 4 — ISOTONIC STALENESS

| Item | Deployed | Candidate |
|---|---|---|
| Fit date | 2026-06-06T22:27Z | 2026-06-09T09:30Z |
| Age today | **16 days** | 13 days |
| n_live | 0 | 1,037 |
| Ceiling (p_cal at p_raw=1.0) | **0.6316** | **0.3739** |
| Candidate unchanged from prior report | — | **Yes (13 days stale)** |

### Grid-point comparison

| p_raw | Deployed | Candidate | Δ | Material? |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 | No |
| 0.10 | 0.1340 | 0.1408 | +0.007 | No |
| 0.20 | 0.2663 | 0.2588 | −0.008 | No |
| 0.30–0.90 | 0.3801 (flat) | 0.3739 (flat) | −0.006 | No |
| 0.95 | 0.3822 | 0.3739 | −0.008 | No |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **YES (>0.05)** |

One material point: p_raw = 1.0, deployed ceiling 0.6316 vs candidate ceiling 0.3739, delta = −0.258.

**Direction:** Candidate moves p_cal DOWN at the terminal confidence point by 0.26. The ECE analysis confirms rows at p_cal ≈ 0.63 have actual win rate 99.1% (n=919 s50 rows). Deploying the candidate would produce p_cal = 0.37 for a bucket with 99% actual win rate — severe underestimate at exactly the moment the model has maximum certainty.

**Recommendation:** Do NOT deploy the candidate. Both maps share the flat-top problem at 0.38 (all p_raw 0.30–0.90 collapsed to same output), but the deployed correctly preserves the terminal signal (0.63). A new refit that addresses the flat-top (larger live dataset or revised calibration method) should be the target, not the current candidate.

---

## Section 5 — STATE DIFF

| Metric | 2026-06-20 | 2026-06-21 | 2026-06-22 |
|---|---|---|---|
| brier7 | — | 0.0597 | **0.0475** ↓ |
| ece7 | — | 0.031 | **0.0255** ↓ |
| rho7 | — | 0.392 | **0.4625** ↑ |
| disp_ratio7 | 0.584 | 0.671 | **0.714** ↑ |
| Active alerts | DISP | DISP | **DISP** |

Calibration improving on all three metrics. Dispersion ratio recovering slowly but remains in alert zone. No new alerts opened. No prior alerts closed.
