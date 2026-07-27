# Gate-Keeper Report — 2026-07-27

**STALL (run 7)** — `system_status.txt`: `failed unknown` (systemd dead since 2026-07-24T10:09:19Z). Snapshot 2026-07-27T09:10:46Z (fresh). Abort condition met; gate metrics held at prior authoritative values except **G8 UPDOWN_CROSSING → REJECTED** (confirmed by EVOLVE weekly 2026-07-26).

**Capital**: $88.750373 ($21.50 CLOB + $67.25 owner-manual on-chain per EVOLVE 2026-07-26; on-chain to the cent). Note: capital still below engine ruin_floor $89.16; band paths mechanically blocked. Burn rate: $0.

---

## Gate Ledger

| Gate | n (auth) | +24h | WR | ROI | CI95 | Status | ETA / Notes |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES (per slice) | 934 | +0 | 15.3% sim | +4.0% sim ⚠️ UB | [−10.9%, +21.1%] | AMBIGUOUS | Band dark day 21 (BAND_LIVE=False since Jul-06). ROI is upper bound — G3 winner's curse blocks sim-CI re-enable. Inert. |
| G2a BAND_NO shadow | 115 | +0 | 68.7% / live 39.2% | +1.3% | [−11.9%, +12.7%] | AMBIGUOUS | BAND_NO_ENABLED=False. Live sub-leg n=51 WR=39.2% effectively REJECTED — do not re-enable on shadow CI alone. |
| G2b PAIR_FAV_NO | 9 live | +0 | — | CF +52.9% (biased) | CF [+12.6%, +85.5%] biased | COLLECTING | Band dark; CF biased per state_log Jul-11. Inert. ETA: indeterminate. |
| G2c PAIR_FAV_YES | 9 live | +0 | — | — | — | COLLECTING | Band dark; inert. ETA: indeterminate. |
| G3 FILLED_vs_FIRED | 75 filled | +0 | 17.3% filled vs 7.6% sim | −75.8% filled | [−75.0%, −34.2%] | WATCH_ITEM | **Winner's curse CONFIRMED** (gap −83.4 pp). CI entirely negative. Hard blocker: no sim-CI argument may re-enable G1 or G7. |
| G4 BASKET_EXIT | — | — | — | — | — | VOID | Permanently retired 2026-06-22 (4 fatal flaws). |
| G5 THERMO_MAKER_NO | 125 | +0 | — | 0.0% net | [−9.0%, +2.0%] | **REJECTED** | THERMO_MAKER_LIVE=False since Jun-23. Candidate log only. No reconsideration without explicit human directive. |
| G6 M1_BETA_LOCKOUT | 31 | +0 | 74.2% | −0.6% | [−20.6%, +24.4%] | **REJECTED** | MIN_LOCKOUT_LIVE=False. 0.5°C floor revert recommendation stands (state_log 2026-06-09). No reconsideration without explicit human directive. n=31 frozen below 100; gate rejected by human directive Jul-04. |
| G7 SUM_POSTED 0.70–0.85 | 382 | +0 | — | +11.5% sim ⚠️ UB | [−11.4%, +38.9%] | AMBIGUOUS | Band dark; inert. ROI upper bound per G3 winner's curse. ~147 shadow est since wind-down. ETA: indeterminate. |
| **G8 UPDOWN_CROSSING** | **127 confirmed** | **+39 ✓** | **95.28%** | sim −$5.52 | **[90.1%, 97.8%]** | ★ **REJECTED** ← NEW | Certainty-taker class killed by EVOLVE 2026-07-26. n=127, WR=0.9528 < BE=0.9651. Pooled 5-asset n=469 WR=0.964 < BE=0.965. Class closed; graveyard #15. |

*⚠️ UB = sim ROI is upper bound; G3 winner's curse confirmed. +24h = 0 for all frozen gates except G8 (confirmed authoritative change from EVOLVE).*

---

## State Transitions vs Prior Run (2026-07-26T09:07Z)

