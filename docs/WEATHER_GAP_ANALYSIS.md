# STWA Weather — Research Gap Analysis (alpha lost before the final probability)

> Built 2026-06-08 from a 5-lane code/data audit (stwa_engine.py, weather_arb.py, log-consumption
> grep, calibration/aggregation, data-richness) + an adversarial quantify pass against real
> resolution data. 42 raw gaps → deduped + verdicts below. Raw JSON: `docs/_gap_raw.json`.
> Authoritative behavioral source remains `strategy/stwa_engine.py` / `weather_arb.py`.
>
> Method note: quantify agents defaulted to "no signal" unless data cleared the n≥100 / Brier-delta bar.
> 7 gaps were tested with real data; the rest are high-confidence code findings not yet n-tested.

---

## A. CONFIRMED WITH DATA (quantified — act on these first)

### A1. ⭐ Humidity (dew) correction is wired to the WRONG variable — `category 4 (transformed incorrectly)`, Tier 1
- **Verdict:** signal **True**, monetizable **True**, **STRONG**.
- The dewpoint-departure coefficient is fit on (forecast dew − climatic dew) but applied in-engine
  against the cached **NWP air temperature**, not NWP dew. This roughly **doubles forecast-center MSE**
  on affected city-days. It is an active bug corrupting the center the whole NO path sizes off.
- **Action = pure alpha recovery, not new alpha.** Fix the cached quantity; re-measure CRPS.

### A2. ⭐ Center is NOT zero-mean — frozen-2024 `peak_bias` has drifted — `category 3/4`, Tier 1
- **Verdict:** signal **True**, monetizable **True**, **STRONG**, OOS CRPS **+5.2%** (pooled).
- `peak_bias` is frozen from a 2024 fit; the hourly `drift_bias` EMA does **not** correct the residual
  at the diurnal peak. **Directly refutes the CLAUDE.md claim that "the mean is handled well."**
- Action: re-fit / live-track peak_bias per city-month; this is the single biggest center-accuracy lever found.

### A3. ⭐ Forecast revision velocity (dμ/dt) predicts error & overconfidence — `category 2/5`, Tier 1→2
- **Verdict:** signal **True**, monetizable **True**, **STRONG**, monotone calibration.
- |μ_last − μ_first| across the intraday revision series (we store ~48 snapshots/city-day, up to 300)
  predicts both forecast error magnitude and model overconfidence — yet it **never widens the priced σ**.
  The revision history is used only as static training data, never as a live feature.
- Action: map revision velocity → a σ-inflation multiplier (more revision today ⇒ wider, less confident book).

### A4. Sky-cloud σ multiplier reaches only the SHADOW MC pricer, not live PA_SHRUNK — `category 5`, Tier 1
- **Verdict:** signal **True**, monetizable **False (moderate)**. Cloud-conditioned σ is real signal but
  it's plumbed into the shadow MC path; the live PA_SHRUNK distribution that actually sizes NO never sees it.
- Action: thread the cloud-regime σ multiplier into the live pricer (low-cost plumbing fix).

---

## B. REFUTED (do NOT build — data killed them)
- **kriging_pct** (spatial-propagation share): raw corr +0.39 **collapses** under controls → no usable signal.
- **Live cross-model dispersion vs |error|**: weak/none. *Important nuance:* naive same-cycle model spread
  is NOT predictive, but **revision velocity (A3) IS** — chase the time-derivative, not the static spread.
- **Marine/cirrus μ-adjustments**: no measurable lift; MAE gets *worse* with them, and they never reach a
  live decision anyway. Leave dead.

---

## C. HIGH-CONFIDENCE CODE GAPS (not yet n-tested — quantify before trading)

### Tier 1 — existing data/state/logs not monetized
- **`ensemble_sigma` is static climatology, not realized uncertainty** (cat 4). Engine prices with a fixed
  per-month σ≈1.0–1.1; the live daily ensemble σ is computed then discarded. (Note: B says *static spread*
  isn't predictive — the value is in A3's *revision* σ, so reshape this as "σ should be dynamic via revisions.")
- **Joint 2N Kalman velocity** (`x_hat_joint/v_hat_joint/pv_var_joint`) computed every tick, **only logged** —
  live pricer center excludes velocity entirely (also OLS `v_hat`). The inertial-OU trend term is unpriced.
- **Per-source feed-lead / `obs_receipt`** (the NMS edge): measured (~9–28 min lead) but **never gates or sizes**.
  ⚠ one auditor flagged it may be "provably not monetized" at our latency — quantify capture rate before building.
- **`n_models`** present but never gates entry (no-op confidence inflation).
- **`confidence` multiplier double-counts** phase/regime that are already separate gates (shrinks favorites toward 0.5 twice).
- **hot_bust_rates** continuous prob collapsed to a binary trigger, and only in a side path — not STWA sizing.
- **NEG_RISK_ARB disabled in the engine** per one auditor — the only calibration-free, guaranteed-profit edge
  left unmonetized. **Verify against live flags before acting (contradicts CLAUDE.md "always on").**

### Tier 2 — new transforms of existing data
- **Isotonic recal is ONE global map** across all 49 cities, all months, all lead-times, all phases (cat 4).
  Conditional calibration is lost — strongest structural calibration gap. Condition the map on at least city-cluster × phase.
- **Multi-pricer disagreement** (MC/GEV/PA vs PA-shrunk) computed every bucket, never used as a model-uncertainty gate.
- **PRICE_FLOOR 0.50 / NO band** are hard binary cutoffs discarding the continuous price-dependent edge curve.
- **Hour-conditioned β and σ-shrink tables exist but are gated OFF**; live uses fixed β=0.30 (dead code, cat 3).

---

## D. WELL-HANDLED (contrast — don't re-discover)
- Per-hour learned `drift_bias` IS applied live (but see A2 — insufficient at peak).
- Center anchoring structure is sound; the failure is the *bias term staleness*, not the architecture.

---

## E. ANSWERS TO THE 5 QUESTIONS
1. **Already modeled:** bias-corrected NWP center, per-hour drift_bias, marine/cirrus μ-adj, isotonic recal (global), running-max floor.
2. **Collected but UNUSED:** joint-Kalman velocity, feed-lead/obs_receipt, n_models, kriging_pct (dead), revision history as live feature, multi-pricer disagreement.
3. **Partially modeled:** regime (continuous→binary), sky/cloud (continuous→3-level, shadow-only), hot_bust (continuous→binary).
4. **Transformed INCORRECTLY:** ⭐ dew correction vs air-temp (A1), σ=static-climatology not dynamic, peak_bias stale (A2), confidence double-count.
5. **Present but never reaches a decision:** feed-lead, joint velocity, sky σ-multiplier (A4), revision velocity (A3), GEV/PA pricers.

---

## F. STRATEGY SHORTLIST (from confirmed gaps — backtest before deploy)
1. **Center-repair bundle (A1+A2):** fix dew wiring + live peak_bias tracking. Highest EV, lowest novelty — recovers MSE the NO path already trades on. Backtest = re-run pricer CRPS with corrected center.
2. **Revision-velocity σ-inflation (A3):** dμ/dt → dynamic σ; trade *against* the book when our σ is wider on high-revision days. The flagship candidate (revision dynamics + uncertainty + microstructure).
3. **Conditional isotonic (C/Tier2):** city-cluster × phase recal maps. Calibration alpha, needs n≥100 per cell.

**NEXT:** quantify #2 and #3 (one focused backtest each), then design the flagship around #2.
