# EVOLVE Daily Report — 2026-07-14 (evening slot 21:53Z; morning slot died on session limit at 11:32Z, this run covers the full day)

## Health & equity — first the honest picture
- **Equity: $34.04 CLOB-actual cash, 0 open positions = 15.3% of 30d-HW $222.90.
  The $40 kernel floor remains breached** (owner waiver 07-13, recorded at $39.40).
  Bleed since waiver: −$5.36, all attributable to the UPDOWN-SNIPER path — and now
  fully explained (below). Day move: $34.74 → $34.04 (−2.0%); no daily-halt breach.
- Services: `klaus` active (restarted 22:04Z post-deploy, fresh [WA] cycle 22:05Z,
  startup orphan sweep clean), `klaus_updown_sniper` active (restarted 22:03Z on new
  params), `klaus_updown_shadow` active. Sprint ladder cron alive (10-min evals through
  22:00Z), DRY mode as disarmed 07-13, 0 tracebacks, all 25 shots settled (8W/17L).
- 7d realized (engine, trades.jsonl): n=0 resolutions — all weather paths mechanically
  blocked by ruin_floor $89.16 and flag-dark under the wind-down rail. 7d equity
  trajectory: $163.16 (07-10) → $34.04, dominated by 07-13 ladder losses (−$46.79) and
  the pre-disarm drawdown; see 07-13 report.

## Main finding: the "unknown stop-sell" was the engine cannibalizing the sniper
The research audit's §2B mystery (positions exiting 3s after entry despite
hold-to-redemption policy) is **main.py's `_window_end_balance_sweep`**: the sniper is
a separate process on the shared wallet, its holds never appear in
`risk.open_positions`, so the sweep classified every sniper fill as an orphan and
force-sold it at the bid in the final 120s of each window.

Wallet-truth per-fill join (fires × ORPHAN_SELL rows):
- 21/25 tracked fills since go-live were force-sold (12 on 07-14 alone), with slippage
  as bad as 0.98→0.88, 0.989→0.939, 0.97→0.73.
- Booked PnL −$11.63 was wrong in **both directions**: the +$0.11-style "redemption
  wins" were phantom (shares already sold at bid), and the three −$5 "full losses" were
  phantom too — the sweep had accidentally stop-lossed them (−$15.69 booked vs −$1.91
  true).
- TRUE realized since go-live: **−$5.48** (−$2.59 tracked + −$2.89 untracked 10:49Z
  first fill, 39.25sh @0.99 sold @0.92). This reconciles the cash ledger
  $39.40 → $34.04 exactly. No unexplained leak.
- Consequence for the gate: **every pre-22:04Z live sample is VOID** — it measured
  "sniper + accidental stop-loss", not the registered policy. Clean accumulation
  restarts 22:04Z.

## Actions taken (2 live-effect = at daily cap; breached-rail day = cutting only)
1. **Orphan-sweep exclusion for sniper-held tokens** (`main.py`, commit `7f3234c4d`,
   Tier-1 mechanical fix). Sweep skips token_ids in the sniper's state file; fail-open.
   Verified: py_compile, deploy, restart, fresh cycle, startup sweep clean. Winners
   still convert to cash — the Redeemer loop is wallet-wide (data-api `redeemable`).
   Review 07-17; revert if sniper positions stop cashing within 24h.
2. **Sniper CLIP $5→$2, RESERVE $2→$20** (commit `571b58b39`, Tier-2 stake cut, adopts
   the dead morning slot's edit with evidence corrected to wallet truth). Caps a
   reversal at $2, stops the path at wallet <$22, ~2.5× runway to the n≥100 gate.
   Review 07-17.

## Actions REJECTED / not taken
- **BAND_LIVE flip** despite join printing "DECISION-READY n=760, YES ROI +6.3%":
  sim-join ROI is an upper bound (winners_curse_crosstab_0711 — realized fills −75.8%
  same era; tonight's yes_capture markout re-confirms: med −3.45¢, 94% adverse,
  n=340). Also blocked by the wind-down rail. Gate not satisfied on two independent
  grounds.
- **MIN_LOCKOUT re-enable** (evidence gate long passed, 197/197): pre-registered
  revert_condition from 07-11 fired on 07-13 (equity <50% HW) and the rail is still
  breached. Stays READY-ON-RAIL-CLEAR.
- **Sniper kill**: considered (kernel floor breached, path realized-negative) but the
  owner waiver 07-13 explicitly covers this path; the honest attribution shows the
  loss was mostly execution interference we just removed plus one pre-SIG_FLOOR σ-junk
  fire. Cut to minimum size instead; RESERVE $20 now backstops ruin mechanically.
- **NHC count-lock extension / other capacity work**: breached-rail day — no
  optimization.

## Experiments
- `updown_sniper_live`: COLLECTING, tape void pre-22:04Z, clean restart at $2 clips;
  review 07-16.
- `updown_shadow_offline_gate`: regrade on post-fix labels in progress; review 07-15.
- `yes_capture_shadow`: overdue 07-11 review closed as EXTEND→08-01 (informational
  only; curse re-confirmed).
- `band_dial_timeseries`: n=33 resolved days, trend-only, nothing due.
- S3 disp_ratio standing condition: pooled 0.71–0.86 all full days — NOT met. Caveat:
  settled-data rows end 07-11 (n=15 degenerate) — matches calib_monitor's degraded
  data-access alert; gauge needs its feed checked if rows don't resume by 07-16.

## Standing risks
- Equity below kernel floor with one live path under owner waiver; max further
  exposure now mechanically ~$12 (wallet $34 → $22 reserve stop).
- Sniper missed-fill mode: 2 consecutive OrderStatus.FAILED crosses (21:09Z, 21:39Z,
  ask taken first) — no capital effect; watch frequency on the $2 clips.
- Settled-dispersion feed degraded since 07-12 (S3 gauge blind); cloud calib monitor
  separately alerted.
- bankroll.json `daily_start_capital` reset suspicion (charter note 07-02) unresolved
  but not load-bearing today (reconciled against CLOB directly).
