# Lockout-Edge Scope (2026-06-08)

> Built after the center→NO-PnL gate test (state-log 2026-06-08) concluded that
> favorite-longshot **forecast**-NO is structurally marginal at our ~0.8°C center
> accuracy, and the durable, calibration-free edge is **settlement-lock NO** (the
> running-max floor). This scopes growing the lockout edge; it does NOT chase more
> forecast accuracy. Authoritative behaviour: `strategy/weather_arb.py` (M1β).

## The edge, today
- **Settlement-lock NO**: once `official_running_max_c` passes a bucket's ceiling the
  bucket physically cannot resolve YES; buy NO while a stale YES bid persists.
- **Validated**: gated (asos margin ≥0.5°C + oracle-clean, ex-HK) WR ≈98.7% (Gamma-join
  n=671). Live impl = **M1β** (`M1_BETA_PROBE_*`): NO_ASK [0.70,0.97], stake $40, depth
  gate $5, fires on first detection (`MIN_SEC_SINCE=0`), TP recycle at 0.999, oracle
  blocklist {VHHH,RJTT,ZGSZ,WSSS}.
- **Capacity-capped ~$56/day** (clean fillable lockouts). Raw candidate supply is large
  (44 cities, ~15k snaps/day) — the binding constraint is *fillable clean* lockouts.
- **Broad weather-NO is −$361 all-time**: the bleed is forecast-NO, not lockout.

## WS0 — Stop the forecast-NO bleed  *(defensive; largely DONE 2026-06-08)*
- model_no_scorecard: engine model-NO bleeder is the **[0.50,0.70) band** (n=33 ≈−$24);
  only [0.70,0.85) is +EV (n=13 +$9.20 WR92%, and that band overlaps M1β → likely the
  lockout leaking through, not forecast skill).
- **Already deployed today**: `NO_FLOOR=0.70`/`NO_CEIL=0.88` (gates the [0.50,0.70)
  bleeder) + the stale-running_max fix (killed the −$27 false-lockout re-enable losses).
- **Remaining**: with the new `floored` tag (entry 613) accumulating, split realized
  [0.70,0.88] NO by floored(lockout) vs forecast. **Gate: n≥100.** Prior (structural
  test) says forecast-NO is marginal → expect to disable engine forecast-NO and rely on
  M1β lockout once the split confirms. Until then, no change (bleed is gated).

## WS1 — Maker-on-locked-certainty  *(highest upside; the structural lever)*
- ColdMath teardown: top on-chain traders harvest the deep-certainty band (no_ask
  0.97–1.0) with **maker** orders → rebates, not taker fees. M1β caps at 0.97 and pays
  taker fees, skipping exactly that band.
- The generic "maker MVP" was falsified by adverse selection (filled when wrong). **A
  physically *locked* bucket has no adverse selection** — it cannot resolve YES — so the
  winner's curse doesn't apply. This is the one place maker is clean.
- **Build**: shadow logger that, on confirmed-locked buckets, posts (shadow) NO bids just
  under the stale YES ask; measure fill-rate, time-to-fill, and rebate-vs-fee capture vs
  current taker fills. **Gate: shadow fill economics n≥100 + positive maker-PnL.**
- **Value**: unlocks the highest-volume certainty band AND flips fee→rebate; plausibly
  multiplies the $56/day cap. Needs CLOB maker-order capability (infra check first).

## WS2 — Capacity & timing within the clean slice
- Best NO price is in the first ~15 min of a lockout, then the book reprices toward $1
  (lockout_exec_backtest, entry 609). Levers:
  - **Earlier detection** via NMS feed-lead: receiving the resolving hourly METAR before
    AWC's batch → lock detected seconds–minutes earlier → fill before the reprice. Ties
    to the `obs_receipt` instrument (entry 615). **Gate: `feed_lead_measure` shows real
    median lead on resolution-grade (AWC+other) obs.** (Stage-0 found the sub-hourly feeds
    never lead the *resolution* value — the test is whether we get the *same* hourly METAR
    earlier.)
  - **Fill depth**: measure fillable-depth distribution on clean-locked buckets — is the
    $5 depth gate / $40 stake the binding cap, or is it candidate count?

## WS3 — Oracle-clean city expansion
- Wrong-oracle cities create false locks (Tokyo AMeDAS mis-map, HK/Shenzhen/Singapore);
  blocklist {VHHH,RJTT,ZGSZ,WSSS}. Audit all 51 cities' `official_running_max_c` source
  vs the Gamma/UMA resolution oracle; expand the *clean* set (more clean cities = more
  capacity), fix/borderline ones. **Gate: per-city Gamma-join WR n≥100.**

## Sequence
WS0 (done/instrumented) → **WS1** (highest upside; needs infra check + shadow build +
validation) → WS2/WS3 (incremental capacity). WS1 is the structural growth; the rest is
optimization of a validated-but-small edge.
