# VOLARB Quantitative Audit — 2026-05-20 18:11 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-20T18:08:11Z (2.9 min old — FRESH) |
| Klaus state | active (systemd: active, CAS_LOWASK sole strategy, 0 open positions) |
| Capital | $63.12 (prior audit 2026-05-20 12:14 UTC: $60.13 → **+$2.99 Δ** — CAS_LOWASK, not VOLARB) |
| VOLARB n (live era, deduped) | **885** (prior: 885, Δ=**0** — zero new VOLARB trades; last trade 2026-05-19T02:50:33Z, **39h+ retired**) |
| drift_status | OK — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Data window | 2026-05-16T21:00Z .. 2026-05-19T02:50Z (53h50m total VOLARB operation) |
| Open audit PRs | NONE |

**STRATEGY STATUS: RETIRED.** VOLARB entries disabled 2026-05-17 19:56 UTC (CAS_LOWASK launched).
Formally retired 2026-05-19 (`volarb_strategy=None`, import removed, CLAUDE.md rewritten).
All 885 trades are historical. No parameter change to `strategy/volarb.py` has operational effect.
This is the 4th consecutive audit of a retired strategy with Δ=0 new trades.

**CODE MISMATCH NOTE (4th consecutive occurrence):** Audit prompt assumes `EDGE_FLOOR=0.15`
(prescribing raise 0.15→0.17). Actual code: `EDGE_FLOOR_DEFAULT=0.10`, `EDGE_FLOOR_BY_ASSET
={"BTC":0.10,"ETH":0.10,"SOL":0.10}` — user-explicitly-set 2026-05-17 10:20 UTC (state_log).
Raising to 0.17 would contradict that instruction; raising to 0.17 from 0.10 is also >70%
change → well above ±20% Tier 1 ceiling → Tier 2 minimum. Prescription is incoherent.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (2.9 min) |
| `system_status.txt` contains `active` | PASS |
| `bankroll.json` capital non-zero | PASS ($63.12) |
| Code drift guard | PASS — data-mirror has no `strategy/volarb.py`; mirror-file-present condition N/A |
| Open `audit/volarb-*` PRs | NONE (GitHub MCP confirmed) |
| STALE_MIRROR | NO |
| BOT_DOWN | NO (active; running CAS_LOWASK) |
| DATA_CORRUPT | NO |

---

## 6h Recency Cells (n≥10)

Window: 2026-05-20T12:08Z .. 2026-05-20T18:08Z  
**VOLARB trades in window: 0** (strategy retired 39h+ ago; last trade 2026-05-19T02:50:33Z)

No cells to report.

---

## Full-Window Cell Scan (2026-05-16T21:00Z .. 2026-05-19T02:50Z)

### Overall

| metric | value | backtest baseline ($1-equiv) | vs baseline |
|---|---|---|---|
| n | 885 | — | — |
| WR | 34.7% | 51.7% (backtest) | WELL BELOW |
| PF | 1.061 | — | — |
| net_sum | +$54.69 | — | — |
| EV/trade | +$0.0618 | CI=[+$0.244, +$0.352] | BELOW CI lower |
| CI95 | [−$0.092, +$0.220] | [+$0.244, +$0.352] | ranges do not overlap |

### Per-Asset

| dimension | cell | n | WR | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|---|
| asset | BTC | 286 | 32.9% | 1.085 | +$23.74 | +$0.0830 | [−$0.178, +$0.356] | BELOW lower (+$0.244) | BELOW_CI |
| asset | ETH | 305 | 32.5% | 0.966 | −$10.78 | −$0.0353 | [−$0.292, +$0.231] | BELOW lower (+$0.244) | BELOW_CI |
| asset | SOL | 294 | 38.8% | 1.140 | +$41.74 | +$0.1420 | [−$0.136, +$0.419] | BELOW lower (+$0.244) | BELOW_CI |

All three assets BELOW_CI at n≥100. Promotion moot — strategy retired.

### Per-Hour-UTC

