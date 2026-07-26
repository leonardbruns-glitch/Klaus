# EVOLVE weekly report — 2026-07-26

**First sentence, as the kernel requires: the loop realized $0.00 this week (zero
fires, zero settles — path cut since 07-19), the UPDOWN-SNIPER certainty-taker
class was KILLED today on its pre-registered gate, and the owner shut down the
weather engine, the daily actuator, and the liveness watchdog on 07-24 — the loop
is now weekly-only, with no live path and no measured +EV class anywhere.**
Tracked capital rose $21.50 → $88.75, but every cent of that (+$67.25) is
OWNER-MANUAL trading, not loop PnL.

## JOB 1 — Scoreboard (computed)

| Metric | Value | Source |
|---|---|---|
| Loop realized PnL (week) | **$0.00** | tape: 0 SETTLEs since 07-19 08:04Z (last = the −$22.09 cut loss) |
| Fires/day | 0 (UPDOWN_STOP since 07-19 11:26Z; tape = stop_file skips only) | logs/updown_sniper.jsonl |
| Equity | **$88.750373 cash, 0 open positions** | CLOB fetch_usdc_balance + data-api positions (value $0.00) |
| Equity delta vs 07-19 | +$67.254931 — **owner-manual**: 3 btc-updown-5m round trips 07-24/25 (+15.34, +38.92, +12.99), on-chain reconciled to the cent | data-api activity |
| Weather residuals | $0 (no new trades.jsonl rows; last row = 07-19 CAPITAL_CORRECTION) | trades.jsonl |
| NEG_RISK_ARB / RECYCLE099 | 0 fills; **not even scanning since 07-24 10:10Z** (klaus owner-stopped) | journalctl |
| Kelly | n/a (off since cut) | — |
| $10k/mo trajectory | **NOT on it.** Loop lifetime sniper PnL −$17.90; no live path; no CI-cleared edge; binding constraint = strategy-class discovery, which is now owner-level (see below) | computed |

Kernel floor note: equity $88.75 > $40 — the floor blocker on re-arms is lifted,
but nothing is eligible to arm (class killed).

## JOB 2 — Strategy review (verdicts executed)

- **updown_crossing_reenable_gate → KILLED** (the operative verdict of the week).
  Post-cut CROSSING p≥0.995 5m: n=127 ≥ 100, point WR 0.9528 < BE 0.9651, CI-lo
  0.9008, sim −$8.88. All-history n=246 point 0.9634 < BE 0.9641. The kill was
  KILL-LOCKED since 07-23 and formalized today (the 07-24/25 daily slots that
  would have executed it never ran — timer owner-disabled). Graveyard #15.
- **Class-wide confirmation:** pooled 5-asset 5m crossing n=469 WR 0.964 < BE
  0.965, ROI −0.1%/$. Per-cell: btc REJECTED n=152 (−$2.45; p≥.995 n=91 WR 0.945
  −$8.25); xrp 48W/5L −$14.59; **eth clean-cell broke** (50W/2L, −$2.40; was
  38/38 on 07-23); doge (+$2.80, 41W/1L) and sol (+$2.17, 35W/1L) point-positive
  at n≈40, CI nowhere near. Cells stay COLLECTING as the graveyard-contradiction
  ledger only (review 08-02); promotion needs the reinforced gate.
- **Rescue strata all broke out-of-sample** (updown_margin_strata 07-26):
  mv≥8bp took 5 losses at 8.8–10.7bp (n=170, no clear); t_left [15,30)s
  dead-zone REJECTED on its own kill criterion (8 of 17 losses outside the zone);
  sig-real +0.6%/$ point cannot clear CI before n≈3000. 15m step dead (n=38 WR
  0.921, −$7.54).
- **NEG_RISK_ARB / RECYCLE099:** dormant → halted 07-24 with klaus. No loop
  action possible (units are owner-domain).
