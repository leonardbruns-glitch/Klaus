# Gate-Keeper Report — 2026-07-16

**Run timestamp:** 2026-07-16T09:13:40Z
**Snapshot:** 2026-07-16T09:05:16Z (age ~8 min — FRESH)
**Prior run:** 2026-07-15T09:15:00Z
**Band dark:** Day 10 (BAND_LIVE=False since 2026-07-06T22:08Z)
**Bankroll:** $31.07 (was $36.54 at prior run, **−$5.47 / −15.0%** — UPDOWN-SNIPER losses)
**Capital vs engine ruin floor ($89.16):** 34.9% (was 40.9%) — mechanically blocked
**Daily start Jul-16:** $33.86 | **Intraday PnL:** −$2.79 (daily stop = −$4.50, within limit)
**Open positions:** 0 (bankroll saved 07:31Z)

---

## STRUCTURAL BLOCKERS (unchanged)

1. **BAND_LIVE=False** (day 10) — zero resolutions flowing into any band gate. All n-counts frozen.
2. **Capital $31.07 < engine ruin_floor $89.16** — all band paths mechanically blocked.
3. **Winner's curse CONFIRMED** (G3, n=75): sim ROI is an UPPER BOUND. G1 and G7 AMBIGUOUS CI cannot serve as re-enable evidence.
4. **Pre-registered re-enable condition unmet:** pair_fav n≥40 requires BAND_LIVE=True first (n=9, frozen).
5. **VPS band_resolution_join.py** network-blocked in sandbox — no CLOB winner-flag refresh. Resolution truth requires VPS run.

---

## LEDGER TABLE

| Gate | n (resolved) | +24h Δn | WR | ROI | CI95 | Status | ETA to threshold |
|---|---|---|---|---|---|---|---|
| G1: BAND_YES | 934 | **0** | 15.3% | +4.0%\* | [−10.9, +21.1] | **AMBIGUOUS** | N/A — n≥threshold, CI straddles 0; band dark freezes resolutions |
| G2a: BAND_NO d+1 | 115 | **0** | 68.7% | +1.3% | [−11.9, +12.7] | **AMBIGUOUS** | N/A — BAND_NO_ENABLED=False; live n=51 WR=39.2% effectively REJECTED |
| G2b: PAIR_FAV YES | 9 | **0** | — | — | — | **COLLECTING** | ~8.3d from band re-enable (rate ~11/day) |
| G2c: PAIR_FAV NO | 9 | **0** | — | — | — | **COLLECTING** | ~8.3d from band re-enable; CF CI=[+12.6,+85.5] winner's-curse qualified |
| G3: FILLED_vs_FIRED | 75 (filled) | **0** | 17.3% | −75.8% (filled) vs +7.6% (sim) | [−75.0, −34.2] | **WATCH_ITEM** | 75≥40 — triggered; frozen (0 new band fills) |
| G4: BASKET_EXIT | — | — | — | — | — | **VOID** | Permanently retired (Jun-22) |
| G5: THERMO_MAKER_NO | 125 | **0** | — | 0.0% | [−9.0, +2.0] | **REJECTED** | Done |
| G6: M1_BETA_LOCKOUT | 31 | **0** | 74.2% | −0.6% | [−20.6, +24.4] | **REJECTED** | Done (EVOLVE Jul-04) |
| G7: SUM_POSTED [0.70,0.85] | 382 | **0** | — | +11.5%\* | [−11.4, +38.9] | **AMBIGUOUS** | N/A — n≥threshold, CI straddles 0; band dark freezes resolutions |

\*ROI marked with \* = **UPPER BOUND** per winner's curse analysis (state_log Jul-11 22:15Z). Do NOT cite as evidence for re-enable.

### Shadow Fire Counts (counterfactual only — no resolution truth)

| Gate | Shadow fires since wind-down | +24h new | Rate / day | All-time total |
|---|---|---|---|---|
| G1 (BAND_YES, all cities, dedup) | 123 (was 107) | **+16** | ~13.0/day (9.46d avg) | ~6,399 est. |
| G7 (sum_posted [0.70,0.85]) | 85 (was 72) | **+13** | ~9.0/day (9.46d avg) | ~3,175 |

**Jul-15 new (post-09:15Z):** +5 total fires, +4 in G7 range.
**Jul-16 new (00:00–09:05Z):** +11 total fires, +9 in G7 range.

Sample Jul-16 fires observed (d+1/d+2 heavy):
- Seoul d+1 sum_posted=0.80; Taipei d+1 0.84; Seoul d+2 0.84/0.76; Wuhan d+2 0.63/0.84;
  Shanghai d+2 0.84; Chongqing d+2 0.62/0.68; Chengdu d+2 0.61; London d+1 0.62; Munich d+2 (2×) 0.69/0.73

All counterfactual. No BAND_LIVE posts made.

---

## STATE TRANSITIONS vs PRIOR RUN

| Gate | Prior Status | Current Status | Change |
|---|---|---|---|
| G1 BAND_YES | AMBIGUOUS | AMBIGUOUS | No change |
| G2a BAND_NO d+1 | AMBIGUOUS | AMBIGUOUS | No change |
| G2b PAIR_FAV YES | COLLECTING | COLLECTING | No change |
| G2c PAIR_FAV NO | COLLECTING | COLLECTING | No change |
| G3 FILLED_vs_FIRED | WATCH_ITEM | WATCH_ITEM | No change |
| G4 BASKET_EXIT | VOID | VOID | No change |
| G5 THERMO_MAKER_NO | REJECTED | REJECTED | No change |
| G6 M1_BETA_LOCKOUT | REJECTED | REJECTED | No change |
| G7 SUM_POSTED | AMBIGUOUS | AMBIGUOUS | No change |