| H | n | WR | PF | sum | EV/trade | CI95 | status |
|---|---|---|---|---|---|---|---|
| H00 | 39 | 35.9% | 1.360 | +$12.46 | +$0.320 | [−$0.379, +$1.051] | COLLECT |
| H01 | 66 | 48.5% | 1.953 | +$51.76 | +$0.784 | [+$0.144, +$1.415] | WATCHLIST |
| H02 | 64 | 40.6% | 1.185 | +$12.56 | +$0.196 | [−$0.388, +$0.806] | WATCHLIST |
| H03 | 36 | 44.4% | 1.374 | +$13.38 | +$0.372 | [−$0.451, +$1.205] | COLLECT |
| H04 | 37 | 32.4% | 0.873 | −$5.42 | −$0.147 | [−$0.887, +$0.616] | COLLECT |
| H05 | 35 | 14.3% | 0.359 | −$30.13 | −$0.861 | [−$1.400, −$0.245] | COLLECT |
| H06 | 35 | 31.4% | 1.020 | +$0.72 | +$0.021 | [−$0.698, +$0.801] | COLLECT |
| H07 | 31 | 19.4% | 0.616 | −$13.60 | −$0.439 | [−$1.098, +$0.346] | COLLECT |
| H08 | 35 | 28.6% | 1.498 | +$14.30 | +$0.409 | [−$0.391, +$1.306] | COLLECT |
| H09 | 28 | 14.3% | 0.438 | −$15.75 | −$0.563 | [−$1.047, +$0.064] | COLLECT |
| H10 | 38 | 34.2% | 1.162 | +$5.34 | +$0.141 | [−$0.517, +$0.823] | COLLECT |
| H11 | 71 | 35.2% | 1.196 | +$13.53 | +$0.191 | [−$0.355, +$0.744] | WATCHLIST |
| H12 | 36 | 36.1% | 0.970 | −$1.20 | −$0.033 | [−$0.779, +$0.765] | COLLECT |
| H13 | 36 | 33.3% | 1.022 | +$0.83 | +$0.023 | [−$0.715, +$0.782] | COLLECT |
| H14 | 47 | 29.8% | 0.894 | −$5.05 | −$0.108 | [−$0.707, +$0.473] | WATCHLIST |
| H15 | 36 | 30.6% | 0.898 | −$4.45 | −$0.124 | [−$0.899, +$0.729] | COLLECT |
| H16 | 30 | 16.7% | 0.428 | −$21.46 | −$0.715 | [−$1.303, −$0.033] | COLLECT |
| H17 | 21 | 38.1% | 0.752 | −$8.14 | −$0.388 | [−$2.018, +$1.060] | COLLECT |
| H18 | 25 | 60.0% | 1.406 | +$7.53 | +$0.301 | [−$0.478, +$1.102] | COLLECT |
| H20 | 3 | 100.0% | inf | +$9.05 | +$3.016 | [+$2.966, +$3.116] | COLLECT (n=3) |
| H21 | 39 | 51.3% | 1.873 | +$23.67 | +$0.607 | [−$0.075, +$1.298] | COLLECT |
| H22 | 40 | 32.5% | 0.872 | −$5.48 | −$0.137 | [−$0.783, +$0.547] | WATCHLIST |
| H23 | 57 | 33.3% | 1.004 | +$0.24 | +$0.004 | [−$0.573, +$0.611] | WATCHLIST |

No hour reaches n≥100. Per-hour patch condition cannot trigger.

### Per-Ask-Band

| band | n | WR | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| [0.00, 0.10) | 10 | 0.0% | 0.000 | −$9.11 | −$0.911 | [−$1.099, −$0.740] | — | COLLECT |
| [0.10, 0.20) | 91 | 18.7% | 1.197 | +$13.60 | +$0.149 | [−$0.316, +$0.658] | BELOW lower | WATCHLIST |
| [0.20, 0.30) | 227 | 26.4% | 0.997 | −$0.73 | −$0.003 | [−$0.286, +$0.274] | BELOW lower | BELOW_CI |
| [0.30, 0.40) | 390 | 38.7% | 1.115 | +$46.99 | +$0.121 | [−$0.114, +$0.361] | BELOW lower | BELOW_CI |
| [0.40, 0.50) | 157 | 47.1% | 1.075 | +$13.38 | +$0.085 | [−$0.291, +$0.466] | BELOW lower | BELOW_CI |
| [0.50, 0.60) | 8 | 50.0% | 0.881 | −$1.25 | −$0.157 | [−$1.991, +$1.671] | — | COLLECT |

