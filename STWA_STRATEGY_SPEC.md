# STWA — Validated Strategy Specification
**Spatiotemporal Weather Arbitrage on Polymarket daily-high-temperature markets**
Status: LIVE (arb path), real capital. Spec version 1.0 — 2026-05-31.

> This is the evidence-grounded counterpart to speculative "skill" specs. Every
> claim here is tied to a measurement on real data. Where an idea is **unproven**
> or **falsified**, it is marked as such — not dressed up. If this spec ever
> contradicts the live data, **the data wins** and this file gets updated.

---

## 1. What the strategy is
Trades Polymarket **daily-maximum-temperature** markets across 51 cities. A market
resolves on the **daily max** — the supremum of the day's temperature path — rounded
to a whole degree from the **official hourly METAR/SPECI** observation (AWC/NWS), NOT
sub-hourly ASOS spikes. Engine: a 51-city joint Kalman filter over 2D Langevin paths
produces a forecast distribution for each city's daily max; bucket win-probabilities
are priced (`PA_SHRUNK`), isotonically recalibrated, and sized by fractional Kelly.

**The keystone math fact:** the daily max is decided in a narrow window around the
diurnal peak, not uniformly across the day. Mis-handling this (maxing over the whole
remaining horizon) was the root cause of historical YES overconfidence.

---

## 2. The validated edges — what we actually exploit

### 2a. NEG_RISK_ARB  ✅ structurally sound, calibration-independent
**Trigger:** within a city's mutually-exclusive bucket set, when the YES asks spanning
the buckets sum to **< 0.85** (< 0.80 if ≥4 legs), buy the spanning set for a
guaranteed sub-$1 payoff of $1.
**Why it's real:** the payoff is a structural identity — exactly one bucket resolves
YES → $1. It does **not** depend on our model being calibrated. This is the only
edge that is sound *today*.
**Constraint:** capacity-limited — needs Σask<1 windows AND fillable equal-share depth.
Sizing must raise global share count `k` so every leg fills; abort if total > 1.5×budget.

### 2b. LOCKOUT-NO  ✅ validated (94.6% WR, n=501) — NOT YET LIVE
**Trigger:** once `running_max` (official, AWC/NWS only) physically passes a bucket's
ceiling, that bucket **cannot** resolve YES — but a lagging market-maker often leaves a
stale YES bid. Buy **NO** at ~$0.97 → resolves $1.00.
**Evidence:** joined to real Gamma resolution: WR 94.6% raw, ~100% provenance-clean.
**Binding constraint:** `running_max` **provenance** — must use only official hourly
METAR/SPECI, never sub-hourly point obs (the M1β/P3 oracle bug). Block Hong Kong (HKO
oracle, not WU). Low-capacity, late-window, patient: fillable cheap NO mostly appears
>60 min into a lockout.
**Status:** shadow-only. Go-live gated on OOS confirmation against post-2026-05-29
(post-oracle-fix) data + a provenance-clean city whitelist.

---

## 3. Exit policy — HOLD TO RESOLUTION (no PT, no SL)
Tokens resolve 1.0/0.0 at daily-max settlement. A weather position **must ride
intraday noise through to the diurnal peak**; the max isn't known until the peak passes.

> **Mid-day liquidation / "optimal stopping" is FORBIDDEN for this strategy.** It was
> tried and it lost money: the pre-fix mid-day-sell era (May 20–22) booked −$27 over
> 36 trades with repeated CATASTROPHIC_SL exits. Selling a weather token before the
> peak forfeits the entire thesis. Even LOCKOUT-NO works by *holding* the locked-out
> NO to $1.00. Any spec that mandates "forbid hold-to-resolution" is inverting the edge.

Settlement is detected by `_stwa_resolution_loop` (weather_arb.py): polls Gamma
`/markets?condition_ids=<cid>&closed=true` every 300s (the **default query hides closed
markets** — `closed=true` is mandatory), maps our token via `clobTokenIds`→`outcomePrices`,
requires a definitive 0/1, then `close_position(actual_fee=0)` + `record_trade`.

---

## 4. Sizing & capital
- **Fractional Kelly 0.20** of full Kelly; horse-race Kelly for mutually-exclusive YES,
  independent Kelly for NO.
