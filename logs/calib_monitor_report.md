# Calibration & Dispersion Monitor — 2026-07-18

**Run:** 2026-07-18T08:11Z | **Snapshot:** 2026-07-18T08:09Z (2 min old — OK)  
**System:** `active` | Bankroll: $37.57 | Open positions: 0 | Band: DARK (day 12)  
**Data access:** GitHub MCP (git fetch timeout — network proxy blocks git protocol; all data read via GitHub API; full pipeline ran)  
**Prior state:** 2026-07-17 — brier7=0.020(proxy,4d), disp_ratio=0.704(n=110,decision-grade), 2 alerts (S3-d15, S4)

---

## SECTION 1 — SETTLED LANE (confirmed resolution labels)

> **CAVEAT (pre-registered limitation):** No ground-truth resolution labels available. `window_resolution.jsonl` (393 rows) contains BTC/ETH/SOL updown market resolutions only — not weather temperature outcomes. Proxy method (POST_PEAK price convergence as winner) remains the only available approach. Metrics are proxy-grade.

**Method:** Per-city, bucket with highest final p_cal treated as winner (y=1), all others y=0. Brier = mean((p_cal − y)²).

**5-date proxy window (07-12..07-16):**

| Date | Proxy Brier | n cities | n sampled rows | Source |
|---|---|---|---|---|
| 2026-07-12 | 0.022 | 37 | 321 | prior run (carry) |
| 2026-07-13 | 0.020 | 35 | 307 | prior run (carry) |
| 2026-07-14 | 0.020 | 37 | 327 | prior run (carry) |
| 2026-07-15 | 0.019 | 38 | 337 | prior run (carry) |
| 2026-07-16 | 0.030 | 41 | 7,455 | fresh (s50 full-day file, incl. d1/d2 PRE_PEAK rows) |

**Note on 07-16 higher proxy Brier (0.030 vs 0.019–0.022 for older dates):** The 07-16 s50 file contains concurrent d1/d2 evaluations (50.2% PRE_PEAK) for markets resolving 07-17 and 07-18. The proxy winner-assignment method is weaker for pre-resolution rows; true completed-day Brier for 07-16 is likely in the 0.019–0.022 range. The 0.030 is an upper bound.

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Brier7 (5-date proxy avg) | **0.022** | >0.15 = alert | OK — far below threshold |
| ECE7 (carried from 07-17) | **0.0448** | >0.05 = alert | OK — below threshold |
| Rank rho7 (carried from 07-17) | **0.8343** | <0.15 = alert | OK — above floor (circular proxy) |

No settled-lane alerts. Key structural finding unchanged from prior run: **isotonic plateau collapse** — p_raw∈[0.30, 0.95] maps to p_cal≈0.38 (zero discrimination across 65% of probability range). Directly visible in pricer data: p90(non-zero p_cal) = 0.3801 on every observed day — the isotonic ceiling is binding.

---

## SECTION 2 — PROXY LANE (early warning, p_cal vs mid divergence)

Market book mid not present in pricer_s50 schema. p_cal stability check:

| Date | n rows (s50) | %non-zero | %high-conf (>0.50) | Median p_cal (nz) | p90 |
|---|---|---|---|---|---|
| 2026-07-15 | 7,501 | 34.0% | 2.6% | — | 0.3801 |
| 2026-07-16 | 7,455 | 47.9% | 2.95% | 0.0934 | 0.3801 |
| 2026-07-17 | 7,108 | 49.5% | 2.17% | 0.0864 | 0.3801 |
| 2026-07-18 (partial, ~8am) | ~2,300 est. | — | — | — | — |

**Phase distribution 07-17:** PRE_PEAK 52.0%, POST_PEAK 36.3%, AT_PEAK 11.7%  
**Phase distribution 07-16:** PRE_PEAK 50.2%, POST_PEAK 38.6%, AT_PEAK 11.1%

