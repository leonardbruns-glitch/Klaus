# EVOLVE Daily Report — 2026-07-15 (morning slot, 11:23 UTC)

## Health & equity (first, honestly)
- `klaus` **active**; `klaus_updown_sniper` **active** (restarted 11:34Z for the rails
  fix, state intact); `klaus_updown_shadow` active. No crashloop flag.
- **Equity: $37.01 cash, 0 open positions** (CLOB-actual, 11:23Z). This is **below the
  $40 kernel floor** (standing 2026-07-13 owner waiver, sniper only) and 16.6% of the
  30d high-water $222.90. 7d equity change: **−$66.6** (07-08 EOD $103.62 → $37.01),
  dominated by the 07-09..07-13 sprint-ladder losses (ladder DISARMED 07-13) and
  pre-fix sniper damage. Since the 07-14 22:04Z fixes the trajectory is positive:
  +$2.97 wallet since then (sniper +$2.08 realized today, 9W/0L).
- 7d realized PnL from `trades.jsonl`: no resolved weather trades (band dark day 9,
  engine ruin_floor $89.16 mechanically blocks all STWA paths); the only live path is
  UPDOWN-SNIPER. Rails-breached day ⇒ cutting/verification mode, no optimization.

## Actions taken (1 live-effect change, commit `7e569bb46`)
1. **Sniper rails re-based on TRUE fire cost** (live change #1 of 2 allowed):
   - Found: the CLOB enforces a **5-share buy minimum**; `order_manager` snaps size up,
     so yesterday's CLIP $5→$2 cut **never took effect** — all 9 post-fix fills are
     exactly 5.0 shares ($4.50–4.92 each). The $20 reserve check under-counted true
     cost by ~$2.9/fire (could have taken the wallet to ~$17.1).
   - Fix: `est_cost = max(CLIP_USD, 5·ask)` now gates depth and cash reserve;
     `DAILY_STOP_LOSS` 6.0→4.5 so one full-clip loss (~14% of equity) halts the day.
   - Deployed 11:34Z, service verified active, state reconciled (`open={}`).
2. **S3 dispersion gauge restored** (measurement-only, not counted against cap):
   `settled_disp_ratio.py` had a hard-coded DATES list ending 07-10 — the "settled
   feed dead since 07-12" alert was this script bug, not a dead upstream. Now rolls
   the last 18 hot-log day dirs. Pooled impl/real 07-11..07-14: 0.718/0.816/0.675/
   0.942 — **band re-enable dispersion condition still NOT met** (needs ≥1.10×5d).

## Verifications (post-07-14-fix)
- **Orphan-sweep fix HOLDING**: 9 fills → 9 settles, zero ORPHAN_SELLs since 22:04Z;
  `main.py` sweep exclusion confirmed reading `updown_sniper_state.json` open tokens
  (research-audit item 2A verified: state file is rewritten on every fill/settle).
- **Offline shadow regrade ran** (`shadow_grade.py --refetch`): n=32 true-labeled
  policy windows since the settle-bug fix, WR 96.9% CI [84.3, 99.4], +0.59%/$ at avg
  ask 0.964 ≈ breakeven — point estimate above water, **CI does not clear breakeven**.
  Combined true-labeled evidence ≈41 (9 live + 32 regrade): still COLLECTING, n<100.
- **Sprint ladder** (STEP 2b): cron alive (fresh evals 11:20Z), DRY mode (disarmed
  07-13, owner re-arm only), 25/25 shots settled 8W/17L, sleeve state consistent.
  Sprint gap (07-14 EOD): equity $34.13 vs target $573.65 → **−$539.52**.
- 3 sniper FIREs returned OrderStatus.FAILED (missed crosses, 0 shares, $0 effect) —
  2 within 11s on the same window at 08:39Z; watch frequency, no action at n=3.

## Actions REJECTED / not taken (with the failed gate)
- **Any band/weather re-enable** — triple-blocked: equity rail (<50% 30d-HW),
  ruin_floor mechanical block, winner's curse (sim ROI = upper bound; realized fills
  −75.8% n=75). Today's sim join (+9.4% YES n=646) does NOT qualify as evidence.
- **MIN_LOCKOUT re-enable** — evidence gate passed (197/197) but the 07-13
  pre-registered equity-rail cut stands; rail must clear first (equity ≥50% 30d-HW).
- **Sniper scale-up** (clip/fires/day) — n≈41 < 100 gate; also forbidden on a
  breached-rail day. The path stays in gate-collection mode.
- **Sprint-ladder re-seed** — not applicable: ladder DISARMED by 07-13 kernel-breach
  entry (owner re-arm only); re-seed rule requires free USDC − $20 − resting ≥ $15
  (marginal at $37) and is moot while disarmed.

## Experiments status
- `updown_sniper_live` — COLLECTING (~41 true-labeled; review 07-16).
- `updown_shadow_offline_gate` — COLLECTING; regrade pipeline now proven end-to-end.
- `band_dial_timeseries` — n=35 resolved days (needs 90); lag+2 Spearman −0.22 (n=33),
  still adverse/noise; no dial.
- `yes_capture_shadow` — markout still adverse (93% adverse, med −2.9¢): YES taker
  re-entry stays dead; review 2026-08-01.
- `pair_clip_cofill` — ACCRUAL-FROZEN (band dark), NO_PAIR +44.2% at n=13 (n<40, no
  action possible while dark).
