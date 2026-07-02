# Klaus — Persistent Context for Claude Code

## WHAT THE BOT IS DOING RIGHT NOW
**Strategy: STWA (Spatiotemporal Weather Arbitrage)**

Trades Polymarket **daily-high-temperature** markets across 51 cities. A market resolves on the **daily maximum** temperature — the supremum of the day's temperature path — rounded to a whole degree (°F or °C per market) from the official observation.

Engine: `strategy/stwa_engine.py`, driven by `strategy/weather_arb.py`. A 51-city joint Kalman filter over 2D Langevin temperature paths produces a forecast distribution for each city's daily max; bucket win-probabilities are priced, isotonically recalibrated, and sized by Kelly.

Live structure (updated 2026-06-12) — **BAND-first MAKER system** (badatmath mirror, BAND-V3 deployed 06-11). Flags in `strategy/stwa_engine.py` are AUTHORITATIVE (`data/band_config.txt` on the data-mirror snapshots them); this table drifts.
- **STRUCT_BAND maker** (the core): one unified ROI-ordered posting queue, one cash pool — d+2 YES > d+1 YES > d+1 NO > PAIR_FAV > d+2 NO > d+0 YES(mode) > d+0 NO. Mode-centered YES band (off≤1 posted legs, Σ(posted) gate ≤0.85, real-book join-touch quoting, px floor 0.03 d+1/d+2 / 0.10 d+0, ceil ~0.45); favorite-NO overlay 0.52–0.85 on the FULL ladder incl. edge buckets (skip ±1 shoulders); PAIR_FAV both-sides quoting on converged favorites (Σ≤0.90). Cash gate `MAKER_CASH_FRAC=0.90`·free USDC (non-latching), breaker $150, dead-quote reclaim (≥6h old + ≥2¢ behind touch). NO-starvation fixed 06-12 (cash pre-check before book fetch, YES fetch sub-budget 50/80, NO rotation, `[STRUCT-BAND-Q]` cycle log).
- **RECYCLE099** — resting 0.99/0.999 maker asks (`maker_sell`) on held winners; same-day convergence capital recycling.
- **NEG_RISK_ARB** — Σ YES asks < 0.85 spanning set. Model-independent, always on (returns before the candidate loop).
- **THERMO** upper-tail maker-NO — validating, capped $15/day until first 20 resolve clean.
- **M1β lockout-NO** — official-METAR running-max lockouts, provenance-gated.
- **Engine directional taker paths BOTH DISABLED**: `STWA_REGULAR_YES_ENABLED=False` (2026-06-05, σ-collapse disaster) and `STWA_REGULAR_NO_ENABLED=False` (2026-06-11, 0 fires in 48h + armed taker duplicate of the maker NO overlay). The 51-city Kalman engine currently allocates ~no live capital directly; band centers on the MARKET mode.

**Scale-up gate:** `band_resolution_join.py` per-side n≥100 with CI clearing zero (gate-keeper routine tracks the full ledger daily).

Exit: **hold to resolution**. Tokens resolve 1.0/0.0 at daily-max settlement. No profit-target, no stop-loss — a weather position must ride intraday noise through to the diurnal peak.

This is not a simulation. Capital is real. Every parameter change has a dollar cost.

---

## SESSION START PROTOCOL
**MANDATORY:** Read `state_log.md` and internally summarize the last 10 entries before any analysis or code change. Never rely on prior session memory without verifying against the log. Append every session-altering decision (filter added/removed, threshold changed, rule changed, interpretation changed) with: `YYYY-MM-DD HH:MM UTC | SYSTEM/CITY | exact change | reason + evidence`. Only log meaningful state changes, not commentary.

---

## CODING DISCIPLINE
1. **Think before coding** — state the goal and root cause before touching any file.
2. **Simplicity first** — the simplest change that achieves the goal is the right change.
3. **Surgical edits only** — change the minimum lines necessary. No cleanup, no refactoring, no extras.
4. **Goal-driven targets** — define what success looks like (metric, threshold, behaviour) before starting. If the target isn't clear, ask.

---

## ANTI-SYCOPHANCY RULES
1. **A losing trade is not explained away** — it is data. If the last 5 trades are losses, the strategy may be broken. Say so.
2. **Never conclude edge exists from fewer than 100 trades per bucket.** Never. At n=40–99: flag as a potential trend only, do not act.
3. **Optimistic commit messages are a red flag** — if writing "should improve WR" without n≥100 evidence, stop.
4. **If analysis contradicts data, data wins.** Not the thesis. Not the architecture. The data.
5. **Shadow signals are not live entries.** Confirm `STWA_LIVE=true` and which buy paths are enabled before analysing live performance.

