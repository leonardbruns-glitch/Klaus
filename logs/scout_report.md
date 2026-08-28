# VOLARB Alpha Scout — 2026-06-04T12:43Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-06-04T12:26:53Z (~16 min old — FRESH) |
| Klaus state | active (WEATHER/STWA strategy; bankroll $71.990738) |
| Klaus HEAD | a4403c5c |
| Capital | $71.990738 |
| VOLARB live n | **887 — FROZEN 16.4 days** (Δn=0 vs prior cycle 2026-06-03T00:43Z) |
| VOLARB date range | 2026-05-16T21:00 – 2026-05-19T02:50 UTC (53.8h / 2.2 days active) |
| Last VOLARB trade | 2026-05-19T02:50Z (SOL) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |
| Current active strategy | WEATHER/STWA (not in Scout scope) |

**Pre-flight results:**
- snapshot_ts age: ~16 min — **PASS**
- integrity_report.json: ABSENT from data-mirror — treated as PASS (consistent with all prior cycles)
- Last Scout commit: 2026-06-03T00:43Z (~36h ago, ≥8h threshold) — **PROCEED**
- CODE_DESYNC check: SNAPSHOT HEAD=a4403c5c (accepted — live strategy active)
- Δn since prior scout (Cycle 6): **Δn=0** — dataset permanently frozen at n=887

**Aggregate VOLARB ($1-equiv, kline_pnl basis — canonical per research_status.md §1):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| kline_pnl available | 876/887 (99%) | — |
| WR (kline_pnl>0) | 31.6% (277/876) | below 40% backtest expectation |
| kEV/trade ($1-equiv) | −$0.023 | CI=[−$0.127, +$0.081] — **BELOW_CI** |
| Days since last trade | 16.4 | — |
| 24h delta n | 0 | permanently frozen |

**Strategic context flag (escalated — not a pre-flight abort):**
> VOLARB ran 2.2 days then retired. All investigation families declared TERMINAL in Cycle 5 (2026-05-31).
> Cycles 6 and 7 (this report) are arithmetically identical. `research_status.md` pre-dates VOLARB
> activation and describes LDA as active. Active strategy is now WEATHER/STWA (last trade 2026-06-04).
> **Recommend human decision: decommission VOLARB Scout series or formally archive and close.**

---

## Continuity vs Prior Scout (Cycle 6 — 2026-06-03T00:43Z, ~36h ago)

**Δn=0: every cell is arithmetically identical to Cycle 6. No new conclusions possible.**

| Family | Cycle 6 Status | Δn | Cycle 7 Status |
|---|---|---|---|
| H1 per-asset alpha | DISCARD terminal (cycles 4–6) | 0 | DISCARD terminal (cycle 7) |
| H2 per-hour UTC | DATA_MISSING / CLOSED (cycles 5–6) | 0 | DATA_MISSING / CLOSED (cycle 7) |
| H3 per-ask-band | DISCARD terminal (cycles 4–6) | 0 | DISCARD terminal (cycle 7) |
| H4 Phase 2 longshot | MOOT closed (cycles 5–6) | 0 | MOOT confirmed (cycle 7) |
| H5 sec-to-res | DISCARD terminal (prior cycles) | 0 | DISCARD terminal (cycle 7) |
| H6 direction asymmetry | DISCARD terminal (cycles 4–6) | 0 | DISCARD terminal (cycle 7) |
| H7 watchlist trajectories | DISCARD terminal (cycles 5–6) | 0 | DISCARD terminal (cycle 7) |

**Resolved/closed since prior:** None new. All families terminal or MOOT since Cycle 5.

---

## Investigations H1, H6, H4 (Cycle 7 Terminal Reconfirmation)

*Selection rationale: H1 and H6 are the n≥100 cells with the most prior watchlist activity; H4 is
the shadow-recorder item. Δn=0 makes all three arithmetically identical to Cycle 6.*

---

### H1: Per-Asset Alpha Re-Allocation

**HYPOTHESIS:** VOLARB live EV differs significantly by asset; BTC was backtest alpha (+$14.81 projected). If BTC live EV below CI lower (+$0.244) and n≥100 → raise EDGE_FLOOR globally.

**METHOD:** kline_pnl/$1-equiv by asset (n≥100 threshold, CI95 vs baseline).

**RESULT:**

| Asset | kn | WR% | kEV/$1 | CI95 (approx) | vs baseline CI [+0.244, +0.352] | Δn |
|---|---|---|---|---|---|---|
| BTC | 283 | 31.1% | +$0.039 | [−$0.159, +$0.237] | **BELOW_CI** (CI_hi < +0.244) | 0 |
| ETH | 301 | 30.2% | −$0.056 | [−$0.245, +$0.133] | **BELOW_CI** | 0 |
| SOL | 292 | 33.6% | −$0.044 | [−$0.202, +$0.114] | **BELOW_CI** | 0 |

**CONCLUSION: DISCARD (terminal — Cycle 7).** All three assets below baseline floor. BTC best at +$0.039/trade but CI_hi still below +$0.244. Backtest BTC alpha never materialised in the 2.2-day live window. Δn=0 permanently locks this result.

