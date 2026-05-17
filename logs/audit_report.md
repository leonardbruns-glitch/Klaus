# VOLARB Quantitative Audit — 2026-05-17 12:16 UTC

## Snapshot

| field | value |
|---|---|
| snapshot_ts | 2026-05-17T12:08:33Z (8 min old — FRESH) |
| Klaus state | active (systemd: active, 0 open positions) |
| Capital | $80.43 (prior audit 00:16 UTC: $67.03 → +$13.40 Δ) |
| VOLARB n (live era) | 528 (deduped first-fire per (asset, ts_open rounded to second)) |
| drift_status | OK — data-mirror has no strategy/volarb.py; dev branch parameters confirmed current |
| Data window | 2026-05-16T21:00Z .. 2026-05-17T12:08Z (15h8m) |

**EDGE_FLOOR NOTE:** Audit prompt assumes current EDGE_FLOOR=0.15. Actual deployed value is **0.10**
(user instruction 2026-05-17 10:20 UTC: lowered 0.30→0.10 after live evidence showed
floor=0.30 produced WR=19.3% EV=-$0.224/trade at n=88 — see Era Analysis below).
Patch proposal "0.15→0.17" is moot; actual current is 0.10.

---

## Pre-flight Checks

| check | result |
|---|---|
| Snapshot age ≤45 min | PASS (8 min) |
| `system_status.txt` active | PASS |
| `bankroll.json` capital non-zero | PASS ($80.43) |
| Code drift guard | PASS (data-mirror has no strategy/volarb.py; N/A condition) |
| Integrity report `blocks_agent_run` | N/A (integrity_report.json absent from mirror) |

---

## Overall VOLARB Performance (live era)

| metric | value | baseline (1-equiv) | vs baseline |
|---|---|---|---|
| n | 528 | — | — |
| WR | 34.8% | — | — |
| PF | 1.169 | — | — |
| net_sum | +$84.60 | — | — |
| EV/trade | +$0.1602 | +$0.298 mid | BELOW mid, overlapping CI |
| CI95 | [-$0.035, +$0.362] | [+$0.244, +$0.352] | OVERLAPPING baseline window |
| fee_bleed | 9.6% of gross ($9.03/$93.63) | <20% kill-switch | OK |

Strategy is cash-flow positive but tracking below backtest. CI overlaps with baseline lower (+$0.244)
— not decisively below zero and not decisively at backtest. **Status: COLLECTING.**

Stake structure note: VOLARB uses 5 shares minimum (CLOB min). Actual stake = 5 × entry_price,
ranging $0.33–$2.75, mean $1.52. The $1-equiv backtest CI comparison is approximate.

---

## EDGE_FLOOR Era Analysis (informational)

| era | floor | n | WR | EV/trade | sum |
|---|---|---|---|---|---|
| Pre-07:26 UTC (0.15 all) | 0.15 | 352 | 37.8% | +$0.225 | +$79.35 |
| 07:26–07:44 UTC (0.15/0.25) | 0.15/0.25 | 12 | 41.7% | +$0.469 | +$5.63 |
| 07:44–10:20 UTC (0.30 all) | 0.30 | 88 | 19.3% | -$0.224 | -$19.68 |
| Post-10:20 UTC (0.10 all) | 0.10 | 76 | 38.2% | +$0.254 | +$19.29 |

**Finding:** floor=0.30 era was significantly negative (WR 19.3%, EV -$0.224). User's decision to
revert to 0.10 at 10:20 UTC was correct and is supported by this data. Post-10:20 performance
restored to pre-0.30 levels (+$0.254/trade, WR 38.2%).

---

## 6h Recency Cells (n≥10 threshold)

Window: 2026-05-17 06:08 UTC .. 12:08 UTC (n=196 records)

| cell | n | WR | net_sum | EV | flag |
|---|---|---|---|---|---|
| BTC×[0.10,0.20) | 15 | 26.7% | +$8.16 | +$0.544 | — |
| BTC×[0.20,0.30) | 23 | 21.7% | -$2.86 | -$0.124 | — |
| BTC×[0.30,0.40) | 21 | 38.1% | +$4.18 | +$0.199 | — |
| ETH×[0.10,0.20) | 19 | 15.8% | +$1.46 | +$0.077 | — |
| ETH×[0.20,0.30) | 20 | 20.0% | -$5.78 | -$0.289 | — |
| ETH×[0.30,0.40) | 24 | 37.5% | +$3.27 | +$0.136 | — |
| SOL×[0.20,0.30) | 22 | 27.3% | -$2.06 | -$0.094 | — |
| SOL×[0.30,0.40) | 20 | 40.0% | +$4.80 | +$0.240 | — |
| SOL×[0.40,0.50) | 14 | 50.0% | +$2.81 | +$0.200 | — |
| BTC (all 6h) | 64 | 28.1% | +$6.09 | +$0.095 | — |
| ETH (all 6h) | 67 | 25.4% | -$3.07 | -$0.046 | — |
| SOL (all 6h) | 65 | 33.8% | +$0.87 | +$0.013 | — |

