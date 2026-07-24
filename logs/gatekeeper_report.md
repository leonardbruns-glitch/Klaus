# Gate-Keeper Report — 2026-07-24

**Generated:** 2026-07-24T09:12Z
**SNAPSHOT:** 2026-07-24T09:00:04Z (12 min old — PASS)
**System:** `active` (PASS)
**Prior run:** 2026-07-23T09:00:00Z

---

## Context

Zero active trading paths. UPDOWN_STOP (since 2026-07-19T11:26Z) + BAND_LIVE=False (since 2026-07-06T22:08Z) + LDA_STOP (rolling-20 worst −$36.39 < −$30 threshold). Equity $21.4954 cash (CLOB-exact, on-chain confirmed morning Jul-23) = 24.1% of ruin_floor $89.16. All band/STWA/ladder paths mechanically blocked. Burn rate zero; shadow accrues free.

**Network blocked — 4th consecutive run.** shadow_grade.py, band_resolution_join.py, maker_fills_recent.log unrunnable from this container. G8 data sourced from `data/gate_ledger_latest.md` refreshed by EVOLVE at 2026-07-23T22:05Z (authoritative shadow_grade.py run on VPS). G1/G7 n frozen (no resolution flow while band dark).

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA to threshold |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES | 934 | 0 | 15.3% | +4.0% ↑ | [−10.9, +21.1%] | AMBIGUOUS | N/A — band dark, no accrual |
| G2a BAND_NO d+1 shadow | 115 | 0 | 68.7% | +1.3% ↑ | [−11.9, +12.7%] | AMBIGUOUS | N/A — band dark, no accrual |
| G2b PAIR_FAV_YES (live) | 9 | 0 | — | — | — | COLLECTING | N/A — frozen (band dark) |
| G2c PAIR_FAV_NO (live) | 9 | 0 | — | — | — | COLLECTING | N/A — frozen (band dark) |
| G3 FILLED_VS_FIRED | 75 | 0 | 17.3% filled | −75.8% | [−75.0, −34.2%] | WATCH_ITEM | N/A — no new fills possible |
| G4 BASKET_EXIT | — | — | — | — | — | **VOID** | — (permanently retired) |
| G5 THERMO_MAKER_NO | 125 | 0 | — | 0.0% net fees | [−9.0, +2.0%] | **REJECTED** | — |
| G6 M1_BETA_LOCKOUT | 31 | 0 | 74.2% | −0.6% | [−20.6, +24.4%] | **REJECTED** | — |
| G7 SUM_POSTED [0.70,0.85] | 382 | 0 | — | +11.5% ↑ | [−11.4, +38.9%] | AMBIGUOUS | N/A — band dark, no accrual |
| **G8 UPDOWN_CROSSING p≥0.995 5m** | **88** | **+16** | **95.45% (84W/4L)** | **−$5.52 sim** | **[88.9%, 98.2%]** | **COLLECTING ⚠ KILL-LOCKED** | **~Jul-25 (7/day)** |

↑ = **UPPER BOUND.** G3 winner's curse confirmed (n=75 filled: WR 17.3%, ROI −75.8%; vs sim ROI +7.6%; gap −83.4 pp; CI entirely negative). No G1 or G7 re-enable argument may cite sim ROI as evidence.

---

## State Transitions vs Prior Run

| Gate | Prior status | Current status | Change |
|---|---|---|---|
| G1 BAND_YES | AMBIGUOUS | AMBIGUOUS | No change — band dark day 18 |
| G2 BAND_NO / PAIR_FAV | AMBIGUOUS / COLLECTING | AMBIGUOUS / COLLECTING | No change — frozen |
| G3 FILLED_VS_FIRED | WATCH_ITEM | WATCH_ITEM | No change |
| G4 BASKET_EXIT | VOID | VOID | — |
| G5 THERMO_MAKER_NO | REJECTED | REJECTED | No change |
| G6 M1_BETA_LOCKOUT | REJECTED | REJECTED | No change |
| G7 SUM_POSTED | AMBIGUOUS | AMBIGUOUS | No change — band dark |
| **G8 UPDOWN_CROSSING** | COLLECTING n=72, 70W/2L | COLLECTING n=88, 84W/4L | **+16 events. KILL-LOCKED: kill unavoidable at n≥100.** |

