# EVOLVE Weekly Report — 2026-07-19

**A losing week: equity ~$120 → $21.50 (−82%). The sole live path (UPDOWN-SNIPER
candidate) took its first loss at 50%-Kelly sizing and was CUT by its
pre-registered PF rail at 11:26Z today. Every live path is now halted; equity is
below the $40 kernel floor; burn rate is zero.** The $10k/month objective is not
on trajectory and cannot be reached from $21.50 by any gated action available to
the loop. Note: this is the first completed weekly since 07-05 — the 07-12 weekly
died twice on session limits, so this report covers two weeks of weekly duties
(the 07-15 interactive refocus did the mid-week restructuring).

## 1. Scoreboard (computed, wallet-reconciled)

| Metric | Value |
|---|---|
| Equity now | **$21.4954** CLOB-actual == bankroll.json exact, 0 open positions |
| Equity at missed 07-12 weekly slot | ~$120 tracked (cash + ladder shots at cost) |
| Week Δ | **−$98.5 (−82%)** |
| Sniper realized, wallet-truth (go-live 07-13 $39.40 → now) | **−$17.90** = void pre-fix era −$5.48 + v1 −$8.14 + candidate −$4.64 + fees/redemption-poach ≈−$0.4 (+$0.80 unattributed inflow 07-15) |
| Candidate tape (07-16 14:59Z → cut) | 27 settles, 26W/1L, WR 0.963, **net −$4.64, PF 0.79** |
| Fires/day (candidate, filled) | 6 / 12 / 4 / 5 (07-16..19); net/fire −$0.17 |
| Sprint ladder (owner-authorized, disarmed 07-13) | 0W/7L; ≈−$80 realized inside the week window |
| Weather engine | $0 — zero trades.jsonl rows; NEG_RISK_ARB + RECYCLE099 0 fills (ruin_floor $89.16 blocks entries) |
| Kelly | Was owner-waived ON at FRAC 0.50; **era ended with the cut — OFF** |

**The loss that defined the week:** btc-updown-5m-1784447700, Down @0.93,
p_model 0.9953, Kelly clip $22.09 = 50.6% of wallet, resolved Up. One settle
erased all 26 candidate wins ($17.45). This was the *declared* worst case of the
owner's 50%-Kelly + MAX_LOSSES_DAY=1 structure operating as designed: the day
halted at loss #1 (08:04Z), the PF rail cut the path (11:26Z). No rail failed.
Realized growth vs the projected band: the 07-16 projection was ~+1.5%/fire if
the 42/0 slice edge held; realized candidate ROI/fire was −0.4% — the slice edge
did not hold, and §2 explains that the slice itself was mismeasured.

**Gate status (the number the loop turns on):** the operative gate is now the
**CROSSING p≥0.995 5m slice** (see §3). All-history: n=119, WR 0.9748, CI-lo
0.9285 vs breakeven 0.9630 — point clears, CI-lo does not. Post-cut (the
re-enable ledger): **n=0, collecting from zero**, n≥100 ≈ 07-24 at ~20/day.

**Trajectory statement (kernel honesty):** $10k/month requires ~465× current
equity per month. Not reachable by sizing, cadence, or any charter-gated action
from $21.50. The binding constraint is (1) a CI-clearing edge measurement on the
corrected population, then (2) an owner decision on capital/floor — recorded in
PENDING_HUMAN terms in the re-enable pre-registration.

## 2. The week's structural finding: the gate measured the wrong population

The live bot fires when p_model **crosses** 0.995 inside the final window. The
"candidate slice" that justified the arm graded each window at its **first**
p≥0.99 snapshot — so windows first seen at 0.99≤p<0.995 that later drifted over
0.995 were fired live but **excluded** from the slice. The 07-19 loss (first snap
0.9902, live fire at 0.9953) was invisible to a slice showing WR 1.0000 (n=59).
The dead 11:23Z daily authored the fix (`shadow_grade.py` CROSSING slice +
CUT_TS); the weekly verified, committed, and re-pointed everything at it. The
first-fire slice is condemned — nothing may cite it again. Corollary: **the
07-16 owner-waiver arm was evidenced on a biased slice.** The honest all-history
number never cleared its CI.

## 3. Strategy review — verdicts (executed)

