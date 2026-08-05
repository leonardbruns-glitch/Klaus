# Gate-Keeper Report — 2026-08-05

**ABORT: `system_status.txt` missing 'active' — shows `failed/unknown`. STALL day 16; system down since 2026-07-24T10:09:19Z.**

---

## Ledger Table

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES (all slices) | 934 | 0 | 15.3% | +4.0%† | [−10.9, +21.1%] | AMBIGUOUS | ∞ — band dark day 30 |
| G2a BAND_NO d1 (shadow) | 115 | 0 | 68.7% | +1.3% | [−11.9, +12.7%] | AMBIGUOUS | n/a — NO disabled |
| G2b PAIR_FAV YES (post-guard) | 9 | 0 | — | — | — | COLLECTING | ∞ — band dark day 30 |
| G2c PAIR_FAV NO (post-guard) | 9 | 0 | — | — | — | COLLECTING | ∞ — band dark day 30 |
| G3 FILLED-vs-FIRED | 75 | 0 | 17.3% filled | −75.8% | [−75.0, −34.2%] | WATCH_ITEM | confirmed; no accrual |
| G4 BASKET_EXIT | — | — | — | — | — | VOID | retired permanently |
| G5 THERMO_MAKER_NO | 125 | 0 | — | 0.0% | [−9.0, +2.0%] | REJECTED | closed |
| G6 M1_BETA_LOCKOUT | 31 | 0 | 74.2% | −0.6% | [−20.6, +24.4%] | REJECTED | closed |
| G7 SUM_POSTED [0.70, 0.85] | 382 | 0 | — | +11.5%† | [−11.4, +38.9%] | AMBIGUOUS | ∞ — band dark day 30 |
| G8 UPDOWN_CROSSING | 127 | 0 | 95.3% | — | CI-lo 90.1% < BE 96.5% | REJECTED | closed (graveyard #15) |

† UPPER BOUND — winner's curse confirmed via G3 (filled WR 17.3% vs sim 7.6%; n=75, CI entirely negative).

---

## State Transitions vs Prior (2026-08-04T09:10Z)

None. All gates frozen.

| Informational counter | Prior | Now |
|---|---|---|
| STALL count | 15 | **16** |
| System failed (days) | 11 | **12** |
| Band dark (days) | 29 | **30** |
| n added across all gates | 0 | **0** |

---

## Structural Blockers (all carry forward)

1. **UPDOWN_STOP**: sniper CUT 2026-07-19 (PF 0.79 < 0.8 charter rail). G8 REJECTED graveyard #15. No live updown path.
2. **BAND_DARK day 30**: BAND_LIVE=False since 2026-07-06T22:08Z. Zero band resolutions. G1, G2, G7 frozen.
3. **LDA_STOP**: rolling-20 worst −$36.39 < −$30 threshold.
4. **CAPITAL $88.75** below engine ruin_floor $89.16 (by $0.41). All band paths mechanically blocked.
5. **WINNER'S CURSE (G3)**: filled ROI −75.8% vs sim +7.6%; n=75, CI=[−75%, −34.2%]. Sim figures on G1/G7 are upper bounds only.
6. **SYSTEM**: failed/unknown day 12 (since 2026-07-24T10:09:19Z). Weekly-loop-only mode.
7. **G5, G6**: REJECTED by human directive. No reconsideration without explicit instruction.

---

## PROPOSED ACTIONS (human review)

**No newly READY or REJECTED gates this run. No flag or param changes to propose.**

- G8 kill receipt already formalized (EVOLVE 2026-07-26, commit `ddbcecdd1`, graveyard #15). No further action.
- System SSH: required if path forward intended. Burn rate zero — timing owner's discretion.
- Capital: $88.75 is $0.41 below ruin_floor $89.16. Owner to decide on injection or charter amendment.
- All gate ETA clocks paused indefinitely while band dark + system failed.