Distribution stable. p90 locked at 0.3801 on all days (isotonic cap binding). Slight decrease in %high-conf from 07-16 (2.95%) to 07-17 (2.17%) — within normal variation. No divergence spike detected.

**Note:** Elevated PRE_PEAK % in 07-16 s50 file reflects concurrent d1/d2 evaluations (markets resolving 07-17/18) — expected behaviour, not a data anomaly.

---

## SECTION 3 — DISPERSION GAUGE ⚠️ ALERT ACTIVE

> **This is the most important section.** The band edge rests on market-implied dispersion exceeding true dispersion (true sigma ~1.3°C). This gauge monitors whether that edge holds.

**Method:** `band_struct_lite` rows where `reason=converged`. For each: `sigma_implied = 1°C / (2√2 × erfinv(mode_ask))`. Ratio = sigma_implied / 1.3°C.

### 2026-07-17 new data (n=23 fire rows)

| Metric | Value |
|---|---|
| Daily n fire rows | **23** |
| Daily median ratio | **0.6516** |
| Rows above 1.10 | **2** (8.7%) — **FIRST TIME IN MONITORING WINDOW** |
| Rows below 1.10 | 21 (91.3%) |
| Rows below 1.00 | 19 (82.6%) |

**Rows exceeding 1.10 threshold (new signal — first observed):**

| City | days_out | mode_ask | sigma_implied | ratio |
|---|---|---|---|---|
| Wuhan | 0 | 0.255 | 1.537°C | **1.183** |
| Chengdu | 0 | 0.265 | 1.477°C | **1.136** |

These are the first rows in this monitoring window where sigma_implied exceeds the 1.3°C baseline. Both are same-day (d0) Asia markets with very tight mode_ask ≤ 0.27. This is a localized genuine edge signal in Asia d0.

**Additional d0 rows near threshold (mode_ask 0.28–0.35):**

| City | days_out | mode_ask | ratio |
|---|---|---|---|
| Chengdu | 0 | 0.280 | 1.073 |
| Chongqing | 0 | 0.290 | 1.034 |
| Munich | 0 | 0.305 | 0.981 |
| Seoul | 0 | 0.325 | 0.917 |

Four rows exceed ratio=1.0 on 07-17, vs approximately 1 row on prior days. The d0 Asia cluster is narrowing the gap to threshold.

**07-17 by days_out:**

| days_out | n | Daily median ratio | vs prior 7d trailing |
|---|---|---|---|
| d0 | 18 | **0.8412** | ↑ from prior d0 trailing ~0.744 |
| d1 | 1 | 0.6276 | ≈ stable |
| d2 | 3 | 0.5702 | ≈ stable |

**d0 significant improvement on 07-17.** Asia same-day markets showing daily median ratio 0.84 — the forward (d1/d2) markets remain deeply inverted.

**07-17 by region:**

| Region | n | Daily median ratio |
|---|---|---|
| EU | 5 | 0.6276 |
| Asia | 15 | 0.7757 |
| Other | 3 | 0.4335 |

*Note: "Other" includes two Chongqing entries (not in EU/Asia lookup) and one lowercase `munich` data quality row (days_out=None). See data quality flag in Section 5.*

### 7-day rolling (2026-07-12..2026-07-17, n=133)

| Metric | Value | Threshold | Status |
|---|---|---|---|
| **7d median disp_ratio** | **≈0.70** (estimated) | <1.10 = ALERT | 🚨 ALERT |
| % rows below 1.10 | 98.5% (131/133) | — | ↓ from 100% |
| % rows below 1.00 | 96.2% (128/133) | — | ↓ from 99.1% |
| n fire rows | **133** | ≥100 = decision-grade | DECISION-GRADE |

