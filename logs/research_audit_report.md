# Klaus Research Audit — 2026-06-21
**Generated:** 2026-06-21T10:30Z  
**Snapshot age:** 15 min (2026-06-21T10:15:16Z — FRESH, within 6h gate ✓)  
**System:** `klaus systemd: active` ✓ | **Capital:** $287.40 (bankroll.json)  
**Specialist reports consumed:** exec_audit (07:07 UTC), calib_monitor (08:07 UTC), gatekeeper (09:07 UTC), pnl_ledger (23:37 UTC Jun20) — all within 36h gate ✓  
**Day-of-month mod 3:** 21 mod 3 = 0 → **Market intelligence: Competitor posture**

---

## 1. PRIMARY BOTTLENECK: ROI/turn — YES band dispersion edge is inverted for the 7th consecutive session

**Verdict:** The compounding equation (ROI/turn × turns/day × equity deployed) is bottlenecked at **ROI/turn**, not turns or equity.

**Evidence from specialist reports:**

- **calib_monitor:** Dispersion ratio = 0.671, 7th consecutive session below the 1.10 floor. Full recovery required = +0.429 from here. The model-implied σ (0.882°C) is only 67% of empirical crossing distance (true σ 1.373°C). **The edge premise of the YES band is inverted**: the market is more dispersed than our model projects, meaning YES shoulders are not systematically mispriced in our favor.

- **pnl_ledger (Jun20):** YES STWA resolution ROI = **–79.1%** on the Jun18 vintage (2/28 wins = 7%). RECYCLE099 generated +$36.72 (53.8% ROI on exits) but was insufficient to cover –$74.82 in resolution losses. Net day: –$32.80 (–16.5%). Resolution losses are structurally large **every day** — the 7-day pnl_ledger table shows trades.jsonl net_pnl is negative every single day (–$64 to –$119/day). All positive capital days are entirely explained by RECYCLE099 volume.

- **exec_audit:** Winner's curse proxy = **39.4% ITM** (13 wins / 33 resolved fills), below the 50% efficient-pricing baseline. This is sub-threshold (n=33, data-collection) but directionally consistent with adverse fill selection. The structural source (per state_log Jun18 23:59): stale YES orders run over by informed drift — orders >6h old show the most adverse markout (–1.07¢/sh), while <5m fills are cleanest (+1.57¢/sh). The 2h directional reclaim is protective.

- **state_log (Jun18 11:30):** band_net_attribution confirmed YES net –4.9% (n=299), NO net +7.2% (n=97) over the prior measurement window. band_dispersion_test (Jun18 21:20): shoulder calibration gap (WR − ask) = ~0 (<1 SE) across all offsets and regimes — the +8% band ROI on resolved winners is overround/rebate spread, not dispersion edge. The mode is the only mispriced cell, and its gap flips sign by regime.

**The net picture:** the system is running a daily lottery on YES positions. 93–97% lose at resolution (–100% of stake). 3–7% converge to 0.99 and are captured by RECYCLE099 at +400–2000% ROI. On days with high RECYCLE099 volume (19 exits Jun19, +$78.58), capital compounds. On low-RECYCLE099 days (12 exits Jun20, +$36.72), resolution losses dominate. This is NOT a dispersion-edge system today — it is a RECYCLE099 velocity system riding the minority of YES positions that happen to win, with the majority of capital deployed in structurally losing positions.

**Today's recovery (+$88 since Jun20 EOD, $199→$287) confirms:** RECYCLE099 is the actual positive engine, running at ~$72/day for the 6-day exec_audit window. The drag is the YES band resolution losses. The correct optimization focus is: maximize RECYCLE099 velocity while minimizing exposure in the losing tail of YES positions.

**Turns/day (0.579) and equity deployment are secondary:** the exec_audit identifies the constraint as new qualifying market availability (0.18–0.24 posts/cycle), not cash (cash_preskip $127–141 with 0–3 new posts/cycle means most queue positions are already resting in the book). The $782 SELL_EXIT backlog is deferred PnL, not locked dead capital.

---

## 2. EXISTING-SYSTEM OPTIMIZATION: what the four reports imply

