# VOLARB Quantitative Audit — 2026-06-08 06:13 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-06-08T05:56:07Z (17.6 min old — FRESH) |
| Klaus state | active (systemd: active; running STWA/weather, 0 open positions) |
| Capital | $51.06 (prior audit 2026-06-07T06:11Z: $60.95; Δ=**−$9.89** — STWA weather losses) |
| VOLARB n (live era, post-dedup) | **885** (prior: 885, Δ=**0** — 20th consecutive audit with zero new unique trades; last unique trade 2026-05-19T02:50:33Z, ~603h retired) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE (confirmed via GitHub MCP) |
| Run | **20th consecutive audit** with Δ=0 new unique trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten.
- 2026-05-29: CLAUDE.md fully reoriented to STWA. No crypto running.
- **Any parameter change to `strategy/volarb.py` has zero operational effect.** VPS does not run it.
- `term_remaining_s = 0.0` for all 885 trades; REM probes (REM_MIN_S, REM_MAX_S) cannot be computed.
- EDGE_FLOOR on dev branch is `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}` (per-asset dict), not scalar 0.15; the audit prompt's `0.15 → 0.17` raise is structurally inapplicable.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤ 45 min | PASS (17.6 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($51.06) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-06-08T00:13Z .. 2026-06-08T06:13Z
**VOLARB trades in window: 0** (strategy retired ~603h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (first-fire dedup per `(asset, round(ts_open))`). Δ vs prior audit = 0.
Backtest $1-equiv baseline CI = [+$0.244, +$0.352].

### Overall

| metric | value | backtest $1-equiv | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51.7% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 mid | **BELOW CI lower (+$0.244)** |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.093, +$0.217] | [+$0.244, +$0.352] | **STRADDLES ZERO / BELOW BASELINE** |

**EDGE_FLOOR raise criteria check** (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):
- n≥200 = YES (885) · EV<+$0.10 = YES (+$0.062) · PF<1.10 = YES (1.061) · CI_lo<0 = YES (−$0.093)
- → All 4 criteria technically met. **SUPPRESSED** — two grounds:
  1. Strategy RETIRED on VPS since 2026-05-19: any edit to `strategy/volarb.py` has zero operational effect.
  2. EDGE_FLOOR is a per-asset dict on dev branch (`EDGE_FLOOR_BY_ASSET`), not a scalar; the scalar `0.15→0.17` raise specified in the audit prompt is inapplicable as written.

### Per-Asset (all n≥100)

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9 | 1.085 | +$23.74 | +$0.083 | [−$0.175, +$0.348] | BELOW CI lower; CI straddles 0 | WATCHLIST |
| asset | ETH | 305 | 32.5 | 0.966 | −$10.78 | −$0.035 | [−$0.294, +$0.223] | BELOW CI lower; PF<1.0; CI straddles 0 | WATCHLIST |
| asset | SOL | 294 | 38.8 | 1.140 | +$41.74 | +$0.142 | [−$0.125, +$0.410] | BELOW CI lower; CI straddles 0 | WATCHLIST |

No per-asset cell meets lever criteria (require CI_upper < 0; all three straddle zero).

### Per-Hour UTC (watchlist cells 40≤n<100 only; n<40 = COLLECTING omitted)

| H | n | WR% | EV/trade | CI95 | status |
|---|---|---|---|---|---|
| H01 | 66 | 48.5 | +$0.784 | [+$0.174, +$1.415] | WATCHLIST (positive — above baseline CI lower) |
| H02 | 64 | 40.6 | +$0.196 | [−$0.360, +$0.796] | WATCHLIST |
| H11 | 71 | 35.2 | +$0.191 | [−$0.356, +$0.743] | WATCHLIST |
| H14 | 47 | 29.8 | −$0.107 | [−$0.694, +$0.492] | WATCHLIST (negative) |
| H22 | 40 | 32.5 | −$0.137 | [−$0.768, +$0.540] | WATCHLIST (negative) |
| H23 | 57 | 33.3 | +$0.004 | [−$0.553, +$0.597] | WATCHLIST |

No per-hour cell meets lever criteria at n<100 (threshold n≥100 required).