[0.30,0.40) is the dominant band (n=390, 44% of trades) and is BELOW_CI.
Pattern: live WR rises monotonically with ask price (0%→19%→26%→39%→47%→50%) while
model confidence inversely predicts outcome — consistent with state_log 2026-05-17 12:30
anti-calibration diagnosis (r≈0, hour-of-day confound).

---

## Lever Probes

| lever | probe cell | n | EV | CI95 | lever_candidate | blocker |
|---|---|---|---|---|---|---|
| ASK_CEIL lower (0.60→0.55) | [0.50, 0.60) | 8 | −$0.157 | [−$1.991, +$1.671] | NO | n=8 << 100 |
| REM_MAX_S lower (280→260) | [260, 280)s rem-at-entry | 0 | — | — | NO | `term_remaining_s`=0 for all 885 records; VOLARB doesn't log rem-at-entry |
| REM_MIN_S raise (60→80) | [60, 80)s rem-at-entry | 0 | — | — | NO | same field issue; structurally uncomputable |
| ASK_DEPTH_MULT raise | adverse-selection check | 885 | — | — | NO | `slippage_entry`=0.0 for 100% of records; zero adverse-selection evidence |

**REM field note:** VOLARB hold-to-resolution exits do not record remaining time at entry.
`term_remaining_s` and `sniper_lag_remaining` are both 0.0 across all 885 records (these
fields belong to LDA/SNIPER schema). `hold_seconds` tracks actual hold duration, not
rem-at-entry. REM lever probes are structurally uncomputable from VOLARB trade logs.

---

## Proposed Patch

**NO PATCH.**

EDGE_FLOOR raise conditions are technically met (n=885≥200, EV=+$0.062<$0.10,
PF=1.061<1.10, CI_lower=−$0.092<0), but two independent hard blockers apply:

1. **Strategy retired.** `strategy/volarb.py` is never called (VOLARB object removed
   2026-05-19). Editing any constant has zero operational effect. A patch PR to dead code
   is noise.

2. **Prescribed value is incoherent.** "0.15→0.17" targets a stale value. Actual code:
   `EDGE_FLOOR_DEFAULT=0.10` (set by explicit user instruction 2026-05-17 10:20 UTC,
   state_log). Raising 0.10→0.17 is +70%, violates ±20% Tier 1 ceiling, and contradicts
   an explicit user directive. This is the **4th consecutive audit cycle** flagging this
   mismatch.

No other lever probe clears n≥100. Stack ranking is vacuous.

---

## Watchlist (40≤n<100; informational — strategy retired)

| dimension | cell | n | WR | EV/trade | CI95 | Δ vs prior audit | note |
|---|---|---|---|---|---|---|---|
| hour | H01 | 66 | 48.5% | +$0.784 | [+$0.144, +$1.415] | 0 (unchanged) | only VOLARB hour with CI lower > 0 |
| hour | H02 | 64 | 40.6% | +$0.196 | [−$0.388, +$0.812] | 0 | weakly positive |
| hour | H11 | 71 | 35.2% | +$0.191 | [−$0.355, +$0.744] | 0 | mixed |
| hour | H14 | 47 | 29.8% | −$0.108 | [−$0.707, +$0.473] | 0 | trending negative |
| hour | H22 | 40 | 32.5% | −$0.137 | [−$0.783, +$0.547] | 0 | trending negative |
| hour | H23 | 57 | 33.3% | +$0.004 | [−$0.573, +$0.611] | 0 | flat |
| ask | [0.10,0.20) | 91 | 18.7% | +$0.149 | [−$0.316, +$0.658] | 0 | mixed |

Δ=0 new trades since prior audit. All cells frozen. Will never reach n≥100 while strategy
is retired.

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
prescribes a raise to 0.17. This has been stale since 2026-05-17 10:20 UTC (3+ days).
VOLARB has been retired since 2026-05-17 19:56 UTC with zero new trades for 39+ hours.
Running this audit every 6h against a fully-retired, Δ=0-trade strategy generates noise
without operational value. Recommend retiring or pausing this scheduled agent until
VOLARB is reactivated, or retargeting it to the active strategy (CAS_LOWASK).