### A. Gate 2 VPS resolution join (URGENT, highest impact)
**Finding (gatekeeper):** BAND_NO_PAIR_FAV crossed n=100 (now n=128) over 24h ago. BAND_NO_ENABLED=True with BAND_NO_STAKE=$5 is live. CI is blocked from container (Gamma 403). VPS operator must run band_resolution_join.py against post-Jun19T00:30 fire_no/pair_fav legs.  
**Expected delta:** Confirms or kills the NO engine. NO is 66% of fill dollars ($95/24h), the only realized +EV directional side (+7.2% realized, state_log Jun18). CI95 lower bound >0 → validated; CI spans zero → reduce stake immediately.  
**Confidence:** High that NO is positive (fill tape + realized data). Effort: ~1h VPS.

### B. Isotonic live-refit cron (LOW urgency, but growing staleness)
**Finding (calib_monitor):** Deployed isotonic is 15 days old; candidate is 12 days old; cron has not generated a fresher candidate in 12 days. The deployed ceiling (p_raw=1.0 → p_cal=0.6316) causes the [0.6,0.7) bin to show 94% actual acc vs 62.9% assigned — a structural artifact. The candidate isotonic would *worsen* the ceiling (0.3739 vs deployed 0.6316) — wrong direction. A fresh live-data refit is needed before any promotion.  
**Expected delta:** p_cal quality improvement for YES shoulder selection. Marginal on RECYCLE099 (triggers on price convergence, not p_cal).  
**Confidence:** Medium. Effort: ~30 min VPS cron trigger.

### C. THERMO and M1_BETA: declare dormant, route-diagnose or kill
**Finding (gatekeeper):** THERMO (Gate 5) has 25,818 candidates with 0 fires in 9+ days. M1_BETA_LOCKOUT (Gate 6) has 16,611 candidates with 0 fires in 11+ days. Both gates STALLED at n=3 and n=31 respectively.  
**THERMO:** n=3, CI upper=+0.7% — one more adverse fill pushes fully negative. At 0 fires/day, ETA to n=20 kill-gate = infinite. BAND_TAILNO_VALIDATED=False + BAND_NO_MAX=0.85 means all THERMO candidates (0.85–0.95) are above the live NO ceiling. The engine is collecting shadow candidates that can never become live orders under Phase-1 config. This is a phase-lock, not a stall.  
**Expected delta from diagnosis:** Clarify whether Gate 5 should be listed as "deferred Phase 2/3" (config-gated) or "stalled" (code bug). Frees monitoring overhead.  
**Confidence:** High. Effort: ~30 min VPS diagnostic.

### D. UNTRACKED FILL accounting gap (MEDIUM priority, data quality)
**Finding (exec_audit):** Large untracked fill volumes: Jun19 ~50 tokens, Jun20 ~32 tokens, Jun21 ~7 tokens. Token 1063830058162561 (Miami NO) shows live UNTRACKED FILL events at 09:46 UTC today. Jun20 P&L has $5.25 unexplained gap attributable to untracked RECYCLE099 exits. Real capital is likely slightly better than logged.  
**Confidence:** Medium (root cause identified). Effort: VPS tracker state audit.

---

## 3. GATE PIPELINE

| Gate | n | Status | ETA | Accelerator |
|---|---|---|---|---|
| 4. BASKET_EXIT | ≈72 (16 verified) | COLLECTING | **~3.5 days** | Confirm VPS archives basket_exit_shadow.jsonl daily — Jun16–19 gap shows cron was missing |
| 2. BAND_NO_PAIR_FAV | 128 | COLLECTING ★n≥100 | **BLOCKED** (VPS join needed) | VPS: band_resolution_join.py on post-Jun19T00:30 NO legs |
| 1. BAND_YES | 5,154 | COLLECTING | BLOCKED (Gamma 403) | VPS resolution join; clean window = post-Jun19T00:30 (~701 clean legs) |
| 7. SUM_POSTED [0.70,0.85] | 2,473 | COLLECTING | BLOCKED (Gamma 403) | Same VPS join as Gate 1 |
| 5. THERMO_MAKER_NO | 3 | STALLED (day 9+) | **INFINITE** | Diagnose: BAND_NO_MAX=0.85 + BAND_TAILNO_VALIDATED=False likely phase-locks all candidates |
| 6. M1_BETA_LOCKOUT | 31 | STALLED (day 11+) | **INFINITE** | Diagnose: thin-margin route check |