| Path | n / evidence | Verdict | Action taken |
|---|---|---|---|
| UPDOWN-SNIPER btc-5m candidate | 27 settles, PF 0.79 < 0.8 | **CUT (rail)** — stands | Stop-file verified; cut retro-registered in ledger + state_log (the dead daily never logged it) |
| btc-15m | v1 pool: n=11, WR 0.818, −$8.12 | dead inside the v1 cut | none (stays cut) |
| Re-enable path | crossing slice post-cut n=0 | pre-registered | experiment `updown_crossing_reenable_gate`; gate pass → PENDING_HUMAN, **never auto-arm** (equity < $40 kernel floor; owner waiver chain ended with the cut — ESCALATIONS #1) |
| eth/sol/xrp 15m cells | eth 3+/3W, xrp 4+/4W, sol 0 | keep collecting | capacity 0–1 fires/day at v1 gates; per-asset gate sweep = next weekly's experiment candidate |
| NEG_RISK_ARB | 0 fills (entry-blocked by ruin_floor) | keep enabled | none |
| RECYCLE099 | 0 fills | keep enabled | none |
| Weather dark paths | BAND_LIVE/M1β/MIN_LOCKOUT/THERMO_LIVE/taker flags all False (verified in source) | **stayed dark** ✓ | none |
| Band re-enable trigger | settled disp_ratio last 5d: 0.942/1.097/1.003/0.967/~0.74 | **NOT met** (needs ≥1.10 × 5d) | none |
| Sprint ladder | crontab `SPRINT_LADDER_LIVE=0` verified | disarmed, owner-only | none |

## 4. Experiment (exactly one new): `updown_crossing_reenable_gate`

- **Hypothesis:** the live-fired population (p_model crossing ≥0.995, 5m windows)
  retains net edge above its avg-ask breakeven; the first-fire slice overstated
  it by excluding late-crossing (more adverse) windows.
- **Mechanism:** crossing fires happen later (lower t_left) after larger drift;
  adverse selection concentrates there — the one live loss was a crossing fire.
- **Metric:** Wilson CI on WR of post-cut (ts>1784460372) CROSSING rows vs that
  slice's avg-ask breakeven + sim pnl/$ (`shadow_grade.py`, already deployed).
- **n-gate:** n≥100 post-cut only (pre-cut rows never count — kernel-style
  re-entry discipline).
- **Kill:** at n≥100 point WR < breakeven → class closed, graveyard entry.
  Interim: any 5d stretch sim pnl/$ < −2%.
- **Review:** 2026-07-24 (interim); decision at n≥100.
- **Graveyard check:** not a rebuilt corpse — a measurement correction of the
  current class's gate. (The weather "certainty-taker CLOSED" verdict is the
  temporal-P5 family; distinct mechanism and market.)
- Shadow-only; zero live capital effect; zero code beyond the grader edit.

## 5. Loop self-evolution

- **Run health: the 11:23Z slot is structurally dead.** 5/7 morning dailies this
  week died on "session limit resets 12pm" (07-13/14/17/18/19); the 07-12 weekly
  died twice. Evening slots: 7/7 completed. Today's morning failure had real
  cost: it created UPDOWN_STOP and the grader fix, then died before logging —
  3h of unregistered risk state, inherited and finished by this run. Fix needs an
  interactive session (timer units are kernel-protected): **escalated** with the
  proposed change (first OnCalendar 11:23 → ~12:10 UTC).
- **Watchdogs:** liveness log clean since 07-14; the 07-18 wedge watchdog has not
  re-tripped (sniper alive-and-quiet verified against shadow snaps 07-18).
- **Thrash:** none loop-caused — every toggle this week was a pre-registered rail
  action or an owner waiver, all documented.
- **Standing migration item (cloud analysts):** mirror push script now ships
  sniper extracts (`updown_sniper.jsonl`, state, `UPDOWN_STOP`,
  `gate_ledger_latest.md`) — verified on the 13:52:30Z data-mirror push; repo
  copy added at `scripts/klaus_data_mirror.sh`. Retasking the first analyst is
  deferred to next weekly with reasoning: the extracts landed this run, and
  session budget is the loop's scarcest resource (see run health) — spending it
  on cloud-routine surgery while UPDOWN_STOP holds and post-cut n=0 buys nothing
  this week. Until then their reports stay advisory-only.
- **Prompt maintenance (done):** `daily_prompt.md` STEP 2/3 rewritten — the old
  standing tree read the condemned first-fire slice and would have false-passed
  Kelly/re-enable within ~3 zero-loss days. Validation: `run_agent.sh test`
  turned out to DEADLOCK when invoked from inside an agent run (it waits on the
  shared flock the running agent holds — a loop defect found and fixed this run:
  `weekly_prompt.md` now prescribes the static launcher-gate checks instead).
  Static gates verified passing: CHARTER.md reference intact in both edited
  prompts + INVARIANTS sha256 pin matches — these are the exact conditions
  `run_agent.sh` enforces before launching the daily.
- **Amendment:** FIRST READING filed (ledger pre-registration for interactive
  deploys — 07-08 and 07-16 both bypassed the ledger; second reading due
  2026-07-26). No second readings were pending.
- **ESCALATIONS processed:** two new kernel-adjacent records (floor re-entry
  ruling; timer escalation); nothing unresolved within loop authority.

## 6. Next week's single biggest lever

**Let the corrected gate fill.** Post-cut crossing slice reaches n≥100 around
07-24. If CI-lo clears breakeven → the case (with min-size restart terms and the
owner floor-waiver requirement) goes to PENDING_HUMAN. If point WR lands below
breakeven → the BTC-5m certainty class is closed and the graveyard gets a new
entry, and the loop's remaining assets are the eth/sol/xrp tapes (per-asset gate
sweep = next weekly's experiment) and $21.50 of preserved capital. Either answer
is progress; un-edged firing is not. Secondary: interactive session should move
the daily timer (escalated) — half the loop's compute is dying on a clock
collision.
