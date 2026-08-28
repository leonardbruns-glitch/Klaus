# EVOLVE daily report — 2026-07-21 (evening slot; the 21:53:16Z primary-model
run died immediately on usage credits — `run_daily_2026-07-21T215316Z.log`
shows "You're out of usage credits" rc=1 with zero work done — this is the
retry-on-default-model recovery. The 11:23Z morning slot completed cleanly
(rc=0) and did real work, so there was no backlog gap to recover; this slot
covers the evening measurement fresh.)

**The system is still halted and risk-off.** The UPDOWN-SNIPER has been cut
since 2026-07-19 11:26Z by the pre-registered PF rail. Equity $21.495442
(CLOB-actual, exact match to bankroll, 0 open positions) remains below the $40
kernel floor. No path may re-arm without an owner floor re-waiver. This slot
made **zero live-trading changes**; it re-measured the gate, confirmed no
ledger reviews were due, and logged.

## Health
- Services: klaus / klaus_updown_sniper / klaus_updown_shadow all active.
  Watchdog log: zero forced restarts since 07-14.
- No `logs/evolve/CRASHLOOP.flag`.
- `logs/UPDOWN_STOP` verified present (since 07-19 11:26Z). Tape shows only
  `stop_file` skips through 17:19Z today; 0 fires, 0 settles, wallet unchanged
  since the cut (`updown_sniper_state.json`: day 20260721, fires=0, open={}).
- `git pull --rebase --autostash` — already up to date, nothing to sync.
- Disk: 91% used, 8.4G free — up from 89% this morning. Still not urgent but
  trending; worth confirming the KEEP_DAYS=10 prune cron is still running if
  it keeps climbing.

## Equity & 7d PnL
- Equity: **$21.50** cash, $0 positions. $0 realized today (0 fires since the
  cut, confirmed unchanged from this morning).
- Sniper tape 7d realized (settles since 07-14): **−$15.23** over 81 settles
  — unchanged from this morning (no new settles). Weather 7d realized: **$0**
  (0 `trades.jsonl` WEATHER_STWA settlements — confirms dark).

## Sniper gate — the number the loop turns on
- **CROSSING p≥0.995 5m POST-CUT: n=57 (56W/1L), WR 0.9825, CI-lo 0.9071 vs BE
  0.9683, sim +$4.16.** Accrual 55→57 in ~10.25h (~4.7/hr — noticeably slower
  than the ~30/day trend seen 38→55; small sample, not treated as a signal
  change). Point WR stays comfortably above breakeven; the CI-lo gap is
  essentially flat versus the 11:45Z reading (0.904→0.907, vs BE 0.9683) after
  several slots of steady narrowing — n≥100 ETA remains ~07-22/07-23 assuming
  accrual picks back up, but this slot's slower rate pushes it toward the
  later end of that window.
- All-history crossing: n=176 WR 0.9773, CI-lo 0.9430 vs BE 0.9647 — point
  clears, CI-lo does not (gap ~0.022, consistent with the morning reading).
- Re-enable gate unchanged: post-cut n≥100 + CI-lo>BE + owner floor re-waiver +
  min-size restart. Gate-pass → PENDING_HUMAN, never auto-arm. Kill: post-cut
  n≥100 with point WR < BE → class closed. Neither condition met yet. Kelly
  OFF.

## Cells
- Per-asset (`updown_asset_grade.py`): btc unfiltered graded n=116 (up from
  110, past n≥100) — WR 0.974 CI-lo 0.927 BE 0.964 +$6.09 (p≥.995 sub-slice
  n=68 WR 0.971 CI-lo 0.899 BE 0.963 +$2.60, still short). eth 20/20W, xrp
  12/12W, doge 8/8W, sol 4/4W — all COLLECTING, none within reach of n≥100.
- No promotion question exists yet for any cell; the path is cut regardless.

## Weather (maintenance)
- Band re-enable trigger NOT met: settled disp_ratio 07-17..07-21 (07-21
  partial, n=20) = 0.967/0.849/1.106/1.256/0.882 — 2 of 5 clear the 1.10 line,
  not sustained.
- NEG_RISK_ARB / RECYCLE099 alive ([WA] cycling normally this slot, shadow-only
  logging); 0 fills — ruin_floor $89.16 blocks entries mechanically. Not
  tuned. BAND_LIVE confirmed still False in `strategy/stwa_engine.py`.

## Actions taken
1. Ran `shadow_grade.py --refetch` and `updown_asset_grade.py` — fresh gate
   and per-asset numbers above.
2. Confirmed no ledger reviews due this slot (the two 07-21 reviews were
   already closed by the morning slot).
3. Gate ledger refreshed + committed; `experiments.jsonl` appended with this
   slot's crossing-gate reading.

## Actions rejected / not taken
- **Any sniper re-enable**: post-cut n=57 vs gate n≥100 — not yet; owner floor
  re-waiver required regardless (equity < $40 kernel floor).
- **Any optimization**: standing rail-breach posture (kernel floor) —
  measure-and-hold day per daily prompt STEP 0.
- No ledger reviews were due this slot.

## Experiments
- `updown_crossing_reenable_gate`: COLLECTING (post-cut n=57; review 07-24).
- `updown_multiasset_15m`: COLLECTING (review 07-26).
- `updown_t_left_deadzone_exclusion`: PROPOSED by an interactive session
  (07-20 08:47Z), prospective-only, explicitly look-ahead-biased if graded on
  the historical sample that motivated it; review 07-27, not due yet.
- Weather standing conditions unchanged.

## Standing risks
1. Equity $21.50 < $40 kernel floor — no live path may re-arm without owner.
2. The only path to the $10k/mo objective right now is a CI-clearing
   measurement (crossing gate n≥100, ETA slipping toward 07-23 on this
   slot's slower accrual) followed by an owner capital/floor decision.
   Nothing live is earning.
3. Session limits/usage-credit exhaustion keep killing slots before any work
   (today's evening 21:53Z primary run) — this is a recurring pattern, not
   a one-off; the retry-on-default-model fallback is absorbing it so far.
4. Disk climbed 89%→91% today (8.4G free) — not urgent, but if the trend
   continues confirm the prune cron next slot.
