# EVOLVE daily report — 2026-07-09 (evening slot 21:53Z; morning slot died on weekly session limit — full-day backlog covered)

## Health & equity (first paragraph, per honesty rules)
`klaus` ACTIVE, fresh `[WA]` cycles at 21:53Z. **Equity $158.63 all-cash**
(CLOB-actual; 0 engine positions, 0 open ladder shots) = **71.2% of 30d-HW $222.90**
— equity rail CLEARED (first non-breached slot since 07-07); tracked > ruin_floor
$89.16, engine no-new-entries dis-armed. Daily realized **+$74.70 (+89%)** on
daily_start $83.93 — ALL sprint ladder (Chicago 88-89°F +$19.91, Tokyo 30°C +≈$76
via the FIRST live 0.99-early-exit, Guangzhou 33°C −$14.06, Tel Aviv 30°C −$5.30).
**7d realized −$79.36 PF 0.116 (n=32)** — entirely from paths already cut
07-02/07-06 (band remnants −$56.27, Moscow M1β −$24.65); post-wind-down engine
flow ≈ $0 — the bleed remains stopped. The recovery is ladder coin-flips, not
compounding edge; stated plainly. −14% freeze active until **07-10 21:53Z**.

## Actions taken (0 live-effect changes; 2/2 cap unspent)
1. **STEP 2 measurement shipped**: `band_resolution_join.py` (n=654 DECISION-READY)
   + NEW `analysis/weather/band_sum_posted_slice.py` (read-only analysis) →
   `logs/evolve/gate_ledger_latest.md` refreshed. This executes the analysts' PA-1
   ask a slot early (it was scheduled for the 07-10 morning slot, which may die on
   session limits again — tomorrow evening's decision now has its inputs in hand).
2. **G7 SUM_POSTED [0.70,0.85] ANSWERED**: n=382, ROI +11.5%, Wilson
   [−11.4%, +38.9%] → **AMBIGUOUS, NOT READY** (n cleared, CI straddles zero).
   5-reports-running gatekeeper advisory closed.
3. **Isotonic PA-1 CLOSED — no defect**: the live-refit cron is NOT dead (prior
   ledger claim wrong; it runs daily 09:30, log fresh today). The guard held
   legitimately (cal_days 11<14; OOS cal Brier not improved). The fresh candidate
   fit ON JULY DATA is still flat (g≈0.376 for p∈[0.35,0.85]) ⇒ the mid-range
   plateau is **structural, not staleness** (research-audit Experiment 3's
   decision-if-no branch). Auto-promotes ~07-12 iff OOS improves. No code change.
4. **Bookkeeping**: 6 overdue ledger review-dates closed with evidence (4 were
   KEEP-verified on 07-05 but never annotated; 07-06 freeze SUPERSEDED; the 07-07
   ladder fill-cost fix closed KEEP — all 6 subsequent fires carry fill_px, sleeve
   arithmetic reconciles exactly). `experiments.jsonl` pair_clip_cofill updated
   with tonight's join evidence.

## Actions REJECTED / DEFERRED (the list that matters)
- **MIN_LOCKOUT_LIVE=True re-enable** — pre-registered rail-clear condition IS met
  (equity 71% of HW) and the 197/197 margin≥1.0 evidence stands, BUT the flag was
  changed 07-08 21:53Z: **72h anti-thrash freeze** (and the −14% freeze) block it.
  Deferred to its 07-11 ledger review. Expected cost ≈ $0: it posted 0 orders in
  its 7h live window (min-side executable capacity ≈ 0).
- **BAND_LIVE re-enable** — the analysts' PA-2 OR-condition fails on BOTH branches
  (G7 AMBIGUOUS; disp recovery not confirmed — per-day 07-03..09 ROI oscillates
  around zero with huge CIs). More fundamentally, the BINDING pre-registered
  condition (post-guard pair n≥40 positive trend) has **post-guard resolved = 0**
  and cannot accrue while the band is dark. A daily slot does not swap in a weaker
  condition after the fact. → **weekly 07-12 structural decision**: wire a band
  shadow-posting mode (counterfactual accrual, no capital) or amend the condition
  through the normal gate. ALL-pair economics stay promising: +13.0%/$ (n=30<40).
- **Ladder gate tuning** — not triggered: 3/3 fires today (no zero-candidate days);
  WR 42.9% vs avg fill 0.434 at n=14 = at-ask, no systematic worse-than-ask
  selection. Negative-model-edge subgroup 0W/2L is n=2, watch only (rule needs n≥10).

## Sprint-30 / ladder supervision (STEP 2b)
Cron healthy (10-min cadence, benign api-key 400 noise). Settlement integrity: all
FIRED→settled <36h; sleeve **$172.82** reconciles EXACTLY against events. Lifetime:
**14 resolved, 6W/8L, net ≈ +$110** (redemption-basis; supersedes the mis-added
≈+$14 for 10 shots in the 07-08 ledger — that set nets ≈ +$35). First live
0.99-early-exit worked (Tokyo sold ~0.99 intraday, capital recycled same day) —
validates the 07-08 velocity upgrade ahead of its 07-12 review. Sleeve $172.82 >
$5: no re-seed. Sprint day ~7: equity $158.63 vs target ≈$256 → **gap ≈ −$98**.

## Experiments status
- pair_clip_cofill: ACCRUAL-FROZEN (structural; weekly 07-12 decision) — evidence
  note appended tonight.
- Isotonic freshness (research-audit Exp 3): ANSWERED — structural flatness.
- Lockout divergence family, temporal P5, count-lock, minmax: closed 07-08,
  unchanged.
- Band dial series: 29 resolved days (gate n≥90 OOS) — collecting, do not interpret.

## Standing risks
1. The recovery is variance (ladder coin-flips at ~0.43 avg fill), not edge; the
   engine currently deploys ≈$0 into any +EV-proven path. Compounding remains
   blocked on the weekly's band-accrual decision and the 07-11 MIN_LOCKOUT review.
2. Weekly Claude session limits keep killing morning slots (3 of the last 4);
   tonight's run front-loaded tomorrow's decision inputs so a dead 07-10 morning
   slot costs nothing.
3. p_cal has ~no mid-range discrimination (structural) — any future gate leaning
   on it in p∈[0.35,0.85] inherits that.
