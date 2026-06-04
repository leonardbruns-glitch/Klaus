# VOLARB Quantitative Audit — 2026-06-04 06:12 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-04T06:08:13Z (4 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $54.99 (prior audit 2026-06-03T06:12Z: $55.91; Δ=−$0.92 — STWA losses, no VOLARB PnL) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — 17th consecutive audit with zero new unique trades; last unique trade 2026-05-19T02:50:33Z, ~385h retired) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **17th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten to CAS_LOWASK.
- 2026-05-29: CLAUDE.md fully reoriented to STWA (weather arb). No crypto at all.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not run it.
- Dev branch has `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` + `EDGE_FLOOR_DEFAULT=0.10` (per-asset dict, per user instruction 2026-05-17 10:20 UTC). Audit prompt's scalar `EDGE_FLOOR=0.15 → 0.17` is inapplicable as specified.
- `term_remaining_s` = 0.0 for all 885 trades; REM probes cannot be computed from this dataset.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (4 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($54.99) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-04T00:08Z .. 2026-06-04T06:08Z
**VOLARB trades in window: 0** (strategy retired ~385h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (first-fire dedup per `(asset, round(ts_open))`).
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | backtest $1-equiv | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51.7% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 mid | **BELOW CI lower (+$0.244)** |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.097, +$0.219] | [+$0.244, +$0.352] | **STRADDLES ZERO / BELOW BASELINE** |

**EDGE_FLOOR raise criteria check** (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):
- n≥200 = YES (885) · EV<+$0.10 = YES (+$0.062) · PF<1.10 = YES (1.061) · CI_lo<0 = YES (−$0.097)
- → All 4 criteria technically met. **SUPPRESSED — (1) strategy RETIRED, zero operational effect; (2) EDGE_FLOOR is per-asset dict on dev branch, 0.15→0.17 raise inapplicable as specified.**

### Per-Asset (all n≥100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.175, +$0.348] | BELOW CI lower (+$0.244) | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.294, +$0.232] | BELOW CI lower (+$0.244) | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.413] | BELOW CI lower (+$0.244) | WATCHLIST |

### Per-Hour UTC (all n<100 → all COLLECTING)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| hour | h=00 | 39 | 35.9 | 1.360 | +$12.46 | +$0.320 | [−$0.412, +$1.098] | n<100 | COLLECTING |
| hour | h=01 | 66 | 48.5 | 1.953 | +$51.76 | +$0.784 | [+$0.174, +$1.413] | n<100 | COLLECTING |
| hour | h=02 | 64 | 40.6 | 1.185 | +$12.56 | +$0.196 | [−$0.384, +$0.807] | n<100 | COLLECTING |
| hour | h=03 | 36 | 44.4 | 1.374 | +$13.38 | +$0.372 | [−$0.424, +$1.146] | n<100 | COLLECTING |
| hour | h=04 | 37 | 32.4 | 0.873 | −$5.42 | −$0.147 | [−$0.880, +$0.611] | n<100 | COLLECTING |
| hour | h=05 | 35 | 14.3 | 0.359 | −$30.13 | −$0.861 | [−$1.391, −$0.225] | n<100 | COLLECTING (notable: CI95 fully negative) |
| hour | h=06 | 35 | 31.4 | 1.020 | +$0.72 | +$0.021 | [−$0.709, +$0.810] | n<100 | COLLECTING |
| hour | h=07 | 31 | 19.4 | 0.616 | −$13.60 | −$0.439 | [−$1.090, +$0.335] | n<100 | COLLECTING |
| hour | h=08 | 35 | 28.6 | 1.498 | +$14.30 | +$0.409 | [−$0.395, +$1.306] | n<100 | COLLECTING |
| hour | h=09 | 28 | 14.3 | 0.438 | −$15.75 | −$0.563 | [−$1.092, +$0.071] | n<100 | COLLECTING |
| hour | h=10 | 38 | 34.2 | 1.162 | +$5.34 | +$0.141 | [−$0.503, +$0.828] | n<100 | COLLECTING |
| hour | h=11 | 71 | 35.2 | 1.196 | +$13.53 | +$0.191 | [−$0.352, +$0.754] | n<100 | COLLECTING |
| hour | h=12 | 36 | 36.1 | 0.970 | −$1.20 | −$0.033 | [−$0.742, +$0.765] | n<100 | COLLECTING |
| hour | h=13 | 36 | 33.3 | 1.022 | +$0.83 | +$0.023 | [−$0.704, +$0.782] | n<100 | COLLECTING |
| hour | h=14 | 47 | 29.8 | 0.894 | −$5.05 | −$0.108 | [−$0.683, +$0.508] | n<100 | COLLECTING |
| hour | h=15 | 36 | 30.6 | 0.898 | −$4.45 | −$0.124 | [−$0.900, +$0.726] | n<100 | COLLECTING |
| hour | h=16 | 30 | 16.7 | 0.428 | −$21.46 | −$0.715 | [−$1.297, −$0.032] | n<100 | COLLECTING (notable: CI95 upper <0) |
| hour | h=17 | 21 | 38.1 | 0.752 | −$8.14 | −$0.388 | [−$2.034, +$1.025] | n<100 | COLLECTING |
| hour | h=18 | 25 | 60.0 | 1.406 | +$7.53 | +$0.301 | [−$0.495, +$1.117] | n<100 | COLLECTING |
| hour | h=20 | 3 | 100.0 | inf | +$9.05 | +$3.016 | [+$2.966, +$3.116] | n<100 | COLLECTING (n=3, ignore) |
| hour | h=21 | 39 | 51.3 | 1.873 | +$23.67 | +$0.607 | [−$0.053, +$1.255] | n<100 | COLLECTING |
| hour | h=22 | 40 | 32.5 | 0.872 | −$5.48 | −$0.137 | [−$0.779, +$0.545] | n<100 | COLLECTING |
| hour | h=23 | 57 | 33.3 | 1.004 | +$0.24 | +$0.004 | [−$0.576, +$0.586] | n<100 | COLLECTING |

### Per-Ask-Band

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| ask_band | [0.10,0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | [−$0.307, +$0.641] | n<100 | COLLECTING |
| ask_band | [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.281, +$0.276] | BELOW CI lower (+$0.244) | WATCHLIST |
| ask_band | [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.121 | [−$0.120, +$0.351] | BELOW CI lower (+$0.244) | WATCHLIST |
| ask_band | [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.284, +$0.475] | BELOW CI lower (+$0.244) | WATCHLIST |
| ask_band | [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$1.991, +$1.684] | n<100 | COLLECTING |

---

## Lever Probes

- **ASK_CEIL probe [0.50, 0.60):** n=8, WR=50.0%, EV=−$0.157, CI=[−$1.991, +$1.684] → **NOT_A_LEVER** (n<100; n=8 insufficient, CI massively wide)
- **REM_MAX_S probe [260, 280):** `term_remaining_s` uniformly 0 for all 885 trades — field not logged at entry time → **UNAVAILABLE**
- **REM_MIN_S probe [60, 80):** Same — `term_remaining_s` uniformly 0 → **UNAVAILABLE**
- **ASK_DEPTH_MULT probe:** No adverse-selection slippage evidence in dataset; `ob_depth_at_entry` field sparsely populated → **NOT_A_LEVER**

---

## Proposed Patch (capped at 1)

**no patch**

Rationale:
1. **Strategy RETIRED** — VOLARB disabled 2026-05-17 19:56 UTC; `volarb_strategy=None`, import removed. Bot runs STWA (weather arb). Any edit to `strategy/volarb.py` has zero operational effect.
2. **Lever type mismatch** — EDGE_FLOOR raise (0.15→0.17) is inapplicable: dev branch has per-asset dict `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` (user-instructed 2026-05-17 10:20 UTC), not a scalar constant.
3. **No other lever meets n≥100 threshold** — ASK_CEIL [0.50,0.60) n=8; REM probes unavailable; ASK_DEPTH_MULT no evidence.
4. **Dataset frozen** — n=885 for 17 consecutive audits. No new trades expected. 

---

## Watchlist (n≥40 cells trending negative, delta vs prior audit)

All entries stable (Δ=0 new trades since prior audit 2026-06-03T06:12Z):

| dimension | cell | n | EV/trade | CI95 | vs_prior_audit | note |
|---|---|---|---|---|---|---|
| asset | BTC | 286 | +$0.083 | [−$0.175, +$0.348] | unchanged | BELOW backtest CI lower (+$0.244); CI straddles zero |
| asset | ETH | 305 | −$0.035 | [−$0.294, +$0.232] | unchanged | BELOW zero; worst asset; CI fully spans loss |
| asset | SOL | 294 | +$0.142 | [−$0.125, +$0.413] | unchanged | Best asset but still BELOW CI lower |
| ask_band | [0.20,0.30) | 227 | −$0.003 | [−$0.281, +$0.276] | unchanged | Near-zero EV, CI straddles |
| ask_band | [0.30,0.40) | 390 | +$0.121 | [−$0.120, +$0.351] | unchanged | CI straddles zero |
| ask_band | [0.40,0.50) | 157 | +$0.085 | [−$0.284, +$0.475] | unchanged | CI straddles zero |
| hour | h=05 | 35 | −$0.861 | [−$1.391, −$0.225] | unchanged | CI95 fully negative — worst hour; n<100 |
| hour | h=16 | 30 | −$0.715 | [−$1.297, −$0.032] | unchanged | CI95 upper <0; n<100 |

*Notes: All per-asset/per-hour cells below CI lower are watchlist items only — no per-asset/per-hour block lever exists in Phase 1. Forward to user for review if strategy ever reactivated.*

---

## Skipped — User Override (state_log)

- Per-asset EDGE_FLOOR changes (dict structure) — user-instructed override 2026-05-17 10:20 UTC; audit prompt scalar definition inapplicable.
- No other state_log overrides relevant to VOLARB levers.

---

*Audit run: 2026-06-04 06:12 UTC | n=885 | Status: NO_PATCH — RETIRED | Δ vs prior: 0 new trades*