**FAILURE_MET:** yes — all assets BELOW_CI; VOLARB retired; no lever exists.

**IF_DEPLOYED:** N/A — VOLARB retired; no EDGE_FLOOR lever applicable.

---

### H6: Direction Asymmetry (up vs down)

**HYPOTHESIS:** VOLARB live EV differs between `bond_outcome_direction='up'` and `'down'`; backtest had no direction split.

**METHOD:** kline_pnl/$1-equiv by direction cell (n≥100 threshold, CI95 vs baseline).

**RESULT:**

| Direction | kn | WR% | kEV/$1 | CI95 (approx) | vs baseline CI [+0.244, +0.352] | Δn |
|---|---|---|---|---|---|---|
| up | 389 | 28.5% | −$0.029 | [−$0.197, +$0.140] | **BELOW_CI** | 0 |
| down | 487 | 34.1% | −$0.019 | [−$0.149, +$0.111] | **BELOW_CI** | 0 |

**CONCLUSION: DISCARD (terminal — Cycle 7).** Both directions BELOW_CI. 'down' has marginally higher WR (34.1% vs 28.5%) but CI overlaps — not actionable. Δn=0 permanently locks this result.

**FAILURE_MET:** yes — both directions BELOW_CI; no direction gate lever in VOLARB.

**IF_DEPLOYED:** N/A — VOLARB retired.

---

### H4: Phase 2 Longshot Gate Prep (ask 0.00–0.10)

**HYPOTHESIS:** A shadow logger exists recording sub-0.10 ask candidates with outcomes, enabling Phase 2 gate calibration.

**METHOD:** Check `shadow_summary.json` for `volarb_longshot_shadow` logger; check `data/shadow/volarb_longshot_shadow.jsonl`.

**RESULT:** `volarb_longshot_shadow.jsonl` ABSENT from data-mirror (confirmed via `git show` → not-found). `shadow_summary.json` contains no entry with key matching `volarb_longshot`. Latest shadow loggers in summary are dated 2026-05-25 and are LDA/WEATHER-strategy loggers only.

**CONCLUSION: MOOT (confirmed — Cycle 7).** VOLARB retired before Phase 2 recorder was ever built. No data collection possible. Phase 2 cannot be calibrated. Formally closed.

**FAILURE_MET:** yes — recorder was never deployed; strategy retired.

**IF_DEPLOYED:** N/A — VOLARB retired.

---

## Priority Signal for Next Implementation

**No actionable signal this cycle — continue collecting (n=887 — permanently frozen).**

VOLARB live kEV=−$0.023/trade ($1-equiv), CI=[−$0.127, +$0.081], is entirely below the backtest baseline lower bound of +$0.244. All per-asset and per-direction cells at n≥100 are BELOW_CI. The dataset has not grown since 2026-05-19. There is no signal to act on and no new data will arrive.

**Terminal determination:** VOLARB failed to replicate backtest EV during its 2.2-day live run. The strategy is retired. All investigation families are closed. This Scout series has no further analytical work to perform.

---

## Closed-Family Confirmations (null re-validation, Cycle 7)

Re-validated as null this cycle (prevents re-investigation in future automated runs):

| Family | Last live result | Terminal since |
|---|---|---|
| H1 per-asset alpha (BTC/ETH/SOL) | all BELOW_CI at n≥283 | Cycle 4 |
| H2 per-hour UTC breakdown | ts_open field unavailable for hour_utc extraction; DATA_MISSING closed | Cycle 5 |
| H3 per-ask-band [0.10–0.60) | all BELOW_CI at n≥91 (sub-100 cells INCONCLUSIVE) | Cycle 4 |
| H4 Phase 2 longshot recorder | recorder never deployed; VOLARB retired before build | Cycle 5 |
| H5 seconds_to_resolution slice | rem_at_entry field unpopulated in live VOLARB records | Cycle 3 |
| H6 direction asymmetry (up/down) | both BELOW_CI at n≥389 | Cycle 4 |
| H7 watchlist cell trajectories | all n<100 cells frozen; no drift possible | Cycle 5 |

---

## Open Requests for Auditor / Shadow Validator

**Cells trending to n≥100 within next 24h:** None. Dataset frozen at n=887; no new VOLARB trades expected.

**Shadow loggers past threshold:** None VOLARB-related. All current shadow loggers (gate_trace, hold_path, exit_policy_shadow, market_timeline) are LDA/WEATHER-strategy loggers — outside VOLARB Scout scope.

**Phase 2 longshot recorder status:** MOOT — VOLARB retired, recorder never built, no future build warranted.

**Escalation to human review (repeated from Cycle 6):**
> This is the 7th VOLARB Scout cycle. The dataset has been frozen at n=887 since 2026-05-19 (16.4 days).
> All investigation families have been terminal since Cycle 5 (2026-05-31). Each additional Scout cycle
> consumes agent resources with zero analytical output. **Recommend: archive this Scout series and
> remove VOLARB Scout from the scheduler.** If VOLARB is ever re-activated, a fresh Scout series
> should be commissioned at that time.
