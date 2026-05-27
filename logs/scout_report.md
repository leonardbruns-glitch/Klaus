# VOLARB Alpha Scout — 2026-05-27T12:42Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-27T12:31:56Z (~11 min old — FRESH) |
| Klaus state | active (SNIPER last fired 2026-05-27T00:28Z; LDA retired 2026-05-17) |
| Klaus HEAD | b3437493 |
| Capital | $95.304 (bankroll.json, saved_ts 2026-05-27T11:25:51Z) |
| VOLARB n (live era, is_live=True, ts_open ≥ 1778965200) | **887 — FROZEN 8.2 days** |
| VOLARB date range | 2026-05-16T21:00 – 2026-05-19T02:50 UTC (53.8h / 2.2 days) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight results:**
- snapshot_ts age: ~11 min — **PASS**
- integrity_report.json: absent — treated as **PASS**
- Last Scout commit: 2026-05-27T00:42Z (~12h ago, >8h threshold) — **PROCEED**
- CODE_DESYNC: VOLARB retired; no active VOLARB gate branch — **N/A**

**VOLARB STATUS: PERMANENTLY RETIRED. TERMINAL CLOSURE CYCLE.**
Strategy last fired 2026-05-19T02:50Z. n=887 frozen with zero 12h delta across all cells. This cycle is the final post-mortem confirmation run.

**Aggregate VOLARB ($1-equiv, kline_pnl, first-fire dedup):**

| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n | 887 | — |
| kline_pnl available | 876/887 (99%) | — |
| WR (net_pnl>0) | 34.6% (307/887) | below 40% backtest expectation |
| kEV/trade ($1-equiv, kline) | −$0.023 | CI=[−0.127, +0.081] — **BELOW baseline CI lower (+0.244)** |
| 12h delta n | 0 | frozen |

⚠️ **CAPITAL ANOMALY (flag for human review):** SNIPER last trade (2026-05-27T00:28:16Z) shows capital_after=$27.98. Current bankroll capital=$95.304 (saved_ts 11:25Z). No trades in the database explain the +$67.3 gain between 00:28Z and 11:25Z. Likely a user capital injection. This is outside VOLARB scope; flagged for Auditor/human acknowledgement.

---

## Continuity vs Prior Scout (2026-05-27T00:42Z, ~12h ago)

**Investigations carried forward from prior (all zero-delta):**
- H5 (seconds-to-resolution): Prior SIGNAL_FOUND for [220-280)s BELOW_CI. Re-confirmed this cycle with full bucket breakdown including [60-100)s detail. → **CONFIRMED CLOSED**
- H6 (direction): Prior DISCARD for both 'up' and 'down' BELOW_CI. Re-confirmed with stable kEV. → **CONFIRMED CLOSED**
- H7 (watchlist trajectories): Prior zero-delta report. Re-confirmed all cells zero-delta. → **CONFIRMED CLOSED**

**Resolved since prior (carried to confirmed-null):**
- H1 (per-asset): BTC/ETH/SOL all BELOW_CI. Zero delta re-confirmed.
- H2 (per-hour): Permanently INCONCLUSIVE (n<100 per hour). Zero delta.
- H3 (per-ask-band): All n≥100 bands BELOW_CI. Zero delta re-confirmed.
- H4 (longshot Phase 2): MOOT — recorder never deployed, strategy retired.

---

## Investigation H5 — Seconds-to-Resolution Slice

**HYPOTHESIS:** VOLARB entered predominantly in the [220-280)s remaining bucket (early in the 300s window), maximising adverse path exposure. Backtest assumed edge was leak-clean at rem≥60s. Live data should validate or challenge this; specific bucket performance determines whether narrower REM gates would have improved EV.

**METHOD:** Compute `window_end = ((int(ts_open) // 300) + 1) * 300` for each VOLARB kline row. Slice into [60-100), [100-160), [160-220), [220-280)s bands. Compute n, WR, kEV/$1-equiv, CI95, vs_baseline_CI. Compare 12h delta to prior values.

**RESULT:**

| Band (rem_s) | n | 12h Δ | WR% | kEV/$1 | CI95 (kline) | vs_baseline_CI |
|---|---|---|---|---|---|---|
| [60-100) | 14 | 0 | 7.1% | −$1.061 | [−1.147, −0.975] | **BELOW_CI** |
| [100-160) | 64 | 0 | 32.8% | +$0.221 | [−0.298, +0.740] | WITHIN_CI (n<100) |
| [160-220) | 187 | 0 | 36.9% | +$0.044 | [−0.192, +0.279] | WITHIN_CI |
| [220-280) | 609 | 0 | 34.3% | −$0.042 | [−0.160, +0.076] | **BELOW_CI** |

*All 12h deltas are zero — dataset frozen.*

