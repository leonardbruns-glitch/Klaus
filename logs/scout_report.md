# VOLARB Alpha Scout — 2026-06-03T00:43Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-06-03T00:35:38Z (~7.8 min old — FRESH) |
| Klaus state | active (WEATHER/STWA strategy; bankroll $117.694698) |
| Klaus HEAD | 11b40e73 |
| Capital | $117.694698 |
| VOLARB live n | **887 — FROZEN 14.9 days** (Δn=0 vs prior cycle 2026-05-31T00:43Z) |
| VOLARB date range | 2026-05-16T21:00 – 2026-05-19T02:50 UTC (53.8h / 2.2 days active) |
| Last VOLARB trade | 2026-05-19T02:50Z (SOL) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |
| Current active strategy | WEATHER/STWA (last trade 2026-06-02T14:01Z — not in Scout scope) |

**Pre-flight results:**
- snapshot_ts age: ~7.8 min — **PASS**
- integrity_report.json: ABSENT from data-mirror — treated as PASS (consistent with prior cycles)
- Last Scout commit: 2026-05-31T00:43Z (~3 days ago, ≥8h threshold) — **PROCEED**
- CODE_DESYNC check: SNAPSHOT HEAD=11b40e73 (accepted)
- Δn since prior scout: **Δn=0** — dataset permanently frozen at n=887

**Strategic context flag (not a pre-flight abort, logged for Auditor/human review):**
- `research_status.md` was last updated 2026-05-16 12:50 UTC, 8.2h *before* VOLARB activation at 21:00 UTC.
  It describes LDA as the active strategy and does not mention VOLARB.
- The *actual* currently active strategy is **WEATHER/STWA** (173 trades, last trade 2026-06-02).
  Neither LDA nor VOLARB is generating new trades.
- VOLARB ran for exactly 2.2 days then retired. This Scout mandate operates on a dead dataset.
  All investigation families were declared terminal in cycle 5 (2026-05-31).
  **Recommend human review of whether VOLARB Scout cycles should continue.**

**Aggregate VOLARB ($1-equiv, kline_pnl basis — canonical per research_status.md §1):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| kline_pnl available | 876/887 (99%) | — |
| WR (kline_pnl>0) | 31.6% (277/876) | below 40% backtest expectation |
| kEV/trade ($1-equiv) | −$0.023 | CI=[−$0.127, +$0.081] — **BELOW_CI** |
| Days since last trade | 14.9 | — |
| 24h delta n | 0 | permanently frozen |

---

## Continuity vs Prior Scout (Cycle 5 — 2026-05-31T00:43Z, ~3 days ago)

**Δn=0: every cell is arithmetically identical to prior cycle. No new conclusions possible.**

Investigations carried over from prior cycle (terminal status reconfirmed):

| Family | Prior Status | Δn | Cycle 6 Status |
|---|---|---|---|
| H1 per-asset alpha | DISCARD terminal (cycles 4–5) | 0 | DISCARD terminal (cycle 6) |
| H2 per-hour UTC | DATA_MISSING; cross-LDA flag CLOSED (cycle 5) | 0 | DATA_MISSING / CLOSED (cycle 6) |
| H3 per-ask-band | DISCARD terminal (cycles 4–5) | 0 | DISCARD terminal (cycle 6) |
| H4 Phase 2 longshot | MOOT formally closed (cycle 5) | 0 | MOOT confirmed (cycle 6) |
| H5 sec-to-res | DISCARD terminal (field unpopulated — prior cycles) | 0 | DISCARD terminal (cycle 6) |
| H6 direction asymmetry | DISCARD terminal (cycles 4–5) | 0 | DISCARD terminal (cycle 6) |
| H7 watchlist trajectories | DISCARD terminal (cycle 5) | 0 | DISCARD terminal (cycle 6) |

**Resolved/closed since prior:** None new. All families already terminal or MOOT.

---

## Investigations H1, H7, H4 (Cycle 6 Terminal Reconfirmation)

*Selection rationale: H1 and H7 are the n≥100 cells that could theoretically diverge if Δn>0;
H4 is the sole previously-open shadow item. Δn=0 makes all three arithmetically identical to cycle 5.*

---

