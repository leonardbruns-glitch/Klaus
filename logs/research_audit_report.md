# Klaus Research Audit — 2026-06-18T11:00Z

**Analyst:** Research Strategist (scheduled routine)
**Snapshot:** 2026-06-18T10:16:41Z (age ~1h — FRESH)
**System:** `klaus systemd: active` (uptime since 2026-06-17T12:11:58 UTC)
**Capital:** $243.50 (bankroll.json saved 2026-06-18T10:00 UTC)
**Branch:** `claude/find-lag-parameter-rFQ0N`

---

## SPECIALIST REPORT FRESHNESS

| Report | Dated | Age | Status |
|---|---|---|---|
| exec_audit_report.md | 2026-06-17T07:11Z | 27.8h | OK |
| calib_monitor_report.md | 2026-06-16T08:16Z | 50.7h | **STALE (>36h)** |
| gatekeeper_report.md | 2026-06-17T10:23Z | 24.6h | OK |
| pnl_ledger_report.md | 2026-06-14T23:37Z | 83.4h | **STALE (>36h)** |

**calib_monitor and pnl_ledger are stale.** Dispersion dimension sourced from calib_monitor day-by-day table (Jun11-15) + state_log entries. PnL dimension sourced from raw bankroll.json ($243.50, Jun18 10:00 UTC) + trades.jsonl (WEATHER_STRUCT_BAND n=252 resolved, pnl=−$463.65, WR 7.1%; bankroll total_pnl=+$41.12 all-time). No analysis fabricated beyond these raw inputs.

---

## 1. PRIMARY BOTTLENECK FOR COMPOUNDING

**DISPERSION EDGE COLLAPSE — the foundational assumption of the band system is inverted and has been for ≥6 consecutive days.**

The band harvests over-dispersion premium: it profits when market implied sigma exceeds true sigma of daily temperature outcomes (ratio > 1.10). Every other lever — turns/day, NO parity, cash velocity, pair co-fill — is irrelevant if entry edge is net-negative.

Day-by-day from calib_monitor (Jun16 report, day-by-day table — the authoritative dispersion series):

| Date | True sigma | Dispersion ratio (model) | Status |
|---|---|---|---|
| 2026-06-11 | 1.64°C | 0.728 | below 1.10 |
| 2026-06-12 | 1.52°C | 0.592 | below 1.10 |
| 2026-06-13 | 1.36°C | 0.667 | below 1.10 |
| 2026-06-14 | 1.42°C | 0.516 | below 1.10 |
| 2026-06-15 | 1.75°C | 0.504 | below 1.10 |

Trend: 0.728 → 0.504, monotonically decreasing. Implied sigma ~0.96°C (model) / ~0.73°C (market, n=80). True sigma 1.55°C. The market is correctly pricing tighter-than-true distributions; we are buying wings that the market has accurately priced as cheap.

Exec_audit confirms at entry level: YES fills resolve at **WR 4.4%** (n=137, decision-grade) vs breakeven 23.1% → gap of **−18.7pp**. STWA_RESOLVED ROI = −88.6% net, −$338.63 over 7d. Gatekeeper: net band era P&L +$58.56 Jun11-16 → +$27.75 Jun11-17, with Jun15-17 net-negative. Trades.jsonl: WEATHER_STRUCT_BAND all-time pnl = −$463.65, WR 7.1% (n=252). The system is net-positive ($41.12 all-time) only via RECYCLE099 convergence exits — a mechanism that recycles existing positions, not one that generates new entry edge.

**Why this outranks equity deployed and turns/day:** At current dispersion inversion, increasing velocity (turns/day) compounds entry losses faster. Fixing NO parity deploys more capital into a currently −88.6% ROI resolution stream. Structural improvements are not additive when the edge premise is inverted.

---

## 2. EXISTING-SYSTEM OPTIMIZATION

### 2a. Kill-Switch Re-Anchor (CRITICAL — 3× flagged, never fixed)
`bankroll.daily_start_capital` = $15.95. Current capital = $243.50. Daily halt fires at `capital < daily_start − $10` = $5.95 — permanently unreachable. Daily loss limit is broken.

- **Expected delta:** Restores the intraday −$10 halt (or proportional equivalent) as a functioning brake. During dispersion inversion, this is the only automated stop on a bad resolution day.
- **Confidence:** Certain — arithmetic. Flagged state_log Jun14, Jun15, gatekeeper Jun17.
- **Effort:** 1-line startup fix (reset `daily_start_capital = capital` at session start). Tier-1 bug fix.

