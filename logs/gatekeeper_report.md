# Gate-Keeper Report — 2026-07-19T09:19Z

**Snapshot**: 2026-07-19T09:10:39Z (9 min old — OK)  
**Klaus systemd**: active  
**Band**: dark day 13 (BAND_LIVE=False since 2026-07-06T22:08Z)  
**Prior run**: 2026-07-18T09:11Z  
**Capital**: $21.495 ← was $37.569 Jul-19 daily-start = **−$16.07 (−42.8%) INTRADAY ⚠**

---

## Gate Ledger

| Gate | n (resolved) | +24h n | WR | ROI % | CI95 | Status | ETA to threshold |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES | 934 | +0 res / +9 shadow | 0.153 | +4.0 † | [−10.9, +21.1] | AMBIGUOUS | ∞ (frozen; WC blocker) |
| G2a BAND_NO | 115 | +0 | 0.687 | +1.3 | [−11.9, +12.7] | AMBIGUOUS ‡ | ∞ (frozen; live n=51 WR=39.2% eff. REJECTED) |
| G2b PAIR_FAV_YES | 9 | +0 | — | — | — | COLLECTING | ~8d from band re-enable |
| G2c PAIR_FAV_NO | 9 | +0 | — | — | — | COLLECTING | ~8d from band re-enable |
| G3 FILLED_vs_FIRED | 75 | +0 | 0.173 | −75.8 | [−75.0, −34.2] | WATCH_ITEM | n/a |
| G4 BASKET_EXIT | VOID | — | — | — | — | VOID | Permanently retired (Jun-22) |
| G5 THERMO_MAKER_NO | 125 | +0 | — | 0.0 | [−9.0, +2.0] | REJECTED | Inert (EVOLVE Jul-04) |
| G6 M1_BETA_LOCKOUT | 31 | +0 | 0.742 | −0.6 | [−20.6, +24.4] | REJECTED | Inert (EVOLVE Jul-04) |
| G7 SUM_POSTED [0.70,0.85] | 382 | +0 res / +7 shadow | — | +11.5 † | [−11.4, +38.9] | AMBIGUOUS | ∞ (frozen; WC blocker) |

† ROI is **UPPER BOUND** (winner's curse confirmed via G3 n=75; simulation CI must not be cited as re-enable evidence).  
‡ G2a shadow CI straddles 0 (AMBIGUOUS) but live n=51 WR=39.2% is effectively REJECTED. Do not re-enable BAND_NO on shadow CI alone.

---

## State Transitions vs Prior Run (2026-07-18T09:11Z)

**None.** All gate statuses identical to prior run.

Structural blockers unchanged:
- BAND_LIVE=False (day 13). Zero new resolutions flowing.
- Capital $21.495 = 24.1% of band-engine ruin floor $89.16 — all band paths mechanically blocked.
- Winner's curse CONFIRMED (G3 WATCH_ITEM, n=75): sim ROI is upper bound; G1 and G7 AMBIGUOUS CI must not trigger re-enable.
- G2b/G2c PAIR_FAV: n=9 each, frozen. Pre-condition n≥40 still unmet.
- G2a BAND_NO: BAND_NO_ENABLED=False since Jul-02; live WR 39.2% effectively REJECTED.
- G5/G6: REJECTED; no live orders; no reconsideration without explicit human directive.

---

## Shadow Accumulation (counterfactual only — no resolution truth while band dark)

| Logger | Jul-18 09:11Z | +24h | Jul-19 09:10Z | Rate/day |
|---|---|---|---|---|
| G1 shadow fires (since wind-down Jul-06) | 154 | **+9** | **163** | ~13 |
| G7 shadow fires (since wind-down Jul-06) | 100 | **+7** | **107** | ~8.6 |
| thermo_maker.jsonl (bytes, hot) | 3,699,026 | +360,524 | 4,059,550 | — |
| metar_lockout.jsonl (bytes, hot) | 8,102,573 | +374,454 | 8,477,027 | — |

**G1 +9 shadow fires (Jul-19 00:03–07:45Z)**:  
Beijing d+1 (sum=0.679) · Wuhan d+1 (0.662) · Tokyo d+2 (0.790) · Taipei d+2 (0.790) · Wuhan d+2 (0.795) · Chongqing d+2 (0.805) · Beijing d+2 (0.825) · Munich d+2 (0.765) · London d+1 (0.815)

**G7 +7 fires in [0.70,0.85]**:  
Tokyo 0.790 · Taipei 0.790 · Wuhan d+2 0.795 · Chongqing 0.805 · Beijing d+2 0.825 · Munich 0.765 · London d+1 0.815  
(Beijing d+1 0.679 and Wuhan d+1 0.662 below 0.70 floor — not G7-eligible)

---

## G3 New Fills Since Prior Run

7 new entries in maker_fills_recent.log since Jul-18 09:11Z. **0 are STRUCT_BAND_Q fills** — G3 n stays at 75.

| Time (UTC) | Type | Price | Size | Classification |
|---|---|---|---|---|
| Jul-18 23:19 | TAKER BUY | 0.98 | 19.5 | UPDOWN-SNIPER |
| Jul-19 00:24 | TAKER BUY | 0.88 | 21.3 | UPDOWN-SNIPER |
| Jul-19 02:14 | MAKER BUY | 0.02 | 146.33 | Orphan-pattern (4th on record) |
| Jul-19 02:44 | TAKER BUY | 0.91 | 22.75 | UPDOWN-SNIPER |
| Jul-19 03:24 | TAKER BUY | 0.98 | 22.0 | UPDOWN-SNIPER |
| Jul-19 07:59 | TAKER BUY | 0.94 | 23.5 | UPDOWN-SNIPER |

G3 n conservatively held at 75 until Exec Auditor classifies the Jul-16 SELL@0.96 and Jul-18 SELL@0.92 anomalous SELL pairs. Fourth orphan-pattern MAKER BUY@0.02 (Jul-19 02:14Z, token 5717613…) joins the pattern — also awaiting classification.

---

## ⚠ Capital Alert (outside pre-registered gate scope — human awareness only)

Capital collapsed $37.569 → $21.495 intraday Jul-19 (**−$16.07, −42.8%**). 0 open positions at snapshot — all trades settled. Cause: 5 TAKER UPDOWN-SNIPER BUYs at 0.88–0.98 (Jul-18 23:19Z through Jul-19 07:59Z) with at least 1–2 NO resolutions implied. Kill-watch was CLEAN day 3 (21/21W +$11.54) at the Jul-18 22:08Z state_log entry. Post-midnight kill-watch state **unknown** — no Jul-19 EVOLVE commit visible at snapshot time. Human review required to verify halt rule status.

---

## PROPOSED ACTIONS (human review)

**No gates newly READY or REJECTED. No flag or parameter changes proposed.**

Human review requested on two outstanding items:

1. **⚠ Capital collapse −$16.07 (Jul-19 intraday)**: Confirm sniper kill-watch status; verify whether any halt rule was triggered. PnL ledger commit for Jul-19 not yet posted at snapshot time.
2. **G3 Exec Auditor backlog**: Jul-16 SELL@0.96 + Jul-18 SELL@0.92 anomalous SELLs + 4th orphan MAKER BUY@0.02 unclassified. G3 n stuck at 75 until resolved.

---
*ready=0 rejected=0 collecting=3 ambiguous=3 watch_item=1 void=1 (G5/G6 rejected inert)*
