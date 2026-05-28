# VOLARB Quantitative Audit — 2026-05-28 00:18 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-28T00:08:53Z (7.9 min old — FRESH) |
| Klaus state | active (systemd: active; running CAS_LOWASK/weather, 0 open positions) |
| Capital | $95.30 (unchanged from prior audit 2026-05-27 12:18 UTC — no VOLARB PnL) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — zero new VOLARB trades; last trade 2026-05-19T02:50:33Z, **~213h retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m CLOSED) |
| Open audit PRs | NONE |
| Run | **12th consecutive audit** with Δ=0 new trades |

**STRATEGY STATUS: RETIRED.**
- 2026-05-17 19:56 UTC: VOLARB entries disabled; CAS_LOWASK launched.
- 2026-05-19: `volarb_strategy=None`, import removed, CLAUDE.md rewritten to CAS_LOWASK.
- All 885 trades are historical. Any parameter change to `strategy/volarb.py` has zero operational effect.

**CODE MISMATCH NOTE (12th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15`.
Actual code: `EDGE_FLOOR_DEFAULT=0.10` (per-asset dict; no scalar `EDGE_FLOOR`), set by explicit user
instruction 2026-05-17 10:20 UTC (state_log). Prompt's "0.15 → 0.17 raise" is inapplicable.

**REM FIELD NOTE:** `term_remaining_s` is 0.0/None for all 885 VOLARB trades — field was not
populated in the VOLARB era. REM_MAX_S and REM_MIN_S lever probes: n=0 in both windows. No data.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (7.9 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($95.30) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Open `audit/volarb-*` PRs | NONE |
| STALE_MIRROR | NO |
| BOT_DOWN | NO |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-05-27T18:08Z .. 2026-05-28T00:08Z
**VOLARB trades in window: 0** (strategy retired ~213h ago; last trade 2026-05-19T02:50:33Z)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| — | 0 | — | — | — | no VOLARB trades in 6h window |

---

## Full-Window Cell Scan (data window: 2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 (first-fire dedup per `(asset, round(ts_open))`).
Backtest $1-equiv CI baseline = [+$0.244, +$0.352].

### Overall

| metric | value | backtest $1-equiv | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | ~51.7% | BELOW |
| PF | 1.061 | >1.3 | BELOW |
| EV/trade | +$0.062 | +$0.298 mid | BELOW CI lower |
| sum net_pnl | +$54.69 | — | — |
| CI95 EV/trade | [−$0.084, +$0.210] | [+$0.244, +$0.352] | CI STRADDLES ZERO |

**EDGE_FLOOR raise criteria check (n≥200 AND EV<+$0.10 AND PF<1.10 AND CI_lo<0):**
n≥200=YES(885) · EV<+$0.10=YES(+$0.062) · PF<1.10=YES(1.061) · CI_lo<0=YES(−$0.084)
→ All 4 criteria technically MET — suppressed: strategy RETIRED. Patch has zero operational effect.

### Per-Asset

| dimension | cell | n | WR% | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9% | 1.085 | +$23.74 | +$0.083 | [−$0.177, +$0.359] | BELOW CI lower | watchlist |
| asset | ETH | 305 | 32.5% | 0.966 | −$10.77 | −$0.035 | [−$0.300, +$0.234] | BELOW CI lower | watchlist |
| asset | SOL | 294 | 38.8% | 1.140 | +$41.72 | +$0.142 | [−$0.126, +$0.405] | BELOW CI lower | watchlist |

All three assets n≥100 with EV/trade below backtest CI lower (+$0.244). Watchlist only — strategy retired.

### Per-Hour UTC (n≥10 shown)

| dimension | cell | n | WR% | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|
| hour | H00 | 39 | 35.9% | +$0.320 | [−$0.425, +$1.062] | straddles zero | COLLECT |
| hour | H01 | 66 | 48.5% | +$0.784 | [+$0.163, +$1.386] | ABOVE CI upper | WL_PEND |
| hour | H02 | 64 | 40.6% | +$0.196 | [−$0.391, +$0.780] | straddles zero | WL_PEND |
| hour | H03 | 36 | 44.4% | +$0.372 | [−$0.414, +$1.172] | straddles zero | COLLECT |
| hour | H04 | 37 | 32.4% | −$0.147 | [−$0.856, +$0.611] | straddles zero | COLLECT |
| hour | H05 | 35 | 14.3% | −$0.861 | [−$1.406, −$0.214] | below zero | COLLECT |
| hour | H06 | 35 | 31.4% | +$0.021 | [−$0.693, +$0.898] | straddles zero | COLLECT |
| hour | H07 | 31 | 19.4% | −$0.439 | [−$1.100, +$0.305] | straddles zero | COLLECT |
| hour | H08 | 35 | 28.6% | +$0.409 | [−$0.387, +$1.253] | straddles zero | COLLECT |
| hour | H09 | 28 | 14.3% | −$0.563 | [−$1.071, +$0.052] | straddles zero | COLLECT |
| hour | H10 | 38 | 34.2% | +$0.141 | [−$0.531, +$0.807] | straddles zero | COLLECT |
| hour | H11 | 71 | 35.2% | +$0.191 | [−$0.369, +$0.785] | straddles zero | WL_PEND |
| hour | H12 | 36 | 36.1% | −$0.033 | [−$0.750, +$0.690] | straddles zero | COLLECT |
| hour | H13 | 36 | 33.3% | +$0.023 | [−$0.736, +$0.788] | straddles zero | COLLECT |
| hour | H14 | 47 | 29.8% | −$0.108 | [−$0.647, +$0.539] | straddles zero | WL_PEND |
| hour | H15 | 36 | 30.6% | −$0.124 | [−$0.926, +$0.703] | straddles zero | COLLECT |
| hour | H16 | 30 | 16.7% | −$0.715 | [−$1.273, −$0.052] | below zero | COLLECT |
| hour | H17 | 21 | 38.1% | −$0.388 | [−$2.164, +$1.047] | straddles zero | COLLECT |
| hour | H18 | 25 | 60.0% | +$0.301 | [−$0.508, +$1.080] | straddles zero | COLLECT |
| hour | H21 | 39 | 51.3% | +$0.607 | [−$0.051, +$1.292] | straddles zero | COLLECT |
| hour | H22 | 40 | 32.5% | −$0.137 | [−$0.790, +$0.503] | straddles zero | WL_PEND |
| hour | H23 | 57 | 33.3% | +$0.004 | [−$0.570, +$0.613] | straddles zero | WL_PEND |

No hour cell crossed n≥100. H01 shows CI=[+0.163,+1.386] clearing zero (n=66, WL_PEND). Moot: strategy retired.

### Per-Ask-Band

| dimension | cell | n | WR% | EV/trade | CI95 | sum | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| ask_band | [0.00,0.10) | 10 | 0.0% | −$0.911 | [−$1.093, −$0.742] | −$9.11 | below zero | COLLECT |
| ask_band | [0.10,0.20) | 91 | 18.7% | +$0.149 | [−$0.312, +$0.665] | +$13.60 | below CI lower | WL_PEND |
| ask_band | [0.20,0.30) | 227 | 26.4% | −$0.003 | [−$0.275, +$0.264] | −$0.73 | BELOW CI lower | WATCH |
| ask_band | [0.30,0.40) | 390 | 38.7% | +$0.121 | [−$0.128, +$0.350] | +$46.99 | BELOW CI lower | WATCH |
| ask_band | [0.40,0.50) | 157 | 47.1% | +$0.085 | [−$0.294, +$0.466] | +$13.38 | BELOW CI lower | WATCH |
| ask_band | [0.50,0.60) | 8 | 50.0% | −$0.157 | [−$1.991, +$1.690] | −$1.25 | straddles zero | COLLECT |

---

## Lever Probes

- **ASK_CEIL probe [0.50,0.60):** n=8, EV=−$0.157, CI95=[−$1.991, +$1.690]. NOT a lever candidate (n<100; n<40 = collect only).
- **REM_MAX_S probe [260,280):** n=0. `term_remaining_s` not populated in VOLARB era. No data — no action.
- **REM_MIN_S probe [60,80):** n=0. Same reason. No data — no action.
- **ASK_DEPTH_MULT probe:** No adverse-selection slippage field in VOLARB era schema. n<200 in all degrading cells. No action.

---

## Proposed Patch (capped at 1)

**no patch**

Rationale:
1. VOLARB strategy is RETIRED (`volarb_strategy=None` since 2026-05-19). Any edit to `strategy/volarb.py` has zero operational effect.
2. EDGE_FLOOR raise technically meets all 4 criteria (n=885≥200; EV=+$0.062<+$0.10; PF=1.061<1.10; CI_lo=−$0.084<0) but patching dead code is noise.
3. ASK_CEIL, REM_MAX_S, REM_MIN_S: all probes n=0 or n<100. No lever candidate.
4. No new trades since 2026-05-19T02:50:33Z (213.5h ago). Dataset is permanently frozen.

---

## Watchlist (40≤n<100; moot — dataset frozen, strategy retired)

| cell | n | EV | Δ vs prior | note |
|---|---|---|---|---|
| H01 | 66 | +$0.784 | unchanged | positive CI=[+0.163,+1.386]; best hour observed |
| H02 | 64 | +$0.196 | unchanged | neutral; CI straddles zero |
| H11 | 71 | +$0.191 | unchanged | neutral; CI straddles zero |
| H14 | 47 | −$0.108 | unchanged | mildly negative; CI straddles zero |
| H22 | 40 | −$0.137 | unchanged | mildly negative; CI straddles zero |
| H23 | 57 | +$0.004 | unchanged | flat; CI straddles zero |
| [0.10,0.20) | 91 | +$0.149 | unchanged | WL_PEND; CI straddles zero |

---

## Skipped — User Override (state_log)

None applicable. State_log overrides (H11 unblock 2026-05-19, CAS hour blocks) relate to CAS_LOWASK, not VOLARB.

---

## Delta vs Prior Audit (2026-05-27 12:18 UTC)

| metric | prior | current | Δ |
|---|---|---|---|
| n | 885 | 885 | 0 |
| WR | 34.7% | 34.7% | 0 |
| EV/trade | +$0.062 | +$0.062 | 0 |
| capital | $95.30 | $95.30 | 0 |
| patch | no patch | no patch | — |
| status | RETIRED | RETIRED | — |
