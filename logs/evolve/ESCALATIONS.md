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