### 2b. Phantom-Exposure Fix (Jun17 06:45) — Impact Unconfirmed
Fix deployed but exec_audit ran 26 min later (07:11 UTC) — insufficient time to see post-fix behavior. Pre-fix: bot tracked ~$39 exposure vs ~$17 real open BUYs on CLOB → ~$22 phantom headroom pinned. Expected post-fix: cycle headroom rises from ~$0.5 to ~$17-22, yes_cap from ~$0.36 to ~$2+, enabling NO posting (BAND_NO_STAKE=4.5 requires ≥$4.50 available).

- **Expected delta:** High — cash-gate strangle was diagnosed as the dominant binding constraint (Jun17 06:45 state_log). Fix + proportional queue + book clear all deployed Jun17 11-12.
- **Confidence:** High for mechanism; zero confirmed by data yet.
- **Effort:** Watch next exec_audit (Jun18 07:07). No action needed if NO posts are appearing.

### 2c. NO Parity Structural Failure (5/6 days <25% NO posts)
Resting book at exec_audit: 38 YES / 5 NO = 11.6% NO. NO fires = 0 on Jun16, 0 on Jun17 (pre-fix). Root cause confirmed as phantom-exposure strangle pre-Jun17. Post-fix, the BAND_NO_CASH_RESERVE=0.25 still limits NO to 25% of cycle headroom; at $20+ headroom (post-fix), that's $5 — just above the $4.50 min stake, so NO can now fire. The proportional queue allocates ~36% to NO cells, prioritizing d+1 NO.

- **Expected delta:** NO should resume after Jun17 12:12 (book clear + proportional queue + post-phantom-fix headroom). Monitor Jun18 fill tape.
- **Confidence:** Medium — depends on whether headroom post-fix is confirmed ≥$12 (to give 36% × $12 = $4.32... borderline). May need BAND_NO_STAKE lowered to $3 if headroom is only $10-12.
- **Effort:** Monitor only for 24h; act if NO still =0 in Jun18 fill tape.

### 2d. Sum Gate Under Dispersion Inversion — Unconfirmed
BAND_SUM_MAX=0.85. Historical ROI by Σ-bucket (pre-Jun11, from state_log Jun11): Σ<0.50 +57.4% (n=214), 0.50-0.70 +39.0% (n=111), 0.70-0.85 +13.0% (n=46 trend). The 0.70-0.85 "trend" ROI may be negative in the current dispersion-inverted regime. No Jun11+ slice analysis exists yet.

- **Expected delta:** Tightening to 0.75 rejects thin-margin legs most exposed to adverse selection when dispersion is inverted. Magnitude unknown without the slice.
- **Confidence:** Low — requires Experiment C analysis first.
- **Effort:** VPS script run (48h, see Experiment C).

---

## 3. GATE PIPELINE REVIEW

No gate transitioned READY or REJECTED since last run. All COLLECTING.

| Gate | n | Status | Nearest-Ready Accelerant |
|---|---|---|---|
| BAND_YES | 3,296 legs (cloud) / 3,418 (VPS Jun17) | CI blocked on Gamma 403 from cloud | VPS cron now fixed — daily resolution join should unblock CI. Verify Jun17 VPS run output. |
| BAND_NO_PAIR_FAV | 53 (39 NO + 14 PAIR_FAV first seen Jun16-17) | Collecting | Phantom-exposure fix should restore NO firing; PAIR_FAV gaining slowly. ETA ~7d at current rate if NO resumes. |
| M1_BETA_LOCKOUT | 31 | CI straddles zero [−21.9%, +25.0%] | No safe accelerant. Detections are event-driven (METAR lockout events). Confirm metar_lockout.jsonl is actively logging on VPS. ETA ~13d. |
| THERMO_MAKER_NO | 3 | Nascent — 34d to kill-gate 20 | $15/day cap is correct — do not expand before n=20 kill-gate. |
| FILLED_VS_FIRED | 179 | Watch item, not decision gate | Format changed to syslog; not gate-critical. |
| BASKET_EXIT | 6,254 | Unit defn blocker (float-jitter on t_close) | Human must define canonical unit (round t_close to nearest second) before computing cash-out metric. |
| SUM_POSTED_0.70-0.85 | 1,379 | CI blocked on Gamma 403 | VPS cron fix is the enabler. Same as BAND_YES. |

