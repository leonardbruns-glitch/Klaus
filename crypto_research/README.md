# crypto_research — non-HFT structural-edge research framework

A **sandbox** package for designing and backtesting Polymarket crypto up/down
strategies (BTC/ETH/SOL, 5-min `window_size_s=300` and 15-min `=900`) on the
accumulated Tier-1 feature era. It is fully decoupled from the live bot: it
only reads `logs/`, never imports `strategy/` / `main.py` / `config.py`, and
writes nothing outside this directory.

See `../CRYPTO_DATA_BLUEPRINT.md` for the authoritative data matrix.

## NON-HFT mandate

Every decision is made at **bar cadence** (one `market_timeline` row, typically
seconds-to-minutes apart), never per tick. The edge must be
structural / probabilistic / mathematical — a mispricing of the Polymarket
`mid` against the realised outcome distribution, a funding basis, an
order-flow imbalance integrated over a bar — **not** latency racing. The
metrics annualizer is computed on bar returns (`periods_per_year_for_window`),
and the engine exposes data strictly `<= t` to each strategy step.

## Install

Hard deps only: `numpy`, `pandas`, `scipy` (already present).

Optional (any use MUST have a pure numpy/scipy fallback):

```bash
pip install hmmlearn      # optional: regime HMMs (fallback: numpy EM)
pip install statsmodels   # optional: GLM/quantile reg (fallback: scipy.optimize)
```

## Smoke test (no real logs needed)

```bash
python3 -m crypto_research._smoke_test
```

Exercises schema, synthetic panels, fill model reproducibility, portfolio
(binary + perp/funding + fee curve), metrics, the registry, a full engine run,
and a no-look-ahead audit.

## Strategies

- **`s2_hmm_regime`** (`strategies/s2_hmm_regime.py`) — HMM regime lead-lag with
  OBI-driven non-homogeneous transitions. Self-contained `GaussianHMM`
  (numpy Baum-Welch) + `NonHomogeneousHMM` (time-varying
  `A_t[i,j]=softmax_j(beta_ij + w_ij·OBI_t)`, joint gradient-EM or a documented
  two-step approximation). Decides at the close of each 5-/15-min bar; fires
  `BUY_YES`/`BUY_NO` when the OBI-warped one-step-ahead transition probability
  into the bull/bear regime exceeds `p_enter` (default 0.75) and the
  post-fee/post-fill modelled edge clears `edge_min`. `hmmlearn` is used as an
  optional cross-check baseline (numpy EM is the default fallback).
  Self-test (synthetic, no real logs):

  ```bash
  python3 -m crypto_research.strategies._test_s2
  ```

  Validates EM convergence, OBI-transition responsiveness, full engine routing
  (machinery; PnL not asserted on noise-OBI synthetic data), a 98% directional
  hit-rate when OBI genuinely drives the outcome, and the no-look-ahead audit.

- **`binary_delta_hedge`** (`strategies/s1_binary_delta_hedge.py`) — digital-option
  delta-hedger / variance-risk-premium stat-arb. A Polymarket up/down contract
  is a **cash-or-nothing binary call** paying `$1` iff `S_T > K` with strike
  `K = S_open` (window-open Binance price), expiry `T = window_end`. Prices it
  under Black-Scholes (`r=q≈0`), estimates realized vol `RV` from the causal
  spot path, recovers implied vol `IV` by inverting the market mid, trades the
  **variance risk premium** `sign(IV − RV)`, and **delta-hedges** the binary
  leg with a crypto perp swap (`HEDGE` signals) to isolate variance P&L. Core
  maths (full derivations in the module docstring):

  ```
  d2 = [ln(S/K) − 0.5 σ²T] / (σ√T)              # r≈0
  C  = Φ(d2)                                     # binary-call price, ATM → 0.5
  Δ  = φ(d2) / (S σ √T)                          # delta (→∞ as T→0/ATM)
  Γ  = −φ(d2)(1 + d2/(σ√T)) / (S² σ √T)          # gamma (sign flips @ strike)
  ∂C/∂σ = −φ(d2)[ ln(S/K)/(σ²√T) + 0.5√T ]       # vega (ill-conditioned @ ATM)
  hedge P&L ≈ Σ 0.5·Γ·(dS² − σ²S²dt)             # gamma/theta dollar-P&L
  ```

  Caveats honored in code: **IV identification** — vega is ill-conditioned near
  ATM, so `BinaryGreeks.implied_vol` returns `None` there (`moneyness_floor`
  gate) and the strategy falls back to a price-vs-model comparison; **discrete-
  hedging risk** — binary delta/gamma blow up as `T→0` / ATM, so new hedged legs
  are refused inside `min_seconds_to_resolution` and hedge notional is capped
  (`max_delta_notional_frac`); **engine perp-feedback** — the shared engine
  never *closes* perp legs, so the hedge is sized off a **fixed**
  `hedge_ref_notional` (NOT live bankroll) to avoid an equity-feedback
  compounding loop. The perp leg uses its own (tighter) cost model
  (`perp_slippage_frac`) plus carried `funding_rate`. Optional dependency:
  `implied_vol` prefers `scipy.optimize.brentq` (scipy is a hard dep) but
  **degrades to a self-contained bisection** if Brent is unavailable.