---

## DATA PRIMACY PROTOCOL
Run before any analysis or code change:
```
1. Confirm STWA_LIVE=true + which paths fire (arb / NO / YES); count resolved STWA
   positions (trades.jsonl WEATHER_STWA) and signal activity (shadow logs)
2. Realized vs predicted edge; Brier / log-loss of p_cal vs resolution; arb capture rate
3. Split by city, by side (YES / NO / arb), by lead-time-to-peak — city temps in LOCAL time, never UTC
4. n≥100 per city for decisions. n=40-99: flag trends only. n<40: data collection mode, no changes
5. Kill switch triggered? If yes — halt before anything else
```

**Data integrity rules:**
- Resolution oracle = the WU-displayed daily high, sourced from **official hourly METARs + SPECIs only** (AWC / NWS). `official_running_max_c` is populated ONLY from `{AWC, NWS}` — never from 1-min / sub-hourly ASOS spikes. The oracle does not see those; using them for lockout or running_max creates **false lockouts** (the M1β and P3 oracle-audit bugs).
- Resolution is **whole-degree**; bucket padding is **unit-aware** (±0.5°F for °F markets, ±0.5°C for °C markets), applied once in `_parse_outcome`. Never apply a °C pad to a °F market.
- `running_max` is monotone non-decreasing, floored to the official high; never reset by a decreasing NWP feed.
- Only **NEG_RISK_ARB** is calibration-independent. Regular YES/NO edge rides on the isotonic recal map holding up on live 2026 resolution — treat as provisional until n≥100 confirms.
- STWA fills reach `logs/trades.jsonl` only at resolution; they appear in `risk.open_positions` immediately. For "are we trading / what fired", read the shadow logs.
- Cross-check the live pricer log (`logs/shadow/hot/<date>/stwa_pricer_eval.jsonl`) against ASOS / Gamma resolution before drawing any pricing conclusion.

---

## MATHEMATICAL CORE
The market resolves on the **daily max = sup of the temperature path over the remaining window.** This is the keystone: maxing over the full remaining horizon over-counts "tries" — the daily max is actually decided in a narrow window around the diurnal peak. Getting this wrong was the root cause of past YES overconfidence.

- **Process** — 2D Langevin (inertial OU) per city: `dX = V dt`, `dV = (−γV − κX) dt + σ dW`. Joint 51-city state with empirical spatial covariance (Ledoit-Wolf 51×51 shrinkage).
- **State estimate** — Kalman posterior on the residual `X` (the bias-corrected NWP forecast is the drift baseline). A joint `(X,V)` 2N Kalman runs in **shadow**; under hard-coded γ=1.5 its velocity is over-damped, so live still uses position-OU + OLS velocity. Tier-3b (joint κ,γ,σ MLE refit per city) is the real unlock.
- **Pricer (`PA_SHRUNK`, primary; reversible to `MC`)** — daily-max center = bias-corrected NWP peak + per-city `peak_bias` + **β·(observed residual now)** with **β ≈ 0.30**: the morning anomaly mean-reverts ~70% by peak (head-to-head finding; naïve β=1 momentum is +20–25% *worse* than ignoring the obs). Spread σ ≈ 1.0–1.1°C per city (validated vs ASOS — spread was already right; the failure was **mis-location**, not mis-spread). Bucket probs = differences of ONE monotone CDF with a **running-max hard floor** ⇒ coherent, Σ = 1.
- **Recalibration** — raw MC `p_model` was 4.3× overconfident (mean 0.326 vs WR 0.075; rank-corr −0.19, anti-predictive). PA-shrunk fixed the ordering (rank-corr +0.39) but stays overconfident for p>0.5; an isotonic map `g` (fit on 2024) maps raw→calibrated (Brier 0.128→0.114, ECE→0). **YES/NO sizing uses `g(p)`; arb uses raw `p` for the Σ-coverage gate** (range-coverage, robust to per-bucket miscalibration).
- **Allocation** — horse-race Kelly for mutually-exclusive YES buckets; fraction 0.20. (Engine independent-Kelly NO is DISABLED as of 2026-06-01 — all NO via M1β lockout harvest; the NO-sizing code remains but receives no candidates.) Bounded by a **per-city-day budget net of already-held capital** (Tier-4) so cross-time forecast drift can't accumulate mutually-exclusive YES buckets summing to >1. The YES ladder is further gated by the **width gate** (book σ > 1.10×our σ) and **PRE_PEAK only**.

