# crypto_research — Research Framework (DRAFT)

A **research scaffold** for structurally-advantaged, NON-HFT strategies on
Polymarket BTC/ETH/SOL up/down binary windows (5-min = `window_size_s 300`,
15-min = `900`). Four candidate strategies, a no-look-ahead event-driven
backtester with a punitive execution model, a parameter-search harness with
walk-forward overfitting guards, and a CLI.

---

## ⚠️ HONEST DISCLAIMER — read this first

**No live edge is proven here.** These are research scaffolds, not a deployable
edge.

* The base rate is a **near coin-flip**: classes are balanced ~48–51% up across
  all six (asset × window-size) buckets in `window_resolution`. A directional
  prior buys you nothing — **any edge must come from the features**, and whether
  any of these four models actually extracts one is an *empirical question that
  is not yet answered*.
* Every metric you will see on `--synthetic` data is a **machinery / sign-
  correctness check only**. The synthetic generator embeds a deliberate
  ground-truth edge, so large Sortino / PnL there proves the *plumbing* works,
  **not** that the strategy has alpha. Large synthetic Sharpe/PnL follows from
  the injected ground-truth edge plus bankroll compounding — **ignore the
  magnitude**. (An earlier *uncapped* equity blow-up traced to two real S1
  defects — a missing one-leg-per-window guard and perp hedge legs the engine
  never closed, so their mark-to-market accumulated across the whole run — both
  now fixed: S1 re-hedges instead of re-entering, and the engine unwinds each
  hedge at its window's settlement.)
* A real edge claim requires **n ≥ 100 out-of-sample trades per
  (asset, window_size, regime) bucket**, on the real Tier-1 feature era, with a
  positive **walk-forward** (not in-sample) result after fees + funding +
  bimodal fills. Below n=100 it is data-collection / trend-only. This is the
  project's anti-sycophancy mandate and it binds here.
* Two-era data caveat (see `CRYPTO_DATA_BLUEPRINT.md`): rich Tier-1 features
  exist **only 2026-05-26 … 06-05 (11 days)**; real fills exist **only
  2026-04-14 … 05-21**. They barely overlap. `window_resolution` is the bridge
  label set. Eleven days of 5-min windows is enough to *explore*; it is **thin**
  for a confident edge claim and starves 15-min folds.

Treat positive numbers as "the code runs and the math is sign-correct," never as
"this makes money," until a real-data walk-forward at n≥100 says otherwise.

---

## The four strategies (one paragraph each)

All four model a Polymarket up/down contract as a **cash-or-nothing binary** on
the window's endpoint move and decide at **bar cadence** (one `market_timeline`
row per `on_step`, seconds-to-minutes apart). None races the tape.

