# EVOLVE daily report — 2026-07-08 (21:53Z evening slot; morning slot died on session limit — this run covered the full day)

## First paragraph, honest per kernel
**Breached-rail day.** Equity at 21:53Z is **$83.93** (cash $59.59 CLOB-actual +
Chicago ladder shot at cost $24.34) = **37.7% of 30d-HW $222.90** — the drawdown
wind-down rail (50% = $111.45) that cleared 07-07 evening **re-breached** at ~16:35Z
today when both China ladder shots lost (Shanghai −$6.84, Guangzhou −$43.78,
authorized coin-flips). Tracked capital $84.47 sits **below the ratcheted ruin floor
$89.16** — engine no-new-entries is armed, and that is the intended behaviour, not a
bug. Daily realized ≈ −38% of daily_start $136.77, re-tripping the −14% rail → no
size/ceiling increases until **07-10 21:53Z**. 7d realized **−$98.81, PF 0.095,
n=36** — all of it from paths already cut 07-02/07-06; the engine had **zero**
resolved trades today and post-wind-down engine flow remains ≈$0. The bleed is
stopped on the engine side; today's damage is 100% the owner-mandated ladder sleeve
doing what a 75%-per-shot coin-flip sleeve does.

## Service health
`klaus` active all day; restarted 22:00Z for tonight's deploy, fresh `[WA]` cycle
verified 22:02Z, balance polling live. No crashloop flag. Ladder cron on 10-min
cadence (syslog-verified); recurring `400 Could not create api key` py_clob client
noise since ≥07-04 is benign (fires/settles unaffected) — documented, not chased.

## Actions taken (2 live-effect, both cuts — commit 64a4e312b)
1. **MIN_LOCKOUT_LIVE True→False** — charter drawdown rail executed as written.
   Rail-driven, NOT evidence-driven: the divergence study's 197/197 (margin≥1.0,
   Wilson CI-low 98.1%) stands; the flag posted **0 orders** during its 7h
   owner-directed re-enable, so the cut costs ≈$0. Re-enable condition written to
   ledger: equity ≥ 50%·30d-HW — evidence gate already satisfied, no re-proof needed.
2. **sprint_ladder.py kernel-floor guard** (`KERNEL_FLOOR_USD=40` skip in `fire()`) —
   INVARIANTS #2 halts all live paths below $40 tracked, but nothing enforced it for
   the cron ladder (engine ruin_floor doesn't gate it; the $20 cash reserve floors
   BELOW the kernel). From $84.47 tracked, two losing shots cross $40 unstopped.
   Kernel-adjacent reasoning recorded in ESCALATIONS #1. Guard is inert above $40.

Deployment discipline: py_compile ✓, evidence-citing commit ✓, push ✓, restart ✓,
fresh-cycle verify ✓. Live surface now: **NEG_RISK_ARB + RECYCLE099 + redemption**
(+ principal-authorized sprint ladder, outside charter scope) — exactly the 07-06
wind-down posture.

## Actions REJECTED / deferred (with the failed gate)
- **Isotonic settled-lane rebuild + refit-cron repair (PA-1)** — both calib and
  research audits name it the top lever (live-refit cron dead since Jun 9, gauge
  degenerate, candidate map ruled un-deployable by the calib monitor itself).
  REJECTED **today only** on rail state: breached-rail day = cutting, not
  optimizing (daily prompt STEP 0). **Queued as the first action of the next
  non-breached morning slot.**
- **Any band/pair re-enable** — fresh join n=623: band YES +0.7% [−18.5,+23.9]
  ≈ zero edge; co-filled pairs +13%/pair only CI-clear at n=31 < 40 and
  conditional-on-fill. Fails n-gate and rail state both.
- **Reverting the owner's ladder 3/$60 raise** — outside charter scope (bounded
  tuning conditions not met: no 2-day zero-candidate streak, no n≥10 gate-selection
  evidence). The −14% freeze bars further increases until 07-10 21:53Z; cash
  ($59.59 − $20 reserve) bounds the next shot at ~$39.59 regardless.
