# Gate-Keeper Report — 2026-07-18T09:11Z

**Snapshot:** 2026-07-18T08:55:38Z (age: 16 min — OK)
**System:** `klaus systemd: active`
**Bankroll:** $37.57 (+$5.81 since prior run; +$2.07 today vs daily start $35.50)
**Capital vs ruin floor:** $37.57 / $89.16 = **42.1%** (below floor — all band paths blocked)
**Band state:** WIND-DOWN active — BAND_LIVE=False since 2026-07-06T22:08Z (day **12**)
**Open positions:** 0
**Prior run:** 2026-07-17T09:15Z

---

## Gate Ledger

| # | Gate | n (resolved) | +24h res | Shadow +24h★ | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|---|---|
| G1 | BAND_YES (all slices) | 934 | +0 | +18 (→154 total) | 0.153 | +4.0% | [-10.9, +21.1] | **AMBIGUOUS** | N/A (band dark) |
| G2a | BAND_NO d+1 | 115 | +0 | — | 0.687 | +1.3% | [-11.9, +12.7] | **AMBIGUOUS** | N/A (band dark) |
| G2b | PAIR_FAV_YES | 9 | +0 | — | — | — | — | **COLLECTING** | ~8.3d from re-enable |
| G2c | PAIR_FAV_NO | 9 | +0 | — | — | — | — | **COLLECTING** | ~8.3d from re-enable |
| G3 | FILLED_VS_FIRED | 75★★ | +0★★ | — | 0.173 | -75.8% | [-75.0, -34.2] | **WATCH_ITEM** | WC confirmed |
| G4 | BASKET_EXIT | — | — | — | — | — | — | **VOID** | Permanent |
| G5 | THERMO_MAKER_NO | 125 | +0 | — | — | 0.0% | [-9.0, +2.0] | **REJECTED** | — |
| G6 | M1_BETA_LOCKOUT | 31 | +0 | — | 0.742 | -0.6% | [-20.6, +24.4] | **REJECTED** | — |
| G7 | SUM_POSTED [0.70, 0.85] | 382 | +0 | +8 (→100 total) | — | +11.5% | [-11.4, +38.9] | **AMBIGUOUS** | N/A (band dark) |

★ Shadow fire counts are **counterfactual only** — no resolution truth available while band is dark. They do not count toward CI thresholds.

★★ G3: n=75 conservatively frozen pending Exec Auditor classification. +11 new untracked fills since prior run (detail below). WC gap fully confirmed: sim ROI +7.6% vs filled ROI -75.8%, gap -83.4pp, CI entirely negative.

---

## State Transitions vs Prior (2026-07-17T09:15Z)

**No status changes this cycle.** All gates hold their prior status.

### Changes noted:

**G1 (BAND_YES):** Shadow fires since wind-down: 136 → **154** (+18 in 24h). Rate ~18/day (up from ~13/day — band engine scanning d+2 at higher cadence). Resolved n=934 frozen. ROI/CI unchanged.

**G3 (FILLED_VS_FIRED) — ALERT: 2nd anomalous MAKER SELL on record.**
- New fills since prior run (Jul-17 09:15Z → Jul-18 09:11Z):
  - 7 TAKER fills (sniper strategy; not G3-eligible)
  - 3 MAKER orphan-pattern BUY@0.02-0.06 (Jul-17 13:34Z BUY@0.06×33+25; Jul-17 18:34Z BUY@0.02×150; Jul-17 18:44Z BUY@0.02×78) — consistent with prior STRUCT-BAND-Q pattern, not anomalous
  - **1 new ANOMALOUS pair (Jul-18 00:54Z):** MAKER SELL@0.92 size=9.32 token=2664940529472113 **+** MAKER BUY@0.08 size=44.875 token=7094108612094851 — SELL-high + BUY-low pair on likely complementary legs
- Prior unclassified: Jul-16 21:39Z MAKER SELL@0.96 size=147.05 token=1399483673820402
- **Pattern now: 2× anomalous SELL@0.92-0.96 on record. Exec Auditor classification doubly overdue.** n held at 75 conservative until classified.

**G5 (THERMO_MAKER):** Shadow file now 3.7MB (prior ~3.6MB). Still REJECTED, no reconsideration.

**G6 (M1_BETA_LOCKOUT):** Shadow file (metar_min_lockout.jsonl) 8.1MB. Still REJECTED.

**G7 (SUM_POSTED [0.70,0.85]):** Shadow fires since wind-down: 92 → **100** (+8 in 24h). New fires:
- Jul-17 post-prior: Taipei d+1 0.843, Chongqing d+1 0.844, Wuhan d+1 0.758, Chengdu d+2 0.763, Wuhan d+1 0.786, Chengdu d+1 0.784
- Jul-18: Taipei d+2 0.725, Munich d+2 0.840
Resolved n=382 frozen. ROI/CI unchanged. Winner's curse blocker: ROI +11.5% is upper bound.

**Capital:** $31.76 → $37.57 (+18.4%). Sniper candidate 18/18W kill-watch CLEAN day 2. Capital remains below engine ruin floor — band paths blocked regardless of gate status.

---

## Structural Blockers (all band paths)

1. **WIND-DOWN active** — BAND_LIVE=False since Jul-06 22:08Z (day 12). Zero band resolutions flowing.
2. **Capital below engine ruin floor** — $37.57 = 42.1% of $89.16. All band scale-up paths mechanically blocked.
3. **Pre-registered re-enable condition unmet** — post-guard pair n≥40 (currently n=9, frozen).
4. **Winner's curse CONFIRMED** (G3 WATCH_ITEM, n=75): sim ROI is UPPER BOUND — no band re-enable may cite G1 or G7 sim CI as supporting evidence.
5. **G2a BAND_NO: live n=51 WR=39.2%** — effectively REJECTED; shadow CI AMBIGUOUS is irrelevant.
6. **Network-blocked sandbox** — band_resolution_join.py cannot run; all resolution n counts frozen at Jul-06 state.

---

## PROPOSED ACTIONS (human review)

**None this cycle.** No gate newly hit READY or REJECTED.

Standing items requiring human action:
- **[EXEC AUDITOR REQUIRED]** Classify 2 anomalous MAKER SELL fills before next G3 update:
  1. Jul-16 21:39Z SELL@0.96 size=147.05 token=1399483673820402 (overdue since Jul-17)
  2. Jul-18 00:54Z SELL@0.92 size=9.32 token=2664940529472113 (new this cycle; paired with BUY@0.08 size=44.875 token=7094108612094851)
- **[CAPITAL]** Engine ruin floor ($89.16) remains far above current capital ($37.57). No band action possible at this level.
