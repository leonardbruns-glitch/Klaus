# EVOLVE daily report — 2026-07-07 (11:23 UTC morning slot)

## Health & equity (first, honestly)
- `klaus` **active**; restarted 11:36Z for the rail deploy, verified fresh `[WA]` cycles
  + MIN_LOCKOUT 0 posts (wind-down holding). No crashloop flag. Backlog: none — the
  07-06 21:53 run completed rc=0 and covered its day.
- **Equity $108.35** = cash $42.02 + 2 open sprint-ladder shots at actual cost $66.33
  (Tokyo 26°C 56sh@0.37 $21.37 partial fill; Singapore 32°C 94.75sh@0.462 $44.96).
  Cash cross-check exact vs data-api fills.
- **WIND-DOWN PERSISTS**: equity = 48.6% of 30d-HW $222.90, below the 50% rail.
  Breached-rail day → no optimization; steps 3–4 skipped by design.
- **7d realized −$128.38, PF 0.085 (n=45)** — a losing week, stated plainly. Attribution:
  band YES/maker ≈ −$105 and M1β Moscow −$24.65 — **all from paths already cut**
  (07-02 favNO, 07-03 band pause, 07-06 full wind-down). Realized flow since wind-down: $0.
- Daily-loss rail status: the morning's apparent 61% daily loss was a **false trip**
  (cash-proxy reading ladder fires as losses) — fixed today, see actions. True realized
  today ≈ $0. The 07-06 −14% breach still bars size/ceiling increases until 07-08 21:53Z
  (nothing raised; ruin-floor ratchet is a tighten).

## Actions taken (2/2 live-effect, both rail/bookkeeping — zero new risk)
1. **Tracked-capital comparator + ruin-floor ratchet** (commit `1e41ca7fa`, deployed+verified):
   bankroll syncs now count open ladder shots at cost (`main._ladder_open_cost()`);
   pre-fix capital read $42.02 vs true $108.35 and the daily halt was falsely tripped.
   Then `ruin_floor` 40.0 → **89.16** = 0.40 × HW $222.90 per INVARIANTS #2 ratchet
   (raise-only). Verified post-restart: `BANKROLL SYNC 42.02 → 108.35`, halt clear.
2. **Sprint-ladder fill-cost recording + reconcile** (STEP 2b): fire path records actual
   cost (was: intended stake — 2nd partial-fill mis-record in 4 days). State reconciled
   vs data-api under flock: sleeve 26.94 → **$50.61**, Tokyo stake 45→21.37,
   Singapore 45→44.96. Cron health verified via syslog (fires every 10 min; post-cap
   log silence is by-design).

## Actions REJECTED / deferred (with the failed gate)
- **Any band/lockout re-enable** — wind-down rail + disp_ratio 0.817 locked (<1.10
  trigger) + gauge stale (isotonic plateau). Both conditions of the 07-06 re-enable
  spec unmet.
- **Wiring is_halted/is_ruined into maker paths** — unblocked by today's comparator fix
  but deliberately deferred: breached-rail day, 2-change cap spent, and every maker path
  is already off. Next available slot candidate.