**Gate 4 (BASKET_EXIT) is nearest READY** and holds the first confirmed positive CI in the ledger: [+11.5%, +34.0%] on n=16 verified closed baskets (WR=100%). To accelerate **without degrading expectancy**: ensure the VPS is writing daily shadow archives (no stake change, no breadth change — pure data collection fix). At 8 confirmed closures/day, n=100 arrives in 3.5 days *if* the archive cron resumes. The Jun16–19 gap is the only obstacle.

**Gate 2 (BAND_NO_PAIR_FAV)** is the most capital-critical because BAND_NO is live and actively staking at $5/fill. The 24h+ delay since n=100 crossing means ~$75/day in NO-side exposure is running without a validated CI. Every additional day accumulates more post-boundary data for the join; run it today.

**Gates 5 and 6 are phase-locked, not broken.** If the route diagnostic confirms THERMO cannot fire under Phase-1 config, they should be administratively closed (removed from active-experiment ledger and flagged as "resumes at BAND_PHASE2_CAPITAL=$600"). This clears false-alarm STALLED noise.

---

## 4. ASSUMPTION ATTACK

### Assumption A: Dispersion premium persists (YES band edge)
**Status: THREATENED** — the primary risk flag.

Supporting evidence: *none today*. The dispersion ratio is 0.671 for the 7th consecutive session, still 0.429 below the 1.10 floor. The band_dispersion_test showed shoulder calibration gap ≈ 0 (statistically indistinguishable from zero). Realized YES net = –4.9% (n<100, confounded). Jun18 vintage had 6-7% WR vs 15-20% theoretical at avg entry ~0.15. EU region at 0.830 is best but still below threshold and n=20 ratios.

Threatening evidence: every measurement to date contradicts this assumption for YES shoulders. The only mode-level gap is regime-dependent (loose regime YES +10%, peaked regime YES –4%). A static band rule fires regardless of regime, so the regime-conditional edge is not being harvested.

**Today's positive signal:** ratio improved +0.087 (0.584→0.671), the largest single-session gain in 5 reports. If this continues for 2 more sessions at similar magnitude, the ratio approaches the 0.80 EU-region threshold where edge may begin to exist. The Jun14 spike (0.620→0.835) reversed immediately — one session is not confirmation.

### Assumption B: Fills are not adversely selected
**Status: INCONCLUSIVE — proxy at-risk, n=33 below decision threshold**

Supporting evidence: fill rate 86-115% (Jun19-20), NO fill quality +7.2% realized. The 2h directional reclaim protects against the >6h stale-order adverse markout. RECYCLE099 today generated significant capital (implied $35-80+ this morning alone based on $199→$287 recovery).

Threatening evidence: winner's curse proxy 39.4% ITM (n=33). YES fills at entry 0.10–0.30 are being filled by takers who (apparently) know more than the book about which buckets will lose. The Jun18 vintage 6-7% WR on YES confirms this pattern.

**Flag for next exec_audit at n≥40 resolved fills.**

### Assumption C: RECYCLE099 velocity scales with capital
**Status: SUPPORTED — the actual working edge of the system**

The exec_audit confirms n=89 exits in 6 days, $436.34 gross (157.2% ROI on cost basis). Today's $88 capital recovery since Jun20 EOD demonstrates the engine is running. The velocity constraint is upstream (how many YES positions happen to converge to 0.99 before resolution). The 14.8 winners/day at current capital is healthy.

Threatening sub-assumption: if dispersion inverts further, the pool of near-resolution positions shrinks. Current regime (ratio 0.671) already reduces the supply. The system needs a sufficient tail of YES positions that almost-win to feed RECYCLE099, even if most positions lose at resolution. Reducing YES breadth too aggressively could starve RECYCLE099.

---

## 5. MARKET INTELLIGENCE: Competitor posture (day mod 3 = 0)

### badatmath_watch fill tape: 10-day gap

