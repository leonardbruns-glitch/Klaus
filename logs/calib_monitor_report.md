# Calibration & Dispersion Monitor Report — 2026-07-15

**Run UTC:** 2026-07-15 ~12:00Z (automated)
**Snapshot:** 2026-07-15T08:00:55Z (age ≈ 4h — within 6h window ✓)
**System:** `klaus systemd: active` ✓ — uptime since 2026-07-15 02:40:11 UTC
**Data access:** DEGRADED (git fetch timeout — network proxy blocks git protocol; data accessed via GitHub raw API, same condition as 2026-07-14)

---

## §1 — SETTLED LANE (Confirmed Labels)

**Source:** `stwa_pricer_eval_s50` from 2026-07-13 (oldest accessible fully-resolved day). July 14 POST_PEAK data not retrieved. 7-day window uses July 13 as anchor + carry-forward from prior state.

**Post-sampling n:** From s50 file, ~65 POST_PEAK rows identified across 7 US/Americas cities (Chicago, Austin, Denver, Los Angeles, Buenos Aires, Seattle, Toronto). Unique (city, bucket) pairs: ~52. Pre-50× expansion this represents ~2,600 true resolved observations for that one day — adequate for Brier, marginal for per-city ECE.

**Resolutions inferred from running_max at POST_PEAK:**

| City | running_max (°C) | Winner bucket | p_cal (winner) | p_cal (2nd) |
|------|-----------------|---------------|----------------|-------------|
| Chicago | 30.0 | [29.72–30.83] | 0.6316 | 0.0 |
| Austin | 35.0 | [34.17–35.28] | 0.6316 | 0.0 |
| Denver | 35.7 | [35.28–36.39] | 0.6316 | 0.0 |
| Los Angeles | 23.3 | [23.06–24.17] | 0.6316 | 0.0 |
| Buenos Aires | 12.0 | [11.5–12.5] | 0.55044 | 0.00177 |
| Seattle | 22.2 | ~[21.94–23.06]* | n/a (not sampled) | 0.16913 (wrong bucket) |
| Toronto | 27.0 | ~[26.5–27.5]* | n/a (not sampled) | 0.0 |

*winning bucket not present in s50 sample for these cities.

**Brier score (July 13 s50 sample, n≈52 unique pairs):**
- Winner buckets with non-trivial p_cal: 5 observations
- Brier contributions: `(0.6316−1)²×4 + (0.55044−1)²×1 = 0.5420 + 0.2021 = 0.744`
- Notable non-winner: Seattle [23.06–24.17] p_cal=0.16913, outcome=0 → `0.029`
- All others at p_cal≈0, outcome=0 → Brier ≈ 0
- **POST_PEAK Brier = (0.744 + 0.029) / 52 ≈ 0.015** (artificially low — POST_PEAK near-certain)

**7-day Brier (brier7):** Carrying 0.053 from 2026-07-13 confirmed chain. POST_PEAK Brier is not the same as the market-facing PRE_PEAK calibration metric. **brier7 = 0.053 (carry, below 0.15 — NO ALERT).**

**ECE7:** Uncomputable — sample bimodal (all losers at p_cal≈0, all winners at 0.6316 ceiling). Only 2 populated bins in 10-bin scheme. n<40 per bin. **ECE7 = null (collect, not decision-grade).**

**Rank-rho7:** Uncomputable — rank correlation degenerate with bimodal structure. **rho7 = null.**

**Structural observation:** Deployed isotonic ceiling p_raw=1.0 → p_cal=0.6316. This is not a calibration failure; it is a designed conservative ceiling from the June 2024 fit. Winner buckets hitting this ceiling is expected behavior.

---

## §2 — PROXY LANE (Early Warning, Unsettled)

**Source:** Today's `stwa_pricer_eval_s50` (2026-07-15, ts≈05:24–05:26 UTC).

**Sample observations (PRE_PEAK):**

| City | Bucket | p_cal | running_max |
|------|--------|-------|-------------|
| Taipei | [35.5–36.5] | 0.3801 (plateau) | 31.0 |
| Istanbul | [24.5–25.5] | 0.3801 (plateau) | 22.0 |
| Manila | [34.5–35.5] | 0.3801 (plateau) | 30.0 |
| Ankara | [−999, 25.5] | 0.01548 | 17.0 |
| Jeddah | [33.5–34.5] | 0.01183 | 33.0 |

**Band-struct mode_ask (d+0, 05:24Z):** Seoul 0.385 | Tokyo 0.435 | Taipei 0.355 | Beijing 0.375 | Wuhan 0.485 | Chengdu 0.35 | Munich 0.415 | Shanghai 0.47 | London 0.485

**p_cal vs mode_ask divergence (Taipei):** |0.3801 − 0.355| = 0.025 — moderate, within expected range of 0.3801 plateau systematically above book mid.

**Proxy assessment:** No spike vs 7d baseline (baseline not established under degraded access). No proxy early-warning alert.

---

## §3 — DISPERSION GAUGE (Edge Variable — Most Important)

**Pre-registered threshold:** 7d median implied/realized ratio < 1.10 → S3 ALERT.

