# Gate-Keeper Report — 2026-07-31T09:15:00Z

## !! STALL (day 11) — `system_status.txt` shows `failed/unknown`, not `active` — no new accumulation possible !!

**Snapshot**: 2026-07-31T09:02:33Z (age ~13 min at run time, within 6h limit).  
**System**: failed since 2026-07-24T10:09:19Z — **day 7**.  
**Loop mode**: WEEKLY-ONLY (daily + liveness timers owner-disabled 2026-07-24 per EVOLVE 2026-07-26).  
**Network**: git fetch timed out (11th consecutive stall). All gate counts carried from prior authoritative sources. Zero new shadow data confirmed: no gate-relevant loggers (band_struct, thermo_maker, metar_lockout) have written since 2026-07-24T10:09Z.  
**Capital**: $88.750373 — **$0.41 below ruin floor $89.16** (all band paths mechanically blocked).  
**Open positions**: 0.

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA / Notes |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES per slice | 934 | +0 | 15.3% | +4.0% | [−10.9, +21.1]% | AMBIGUOUS | Band dark day 25; ROI is upper bound (G3 WC confirmed); capital $0.41 below ruin floor; gate inert |
| G2a BAND_NO_d1 (shadow) | 115 | +0 | 68.7% | +1.3% | [−11.9, +12.7]% | AMBIGUOUS | BAND_NO_ENABLED=False; live n=51 WR=39.2% effectively REJECTED — shadow CI cannot override live result |
| G2b PAIR_FAV_YES | 9 | +0 | — | — | [—, —] | COLLECTING | Frozen (band dark day 25); ETA indeterminate |
| G2c PAIR_FAV_NO | 9 | +0 | — | — | [—, —] | COLLECTING | CF ROI (52.9%) biased by winner's curse (confirmed Jul-11); ETA indeterminate |
| G3 FILLED_vs_FIRED | 75 | +0 | 17.3% | −75.8% | [−75.0, −34.2]% | WATCH_ITEM | Winner's curse CONFIRMED; CI entirely negative; hard blocker on G1/G7 re-enable arguments |
| G4 BASKET_EXIT | — | — | — | — | — | **VOID** | PERMANENTLY RETIRED Jun-22 (4 fatal flaws); do not revisit |
| G5 THERMO_MAKER_NO | 125 | +0 | — | 0.0% | [−9.0, +2.0]% | **REJECTED** | ROI net fees is −EV; THERMO_MAKER_LIVE=False; no reconsideration without human directive |
| G6 M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | [−20.6, +24.4]% | **REJECTED** | Human directive EVOLVE Jul-04; MIN_LOCKOUT_LIVE=False; revert-to-0.5C-floors recommendation stands |
| G7 SUM_POSTED [0.70,0.85] | 382 | +0 | — | +11.5% | [−11.4, +38.9]% | AMBIGUOUS | Upper bound (G3 WC); band dark day 25; band_resolution_join.py blocked; gate inert |
| G8 UPDOWN_CROSSING | 127 | +0 | 95.3% | — | WR-CI [90.1, 97.8]% | **REJECTED** | Graveyard #15; WR 95.3% < BE 96.51%; pooled 5-asset n=469 WR 96.4% < BE 96.5%; killed EVOLVE 2026-07-26; class closed |

---

## State Transitions vs Prior Run (2026-07-30T09:15:00Z)

**No transitions.** All gates frozen. Informational increments only:
- Band dark: day 24 → **day 25**
- System failed: day 6 → **day 7**
- Stall count: 10 → **11**

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED this run — no flag/param changes proposed.**

### Standing structural blockers (unchanged):
1. **UPDOWN_STOP**: Sniper CUT 2026-07-19T11:26Z (PF 0.79 < 0.8 charter rail). G8 UPDOWN_CROSSING REJECTED → graveyard #15 (EVOLVE 2026-07-26). No updown path remains.
2. **WIND-DOWN**: BAND_LIVE=False since 2026-07-06T22:08Z — day 25. No band resolutions flowing. G2b/G2c/G7 accumulation frozen.
3. **LDA_STOP**: Rolling-20 worst −$36.39 below −$30 threshold. No LDA fires.
4. **Capital below ruin floor**: $88.75 < $89.16 (by $0.41) — mechanically blocks all band paths even if BAND_LIVE were re-enabled.
5. **G3 winner's curse CONFIRMED** (n=75, filled WR 17.3% vs sim 7.6%): G1 ROI +4.0% and G7 ROI +11.5% are ceiling estimates, not true expected values.
6. **G5 / G6**: REJECTED by prior EVOLVE human decisions; no reconsideration without explicit human directive.
7. **System failed day 7**: Burn rate zero. SSH to VPS if/when path forward intended. No urgency on timing.

### Summary:
No live trading paths remain. Next gate accumulation requires: (a) VPS restart + systemd service re-enable, AND (b) capital injection to clear ruin floor ($89.16), AND (c) explicit human decision on BAND_LIVE re-enable. Gate verdicts cannot change until the system fires again.
