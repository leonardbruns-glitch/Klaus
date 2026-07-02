# PENDING HUMAN — items the evolve loop may not decide alone

Append-only queue. The human clears items by deleting them (optionally noting the
decision in state_log.md). Agents: never delete another entry, never act on an item
here until the human has answered.

## 2026-07-02 — seeded at loop build (EVOLVE v2)
1. **Engine-level kill switches are config-disabled** (`max_daily_loss_pct=0`,
   `ruin_floor=0` — see weather_arb.py ~L8204). The charter rails are enforced
   procedurally by the daily agent instead (1×/day granularity). If you want a
   mechanical intraday halt, that's a Tier-3 threshold decision: say the word and the
   loop wires it.
2. **`config/auto_kill.json` has zero readers in live code** — the 08:30 daily_audit
   cron writes it, but `is_killed()` is called nowhere, and its strategy-class list
   predates STWA/BAND. Candidate: wire an is_killed-equivalent check (class
   `WEATHER_STWA` + band paths) into the band loop as a protective filter. Left to the
   daily agent as a Tier-2 candidate; flagged here because it touches the risk surface.
3. **bond_watchdog retired** (disabled at install): it watched the retired BOND scanner
   and could never fire — superseded by `klaus_liveness.timer`, which watches the
   actual service + log heartbeat. Delete `/etc/systemd/system/bond_watchdog.*` and
   `/usr/local/bin/klaus_bond_watchdog.sh` whenever convenient.
4. **Loop cost note:** the actuator runs headless Claude (fable-5) 1×/day + weekly +
   on crash-loops, `--max-turns 250`, ~3h timeout. If spend needs a cap, options are a
   cheaper model in `ops/evolve/run_agent.sh` or lower turn caps — human call.