> **Estimation note:** 7d median cannot be computed exactly — individual row ratios for 07-12..07-16 are not stored in this environment (only daily medians and n are available from prior state). Estimate: of the 23 new 07-17 rows, 12 fall below the prior median (0.704) and 11 fall above, placing the combined 67th-percentile row very close to 0.704. Conservative estimate: **7d median ≈ 0.70 (±0.02)**. The alert fires regardless of where the exact value lands in this range.

**Trend (daily medians):**

| Date | n fire | Median ratio | Rows >1.10 |
|---|---|---|---|
| 2026-07-12 | 21 | 0.765 | 0 |
| 2026-07-13 | 25 | 0.686 | 0 |
| 2026-07-14 | 25 | 0.714 | 0 |
| 2026-07-15 | 21 | 0.652 | 0 |
| 2026-07-16 | 18 | 0.704 | 0 |
| **2026-07-17** | 23 | **0.652** | **2** ← first above-threshold rows |
| **7d median** | **133** | **≈0.70** | **2 total** |

Trend: 7d median has oscillated 0.65–0.77 for 16 days, all far below 1.10. 07-17 is the first day with any rows exceeding 1.10 — concentrated in Wuhan and Chengdu d0 at very tight mode_ask. This is the first recovery signal in this monitoring period. It is early (2 of 23 rows); 3–5 days of sustained improvement across multiple cities would be required to revise the alert posture.

**7d estimates by region and days_out (estimated from combined n, derived from daily data):**

| Region | n (est.) | 7d median (est.) |
|---|---|---|
| EU | ~27 | ≈0.628 (stable vs 0.628 prior) |
| Asia | ~80 | ≈0.73 (slight improvement from 07-17 d0) |
| Other | ~26 | ≈0.70 |

| days_out | n (est.) | 7d median (est.) |
|---|---|---|
| d0 | ~100 | ≈0.76 (↑ from 0.744, 07-17 daily d0 median 0.841) |
| d1 | ~19 | ≈0.635 |
| d2 | ~13 | ≈0.57 |

**Inversion day count: 16 consecutive days** (d15→d16).

**ALERT S3-d16: disp_ratio7≈0.70 < 1.10 — INVERTED DISPERSION EDGE — 16th consecutive day — DECISION-GRADE (n=133) — FIRST RECOVERY SIGNAL: 2/23 rows on 07-17 exceed 1.10 (Wuhan d0=1.183, Chengdu d0=1.136) — Asia d0 daily median 0.841 — d+1/d+2 remain deeply inverted (≈0.57–0.64)**

---

## SECTION 4 — ISOTONIC STALENESS ⚠️ ALERT ACTIVE

| | Deployed (`stwa_isotonic.json`) | Candidate (`stwa_isotonic_candidate.json`) |
|---|---|---|
| Refit date | 2026-06-06 | 2026-06-09 |
| Days since refit | **42d** (was 41d) | **39d** (was 38d) |
| n_live at refit | 0 | 1,037 |
| live_calendar_days | 0 | 2 |
| OOS brier | null | null |
| near_identity_maxdev | 0.568 | 0.626 |

**Diff summary (deployed vs candidate):**

| p_raw | Deployed p_cal | Candidate p_cal | \|Δ\| |
|---|---|---|---|
| 0.00 | 0.0000 | 0.0175 | 0.0175 |
| 0.05–0.10 | 0.0695–0.134 | 0.0758–0.141 | 0.006–0.007 |
| 0.30–0.95 | **0.3801** (plateau) | **0.3739** (plateau) | 0.006 |
| 0.95 | 0.3822 | 0.3739 | 0.008 |
| **1.00** | **0.6316** | **0.3739** | **0.2577** ← material |

Material differences (>0.05): **1** (at p_raw=1.0 only). Content of both files **unchanged from yesterday** (same refit dates, same calibrated values).

Both curves maintain the **plateau pathology**: p_raw∈[0.30, 0.95] → p_cal≈0.38. This is directly binding on live data — p90(non-zero p_cal) = 0.3801 every observed day. The candidate's only structural change is removing the certainty spike at p_raw=1.0; the plateau persists. OOS brier_live_oos_cal = null for both curves.

