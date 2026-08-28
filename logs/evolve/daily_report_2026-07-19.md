# EVOLVE daily report — 2026-07-19 (evening slot 21:53Z; morning 11:23Z slot died on session limits after creating UPDOWN_STOP — its work was retro-covered by the 14:30Z weekly)

**The system is halted and risk-off.** The UPDOWN-SNIPER was cut this morning at
11:26Z by the pre-registered PF rail (candidate tape PF 0.79 over 27 settles; one
−$22.09 half-Kelly loss erased all 26 candidate wins). Equity $21.4954
(CLOB-actual, exact match to bankroll, 0 open positions) is below the $40 kernel
floor. No path may re-arm without an owner floor re-waiver. This slot made **zero
live-trading changes**; it measured, fixed a disk-pressure infra risk, and logged.

## Health
- Services: klaus / klaus_updown_sniper / klaus_updown_shadow all active.
  Watchdog log: zero forced restarts since 07-14. Wedge watchdog (ee014ba92)
  holding — sniper alive and correctly idle (tape shows only `stop_file` skips).
- `logs/UPDOWN_STOP` verified present (created 11:26Z). No fires, no settles,
  wallet unchanged since the cut.
- **Disk (new finding, fixed this slot):** 95% full / 4.8G free against ~3–4G/day
  intraday shadow accrual before the 04:00 prune cron — thin margin made worse by
  the 4 new alt-asset 5m recorders enabled 19:05Z. Reclaimed **without deleting
  any data**: journal vacuum (3.0G, duplicated by bot.log rotation) + gzip of
  shadow/hot 07-10/11/12 (9.2G→616M; those dirs were scheduled for outright
  deletion by the KEEP_DAYS=10 prune within 1–3 days — compression preserves
  them). Now 83% / 17G free. Structural fix (lag_ws_events.jsonl 8.1G
  live-append; market_ticks.jsonl 2.5G) remains an owner call (19:05Z escalation
  stands).

## Equity & 7d PnL
- Equity: **$21.50** cash, $0 positions. Day realized **−$16.57** (all pre-cut:
  5 fires 4W/1L, the −$22.09 loss). Nothing since the cut — burn rate zero.
- Week (from the weekly scoreboard, unchanged since): ~$120 → $21.50 (−82%);
  ladder −$80 (0W/7L, disarmed), sniper wallet-truth −$17.90, weather $0.

## Sniper gate — the number the loop turns on
- **CROSSING p≥0.995 5m POST-CUT: n=2, 1W/1L, sim −$4.88** (CI meaningless at
  n=2). The first post-cut crossing events include a loss — the early tape is
  consistent with the cut being right, not with a rescued edge.
- All-history crossing: n=121 WR 0.9669, CI-lo 0.9181 vs BE 0.9629 — point
  barely clears, **CI does not**; WR fell from 0.9748 (weekly) on 2 new events.
- 19:05Z Gamma-truth regrade corroborates: 7d n=129 WR 0.969, CI-lo 0.923, no
  cell clears CI. The pre-registered mv≥8bp stratum (n=64, 63W, +2.1%/$) is a
  trend-flag only (CI-lo 0.917 < BE).
- Re-enable gate unchanged: post-cut n≥100 + CI-lo>BE + owner floor re-waiver +
  min-size restart. Gate-pass → PENDING_HUMAN, never auto-arm. Kill: post-cut
  n≥100 with point WR < BE → class closed. Kelly OFF.

## Cells
- Per-asset 15m (v1 gates): btc 69 graded WR 0.957 −$3.07; eth 3/3W; xrp 5/5W;
  sol/doge 0 — all COLLECTING, no promotion question exists yet.
- **Alt-asset 5m shadows (eth/sol/xrp/doge) verified writing** since 19:05Z
  (~360 snaps each in recent tail). First per-asset 5m grade when snaps span ≥2
  days (~07-21); expected 3–5× n-collection speedup for the re-enable gate's
  breadth.

## Weather (maintenance)
- Band re-enable trigger NOT met: settled disp_ratio 07-14..07-18 =
  0.942/1.097/1.003/0.967/0.849 (needs ≥1.10 × 5d).
- NEG_RISK_ARB / RECYCLE099 alive ([WA] cycle 21:56Z); 0 fills — ruin_floor
  $89.16 blocks entries mechanically. Not tuned.

## Actions taken
1. **Disk reclaim** (Tier-1 infra health, bookkeeping — not vs 2-cap; ledger
   22:10Z entry, review 07-22). Evidence and revert condition in the ledger.
2. Gate ledger refreshed + committed; experiments.jsonl updated
   (updown_crossing_reenable_gate COLLECTING, post-cut n=2 numbers logged).

## Actions rejected / not taken
- **Any sniper re-enable**: post-cut n=2 vs gate n≥100 — nowhere near; owner
  floor re-waiver required regardless (equity < $40 kernel floor).
- **Any optimization**: breached-rail day (kernel floor) — measure-and-cut
  posture per daily prompt STEP 0.
- **KEEP_DAYS tightening or deletion of live-append logs** (lag_ws_events,
  market_ticks): deletion decisions are not the loop's to make (invariant 3);
  owner escalation stands.
- Ledger reviews: none due (all closed through 07-18; verified in ledger).

## Experiments
- `updown_crossing_reenable_gate`: COLLECTING (post-cut n=2; review 07-26).
- `updown_multiasset_15m`: COLLECTING (review 07-26); 5m alt-asset shadows now
  feeding it faster.
- `updown_sniper_candidate_live`: CUT-BY-RAIL, closed tape (review 07-26).
- Weather standing conditions unchanged.

## Standing risks
1. Equity $21.50 < $40 kernel floor — no live path may re-arm without owner.
2. The only path to the $10k/mo objective right now is a CI-clearing measurement
   (crossing gate n≥100 ≈ 07-24 for btc; alt-assets widen it) followed by an
   owner capital/floor decision. Nothing live is earning.
3. Session limits keep killing the 11:23 slot (5/7 mornings) — timer fix is
   escalated, kernel-protected unit (owner).
4. Disk: near-term pressure resolved; structural growth (lag_ws_events 8.1G
   live-append) still needs an owner decision.