**Key observation:** The VPS cron fix (Jun17 05:45) is the single highest-leverage gate-infrastructure event this week. If running, all resolution-dependent gates should have decision-grade CI by Jun20. Human should verify: `tail -20 /root/Klaus/logs/band_resolution_join.log` or equivalent on VPS.

---

## 4. ASSUMPTION ATTACK

### Assumption 1: Dispersion premium persists (implied sigma > true sigma)
**Status: THREATENED — inverted for 6+ consecutive days, trending down.**

Evidence FOR: VPS band_resolution_join (Jun17, n=3,418): conditional-on-fill YES +7.6% (n=3,275, WR 20.5% vs quote 0.191), every slice positive. This is decision-grade at n.

Evidence AGAINST: calib_monitor dispersion ratio 0.504-0.728 over Jun11-15, monotonically decreasing. The +7.6% historical ROI is a corpus-wide average likely dominated by Jun11-13 when ratio was 0.67-0.73. The same VPS report was run Jun17 05:45 — its corpus includes Jun11-15 data where the ratio was already inverted (0.504-0.73). The conditional ROI measures fills selected by Σ-gate/price-window, not the dispersion regime. A regime-conditioned split (Jun11-12 vs Jun14-15) would isolate whether +7.6% holds when ratio<0.60.

**Verdict: Assumption 1 is the load-bearing risk. Historical edge is real; current regime is adverse. Monitor the gauge, not the corpus-average ROI.**

### Assumption 2: Fills are not adversely selected
**Status: FALSIFIED on current resolution window (n=137, decision-grade).**

Exec_audit: YES resolution WR 4.4% vs breakeven 23.1% = −18.7pp. At avg entry 0.231, the true resolution probability for our filled legs is ~4%, not 23%. The market is accurately pricing what we post; we are on the wrong side.

Survivor-bias caveat: RECYCLE099 exits winners before resolution → STWA_RESOLVED population is skewed toward losers. But even a 50% bias correction (assume recycle captures all true-WR 23% positions) would only lift estimated true WR to ~8-9%, still far below breakeven.

All-fires comparison from exec_audit: "n=1,856 leg quotes Jun15-16" with fill rates 86-88%. A high fill rate against a −18.7pp resolution shortfall means the market is filling our quotes quickly because our YES bids are BELOW fair value in a market that is willing to take them — consistent with dispersion inversion (the YES legs we quote are indeed cheap, meaning the market knows the outcome distribution is narrower than we assume).

**Verdict: Assumption 2 is falsified for the Jun15-17 resolution cohort. Cannot be assumed intact.**

### Assumption 3: Recycle velocity scales (RECYCLE099 + merge flywheel)
**Status: PARTIALLY SUPPORTED — recycle is real, scale is insufficient at current dispersion.**

Evidence FOR: exit099 events 67 total at +$383.15 (WR 98.5%) per gatekeeper. The convergence mechanism works — the exit triggers correctly.

Evidence AGAINST: At current rates (~10/day), gross recycle yield ~+$57/day. Against STWA_RESOLVED losses at current WR (~$66/day loss rate from 7d data), the system is net-negative on the resolution side. Pair co-fill (same-bucket pair-quoting, Jun17) is the proposed fix to raise recycle velocity 3-5× — but co-fill data does not yet exist.

Key structural bet: if same-bucket pairs achieve co-fill rate ≥20%, each YES position generates an offsetting NO position. When YES resolves NO (which happens 95.6% of the time), the NO pair resolves YES and the pair is net-positive. This is the pair-merge mechanism. Whether the CLOB will fill our NO pair leg at prices that preserve ≥$0.08/sh margin (BAND_PAIR_SUM_MAX=0.92) is unproven.

**Verdict: Assumption 3 is mechanically sound but empirically unproven at the new pair-quoting scale. First 72h data (Jun17-20) is the critical test.**

---

## 5. MARKET INTELLIGENCE — [0] Competitor Posture

*(18 mod 3 = 0 → competitor posture. Gamma API 403 from container — no live data. Working from state_log Jun17 10:45, most recent complete teardown.)*

