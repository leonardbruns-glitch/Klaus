# Weather Ecosystem — Data Inventory & Blueprint

> **Purpose:** complete catalog of every data artifact in the STWA weather ecosystem —
> raw feeds, persistent state, live shadow logs, resolution/trade data, the cron jobs
> that produce them, and the analysis scripts that consume them. Built so a fresh agent
> can be pointed at a weather task and know *exactly* where every fact lives, what schema
> it has, who writes it, and the provenance gotchas. Sister doc to `CRYPTO_DATA_BLUEPRINT.md`.
>
> **Built:** 2026-06-08. Verify paths/schemas before relying on them (logs rotate; the
> bot is live and schemas evolve). Authoritative behavioral source is always
> `strategy/stwa_engine.py` + `strategy/weather_arb.py`, not this doc.

---

## 0. The universe

- **49–51 cities.** Canonical registry: `analysis/weather/stations.py` (`Station` objects:
  slug, ICAO, lat/lon, **local tz**, °C-vs-°F market unit). `skill_matrix.json` has 49
  stations; `oracle_calibration.json` / `regime_today.json` carry 50–51.
- **Market:** Polymarket **daily-high-temperature** per city. Resolves on the **daily max**
  (sup of the day's temperature path), rounded to whole degree (°F or °C per market).
- **Oracle of truth:** WU-displayed daily high = official **hourly METAR + SPECI** only
  (AWC / NWS). Never 1-min/sub-hourly ASOS spikes. Whole-degree; bucket pad is unit-aware
  (±0.5°F or ±0.5°C), applied once in `_parse_outcome`.
- **All city temperatures are LOCAL time** (`Station.tz`). Never UTC for diurnal/peak logic.

---

## 1. Raw input feeds (live — the "early temperature info" edge)

### 1a. Live NMS observation feeds — `strategy/national_met.py`
Layered fastest→slowest, all merge into `_icao_metar_cache` (freshest-per-station wins).
Receipt-time logged per source to `obs_receipt.jsonl` (see §4). **Sources observed live
2026-06-08:** Synoptic, AWC, NWS, WIS2, JMA, FMI, DWD, IMGW.

| Source | Coverage | Latency | Auth | Notes |
|---|---|---|---|---|
| Synoptic HF-ASOS | US cities (KLAX…) | 1–5 min | key | fastest US |
| Singapore NEA | WSSS Changi (S24) | ~2 min | none | |
| JMA AMeDAS | RJTT Tokyo Haneda (44166) | ~9 min | none | fills AWC hourly gaps |
| DWD BrightSky | EDDM/EDDB Munich/Berlin | ~7 min | none | |
| FMI WFS | EFHK Helsinki | ~7 min | none | |
| IMGW Poland | EPWA Warsaw | ~10 min | none | |
| KMA | RKSI/RKPK Korea | — | key (`KMA_API_KEY`) | dormant w/o key |
| NOAA NWS API | US fallback | ~10 min | none | |
| WIS2 MQTT push | 60+ global airports | push | none | `strategy/wis2_synop.py`; TLS-only :8883 |
| AWC METAR batch | **ALL ICAO globally** | 15–30 min | none | **universal baseline**, 4-min poll |

- **Feed-lead gain:** ~9–28 min over AWC baseline (Stage-0 measurement, commit d73a08d7).
- **Expansion candidates:** SynopticData full / AEMET (Spain) / Météo-France / KNMI keys;
  WIS2 MQTT for global BUFR. Register: KMA `apihub.kma.go.kr`, AEMET `opendata.aemet.es`.
- Related: `strategy/upstream_map.py` (validated upstream→downstream synoptic pairs, r≥0.30,
  from 10yr ASOS), `strategy/upstream_oracle.py`.

### 1b. Historical training corpora (parquet) — `data/`
| File | Rows | Schema | Use |
|---|---|---|---|
| `stwa_asos.parquet` | 1.74M | city, icao, time_utc, temp_c, dew_c, sky_rank | ASOS obs history (calibration ground truth) |
| `stwa_nwp.parquet` | 1.79M | city, icao, time_utc, temp_nwp_c, dew_nwp_c, model | NWP forecast history (multi-model) |
| `stwa_nwp_gfs_global.parquet` | 0.70M | (same) | GFS global backfill |
| `taker_wallet_profiles.parquet` | 7709 | wallet, name, n, pnl, wr, edge_per_$, ci… | on-chain wallet edge profiles (taker research) |
| `taker_trades_*.parquet` | — | per-trade taker tape (date-ranged) | taker-flow studies |

- ASOS history is also cached per-station 2015–2024 in `logs/asos_cache/*.json` (36 files,
  e.g. `KLAX_2015_2024.json`).
- Producers: `analytics/stwa_fetch_data.py`, `analytics/backfill_nwp_gfs_global.py`.
- Open-Meteo multi-model archive AI cache: `logs/backtest_cache/ai_<city>_<range>_d1.json`
  (1863 files) — per-city per-model historical forecasts feeding the skill matrix.

---

## 2. Persistent state & calibration stores

### 2a. `config/` — fitted parameters (slow-changing)
| File | Structure | What it is |
|---|---|---|
| `stwa_params.json` | stations, spatial_covariance (51×51 Ledoit-Wolf), city_order, spatial_kernel, fit_date | **Kalman/Langevin params** — per-city (κ,γ,σ) + joint spatial cov. Refit: `analytics/stwa_fit_params.py` |
| `oracle_calibration.json` | _meta, stations(50), sigma_calibrated_c, discretization_mbe_c | per-station σ + discretization bias for the oracle |
| `stwa_city_dist.json` | per-city dist params (12 keys) | per-city daily-max distribution params |
| `stwa_peak_calib.json` | _beta(0.30), per-city peak_bias | **β-shrinkage + peak_bias** (center = NWP_peak + peak_bias + β·x_hat) |
| `stwa_isotonic.json` | grid, calibrated, fit | **isotonic recal map `g`** (raw p_model → p_cal). `.bak` + `_candidate.json` (guarded auto-promote) |
| `wu_resolution_stations.json` | city → station | which station WU uses for resolution |
| `auto_kill.json` | WEATHER_INTRADAY/TAIL/NOSIDE/CITYCTR | per-substrategy kill flags |

### 2b. `strategy/` — model state & lookup tables (faster-changing)
| File | Structure | What it is |
|---|---|---|
| `skill_matrix.json` | _meta, stations(49) × {era5, gfs_seamless, icon, ecmwf_ifs025, graphcast, gem, jma, ukmo, meteofrance, merra2, aifs, _climatology} | **per-(city,model) forecast skill** (RMSE/bias by month). Refit daily (cron 09:00). `_pre_ukmo_jma` = prior snapshot |
| `hot_bust_rates.json` | _meta, cities | GFS-d1 hot/cold **bust rates** per city/month. Append daily (cron 10:00) |
| `regime_today.json` | generated_at, target_dates, cities(51) × date × {regime, mu, sigma, spread, n_models, bias_corr} | **today/next-3-day regime** (normal/volatile) + ensemble μ/σ. Rebuilt daily (cron 06:00) |
| `tail_trigger_calibration.json` | _meta, cities | tail-bucket trigger calibration |
| `station_microclimate.py` | code | per-station microclimate adjustments |
| `bucket_consensus_state.json` | {} | runtime consensus scratch |

### 2c. `data/` — live engine state (restored on restart)
| File | What it is |
|---|---|
| `stwa_kalman_state.npz` | Kalman posterior (X,V) per city + covariance — restored on boot, no warm-up blind window |
| `stwa_city_state.json` | per-city velocity (OLS) + running state, all 51 cities |

---

## 3. Live shadow logs — `logs/shadow/hot/<YYYY-MM-DD>/`
**Rotated daily; pruned to KEEP_DAYS=10 (cron 04:00, `ops/prune_shadow_logs.sh`). Present
2026-05-29 … today.** These are the primary "what fired / what did the model think" record.
STWA fills do NOT hit `trades.jsonl` until resolution — read these for live behavior.

| File | Schema (keys) | Meaning |
|---|---|---|
| `stwa_pricer_eval.jsonl` | city, lo, hi, **p_mc, p_gev, p_pa, p_ps, p_cal**, running_max, t_close, phase, ts | **Pricer A/B per bucket** — MC/GEV/PA/PA-shrunk + isotonic p_cal. Core calibration record |
| `stwa_state.jsonl` | ts, city, regime, running_max, last_obs_ts, metar_age_s, kalman_mu/var, v_hat_ols, pv_var_ols, **x_hat_joint, v_hat_joint** (2N shadow), nwp_mu, suspended | engine state snapshot incl. joint 2N Kalman shadow |
| `stwa_signals.jsonl` | city, bucket, direction, token_id, p_model, ask, edge, confidence, stake, regime, phase, metar_age_s, kalman_var, kriging_pct, p_gev, drift_bias, ts, clob_ask_live | **directional entry signals** (the actual buy decisions) |
| `stwa_ladder_book.jsonl` | ts, city, phase, regime, buckets | full bucket book snapshot |
| `metar_lockout.jsonl` | schema_version, city, icao, token_id, bucket_lo/hi_c_padded, running_max_c, asos_running_max_c, yes/no books, fill_path, seconds_since_first_lockout, seconds_to_event_close, peak_hour_utc… | **lockout-NO** candidates (running_max passed ceiling) |
| `m1_beta_probe.jsonl` | schema_version, phase, ts_submitted, condition_id, city, icao, running_max_c, bucket_lo/hi_c, depth_c, yes/no books at signal, sec_since_first_lockout, sec_to_close, stake_usd, layer_min_edge/depth… | **M1β lockout-NO probe** (layered) |
| `no_arb_probe.jsonl` | ts, city, N, proxy_sum_no, real_sum_no, payoff_N_1, real_edge, n_legs_fillable, all_legs_fillable, min_leg_depth_usd, real_arb, legs | **NEG_RISK_ARB** opportunity probe |
| `obs_receipt.jsonl` | recv_ts, icao, source, obs_valid_ts, temp_c | **per-source obs receipt-time** (feed-lead measurement, Stage-0) |
| `dip_shadow.jsonl` | — | lockout dip-rebuy shadow |
| `ladder.jsonl` | — | ladder fills |

**Non-weather shadow streams in the same dirs** (crypto/other strategies, large): `binance_trade`,
`token_trade`, `market_timeline`, `ob_delta`, `gate_trace`, `hold_path`, `maker_flow`,
`maker_shadow`, `fade_shadow`, `exit_policy_shadow`, `discover_signal`, `window_resolution`
(crypto 5m up/down), `shadow_telemetry`, `order_lifecycle`. Ignore for weather work.

---

## 4. Weather process logs — `logs/weather/`
| File | What it is |
|---|---|
| `forecast_actuals.jsonl` (17MB) | event, slug, city_slug, valid_day, month, **model_values, ensemble_mu, ensemble_sigma**, ts_utc — forecast-vs-actual record, the main calibration feed |
| `forecast_actuals_gamma.jsonl` | same joined against Gamma resolution |
| `hot_bust_observations.jsonl` | date, city, month, gfs_d1, actual, error — daily GFS-d1 bust observations |
| `resolved.log` / `audit.log` / `refresh.log` / `regime.log` / `isotonic_refit.log` / `hot_bust.log` | cron stdout for the 6 daily jobs (see §6) |
| `daily_summary_<date>.json` | per-day rollup |

Other top-level weather streams in `logs/`:
- `logs/shadow/flb_screener.jsonl` (35MB) + `logs/flb_screener.out` — favorite-longshot-bias screener.
- `logs/shadow/met_adjustments.jsonl` — ts, city, icao, marine, cirrus, latent_heat, mu_baseline, mu_final, total_delta (meteorological μ-adjustments).
- `logs/shadow/tail_resolver.jsonl` — overdue-market tail resolver scores.
- `logs/m1_beta_probe_state.json` — M1β probe persistent counters.

---

## 5. Resolution & trade data (realized PnL)
- `logs/trades.jsonl` (23MB) — **STWA fills appear ONLY at resolution**, tagged `WEATHER_STWA`
  (also `WEATHER_FAVYES`, lockout tags). At fill they live in `risk.open_positions` /
  `logs/positions.json`. Schema/gotchas: use the **`trades-query` skill** before querying.
  Backups: `trades.jsonl.bak_weather`, `.bak`.
- `logs/bankroll.json` — **NOT authoritative** (user sells manually; bot can't see it). Never
  conclude PnL/ruin from it alone.
- Resolution oracle join: `analytics/backfill_weather_resolution.py`,
  `analysis/weather/lockout_resolution_join.py`, `reconcile_actuals_gamma.py`. Gamma UMA
  `closed=true` = truth.

---

## 6. Cron jobs (the production pipeline) — `crontab -l`
| Time (UTC) | Job | Produces |
|---|---|---|
| 06:00 | `analysis.weather.regime_detection` | `strategy/regime_today.json` → `logs/weather/regime.log` |
| 08:30 | `analysis.weather.daily_audit` | `logs/weather/audit.log`, `audit_report.md` |
| 09:00 | `analysis.weather.refresh_skill_matrix --mode live` | `strategy/skill_matrix.json` → `refresh.log` |
| 09:30 | `analysis.weather.stwa_isotonic_live_refit` | `config/stwa_isotonic_candidate.json` (guarded promote) → `isotonic_refit.log` |
| 10:00 | `analysis.weather.build_hot_bust_table --mode append` | `strategy/hot_bust_rates.json`, `hot_bust_observations.jsonl` → `hot_bust.log` |
| 12:00 | `analysis.weather.resolved_feedback` | resolution feedback → `resolved.log` |
| 04:00 | `ops/prune_shadow_logs.sh` (KEEP_DAYS=10) | prunes `logs/shadow/hot/*` |

---

## 7. Analysis / tooling layer (consumers — what to run, not data)
`analysis/weather/` (~110 scripts). Key clusters:
- **Calibration/pricing:** `stwa_pricer_backtest.py`, `stwa_intraday_value.py` (β head-to-head),
  `stwa_isotonic_calib.py` / `_live_refit.py` / `_live_join.py`, `nowcast_sigma.py`,
  `stwa_sigma_collapse_backtest.py`, `forward_calibration.py`, `emos_recal.py`, `calib_verify.py`.
- **Skill matrix build:** `build_skill_matrix.py`, `refresh_skill_matrix.py`,
  `add_ai_models_to_matrix.py`, `add_climatology.py`, `add_nasa_power_to_matrix.py`,
  `compare_ensemble_accuracy.py`, `skill_scorecard.py`.
- **Lockout/M1β:** `lockout_capacity.py`, `lockout_resolution_join.py`, `lockout_reliability.py`,
  `lockout_staleness.py`, `lockout_exec_backtest.py`, `m1_beta_probe_report.py`,
  `m1_layer_ev_curves.py`, `m1_live_resolution.py`, `m1_sf_forensic.py`.
- **Arb/NO:** `no_arb_probe_summary.py`, `no_ladder_test.py`, `model_no_scorecard.py`,
  `favorite_ev.py`, `role_misprice.py`.
- **Regime/forecast:** `regime_detection.py` (cron), `build_peak_monthly.py`,
  `peak_calib_monthly.py`, `diurnal_analysis.py`, `thermo_ev.py`, `thermo_nowcast.py`,
  `metar_nowcast_reliability.py`, `peak_hour_validate.py`.
- **Feeds/oracle:** `feed_lead_measure.py`, `wis2_debug.py`, `noaa_scraper.py`,
  `wu_high_scraper.py`, `wu_monitor.py`, `oracle_calibration.py`, `oracle_backtest.py`,
  `build_station_map.py`, `stations.py`, `city_correlations.py`.
- **Falsified dead-ends (do NOT rebuild):** `taker_*` (fade-takers), `mm_*` (MM-fingerprint),
  `maker_backtest.py` (maker MVP) — all falsified 2026-05-29.
- `analytics/`: `stwa_fetch_data.py`, `stwa_fit_params.py`, `backfill_nwp_gfs_global.py`,
  `backfill_weather_resolution.py`, `regime.py`, `weather_scan_now.py`.

---

## 8. Provenance gotchas (read before drawing conclusions)
1. **Oracle = hourly METAR/SPECI only** (`official_running_max_c` from {AWC, NWS}). Sub-hourly
   ASOS spikes cause **false lockouts** (the M1β / P3 bugs). `running_max` is monotone,
   official-floored, never reset by a decreasing NWP feed.
2. **Live trades → shadow logs, not `trades.jsonl`** (which only fills at resolution). Use the
   `trades-query` skill.
3. **Only NEG_RISK_ARB is calibration-independent.** YES/NO edge rides on the isotonic map
   holding on live 2026 resolution — provisional until n≥100 per bucket.
4. **n≥100 per city/bucket to conclude edge.** n=40–99 = trend-only flag. n<40 = collection mode.
5. **Local time always** for peaks/diurnal (`Station.tz`).
6. **Bankroll.json is not authoritative** (manual sells).
7. **σ-collapse is OFF** (2026-06-06); isotonic map re-aligned to flat-σ. **YES is DISABLED**;
   live paths = NEG_RISK_ARB + engine model-NO + M1β lockout-NO. Trust `stwa_engine.py` over
   the CLAUDE.md params table if they disagree.
8. Block oracle-mismatch cities for lockout: {VHHH/Hong Kong, RJTT, ZGSZ, WSSS}.

---

## 9. Quick-reference: "where does X live?"
| I need… | Look at |
|---|---|
| What the model believed about a bucket | `stwa_pricer_eval.jsonl` (p_mc/gev/pa/ps/cal) |
| What we actually bought | `stwa_signals.jsonl` + `risk.open_positions` |
| Engine internal state (Kalman, regime) | `stwa_state.jsonl` + `data/stwa_kalman_state.npz` |
| Forecast vs actual (calibration) | `logs/weather/forecast_actuals.jsonl` |
| Per-(city,model) skill | `strategy/skill_matrix.json` |
| Today's regime / μ / σ | `strategy/regime_today.json` |
| Lockout-NO opportunities | `metar_lockout.jsonl`, `m1_beta_probe.jsonl` |
| Arb opportunities | `no_arb_probe.jsonl` |
| Feed latency / who's fastest | `obs_receipt.jsonl` |
| Fitted (κ,γ,σ) + spatial cov | `config/stwa_params.json` |
| Isotonic recal map | `config/stwa_isotonic.json` |
| Realized PnL (at resolution) | `logs/trades.jsonl` (WEATHER_STWA), via `trades-query` skill |
| Raw ASOS/NWP history | `data/stwa_asos.parquet`, `data/stwa_nwp*.parquet` |