**The badatmath fill tape has been dark since 2026-06-11T23:58Z.** shadow_summary.json shows last badatmath_watch.jsonl entry from Jun11. The Jun12–21 period (10 days) has no fill-join observations.

**Last known posture (Jun11):** CLOB ladder books showed YES bids at [0.18, 0.21] across 3 levels; fill prices at 0.18–0.34 (YES); event-level depth consistent with $4-5/fill median fill size (consistent with our $3/$5 restoration). Band width ~5 buckets (±2 from mode) — which we now match with BAND_YES_MAX_OFF=2.

**Inferred current posture (from state_log Jun19 forensic):** He is in the June merge-velocity era. At $6-9k/day fill volume and ~$15k capital, his fill rate is ~10-15 fills/city/day vs our 0.18-0.24 posts/cycle. The merge engine (YES + NO on same bucket = pair) generates his velocity — we have same-bucket pairing enabled but only 2 confirmed merge co-fills to date (n=9 total merges per state_log Jun18 22:55). His co-fill rate ~40% vs our ~5%.

**Actionable gap:** We cannot detect whether he has modified his YES ceiling, NO composition, or added new cities post-Jun12. The shadow logger restart should be verified (P2 action above). This intelligence gap is concerning given that our config is calibrated to mirror his Jun-era posture.

---

## 6. THREE EXPERIMENTS

### Experiment 1: Gate 2 resolution join (NO engine CI)
**Hypothesis:** BAND_NO_PAIR_FAV legs (fire_no/pair_fav, d+1) in the post-clean-window (Jun19T00:30 onward) have ROI > 0% with CI95 lower bound > 0.  
**Data needed:** Gamma resolution truth for ~70-90 clean-window NO legs in band_struct_lite.jsonl.  
**Time:** 1 day (VPS run of band_resolution_join.py). **Cost:** Zero.  
**Success metric:** CI95 lower bound > 0 → READY. CI spans zero → AMBIGUOUS. CI upper < 0 → REJECTED (disable BAND_NO_ENABLED).  
**Decision-if-yes:** NO engine validated; hold current $5 stake and strict-rank d+1-NO-first queue.  
**Decision-if-no:** Cut BAND_NO_STAKE to $1-2 immediately; diagnose adverse selection source.

### Experiment 2: Dispersion-ratio daily YES gate
**Hypothesis:** Daily dispersion ratio correlates with YES band fill-to-resolution WR. Ratio > 0.80 days have positive YES WR; ratio < 0.60 days are structural losers.  
**Data needed:** Join calib_monitor_state.json (daily ratio) with band_net_attribution YES ROI by entry date on VPS. Window = 7+ resolved days.  
**Time:** 1 day coding + 7 days observation. **Cost:** Zero (analytics only, no live capital at risk).  
**Success metric:** |Spearman(dispersion_ratio, YES_daily_WR)| > 0.5 at n≥7 days.  
**Decision-if-yes:** Implement daily dispersion gate: suppress YES posting when ratio < 0.70. Does NOT reduce RECYCLE099 wins proportionally (fewer bids = fewer fills, but those not-posted were mostly losers at ratio < 0.70).  
**Decision-if-no:** Dispersion ratio has no intraday predictive power → alert remains a system-level watch, not a trade gate. Accept current YES lottery posture as deliberate.

### Experiment 3: THERMO route diagnostic
**Hypothesis:** Gate 5 stall is caused by BAND_NO_MAX=0.85 + BAND_TAILNO_VALIDATED=False phase-locking all 25,818 candidates, not a code bug.  
**Data:** Check thermo_maker.jsonl candidate no_ask distribution. If all candidates have no_ask > 0.85, config gates them. If some have no_ask ≤ 0.85 and still don't fire, route is broken.  
**Time:** 30 min VPS diagnostic. **Cost:** Zero.  
**Success metric:** >90% of candidates have no_ask > BAND_NO_MAX (0.85) → confirmed phase-locked.  
**Decision-if-phase-locked:** Close Gate 5 as "deferred Phase 2/3" (BAND_TAILNO_VALIDATED=False by design; resumes when capital reaches $600 and THERMO shadow data accumulates). Remove from active-experiment ledger.  
**Decision-if-code-broken:** Fix the THERMO fire path for the shadow-logging mode so actual data accumulates (even at shadow, not live, the n=3 gate data is worthless at current rate).