- **PAIR_FAV_SUM_MAX loosening** (research-audit backlog item) — still rejected;
  same naked-YES surface the clip data condemned 07-05.

## Sprint-30 ladder supervision (STEP 2b)
- Health ✓ (cron cadence verified), settlement integrity ✓ (China shots settled
  16:30Z within hours; sleeve arithmetic 94.74 − 24.34 = 70.40 exact).
- Today: 3/3 fires used — Shanghai lost −$6.84, Guangzhou lost −$43.78, **Chicago
  88–89°F open** ($24.34 @0.55, 44.25sh, settles ~05:00Z 07-09; win pays ~+$19.9).
- Lifetime: 11 fired / 10 resolved / **4W-6L, net ≈ +$14**. The 07-05 "+$148.70
  week" has round-tripped — stated plainly: this sleeve is p≈ask variance by
  design, and the week's equity path (+$88 ahead → −$122 behind day-6 target)
  is what that looks like.
- Sprint gap (last tracker line 07-07 23:50Z): equity $136.77 vs target $188.21 =
  −$51.44; tonight's 23:50Z line will restate to ≈ −$122 (equity $83.93 vs ≈$206).
- New guard: kernel floor $40 (above). No tuning of shot-selection gates (conditions
  not met).

## Experiments
- **lockout_oracle_divergence → COMPLETED-EARLY** (run 07-08 under owner directive,
  was 07-13): lockout TAKER killed (58/58 executable at divergent stations, EV
  −6.5%/fill); MIN maker evidence-passed (197/197) but rail-gated off tonight.
- **temporal_lock_p5 → KILLED** (472 candidates, −EV every slice after fee; scanner
  d+1 date-join bug found — fix before any future P5 work).
- **nhc_count_lock → KILLED** (0 executable in 11d).
- **minmax_coherence → DEFERRED** (~$5-15/wk, needs new executor; not worth code
  risk).
- **pair_clip_cofill → ACCRUAL-FROZEN flag added**: the counterfactual cannot accrue
  while BAND_LIVE=False (pair branch nests inside the YES posting loop). n≈9/side
  frozen since 07-06. The 07-19 review will be empty unless the weekly either wires
  a band shadow-posting mode or extends the review — handed to the weekly.
- yes_capture_shadow (review 07-11), band_dial (28d), band_reenable_trigger
  (disp_ratio 0.817 < 1.10, gauge stale pending PA-1): COLLECTING, no action.

## Bookkeeping / discipline
- Retro-registered the interactive session's 4 unledgered live changes in
  ledger.jsonl (ESCALATIONS #3 notes the process gap for the weekly).
- Gate ledger refreshed from tonight's VPS join (n=623) and committed.
- Backlog check: only today's 11:23 slot was missed since the last rc=0; its
  review-date work (freeze expiry decision) is handled here.

## Standing risks
1. **One losing shot from engine-halt territory, two from the kernel.** Chicago loss
   tonight → tracked ≈ $60; a further ~$39 shot loss → ≈ $20 < kernel $40 — the new
   guard now blocks the fire that would follow, but cannot block the loss that gets
   us there. No lever exists inside charter scope (ladder is owner-mandated).
2. **Wind-down flip-flop seam** (2nd occurrence): owner-sleeve variance toggles
   evidence-passed engine paths via the shared-HW rail. Weekly amendment discussion
   already seeded (07-06 ESCALATIONS #2, reinforced tonight).
3. **PA-1 calibration staleness** blocks the whole band re-enable tree; every day it
   slips, the dial/dispersion gauges degrade further.
4. Sprint mandate honesty: at $83.93 equity, day 6 of 30, target $10k — P(mandate)
   remains ~1-3% (unchanged from the 07-08 interactive audit; capital deposit is
   still the only real scale lever, flagged in PENDING_HUMAN).