No cell reaches n≥10 with EV<-$0.50 flag threshold. No recency alarm.

---

## Full-Window Cell Scan (2026-05-16T21:00Z .. 2026-05-17T12:08Z)

### Per-Asset

| asset | n | WR | PF | sum | EV/trade | CI95 | vs_baseline_CI | status |
|---|---|---|---|---|---|---|---|---|
| BTC | 167 | 30.5% | 1.070 | +$11.34 | +$0.068 | [-$0.275, +$0.418] | BELOW lower ($0.244) | **WATCHLIST** |
| ETH | 184 | 32.6% | 1.105 | +$18.56 | +$0.101 | [-$0.223, +$0.427] | BELOW lower ($0.244) | **WATCHLIST** |
| SOL | 177 | 41.2% | 1.336 | +$54.69 | +$0.309 | [-$0.039, +$0.657] | ABOVE lower ($0.244), CI overlapping | OK |

BTC and ETH watchlisted: n≥100, EV below backtest CI lower (+$0.244). CIs are wide (overlapping
zero). No patch lever applicable (per-asset EDGE_FLOOR exists in code but is not a listed VOLARB
Phase 1 lever; per-asset blocks not introduced per anti-sycophancy rules).

### Per-Hour UTC (n≥10 shown; all n<100 → COLLECTING)

| hour | n | WR | PF | sum | EV/trade | CI95 | status |
|---|---|---|---|---|---|---|---|
| H00 | 36 | 30.6% | 1.103 | +$3.57 | +$0.099 | [-$0.630, +$0.911] | COLLECTING |
| H01 | 36 | 50.0% | 2.638 | +$39.71 | +$1.103 | [+$0.253, +$1.976] | COLLECTING |
| H02 | 37 | 51.4% | 1.964 | +$28.90 | +$0.781 | [+$0.001, +$1.523] | COLLECTING |
| H03 | 36 | 44.4% | 1.374 | +$13.38 | +$0.372 | [-$0.424, +$1.146] | COLLECTING |
| H04 | 37 | 32.4% | 0.873 | -$5.42 | -$0.147 | [-$0.880, +$0.611] | COLLECTING |
| H05 | 35 | 14.3% | 0.359 | -$30.13 | -$0.861 | [-$1.391, -$0.225] | COLLECT (n<40 — awareness only) |
| H06 | 35 | 31.4% | 1.020 | +$0.72 | +$0.021 | [-$0.709, +$0.810] | COLLECTING |
| H07 | 31 | 19.4% | 0.616 | -$13.60 | -$0.439 | [-$1.090, +$0.335] | COLLECTING |
| H08 | 32 | 28.1% | 1.547 | +$14.10 | +$0.441 | [-$0.416, +$1.340] | COLLECTING |
| H09 | 28 | 14.3% | 0.438 | -$15.75 | -$0.563 | [-$1.092, +$0.071] | COLLECTING |
| H10 | 35 | 31.4% | 1.053 | +$1.62 | +$0.046 | [-$0.606, +$0.755] | COLLECTING |
| H11 | 38 | 44.7% | 1.565 | +$18.83 | +$0.495 | [-$0.257, +$1.241] | COLLECTING |
| H21 | 37 | 48.6% | 1.671 | +$18.19 | +$0.492 | [-$0.164, +$1.170] | COLLECTING |
| H22 | 37 | 29.7% | 0.768 | -$9.41 | -$0.254 | [-$0.875, +$0.413] | COLLECTING |
| H23 | 35 | 42.9% | 1.816 | +$21.04 | +$0.601 | [-$0.137, +$1.357] | COLLECTING |

No hour crosses n≥100. All COLLECTING. H05 (n=35, CI [-$1.39, -$0.22] entirely negative)
flagged for awareness but IGNORED per n<40 rule.

### Per-Ask-Band

| band | n | WR | PF | sum | EV/trade | CI95 | vs_baseline | status |
|---|---|---|---|---|---|---|---|---|
| <0.10 | 7 | 0.0% | 0.000 | -$6.56 | -$0.938 | [-$1.206, -$0.709] | — | IGNORE (n<40) |
| [0.10,0.20) | 68 | 19.1% | 1.228 | +$11.57 | +$0.170 | [-$0.358, +$0.744] | n<100 | COLLECTING |
| [0.20,0.30) | 160 | 28.1% | 1.070 | +$10.02 | +$0.063 | [-$0.275, +$0.395] | BELOW lower | MONITOR |
| [0.30,0.40) | 212 | 39.6% | 1.193 | +$41.56 | +$0.196 | [-$0.111, +$0.516] | BELOW lower | MONITOR |
| [0.40,0.50) | 77 | 51.9% | 1.364 | +$28.86 | +$0.375 | [-$0.187, +$0.919] | n<100 | COLLECTING |
| [0.50,0.60) | 4 | 50.0% | 0.843 | -$0.85 | -$0.213 | — | — | IGNORE (n<40) |

