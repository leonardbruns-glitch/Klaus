# Klaus Gate-Keeper Report — 2026-08-02T09:11:35Z

## ⚠ STALL #13 — ABORT TRIGGERED

**Abort reason:** `system_status.txt` missing `'klaus systemd: active'` — shows `failed/unknown`.
**System down since:** 2026-07-24T10:09:19Z (day **9** of failure).
**Loop mode:** WEEKLY-ONLY (daily + liveness timers owner-disabled 2026-07-24, per EVOLVE 2026-07-26).
**Snapshot age:** 11 min (PASS — threshold 6h).
**Shadow data:** Zero gate-relevant files (band_struct, thermo_maker, metar_lockout absent since system failure).
**No state transitions this run.** All gate counts frozen at prior values.

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI 95% | Status | ETA |
|------|---|------|----|-----|--------|--------|-----|
| G1 BAND_YES (all slices) | 934 | 0 | 15.3% | +4.0% | [−10.9%, +21.1%] | **AMBIGUOUS** | ∞ (band dark day 27) |
| G2a BAND_NO d+1 (shadow) | 115 | 0 | 68.7% | +1.3% | [−11.9%, +12.7%] | **AMBIGUOUS** | ∞ (NO disabled) |
| G2b PAIR_FAV YES (live post-guard) | 9 | 0 | — | — | — | **COLLECTING** | ∞ (band dark) |
| G2c PAIR_FAV NO (live post-guard) | 9 | 0 | — | — | — | **COLLECTING** | ∞ (band dark) |
| G3 FILLED_VS_FIRED (winner's curse) | 75 | 0 | 17.3% | −75.8% | [−75.0%, −34.2%] | **WATCH_ITEM** | n/a |
| G4 BASKET_EXIT | — | — | — | — | — | **VOID** | Permanently retired |
| G5 THERMO_MAKER_NO | 125 | 0 | — | 0.0% | [−9.0%, +2.0%] | **REJECTED** | n/a |
| G6 M1_BETA_LOCKOUT | 31 | 0 | 74.2% | −0.6% | [−20.6%, +24.4%] | **REJECTED** | n/a |
| G7 SUM_POSTED [0.70,0.85] | 382 | 0 | — | +11.5% | [−11.4%, +38.9%] | **AMBIGUOUS** | ∞ (band dark day 27) |
| G8 UPDOWN_CROSSING | 127 | 0 | 95.3% | — | [90.1%, 97.8%] | **REJECTED** | n/a (graveyard #15) |

**Notes on ROI bounds:**
- G1 ROI +4.0% is an **upper bound** — G3 winner's curse confirmed (filled WR 17.3% vs sim 7.6%, gap −83.4 pp).
- G7 ROI +11.5% is an **upper bound** for the same reason. Both gates inert while band is dark.
- G8 WR 95.3% < BE 96.51% at n=127; pooled 5-asset WR 96.4% < BE 96.5% — REJECTED is correct.

---

## State Transitions vs Prior Run (2026-08-01T09:15:00Z)

| Gate | Prior Status | Current Status | Change |
|------|-------------|----------------|--------|
| G1 BAND_YES | AMBIGUOUS | AMBIGUOUS | No change |
| G2a BAND_NO d+1 | AMBIGUOUS | AMBIGUOUS | No change |
| G2b PAIR_FAV YES | COLLECTING | COLLECTING | No change |
| G2c PAIR_FAV NO | COLLECTING | COLLECTING | No change |
| G3 FILLED_VS_FIRED | WATCH_ITEM | WATCH_ITEM | No change |
| G4 BASKET_EXIT | VOID | VOID | No change |
| G5 THERMO_MAKER_NO | REJECTED | REJECTED | No change |
| G6 M1_BETA_LOCKOUT | REJECTED | REJECTED | No change |
| G7 SUM_POSTED | AMBIGUOUS | AMBIGUOUS | No change |
| G8 UPDOWN_CROSSING | REJECTED | REJECTED | No change (kill executed EVOLVE 2026-07-26) |

**Informational counters:** STALL count 12 → **13**. Band dark day 26 → **27**. System failed day 8 → **9**.

---

## Structural Blockers (unchanged)

1. **UPDOWN_STOP active** — sniper CUT 2026-07-19T11:26Z (PF 0.79 < 0.80 charter rail). Class closed (G8 REJECTED + graveyard #15).
2. **WIND-DOWN active** — BAND_LIVE=False since Jul-06 22:08Z. Day **27**. Zero band resolutions flowing. All G1/G2/G7 counts frozen.
3. **LDA_STOP active** — rolling-20 worst −$36.39 below −$30 threshold. No LDA path.
4. **Capital $88.75 < ruin_floor $89.16** (below by $0.41) — all band paths mechanically blocked per charter.
5. **Winner's curse CONFIRMED** (G3, n=75) — sim ROI is upper bound; any sim-based READY verdict is biased.
6. **G5 THERMO / G6 M1** — both REJECTED; no reconsideration without explicit human directive.
7. **G8 UPDOWN_CROSSING** — REJECTED; graveyard #15. No live updown path. Class closed.
8. **SYSTEM FAILED** — day 9. Weekly-loop-only mode. No new data accruing on any gate.

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED this run.** Nothing to flip.

| Item | Action |
|------|--------|
| No new transitions | No flag/param changes needed |
| System continued failure (day 9) | SSH to VPS if path forward intended; burn rate is zero so timing is not urgent |
| Capital $88.75 (−$0.41 below ruin floor) | Owner to decide: injection to clear ruin floor, or charter amendment to redefine it |
| G8 kill receipt | Already formalized EVOLVE 2026-07-26 (commit ddbcecdd1, graveyard #15) — no further action |

**Bottom line:** System is down, all trading paths are closed, and no gate has moved. Nothing to do until the system is restarted or the human decides on a path forward. The gate ledger is frozen.
