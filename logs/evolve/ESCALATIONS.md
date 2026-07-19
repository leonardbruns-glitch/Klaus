# ESCALATIONS — decisions journal (no human in the loop)

Append-only. Unattended agents record kernel-adjacent decisions, open questions, and
invariant-conflict cases here. NOTHING blocks on this file — the charter tells you what
you may decide yourself; the kernel tells you what nobody may. An interactive session
reviews this whenever one happens to occur. The weekly agent processes open items.

## 2026-07-02 — loop v2 constitution (interactive session, owner directive)
- **RESOLVED — engine ruin_floor armed at $40** (config.py; was 0.0/disabled per the
  2026-05-15 owner instruction — superseded by the 2026-07-02 full-autonomy directive:
  with no human backstop, the machine must have a mechanical one).
- **OPEN — bankroll daily-reset suspect:** bankroll.json shows daily_start_capital=15.95
  vs capital=72.27 and bot.log has no DAILY_RESET lines; if `maybe_reset_daily` isn't
  firing, the 14% daily-loss halt computes off a stale base (could over- OR under-trip).
  Daily agent: audit `risk/manager.py` reset wiring against the live log, fix per
  deployment discipline.
- **OPEN — auto_kill wiring:** `config/auto_kill.json` (08:30 cron) has zero readers;
  `is_killed()` uncalled, class list predates STWA/BAND. Candidate: wire an equivalent
  protective check (WEATHER_STWA + band paths) into the band loop, or retire the cron
  and rely on the charter's path-cut rail. Loop-decidable (protective).
- **NOTE — loop cost:** actuator = fable-5, 2×/day + weekly + crash-repairs,
  max-turns 250. Owner accepted cost implicitly with the full-autonomy directive.
2026-07-02T06:20:33Z KERNEL TAMPER: INVARIANTS.md hash mismatch, restore failed — refusing to launch daily agent
2026-07-02T11:23:06Z KERNEL TAMPER: INVARIANTS.md hash mismatch, restore failed — refusing to launch daily agent
2026-07-02T21:53:16Z KERNEL TAMPER: INVARIANTS.md hash mismatch, restore failed — refusing to launch daily agent
2026-07-03T11:23:16Z KERNEL TAMPER: INVARIANTS.md hash mismatch, restore failed — refusing to launch daily agent
2026-07-04 22:20Z DAILY: actuator schedule unreliable — 4 of 5 daily slots (07-03 11:23/14:05/21:53, 07-04 11:23) died on "session limit" before doing any work (both primary and fallback model); tonight's 21:53 run is the FIRST completed daily. Unattended agents may not touch the systemd units — an interactive session should stagger the slots away from limit-reset boundaries (11:23 slot hit "resets 12pm" twice) and/or configure a cheaper fallback model in run_agent.sh. Until then assume the loop runs ~1x/day at best; liveness watchdog + crons carry the mechanical safety.
2026-07-04 22:20Z DAILY: RESOLVED — the 07-02 "bankroll daily-reset suspect" open item: maybe_reset_daily() had zero callers + last_utc_day never persisted; wired + persisted in commit 2813daa1e. Verify DAILY_RESET fires at 2026-07-05 00:00Z (review 07-06, ledger.jsonl).
2026-07-05 WEEKLY: actuator schedule STILL unreliable — 07-05 11:23 slot also died on session limits (score now 2 completed / 9 attempted since 07-02; the only completions are 07-04 21:53 daily + this weekly). Systemd units are kernel-protected, so the loop cannot re-stagger its own slots. Mitigation shipped at prompt level: daily_prompt.md STEP 0 now makes any completing run cover the whole failed-slot backlog (review_dates + missed analyst reports). Interactive session should still re-stagger timers away from limit-reset boundaries and/or set a cheaper fallback model in run_agent.sh.
2026-07-05 WEEKLY: RESOLVED (retire-in-place) — the 07-02 "auto_kill wiring" open item. Decision: do NOT wire is_killed() into the band loop. Rationale: the strategy-class list predates STWA (would guard nothing real); the engine now has TWO armed mechanical rails (ruin_floor=$40 at risk/manager.py:242 blocks new entries; 14% daily-loss halt armed 07-04 commit 2813daa1e) plus the charter path-cut rail enforced procedurally. The 08:30 cron writing auto_kill.json is harmless — left running as a sensor. Revisit only if a new live path enables.
2026-07-05 WEEKLY: SENSOR SEAM (no action, documented) — engine "capital" (bankroll.json, cash proxy) hit $39.69 < ruin_floor $40 intraday today while true equity was ~$217 (cash $10.69 + $194 resolved-pending redemptions + $12 at-risk legs): cash->position conversion (2 ladder fires + M1beta $75.85 Moscow harvest) reads as "loss" to the cash-only proxy. The floor blocking NEW entries while cash is genuinely $10 is CORRECT behavior (nothing to trade with), so this is protective, not a defect; but daily agents must never report a floor/halt event as capital loss without decomposing cash vs positions (charter risk-rail preamble already mandates this). Self-resolves at redemption (~00-02Z).