- **Per-city-day budget** R = max(0, min(5%·bankroll, $15) − held_k), `held_k` scoped to
  positions <28h old (so stale never-clearing positions don't starve the arb budget).
- **Stakes** min $3 / max $20; `NEG_RISK_ARB_MIN` $0.50.
- **Sizing reads the live bankroll** — when capital is low, budgets shrink automatically.
  (At true capital $30.74, R≈$1.54 < $3 → only sub-$1.54 arb legs fire. Correct
  accounting is itself a risk control.)

---

## 5. Kill switches & capital rules
| Metric | Rule (CLAUDE.md) | Code reality (2026-05-31) |
|---|---|---|
| Win rate | flag if <35%/20 | not coded as auto-halt |
| Profit factor | halt if <0.8/20 | not coded |
| Daily loss | halt after −$10/day | `is_halted` exists but `max_daily_loss_pct=0` (disabled) |
| Ruin floor | shut down <$50 | `is_ruined` exists but `ruin_floor=0` (disabled) |

STWA now **checks** `is_halted`/`is_ruined` before deploying capital (mirrors the other
strategies), but those thresholds are **config-disabled** (user decision 2026-05-15) and
shared across all strategies. Re-arming them is a Tier-3 cross-strategy decision.
**Current true capital ($30.74) is below the documented $50 ruin floor** — flagged.

---

## 6. Self-audit / validation bounds (the honest closed loop)
Run the Data-Primacy Protocol before any analysis or change:
1. Confirm `STWA_LIVE` + which paths fire (arb/NO/YES). Count resolved positions
   (`trades.jsonl` WEATHER_STWA) + signal activity (shadow logs).
2. Realized vs predicted edge; **Brier / log-loss of p_cal vs resolution**; arb capture rate.
3. Split by city, side, lead-time-to-peak (city temps in **local** time, never UTC).
4. **n≥100 per bucket for any decision.** n=40–99: flag a trend only, do not act. n<40:
   data-collection mode, no changes.
5. Kill-switch check first.

**Anti-sycophancy invariants:**
- A losing trade is data, not a story. 5 losses in a row → the strategy may be broken; say so.
- Never conclude an edge exists from <100 trades/bucket.
- "Should improve WR" with no n≥100 evidence is a red flag — stop.
- Only NEG_RISK_ARB is calibration-independent; directional edge is provisional until
  n≥100 live resolution confirms `p_cal`.

**Slippage / execution audit (the legitimate "every-N-cycles" loop):** compare
`stwa_pricer_eval.jsonl` (p_mc/p_gev/p_pa/p_ps/p_cal per bucket) against ASOS/Gamma
resolution; if realized edge < predicted or fill slippage is structural, throttle and log
to `state_log.md` — not a hidden DB.

---

## 7. Falsified / forbidden — DO NOT REBUILD (all tested on real data)
- **Directional regular-YES** — −EV, miscalibrated: mean p_model 0.326 vs WR 0.075
  (4.3× overconfident); live resolved n=76 at **12% WR, −$43**. SUSPENDED. Re-enable
  ONLY after live n≥100 confirms recalibrated `p_cal`.
- **Mid-day liquidation / optimal-stopping exits** — see §3. Falsified; lost money.
- **Maker MVP on cheap tails** — adverse selection / winner's curse: you fill exactly
  when wrong; −EV at touch.
- **Fade-the-takers** — market is efficiently priced (Brier 0.011–0.015); taker flow is
  informed (follow, don't fade); wallet edge doesn't persist. Falsified on 458k trades.
- **MM-fingerprinting meta-game** — ~10 boundary-pinned MMs; collapses into the existing
  lockout edge, not distinct alpha.

---

## 8. Live state (2026-05-31)
- Engine STWA, `STWA_LIVE=True`. Live paths: **NEG_RISK_ARB + NO**; **regular-YES suspended**.
- Resolution poller live (commit 7833cd86). Bankroll true: **$30.74**.
- Realized to date: −$64.57 / 138 trades / 29.7% WR (YES −$43/12%, NO −$21/52%).
- **No "extreme profitability" is supported by current data.** The path to a viable edge
  is: keep the calibration-free arb, ship LOCKOUT-NO (the validated 94.6% edge), and let
  the math upgrades earn directional YES back only if n≥100 live resolution proves it.
