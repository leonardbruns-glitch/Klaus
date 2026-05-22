# VOLARB Quantitative Audit — 2026-05-22 18:10 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-22T18:03:29Z (≈7 min old — FRESH) |
| Klaus state | active (systemd: active; running CAS_LOWASK/weather, 0 open positions) |
| Capital | $32.34 (prior audit 2026-05-21 12:10 UTC: $68.07 → **−$35.73 Δ** — CAS_LOWASK drawdown, not VOLARB) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — zero new VOLARB trades; last trade 2026-05-19T02:50:33Z, **87h+ retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m total VOLARB operation — CLOSED) |
| Open audit PRs | NONE (GitHub MCP confirmed) |
| Run | **6th consecutive audit** with Δ=0 new trades |

**STRATEGY STATUS: RETIRED.** VOLARB entries disabled 2026-05-17 19:56 UTC (CAS_LOWASK launched).
Formally retired 2026-05-19 (`volarb_strategy=None`, import removed, CLAUDE.md rewritten).
All 885 trades are historical. No parameter change to `strategy/volarb.py` has operational effect.

**CODE MISMATCH NOTE (6th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15`
(prescribing raise 0.15→0.17). Actual code: `EDGE_FLOOR_DEFAULT=0.10`, `EDGE_FLOOR_BY_ASSET
={"BTC":0.10,"ETH":0.10,"SOL":0.10}` — set by explicit user instruction 2026-05-17 10:20 UTC
(state_log). Raising to 0.17 from 0.10 = +70% change, violates ±20% Tier 1 ceiling, and
contradicts an explicit user directive.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (≈7 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($32.34) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Open `audit/volarb-*` PRs | NONE (GitHub MCP confirmed) |
| STALE_MIRROR | NO |
| BOT_DOWN | NO (active; running CAS_LOWASK/weather) |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-05-22T12:03Z .. 2026-05-22T18:03Z
**VOLARB trades in window: 0** (strategy retired 87h+ ago; last trade 2026-05-19T02:50:33Z)

No cells to report.

---

## Full-Window Cell Scan (2026-05-16T21:00Z .. 2026-05-19T02:50Z)

Dataset CLOSED. n=885 unchanged since 2026-05-19T02:50:33Z. All values identical to prior audit.

### Overall

| metric | value | backtest baseline ($1-equiv) | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | 51.7% (backtest OOS) | WELL BELOW |
| PF | 1.061 | — | — |
| net_sum | +$54.69 | — | — |
| EV/trade | +$0.062 | CI=[+$0.244, +$0.352] | BELOW CI lower |
| CI95 | [−$0.084, +$0.210] | [+$0.244, +$0.352] | ranges do not overlap |

*kline_pnl cross-check (n=874 resolved): WR=31.7%, EV=−$0.031/trade — net_pnl overstates performance.*

### Per-Asset

| dimension | cell | n | WR | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9% | 1.085 | +$23.74 | +$0.083 | [−$0.177, +$0.359] | BELOW lower (+$0.244) | BELOW_CI |
| asset | ETH | 305 | 32.5% | 0.966 | −$10.78 | −$0.035 | [−$0.300, +$0.234] | BELOW lower (+$0.244) | BELOW_CI |
| asset | SOL | 294 | 38.8% | 1.140 | +$41.74 | +$0.142 | [−$0.126, +$0.405] | BELOW lower (+$0.244) | BELOW_CI |

All three assets BELOW_CI at n≥100. Promotion moot — strategy retired.

### Per-Hour-UTC (full VOLARB window)

| H | n | WR | PF | sum | EV/trade | CI95 | status |
|---|---|---|---|---|---|---|---|
| H00 | 39 | 35.9% | 1.360 | +$12.46 | +$0.320 | [−$0.425, +$1.062] | COLLECT (n<40) |
| H01 | 66 | 48.5% | 1.953 | +$51.76 | +$0.784 | [+$0.163, +$1.386] | WATCHLIST |
| H02 | 64 | 40.6% | 1.185 | +$12.56 | +$0.196 | [−$0.391, +$0.780] | WATCHLIST |
| H03 | 36 | 44.4% | 1.374 | +$13.38 | +$0.372 | [−$0.414, +$1.172] | COLLECT |
| H04 | 37 | 32.4% | 0.873 | −$5.42 | −$0.147 | [−$0.856, +$0.611] | COLLECT |
| H05 | 35 | 14.3% | 0.359 | −$30.13 | −$0.861 | [−$1.406, −$0.214] | COLLECT (n<40; CI upper<0) |
| H06 | 35 | 31.4% | 1.020 | +$0.72 | +$0.021 | [−$0.693, +$0.898] | COLLECT |
| H07 | 31 | 19.4% | 0.616 | −$13.60 | −$0.439 | [−$1.100, +$0.305] | COLLECT |
| H08 | 35 | 28.6% | 1.498 | +$14.30 | +$0.409 | [−$0.387, +$1.253] | COLLECT |
| H09 | 28 | 14.3% | 0.438 | −$15.75 | −$0.563 | [−$1.071, +$0.052] | COLLECT |
| H10 | 38 | 34.2% | 1.162 | +$5.34 | +$0.141 | [−$0.531, +$0.807] | COLLECT |
| H11 | 71 | 35.2% | 1.196 | +$13.53 | +$0.191 | [−$0.369, +$0.785] | WATCHLIST |
| H12 | 36 | 36.1% | 0.970 | −$1.20 | −$0.033 | [−$0.750, +$0.690] | COLLECT |
| H13 | 36 | 33.3% | 1.022 | +$0.83 | +$0.023 | [−$0.736, +$0.788] | COLLECT |
| H14 | 47 | 29.8% | 0.894 | −$5.05 | −$0.108 | [−$0.647, +$0.539] | WATCHLIST (neg drift) |
| H15 | 36 | 30.6% | 0.898 | −$4.45 | −$0.124 | [−$0.926, +$0.703] | COLLECT |
| H16 | 30 | 16.7% | 0.428 | −$21.46 | −$0.715 | [−$1.273, −$0.052] | COLLECT (n<40; CI upper<0) |
| H17 | 21 | 38.1% | 0.752 | −$8.14 | −$0.388 | [−$2.164, +$1.047] | COLLECT |
| H18 | 25 | 60.0% | 1.406 | +$7.53 | +$0.301 | [−$0.508, +$1.080] | COLLECT |
| H20 | 3 | 100.0% | inf | +$9.05 | +$3.016 | N/A | COLLECT (n<40) |
| H21 | 39 | 51.3% | 1.873 | +$23.67 | +$0.607 | [−$0.051, +$1.292] | COLLECT |
| H22 | 40 | 32.5% | 0.872 | −$5.48 | −$0.137 | [−$0.790, +$0.503] | WATCHLIST (neg drift) |
| H23 | 57 | 33.3% | 1.004 | +$0.24 | +$0.004 | [−$0.570, +$0.613] | WATCHLIST |

### Per-Ask-Band

| band | n | WR | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| [0.00, 0.10) | 10 | 0.0% | 0.000 | −$9.11 | −$0.911 | [−$1.093, −$0.742] | BELOW_CI_NEG | COLLECT (n<40) |
| [0.10, 0.20) | 91 | 18.7% | 1.197 | +$13.60 | +$0.149 | [−$0.312, +$0.665] | BELOW CI lower | WATCHLIST |
| [0.20, 0.30) | 227 | 26.4% | 0.997 | −$0.73 | −$0.003 | [−$0.275, +$0.264] | BELOW CI lower | BELOW_CI |
| [0.30, 0.40) | 390 | 38.7% | 1.115 | +$46.99 | +$0.121 | [−$0.128, +$0.350] | BELOW CI lower | BELOW_CI |
| [0.40, 0.50) | 157 | 47.1% | 1.075 | +$13.38 | +$0.085 | [−$0.294, +$0.466] | BELOW CI lower | BELOW_CI |
| [0.50, 0.60) | 8 | 50.0% | 0.881 | −$1.25 | −$0.157 | [−$1.991, +$1.690] | — | COLLECT (n<40) |

Pattern: live WR rises monotonically with ask (0%→19%→27%→39%→47%) while model confidence
inversely predicts outcome — consistent with anti-calibration / r≈0 diagnosis (state_log
2026-05-17 12:30). Dataset is closed; this pattern will not resolve.

---

## Lever Probes

| lever | probe cell | n | EV | CI95 | lever_candidate | blocker |
|---|---|---|---|---|---|---|
| ASK_CEIL lower (0.60→0.55) | [0.50, 0.60) | 8 | −$0.157 | [−$1.991, +$1.690] | NO | n=8 << 100 |
| REM_MAX_S lower (280→260) | [260, 280)s hold_proxy | 100 | +$0.452 | [+$0.032, +$0.905] | NO | EV > 0, CI lower > 0 — positive cell; no case to lower ceiling |
| REM_MIN_S raise (60→80) | [60, 80)s hold_proxy | 2 | +$0.766 | N/A | NO | n=2 << 100 |
| ASK_DEPTH_MULT raise | adverse-selection check | 885 | — | — | NO | `slippage_entry`=0.0 for 100% of records; no adverse-selection signal |

**REM field note:** `term_remaining_s` = 0.0 for all 885 records (VOLARB never logged
rem-at-entry; this is an LDA/SNIPER schema field). REM probes use `hold_seconds` (actual
hold duration, range 3.8–367.5s, median 275.6s) as a proxy under hold-to-resolution
assumption. For TP20 exits (n=267, 30.2% of trades), `hold_seconds` understates actual
rem-at-entry. Proxy is structurally limited; REM probe n-counts are unreliable.

---

## Proposed Patch

**NO PATCH.**

### EDGE_FLOOR raise — conditions technically met, two independent hard blockers

Conditions: n=885 ≥ 200 ✓ | EV=+$0.062 < +$0.10 ✓ | PF=1.061 < 1.10 ✓ | CI95_lower=−$0.084 < 0 ✓

**Blocker 1 — Strategy retired.** `strategy/volarb.py` is dead code: VOLARB object removed
2026-05-19 (`volarb_strategy=None`); `schedule_if_ready` never called from `main.py`. Any
constant edit has zero operational effect. A patch PR to dead code is noise.

**Blocker 2 — Prescribed value is incoherent.** "0.15→0.17" targets a stale constant.
Actual code: `EDGE_FLOOR_DEFAULT=0.10` (set by explicit user instruction 2026-05-17 10:20
UTC, state_log). Raising 0.10→0.17 = +70% — violates ±20% Tier 1 ceiling and contradicts
an explicit user directive. This is the **6th consecutive audit cycle** flagging this mismatch.

No other lever probe clears n≥100 with negative EV and CI95 upper < 0. Stack ranking is vacuous.

---

## Watchlist (40≤n<100; informational — strategy retired, frozen at n=885)

| dimension | cell | n | WR | EV/trade | CI95 | Δ vs prior | note |
|---|---|---|---|---|---|---|---|
| hour | H01 | 66 | 48.5% | +$0.784 | [+$0.163, +$1.386] | 0 | only VOLARB hour with CI lower > 0; frozen |
| hour | H02 | 64 | 40.6% | +$0.196 | [−$0.391, +$0.780] | 0 | weakly positive; frozen |
| hour | H11 | 71 | 35.2% | +$0.191 | [−$0.369, +$0.785] | 0 | mixed; frozen |
| hour | H14 | 47 | 29.8% | −$0.108 | [−$0.647, +$0.539] | 0 | trending negative; frozen |
| hour | H22 | 40 | 32.5% | −$0.137 | [−$0.790, +$0.503] | 0 | trending negative; frozen |
| hour | H23 | 57 | 33.3% | +$0.004 | [−$0.570, +$0.613] | 0 | flat; frozen |
| ask | [0.10,0.20) | 91 | 18.7% | +$0.149 | [−$0.312, +$0.665] | 0 | below baseline; frozen |

All cells frozen at Δ=0 since 2026-05-19T02:50Z. Will never reach n≥100 while strategy is retired.

---

## Skipped — User Override (state_log)

| override | date | effect on this audit |
|---|---|---|
| `EDGE_FLOOR_DEFAULT=0.10` user instruction | 2026-05-17 10:20 UTC | EDGE_FLOOR raise prescription (0.15→0.17) does not apply to actual code value |
| VOLARB disabled user instruction | 2026-05-17 19:56 UTC | All parameter edits to `strategy/volarb.py` are inert |
| VOLARB `volarb_strategy=None` user instruction | 2026-05-19 | Strategy object removed; code path unreachable |

---

## Meta-note for prompt maintainer

The VOLARB Quantitative Auditor prompt references `EDGE_FLOOR=0.15` as "current" and
prescribes a raise to 0.17. This has been stale since 2026-05-17 10:20 UTC (~5 days).
VOLARB has been fully retired since 2026-05-17 19:56 UTC with zero new trades for 87+ hours.
This is the **6th consecutive** NO PATCH audit with Δ=0 new trades. The VOLARB dataset is
**closed** (n=885 final). Running this agent against frozen, retired data generates noise
without operational value. Recommend retiring or pausing this scheduled agent until VOLARB
is reactivated, or retargeting it to the active strategy (CAS_LOWASK / weather arb).