## 2026-07-05 22:25Z (daily 21:53 slot) — ruin-floor comparator deferral + ladder/account overlap
- Deferred (deliberately) the weekly-spec'd ruin-floor comparator + ratchet: correct "tracked capital" needs ladder shots (separate cron process, not in risk.open_positions) and resolved-pending redemptions (invisible to both cash and positions until the redemption sweep). Auto-correct (main.py:455-492) already does cash + engine-positions-at-cost; the gap is exactly the two off-engine components. An evening kernel edit with a live ladder shot pending was judged worse than one more day of the protective false-halt seam. Morning slot: implement comparator, observe one day, THEN ratchet $40 → 0.40×30d-HW (~$88).
- Observation for the next interactive session: the sprint-ladder sleeve ($206.94) now ≈ the entire account's free cash. The ladder's per-shot cap ($45) and $20 reserve are the only live bounds; the charter's engine rails do not bind it (principal carve-out). If the owner wants the account-level split restored, that is an owner decision — flagging, not acting.
- audit.log daily cron has said "no WEATHER trades in last 1d" every day since 06-24 while trades exist — a broken sensor filter (likely asset/tag mismatch). Candidate mechanical fix for a future slot; logged so it stops being invisible.

## 2026-07-06 22:10Z — EVOLVE daily (evening slot; morning slot died on session limit)
1. **Daily-loss halt is wired to the wrong surface.** `BankrollTracker.is_halted`
   (14% rail, armed 07-04) is consulted ONLY in the STWA taker-signal path
   (weather_arb.py ~8234) — which is disabled. The maker/band/pair, M1β, and
   MIN_LOCKOUT paths have no halt check: on 07-06 the engine kept posting through a
   −47% tracked-capital day (M1β fired at 12:01Z with the day already past −14%).
   Fix spec (morning slot, Tier-1 tighten but needs care): (a) compute the halt on an
   equity proxy = bankroll.capital + sprint-ladder open shots at cost (else every $45
   ladder fire reads as −20% and false-halts the engine for the UTC day); (b) gate
   maker posting + M1β/lockout fires + pair posting on `is_halted or is_ruined`;
   (c) settlement/redemption/cancel paths stay un-gated.
