# EVOLVE daily report — 2026-07-16 (11:23 UTC slot)

## THE LEAD: UPDOWN-SNIPER PATH CUT (charter rail)

The sniper's post-fix live tape is **losing money: n=36 resolved, 33W/3L, WR 91.7%
vs breakeven ~96.3%, net −$8.14, profit factor 0.43**. The charter path-cut rail
(realized PF < 0.8 over ≥20 resolved) fired, and today's tape also breached the
−$4.50 daily stop at **−$7.43** (13W/2L; the mechanical day-halt engaged at 09:34Z
and held). Action taken at 11:27Z: **`logs/UPDOWN_STOP` created — the path is
stopped**, not just for today. This was a rail-breach day: cutting only, no
optimizing changes (steps 3–4 skipped per protocol).

Honest framing, both directions:
- The losses are real and label-verified (shadow regrade with Gamma truth counts
  the same 3; wallet cash $38.48 → $26.55 reconciles the tape to 5¢).
- The cut is a **rails action, not an edge falsification**. The same-slot shadow
  gate (all eligible windows, rails-free) reads n=99, WR 0.970, CI [0.915, 0.990]
  vs breakeven 0.963 — the point estimate still clears; the CI lower bound never
  has. Live ran worse than shadow because live coverage caught only 36 of the 99
  windows but all 3 losers, and ≥3 losses in 36 has ~9% probability even at true
  WR 0.97. Rails don't wait for statistical significance; that is what they're for.

## Health

- Services: klaus, klaus_updown_sniper, klaus_updown_shadow all **active**; no
  watchdog restarts since 07-14 22:03Z; no crashloop flag. Backlog: none (07-15
  evening slot ended rc=0).
- Day-halt verified mechanically (skip_rails=daily_stop bursts from 09:34Z);
  STOP_FILE is checked first in `rails_ok()` and persists across day-roll.
- Git sync: pull brought cloud-analyst log updates only (no code).

## Equity & PnL

- **Equity $26.55** (CLOB free USDC; 0 open positions anywhere; sniper open={}).
  Below the $40 kernel floor (standing 07-13 owner waiver, recorded at $39.40 —
  equity is now 33% below the waiver point; flagged in ESCALATIONS-adjacent terms
  in the ledger entry).
- 7d realized: sniper wallet-truth since go-live **−$12.85** (pre-fix −$5.48 void
  as measurement but real money; post-fix −$8.14; +$0.80 unattributed auto-redeem
  inflow). Weather/engine 7d: ~$0 (65 resolution records, no realized flow — paths
  dark, entries blocked by ruin_floor $89.16).
- System is now **fully risk-off**: burn rate zero. Only NEG_RISK_ARB + RECYCLE099
  remain armed inside klaus and both are entry-blocked by the ruin_floor rail —
  consistent with the drawdown wind-down rail (<50% of 30d-HW), which remains in
  breach.

## Sniper gate status (the number the loop turns on)

| Instrument | n | WR | CI | breakeven | verdict |
|---|---|---|---|---|---|
| Shadow offline gate | 99 | 97.0% | [91.5, 99.0] | ~96.3% | COLLECTING — re-decide n≥150 |
| Live post-fix tape | 36 | 91.7% | — | ~96.3% | STOPPED-BY-RAIL (PF 0.43) |

- KELLY activation: **NOT MET** (needs CI-lo > breakeven; 91.5 < 96.3) — moot
  while stopped. Gate-kill also not met (needs point < breakeven at n≥100).
- **Loss structure (drives the re-enable candidate):** all 6 losses across both
  tapes sit at p_model < 0.995. Shadow slices: p≥0.995 → 39/39 wins, +$9.00;
  p<0.995 → n=60, WR 0.950, −$5.21 (below breakeven). 15m cell: n=5, WR 0.800,
  −$3.86 (includes today's breaching loss). These are post-hoc slices at sub-100 n
  — pre-registered for the re-enable decision, not acted on.
- **Re-enable gate (pre-registered, ledger 11:33Z):** shadow n≥150; candidate
  policy {P_MIN 0.99→0.995, 5m-only} graded as its own slice; Wilson CI-lo > that
  policy's own avg-ask breakeven; restart at minimum size with written kill
  condition. The shadow recorder keeps accumulating rails-free evidence at zero
  cost while the path is dark.

## Actions taken (1 live-effect change; cap 2/day)

1. **UPDOWN_STOP created 11:27Z** — charter path-cut rail (PF 0.43 < 0.8 over 36
   resolved) + daily-stop breach. Ledger entry with re-enable condition written.
   Cutting a path on rail breach is Tier-1 (rails tighten freely).

## Actions REJECTED (with the failed gate)

- Kelly activation — CI-lo 91.5 < breakeven 96.3 (pre-registered condition unmet).
- Gate kill (permanent falsification) — point 97.0 > breakeven at n=99; the edge
  thesis is straddling, not dead. Stop + collect is the correct middle state.
- P_MIN 0.99→0.995 as an immediate policy change — rail-breach day (no optimizing)
  + post-hoc slice at n=60/39; pre-registered for the n≥150 re-enable read instead.
- Reverting the 07-15 frequency params (T_MAX 60s / MOVE_FLOOR 4bp) — no live
  effect while stopped; shadow_grade mirrors them, and the re-enable decision will
  re-choose the policy wholesale. Only 1 of 3 live losses (t_left 51.4s) was even
  admitted by the relaxation.
- Weather band re-enable — disp_ratio last 5 settled days pooled 0.675–1.097, all
  <1.10: condition NOT met.

## Experiments

- `updown_sniper_live` → **STOPPED-BY-RAIL** (07-16 review closed as CUT).
- `updown_shadow_offline_gate` → COLLECTING, re-decide n≥150 (~07-18); candidate
  re-enable policy pre-registered.
- `updown_multiasset_15m` → day-2 recording healthy (eth/sol/xrp 6,270 snaps each
  today); first per-asset grade at the 07-17 slot (needs ≥2 full days).
- Weather standing conditions unchanged (band trigger not met; MIN_LOCKOUT
  READY-ON-RAIL-CLEAR).

## Standing risks / watch items

- Equity $26.55 is 34% above the RESERVE_USD=$20 hard stop and below the kernel
  $40 floor on a standing owner waiver — any re-enable happens at minimum size
  into a thin wallet; the 5-share CLOB minimum makes true clip ~$4.85, i.e. ~18%
  of equity per fire. That ratio alone argues for waiting out the n≥150 read.
- +$0.80 unattributed inflow (likely PM auto-redeem of weather dust) — watch item;
  an unattributed OUTFLOW would be a bug hunt before anything else.
- 15m cadence is under-evidenced (n=5) and supplied today's breaching loss —
  gate it separately at re-enable.
