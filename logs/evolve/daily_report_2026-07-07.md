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