**badatmath current state (Jun17 31-day re-derivation, n=42,470 buys / 7,955 resolved):**
- Strategy: 98.6% maker, YES median px 0.130 (0.05-0.45), NO median 0.650 (0.52-0.95)
- Sizing: ~$40 YES + $30 NO per event, bell-curve/share-U
- Velocity: ~100% daily buy$ recycled same-day (merge $41k + redeem $86k/month), ~1 turn/day
- Pair co-fill: ~40%, d0/d1/d2 ~40/40/20 spend split
- Edge: +11.4% ROI from over-dispersion premium (true sigma > implied sigma — opposite of our current regime)
- Growth: $267 → $13.3k in 31d via velocity × reinvestment, not expanding edge

**Gap to badatmath (as of Jun17 data):**
- Turns/day: 0.3-0.4 (ours) vs ~1.0 (his) — 2.5-3.3× gap
- Pair co-fill: ~5% (pre-Jun17) vs ~40% — 8× gap
- Dispersion ratio: ~0.50-0.73 (ours, inverted) vs (presumably >1.10, his edge intact)

**Key implication:** badatmath's +11.4% edge requires dispersion ratio >1.0. If he is trading the same 51-city universe on the same resolution oracle, and our dispersion ratio is 0.50-0.73, either: (a) he has a superior weather model (lower implied sigma closer to true), (b) he focuses on a subset of cities with higher dispersion, or (c) the dispersion inversion is our model's problem, not the market's. Option (c) would mean our model is systematically overestimating implied sigma — consistent with the calib_monitor finding of systematic warm miss (+0.307°C mean residual bias). If our model predicts too warm, we see ladder buckets as cheaper than they are, misidentify the "dispersion edge" as a buying opportunity, and fill at prices that are correctly priced by the market.

No new leaderboard teardown available (API blocked). No delta vs Jun17 state.

---

## 6. EXPERIMENTS

### Experiment A: Regime-conditioned ROI split by dispersion date (fast, high VoI)
- **Hypothesis:** VPS band_resolution_join output, when split by resolution date into Jun11-13 (ratio 0.67-0.73) vs Jun14-17 (ratio 0.50-0.52), shows materially different conditional-on-fill ROI, quantifying how much edge decays when dispersion is inverted.
- **Data:** VPS band_resolution_join n=3,418 (already computed Jun17). Script: `GROUP BY date_resolved, calc ROI per date; corr(dispersion_ratio[date], ROI[date])`.
- **Time:** 4h for script run on VPS.
- **Cost:** $0.
- **Success metric:** Jun11-13 ROI vs Jun14-17 ROI differ by ≥10pp AND Spearman corr(ratio, ROI) > 0.4 over the 7 available days.
- **Decision if yes:** The dispersion ratio is a near-term ROI predictor. Immediately wire BAND_EV_MIN as a function of dispersion ratio (e.g., EV_MIN = 0.08 + 0.10 × max(0, 1.0 − ratio) — raise entry bar when market is efficiently pricing). This is a regime gate, not a dial.
- **Decision if no:** Date-level correlation is noise at n=7 days; the conditional-on-fill ROI is stable across the dispersion range; keep current config, wait for n≥90 days (Experiment from prior audits).
- **Highest VoI of the 3:** directly tests whether the dispersion gauge reading should gate entry.

### Experiment B: Same-bucket pair co-fill validation (72h — already 42h elapsed)
- **Hypothesis:** ≥20% of YES band legs posted Jun17+ receive a same-bucket NO maker fill within 24h.
- **Data:** maker_fills_recent.log Jun17-20 + pair_shadow_join.py outputs + RECYCLE099 merge events per day.
- **Time:** 30h remaining (Jun18 11:00 → Jun20 00:00).
- **Cost:** $0.
- **Success metric:** YES legs with matched NO fill within 24h ≥20%; OR merge events ≥3/day (was ~1/day pre-Jun17).
- **Decision if yes:** Pair engine achieving velocity. Assess BAND_PAIR_SB_MAX_BEHIND loosening (0.10 → 0.15) to improve NO-leg fill probability.
- **Decision if no:** Diagnose: (a) NO still cash-gate failing despite phantom-fix — check headroom; (b) NO fill prices indicate MM avoidance of our NO leg — adversarial signal, rethink YES-then-pair model.

