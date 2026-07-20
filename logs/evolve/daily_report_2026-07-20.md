# EVOLVE daily report — 2026-07-20 (evening slot, ran as the retry-on-default-model
attempt after the primary model hit usage credits at 21:53Z; the 11:23Z morning
slot died the same way at rc=1, `run_daily_2026-07-20T112316Z.log`, but had
already measured the gate and closed one review before dying without committing)

**The system is still halted and risk-off.** The UPDOWN-SNIPER has been cut since
2026-07-19 11:26Z by the pre-registered PF rail. Equity $21.495442 (CLOB-actual,
exact match to bankroll, 0 open positions) remains below the $40 kernel floor. No
path may re-arm without an owner floor re-waiver. This slot made **zero
live-trading changes**; it recovered and committed the morning slot's orphaned
work, re-measured the gate, and logged.

## Health
- Services: klaus / klaus_updown_sniper / klaus_updown_shadow all active.
  Watchdog log: zero forced restarts since 07-14. Wedge watchdog untripped.
- `logs/UPDOWN_STOP` verified present (since 07-19 11:26Z). No fires, no settles,
  wallet unchanged since the cut.
- `git pull --rebase --autostash` was already up to date — no code touched, no
  restart needed.
- **Backlog recovery (this slot's main procedural item):** the 11:23Z slot had
  died on session limits but had already run `shadow_grade.py --refetch`,
  closed the redemption-guard review, and appended `state_log.md` / updated
  `logs/evolve/ledger.jsonl` / `experiments.jsonl` / `gate_ledger_latest.md` —
  all uncommitted in the working tree when it died. Verified the content was
  internally consistent (numbers matched the pattern of prior slots, no
  live-effect changes were made) and folded it into this slot's commit instead
  of discarding or re-doing it.

## Equity & 7d PnL
- Equity: **$21.50** cash, $0 positions. $0 realized today (0 fires since the
  cut — tape is `stop_file` skips only).
- No change since 07-19's scoreboard (~$120 → $21.50 for the week, −82%); no
  live path has earned anything since the cut.

## Sniper gate — the number the loop turns on
- **CROSSING p≥0.995 5m POST-CUT: n=38 (37W/1L), WR 0.9737, CI-lo 0.8650 vs BE
  0.9701, sim +$0.61.** Point WR is back ABOVE breakeven (it was below at the
  11:30Z reading: n=25, WR 0.960 < BE 0.967) — one data point either way doesn't
  move the CI, which remains nowhere close to clearing. Neither the pass branch
  nor the kill branch has triggered.
- All-history crossing: n=157 WR 0.9745, CI-lo 0.9363 vs BE 0.9647 — point
  clears, CI does not (unchanged verdict since the weekly).
- Re-enable gate unchanged: post-cut n≥100 + CI-lo>BE + owner floor re-waiver +
  min-size restart. Gate-pass → PENDING_HUMAN, never auto-arm. Kill: post-cut
  n≥100 with point WR < BE → class closed. Neither condition met yet. Kelly OFF.

## Cells
- Per-asset (`updown_asset_grade.py` 22:00Z): btc n=95 graded WR 0.968 CI-lo
  0.911 BE 0.966 +$1.32 (closest cell to n≥100 of any, still short); p≥.995
  sub-slice n=56 WR 0.964 CI-lo 0.879 BE 0.965 −$0.51. eth 12/12W, xrp 8/8W, sol
  4/4W, doge 3/3W — all COLLECTING, none within reach of n≥100.
- No promotion question exists yet for any alt-asset cell.

## Weather (maintenance)
- Band re-enable trigger NOT met: settled disp_ratio 07-15..07-19 =
  1.097/1.003/0.967/0.849/1.106 (needs ≥1.10 sustained × 5d; only 07-19 grazes
  it). 07-20 is a partial day (pooled 1.196 on 19 of ~38 expected buckets) and
  is excluded from the settled read.
- NEG_RISK_ARB / RECYCLE099 alive ([WA] cycle 21:57Z); 0 fills — ruin_floor
  $89.16 blocks entries mechanically. Not tuned.

## Actions taken
1. Recovered and committed the 11:23Z slot's orphaned work (review closure +
   measurement) rather than re-running it.
2. Closed the overdue (review_date 07-18) `updown_sniper_live` v1-tape
   experiment as SUPERSEDED — folded into `updown_crossing_reenable_gate`, the
   active instrument going forward (bookkeeping only, not a live change).
3. Gate ledger refreshed + committed; experiments.jsonl updated with today's
   n=38 crossing-gate numbers and the per-asset grade.

## Actions rejected / not taken
- **Any sniper re-enable**: post-cut n=38 vs gate n≥100 — not yet; owner floor
  re-waiver required regardless (equity < $40 kernel floor).
- **Any optimization**: standing rail-breach posture (kernel floor) —
  measure-and-hold day per daily prompt STEP 0.
- **Execution-quality measurement** (fill rate / depth headroom for a future
  Kelly sizer): skipped — no new fires since the cut, nothing to measure.
- Ledger reviews: only the one closed above was due; nothing else outstanding.

## Experiments
- `updown_crossing_reenable_gate`: COLLECTING (post-cut n=38; review 07-24).
- `updown_multiasset_15m`: COLLECTING (review 07-26).
- `updown_sniper_live` (v1): SUPERSEDED (closed this slot).
- `updown_t_left_deadzone_exclusion`: PROPOSED by an interactive session
  (08:47Z today), prospective-only, explicitly look-ahead-biased if graded on
  the historical sample that motivated it; review 07-27, not due yet.
- Weather standing conditions unchanged.

## Standing risks
1. Equity $21.50 < $40 kernel floor — no live path may re-arm without owner.
2. The only path to the $10k/mo objective right now is a CI-clearing
   measurement (crossing gate n≥100 ≈ 07-22/07-24) followed by an owner
   capital/floor decision. Nothing live is earning.
3. Session limits keep killing the 11:23Z slot most mornings (again today) —
   timer-move fix is escalated, kernel-protected unit (owner-only edit).
4. When a slot dies mid-run, its uncommitted work can sit in the working tree
   until the next slot recovers it (as happened today) — worth the owner
   checking that no session dies leave contradictory or duplicate uncommitted
   state if two slots ever overlap.
