# Gate-Keeper Stall Report — 2026-07-26

**STALL** — `system_status.txt`: `failed unknown` (6th consecutive network/service stall since 2026-07-24). Snapshot fresh (09:07:33Z). Gates frozen. Exiting. **G8 n=100 THRESHOLD LIKELY CROSSED (est n=105–127) — kill formalization pending VPS restart.**

---

## Gate Ledger (frozen — stall run, no new resolutions)

| Gate | n (auth) | +24h est | WR | ROI | CI95 | Status | ETA / Notes |
|------|-----------|----------|----|-----|------|--------|-------------|
| G1 BAND_YES | 934 | 0 | 15.3% | +4.0% | [−10.9, +21.1] | AMBIGUOUS | Band dark d20; inert. ROI is upper bound (G3 winner's curse). |
| G2a BAND_NO (shadow) | 115 | 0 | 68.7% | +1.3% | [−11.9, +12.7] | AMBIGUOUS | BAND_NO_ENABLED=False. Live n=51 WR=39.2% effectively REJECTED — do not re-enable on shadow CI alone. |
| G2b PAIR_FAV_NO | 9 live | 0 | — | CF +52.9% | CF [+12.6, +85.5] (biased) | COLLECTING | Band dark; CF biased per state_log Jul-11. Inert. |
| G2c PAIR_FAV_YES | 9 live | 0 | — | — | — | COLLECTING | Band dark; inert. |
| G3 FILLED_vs_FIRED | 75 | 0 | 17.3% | −75.8% | [−75.0, −34.2] | WATCH_ITEM | Winner's curse CONFIRMED (n=75 filled WR 17.3% vs sim 7.6%, gap −83.4 pp). CI entirely negative. Hard blocker on G1/G7 sim-CI re-enable arguments. |
| G4 BASKET_EXIT | — | — | — | — | — | VOID | Retired permanently Jun-22. |
| G5 THERMO_MAKER_NO | 125 | 0 | — | 0.0% | [−9.0, +2.0] | **REJECTED** | THERMO_MAKER_LIVE=False. No reconsideration without explicit human directive. |
| G6 M1_BETA_LOCKOUT | 31 | 0 | 74.2% | −0.6% | [−20.6, +24.4] | **REJECTED** | MIN_LOCKOUT_LIVE=False. 0.5C floor revert recommendation stands (state_log 2026-06-09). No reconsideration without explicit human directive. |
| G7 SUM_POSTED 0.70–0.85 | 382 | 0 | — | +11.5% | [−11.4, +38.9] | AMBIGUOUS | Band dark; inert. ROI is upper bound (G3 winner's curse). Gate inert while band dark. |
| G8 UPDOWN_CROSSING | 88 auth / **~105–127 est** | **+7–16 est** | 95.5% auth (84W/4L) | — | [88.9%, 98.2%] (at n=88) | **KILL-LOCKED** | **n=100 LIKELY CROSSED.** shadow_grade.py required to confirm. Kill math immutable (BE=96.49%, min-n-to-clear=114). |

*n_added_since_prior: 0 confirmed for all gates (stall). G8 +24h est = additional accrual at [7,16] events/day.*

---

## State Transitions vs Prior Run (2026-07-25T09:03:00Z)

- **No gate status changes.** Sixth consecutive stall (systemd failed since after 2026-07-24T10:09:19Z).
- **G8 n estimate updated:** prior est 95–111 → **now 105–127** (+24h at [7,16]/day; 59h elapsed since auth Jul-23 22:05Z at n=88).
- **n=100 threshold: CROSSED WITH HIGH PROBABILITY.** Even at the slow-rate floor (7/day), est n=105. Kill formalization is mathematically certain and now likely already threshold-qualified.
- **Band dark:** day 19 → **day 20.** No band resolutions flowing; G1/G7 gates inert.
- **Winner's curse blocker:** G3 WATCH_ITEM holds. No sim-CI argument may be used to re-enable any band path.

---

## PROPOSED ACTIONS (human review)

*No gates newly confirmed READY or REJECTED via authoritative data this run (stall — network blocked, VPS service failed).*

**CRITICAL — G8 UPDOWN_CROSSING KILL (pending VPS confirmation):**
- After VPS restart: `python3 analysis/crypto/shadow_grade.py --refetch` to confirm n and final WR
- If n ≥ 100 confirmed → **CLOSE UPDOWN_CROSSING class.** Do not re-enable without fresh pre-registration and a clean candidate pool.
- Math: best-case at n=100 is 96W/4L = WR 96.0% < BE 96.49%. Min n-to-clear = 114 (zero further losses — unrealistic). BTC cell already REJECTED at n=134. 4/5 asset cells net-negative sim.
- Human confirms the close; gate-keeper records REJECTED on next run.

**SYSTEM:**
- SSH to VPS. Diagnose systemd failure. Restart service.
- Burn rate: $0 (UPDOWN_STOP active Jul-19 + BAND_LIVE=False Jul-06 + LDA_STOP). No capital at risk from downtime.
- Capital $21.495 = 24.1% of ruin floor $89.16 — all band paths mechanically blocked regardless of gate status.

---

*Run ts: 2026-07-26T09:07:33Z (snapshot ts). Abort: system_status.txt missing 'active' (failed/unknown). Gate data frozen at 2026-07-25T09:03:00Z. 6th consecutive stall.*
