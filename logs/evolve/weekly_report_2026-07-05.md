# EVOLVE weekly report — 2026-07-05 (first weekly run; window 2026-06-28 → 2026-07-05 13:45Z)

## JOB 1 — SCOREBOARD (computed from resolution-joined data, not estimated)

**Headline, honestly:** equity roughly 2.5×'d this week ($85 measured 07-03 → $216.68
now), but **85% of the gain is 4 taker coin-flips (3 won) plus one lockout harvest —
variance and a capacity window, not compounding edge.** The engine's own realized week
is **+$8.41**. The week is AHEAD of the $10k/30d trajectory (+$88.6 vs the day-2.57
target) for reasons that do not extrapolate.

Realized / resolved this week:

| Flow | n | Staked | Realized | Note |
|---|---|---|---|---|
| trades.jsonl STWA_RESOLVED | 25 | $110.17 | **−$84.91** | tail of paths already cut (favNO n=16 −$54.08; one-sided pair YES n=5 −$21.50; misc NO n=3 −$9.33) |
| trades.jsonl BAND_MERGE | 6 | $23.01 | **+$3.21** | 3 completed pair merges |
| RECYCLE099 / exit099 sells | 44 | $221.28 basis | **+$90.11** | +40.7% on basis — the quiet velocity engine, every day positive |
| **Engine subtotal** | 75 | ~$354 | **+$8.41** | |
| SPRINT_LADDER (outside charter) | 4 shots | $159.81 | **+$148.70** | Shanghai +$63.50, Seattle +$53.26 (both redeemed), Tokyo +$58.01 (priced 1.000, redemption pending), Munich −$26.07 (lost) |
| M1β lockout-NO Moscow | 4–5 fills | $75.85 | **+$16.30** | priced 1.000, redemption pending — first lockout capacity in weeks |
| **WEEK TOTAL** | | | **≈ +$173.4** | $74.3 of it redemption-pending (resolved-final, not optimistic marks) |

**Equity curve** (cash-proxy before 07-03, ground-truth after): 06-28 $70.4 → 07-01
$67.6 → 07-02 $75.2 → 07-03 **$85 measured baseline** → 07-04 $147.13 → 07-05 13:45
**$216.68** = cash $10.69 + positions-at-mark $205.99 (of which $194.0 priced 1.000
pending redemption; ~$12.0 genuinely at risk in three d+1 pair legs).

**Velocity vs benchmark:** blended resolved flow ≈ $590 over 7.5d on ~$120 avg equity
→ ~0.65 turns/day at +29%/turn blended; **ex-ladder +5.7%/turn**, and engine posting
TODAY is collapsed (0.053 posts/cycle, exec audit). The badatmath benchmark itself is
void: he ran **−$11.3k in 7d** in the same maker structure (07-03 sweep) — the
structure we are benchmarked against is bleeding for its originator.

**Trajectory verdict:** on-trajectory on paper (+$88.6 ahead of day-2.57 target
$128.04), NOT on-trajectory in mechanism. Sustained ladder P(win) ≈ ask by design
(~0.43–0.47/shot; P(3+ of 4) ≈ 27% — lucky, not skilled). The compounding levers the
charter names (edge/turn × turns/day × breadth) are all near zero on the engine side.
Binding constraint: **no live path with proven positive edge/turn has capacity**
(NEG_RISK_ARB Σ=1.000 10d; lockout capacity episodic — one window today in weeks;
pair_fav starved by market pair-sums > 0.90).

## JOB 2 — STRATEGY REVIEW (verdicts executed)

| Path | 7d resolved n | Realized | Verdict |
|---|---|---|---|
| STRUCT_BAND standalone YES | 0 new (OFF since 07-03) | — | **KEEP OFF.** Re-enable trigger (disp_ratio ≥1.10 ×5d) unmet and unmeasurable — gauge degenerate 3d (isotonic refit = queued sensor fix) |
| favNO overlay | 16 (pre-halt tail) | −$54.08 (−69%) | **KEEP HALTED** — the 07-02 rail cut is confirmed by its own resolving tail |
| PAIR_FAV | 9/side + this week's tape | merges +$3.21; one-sided YES deaths −$21.50 | **KEEP at current size, instrument** — root mechanism found (see JOB 3); no param change without gate; n<20 so no rail action available |
| RECYCLE099 | 44 exits | +$90.11 | **KEEP** — core velocity engine |
| NEG_RISK_ARB | 0 windows (10d, Σ=1.000) | $0 | **KEEP** — free option, calibration-independent |
| THERMO | killed 07-04 (n=125, EV≈0) | — | stays KILLED |
| M1β lockout-NO | Moscow window today | +$16.30 pending | **KEEP ARMED** — validated slice (98.7% WR n=671) harvested its first capacity in weeks; per-fire caps ($10/$20) held; flag: $75.85 accumulated on ONE city-day ≈ 35% of equity — lockout physics justifies it, but daily runs should watch fires_today accumulation |
| SPRINT_LADDER (outside charter) | 4 shots, 3W/1L | +$148.70 | monitor-only per mandate; sleeve $105.69; gates honored ($20 reserve skip observed 08:10, fired only post-redemption); Tokyo settle must reconcile to data-api 101.9 sh (state says 101.25) |