**Only meaningful change this run: G8 advanced from n=72 → n=88 (+16 confirmed events, 24h window). Gate remains COLLECTING (n<100). Kill-locked mathematics established by gate_ledger_latest.md (Jul-23 22:05Z, shadow_grade.py authoritative).**

---

## G8 Deep-Dive: UPDOWN_CROSSING Kill Math

Source: `data/gate_ledger_latest.md` — refreshed 2026-07-23T22:05Z by EVOLVE evening slot using shadow_grade.py --refetch on VPS.

| Metric | Value | Note |
|---|---|---|
| n (post-cut, confirmed) | 88 | As of Jul-23 22:05Z; SETTLE count confirmed by gate_ledger |
| Wins / Losses | 84W / 4L | Per shadow_grade.py |
| Point WR | 95.45% | 84/88 |
| Breakeven WR | 96.49% | EVOLVE-reported (Jul-23 22:05Z); varies slightly by asset mix |
| Wilson CI-lo (95%) | 88.9% | z=1.96, Wilson; gap vs BE = −7.6 pp (worsened from −6.6 pp prior run) |
| Wilson CI-hi (95%) | 98.2% | |
| Best-case at n=100 | 96/100 = 96.0% | Assumes 0 further losses — unrealistic |
| Best-case WR vs BE | 96.0% < 96.49% | **KILL unavoidable by point rule** |
| Accrual rate (last 10.5h) | ~7/day | Slowed from 13–16/day earlier; 85→88 in ~10.5h |
| ETA to n=100 | ~Jul-25 | +12 events @ 7/day from Jul-23 22:05Z |

**Pre-registered kill rule:** "if point_WR_post_cut < BE at n≥100, recommend class CLOSED." This condition is now mathematically guaranteed: even the best conceivable path (zero further losses) yields WR=96.0% which is below BE=96.49%. The kill executes when n≥100 lands (~Jul-25 at current rate). No human review needed to await n=100; the math is closed today.

**Per-asset grades (updown_asset_grade.py, Jul-23 21:56Z — ALL-HISTORY, not post-cut isolation):**

| Asset | graded n (all) | WR | BE | pnl | Verdict |
|---|---|---|---|---|---|
| btc | 134 | 96.3% CI [91.6%, 98.4%] | 96.3% | −$0.65 | **REJECTED** — point at BE, CI-lo far below |
| doge | 20 | 95.0% (19W/1L) | 96.1% | −$1.06 | COLLECTING |
| eth | 38 | 100% (38/38) CI [90.8%, 100%] | 96.8% | +$6.32 | COLLECTING — **sole loss-free cell** |
| sol | 17 | 94.1% (16W/1L) | 96.5% | −$2.36 | COLLECTING |
| xrp | 23 | 91.3% (21W/2L) | 96.1% | −$5.67 | COLLECTING — worst cell |

**Cross-cell read:** 4 of 5 assets net-negative sim. BTC (only n≥100 cell) REJECTED. ETH's 38/38 matches the pattern every other cell showed before losses arrived — it is not a re-enable signal, just early phase. The certainty-taker class (buy ~0.96 avg ask at p≥0.995 certainty) is failing uniformly wherever n grows.

---

## Gate Notes (unchanged from prior)

**G1 BAND_YES:** Band dark day 18 (BAND_LIVE=False since Jul-06 22:08Z). n=934 frozen. ROI +4.0% is UPPER BOUND per G3 winner's curse (confirmed adversarial selection at n=75 filled). CI straddles 0 → AMBIGUOUS. Gate inert until BAND_LIVE re-enable AND equity > ruin_floor ($89.16). Currently $21.50 = 24.1% of floor — both conditions unmet.

