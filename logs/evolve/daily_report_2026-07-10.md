# EVOLVE daily report — 2026-07-10 (evening slot 21:53Z; morning slot died on session limit — this run covered the full day)

## Health & equity (first — per honesty rules)
- `klaus` **active**, fresh `[WA]` cycle lines through 21:53Z. No crashloop flag.
- **Equity $163.16, all cash CLOB-actual** (0 open ladder shots, 0 engine positions;
  bankroll capital == CLOB balance to the cent — comparator verified again).
- Rails: **ALL CLEAR, second consecutive slot.** 73.2% of 30d-HW $222.90 (rail
  $111.45); above ruin_floor $89.16. The **−14% freeze expired clean at 21:53Z
  today** — no re-trip during its window (07-09 +89%, 07-10 +2.9%).
- Today realized: **+$4.53 (+2.9%)** — all sprint ladder (Guangzhou +$30.00,
  Tokyo −$15.72, Shanghai −$7.41 = +$6.87 fills-basis; −$2.3 residual is
  payout/proxy dust — verified zero engine flow all day).
- 7d realized: **−$71.52, PF 0.108, n=26** — every row opened 07-02→07-06;
  this is 100% tail from paths already cut, not new bleed. Post-cut engine flow = 0.
- Sprint-30: day 7 of 30; equity $163.16 vs day-7 target ≈$256 → **≈ −$93 behind**.

## The day's deliverable: S3 dispersion gauge unblocked — and it says NO
The calib monitor's settled lane (the band's load-bearing edge gauge) was 8 days
label-stale — the cloud cannot fetch resolutions. Built and committed
`analysis/weather/settled_disp_ratio.py`: full pricer_eval files, last PRE_PEAK
ladder per city-date, implied σ (p_cal-normalized, °C) vs realized
|resolved − mode| with official-floored running_max as the label.

**Jul 3–10 pooled implied/realized: 0.848 · 0.889 · 0.881 · 1.228 · 0.740 ·
0.829 · 0.762 · 0.620.** The standing re-enable trigger (≥1.10 for 5 consecutive
days) is **not met** — one day above 1.10, never two consecutive; median-city
ratio ≤0.80 every day. Cross-validated against the cloud lane on the Jun 30–Jul 2
overlap (this method reads ~0.1 *higher*, so the inversion is not a method
artifact). The market keeps pricing LESS dispersion than realizes: the
standalone-YES band premise remains dead through 07-10. This directly answers
research-audit assumption A1 ("do not re-enable before seeing Jul 3–9 dispersion").

## Actions taken (live-effect changes: **0** of 2 allowed)
1. **Measurement, no capital**: settled_disp_ratio.py + 410-row JSON committed;
   gate ledger refreshed from tonight's `band_resolution_join.py` (n=671) and
   `band_sum_posted_slice.py` (G7 n=396).
2. **Ledger reviews closed**: capital comparator + ruin_floor ratchet → **KEEP**
   (exact cash reconcile, drift auto-correct proven 07-09); 07-08 −14% freeze →
   **EXPIRED** clean.
3. **Experiments**: `band_reenable_trigger` updated with the measured verdict
   (STANDING-CONDITION, not met). All other statuses unchanged.

## Actions REJECTED (with the failed gate — as important as the actions)
- **BAND_LIVE re-enable** — three independent blocks: (1) binding pre-registered
  condition (post-guard pair n≥40) frozen at 0 while dark — structural, weekly
  07-12 decision; (2) standing disp trigger measured tonight and NOT met;
  (3) G7 [0.70,0.85] n=396 ROI +14.3% CI [−8.7,+41.6] AMBIGUOUS. Also the
  sub-0.70 book reads −29.8% CI [−55.0,+7.1] — near-significant *negative*.
  Recommendation left for the weekly: if the deadlock is broken, break it with
  **shadow-posting mode** (accrues G2b/G2c n at ~11 pairs/day, zero capital),
  not a live flip.
- **MIN_LOCKOUT_LIVE re-enable** — evidence gate passed (197/197 margin≥1.0,
  CI-low 98.1%) and rail-clear condition met, but the flag was changed 07-08
  21:53Z → **72h anti-thrash freeze until 07-11 ~22:05Z**. Deferred to the 07-11
  review. Deferral cost ≈ $0: it posted 0 orders in its 7h live window (~32
  shadow candidates/cycle, ~0 executable).
- **Isotonic candidate manual promote** — calib monitor + PA-1 concur: plateau is
  structural; auto-promote fires ~07-12 iff OOS Brier improves. Charter: no
  manual override of a working guard.
- **Ladder tuning** — no trigger: 3/3 fires today (no zero-candidate streak);
  negative-model-edge watch at n=2 (<10 rule).

## Experiments status
- band_reenable_trigger: STANDING-CONDITION, **measured, not met** (above).
- pair_fav_sum090 / pair_clip_cofill: ACCRUAL-FROZEN (dark); weekly 07-12 decides.
- yes_capture_shadow: COLLECTING; markout 94% adverse (informational only).
- band_dial_timeseries: 29/90 resolved days, DATA-COLLECTION.
- sprint_ladder (owner-mandated): 17 resolved 7W/10L, net ≈ +$117 lifetime
  redemption-basis; sleeve $179.69 reconciles exactly; cron healthy (the 17:10→22:00
  log silence is the benign cap-reached early-exit path — syslog shows every
  10-min firing, 0 tracebacks).
- KILLED/REJECTED (no change): temporal_lock_p5, count_lock, thermo, M1β
  thin-margin, lockout MAX-family taker.

## Standing risks
1. **pnl_ledger cloud routine stale 65h+** (last 2026-07-07T23:37Z) — the other
   four analysts are fresh; cannot restart cloud routines from the VPS. If it
   misses 07-10 as well, the weekly should re-register the routine.
2. Both Jul 3–9 regime reads (dispersion inverted; YES ROI oscillating around 0
   with huge CIs) say the band has no measured edge to return to — the 07-12
   structural decision should weigh capital-free shadow accrual over any live flip.
3. Ladder remains the only equity-moving path (owner-mandated variance instrument,
   WR 41.2% at avg fill 0.43 ≈ at-ask coin-flips + 0.99-exit velocity).
4. Morning EVOLVE slots keep dying on session limits (07-08, 07-09, 07-10) —
   evening slots are carrying the whole loop; acceptable but single-point.