- S3 `band_reenable_trigger` — STANDING-CONDITION, now measurable again daily.

## Standing risks
1. Equity $37 < kernel floor $40: one sniper full-clip loss (−$4.9) puts the wallet at
   ~$32; the corrected rails now cap the day at one such loss. Ruin floor $50 and
   weekly floor $75 also breached — all pre-existing, all reported since 07-13.
2. Sniper edge is razor-thin at the ask (breakeven WR ≈95.3–96.4%); the n≥100 gate
   decides whether this path compounds or gets cut. Do not extrapolate 9W/0L.
3. Compounding bottleneck unchanged (research audit concurs): capital 41% of the
   engine ruin floor — no weather path can re-arm until equity recovers, and the only
   recovery engine is a $0.23/win sniper. At the current rate, weeks, not days.
4. Claude session limits killed 4 of the last 8 evolve slots — the morning slot ran
   today; if the evening slot dies, this report covers the day.

---

# Evening slot (21:53 UTC)

## Health & equity (first, honestly)
- All three services **active** (`klaus`, `klaus_updown_sniper`, `klaus_updown_shadow`);
  no crashloop flag, no `UPDOWN_STOP`, no backlog (morning slot ended rc=0).
- One self-healed incident: **02:40Z klaus event-loop stall** (curl 30s timeout in
  `fetch_token_balance` froze the loop 50s) → internal watchdog forced exit, systemd
  restarted, clean recovery. Watch frequency; no action needed at 1 occurrence.
- **Equity: $38.48 cash, 0 open positions** (22:00Z) — still under the $40 kernel
  floor (standing 07-13 owner waiver, sniper only) but **+$4.44 since the 07-14
  22:04Z fixes** and +$1.47 since the morning slot. Trajectory positive.
- Reconciliation: sniper tape explains +$3.64 of the +$4.44; residual **+$0.80
  unattributed inflow**, most plausibly Polymarket auto-redeem of residual weather
  winner dust (7 confirmed winners on disk, no bot tx involved). Logged as a watch
  item — an unattributed OUTFLOW would be a halt-and-hunt.

## Sniper gate status (the number the loop turns on)
- `shadow_grade.py --refetch` 22:02Z: **n=76 true-labeled windows, WR 98.7%,
  Wilson CI [92.9, 99.8] vs breakeven ≈96.2%** — the point estimate clears, the
  CI lower bound does not. **KELLY activation condition (n≥100 AND CI-lo >
  breakeven) NOT met → flag stays OFF.** At the post-14:35Z fire rate, n=100
  arrives in ~1 day; note that even 100/100 wins puts Wilson CI-lo only ≈96.3 —
  the gate will likely need n≈150 to resolve either way. That is the design
  working, not a delay to fix.
- Live tape post-fix: **17 fills / 17 settles, 17W/0L, +$3.64**; today 16 fires,
  +$3.54 realized, consec_loss 0, open={}. Zero orphan-sells (07-14 sweep fix
  holding). Fill rate 77.3% (5 FOK misses at $0 cost — offline gate n grows on
  policy windows, so misses don't slow the gate).
- Depth headroom for the sizer: certainty-cell touch ask depth med **$791**
  (p10 $31); 92% of snaps hold ≥$25 ⇒ CLIP_CAP $25 is not depth-bound at
  activation.

## Actions taken (0 live changes — cap already consumed 11:34Z + 14:35Z)
1. REVIEW-CLOSE (bookkeeping): 07-13 winner-extraction BUGFIX → **KEEP**. 17/17
   post-fix settles consistent with redemption cash; zero settle-vs-Gamma
   disagreements; the regraded shadow feed is functioning as the gate sensor.
2. Gate ledger refreshed and committed (sniper rows lead); experiments.jsonl
   updated with tonight's readouts + registered `updown_multiasset_15m`
   (eth/sol/xrp tape day 1 of 2, per-asset n≥100 gates, review 07-17).

## Actions REJECTED (with the failed gate)
- **KELLY activation** — n=76 < 100 and CI-lo 92.9 < 96.2. Pre-registered
  condition unmet.
- **Gate kill** — point estimate 98.7% > breakeven; not remotely triggered.
- **eth/sol/xrp cell promotion** — tape day 1 of the ≥2-day requirement; zero
  graded windows.
- **Band/weather re-enable** — disp_ratio last 5 settled days 0.718/0.816/0.675/
  0.942/1.040(partial), all <1.10; equity rail also unmet.
- Any further live tuning — daily 2-change anti-thrash cap consumed.

## Experiments
- `updown_shadow_offline_gate` COLLECTING (n=76, review 07-16).
- `updown_sniper_live` COLLECTING (17 clean post-fix samples, review 07-16).
- `updown_multiasset_15m` COLLECTING (day 1/2, review 07-17).
- Weather rows unchanged (band trigger standing-condition not met; NEG_RISK_ARB
  functioning — traded 07-14 19:20Z; RECYCLE099 alive, idle as expected).

## Standing risks
- Equity below kernel floor (waived, sniper-only) — every fire is ~13% of equity
  until the wallet rebuilds; rails: RESERVE $20+est_cost, DAILY_STOP 4.5,
  single-loss day-halt by construction.
- The whole path rides on WR holding ≥~96.2% at 5-share minimum clips; the n≥100
  gate is the only thing that converts this from streak to edge. No sizing moves
  before it clears.
- +$0.80 unattributed inflow (watch item); 02:40Z stall-restart pattern (watch).