**G2a BAND_NO d+1:** Shadow CI AMBIGUOUS (CI straddles 0). Live n=51 WR=39.2% = effectively REJECTED. Do NOT re-enable on shadow CI alone.

**G2b/c PAIR_FAV:** n=9, frozen at BAND_LIVE=False Jul-06. Counterfactual CI on pair_fav_no ([12.6, 85.5]) is biased (winner's curse, state_log Jul-11 22:15Z). Do not cite CF ROI.

**G3 FILLED_VS_FIRED:** Winner's curse CONFIRMED (filled WR 17.3% vs sim WR 7.6%). Hard blocker: no G1 or G7 re-enable may cite sim CI as evidence of positive EV. 4 Exec Auditor items outstanding (Jul-16 SELL@0.96, Jul-18 SELL@0.92, Jul-18 BUY@0.08, Jul-19 orphan BUY@0.02). Blocked on network for 4th consecutive run.

**G5 THERMO_MAKER_NO:** REJECTED (EVOLVE Jul-04 21:53Z). CI straddles 0 but ROI=0.0% net of fees = −EV after costs. No reconsideration without explicit human directive.

**G6 M1_BETA_LOCKOUT:** REJECTED (EVOLVE Jul-04 21:53Z, human decision). MIN_LOCKOUT_LIVE=False. Revert-to-0.5C-floors recommendation stands (state_log 2026-06-09). Shadow file (metar_lockout.jsonl) growing inertly. No reconsideration without explicit human directive.

**G7 SUM_POSTED [0.70,0.85]:** n=382, ROI +11.5% (UPPER BOUND — winner's curse). CI straddles 0 → AMBIGUOUS. Band dark, inert. Shadow fires accumulating (est. 143+ since wind-down) but unresolvable without band live.

---

## Structural Blockers

1. UPDOWN_STOP active (Jul-19 11:26Z): sniper CUT (PF 0.79 over 27 settles < 0.8 charter rail).
2. BAND_LIVE=False (Jul-06 22:08Z): wind-down, day 18. Zero band paths available.
3. LDA_STOP active: rolling-20 worst −$36.39 < −$30 threshold.
4. Equity $21.50 < ruin_floor $89.16 (24.1%): all band/NEG_RISK/RECYCLE paths mechanically blocked.
5. G3 winner's curse confirmed: sim ROI is an upper bound. No re-enable argument may cite G1/G7 sim CI.
6. G5 THERMO, G6 M1: both REJECTED; no reconsideration without explicit human directive.
7. G8 UPDOWN_CROSSING: KILL-LOCKED at n=88. Kill mathematically certain at n≥100 (~Jul-25). No re-enable path visible.

---

## PROPOSED ACTIONS (human review)

**No gates newly READY or REJECTED this run (n=88 < threshold 100).**

### Pending mandatory action — G8 kill formalizes at n=100 (~Jul-25)

When G8 post-cut n reaches 100, the pre-registered kill rule triggers: point WR < BE (guaranteed by math at n=100 even under best-case zero-loss assumption). **Human must review at that point and decide:**

- **CLOSE UPDOWN_CROSSING class:** remove `logs/UPDOWN_STOP`, mark gate REJECTED, no re-enable without new pre-registration and a fresh candidate pool (the post-cut tape is permanently poisoned by the 4 losses). This is the expected outcome per math.
- OR: override with explicit directive and new evidence. There is currently no such evidence.

**This report cannot make the formal REJECTED call** — the rule says n≥100. The gate-keeper will make the formal call at next run after n crosses 100.

### Pending advisory

- **G3 fills backlog:** 4 Exec Auditor items (Jul-16 to Jul-19) remain unclassified. Once network access restores, the Exec Auditor should close these before any re-enable review.
- **Network blocked 4th consecutive run:** shadow_grade.py and band_resolution_join.py cannot be run from this container. If this is a persistent environment issue, VPS access is required to refresh G1/G7 join and G8 per-asset cells.

---

*Gate-keeper is REPORT-ONLY. No strategy code or flags modified.*