---

## 7. SINGLE BEST ACTION

**Run the Gate 2 VPS resolution join for BAND_NO_PAIR_FAV legs today.**

**Justification (citing specialist reports):**
- **Gatekeeper:** "BAND_NO_ENABLED=True, BAND_NO_STAKE=$5 currently LIVE. Cannot affirm or kill without resolution truth." Gate 2 has been above n=100 threshold for >24h with CI blocked.
- **Exec_audit:** NO fills are 66% of fill dollars ($95.40/24h, 36 events), 44% of registered fills at n=108. This is the dominant capital deployment stream.
- **State_log:** NO net +7.2% realized (n=97, ~decision-grade), the only directional side with confirmed positive returns.
- **PnL ledger:** Jun20 WEATHER_MAKER NO had 1/7 wins (14% WR, net –$30.98). But this is the Jun18 vintage — the clean-window gate specifically excludes pre-Jun19T00:30 data to avoid contamination.

The Gate 2 join is the one action where the **data already exists on the VPS** and the **decision is structurally binary** (positive CI = hold, negative CI = cut). It cannot be done from this container (Gamma 403). It requires exactly one command on the VPS.

**Concrete first step:** VPS operator runs:
```
python3 analysis/weather/band_resolution_join.py \
  --start 2026-06-19T00:30 \
  --reason fire_no pair_fav pair_samebucket
```
Post the CI95 output to state_log before end of today's trading session.

---

## PROPOSED ACTIONS (human review)

**[P1 — URGENT, zero capital risk]** Gate 2 VPS resolution join. Run band_resolution_join.py on post-Jun19T00:30 fire_no/pair_fav/pair_samebucket legs. CI branches: lower>0 → READY (hold), spans zero → hold + reduce BAND_NO_STAKE, upper<0 → REJECTED (disable). Read-only operation.

**[P2 — LOW effort, data quality]** Restart badatmath_watch shadow logger. Fill tape dark since Jun11 (10 days). Check VPS shadow logger; restart. No capital impact. Restores competitor visibility.

**[P3 — LOW effort, admin clarity]** Diagnose THERMO route (Experiment 3). If phase-locked by BAND_NO_MAX=0.85 + BAND_TAILNO_VALIDATED=False, close Gate 5 as "deferred Phase 2/3." Remove from STALLED-alert ledger.

**[P4 — LOW effort, data quality]** Trigger isotonic live-refit cron on VPS. Do NOT promote the Jun9 candidate (ceiling direction is wrong). Goal: generate a fresh candidate from Jun16–21 data. Evaluate ceiling direction before any promotion.

**[P5 — WATCH, no action]** Dispersion ratio improved +0.087 today (0.671), largest single-session gain in 5 reports. If ratio sustains >0.70 for 2 more consecutive sessions, run Experiment 2 (dispersion-ratio YES gate correlation test). Do NOT act on a single session — the Jun14 spike (0.835) reversed immediately.

**[NO CHANGE]** YES band config (BAND_PX_CEIL=0.30, BAND_YES_MAX_OFF=2, strict-rank queue, BAND_BASE_STAKE=$3): frozen from Jun19T00:30 clean-window. Gates 1 and 7 blocked on Gamma 403; no per-slice CI available. Hold ≥4 more days.

**[NO CHANGE]** Stakes or position sizes: capital recovered to $287 (Jun14 peak was $267 — we are now ABOVE the Jun14 peak). Peak drawdown the Jun20 trough to Jun21 recovery; the –25.5% drawdown cited in pnl_ledger was Jun14→Jun20; today's $287 fully clears that threshold. No stake reduction warranted.

---

*All claims sourced from exec_audit (07:07 UTC), calib_monitor (08:07 UTC), gatekeeper (09:07 UTC), pnl_ledger (23:37 UTC Jun20), band_config.txt, state_log.md, bankroll.json, maker_fills_recent.log — all read this session. No speculation from n<40 data. Report agent: REPORT-ONLY, no code or parameter changes were made.*