### ★ G8 UPDOWN_CROSSING: KILL-LOCKED → **REJECTED** (first new verdict since Jul-04)

EVOLVE weekly 2026-07-26 executed shadow_grade.py on VPS (brief one-shot session before ongoing downtime), confirmed:
- **n = 127** (auth; was est 105–127 at prior run; +39 from last authoritative n=88 at 2026-07-23 22:05Z)
- **WR = 0.9528** (95.28%); k≈121W, 6L from post-cut pool
- **BE = 0.9651** (96.51%)
- **Point WR < BE at n ≥ 100** → pre-registered kill rule triggered
- Pooled cross-asset check: n=469, WR=0.964 < BE=0.965 → consistent failure at scale
- CI95 (Wilson) at n=127: [**90.1%**, 97.8%] — CI-lo 90.1% is far below BE 96.5%; no path to clearing
- Minimum n to clear BE with current loss count (6L fixed): n = ceil(6 × 0.9651 / (1 − 0.9651)) = ceil(166.5) = 167 — unreachable without additional losses pulling BE further
- Kill executed; class assigned graveyard slot #15
- Secondary kills noted (not registered gates): inverse divergence-fade #16 (WR 7.4% vs BE 12.6%, n=136); t_left dead-zone rejected out-of-sample (8/17 losses outside)

### Other transitions this run: none

- **Capital**: $21.50 → $88.75 (+$67.25 owner on-chain injection; EVOLVE-documented). Capital $88.75 remains below ruin_floor $89.16 — band paths still mechanically blocked.
- **Band dark**: day 20 → **day 21**. No band resolutions flowing.
- **System**: Failed/unknown day 3 (since 2026-07-24T10:09:19Z). Weekly-loop-only mode (daily + liveness timers disabled per EVOLVE). Burn rate zero.
- **G1, G2, G3, G5, G6, G7**: No change; all metrics held from 2026-07-25T09:03Z auth.

---

## PROPOSED ACTIONS (human review)

### ★ Newly REJECTED: G8 UPDOWN_CROSSING

**Kill was already executed by EVOLVE 2026-07-26. Human confirmation receipt required.**

- Class: updown CROSSING (p_model ≥ 0.995, 5-min, multi-asset certainty-taker)
- Verdict: **REJECTED** — n=127, WR=95.28% < BE=96.51%; CI-lo 90.1% far below BE
- Action taken: graveyard #15 assigned; class closed in EVOLVE commit ddbcecdd1
- Human to: confirm EVOLVE's graveyard #15 assignment; archive this gate; confirm no residual code paths remain open
- **No re-enable without: (1) fresh pre-registration in state_log, (2) clean candidate pool with no pre-cut contamination, (3) CI-lo clearing BE at n ≥ 100**

### No other gates newly READY or REJECTED this run.

---

## Structural Blockers (current)

| Blocker | Status |
|---|---|
| UPDOWN_STOP | Active since 2026-07-19T11:26Z (PF 0.79 < 0.80 charter rail) |
| BAND_LIVE=False | Active since 2026-07-06T22:08Z — day 21 |
| G3 WATCH_ITEM | Winner's curse confirmed; blocks all sim-CI G1/G7 re-enable |
| Capital vs ruin_floor | $88.75 < $89.16 — band paths blocked mechanically |
| G5 THERMO | REJECTED; no reconsideration without human directive |
| G6 M1 LOCKOUT | REJECTED; no reconsideration without human directive |
| G8 UPDOWN_CROSSING | REJECTED; class closed; no live updown path |
| SYSTEM | Failed/unknown since 2026-07-24T10:09:19Z; weekly-loop-only |
| LDA | STOP active (rolling-20 PnL < −$30 threshold) |

---

*Run ts: 2026-07-27T~09:20Z. Snapshot ts: 2026-07-27T09:10:46Z (fresh, <6h). System abort: `failed/unknown`. STALL run 7. G8 data from EVOLVE commit ddbcecdd1 (2026-07-26). Prior auth gate values: 2026-07-25T09:03:00Z.*