**No status transitions this run.** Band dark day 10 prevents all resolution-based gate movement.

---

## OBSERVATIONS (not gate decisions)

### Capital Draw-down Alert
Capital fell from **$36.54 → $31.07 (−$5.47, −15.0%)** since prior run. Source: UPDOWN-SNIPER operations. Capital trace (CAPITAL_CORRECTION records):

| Timestamp | Before | Delta | After | Note |
|---|---|---|---|---|
| Jul-15 15:34Z | $36.54 | −$4.37 | $32.17 | Sniper BUY |
| Jul-15 15:39Z | $32.17 | +$5.00 | $37.17 | Sniper WIN (+$0.63 net) |
| Jul-15 21:10Z | $37.17 | −$4.57 | $32.60 | Sniper BUY |
| Jul-15 21:15Z | $32.60 | +$5.00 | $37.60 | Sniper WIN (+$0.43 net) |
| Jul-15 21:30Z | $37.60 | −$9.11 | $28.49 | Sniper BUY ×2 |
| Jul-15 21:35Z | $28.49 | +$10.00 | $38.49 | Sniper WIN ×2 (+$0.89 net) |
| Jul-15 22:56Z | $38.49 | −$4.63 | $33.86 | Sniper BUY → **LOSS** (no settle seen) |
| *(daily start Jul-16: $33.86)* | | | | |
| Jul-16 02:50Z | $33.86 | −$4.37 | $29.49 | Sniper BUY |
| Jul-16 02:55Z | $29.49 | +$5.00 | $34.49 | Sniper WIN (+$0.63 net) |
| Jul-16 05:03Z | $34.49 | −$4.22 | $30.27 | Sniper BUY → **LOSS** (no settle seen) |
| Jul-16 07:26Z | $30.27 | −$4.19 | $26.08 | Sniper BUY |
| Jul-16 07:31Z | $26.08 | +$5.00 | $31.07 | Sniper WIN (+$0.81 net) |

Two losses since prior run: Jul-15 22:56Z (−$4.63) and Jul-16 05:03Z (−$4.22). Total loss basis: −$8.85. Total win basis: +$25.00. Net: −$5.47 over the 24h window (the Jul-15 22:56Z fire fired near end-of-day and resolved against without a matching +5 record).

Capital at 34.9% of engine ruin floor. Sniper daily stop is −$4.50; intraday Jul-16 at −$2.79 (within limit as of 07:31Z save).

**This is not a gate-ledger event.** Reported for completeness; Exec Auditor monitors sniper performance.

### G3 WATCH_ITEM: All Fills Remain UNTRACKED
- Jul-15/Jul-16 fill tape contains **6 new MAKER fills** and **22 new TAKER fills** (all UNTRACKED).
- MAKER fills: BUY@0.09 size=86.6 (Jul-16 04:35), BUY@0.06 size=16.7 (Jul-16 07:25), BUY@0.02 size=10.0 and SELL@0.98 size=1.14 (Jul-16 08:50). These are band-maker orphan fills (low-probability NO legs resolving), not STRUCT-BAND-Q entries.
- TAKER fills: all BUY@0.96–0.99 size=5.0–6.0 (UPDOWN-SNIPER pattern).
- Zero MAKER-FILL or STRUCT-BAND-Q entries in any fill in the log. **n=75 frozen.**
- Exec Auditor co-fill cross-tab for Jul-05 clip-guard period remains outstanding mandatory action.

### G5/G6: Shadow Candidates Only
- **G5 THERMO_MAKER**: 13,122 candidate records in thermo_maker.jsonl — all new since prior run. No resolutions possible (THERMO_MAKER_LIVE=False). Gate REJECTED; no reconsideration without human directive.
- **G6 M1_BETA_LOCKOUT**: 16,844 candidate records in metar_min_lockout.jsonl (end_dates: Jul-15 2,122 records; Jul-16 14,722 records). MIN_LOCKOUT_LIVE=False since Jul-13. Gate REJECTED.

### No New EVOLVE or State-Log Entries (Jul-16)
- Latest state_log entry: Jul-15 22:15Z (EVOLVE evening — KELLY stays OFF, sniper n=76 CI-lo < breakeven 96.2%).
- No Jul-16 entries in state_log as of snapshot time. System active (systemd: active, uptime since Jul-15 02:40:11Z).

---

## PROPOSED ACTIONS (human review)

**No gates newly READY or REJECTED this run.**

No flag or parameter changes are proposed by this report.

**Pending human actions carried forward:**
1. **G3 Exec Auditor cross-tab** (mandatory before any band re-enable): filled-leg co-fill rate for Jul-05 clip-guard period. Outstanding since Jul-11.
2. **Band re-enable path**: Requires (a) capital above engine ruin_floor $89.16 AND (b) pair_fav n≥40 post-guard. Both conditions unmet. No timeline.
3. **Sniper monitoring (non-gate)**: Two losses in 24h (Jul-15 22:56Z and Jul-16 05:03Z). 24h net −$5.47. Intraday Jul-16 −$2.79 within daily stop −$4.50 as of 07:31Z. Exec Auditor scope.

---

*Gate-Keeper is REPORT-ONLY. It does not edit strategy code or flip flags.*
*Resolution truth = CLOB/Gamma winner flags only. No price-drift proxies.*
*CI must clear zero before READY. A REJECTED verdict saves capital — stated plainly.*
*n=40–99 is a trend, never a decision. Below 40, just count.*