1. **`binary_delta_hedge` (S1 — Binary Delta-Hedged, variance-premium-gated).**
   Prices the up/down contract as a Black–Scholes cash-or-nothing binary call
   with strike = the causal window-open Binance spot, and exposes the exact
   binary Greeks (price `e^{-rT}Φ(d2)`, delta `e^{-rT}φ(d2)/(Sσ√T)`, gamma,
   vega) plus a Brent IV inversion. It compares realised vol (close-to-close
   blended with Garman–Klass) to the book-implied vol; **`|IV − RV|` acts as a
   stand-down gate** (no variance premium ⇒ no trade), then buys whichever leg's
   model fair value most beats its expected (bimodal) fill and opens a perp
   delta hedge that the engine unwinds at the window's settlement. Handles the
   two documented binary pathologies (IV non-identified at ATM; delta→∞ as T→0)
   by degrading to a price-vs-model comparison and refusing late hedged legs.
   Ablate the hedge with `hedge_enabled=False` to isolate the pure binary leg.
   **Honest scope (see KNOWN ISSUES):** the *directional* `sign(IV−RV)` selector
   is not yet wired (leg choice is by model-vs-fill edge, not the variance
   view's sign), and the perp hedge is a **bounded fixed-reference variance-carry
   proxy, not a position-exact delta hedge**.

2. **`s2_hmm_regime` (S2 — OBI-Driven Regime-Switching HMM).**
   A latent bull/bear/chop regime drives next-window direction; **order-book
   imbalance (OBI)** is an exogenous covariate that warps the regime-transition
   matrix via a multinomial-logit `A_t[i,j] = softmax(β + w·OBI_t)`. Pure-numpy
   Gaussian HMM (Baum–Welch) and a non-homogeneous input-output HMM (joint
   gradient-EM) are implemented; `hmmlearn` is an *optional* cross-check only.
   At each window close it forward-filters the regime over the cross-window bar
   stream and forecasts the next window's direction, trading when the modelled
   post-fee edge clears the floor. Warmup is unsupervised (never reads labels).

3. **`s3_rough_vol_kl` (S3 — Rough Volatility & Fractional Information
   Divergence).** Estimates a rolling **Hurst exponent** (DFA + R/S) on the
   causal log-return path, then computes a *physical* outcome probability under
   fractional Brownian motion with the rough `τ^{2H}` variance scaling
   (`P_phys = Φ((x + μτ)/(σ τ^H))`). It compares `P_phys` to the book-implied
   `P_poly` via the **Bernoulli KL divergence** and trades the disagreement,
   sizing by asymmetric fractional Kelly (`λ_no < λ_yes` for favorite-longshot
   bias). Collapses to the Brownian baseline at `H=0.5`. *Note: the default
   `min_returns=32` exceeds the synthetic generator's 30 steps/window, so on
   default synthetic panels S3 fires zero trades by design — override
   `--param min_returns=12` to exercise it, or run it on the real era where
   windows have many more rows.*

4. **`microstructure_statarb` (S4 — Efficient-Price Stat-Arb with
   Adverse-Selection Immunization).** In *low-toxicity* windows the binary mid is
   a noisy estimate of `P(up)`; a **microstructure-noise-corrected efficient
   price** (local-level Kalman, Roll bounce → noise variance) plus a
   **noise-robust two-scales realized vol** imply a better-calibrated `P_fair`,
   and the signed gap `mid − P_fair` reverts by window close. The crucial
   safeguard is **VPIN order-flow toxicity**: when informed flow is present the
   strategy *stands down* rather than be the adversely-selected counterparty —
   the antithesis of HFT. Sizing is information-entropy (KL-gain) × (1−toxicity)
   × fractional Kelly. Optional EVT/GPD tail overlay (off by default).

---

## Data: which log feeds which loader

All loaders live in `crypto_research/data/loader.py`. Paths are under
`/root/Klaus/`. See `CRYPTO_DATA_BLUEPRINT.md` for the full schema.

| Log on disk | Loader | Role |
|---|---|---|
| `logs/shadow/hot/<date>/window_resolution.jsonl` | `iter_window_resolution` / `load_resolution_index` | **The clean label set** (`resolved_yes`, `moved_up`, window OHLC). |
| `logs/shadow/hot/<date>/market_timeline.jsonl` | `iter_market_timeline` | **Primary feature panel** (mid/book/OBI/VPIN/binance returns/regimes). |
| `logs/shadow/hot/<date>/binance_trade.jsonl` | `iter_binance_trade` + `attach_binance_ticks` | Raw tick tape (optional enrichment for true volume-VPIN). |
| `logs/shadow/hot/<date>/ob_delta.jsonl` | `iter_ob_delta` | Full L2 book event stream (available; not used by the 4 defaults). |
| `logs/shadow/hot/<date>/token_trade.jsonl` | `iter_token_trade` | Polymarket executed prints (`fee_rate_bps` here is **0.0 — untrusted**). |

**The label join** (`build_window_panels`): `market_timeline` feature rows are
grouped by `(token_id, window_end_ts)` into a `WindowPanel`, then the resolved
label is attached by the composite key **`(asset, window_end_ts, window_size_s)`**
(verified 100% join rate on disk). The `WindowPanel` carries the causal
`timeline` for `on_step` and hides `label_resolved_yes` / settlement OHLC from
the strategy until the engine settles the window. Note the field-name quirk: in
`window_resolution`, `binance_open_5m / close / high / low` are the **window**
OHLC regardless of `window_size_s` (the `_5m` suffix is a misnomer) — the loader
maps them to `panel.binance_open/close/high/low`, which are **never** exposed in
`on_step`.

**Synthetic data** (no logs needed): `make_synthetic_panels(n, seed=...,
window_size_s=300, up_and_down=False, edge_strength=0.6)` embeds a tunable
ground-truth late-window edge for sign-correctness tests.

### Execution-realism model (always applied by the engine)

* **Fees** — injectable `fee_fn`; default peaks **~1.8% of notional at p=0.5**
  (`default_fee_fn(base=0.036)`). The logs' `fee_rate_bps=0.0` is ignored.
* **Bimodal fills** — with prob `1−π_toxic` a benign fill **at touch** + per-share
  slippage in `[0.01, 0.02]`; with prob `π_toxic` a worse fill by an
  `adverse_penalty` (adverse selection). Seeded → reproducible. **Never assumes
  mid-market fills.**
* **Funding** — perp hedge legs accrue per-interval funding (`HEDGE` signals).
* **All metrics are reported after fees + funding.**

---

## Running it — `run_research.py`

`run_research.py` is the CLI. It registers all four strategies on import. Run
from `/root/Klaus/`.

```bash
# List the registered strategies
python3 -m crypto_research.run_research --list

# Single backtest on SYNTHETIC data (default; no logs needed)
python3 -m crypto_research.run_research --synthetic --n 400 \
    --strategy s2_hmm_regime

# Single backtest on the REAL Tier-1 feature era (BTC 5-min)
python3 -m crypto_research.run_research --real \
    --assets BTC --window 300 --start 2026-05-26 --end 2026-06-05 \
    --strategy microstructure_statarb

# Override strategy params (repeatable --param name=value)
python3 -m crypto_research.run_research --synthetic --n 300 \
    --strategy s3_rough_vol_kl --up-and-down \
    --param min_returns=12 --param kl_threshold=0.01

# Stress the execution model and emit JSON
python3 -m crypto_research.run_research --synthetic --strategy binary_delta_hedge \
    --pi-toxic 0.4 --adverse-penalty 0.05 --fee-base 0.05 --json
```

Key flags: `--synthetic|--real`, `--assets`, `--window {300,900}`,
`--start/--end` (real), `--strategy`, `--param name=value` (repeatable),
`--cash`, `--seed`, `--pi-toxic/--adverse-penalty/--fee-base` (execution stress),
`--no-short-entries` (enforce `min_seconds_to_resolution`), `--json`. Full help:
`python3 -m crypto_research.run_research --help`.

---

## Parameter search & overfitting guards — `optimize/search.py`

`crypto_research/optimize/search.py` runs a strategy through the engine over a
parameter grid and ranks by an **objective** (default **annualized Sortino**)
under hard **constraints** (`min_trades`, `min_profit_factor`,
`max_drawdown_limit`, optional `min_win_rate`). Infeasible candidates are kept
but ranked below every feasible one (never "win" by violating a risk floor).

Four entry points (also driven from the CLI via `--search`):

```bash
# Exhaustive GRID search (IN-SAMPLE — explore the surface)
python3 -m crypto_research.run_research --synthetic --n 400 \
    --strategy s2_hmm_regime --search grid \
    --grid p_enter=0.70,0.75,0.80 --grid edge_min=0.02,0.03 \
    --objective sortino --min-trades 30 --min-pf 1.1 --max-mdd 0.4

# RANDOM search (efficient explorer for big grids)
python3 -m crypto_research.run_research --synthetic --n 400 \
    --strategy s2_hmm_regime --search random --n-samples 40 \
    --grid p_enter=0.65,0.70,0.75,0.80,0.85 --grid n_states=2,3,4

# TRAIN/TEST split: select on past, REPORT on held-out future
python3 -m crypto_research.run_research --synthetic --n 600 \
    --strategy s2_hmm_regime --search train_test --train-frac 0.7 --top-k 5 \
    --grid p_enter=0.70,0.75,0.80

# WALK-FORWARD: re-fit on the anchored past, score the next fold (the honest OOS)
python3 -m crypto_research.run_research --synthetic --n 600 \
    --strategy s2_hmm_regime --search walk_forward --k-folds 4 \
    --grid p_enter=0.70,0.75,0.80
```

Programmatic use:

```python
from crypto_research.optimize import grid_search, walk_forward, SearchConfig
import crypto_research.run_research  # side-effect: registers the 4 strategies

report = walk_forward(
    "s2_hmm_regime",
    {"p_enter": [0.70, 0.75, 0.80]},
    panels,                      # List[WindowPanel] from build_window_panels(...)
    k_folds=4,
    config=SearchConfig(objective="sortino", min_trades=100, min_profit_factor=1.2),
)
# report.best_split.test  -> the out-of-sample metrics; report each, not the train number
# report.best_split.degradation = train_obj - test_obj  -> overfitting gauge
```

### Overfitting guards (documented + enforced)

* **Walk-forward is the headline number, not in-sample grid search.** `grid_search`
  / `random_search` are *explorers* on one slice; their ranking is in-sample and
  will overstate edge. Always confirm with `train_test_search` or `walk_forward`
  and **report the TEST metric**.
* **Time-ordered forward split** (`split_panels_time`): train = the past, test =
  the future, cut by `window_end_ts`. No future leaks into parameter selection.
* **Walk-forward** (`walk_forward`): each fold re-selects parameters on the
  anchored past and scores the immediate future, so no single globally-overfit
  point can win; the aggregate per-fold OOS score is the credible estimate.
* **Train→test degradation** (`SplitResult.degradation = train_obj − test_obj`) is
  reported per candidate — a large positive gap flags overfitting even when the
  test score is positive.
* **`min_trades` gate** kills the classic "0 trades / infinite Sharpe" overfit and
  enforces the n≥100 discipline when you set it there.
* **Risk-adjusted objective** (Sortino) + **MDD / PF constraints** stop a single
  lucky window from topping the ranking.
* **Fixed execution-stress seed** across candidates (`SearchConfig.seed`,
  `pi_toxic`, `adverse_penalty`) so differences are attributable to parameters,
  not RNG. For a robustness check, add `seed` as a grid axis and require the
  winner to clear constraints across all seeds (multi-seed stability).

---

## Installation / dependencies

**Hard dependencies (required):** `numpy`, `pandas`, `scipy`. That's it — the
hot path of all four strategies runs on numpy/scipy/stdlib only.

```bash
pip install numpy pandas scipy
```

**Optional extras (NOT required; pure numpy/scipy fallbacks exist):**

```bash
pip install hmmlearn      # S2: accelerated/cross-check Gaussian HMM baseline only
pip install statsmodels   # S2: optional logit cross-check
```

* `hmmlearn` — S2 uses it *only* as an optional accelerated cross-check
  (`GaussianHMM.fit_with_hmmlearn`); the default path is the self-contained
  Baum–Welch implementation and degrades gracefully if it is absent.
* `statsmodels` — optional logit cross-check for S2's transition M-step; also
  optional. Neither extra changes the default results.

S1, S3, and S4 use no optional dependencies at all.

---

## Quick verification (no real logs)

```bash
# Full pipeline self-test (synthetic): schema, fills, portfolio, metrics, engine,
# no-look-ahead audit
python3 -m crypto_research._smoke_test

# Each strategy fires and produces populated metrics on synthetic data
python3 -m crypto_research.run_research --synthetic --strategy binary_delta_hedge
python3 -m crypto_research.run_research --synthetic --strategy s2_hmm_regime
python3 -m crypto_research.run_research --synthetic --strategy s3_rough_vol_kl --param min_returns=12 --up-and-down
python3 -m crypto_research.run_research --synthetic --strategy microstructure_statarb --up-and-down
```

A populated Sharpe/Sortino/MaxDD/ProfitFactor and the passing no-look-ahead audit
confirm the framework is wired correctly. **Remember the disclaimer: synthetic
PnL proves plumbing, not profit.** Real validation = a positive walk-forward at
n≥100 OOS on the 2026-05-26…06-05 Tier-1 era, after fees + funding + bimodal
fills.

---

## KNOWN ISSUES — punch-list before any real-data edge run

The math primitives were independently audited and verified correct, and the
no-look-ahead audit passes for all four. The items below are **wiring / modelling
gaps**, not math errors. Several are deliberate design choices the research lead
should rule on. Severity in brackets.

**Fixed in this build (was broken in the first cut):**
- *[HIGH] Toxic fills never reached PnL.* The limit check rejected every toxic
  draw (`price_limit_buffer` < `adverse_penalty`), so adverse selection — a core
  mandate — was silently absent. **Fixed:** the engine now admits on the benign
  price (`touch + slippage`) and **always books the realized (possibly toxic)
  fill**. Verify with the `toxic=` counter in `_smoke_all_strategies` (now > 0).
- *[HIGH] S1 re-fired a fresh binary every step* (no one-leg-per-window guard).
  **Fixed:** S1 now re-hedges instead of re-entering while holding.
- *[HIGH] Perp hedge legs were never closed* → mark-to-market accumulated for the
  whole run (the equity blow-up). **Fixed:** the engine unwinds each hedge at its
  window's settlement (matched by `window_end_ts`).
- *[GAP] Search `min_trades` defaulted to 30* below the n≥100 mandate. **Fixed:**
  default is now 100.
- *[MED] S4 `min_seconds_to_resolution` was inert* (it relied on an engine flag
  that defaults open), letting `P_fair` collapse to a 0/1 step near close.
  **Fixed:** S4 now enforces the horizon guard internally.

**Still open — decide before trusting any real-data number:**
- *[HIGH] S1 hedge is a proxy, not a position-exact delta hedge.* `_target_perp_qty`
  sizes off a fixed `hedge_ref_notional`, not the actual filled binary shares.
  Fix: size `target_units = -Σ(filled_shares)·Δ` off the real leg. Until then the
  perp leg is a bounded variance-carry term, not a true hedge.
- *[HIGH] S1 `sign(IV−RV)` direction is dead code* (`vrp_dir` is computed but only
  used as an on/off gate). Either enforce it as the leg selector or relabel
  (the README now relabels honestly).
- *[HIGH] S2 horizon/instrument mismatch.* The model forecasts the **next**
  window's regime but the routed token settles against the **current** window.
  Fix: at window `w` close, trade window `w+1`'s token (cross-window linkage), and
  score the call against `w+1`'s label. The `_test_s2.py` "98% accuracy" is a
  same-window measurement artifact — rewrite it to score `w → w+1`.
- *[MED] S3 endpoint `x` should come from Binance spot, not the token mid*
  (`use_binance_path=False` path); and `S_open` is proxied by the first causal
  history row — only trust it when that row starts near the window open
  (`seconds_to_resolution ≈ window_size_s`).
- *[MED] S3 edge gate is not explicitly post-fee* — net the modeled per-share fee
  inside `_gate_edge` rather than leaning on `edge_min`.
- *[LOW] S4 VPIN runs in tick-time on the spot series* with unit volumes; feed
  real per-tick (signed) volumes for the true volume-synchronized VPIN.
- *[LOW] Registry naming is mixed* (`binary_delta_hedge`, `microstructure_statarb`
  vs `s2_hmm_regime`, `s3_rough_vol_kl`) — cosmetic.

**The honest validation protocol** (all four): run `walk_forward` on the real
Tier-1 era with `min_trades ≥ 100` **per (asset, window_size)** bucket, report the
held-out `test` metric (never the train number), and run a fill-realism variant
to confirm the edge survives toxic fills. Treat anything below n=100 as
data-collection/trend-only.