### Per-Ask-Band

| band | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| [0.10,0.20) | 91 | 18.7 | 1.197 | +$13.60 | +$0.149 | [−$0.308, +$0.661] | BELOW CI lower | WATCHLIST |
| [0.20,0.30) | 227 | 26.4 | 0.997 | −$0.73 | −$0.003 | [−$0.276, +$0.274] | BELOW CI lower; PF<1.0 | WATCHLIST (n≥100, CI straddles 0) |
| [0.30,0.40) | 390 | 38.7 | 1.115 | +$46.99 | +$0.120 | [−$0.108, +$0.355] | BELOW CI lower | WATCHLIST (n≥100, CI straddles 0) |
| [0.40,0.50) | 157 | 47.1 | 1.075 | +$13.38 | +$0.085 | [−$0.281, +$0.474] | BELOW CI lower | WATCHLIST (n≥100, CI straddles 0) |
| [0.50,0.60) | 8 | 50.0 | 0.881 | −$1.25 | −$0.157 | [−$1.991, +$1.684] | BELOW CI lower | COLLECTING (n<40) |

---

## Lever Probes

- **ASK_CEIL probe [0.50,0.60):** n=8, EV=−$0.157, CI=[−$1.991, +$1.684] → NOT_LEVER (n=8 << 100 required; CI wide and straddles zero)
- **REM_MAX_S probe [260,280):** n=0 — `term_remaining_s=0.0` for all 885 trades; REM field was not persisted in this data era. Probe inoperable on this dataset. NOT_LEVER.
- **REM_MIN_S probe [60,80):** n=0 — same reason. NOT_LEVER.
- **ASK_DEPTH_MULT probe:** no adverse-selection slippage field in this era's schema; n<200 required. NOT_LEVER.

---

## Proposed Patch (capped at 1)

**no patch**

All four patch conditions fail or are suppressed:
1. EDGE_FLOOR raise (0.15→0.17): criteria technically met (n=885, EV=+$0.062, PF=1.061, CI_lo=−$0.093) but **suppressed** — strategy RETIRED on VPS + EDGE_FLOOR is per-asset dict (not scalar 0.15).
2. ASK_CEIL lower (0.60→0.55): n=8 in [0.50,0.60) << 100 required.
3. REM_MAX_S lower (280→260): n=0 in [260,280) — field not persisted in this era.
4. REM_MIN_S raise (60→80): n=0 in [60,80) — field not persisted in this era.
5. ASK_DEPTH_MULT raise: no slippage evidence + n=885 overall EV>0.

---

## Watchlist (40≤n<100, delta vs prior 2026-06-07T06:11Z)

| cell | n | EV/trade | CI95 | delta vs prior |
|---|---|---|---|---|
| asset: BTC | 286 | +$0.083 | [−$0.175, +$0.348] | Δ=0 |
| asset: ETH | 305 | −$0.035 | [−$0.294, +$0.223] | Δ=0 |
| asset: SOL | 294 | +$0.142 | [−$0.125, +$0.410] | Δ=0 |
| ask [0.10,0.20) | 91 | +$0.149 | [−$0.308, +$0.661] | Δ=0 |
| H01 | 66 | +$0.784 | [+$0.174, +$1.415] | Δ=0 |
| H02 | 64 | +$0.196 | [−$0.360, +$0.796] | Δ=0 |
| H11 | 71 | +$0.191 | [−$0.356, +$0.743] | Δ=0 |
| H14 | 47 | −$0.107 | [−$0.694, +$0.492] | Δ=0 |
| H22 | 40 | −$0.137 | [−$0.768, +$0.540] | Δ=0 |
| H23 | 57 | +$0.004 | [−$0.553, +$0.597] | Δ=0 |

All Δ=0. Dataset is permanently frozen at n=885. Watchlist cells will never graduate to n≥100.

---

## Skipped — User Override (state_log)

No cells marked as user-overridden for VOLARB.

---

## Note for User

The VOLARB audit mandate is fully exhausted. Dataset frozen at n=885; strategy retired ~603h ago. **Recommend decommissioning this scheduled audit.** No further actionable signal exists; running it every 6h generates only noise commits.