**Findings:**
1. **[220-280)s bucket** (n=609, 70% of all entries): kEV=−$0.042 BELOW_CI. The dominant entry zone was the worst-performing. Entries this early in the 300s window gave markets ~4 min of adverse path time, eroding edge.
2. **[60-100)s bucket** (n=14): catastrophic kEV=−$1.061. These near-expiry entries (just above the REM_MIN_S=60 gate) lost almost the entire token value by resolution. WR=7.1% — near coin-flip with no upside.
3. **[100-160)s bucket** (n=64): best bucket at kEV=+$0.221 but CI spans [−0.298, +0.740] (n<100). INCONCLUSIVE by rule; insufficient sample to draw conclusions.
4. **[160-220)s bucket** (n=187): kEV=+$0.044, WITHIN_CI. Mildly positive but far below backtest baseline CI lower (+$0.244). CI_hi=+$0.279 still below baseline lower.

**CONCLUSION: DISCARD (terminal re-confirm).** Dataset frozen; all prior H5 findings stable. The 220-280s bulk-entry pattern was structurally harmful. The 100-160s slot had best kEV but n=64 (INCONCLUSIVE). No actionable gate recommendation possible on frozen data.

**FAILURE_MET:** No. [220-280)s BELOW_CI confirmed (n=609, well above n=100 threshold). But strategy is retired — gate changes are moot.

**IF_DEPLOYED:** N/A — strategy retired. Counterfactual: restricting entries to rem<220s (combined [100-160)s + [160-220)s, n=251) would have increased kEV to ~+$0.094 — still below baseline CI lower (+$0.244). Even with best entry timing, VOLARB had no edge.

**Cross-strategy note (flag for LDA team):** The [60-100)s catastrophe (kEV=−$1.061, n=14) and [220-280)s underperformance validate LDA's late-window focus. LDA's rem_bucket B1=[0,60)s gate (blocked) and B2=[60,120)s preference directly address VOLARB's early-entry failure. If LDA B4 (rem 180-300s) shows negative EV at n≥100, VOLARB [220-280)s data provides corroborating historical precedent.

---

## Investigation H6 — Direction Asymmetry (up vs down)

**HYPOTHESIS:** VOLARB's `bond_outcome_direction` field ('up'/'down') may show meaningful EV asymmetry. Polymarket updown markets have a known bullish bias (crypto tends up); 'up' tokens may be systematically overpriced or underpriced relative to fair value.

**METHOD:** Slice VOLARB kline rows by `bond_outcome_direction`. Compute n, WR, kEV/$1-equiv, CI95, vs_baseline_CI. Compare to prior scout values (prior had field name correction this cycle; current confirms stability).

**RESULT:**

| Direction | n | kn | 12h Δ | WR% | kEV/$1 | CI95 (kline) | vs_baseline_CI |
|---|---|---|---|---|---|---|---|
| up | 393 | 389 | 0 | 30.0% | −$0.029 | [−0.197, +0.140] | **BELOW_CI** |
| down | 494 | 487 | 0 | 38.3% | −$0.019 | [−0.149, +0.111] | **BELOW_CI** |

*Prior scout kEV (corrected): 'up'=−$0.026, 'down'=−$0.024. 12h delta effectively zero (numerical noise only).*

**CONCLUSION: DISCARD (terminal re-confirm).** Both directions BELOW_CI. The difference in kEV between 'up' and 'down' is $0.010 — well within CI noise for both cells. No directional asymmetry exists in VOLARB data. The higher WR for 'down' (38.3% vs 30.0%) does not translate to positive kEV, suggesting 'up' positions were bought at better prices (lower entry_price) but still failed.

**FAILURE_MET:** No. n≥100 for both directions (393, 494) and both are BELOW_CI — confirms no usable directional signal.

**IF_DEPLOYED:** N/A — strategy retired.

---

## Investigation H7 — Watchlist Cell Trajectories (Terminal Closure)

**HYPOTHESIS:** Any watchlist cell could accumulate new trades or drift kEV between scout cycles. With VOLARB frozen at n=887, all 24h deltas should be zero.

**METHOD:** Compare current n and kEV for all previously flagged cells vs 12h prior values (from prior scout report). Flag any cell with |Δ kEV| > 2×SE as drift signal.

**RESULT:**