### H1: Per-Asset Alpha Re-Allocation

**HYPOTHESIS:** VOLARB live EV differs significantly by asset (BTC/ETH/SOL); BTC was backtest alpha
asset (+$14.81 projected). If BTC live EV is below CI lower (+$0.244) and n≥100, raise global EDGE_FLOOR.

**METHOD:** kline_pnl/$1-equiv by asset, n≥100 threshold, CI95 vs baseline.

**RESULT:**

| Asset | kn | WR% | kEV/$1 | CI95 | vs baseline CI [+0.244,+0.352] | Δn vs prior |
|---|---|---|---|---|---|---|
| BTC | 283 | 31.1% | +$0.039 | [−$0.159, +$0.237] | **DISCARD** (CI_hi=+0.237 < +0.244) | 0 |
| ETH | 301 | 30.2% | −$0.075 | [−$0.245, +$0.095] | **DISCARD** | 0 |
| SOL | 292 | 33.6% | −$0.030 | [−$0.202, +$0.142] | **DISCARD** | 0 |

**CONCLUSION: DISCARD (terminal — cycle 6).** All three assets have CI entirely below baseline lower
bound (+$0.244). BTC is the best-performing asset (kEV=+$0.039) but CI_hi=+$0.237 is still below the
baseline floor. Backtest BTC alpha (+$14.81 projected) did not materialise in the 2.2-day live window.
Δn=0 permanently locks this result.

**FAILURE_MET:** yes — all assets DISCARD; no asset meets baseline CI lower bound; dataset frozen.

**IF_DEPLOYED:** N/A — VOLARB retired; no lever exists to act on asset-level signals.

---

### H7: Watchlist Cell Trajectories (24h vs Full Live Window)

**HYPOTHESIS:** Previously-flagged cells ([0.10,0.20) ask n=91 INCONCLUSIVE; H01 n=66 INCONCLUSIVE)
may show drift from prior-cycle values, warranting Auditor elevation.

**METHOD:** Recompute all cell statistics at current n=887. Δn=0 → arithmetic identity; cross-cycle
consistency check only.

**RESULT:**

*n≥100 cells — DISCARD terminal, no change:*

| Cell | kn | WR% | kEV/$1 | CI95 | vs_CI | Δn |
|---|---|---|---|---|---|---|
| [0.20,0.30) ask | 227 | 24.7% | −$0.053 | [−$0.273, +$0.166] | DISCARD | 0 |
| [0.30,0.40) ask | 382 | 35.6% | +$0.010 | [−$0.128, +$0.147] | DISCARD | 0 |
| [0.40,0.50) ask | 156 | 42.9% | −$0.007 | [−$0.189, +$0.175] | DISCARD | 0 |
| direction=up | 389 | 28.5% | −$0.029 | [−$0.197, +$0.140] | DISCARD | 0 |
| direction=down | 487 | 34.1% | −$0.019 | [−$0.149, +$0.111] | DISCARD | 0 |

*n<100 watchlist cells — permanently frozen below n=100 threshold:*

| Cell | kn | WR% | kEV/$1 | CI95 | Note |
|---|---|---|---|---|---|
| [0.10,0.20) ask | 91 | 15.4% | +$0.032 | [−$0.480, +$0.544] | 9 trades short of n=100; frozen |
| H01 UTC | 66 | 45.5% | +$0.389 | [−$0.022, +$0.800] | Most positive hour; will never reach n=100 |
| H11 UTC | 71 | 35.2% | +$0.097 | [−$0.290, +$0.485] | Frozen |
| [0.50,0.60) ask | 8 | 37.5% | −$0.282 | [−$0.974, +$0.410] | Insufficient |

**24h drift check:** Δn=0 across all cells. No drift possible. No cell has changed since cycle 5.
The [0.10,0.20) band (kn=91, 9 rows short of n=100) and H01 (kn=66) are permanently locked below
n-thresholds. No Auditor promotion is possible.

**CONCLUSION: DISCARD (terminal — cycle 6).** Δn=0 prevents any new conclusions. All n≥100 cells
reconfirmed DISCARD (CI_hi < +0.244). Watchlist cells permanently frozen below n=100.

