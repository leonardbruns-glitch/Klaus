# Klaus Calibration & Dispersion Monitor Report
**Date:** 2026-06-23
**Run time:** 2026-06-23T08:10Z (approx)
**Snapshot freshness:** data-mirror snapshot_ts 2026-06-23T07:55:40Z — ~15 min old — OK
**System:** `klaus systemd: active` (bot uptime since 2026-06-23T06:12:09 UTC; 0 open positions)

---

## DATA ACCESS NOTE (transparency)

This run operates in a remote execution environment where `git fetch` times out (network-blocked). Large files (>~1MB) are inaccessible via GitHub API inline delivery. Specifically:

- **`data/shadow/stwa_ladder_book.jsonl` (2.5MB): INACCESSIBLE** — required for the dispersion gauge's implied sigma computation
- **`data/shadow/2026-06-[18..22]/stwa_pricer_eval_s50.jsonl` (1.3–1.9MB each): INACCESSIBLE inline** — analyzed via a subagent that derived outcomes from `running_max` (POST_PEAK phase) rather than CLOB/Gamma winner flags

Calibration metrics (Sections 1–2) are therefore computed via **proxy methodology** and are not directly comparable to prior state values. The dispersion gauge (Section 3 — the load-bearing metric) **cannot be updated today**; the ALERT carries forward from 2026-06-22 (4th consecutive day).

---

## ALERTS (pre-registered only)

> **⚠ DISPERSION_ALERT [CONTINUOUS, DAY 4]:** stwa_ladder_book.jsonl was inaccessible in today's run environment. Last confirmed ratio: **0.714** (2026-06-22, below threshold 1.10). Alert fires for **4th consecutive day** (series: 0.584 → 0.671 → 0.714 → **not computed**). Direction was improving ~+0.04/day but recovery was slow — ~10 more sessions needed at that pace to reach 1.10. The edge inversion on off-mode NO remains the operative assumption until a fresh compute confirms otherwise.

**No calibration alerts** — brier/ECE/rho all within threshold on proxy computation.

---

## Section 1 — SETTLED LANE (confirmed resolution labels)

**Data:** pricer_eval_s50 from 2026-06-18 through 2026-06-22 (5 days). **Methodology caveat:** outcomes derived from `running_max` (POST_PEAK phase: outcome=1 if `lo ≤ running_max < hi`), NOT from CLOB/Gamma winner flags per condition_id. This is a proxy. Results are directional only; not directly comparable to prior state (which used winner flags across the full market lifecycle).

| Metric | Value (proxy) | Prior (winner flags, 2026-06-22) | Alert threshold | Alert? |
|---|---|---|---|---|
| 7d Brier | **0.0266** | 0.0475 | >0.15 | No |
| 7d ECE | **0.0372** | 0.0255 | >0.05 | No |
| 7d Rank-rho (p_cal vs outcome) | **0.6118** | 0.4625 | <0.15 | No |

Brier and rho improved; ECE worsened vs prior (0.0255 → 0.0372). The ECE increase reflects the methodology shift: the proxy selects only POST_PEAK rows (where the model has nearly resolved the outcome), which exposes mid-range p_cal calibration gap more prominently. All three values remain comfortably within thresholds.

**Grade:** decision-grade (n=2,075 resolved rows across 5 days; ≥100 threshold cleared).

**Per-day counts (resolved/sampled):**

| Date | n_resolved (POST_PEAK) | n_sampled (total) |
|---|---|---|
| 2026-06-18 | 402 | 6,027 |
| 2026-06-19 | 357 | 6,687 |
| 2026-06-20 | 429 | 7,754 |
| 2026-06-21 | 466 | 8,438 |
| 2026-06-22 | 421 | 6,567 |
| **Total** | **2,075** | **35,473** |

No single day contributes >22% of resolved rows. No obvious outlier day. Resolution rate ~6% of sampled rows (expected: POST_PEAK is one phase of three; most sampled rows are PRE_PEAK evaluations for markets still live).

### Schema note
pricer_eval_s50 fields: `city`, `lo`, `hi`, `p_mc`, `p_gev`, `p_pa`, `p_ps`, `p_cal`, `running_max`, `t_close`, `phase`, `ts`. **No market price field** (`book_mid`/`market_price`/`mid` absent). Market divergence comparisons (proxy lane) must use `p_mc` as a model proxy, not true market mid.

---

## Section 2 — PROXY LANE (early warning, today's unresolved markets)

**Today's pricer rows:** 2,992 sampled rows (partial day — ~07:55 UTC snapshot).

**Note:** Market mid unavailable in pricer_eval_s50. Proxy metric is median |p_cal − p_mc| — measures how much the isotonic calibration step shifts the raw Monte Carlo estimate, NOT market divergence. Interpret as calibration-compression signal, not market-vs-model divergence.

| Phase | n | Median |p_cal − p_mc| |
|---|---|---|
| PRE_PEAK | 2,141 | 0.0054 |
| AT_PEAK | 133 | 0.0000 |
| POST_PEAK | 718 | 0.0000 |

**By days-to-close:**

| Horizon | n | Median |p_cal − p_mc| | 7d baseline | Spike? |
|---|---|---|---|---|
| days_out ≈ 0 | 1,051 | 0.0000 | 0.0000 | No |
| days_out ≈ 1 | 1,941 | 0.0062 | 0.0084 | −26% below baseline |
| days_out ≈ 2 | 0 | — | — | N/A |