| Cell | Prior n | Now n | 12h Δ | kEV/$1 (now) | Prior kEV | Δ kEV | vs_baseline_CI |
|---|---|---|---|---|---|---|---|
| BTC | 286 | 286 | 0 | +$0.039 | +$0.039 | $0.000 | **BELOW_CI** |
| ETH | 305 | 305 | 0 | −$0.075 | −$0.075 | $0.000 | **BELOW_CI** |
| SOL | 296 | 296 | 0 | −$0.030 | −$0.030 | $0.000 | **BELOW_CI** |
| direction='up' | 393 | 393 | 0 | −$0.029 | −$0.026 | −$0.003 | **BELOW_CI** |
| direction='down' | 494 | 494 | 0 | −$0.019 | −$0.024 | +$0.005 | **BELOW_CI** |
| Ask [0.20,0.30) | 227 | 227 | 0 | −$0.053 | −$0.053 | $0.000 | **BELOW_CI** |
| Ask [0.30,0.40) | 390 | 390 | 0 | +$0.002 | +$0.002 | $0.000 | **BELOW_CI** |
| Ask [0.40,0.50) | 158 | 158 | 0 | −$0.004 | −$0.004 | $0.000 | **BELOW_CI** |

*Direction kEV deltas ($0.003/$0.005) are pure floating-point rounding at 3 decimal places; SE≈$0.087 for n=393 → <1/20th of 1σ. Not a drift signal.*

**CONCLUSION: DISCARD (terminal zero-delta).** All cells frozen. No cell drifted >2σ from prior. No Auditor escalation warranted.

**FAILURE_MET:** N/A — strategy retired; no actionable threshold can be met.

**IF_DEPLOYED:** N/A.

---

## Priority Signal for Next Implementation

**No actionable signal this cycle — VOLARB permanently retired, all investigations closed, dataset frozen at n=887.**

All H1–H7 investigations are closed:
- H1 (per-asset): BELOW_CI for BTC, ETH, SOL — closed
- H2 (per-hour): n<100 per hour, permanently INCONCLUSIVE — closed
- H3 (per-ask-band): All n≥100 bands BELOW_CI — closed
- H4 (longshot Phase 2): recorder never deployed, strategy retired — MOOT/closed
- H5 (seconds-to-resolution): [220-280)s BELOW_CI dominant bucket, confirmed — closed
- H6 (direction): Both directions BELOW_CI, no asymmetry — closed
- H7 (watchlist trajectories): zero delta, all BELOW_CI — closed

**Root cause (consolidated, unchanged from prior):** VOLARB's edge thesis was undermined by its entry-timing profile. 70% of entries (n=609) occurred at 220-280s remaining — the first 20-80s of a 300s window. This maximised adverse path exposure before Chainlink resolution. Even the best bucket ([100-160)s, kEV=+$0.221) fell within the CI of null under insufficient sample. The strategy's aggregate kEV=−$0.023 is $0.267 below the backtest's CI lower bound (+$0.244), a gap too large to be sampling error at n=876.

---

## Closed-Family Confirmations (re-validated null this cycle)

| Family | Confirmed null | Basis |
|---|---|---|
| VOLARB per-asset (H1) | zero-delta re-confirm | BTC/ETH/SOL all BELOW_CI, n≥283 each |
| VOLARB direction (H6) | zero-delta re-confirm | 'up'/'down' both BELOW_CI, kEV diff < $0.01 |
| VOLARB ask-band (H3) | zero-delta re-confirm (via H7) | all n≥100 bands BELOW_CI |
| VOLARB rem-slice [220-280)s | zero-delta re-confirm | 70% of entries, BELOW_CI at n=609 |

---

## Open Requests for Auditor / Human Review

**Capital anomaly (human review required):**
- SNIPER last trade capital_after=$27.98 at 2026-05-27T00:28:16Z
- bankroll.json capital=$95.304 at saved_ts 2026-05-27T11:25:51Z
- Unexplained +$67.3 gain with no matching trades in the database
- Most likely: user capital injection between 00:28Z and 11:25Z
- Action needed: human to confirm or deny capital injection; if confirmed, note in state_log.md

**Cells trending to n≥100:**
- None. VOLARB dataset frozen at n=887. No cells will grow further.

**Shadow loggers past threshold:**
- `shadow_volarb_longshot_shadow.jsonl`: 0 bytes. Was never deployed during VOLARB's active window. Strategy retired — MOOT.
- `exit_policy_shadow`: Active (for LDA strategy), not within VOLARB Scout scope.

**Phase 2 longshot recorder status:** MOOT. VOLARB retired before recorder could be deployed. Archival spec filed in prior scout cycle.

**New strategy context (flag for human / research_status.md update):**
- WEATHER strategy trades appear in trades.jsonl (n=17, 2026-05-21 to 2026-05-26, total net_pnl=−$11.66). Not documented in research_status.md (last updated 2026-05-16). Warrant a research_status.md update entry.
- Active strategy as of last trade: SNIPER (last 2026-05-27T00:28Z, capital_after=$27.98). LDA last fired 2026-05-17. research_status.md still lists LDA as "Active strategy" — may need update.

---

*This is the final VOLARB scout cycle. Dataset frozen, all investigations closed, strategy permanently retired. Future scout cycles should check research_status.md for the current active strategy (SNIPER/WEATHER/LDA) and pivot investigative scope accordingly.*
