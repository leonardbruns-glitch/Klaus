# EVOLVE Daily Report — 2026-07-11 (evening slot 21:53Z; morning slot died on session limit — this run covered the full day)

## Health & Equity
- `klaus` **active**; restarted 22:06:14Z for the MIN_LOCKOUT deploy; fresh `[WA]`
  cycle lines verified 22:09–22:12Z. Ladder cron firing on schedule (last events
  16:21Z fire, 17:00Z settle).
- **Equity $205.76** = cash **$143.34** (CLOB-actual, engine balance line 21:57Z)
  + 2 open ladder shots at TRUE cost $62.42 (London $40.03 resolves ~00:30Z,
  Mexico City $22.39 ~06:30Z). 92.3% of 30d-HW $222.90 — **rails CLEAR, third
  consecutive slot** (50% line $111.45, ruin floor $89.16, no ratchet: below HW).
- Daily realized **+$42.33** (ladder Guangzhou: cost $24.03 → 0.99-exit $65.86 +
  $0.50 residual redeem). Engine realized 7d: **$0** — every engine path was dark
  (wind-down); the pre-cut June band tail (−$71.52 PF 0.108) has rolled out of
  the 7d window. bankroll.json tracked-capital comparator verified exact.

## Actions taken (live-effect cap: 1 of 2 used)
1. **MIN_LOCKOUT_LIVE False→True** (commit c704ff1ed, live change 1/2) —
   pre-registered 07-08 review-date decision executed on its due date: "flip on
   rail clear alone — evidence gate already satisfied" (197/197 min-lockouts
   margin≥1.0, lockout_divergence_0708). $5 maker stake, breaker + oracle
   blocklist inherited. Prior live window posted 0 orders — this is optionality,
   not a PnL projection. Review 07-14; kill = any live loss at margin≥1.0
   (provenance breach) or rail re-breach.
2. **Bookkeeping (uncapped): sprint_ladder fill-cost rebuilt on wallet truth**
   (commit bc0f8c17c) — third partial-fill mis-record caught (London 07-11:
   wallet paid $40.03 / 83.75 sh across 3 partials; response said $31.75 /
   68.26 sh → sleeve overstated $8.28 and 15.49 winning-candidate shares were
   invisible to the 0.99 exit). fire() now books the USDC balance delta after an
   8s stabilization and re-polls matched size. State reconciled against data-api
   (sleeve 169.39 → 160.50, London + MexCity corrected).
3. **Winner's-curse cross-tab run and RESOLVED in direction** (analysis-only;
   the item exec-audit flagged 5 days running and research-audit named "best
   action today"): realized maker fills 06-11..07-06 **n=75: WR 17.3%, ROI
   −75.8%** vs same-era simulated join **+7.6%** (n=3,418) — a ~80pp gap
   conditional on fill, same sign in every price×horizon cell (NO d+1 0.60–0.85:
   filled 20% vs sim 92.9% at the same quote). No survivorship bias (all exits
   0/1). Full note: `logs/evolve/winners_curse_crosstab_0711.md`.

## Actions REJECTED (with the failed gate)
- **BAND_LIVE re-enable** — S3 dispersion trigger unmet (disp_ratio ≥1.10 on
  1/13 confirmed days; median-city ≤0.80 all Jul days) AND tonight's cross-tab:
  sim join ROI no longer qualifies as enabling evidence on its own.
- **Micro-stake PAIR_FAV re-enable tonight** — belongs to the Jul 12 structural
  slot (pre-registered review date of the 07-05 clip-guard; front-running it
  tonight would be an ungated jump). Tonight's contribution: the decision should
  weight **co-fill rate under the clip-guard**, not CF ROI (+52.9% n=32 is
  fire-based and inherits the sim bias). Combined pair lock ≈ +13.0%/pair
  (n=29) remains the honest number *conditional on co-fill*.
- **Isotonic manual promote** — calib-monitor says plateau is structural; auto
  path stays; do nothing (research-audit concurs).
- **G7 / G1-based changes** — both AMBIGUOUS (CI straddles zero), and now
  curse-discounted.

## Sprint ladder supervision (STEP 2b)
- Cron healthy; 3/3 fires used (Guangzhou WON via 0.99 exit +$42.33 realized;
  London + Mexico City open). All pre-07-11 shots settled <36h. Sleeve
  arithmetic reconciles exactly vs data-api after tonight's correction:
  **$160.50** + $62.42 open at cost. Lifetime: 8W/12L settled, net ≈ +$119
  redemption-basis.
- Sprint gap (07-10 23:50Z equity cron): equity $163.16 vs target $303.44, gap
  **−$140.28** (day 8). Tonight's tracked $205.76 narrows it if the open shots
  land; day-9 target ≈ $333.
- Noise flag: `sprint_ladder_cron.log` shows recurring benign
  `auth/api-key 400 "Could not create api key"` lines (key-create falls back to
  derive; fires and 0.99 exits execute fine). Cosmetic; not touched tonight.

## Experiments
- `pair_clip_cofill` — ACCRUAL-FROZEN, n=29 stable, +13.0%/pair combined; Jul 12
  decides micro-stake re-enable; kill condition proposed: one-sided fill share
  >30% over first 20 pairs → off.
- `band_reenable_trigger` — standing condition unmet; addendum recorded (sim ROI
  alone no longer sufficient even if S3 fires).
- `nhc_count_lock`, `temporal_lock_p5` — KILLED (07-08), no change.
- `sprint_ladder` — owner-mandated, supervision above.

## Standing risks
1. Two open ladder shots ($62.42 at cost) resolve overnight; a double loss puts
   equity ≈ $143 (still >50% rail and >floor — no rail consequence).
2. The Jul 12 structural review is tomorrow's weekly slot; everything it needs
   (cross-tab, gate ledger, S3 status, pair co-fill framing) is committed.
3. exec_audit_report.md was committed **base64-encoded** this morning (cloud
   analyst glitch) — readable after decode, will be overwritten by tomorrow's
   07:07Z run; flag for the analysts if it recurs.
4. Maker rebate $3.17 receipt still unverifiable from this box (5+ days stale;
   needs a human/interactive check against the Polymarket account) — carried.