Today's d+1 calibration compression (0.0062) is **below** the 7-day baseline (0.0084). This means the calibration step is making smaller adjustments than usual — p_cal is tracking p_mc more closely. This could indicate:
- Markets are less uncertain today (lower entropy → flatter isotonic adjustment)
- Seasonal or city-composition effect (different cities in today's sample)

**No spike detected.** No early-warning signal from proxy lane.

---

## Section 3 — DISPERSION GAUGE (the load-bearing edge variable)

> **This is the most critical section. The ALERT has been continuous for 4 sessions.**

### Blockers

**`data/shadow/stwa_ladder_book.jsonl` (2,650,762 bytes) is inaccessible** in this run environment (GitHub API 1MB inline limit; git fetch network-blocked). This file contains the per-city, per-bucket ask_yes price ladder needed for the implied sigma computation. **No substitute exists in the accessible files** — the pricer_eval files have no market price field, and the p_mc-based dispersion proxy is corrupted by sentinel `lo=-999` bucket values.

Therefore: **the dispersion ratio CANNOT be computed for 2026-06-23.**

### Carried-forward state

| Metric | Value | Source |
|---|---|---|
| Last confirmed disp_ratio7 | **0.714** | 2026-06-22 compute |
| Alert threshold | 1.10 | pre-registered |
| Alert status | **FIRES (DAY 4)** | ratio 0.714 < 1.10 |
| Last confirmed implied sigma | 0.928°C | ask_yes PRE_PEAK, 16 cities, 2026-06-22 |
| True sigma reference | 1.3°C | CLAUDE.md |
| True sigma data-derived | 0.961°C | std(resolved bucket - mode, 149 city-days, 2026-06-22) |

### 7-day trend (confirmed values)

| Session | Ratio | Δ |
|---|---|---|
| 2026-06-20 | 0.584 | — |
| 2026-06-21 | 0.671 | +0.087 |
| 2026-06-22 | 0.714 | +0.043 |
| **2026-06-23** | **not computed** | — |

Direction before today: recovering slowly. The prior alert analysis (2026-06-22 report) noted ~10 sessions needed at this pace to reach 1.10. Whether the ratio crossed 1.10 today cannot be determined without the ladder book.

### What this means for strategy

The band's edge depends on implied sigma > true sigma (market overestimates temperature dispersion → sell off-mode NO at a premium). With implied sigma at 0.928°C vs true 0.961°C (data-derived), this premium was **inverted** through at least 2026-06-22. The pivot to favNO-on-mode (rank 0, d+1) is directionally correct given the observed inversion.

### Structural recommendation (monitoring infrastructure)

The dispersion gauge is currently computable only from the full 2.5MB stwa_ladder_book.jsonl. The data-mirror service should write a **daily compressed sigma snapshot** (per-city median implied sigma, ~1KB) alongside the existing files. This would make the gauge computable in all run environments. Not a code change I can make — flagging for the user.

---

## Section 4 — ISOTONIC STALENESS

| Item | Deployed | Candidate |
|---|---|---|
| Fit date | 2026-06-06T22:27Z | 2026-06-09T09:30Z |
| Age today | **17 days** | **14 days** |
| n_live | 0 | 1,037 |
| live_calendar_days | 0 | 2 |
| Ceiling (p_cal at p_raw=1.0) | **0.6316** | **0.3739** |
| Candidate unchanged from prior report | — | **Yes (unchanged, 14 days stale)** |

### Grid-point comparison

| p_raw | Deployed | Candidate | Δ | Material? |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | +0.018 | No |
| 0.10 | 0.1340 | 0.1408 | +0.007 | No |
| 0.20 | 0.2663 | 0.2588 | −0.008 | No |
| 0.30–0.95 | 0.3801 (flat) | 0.3739 (flat) | −0.006 | No |
| **1.00** | **0.6316** | **0.3739** | **−0.258** | **YES** |

One material point, unchanged from prior report. The candidate would drop p_cal by **0.258** at p_raw=1.0 — the terminal confidence point. From yesterday's winner-flag data, rows at p_cal ≈ 0.63 (i.e., p_raw=1.0 terminal signal) had actual win rate ~99.1%. Deploying the candidate would set p_cal=0.374 for a bucket with 99% empirical win rate — severe underprice at exactly the moment the model is most certain.

**Recommendation (unchanged):** Do NOT deploy the candidate. The deployed curve's terminal ceiling (0.6316) correctly captures the final-confirmation signal. Both maps share the flat-top problem (all p_raw 0.30–0.95 collapsed to ~0.38), but the deployed is the lesser defect. A full refit with larger live-data weight targeting the flat-top specifically is the correct next step.

---

## Section 5 — STATE DIFF

| Metric | 2026-06-21 | 2026-06-22 | 2026-06-23 |
|---|---|---|---|
| brier7 | 0.0597 | 0.0475 (winner flags) | **0.0266** (running_max proxy) |
| ece7 | 0.031 | 0.0255 (winner flags) | **0.0372** (running_max proxy) |
| rho7 | 0.392 | 0.4625 (winner flags) | **0.6118** (running_max proxy) |
| disp_ratio7 | 0.671 | 0.714 | **not computed** (last known: 0.714) |
| Active alerts | DISP | DISP | **DISP (day 4)** |

Methodology changed today (git fetch timeout; large pricer files inaccessible via API). Values are not directly comparable across the methodology boundary. No calibration alerts under either methodology. Dispersion alert continuous.

---

## Infrastructure gap flagged

The stwa_ladder_book.jsonl at 2.5MB exceeds the GitHub API inline limit (1MB). In any network-constrained run environment, the dispersion gauge goes dark. A lightweight daily summary file (per-city sigma + ratio, <5KB) would resolve this permanently.
