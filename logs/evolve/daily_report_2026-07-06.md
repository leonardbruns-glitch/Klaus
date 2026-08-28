# EVOLVE daily report — 2026-07-06 (21:53Z slot; morning 11:23 slot died on session limit — this run covered the full day)

## The first paragraph, honestly
**The system is bleeding and was wound down tonight.** Equity $108.35 (cash, actual
balance line; the 2 open engine positions are resolved-dead, worth $0) vs $216.68
same time yesterday — a −50% day. Realized: sprint ladder −$90.00 (both shots lost),
engine −$41.25 (Moscow M1β false lockout −$24.65, pre-clip-guard one-sided band-YES
remnants −$16.38, post-guard pairs +$0.75 — the only green). The charter drawdown
rail (equity < 50% of 30d-HW $222.90 = $111.45) is breached ⇒ wind-down executed:
**BAND_LIVE / M1_BETA_PROBE_ENABLED / MIN_LOCKOUT_LIVE all False** (commit
fccd5e46e, deployed 22:08Z, service verified active). Live surface is now
NEG_RISK_ARB + RECYCLE099 + redemption, plus the principal-authorized sprint ladder
(outside charter scope). This was a cutting day; no optimization was attempted.

## Service health
- `klaus` active; restarted 22:08Z post-deploy; fresh [WA] cycles verified.
- DNS/CLOB self-heal: no incidents today. Liveness watchdog: no restarts.
- Sprint-ladder cron: healthy, */10 fires verified in syslog through 22:00Z
  (silence in its log after 16:30Z = both shots settled + daily cap, by design).
- 7d realized (trades.jsonl, resolution-joined): **−$94.64, PF 0.11 (n=36)** — but
  −$68+ of that is paths cut 07-02/07-03 finishing their resolution tail. Post-cut
  flows: pairs small-positive, RECYCLE099 positive.

## Rails (computed from real data, not bankroll.json)
| Rail | Status |
|---|---|
| Kernel floor $40 | CLEAR (equity $108.35) |
| Daily −14% halt | **BREACHED** (−47% tracked capital) → no size/ceiling increases until 07-08 21:53Z |
| Wind-down (equity < 50%·30d-HW) | **BREACHED** ($108.35 < $111.45) → wind-down executed this run |
| Path-cut (7d PF<0.8, n≥20) | WEATHER_MAKER n=18 just under n=20; superseded by wind-down anyway |
| Never end run with klaus inactive | active ✓ |

## Actions taken (2 ledger entries; rail-mandated cuts)
1. **WIND-DOWN (live effect):** BAND_LIVE=False (pair/band → would-post shadow;
   clip-guard counterfactual keeps accruing), M1_BETA_PROBE_ENABLED=False,
   MIN_LOCKOUT_LIVE=False. Evidence in commit fccd5e46e + ledger. Re-enable gates
   written in ledger.jsonl (equity recovery + n-gates; lockout family additionally
   needs the divergence study).
2. **Risk state registered:** 48h freeze on any size/ceiling increase (until
   2026-07-08 21:53Z).

## The Moscow false lockout (engine's biggest single loss today, −$24.65)
UUWW (Vnukovo) 11:55Z SPECI read 23.0°C; the next hourly (12:00Z) read 22.0°C. Our
official running_max locked at 23.0 for the rest of the day; the market resolved
**22°C**. So the 22°C bucket was never actually locked — M1β fired NO@0.9352 ($19.64,
breakeven WR 94%) at depth=0.5°C, exactly the gate minimum, off ONE uncorroborated
ob; a resting lockout-family maker NO@0.06 ($5) filled as the market flipped. Third
false-lockout incident in this class. Key lesson: **{AWC,NWS}-only provenance is not
sufficient for non-US stations** — the SPECI is official, but the WU-displayed high
never showed it, and there is no 1-min ASOS cross-check abroad. Registered
`lockout_oracle_divergence` (experiments.jsonl, review 07-13): join LOCKOUT_SHADOW
candidates × Gamma resolution to quantify divergence by station/ob-type before any
lockout re-enable.

## Actions REJECTED / DEFERRED (with the failed gate)
- **Halt-wiring fix tonight** — REJECTED for the evening slot: `is_halted` gates only
  the disabled STWA taker path (maker/M1β/pair have no halt check and traded through
  a −47% day), but wiring it naively would false-halt on every ladder fire (cash→
  position conversion reads as loss). Needs the equity-proxy fix (capital +
  ladder-at-cost) first. Full spec in ESCALATIONS.md; morning-slot work.
- **Any optimization** (research-audit best-action SUM_POSTED join, isotonic work,
  PAIR_FAV_SUM_MAX tuning) — rail-breach day is for cutting, per charter/prompt.
- **Killing or tuning the ladder** — forbidden (principal-authorized, outside
  charter scope); supervision only. No gate-tuning trigger (no zero-candidate days;
  resolved n=6 < 10).

## Sprint ladder supervision (STEP 2b)
- 07-06: Singapore 31°C ($45 @ 0.44) LOST, Shanghai 34°C ($45 @ 0.44) LOST — both
  settled within hours, state arithmetic exact (sleeve $206.94 − 90 = $116.94 ✓).
- Lifetime: 8 fired, 6 resolved, 3W/3L, net +$56.94 on the $60 seed. p≈ask
  coin-flips per design — yesterday's "+$88 ahead of target" and tonight's "−$38
  behind" are the same variance, stated plainly.
- No re-seed needed (sleeve ≥ $5). Cron healthy.

## Experiments status
- pair_fav_sum090 → WOUND-DOWN-SHADOW; pair_clip_cofill continues as pure
  counterfactual (review 07-19); lockout_oracle_divergence REGISTERED (review 07-13);
  yes_capture/band_dial COLLECTING; PEAKSCALP/THERMO/thin-margin stay KILLED;
  nhc_count_lock still WATCHLIST (not designed — deferred again on a rail day).

## Standing risks
1. Equity $108.35 vs kernel floor $40; ladder can fire 2×$45/day from its own sleeve
   ($116.94) with a $20 free-USDC reserve check — modal ladder outcome remains
   sleeve-to-zero; engine flows now cannot compound losses on top of it.
2. Daily-loss halt still unwired on maker paths (spec in ESCALATIONS) — mitigated
   tonight by the wind-down itself (nothing left to halt).
3. 30d-HW rail seam (HW made of ladder variance) flagged to the WEEKLY for the
   amendment protocol — tonight it was executed as written, per kernel.
4. Isotonic/dispersion gauge still degenerate (window locked Jun28–Jul2) — blocks
   the band re-enable tree; unchanged.