**Honest verdict:** only NEG_RISK_ARB is structurally sound and calibration-independent today (capacity-limited — needs Σask<1 windows + fillable depth). Directional YES/NO are the *path* to a viable edge after the math upgrades, not a guarantee. No "extreme profitability" claim is supported by current data; n≥100 live resolution decides.

---

## CURRENT PARAMETERS (updated 2026-06-12 — `stwa_engine.py` flags are authoritative, this table drifts)
| Parameter | Value | Notes |
|---|---|---|
| Engine | STWA — 51-city joint Kalman | `strategy/stwa_engine.py` + `weather_arb.py`; allocates ~no live capital directly (band uses market mode) |
| Live flag | `STWA_LIVE=True` + `BAND_LIVE=True` | maker band is the core live path |
| Live paths | STRUCT_BAND maker (YES band + NO overlay + PAIR_FAV) + RECYCLE099 + NEG_RISK_ARB + THERMO (capped) + M1β lockout-NO | BAND-V3 2026-06-11 |
| YES enable (taker) | `STWA_REGULAR_YES_ENABLED=False` | DISABLED 2026-06-05; σ-collapse disaster |
| NO enable (taker) | `STWA_REGULAR_NO_ENABLED=False` | DISABLED 2026-06-11; armed taker duplicate of maker NO overlay |
| Band Σ gate | Σ(posted legs) ≤ 0.85 | on the off≤1 basket actually posted, not the ±2 band |
| Band px window | 0.03 (d+1/d+2) / 0.10 (d+0) to ~0.45 YES; NO 0.52–0.85 | real-book re-validated, join-touch never improve |
| Maker cash gate | `MAKER_CASH_FRAC=0.90`·free USDC | non-latching; breaker $150; daily band budget unconstrained (user 06-09) |
| Primary pricer | `PA_SHRUNK` | center = NWP_peak + peak_bias + 0.30·x_hat; reversible to `MC` |
| Intraday weight β | 0.30 | morning residual mean-reverts ~70% by peak (data-backed) |
| Nowcast σ-collapse | DISABLED 2026-06-06 (`NOWCAST_SIGMA_COLLAPSE=False`) | hurt calibration on every metric (Brier 0.181→0.129, ECE halved, rank-ρ up, 5× fewer false-certain buckets; n=53k–76k). σ now = validated per-month. Lockout certainty via running-max floor. Revert: True |
| Recalibration | isotonic `g` (`config/stwa_isotonic.json`) | NO/YES Kelly uses `g(p)`; arb uses raw `p`. Map fit on flat-σ 2024 — now RE-ALIGNED (σ-collapse off). Live-refit cron `stwa_isotonic_live_refit.py` (guarded) keeps it current |
| Kelly fraction | 0.20 | of full Kelly |
| Edge / Kelly floor | `EDGE_MIN=0.04`, `KELLY_F_MIN=0.015` | risk-of-ruin safety |
| Stake | min $3, max $20 | `NEG_RISK_ARB_MIN` $0.50 |
| City-day budget | min(5%·bankroll, $15) − held | Tier-4 cross-time cap. Entry: arb ~$35–55 bankroll; 1st YES leg ~$60; full ladder ~$180 |
| Arb threshold | Σ YES ask < 0.85 (0.80 if ≥4 legs) | NEG_RISK_ARB |
| Prob-sum guard | `PROB_SUM_MAX=1.35` | Σ p_model above → skip city (MC bug) |
| Exit | hold to daily-max settlement | no PT, no SL |
| Oracle | official hourly METAR/SPECI high (AWC/NWS) | NOT 1-min ASOS |

---

## WEATHER EDGE MAP — what's real, what's dead
- **LIVE — STWA** (above). The primary engine.
- **VALIDATED companion — LOCKOUT-NO** (settlement-lock): buy NO once `running_max` has passed a bucket's ceiling (physically impossible to resolve YES) while a stale YES bid persists. WR 94.6% raw / ~100% provenance-clean. **Execution timing: buy EARLY in the lockout** (2026-06-09 census superseded the old late-window advice); oracle blocklist {VHHH, ZGSZ}; HK live only via the HKO 1-min debounced feed. Validators: `analysis/weather/lockout_{capacity,resolution_join}.py`.
- **DEAD-ENDS — do not rebuild** (all falsified on real data 2026-05-29):
  - *Fade-the-takers* — market is efficiently priced (Brier 0.011–0.015), taker flow is informed (follow, don't fade), and wallet edge does NOT persist (can't target "known losers").
  - *MM-fingerprinting meta-game* — ~10 competitive cross-market MMs, deterministic but boundary-pinned; collapses into the existing lockout edge, not a distinct alpha.
  - *Maker MVP* — adverse selection / winner's curse: you get filled exactly when wrong; −EV at touch.