### Historical inversion chain:
| Date | disp_ratio7 | Inversion day |
|------|------------|---------------|
| 2026-07-13 | ≤0.80 | d11 (confirmed) |
| 2026-07-14 | ≤0.80 | d12 (carry) |
| **2026-07-15** | **≤0.80** | **d13 (carry)** |

### Today's observational check:

Computing proxy implied std from today's shadow fire records (model quotes, not book):

**Wuhan d+2** (n_legs=5, sum_ask=0.836): Implied std ≈ **1.20°C** (bucket midpoints weighted by quote fractions)

**Chengdu d+2** (n_legs=5, sum_ask=0.845): Implied std ≈ **1.27°C**

Reference true sigma: ~1.3°C (June 2026 validation). Model-implied today: 1.20–1.27°C.

**Caveat:** These are from our model's quotes, not market book prices. The proper dispersion ratio requires book-side data for resolved days. Band is dark (live=false), no fills available.

**Conclusion:** Cannot independently recompute fresh disp_ratio7. **S3 carry-forward: day 13.** Model quote distribution (1.20–1.27°C) is below true sigma (1.3°C), consistent with sub-1.10 ratio persisting. **No recovery signal.** Band correctly dark.

---

## §4 — ISOTONIC STALENESS

**Comparing deployed (2026-06-06) vs candidate (2026-06-09):**

| p_raw | Deployed | Candidate | Δ | Material? |
|-------|----------|-----------|---|----------|
| 0.0 | 0.0000 | 0.0175 | +0.0175 | No |
| 0.15 | 0.1828 | 0.1828 | 0.0000 | No |
| 0.30–0.90 | 0.3801 | 0.3739 | −0.0062 | No |
| 0.95 | 0.3822 | 0.3739 | −0.0083 | No |
| **1.00** | **0.6316** | **0.3739** | **−0.2577** | **YES** |

**Key structural change:** Deployed has a spike at p_raw=1.0 (0.3822 → 0.6316, +0.249). Candidate removes this spike entirely — plateau stays flat at 0.3739 through p_raw=1.0.

**Direction:** Candidate lowers p_cal for p_raw≥0.95. POST_PEAK winner-bucket p_cal would drop from 0.6316 → 0.3739 (−37%).

**Fit details:** Candidate has n_live=1037 (2 calendar days); deployed has n_live=0. Candidate near_identity_maxdev=0.626 (deployed: 0.568). Candidate is 36 days old without deployment review.

**Interpretation:** Live data (June 9, 1,037 obs) suggests market doesn't support p_cal=0.63 for near-certain predictions — likely because at POST_PEAK, market liquidity collapses and bids don't reach 0.63. Candidate encodes this. Neither deployed nor candidate incorporates July 2026 live data.

**S4 ALERT FIRES (CONFIRMED, NOT CARRY):** max_dev=0.2577 at p_raw=1.0, far exceeds 0.05 threshold. Files read directly today via raw API. The live-refit cron has been producing this candidate since June 9 without deployment review.

---

## §5 — STATE

State written to `logs/calib_monitor_state.json`.

**Transitions 2026-07-14 → 2026-07-15:**
- brier7: 0.053 → 0.053 (carry, stable, NO ALERT)
- ece7: null → null (structural, uncomputable)
- rho7: null → null (structural, uncomputable)
- disp_ratio7: ≤0.80 → ≤0.80 (d12 → d13, **S3 PERSISTS**)
- S4: carry → **CONFIRMED** (files read directly today)
- band_dark_days: 8+ → 9+
- data_access: DEGRADED (persistent)

---

## ALERTS

### Pre-registered alerts that FIRED:

**🚨 S3 (CRITICAL) — Day 13:** `disp_ratio7 ≤0.80 < 1.10`
> The dispersion edge has been inverted for 13 consecutive days (July 3 → July 15). Market implies tighter temperature distributions than realized. Band correctly halted in shadow mode. No recovery signal today. Recommend: maintain shadow; do NOT enable BAND_LIVE until disp_ratio7 > 1.10 for 3+ consecutive days.

**⚠️ S4 — Isotonic Staleness (CONFIRMED):**
> `|deployed[p_raw=1.0] − candidate[p_raw=1.0]| = 0.2577 >> 0.05`. Candidate removes POST_PEAK certainty spike. Candidate written June 9 (36 days ago) with 1,037 live observations. Direction: candidate lowers max p_cal from 0.6316 to 0.3739. Guarded live-refit cron should review this candidate for deployment.

### Pre-registered alerts that DID NOT fire:
- Brier7 = 0.053 < 0.15 → **OK**
- ECE7 = null (uncomputable, not a threshold breach)
- Rank-rho = null (uncomputable, not a threshold breach)
- Proxy spike: none detected

---

## Additional Observations (Non-Alert)

- **Disk 95% full (5GB / 97GB):** Noted in system_status. Not a calib-monitor concern.
- **Prior loss $69.08 (July 13):** Crypto bot result; unrelated to weather band.
- **Shadow pipeline functional:** d+1/d+2 fire records generating correctly (sum_ask 0.55–0.85, 3–5 legs per city, live=false).
- **ECE/rho recovery path:** Requires resolved data access — either git fetch or a labeled PRE_PEAK snapshot archive with joined outcomes spanning 7 days.