- **Weather dark flags:** stayed dark all week ✓. Band re-enable trigger last
  readable window 07-18..07-23: 2 of 5 settled days ≥1.10 — NOT met; the
  disp_ratio sensor is now UNMONITORABLE (klaus stopped). Ladder: disarmed ✓
  (cron runs with SPRINT_LADDER_LIVE=0).

## JOB 3 — Experiment slot: spent on falsification (per the killing-beats-designing clause)

Designed, measured, and killed ONE candidate inside this run rather than
registering it blind: **updown_divergence_fade** (buy the cheap side where
p_model≥0.995 but certainty ask ≤0.95 — motivated by the class's losses
clustering at low asks and the owner's profitable manual cheap-side trade).
Result on history n=136: cheap-side WR 0.074 vs BE 0.126, **ROI −50%/$**, 0 wins
in 4 of 5 assets; the certainty side in the same windows is ALSO −EV (WR ~0.926
vs BE ~0.955). Divergence windows are efficiently priced; the vig eats both
sides. Graveyard #16; script kept at `analysis/crypto/updown_divergence_fade.py`.
Five falsification verdicts executed this week (gate kill, t_left reject,
mv-stratum break, eth-cell break, divergence-fade) — registering a sixth stratum
of a five-times-falsified class to fill a template would have been the exact
failure the design rule warns against.

## JOB 4 — Loop health & self-evolution

- **Daily runs 07-24/25/26: ZERO — `klaus_evolve_daily.timer` disabled by the
  owner 07-24 10:09:29Z** (with `klaus_liveness.timer` at 10:09:12Z and
  `systemctl stop klaus` at 10:09:40Z; SSH 45.85.251.173 10:07–10:13Z; the
  watchdog restarted klaus mid-shutdown at 10:08:46Z and was then disabled —
  intent unambiguous). Honored per kernel; retro-registered in ledger.jsonl;
  ESCALATIONS + PENDING_HUMAN entries written. klaus left in its cosmetic
  'failed' state (still `enabled` — returns on reboot; owner decision flagged).
- **Amendment APPLIED (second reading, 7 days):** interactive/owner live-effect
  changes must be ledger-registered at deploy; next unattended run retro-registers
  gaps. This week's owner shutdown going undocumented for 2 days is the proof case.
  CHARTER.md deployment discipline item 6.
- **Prompt maintenance:** weekly_prompt.md header rewritten to the post-kill,
  weekly-only reality (class dead, klaus stopped, owner trades manually, re-sync
  bankroll each run). Validated via static launcher gates: CHARTER-grep PASS both
  prompts, INVARIANTS sha256 pin PASS. daily_prompt left intact (dormant — no
  vehicle while the timer is disabled).
- **Reviews closed (3, all due today):** disk-reclaim r3 KEEP (disk 75%, graders
  ran clean on .gz); daily_prompt 07-19 rewrite KEEP-AND-DORMANT; weekly_prompt
  wiring-test correction KEEP (this run used the static gates, no deadlock).
- **Bookkeeping:** bankroll.json synced 21.495442 → 88.750373 (CLOB truth; 0
  opens). Standing rule added to prompt: re-sync each weekly while the owner
  trades manually.
- **Cloud analysts (5, weather-era, advisory):** NOT retired — their spend is the
  owner's claude.ai budget and they are the only remaining daily measurement now
  that the daily actuator is off. Recommendation in PENDING_HUMAN: retire all but
  pnl-ledger until a new strategy class exists. Mirror already ships sniper
  extracts (07-19) and pushed clean through the week.
- **No thrash:** zero live-effect changes by the loop for 22 consecutive days.

## Next week's single biggest lever

There is no measurable lever left on current sensors: every certainty-class
variant and its inverse are graveyard entries, weather sensing is owner-stopped,
and equity is $88.75. The lever is an OWNER DECISION (PENDING_HUMAN #2–4): either
re-enable instrumentation around the owner's own profitable manual trading (the
only positive-PnL activity on this account in weeks), fund/point the loop at a
new market family, or go fully dormant. Absent owner input, next weekly:
re-sync bankroll, verify recorders alive, read the multiasset ledger (review
08-02), and stop — no burn, no invented experiments.