### Experiment C: Σ-slice ROI post-Jun11 (48h, uses existing data)
- **Hypothesis:** Within the Jun11+ window (dispersion ratio <0.73 throughout), legs in the Σ(posted) 0.75-0.85 bucket have conditional-on-fill ROI < 0%, while legs in Σ<0.75 remain positive — supporting tightening BAND_SUM_MAX to 0.75 under inversion.
- **Data:** VPS band_resolution_join n=3,418. Need: `WHERE date_resolved >= '2026-06-11' GROUP BY sigma_bucket (lt0.75, 0.75-0.85)`.
- **Time:** 48h (4h VPS script, 44h for additional resolutions).
- **Cost:** $0.
- **Success metric:** n≥40 in 0.75-0.85 slice with mean ROI <0% and CI upper <+5%.
- **Decision if yes:** Raise BAND_SUM_MAX floor → 0.75 while dispersion ratio <0.90.
- **Decision if no:** Σ-slice ROI is stable; sum gate is not the right lever; do not change.

---

## 7. SINGLE BEST ACTION

**Re-anchor `daily_start_capital` to current capital at session start.**

This maximizes (compounding impact × P(success)) / effort:

- **Compounding impact:** The kill-switch is the primary risk control during a dispersion-inverted regime. Without it, a day of heavy resolution losses (e.g., −$30 in a 3h window) has no automated halt. The dispersion gauge has been inverted for 6+ days. STWA_RESOLVED WR = 4.4%. The combination — broken brake + adverse regime — is the condition under which maximum drawdown occurs.
- **P(success):** 100%. The fix is adding one line at session start to update a stale snapshot value. No edge dependency, no market assumption required.
- **Effort:** 30 minutes. Locate the `daily_start_capital` initialization (bankroll.py or weather_arb.py startup block), confirm it does not reset at midnight or session start, add the reset. Commit as Tier-1 bug fix.

**Concrete first step:** Run `grep -r "daily_start_capital" /root/Klaus/` on VPS to find the initialization. Verify whether it loads from `bankroll.json` (stale) or is reset from `capital` at startup. If stale: add `bankroll.daily_start_capital = bankroll.capital` at the point where the daily session begins.

**Gate promotion/kill note:** No gate hit READY or REJECTED (all COLLECTING). The default candidate per protocol would be the nearest-READY gate — which is BAND_NO_PAIR_FAV at n=53 (~7d to READY) — but no action needed there yet. The kill-switch re-anchor is a clear Tier-1 safety fix that takes precedence.

**Cites:** exec_audit_report Jun17 (STWA_RESOLVED −$338.63, 7d; WR 4.4%); gatekeeper_report Jun17 ("daily_start_capital $15.95 vs capital ~$246 ⇒ daily halt cannot fire"); calib_monitor_report Jun16 (dispersion ratio 0.589, ALERT persistent, "not a measurement artifact").

---

## PROPOSED ACTIONS (human review)

| Priority | Action | Tier | Source | Expected Impact |
|---|---|---|---|---|
| P0 | Reset `daily_start_capital` to current capital at session start | Tier 1 (bug fix) | Stale since early bot era; flagged 3× | Restores daily halt during dispersion inversion |
| P1 | Monitor Jun18 fill tape for NO posting resumption | Watch | Phantom-exposure fix Jun17 06:45 | Confirms whether cash-gate strangle is resolved |
| P2 | Run Experiment A: date × ROI split in VPS band_resolution_join | Tier 1 analysis | Existing data n=3,418 | Quantifies whether dispersion gauge should gate entry |
| P3 | Run Experiment C: Σ-slice ROI post-Jun11 | Tier 1 analysis | Same dataset | Tests BAND_SUM_MAX tightening case |
| P4 | Verify VPS band_resolution_join cron ran Jun17 + Jun18 | Tier 1 ops | Cron fix Jun17 05:45 | BAND_YES gate CI depends on it |
| — | **Do NOT expand stakes, capital, or breadth until dispersion ratio >1.10** | Safety | 6+ days inverted, WR 4.4%, kill-switch broken | Scaling into adverse regime compounds losses |

---

*Anti-sycophancy check: Last 5 STWA_RESOLVED trades = 5 losses (−$1.02, −$1.86, −$1.40, −$1.87, −$1.00 from trades.jsonl tail). 7d WR=4.4%, −$338.63 net. The current config is operating in an adverse regime. Total band pnl all-time = −$463.65. The system survives only via RECYCLE099. These facts are stated without mitigation.*