Bands [0.20,0.30) and [0.30,0.40) are MONITOR: n≥100, EV below baseline lower, but EV>-$0.10
(lever threshold not crossed). Continue collecting.

---

## Lever Probes

### ASK_CEIL probe [0.50, 0.60)
n=4 — **BLOCKED** (n<40, far below n≥100 threshold). High-ask side nearly untouched. No decision.

### REM_MAX_S probe [260, 280)s
`term_remaining_s = 0` for **all 528 VOLARB records** (logging bug). **BLOCKED.**
Same issue as prior LDA audit (00:16 UTC). Fix required in volarb.py trade logger.

### REM_MIN_S probe [60, 80)s
Same logging bug. **BLOCKED.**

### ASK_DEPTH_MULT probe
`slippage_entry = 0` for all VOLARB records — adverse-selection evidence unavailable. **BLOCKED.**
n≥200 condition met (528) but overall EV is positive (+$0.160) — EV degradation condition not
triggered regardless.

---

## Proposed Patch

**No patch.**

| lever | conditions required | result |
|---|---|---|
| EDGE_FLOOR raise | n≥200 ✓ AND EV<+$0.10 ✗ AND PF<1.10 ✗ AND CI_lo<0 ✓ | 2 of 4 fail — NO |
| ASK_CEIL lower | n≥100 in [0.50,0.60) | n=4 — BLOCKED |
| REM_MAX_S lower | n≥100 in [260,280) | term_remaining_s=0 — BLOCKED |
| REM_MIN_S raise | n≥100 in [60,80) | term_remaining_s=0 — BLOCKED |
| ASK_DEPTH_MULT raise | slippage evidence + n≥200 + EV degrading | no slippage data — BLOCKED |

---

## Watchlist (40≤n<100 and per-asset/per-hour findings without block lever)

| cell | n | EV/trade | CI95 | note | prior_audit_delta |
|---|---|---|---|---|---|
| BTC (asset) | 167 | +$0.068 | [-$0.275, +$0.418] | EV<baseline lower $0.244; CI wide and positive-tailed | NEW (first VOLARB audit) |
| ETH (asset) | 184 | +$0.101 | [-$0.223, +$0.427] | EV<baseline lower $0.244; CI wide and positive-tailed | NEW |
| [0.20,0.30) band | 160 | +$0.063 | [-$0.275, +$0.395] | n≥100, EV below baseline, above -$0.10 lever bar | NEW |
| [0.30,0.40) band | 212 | +$0.196 | [-$0.111, +$0.516] | n≥100, EV below baseline, above -$0.10 lever bar | NEW |
| H05 UTC | 35 | -$0.861 | [-$1.391, -$0.225] | n<40 — IGNORE; CI entirely negative, awareness flag | NEW |

BTC and ETH are the primary watchlist concerns. Both underperform vs backtest CI lower at n≥100.
SOL is the outperformer (EV=$0.309, above baseline lower). H05 is the most alarming per-hour
pattern but is below the n≥40 threshold for any action.

---

## Skipped — User Override (state_log)

| cell | override | timestamp |
|---|---|---|
| EDGE_FLOOR raise | User lowered EDGE_FLOOR 0.30→0.10 at 10:20 UTC after live evidence confirmed floor=0.30 was destructive (WR=19.3%, EV=-$0.224/trade, n=88). Raising to 0.17 would contradict a same-day user instruction. | 2026-05-17 10:20 UTC |

**Audit prompt parameter map is stale:** EDGE_FLOOR "current 0.15" → actual current is 0.10.
Prompt's proposed "0.15→0.17" is inapplicable. Deployed: `EDGE_FLOOR_BY_ASSET={"BTC":0.10,"ETH":0.10,"SOL":0.10}`.

---

## Infrastructure Notes (fix required for full probe coverage)

1. `term_remaining_s` not flushed to trades.jsonl for VOLARB (= 0 for all 528 records).
   Blocks REM_MIN_S and REM_MAX_S lever evaluation permanently until resolved.
2. `slippage_entry/exit` not populated for VOLARB trades. Blocks ASK_DEPTH_MULT adverse-selection analysis.

---

## Status

**STATUS: NO_PATCH — COLLECTING (n=528, 15h8m)**

Overall EV +$0.160/trade, PF 1.169. Strategy is cash-flow positive. No lever conditions met.
BTC and ETH watchlisted (EV below baseline at n≥100). SOL performing at baseline.
Era analysis validates user's floor decisions: 0.30 was destructive; 0.10 restored performance.
Next check: H05 at n≥40; BTC/ETH per-asset at n≥200 for tighter CI.
