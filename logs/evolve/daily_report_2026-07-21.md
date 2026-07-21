# EVOLVE daily report — 2026-07-21 (morning slot died immediately on usage
credits at 11:23:04Z before any measurement, `run_daily_2026-07-21T112300Z.log`;
this is the recovery slot covering the day fresh)

**The system is still halted and risk-off.** The UPDOWN-SNIPER has been cut since
2026-07-19 11:26Z by the pre-registered PF rail. Equity $21.495442 (CLOB-actual,
exact match to bankroll, 0 open positions) remains below the $40 kernel floor. No
path may re-arm without an owner floor re-waiver. This slot made **zero
live-trading changes**; it re-measured the gate, closed two due bookkeeping
reviews, and logged.

## Health
- Services: klaus / klaus_updown_sniper / klaus_updown_shadow all active.
  Watchdog log: zero forced restarts since 07-14. Wedge watchdog untripped
  (journal shows a single continuous run since the 07-18 20:03Z deploy).
- No `logs/evolve/CRASHLOOP.flag`.
- `logs/UPDOWN_STOP` verified present (since 07-19 11:26Z). No fires, no settles,
  wallet unchanged since the cut — tape shows only `stop_file` skips.
- `git pull --rebase --autostash` brought only cloud-analyst log files (calib
  monitor, gatekeeper, pnl ledger, research audit reports) — no code touched,
  no restart needed.
- Disk: 89% used, 11G free — stable, watch not urgent.
- **Backlog:** the 11:23Z slot died on usage credits before running a single
  command (`"You're out of usage credits"` at rc=1). Nothing was measured or
  written, so there was no orphaned work to recover — this slot is the day's
  only real work.

## Equity & 7d PnL
- Equity: **$21.50** cash, $0 positions. $0 realized today (0 fires since the
  cut).
- Sniper tape 7d realized (settles since 2026-07-14): **−$15.23** over 81
  settles — this window straddles the candidate-era wins, the 07-19 −$22.09
  loss that triggered the cut, and the current zero-fire cut period. Weather
  7d realized: **$0** (0 `trades.jsonl` WEATHER_STWA settlements in the
  window — confirms dark).
- No change to the week's scoreboard (~$120 on 07-12 → $21.50, −82%); no live
  path has earned anything since the cut.

## Sniper gate — the number the loop turns on
- **CROSSING p≥0.995 5m POST-CUT: n=55 (54W/1L), WR 0.9818, CI-lo 0.9039 vs BE
  0.9696, sim +$3.45.** Accrual 38→55 in ~13.5h (~30/day, matching the prior
  estimate). Point WR (0.982) sits comfortably above breakeven; the CI-lo gap
  is narrowing (0.865 at n=38 → 0.904 at n=55, vs BE 0.9696 — gap down from
  0.105 to 0.066) but has not cleared. Neither the pass branch nor the kill
  branch has triggered.
- All-history crossing: n=174 WR 0.9770, CI-lo 0.9424 vs BE 0.9651 — point
  clears, CI-lo does not, but the gap (≈0.023) is the narrowest yet.
- Re-enable gate unchanged: post-cut n≥100 + CI-lo>BE + owner floor re-waiver +
  min-size restart. Gate-pass → PENDING_HUMAN, never auto-arm. Kill: post-cut
  n≥100 with point WR < BE → class closed. Neither condition met yet. Kelly
  OFF. At current accrual (~30/day), n≥100 is ETA ~07-22/07-23.

## Cells
- Per-asset (`updown_asset_grade.py`): btc unfiltered graded n=110 — the
  first cell to cross n≥100 — WR 0.973 CI-lo 0.923 BE 0.965 +$4.70 (this is
  the unfiltered pool, not the operative p≥0.995-crossing gate; p≥.995
  sub-slice n=67 WR 0.970 CI-lo 0.898 BE 0.963 +$2.14, still short). eth
  18/18W, xrp 10/10W, sol 4/4W, doge 5/5W — all COLLECTING, none within reach
  of n≥100.
- No promotion question exists yet for any cell; the path is cut regardless.

## Weather (maintenance)
- Band re-enable trigger NOT met: settled disp_ratio 07-16..07-20 =
  1.003/0.967/0.849/1.106/1.256 (needs ≥1.10 sustained × 5d; 2 of 5 clear the
  line, 3 don't).
- NEG_RISK_ARB / RECYCLE099 alive ([WA] cycle 11:24Z); 0 fills — ruin_floor
  $89.16 blocks entries mechanically. Not tuned.

## Actions taken
1. Ran `shadow_grade.py --refetch` and `updown_asset_grade.py` — fresh gate
   and per-asset numbers above.
2. Closed two due (review_date 07-21) bookkeeping reviews: the split-fill
   top-up commit (`5b06af1c8`, KEEP — unexercised since the cut, no revert
   condition tripped) and the wedge watchdog retro-registration (`ee014ba92`,
   KEEP — zero relaunches since the 07-18 20:03Z deploy, no false-positive
   storm; positive case — catching a real wedge — remains untested since no
   wedge has recurred).
3. Gate ledger refreshed + committed; `experiments.jsonl` updated with
   today's n=55 crossing-gate numbers and the per-asset grade.

## Actions rejected / not taken
- **Any sniper re-enable**: post-cut n=55 vs gate n≥100 — not yet; owner floor
  re-waiver required regardless (equity < $40 kernel floor).
- **Any optimization**: standing rail-breach posture (kernel floor) —
  measure-and-hold day per daily prompt STEP 0.
- **Execution-quality measurement** (fill rate / depth headroom for a future
  Kelly sizer): skipped — no new fires since the cut, nothing to measure.
- No other ledger reviews were due besides the two closed above.

## Experiments
- `updown_crossing_reenable_gate`: COLLECTING (post-cut n=55; review 07-24).
- `updown_multiasset_15m`: COLLECTING (review 07-26).
- `updown_t_left_deadzone_exclusion`: PROPOSED by an interactive session
  (07-20 08:47Z), prospective-only, explicitly look-ahead-biased if graded on
  the historical sample that motivated it; review 07-27, not due yet.
- Weather standing conditions unchanged.

## Standing risks
1. Equity $21.50 < $40 kernel floor — no live path may re-arm without owner.
2. The only path to the $10k/mo objective right now is a CI-clearing
   measurement (crossing gate n≥100 ≈ 07-22/07-23) followed by an owner
   capital/floor decision. Nothing live is earning.
3. Session limits keep killing the 11:23Z slot most mornings (again today,
   this time before any work at all) — timer-move fix is escalated,
   kernel-protected unit (owner-only edit).
4. Disk at 89% — no action needed today, but the 07-19 reclaim headroom is
   being consumed by the widened alt-asset shadow recording; worth a check
   next time it crosses ~92%.