- **PnL-ledger "DATA MIRROR DEAD" alarm** — **FALSE, resolved against primary data**:
  `klaus_data_mirror` pushed 111 snapshots on Jul 6 with zero gaps, current as of
  11:20Z today. Cloud-side fetch error (report's own timestamp internally impossible).
  No VPS action; flagged in gate ledger for the analysts.
- **Ladder gate tuning / re-seed** — no trigger: fired 2/2 every day (no zero-candidate
  streak), sleeve $50.61 > $5.

## Measurements (VPS ground truth, committed in gate_ledger_latest.md)
- `band_resolution_join` n=530 resolved (window-relative): band YES −8.1%
  [−28.3, +16.9] — cut re-confirmed; NO d+1 +6.6% n=62 CI straddles 0 (COLLECTING);
  co-filled PAIR net ≈ +13%/pair-share, post-guard count n=9/side (frozen by wind-down).
- YES-CAPTURE markout: 225 would-be fills, med −1.9¢, 95% adverse — winner's curse
  confirmed again; informational only.
- Band dial: 27 resolved days (<30) — noise, seeding only.
- Calib monitor: disp_ratio 0.817 locked Jun28–Jul2 window (plateau); Jul 3 partial
  0.521°C = continued compression. Re-enable trigger not met.

## Experiments status
- Due today: none (lockout_oracle_divergence review 07-13; pair_clip_cofill 07-19).
- Accruing: pair counterfactual (shadow quotes + pair_clip_skip), lockout shadow
  (3 candidates/cycle logged), MIN_LOCKOUT shadow, PEAKSCALP shadow, band dial series.

## Sprint-30 (day 4)
Equity $108.35 vs day-4 target $160.51 → **−$52.16 behind** (tracker 07-06 23:50Z).
Ladder lifetime: 8 fired, 6 resolved 3W/3L net +$56.94, 2 open (resolve ~15–16Z today;
evening slot verifies settlement ≤36h). The −$114 swing from day 2.6 (+$80 ahead) to
now is ladder variance plus the paths cut in wind-down — variance, not edge, per the
kernel honesty rule.

## Standing risks
1. Both open ladder shots are p≈0.4 coin-flips; if both lose, capital $42.02 < new
   floor $89.16 → engine no-new-entries trips (intended protective behaviour; ladder
   reserve $20 unaffected, mechanical flows RECYCLE099/redemption continue).
2. Dispersion gauge blind (isotonic plateau) — band re-enable tree blocked on
   calibration infra, not on capital.
3. Actuator morning slots keep dying on Claude session limits (07-05, 07-06) —
   ESCALATIONS item for an interactive session stands.
4. Moscow-class false lockouts: divergence study due 07-13 before any lockout re-enable.

---

# Evening slot (21:53 UTC) — verification run

## Health & equity
- `klaus` **active**, fresh `[WA]` cycles at 21:58Z, wind-down holding (MIN_LOCKOUT 29
  candidates / 0 posts, lockout shadow logging, band queue silent). No backlog — the
  morning slot completed rc=0 and this is the same calendar day.
- **Equity $136.77, all cash** (zero open ladder shots, zero engine positions at cost;
  bankroll capital = CLOB actual balance exactly). Daily realized **+$28.41** on
  daily_start $108.35: ladder Tokyo 26°C LOST −$21.37, Singapore 32°C WON +$49.79 net;
  engine flow $0.
- **Wind-down equity rail CLEARED intra-day**: $136.77 = 61.4% of 30d-HW $222.90
  (> 50% line $111.45). **Re-enable withheld** — see rejected actions.
- 7d realized **−$118.43 PF 0.088 (n=42)**, all from paths already cut; flow since
  wind-down = −$4.22 (two legacy pre-cut YES dust legs resolving 07-06 22:49Z).

## Actions taken (0 live-effect; cap was already spent 2/2 by the morning slot)
- Re-ran `band_resolution_join`: **n=591 resolved** (+61 since morning), gate ledger
  refreshed and committed with Wilson CIs. No slice gate-passes: every CI straddles
  zero except PAIR_FAV NO legs (+52.9% [+12.6, +85.5]) which is n=32 < 40 and
  fill-conditioned — stays COLLECTING.
- Verified all four morning deploys against live behaviour: ruin_floor 89.16 in
  config.py; comparator (capital 136.766 = cash + $0 ladder, exact); daily reset
  (last_utc_day=20641, daily_start reset at midnight); ladder fill-cost recording
  (settle arithmetic exact: sleeve 50.61+94.75=145.36, cash 42.02+94.75=136.77).

## Actions REJECTED (with the failed gate)
- **BAND_LIVE / lockout re-enable despite equity rail clearing** — the 07-06 re-enable
  condition is equity ≥50%·HW **AND** post-guard pair n≥40 positive trend; post-guard
  count is n≈9/side (accrual frozen by wind-down itself — counterfactual shadow
  continues). Also: disp_ratio 0.817 < 1.10 trigger, −14% freeze active until
  07-08 21:53Z, and the 2-live-change cap is spent. Single-day equity recovery driven
  by one ladder coin-flip is not evidence of edge; charter prefers no change.
- **Anything sized-up** — freeze until 07-08 21:53Z.

## Sprint-30 ladder (STEP 2b, day 4.99)
- Cron healthy (syslog: fires every 10 min through 21:50Z). Both shots settled ≤36h
  (same day: 15:30Z, 16:40Z). Sleeve **$145.36**, fired 2/2 today (cap).
- Lifetime: **8 fired, 8 resolved, 4W/4L, net +$85.36**. Gap to day-4 target $160.51:
  **≈ −$45** (tracker restates at 23:50Z).
- No gate tuning triggered (fired every day — no zero-candidate streak; no n≥10
  systematic gate-vs-outcome pattern yet at n=8). No re-seed needed (sleeve ≫ $5).
- Bookkeeping note: sleeve $145.36 > free cash $136.77 (engine side net-negative in
  shared wallet) — next fire bounded by live balance − $20 reserve, so no
  over-commitment risk; flagged for the analysts in the gate ledger.

## Experiments
- None due today (yes_capture 07-11, lockout_oracle_divergence 07-13, pair_clip_cofill
  07-19, M1β thin-margin 07-18). All shadow loggers verified accruing.
