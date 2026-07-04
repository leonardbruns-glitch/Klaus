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
