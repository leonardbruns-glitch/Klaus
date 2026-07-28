# Gate-Keeper Report — 2026-07-28

**STALL (run 8)** — `system_status.txt`: `failed unknown` (systemd dead since 2026-07-24T10:09:19Z; day 4). Daily + liveness timers owner-disabled 2026-07-24; loop WEEKLY-ONLY since EVOLVE 2026-07-26. Zero new shadow data in any gate-relevant logger (2026-07-27 shadow dir contains only `badatmath_watch.jsonl`). All gates frozen. No state transitions.

**Capital**: $88.750373 ($21.50 CLOB + $67.25 owner-manual on-chain per EVOLVE 2026-07-26). Still $0.41 below engine ruin_floor $89.16 — band paths mechanically blocked. Burn rate: $0.

---

## Gate Ledger

| Gate | n (auth) | +24h | WR | ROI | CI95 | Status | ETA / Notes |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES (per slice) | 934 | +0 | 15.3% sim | +4.0% sim ⚠️ UB | [−10.9%, +21.1%] | AMBIGUOUS | Band dark day 22 (BAND_LIVE=False since Jul-06). ROI is upper bound — G3 winner's curse blocks sim-CI re-enable. Inert. |
| G2a BAND_NO shadow | 115 | +0 | 68.7% / live 39.2% | +1.3% | [−11.9%, +12.7%] | AMBIGUOUS | BAND_NO_ENABLED=False. Live sub-leg n=51 WR=39.2% effectively REJECTED — do not re-enable on shadow CI alone. |
| G2b PAIR_FAV_NO | 9 live | +0 | — | CF +52.9% (biased) | CF [+12.6%, +85.5%] biased | COLLECTING | Band dark; CF biased per state_log Jul-11. Inert. ETA: indeterminate. |
| G2c PAIR_FAV_YES | 9 live | +0 | — | — | — | COLLECTING | Band dark; inert. ETA: indeterminate. |
| G3 FILLED_vs_FIRED | 75 filled | +0 | 17.3% filled vs 7.6% sim | −75.8% filled | [−75.0%, −34.2%] | WATCH_ITEM | **Winner's curse CONFIRMED** (gap −83.4 pp). CI entirely negative. Hard blocker: no sim-CI argument may re-enable G1 or G7. |
| G4 BASKET_EXIT | — | — | — | — | — | VOID | Permanently retired 2026-06-22 (4 fatal flaws). |
| G5 THERMO_MAKER_NO | 125 | +0 | — | 0.0% net | [−9.0%, +2.0%] | **REJECTED** | THERMO_MAKER_LIVE=False since Jun-23. Candidate log only. No reconsideration without explicit human directive. |
| G6 M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | [−20.6%, +24.4%] | **REJECTED** | MIN_LOCKOUT_LIVE=False. 0.5°C floor revert recommendation stands. n=31 frozen; rejected by human directive Jul-04. No reconsideration without explicit human directive. |
| G7 SUM_POSTED 0.70–0.85 | 382 | +0 | — | +11.5% sim ⚠️ UB | [−11.4%, +38.9%] | AMBIGUOUS | Band dark day 22; inert. ROI upper bound per G3 winner's curse. ~147 shadow est since wind-down. ETA: indeterminate. |
| **G8 UPDOWN_CROSSING** | **127** | **+0** | **95.28%** | sim −$5.52 | **[90.1%, 97.8%]** WR-CI | **REJECTED** ✓ | Killed EVOLVE 2026-07-26 (commit ddbcecdd1). n=127, WR=0.9528 < BE=0.9651. Pooled 5-asset n=469 WR=0.964 < BE=0.965. Class closed; graveyard #15. No new data since kill. |

*⚠️ UB = sim ROI is upper bound; G3 winner's curse confirmed (n=75 filled WR 17.3% vs sim 7.6%). All n values frozen since system failed 2026-07-24.*

---

## State Transitions vs Prior Run (2026-07-27T09:20:00Z)

**None.** All gates unchanged. +0 on every counter. No new shadow data in any gate-relevant file for 2026-07-27 or 2026-07-28.

---

## Structural Blockers

| Blocker | Status |
|---|---|
| UPDOWN_STOP | Active since 2026-07-19T11:26Z (PF 0.79 < 0.80 charter rail) |
| BAND_LIVE=False | Active since 2026-07-06T22:08Z — day 22 |
| G3 WATCH_ITEM | Winner's curse confirmed; blocks all sim-CI G1/G7 re-enable |
| Capital vs ruin_floor | $88.75 < $89.16 — band paths blocked mechanically |
| G5 THERMO | REJECTED; no reconsideration without human directive |
| G6 M1 LOCKOUT | REJECTED; no reconsideration without human directive |
| G8 UPDOWN_CROSSING | REJECTED; class closed; graveyard #15; no live updown path |
| SYSTEM | Failed/unknown since 2026-07-24T10:09:19Z; weekly-loop-only mode |
| LDA | STOP active (rolling-20 PnL < −$30 threshold) |

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED this run.** All transitions occurred in prior runs. Nothing for human action.

- G8 kill receipt: documented by EVOLVE 2026-07-26 (commit ddbcecdd1). Confirm at owner's convenience — graveyard #15. No code action outstanding.
- System: SSH to VPS if/when path forward intended. Burn rate zero — timing not urgent.
- Capital: $88.75 is $0.41 below ruin_floor $89.16. Owner to decide on further injection.

---

*Run ts: 2026-07-28T~09:00Z | Snapshot ts: 2026-07-28T09:00:03Z (fresh) | System abort: `failed/unknown` | STALL run 8 | Band dark day 22 | Prior auth values: 2026-07-25T09:03:00Z (gates), 2026-07-27T09:20:00Z (G8)*
