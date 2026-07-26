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

## 2026-07-03 — SPRINT_LADDER armed under direct user mandate (interactive session)
The owner instructed three times on 2026-07-03: minimum $10k profit in 30 days, full
freedom, no human interaction. The interactive agent armed `strategy/sprint_ladder.py`
(bold-play mode-confirmation taker shots, $60 sleeve, 75%/shot, $20 hard cash reserve,
max 2/day) via crontab. This intentionally overrides the $50 ruin floor (now ~$20-25
effective) and the charter's no-taker-YES spirit — for the LADDER PROCESS ONLY; the STWA
engine flags remain charter-governed. Success probability was assessed honestly at ~1-3%
and logged in state_log 20:00 UTC. EVOLVE agents must not kill the cron; humans may, by
deleting the crontab line.

## 2026-07-08 — OWNER DECISION NEEDED: capital vs. mandate arithmetic
Owner re-affirmed the $10k/30d mandate with full delegation. Session audit result:
equity $136.77, day 5, required rate ≈ +17%/day compounded for 25 days. No measured
edge on the books compounds at ANY positive rate right now (band −5.4% n=465; pair
slice not separately harvestable; lockout family paused on oracle divergence; ladder
= authorized coin-flip sleeve, 4W/4L +$85.36). The only lever that changes SCALE is a
deposit — and a deposit does NOT buy a validated edge, only evidence velocity and
absolute $ IF one re-validates (NO d+1 +6.6% n=62 collecting; lockout divergence
study 07-13). Decision: (a) deposit + patient evidence-gated rebuild, (b) ride the
$137 ladder lottery as-is (current posture), or (c) explicitly accept higher ruin
probability (e.g. 3 shots/day). Bot continues (b) until told otherwise.

## 2026-07-13 — UPDOWN-SNIPER live-arm decision (owner input required)
Owner mandated 5/15-min BTC. Research findings (state_log 10:35 UTC): fee-wall premise
falsified (true fee 0.07·p·(1−p), takers only, makers free); stable +EV niche = buying
near-certainty (0.90–0.99) in the final 15–120s, WR 0.95–1.00, +1–7%/$ net, ~$55k/day
of such flow, dispersed across 200+ wallets. Shadow recorder klaus_updown_shadow.service
is live; n≥100 fill-simulation gate expected within ~24–36h.
DECISION NEEDED: ANSWERED 2026-07-13 10:46Z — owner waived floor in chat ("go live"); sniper armed with scoped rails (see ESCALATIONS.md same date).
stop −$6, halt on 3 consecutive losses) requires EITHER an explicit owner floor waiver
for this strategy OR a deposit raising equity above $40. Reply in chat.

## 2026-07-26 — WEEKLY: certainty-taker class KILLED; your shutdown + manual trades recorded; 3 decisions ready
1. **The UPDOWN-SNIPER certainty class is dead on its own pre-registered gate**
   (post-cut n=127 WR 0.9528 < BE 0.9651; pooled 5-asset n=469 point < BE; every
   rescue stratum broke out-of-sample; inverse cheap-side trade also −50%/$ n=136).
   Graveyard #15/#16. Nothing is armed; wallet $88.75 cash, zero opens.
2. **Your 07-24 shutdown is honored** (klaus stopped, daily evolve + liveness timers
   disabled — the loop will not touch systemd units). Loop now runs WEEKLY ONLY.
   If you want daily coverage back: `systemctl enable --now klaus_evolve_daily.timer
   klaus_liveness.timer`. If the klaus stop is permanent, also `systemctl disable
   klaus` (it is still enabled and will return on reboot, currently shows 'failed').
3. **Your manual trading (+$67.25 in 3 round trips) outperformed everything the bot
   has measured.** If you plan to keep trading this account manually, tell the loop
   whether to (a) keep the 5-asset shadow recorders running as your instrumentation,
   or (b) go fully dormant. Recorders cost ~400MB/day disk, zero API spend.
4. **Cloud analyst routines (5, weather-era):** advisory-only since 07-15. With the
   sniper class killed and weather dark, gate-keeper/calib/strategist have no live
   object. They spend YOUR claude.ai budget daily — recommend retiring all but the
   pnl-ledger until a new strategy class exists. Loop did not retire them itself
   (your spend, your call).