2. **Rail-design seam flagged for the WEEKLY (amendment protocol — daily may not
   amend):** the 30d high-water ($222.90) is 85% ladder coin-flip variance (07-05
   weekly's own words). With sleeve $117 vs engine cash ~$108, every 2-loss ladder
   day (~30% of days at p≈0.45/shot) mechanically breaches "equity < 50%·HW" and
   winds down engine paths that didn't cause the loss. Tonight's wind-down was
   executed as written (kernel: no reinterpretation under a losing streak). The
   weekly should consider an amendment: exclude the principal-authorized sleeve from
   the HW basis, or key the rail to engine-attributed equity. Both readings recorded;
   data will decide.
3. **Lockout provenance gap:** "official {AWC,NWS} only" is NOT sufficient — the
   Moscow 07-06 false lockout came from an official SPECI (11:55Z, 23.0°C) that the
   WU-displayed high never showed (resolved 22°C). Non-US stations lack the 1-min
   ASOS cross-check. lockout_oracle_divergence study registered; lockout family
   stays off until it reports.

## 2026-07-08 21:53Z (EVOLVE daily evening — breached-rail day)
1. **Kernel-enforcement gap CLOSED for the sprint ladder (kernel-adjacent decision,
   recorded per INVARIANTS #5):** INVARIANTS #2 halts ALL live paths below $40
   tracked capital, but nothing enforced it for the cron ladder — engine ruin_floor
   ($89.16) does not gate `sprint_ladder.py`, and its RESERVE_USD floors *cash* at
   $20, i.e. BELOW the kernel. From tonight's $84.47 tracked, two losing shots cross
   $40 with no mechanical stop. Deployed `KERNEL_FLOOR_USD=40` skip in `fire()`
   (commit 64a4e312b). The daily prompt's "may NOT touch the ladder" was read as
   subordinate to the kernel (INVARIANTS override the prompts, by their own text).
   This does NOT alter sizing, reserve, stake fraction, or shot selection above $40
   tracked; below $40 it enforces exactly what the kernel already mandates. A
   false-skip is possible while won-but-unredeemed value is in flight (invisible to
   cash + open-cost) — protective-only, self-resolves at redemption.
2. **Wind-down rail re-breach executed as written (2nd occurrence of the seam
   flagged 07-06 #2):** equity $83.93 = 37.7% of 30d-HW after China ladder losses;
   MIN_LOCKOUT_LIVE re-cut ~7h after the owner-directive enable. The flag posted 0
   orders while live, so the flip-flop cost $0 — but this is now the concrete
   flip-flop case the weekly amendment discussion predicted: an evidence-passed
   engine path (197/197, CI-low 98.1%) is being toggled by owner-sleeve variance it
   does not cause. Both prior readings stand in AMENDMENTS consideration; nothing
   for the daily to do beyond executing the rail as written.
3. **Ledger discipline gap:** the 07-08 interactive session deployed 4 live-effect
   changes (UUWW blocklist, margin revert, MIN_LOCKOUT enable, ladder 3/$60 +
   velocity) with state_log entries but NO ledger.jsonl pre-registration. Retro-
   registered tonight. If interactive sessions bypass the ledger, review_dates and
   revert_conditions silently vanish from the loop's working set — worth a line in
   CLAUDE.md or the charter's deployment discipline at the next weekly.

## 2026-07-13 10:46 UTC — INVARIANTS #2 floor waiver (owner, interactive)
Equity $39.40 < $40 floor. Owner explicitly directed live trading of UPDOWN-SNIPER
("you have to make it happen with 5-15min btc markets" → "can we start now" → "go
live"). Interactive session + owner instruction = constitutional authority per
INVARIANTS preamble. Waiver is SCOPED: only klaus_updown_sniper.service, $5 clips,
day-stop −$6, 3-consecutive-loss halt, $15 max open. All other live paths remain
halted (ladder disarmed 09:25Z, engine ruin-floor armed). n≥100 shadow gate continues
accumulating in parallel; policy re-fit from shadow data due within 36h.

## 2026-07-13 22:12 UTC — EVOLVE evening (kernel-adjacent record)
- **Trading continues below the kernel floor under owner waiver.** Equity $34.86
  CLOB-actual (< $40 kernel, < $50 ruin, < $75 weekly floors). Owner explicitly armed
  UPDOWN-SNIPER live at 10:46Z with the floor waiver recorded. The loop did NOT
  re-litigate the arm; it fixed the path's settlement-booking bug (84/196 labels wrong),
  added SIG_FLOOR against the σ-junk certainty mode (the day's one true loss), and
  corrected phantom accounting (−9.79 booked → −4.29 true).
- **Rail-proportionality tension left for interactive review:** the owner-set sniper
  rails ($5 clip, −$6 day-stop) were sized at arm time. At $34.86 equity a worst-case
  day (stop + one-clip overshoot ≈ −$11) is ~32% of equity; two such days reach the $20
  reserve. The loop did not override owner-set numbers same-day; flagging that either a
  deposit or proportional rail shrink (e.g. clip $3 / stop −$4) is needed if equity
  stays this low.
- **Rails acted on false data today (resolved):** the −$6 day-stop tripped on phantom
  realized −9.79; truth was −4.29. Fixed at source (settle booking). INVARIANTS #4.

## 2026-07-19 14:25 UTC — EVOLVE weekly (kernel-adjacent records)
1. **Kernel-floor re-entry condition (decided within charter, recorded here):**
   equity $21.50 < $40 kernel floor with ALL live paths now halted (sniper cut by
   its own PF rail 11:26Z; weather dark; ladder disarmed; engine ruin_floor blocks
   NEG_RISK/RECYCLE entries). The 07-16 owner waiver chain authorized the
   CANDIDATE arm; that arm ended when the rail cut it. Ruling: any future live
   arm below the $40 floor requires a NEW owner waiver — gate pass alone
   (updown_crossing_reenable_gate) writes to PENDING_HUMAN.md and stops. The loop
   cannot waive the kernel floor for itself, ever.
2. **Daily 11:23Z slot is structurally dead — needs an interactive session to move
   the timer (kernel-protected unit):** 5 of 7 morning slots this week died on
   "session limit resets 12pm (UTC)" (07-13/14/17/18/19); last week's weekly
   (07-12, both attempts) died the same way. The 11:23 slot shares a limit window
   with the 4 cloud analyst routines (07:09–10:13Z commits daily). Today's failure
   had real cost: the morning daily created UPDOWN_STOP + the shadow_grade
   CROSSING edit, then died before logging/committing — 3h of unregistered
   risk-state. Proposed fix for an interactive session: move the first OnCalendar
   in klaus_evolve_daily.timer from 11:23 to ~12:10 UTC (past the reset). The loop
   may not edit systemd units (INVARIANTS preamble).
3. **First-loss postmortem is in the ledger, not here:** the −$22.09 loss was the
   declared worst case of owner-waived 50%-Kelly sizing (worst day −50% via
   MAX_LOSSES_DAY=1) operating as designed. No rail failed; MAX_LOSSES_DAY halted
   the day at loss #1, the PF rail cut the path at the 11:23 slot. What DID fail
   silently was the gate population (first-fire slice blind to crossing fires) —
   fixed and re-registered this run.