**Capital rebalance:** none today — free cash is $10.69 until tonight's redemptions
(~$194); MAKER_CASH_FRAC=0.40 anti-thrash freeze expires 07-06 20:05Z. Decision left
to the 07-06 daily with post-redemption cash in hand.

**Rail states:** kernel floor clear on tracked capital ($216.68 ≫ $40); engine's
cash-proxy comparator touched $39.69 < $40 intraday (conversion, not loss — see
ESCALATIONS sensor-seam note). Wind-down rail state (equity < 50% of 30d HW): **now
CLEAR** — $216.68 vs ~$250 proxy HW = 87% (and today is the new honest measured HW).
Daily-loss halt: DAILY_RESET fired 00:00Z as designed (base $87.17); realized day is
positive; no halt.

## JOB 3 — NEW EXPERIMENT (pre-registered): `pair_clip_cofill`

**Largest MEASURED gap:** the only live posting path (PAIR_FAV) is structurally
self-sabotaging when the market's natural pair-sum exceeds the cap. The code clips the
NO quote to enforce qy+qn ≤ 0.90 (`weather_arb.py` pair branch) — and **42 of 43 pairs
posted 07-03→07-05 were pinned at exactly 0.90**, i.e. the NO leg almost always rests
below its touch. Consequence measured this week: one-sided (YES-only) pair fills
resolved **n=5, −$21.50, −100% of stake** vs +$3.21 from the 3 pairs that did merge.
The clip converts "locked merge" into "naked directional YES at 0.42–0.59" — the exact
winner's-curse slice that killed the standalone band.

- **Hypothesis:** pairs posted with NO clipped >1¢ behind its touch have negative net
  EV; pairs at natural sum ≤0.91 are the only +EV slice.
- **Mechanism:** clip depth ⟶ P(NO co-fill) ⟶ naked-YES exposure.
- **Metric:** per-pair realized net $ by clip depth (nb − qn at post), split
  co-filled / one-sided / no-fill; joined via order_lifecycle + trades.jsonl/exit099.
- **n-gate:** ≥40 resolved pair posts for trend; ≥100 for any live change.
- **Kill criteria:** co-fill rate at clip>1¢ ≥40% AND net EV ≥0 at n≥40 → clip is
  harmless, keep config, kill experiment.
- **Review:** 2026-07-19.
- **Graveyard check:** not a corpse — measures the loss side (naked legs) of a live
  path; distinct from the falsified merge-spine (06-20), which was about
  selection-biased merge ROI.
- **Implementation (shadow-only, deployed tonight):** pair posts now log ya/na/yb/nb
  touches; candidates clipped to nothing log `reason=pair_clip_skip`. Zero live
  behavior change.

## JOB 4 — LOOP HEALTH & SELF-EVOLUTION

- **Actuator schedule: 2 completed / 9 attempted since 07-02.** 07-02 tamper-wedge
  (fixed 07-03), then session limits killed 07-03 (×3), 07-04 11:23, 07-05 11:23. Only
  07-04 21:53 and this weekly ran. Systemd units are kernel-protected — the loop
  cannot re-stagger itself. **Prompt-level mitigation shipped:** daily_prompt.md
  STEP 0 backlog check (a completing run now covers all failed slots' review_dates and
  reports). Interactive session still needed for timer re-stagger / cheaper fallback
  model (ESCALATIONS).
- Liveness watchdog: 6 restarts, all legitimate (07-03 DNS outage ×5, 07-04 deploy
  race ×1 — benign, noted).
- Analyst reports: all 4 arrived fresh today 11:25; pnl_ledger on its 23:37 cadence.
- Thrash check: none (M1β revert was of a 26-day-old param; 07-03 changes stand).
- Amendments: **none proposed** — this week's failures were kernel-protected infra
  (timers) and sensor seams, not charter defects; no pending second readings.
- ESCALATIONS processed: auto_kill item RESOLVED (retire-in-place, rationale logged);
  schedule-reliability and sensor-seam entries appended.

## NEXT WEEK'S SINGLE BIGGEST LEVER

**Make the ruin floor measure what the kernel means, then ratchet it.** Kernel #2 is
defined on *tracked capital*; the engine comparator (risk/manager.py:242) reads the
bankroll cash-proxy, so normal cash→position cycling reads as ruin-proximity (today:
$39.69 "capital" vs $217 true equity). Spec for the daily (one live-effect change,
Tier-1 tighten): comparator = cash + open-position cost basis; then ratchet
ruin_floor $40 → 0.40 × trailing-30d measured HW (≈$86 on today's $216.68) per the
charter formula. Sequencing matters: ratcheting first would false-halt on every ladder
fire. Secondary: isotonic refit cron diagnosis (research audit's #1; restores the
dispersion gauge and with it the band re-enable decision tree).

*Weekly agent, 2026-07-05. Everything in this report was computed from
trades.jsonl, exit099_live.jsonl, sprint_ladder_state.json, data-api positions, and
the analyst reports — no estimates.*