- **`s3_rough_vol_kl`** (`strategies/s3_rough_vol_kl.py`) — rough-volatility
  fractional-Brownian-motion stat-arb. Estimates the **Hurst exponent `H`** of
  the underlying 5-min log-returns (DFA primary, R/S cross-check), forms a
  **physical** endpoint-sign probability under the fBM marginal
  `P_phys = Φ((x + μτ)/(σ·τ^H))` (the rough `τ^{2H}` variance scaling, **not**
  Brownian `τ^{1/2}`), and trades when its **Bernoulli KL divergence** from the
  Polymarket-implied `P_poly` exceeds `kl_threshold` and the sign of
  `P_phys − P_poly` is tradeable. Sizing is **asymmetric fractional Kelly**
  (`f* = p − (1−p)·a/(1−a)`, scaled by `λ_yes`/`λ_no` with `λ_no < λ_yes` for the
  favorite-longshot bias). A Davies–Harte (Cholesky-fallback) **fBM path
  simulator** + Monte-Carlo first-passage estimator (`p_phys_mc_barrier`) is the
  alternative `P_phys` engine for target/barrier markets. No optional heavy deps
  (pure numpy/scipy; uses `math.erf` for `Φ`). Core maths:

  ```
  H        = slope( log F(s) vs log s )                # DFA on fGN (returns)
  Var[B^H] = σ²·τ^{2H}                                  # rough variance scaling
  P_phys   = Φ( (x + μτ) / (σ·τ^H) )                    # endpoint-sign YES prob
  KL(p‖q)  = p·ln(p/q) + (1−p)·ln((1−p)/(1−q))          # information divergence
  f*       = p − (1−p)·a/(1−a)                          # full Kelly at ask a
  f_used   = clip(λ_side·f*, 0, max_position_frac)      # asymmetric fractional
  ```

  Safeguards honored: EV gate uses `expected_fill_price` (closed-form bimodal
  penalty, no RNG); `price_limit = ask + per_share_slippage + price_limit_buffer`
  admits the benign-at-touch fill and rejects the rarer toxic-adverse fill; one
  open leg per token-window; needs `min_frac_elapsed` of path before trusting
  the accumulated move. The math is also runnable standalone:

  ```python
  from crypto_research.strategies.s3_rough_vol_kl import (
      hurst_dfa, hurst_rs, fbm_simulator, p_phys_endpoint,
      p_phys_mc_barrier, kl_bernoulli, asym_fractional_kelly)
  ```

## Layout

```
crypto_research/
  data/
    schema.py     # @dataclass records + WindowPanel (features + label)
    loader.py     # LAZY JSONL iterators, build_window_panels, make_synthetic_panels
  backtest/
    fills.py      # BimodalFillModel (benign-at-touch vs toxic adverse-selection)
    portfolio.py  # binary legs + perp/funding legs + injectable fee_fn + equity curve
    metrics.py    # sharpe/sortino/MDD/profit_factor/summary (+ 5m/15m annualizer)
    engine.py     # event-driven, time-ordered, no-look-ahead BacktestEngine
  strategies/
    base.py       # Strategy ABC + Signal/StrategyContext/StrategyParams + registry
    s1_binary_delta_hedge.py  # S1: digital-option delta-hedger (VRP stat-arb)
    s2_hmm_regime.py          # S2: HMM regime lead-lag (OBI-driven transitions)
    s3_rough_vol_kl.py        # S3: rough-vol fBM P_phys vs P_poly (KL-gated, Kelly)
```

## Data quirks honored

- `window_resolution` `binance_*_5m` suffix is a **misnomer**: full-window
  OHLC (300 *or* 900s). `realized_move_pct == (close-open)/open*100`.
- `fee_rate_bps` in `token_trade` is always `0.0` → ignored; fees modelled by
  injectable `fee_fn(price, shares)` (default peaks ~1.8% notional at p=0.5).
- `binance_trade` has no token/window → bucket by `ts_s` into
  `[window_end_ts - window_size_s, window_end_ts)` per asset
  (`attach_binance_ticks`).
- `resolved_yes` is the UP token's label; DOWN/NO token gets the complement.
- Composite join key: `(asset, window_end_ts, window_size_s)`.

## Safeguards (always on)

- **Bimodal fill**: never mid; benign-at-touch with prob `1-pi_toxic`, else a
  worse adverse-selection fill. Seeded RNG → reproducible.
- **Execution slippage**: per-share penalty drawn once in `[0.01, 0.02]`,
  added against every fill.
- **Fees + funding**: all PnL is after Polymarket `fee_fn` and after perp
  funding accrual.
- **Metrics after costs**: Sharpe, Sortino, MaxDrawdown, ProfitFactor, win
  rate, n.

The downstream interface contract (what the four strategy authors implement)
is delivered separately as the engine/Strategy ABC documentation.