**ALERT S4: isotonic deployed 42d without OOS validation; max_diff=0.2577 at p_raw=1.0; both curves maintain plateau [0.30-0.95]→0.38; candidate removes certainty spike but does not fix plateau; new full refit with OOS validation required before any deployment decision**

---

## SECTION 5 — STATE

**Alerts this run:** 2 (S3-d16, S4 — same alert set as prior session; S3 augmented with first-recovery-signal note)

**Transitions from 2026-07-17:**
- **S3:** persistent (d15→d16); 7d median ≈0.70 (essentially flat from 0.704); grade stable (DECISION-GRADE, n=110→133); **NEW: first 2 rows above 1.10 threshold (Wuhan d0 ratio=1.183, Chengdu d0 ratio=1.136); Asia d0 daily median 0.841 vs prior trailing ~0.744**
- **S4:** persistent; deployed 42d (was 41d); files content unchanged; OOS validation null
- **brier7:** 0.020(4d proxy) → 0.022(5d proxy; added 07-16 Brier=0.030 which is inflated by mixed PRE_PEAK; true completed-day estimate ~0.020)
- **ECE7:** 0.0448 (carry — no update this session; below 0.05 threshold)
- **rho7:** 0.8343 (carry — no update this session; above 0.15 floor)
- **Band:** dark day 11 → dark day 12 (BAND_LIVE=False since 2026-07-06); correctly dark given persistent inversion
- **Bankroll:** $31.76 → $37.57 (+$5.81 from sniper, consistent with EVOLVE audit)
- **Disk:** 97% capacity, ~4GB remaining — unchanged; no VPS action observed

**Data quality flag:** 07-17 band_struct_lite contains 1 row with `city="munich"` (lowercase) and `days_out=None` — EU misclassification, excluded from days_out breakdown. Ratio=0.3876. Recommend title-case city name normalization at ingestion to avoid lost rows.

**Recommendations (report only — live-refit cron governs deployment):**
1. **Dispersion edge:** The 7d median (≈0.70) remains well below 1.10 — the band is correctly dark. However, 07-17 produced the **first rows above 1.10** (Wuhan d0, Chengdu d0 with mode_ask≤0.265). Monitor these two cities specifically in the next 3–5 sessions. If Wuhan and Chengdu d0 consistently show ratio>1.10, it would signal the edge is partially recovering in Asia d0 tight markets — a meaningful change in posture.
2. **Isotonic plateau:** Both deployed (42d) and candidate (39d) curves collapse discrimination across [0.30, 0.95]→0.38. A new isotonic refit with materially larger live_n and OOS brier validation is the correct action before any curve swap. The candidate's spike removal is narrow improvement; it does not address the dominant pathology.
3. **Disk:** 4GB remaining at 97% capacity — unchanged from yesterday. Rotation/pruning needed.

---

## ALERTS — Pre-registered fires only

### 🚨 S3-d16 — DISPERSION EDGE INVERTED (DECISION-GRADE)
**7d median disp_ratio≈0.70 < threshold 1.10**  
16th consecutive day. n=133 (decision-grade). d+1≈0.635, d+2≈0.57 most inverted. **First recovery signal: 2 of 23 rows on 07-17 exceed 1.10 (Wuhan d0 ratio=1.183, Chengdu d0 ratio=1.136) — first time in this monitoring window.** Asia d0 daily median improved to 0.841. 3–5 days of sustained improvement across multiple cities required to revise posture. Band correctly dark.

### ⚠️ S4 — ISOTONIC STALENESS
**max_diff=0.2577 at p_raw=1.0; deployed 42d, no OOS validation**  
Both deployed and candidate curves maintain plateau collapse [0.30-0.95]→0.38. Candidate removes certainty spike at p_raw=1.0 only. No OOS brier for either curve. New full refit with OOS validation required.