**FAILURE_MET:** yes — all n≥100 cells DISCARD; watchlist cells will never reach n=100.

**IF_DEPLOYED:** N/A.

---

### H4: Phase 2 Longshot Gate Prep (ask 0.00–0.10)

**HYPOTHESIS:** A `volarb_longshot_shadow.jsonl` recorder was proposed to track ask<0.10 VOLARB
candidates with realized outcomes. Phase 2 gate requires n≥100 OOS at ask<0.10.

**METHOD:** Check shadow_summary.json (206 loggers, snapshot_ts 2026-06-03T00:35:38Z)
for `volarb_longshot_shadow` or `longshot` entries.

**RESULT:**
- `volarb_longshot_shadow.jsonl`: **ABSENT** from shadow_summary.json (206 loggers checked)
- shadow_summary.json covers dates 2026-05-23 through 2026-06-03 (post-VOLARB retirement)
- VOLARB [0.10,0.20) band: kn=91 — ask<0.10 sub-cell is necessarily n<91; frozen
- Recorder was never deployed during VOLARB's 2.2-day active window (2026-05-16 to 2026-05-19)
- Active shadow loggers are WEATHER/STWA-era (stwa_signals, stwa_state, stwa_pricer_eval through 2026-06-03)

**CONCLUSION: MOOT (formally closed — cycles 5 + 6 reconfirm).** VOLARB retired 14.9 days
before this report. No new VOLARB entries will ever be logged. Phase 2 ask<0.10 gate prep has no
deployment target. Recorder spec proposed in prior cycles was never built; now irrelevant.

**FAILURE_MET:** N/A — strategy retired before threshold was reachable.

**IF_DEPLOYED:** N/A.

---

## Priority Signal for Next Implementation

**No actionable signal this cycle — VOLARB dataset permanently frozen (n=887, Δn=0 for 14.9 days).
All H-families DISCARD terminal (cycles 1–6) or MOOT. Aggregate kEV=−$0.023/trade,
CI=[−$0.127, +$0.081], BELOW baseline floor of +$0.244.**

**Cycle 6 is the terminal confirmation cycle. All findings have been stable for ≥3 Scout cycles
(cycle 4 declared terminal, confirmed cycles 5 and 6). There is no hypothesis left to test,
no threshold to cross, and no new data to collect.**

**Recommendation: Halt VOLARB Scout cycles immediately.** If Scout capacity continues,
redirect mandate to WEATHER/STWA strategy analysis (active, 173 trades in `trades.jsonl`,
shadow loggers live through 2026-06-03).

---

## Closed-Family Confirmations (Cycle 6)

| Family | Status | Reconfirmed | Cycle |
|---|---|---|---|
| H1 per-asset alpha | DISCARD terminal | 2026-06-03 | 6 |
| H2 per-hour UTC | DATA_MISSING + cross-LDA flag CLOSED | 2026-06-03 | 6 |
| H3 per-ask-band | DISCARD terminal | 2026-06-03 | 6 |
| H4 Phase 2 longshot | MOOT | 2026-06-03 | 6 |
| H5 sec-to-res | DISCARD terminal (field unpopulated) | 2026-06-03 | 6 |
| H6 direction asymmetry | DISCARD terminal | 2026-06-03 | 6 |
| H7 watchlist trajectories | DISCARD terminal | 2026-06-03 | 6 |

---

## Open Requests for Auditor / Shadow Validator

**Cells trending to n≥100 within next 24h:** NONE — dataset permanently frozen.

**Shadow loggers past threshold:** NONE in VOLARB scope. volarb_longshot_shadow never deployed → MOOT.

**Phase 2 longshot recorder status:** CLOSED (MOOT — H4 cycles 5–6).

**Structural flags for human review:**
1. `research_status.md` predates VOLARB activation (updated 2026-05-16 12:50 UTC, activation 21:00 UTC).
   Current active strategy (WEATHER/STWA) is not documented. Recommend updating to close VOLARB
   explicitly and document WEATHER/STWA strategy mandate.
2. VOLARB Scout cron should be halted or redirected to WEATHER/STWA mandate.
   Continued VOLARB Scout cycles will produce zero-delta terminal reports indefinitely.