---

## KILL SWITCHES & CAPITAL RULES
| Metric | Floor | Action |
|---|---|---|
| Win rate | >45% | Flag if <35% over 20 trades |
| Profit factor | >1.3 | Halt if <0.8 over 20 trades |
| Daily loss | — | Halt after -$10/day |
| Weekly bankroll | <$75 | Halt, full review |
| Ruin floor | <$50 | Shut down entirely |

Scale-up: raise stake only after WR >55% confirmed over 20+ live trades.

---

## ACTION TIERS
- **Tier 1 (autonomous)**: reads, stats, bug fixes with clear root cause, parameter changes ±20% with n≥100
- **Tier 2 (cite data in commit)**: parameter changes >±20%, new filters, disabling a buy path
- **Tier 3 (never without instruction)**: stake beyond defined limits, kill switch thresholds, enabling/disabling regular-YES, disabling trade logging

---

## INFRASTRUCTURE
- **VPS**: systemd unit `klaus` at `/root/Klaus`
- **Deploy**: `cd /root/Klaus && git pull && systemctl restart klaus`
- **Logs**: `tail -f /root/Klaus/logs/bot.log` or `journalctl -u klaus -f`
- **Dev branch**: `claude/find-lag-parameter-rFQ0N`
- **NMS feeds**: edge lives in early temperature info — 16 stations live (AWC, NWS US, NEA Singapore, IMGW Poland) giving ~9–28 min gains over AWC. Expansion candidates: SynopticData / AEMET / Météo-France / KNMI free keys, WIS2 MQTT for global BUFR.

- **EVOLVE loop (autonomous, 2026-07-02)**: `ops/evolve/` — `CHARTER.md` (human-owned constitution) + headless-Claude actuators: daily 11:23 UTC (`klaus_evolve_daily.timer`, measures ground truth → applies charter-gated changes → deploys → verifies), weekly Sun 13:41 UTC (experiment design), repair-on-crash-loop. Mechanical liveness watchdog every 2 min (`klaus_liveness.timer`; bond_watchdog retired). Reports: `logs/evolve/`; human queue: `logs/evolve/PENDING_HUMAN.md`.

**Development workflow (NON-NEGOTIABLE):**
Claude edits locally → commits → pushes to dev branch → Claude SSHes into VPS to deploy. Never edit or commit on the VPS. Never `git checkout origin/...` on VPS. VPS only writes to `logs/`.

**Deploy command (run via SSH):**
```bash
ssh root@85.137.174.86 "bash -c 'git -C /root/Klaus pull && systemctl restart klaus && systemctl is-active klaus'"
```

---

## KEY DESIGN DECISIONS
- Resolution oracle = WU-displayed daily high from **official hourly METARs + SPECIs only**; `official_running_max_c` populated ONLY from `{AWC, NWS}`, never sub-hourly point obs.
- `NEG_RISK_ARB` returns before the candidate loop → unaffected by the YES/NO enable flags; it is the only edge that doesn't depend on model calibration.
- Bucket padding is unit-aware (`_parse_outcome`); `running_max` is monotone and official-floored.
- STWA positions are tagged `WEATHER_STWA`, appear in `risk.open_positions` at fill, and reach `logs/trades.jsonl` only at resolution.
- One STWA position per city-bucket per day; opposite-direction same-bucket re-entry is blocked; per-city-day budget cap bounds cross-time accumulation.
- Pricer A/B is live: MC / GEV / PA / PA-shrunk + isotonic `p_cal` logged per bucket to `stwa_pricer_eval.jsonl`; joint 2N Kalman shadow in `stwa_state.jsonl`.
- Kalman + per-city velocity state persisted to `data/stwa_kalman_state.npz` + `stwa_city_state.json`; restored on restart (no warm-up blind window).

---

## ANALYSIS SCRIPTS
```bash
# STWA calibration / pricing
python3 analytics/stwa_fit_params.py              # per-city (κ,γ,σ) MLE refit
python3 analysis/weather/stwa_pricer_backtest.py  # pricer vs ASOS, μ-bias diagnostic
python3 analysis/weather/stwa_intraday_value.py   # β-shrinkage head-to-head
python3 analysis/weather/stwa_isotonic_calib.py   # fit isotonic recalibration map

# Edge validation
python3 analysis/weather/lockout_capacity.py
python3 analysis/weather/lockout_resolution_join.py   # WR vs real Gamma resolution
```
