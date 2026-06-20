# Klaus Research Audit — 2026-06-20T14:10Z

**Snapshot:** 2026-06-20T13:46:39Z (fresh, <0.5h) | **System:** `systemd: active` (uptime since 2026-06-19T00:17 UTC, 37.5h) | **Capital:** $211.59 (bankroll.json, 12:52 UTC)

**Specialist report freshness:**
- exec_audit_report.md — 2026-06-20T07:07Z ✓ (<7h)
- calib_monitor_report.md — 2026-06-20T08:10Z ✓ (<6h)
- gatekeeper_report.md — 2026-06-20T12:16Z ✓ (<2h)
- pnl_ledger_report.md — STALLED (data-mirror frozen after 00:39 UTC Jun 20; report aborted). Working from raw mirror data for PnL dimension.

---

## 1. PRIMARY BOTTLENECK: TURNS/DAY — book saturation halting new posts

**Ranking considered:** equity deployed, turns/day, ROI/turn, fills, NO-parity, calibration, dispersion edge, risk frame, data, reliability.

**Verdict: turns/day** is the binding constraint *today*, driven by book saturation.

From exec_audit: Jun 20 avg posted/cycle = 0.0, zero-post cycles = 96%, cash_preskip avg $134 (from raw log: min $111, max $188, n=161 cycles to 13:46 UTC). Deployable cash = $212 × (1 − 0.40 NO_reserve overhead) ≈ $148; committed $134 → free float ≈ **$14**. With NO min stake = $5 and YES min ≈ $1.20, the queue has candidates (no_cands avg 151, pair_cands 24-27) but posts zero because top-ranked items already have resting bids within BAND_RECLAIM_BEHIND of touch (no reclaim fires, no re-post, no headroom for new posts).

**Turns/day degradation:** Jun 18: 69 fills; Jun 19: 38 fills; Jun 20 pace (16 new registered fills in 13.75h, extrapolated): ~28 fills/day. The decline is not fill-rate failure (exec_audit: Jun 18 73%, Jun 19 86%) but *posting-rate collapse* as positions fill and lock capital ahead of daily resolution. Jun 20 side split from raw log: 10 YES new fills ($17.29), 6 NO new fills ($28.62) = **62.3% NO by $** — highest NO share on record, confirming favNO-top-rank (Jun 19 00:30 UTC commit) is measurably working.

**Why it matters for compounding:** ROI/turn × turns/day × equity deployed. Equity is deployed (95% committed), but if turns/day halves (69 → 28) the compounding clock slows proportionally. The capital is *working* (resting bids + open positions awaiting resolution), not idle — but it cycles at weather-resolution cadence (daily), capping throughput structurally.

**What will unblock it:** Positions resolving at day-end (weather settlement tonight) + RECYCLE099 sells at >0.99. No intraday lever exists except reclaim, which correctly protects queue-priority orders.

**Close second: dispersion edge (inverted, 7th consecutive report).** The dispersion ratio 0.584 means the band YES directional premise is structurally inverted. Flagged in Section 4.

---

## 2. EXISTING-SYSTEM OPTIMIZATION

### 2a. NO daily cap approximately binding — conditional relaxation available

exec_audit: Jun 19 NO fills = $60.75 vs BAND_NO_DAILY_CAP = 40 (or 30%×cap ≈ $63.60). Natural liquidity at ~14-20 NO fills/day × $5 = $70-100 potential; cap binding by ~$30-40/day. **Expected delta from raising BAND_NO_CAP_FRAC 0.30→0.40:** ~$20-30 additional NO/day if breadth allows. Confidence: moderate (breadth is real, liquidity untested above current level). Effort: 1-line. **Conditional: do not change before Gate 2 verdict (§6 Experiment A).**

### 2b. cash_preskip $134 is correctly deployed, not idle

Resting bids $13.20 (exec_audit: 11 YES $8.19 + 2 NO $5.01) + open resolved-pending positions ~$121. Capital is working. No leak, no fix needed.

### 2c. NO-parity holding at minimum threshold, fragile

exec_audit: Jun 19 = 26% NO posts, Jun 20 = 25%. The threshold is met but with no margin. Structural breadth limit (~19 NO candidates/day) caps parity regardless of config. No lever available from this session.

### 2d. Isotonic refit cron: investigate staleness (low urgency)

calib_monitor: candidate 11 days stale (n_live frozen at 1,037; should have ~385 live rows at ~35 city-days/day accrual). Refit cron possibly down or threshold not crossed. Deploying current candidate would *worsen* [0.6,0.7) calibration (ceiling 0.37 vs deployed 0.63). Do not deploy. Investigate cron on VPS. Expected delta: small (structural artifact, not data-stale dominated). Effort: low.

### 2e. Data-mirror freeze pattern — disk pressure suspect

pnl_ledger: mirror froze at 00:39 UTC Jun 20, recovered by 13:46 UTC. system_status: disk at 86% full (79G used / 97G total). Disk pressure likely caused the mirror job to fail silently at midnight. A repeat tonight will again stall the pnl_ledger. Expected delta: no P&L impact, but kills measurement visibility. Effort: clear old logs on VPS.

### 2f. YES no_resv_skip now 0 (improvement confirmed)

Raw log STRUCT-BAND-Q Jun 20 13:24-13:44: `yes_resv_skip=0` consistently (was 134-148 under proportional queue Jun 18). The strict-rank mode correctly frees all YES capital from the reservation-skip trap. Previously YES was being withheld from its own budget. Now correctly queue-competed.

---

## 3. GATE PIPELINE REVIEW

From gatekeeper_report (12:16 UTC):

| Gate | n | Status | ETA / Blocker |
|---|---|---|---|
| 1. BAND_YES | 4914 | COLLECTING (CI blocked) | VPS resolution join post-Jun-19-00:30 boundary |
| **2. BAND_NO_PAIR_FAV** | **105** | **★ n≥100 — VPS join needed** | Gamma 403 from container only; VPS unblocked |
| 3. FILLED_VS_FIRED | 100 | COLLECTING (CID join blocked) | Ages out in ~5d; VPS urgent |
| 4. BASKET_EXIT | ≈64 | COLLECTING (infra blocker) | Per-day archive fix; ~Jun 23 at 19/day |
| 5. THERMO_MAKER_NO | 3 | STALLED / near-kill | 0 fires 8+ days; unconfirmed 4th loss pending |
| 6. M1_BETA_LOCKOUT | 31 | STALLED | No thin-margin fires 10+ days; wiring investigation needed |
| 7. SUM_POSTED_0.70-0.85 | 2331 | COLLECTING (CI blocked) | VPS join same as Gate 1 |

**Gate 2 is the highest-priority action.** It crossed n=100 (+15 since last run). It is the gate governing the only sub-system with demonstrated positive ROI (favNO +7.2% aggregate, n=97). The Gamma 403 is sandbox-only. VPS action required within the next 12h before Jun 19 fills age out of the 7d window.

**To accelerate Gate 2 without degrading expectancy:** Breadth only — confirm no_cands enumeration is correctly capturing all 51 cities' favNO candidates. Do not raise NO stake to inflate n faster.

**Gate 5:** Functionally dead. 0 fires for 8 days, CI upper +0.7% with 2 large losses in 3 fills. One additional adverse fill (Paris NO at 0.98 pending confirmation) flips CI fully negative. Recommend declaring REJECTED at next VPS evaluation — no code change needed (BAND_TAILNO_VALIDATED=False already gates it OFF).

**Gate 6:** Thin-margin [0.2, 0.5)C fires absent 10+ days (1 verified trade). Schema v2 logs candidates, not fires — actual fire count may be 0, not just unlogged. Wiring investigation warranted on VPS.

---

## 4. ASSUMPTION ATTACK

### Assumption A: Dispersion premium persists

**THREATENED — 7th consecutive alert. First marginal improvement today (+0.028).**

calib_monitor: ratio = 0.584 (model σ = 0.854°C vs true σ = 1.461°C). Market under-prices weather spread, not over-prices it — the YES-taker directional premise is inverted.

- *Supports:* First improvement in 4 reports. Jun 18 daily ratio = 0.827, Jun 19 = 0.765. EU/Asia highest ratio (0.637). Possible seasonal shift (mid-June temperatures more predictable, true σ compressing; if sustained, ratio could recover toward 1.0).
- *Threatens:* 7-report streak below 1.10. US/Americas most inverted (0.546). Warm bias +0.40°C growing — model misses peak temps, artificially inflating true σ. band_dispersion_test (Jun 18, n=6,899): shoulder calibration gap ≈ statistical zero; the +8% band shadow ROI is bid-below-ask spread, not dispersion premium. YES net −4.9% (n=299, 2-week average confounded by config churn).
- *Critical nuance:* The maker band system does NOT require positive dispersion to be +EV — maker rebate + bid-below-touch spread capture can generate edge independent of directional correctness. However, YES resolution outcomes still require the market to resolve favorably, and with inverted dispersion the mode at d+1 is *over-priced* (WR lower than ask). ONLY at d+2 is the mode under-priced (+0.022 gap). The current d+2 YES priority ranking is structurally correct given band_dispersion_test, and the favNO d+1 overlay is also term-structure-consistent.

### Assumption B: Fills are not adversely selected

**NUANCED — YES: clean at <5m, adverse at >6h. NO: untested but structurally favorable.**

state_log Jun 18 23:59 (band_markout_age.py, n=848): fresh fills (<5m) mk = +1.57¢/sh; stale (>6h) mk = −1.07¢/sh. Root cause = stale orders run over by informed price drift, corrected by 2h directional reclaim. The queue-priority hypothesis was falsified.

NO fills: 6 Jun 20 fills at 0.54-0.64. Directional theta for NO differs from YES: temperature maxima accumulate intraday, so a NO bid resting overnight is filled by someone buying NO after the day's peak confirms — our stale NO should be *cleaner*, not more adverse. This is untested (n=29 NO fills total, too thin for markout-by-age).

- *Supports:* 2h reclaim reduces YES exposure above stale threshold. Fresh fill quality confirmed clean (+1.57¢/sh). Jun 20 NO fills at reasonable mid-range prices (not last-cent).
- *Threatens:* YES net −4.9% aggregate persists despite fill cleanliness (the adverse selection is at *resolution*, not fill). Model predicts wrong-way on YES mode at d+1 (over-priced per band_dispersion_test). Stale YES (>6h) being run over remains an unsolved leak for positions posted before the morning session.

### Assumption C: Recycle velocity scales with book

**SUPPORTED but Jun 20 data-blind.**

pnl_ledger partial: Jun 19 RECYCLE099 = $78.58 across 19 exits — strong. Jun 18→19 capital delta +$17.37 net of ~$61 resolution losses, confirming RECYCLE099 is the primary P&L absorber. 

Jun 20: capital $231.89 (Jun 19 EOD) → $211.59 (12:52 UTC) = −$20.30 in 12.75h. RECYCLE099 exits not visible (exit099_live.jsonl not mirrored today). The −$20.30 is gross; net may be better. Disk pressure (86% full) may explain the data-mirror freeze that hides today's exits.

- *Supports:* Jun 19 $78.58 confirmed strong. yes_resv_skip=0 (strict rank) ensures YES book stays filled, giving RECYCLE099 candidates continuously.
- *Threatens:* If Jun 20's resolution losses outpace RECYCLE099 (the −$20.30 raw figure), the capital trajectory since Jun 13 (estimated $214→$212, essentially flat) would confirm the state_log Jun 18 finding: 14d net ≈ +$3, not profitable.

---

## 5. MARKET INTELLIGENCE (Day-of-month 20 mod 3 = 2: Platform mechanics)

**Scope:** Fee schedule / maker-rebate / liquidity-rewards changes since state_log last captured.

From state_log knowledge base: updown BTC/ETH/SOL taker fee ~1.56% at 50% odds (2026-03-30). Weather maker rebate ≈ 100% of taker fee redistributed. Fee reform 2026-03-30 added 8 categories; updown rates unchanged. No subsequent fee changes appear in Jun 12-19 state_log entries.

Sandbox blocks direct docs.polymarket.com access. The STRUCT-BAND-Q logs for Jun 20 show no anomalous posting mechanics (normal bid/ask format, fills via USER-WS, maker-fill confirmation pattern unchanged). **No evidence of fee schedule or rebate-structure changes in this window. Clean.**

**One infrastructure risk note:** The Cloudflare WAF / QuantVPS Dublin stack remains the critical dependency (CLAUDE.md). The 37.5h continuous uptime with no WAF blocks is the relevant data point — the stack is holding. Disk pressure (86%) is the near-term infrastructure risk: if disk fills, the bot's logging and potentially the mirror service will fail. This is more urgent than any fee-schedule uncertainty.

---

## 6. THREE EXPERIMENTS

### Experiment A: Gate 2 resolution join (VPS, <1h)
**Hypothesis:** favNO maker fills (n=105) resolve at CI95 > 0, confirming the +7.2% aggregate edge holds on our specific fills with the current config.
**Data:** Run `band_resolution_join.py` on VPS targeting fire_no/pair_fav records from Jun 15+. Gamma API accessible from QuantVPS Dublin (not sandbox).
**Time:** <1h. **Cost:** $0 (code already built).
**Success metric:** CI95 lower > 0 → Gate 2 READY.
**Decision-if-yes:** Authorize BAND_NO_CAP_FRAC increase 0.30→0.40 (§2a). Start breadth investigation for NO candidate expansion.
**Decision-if-ambiguous (CI straddles 0):** Hold. Collect more resolved legs. Do not scale NO stake.
**Decision-if-rejected:** favNO is +EV in aggregate but NOT in execution — adverse fill or resolution miss. Strategic rethink: lean entirely on RECYCLE099 + NEG_RISK_ARB. Cease adding NO quote capital.

### Experiment B: NO-fill markout-by-age (VPS, 2-3 days)
**Hypothesis:** favNO fills show flat or improving markout at >6h age (directional theta: NO bids on temperature markets converge to 1.0 as day progresses, making stale NO bids *cleaner* than stale YES), implying the 2h directional reclaim hurts NO queue priority unnecessarily.
**Data:** Replicate `band_markout_age.py` for side=NO only. Current n=29 NO fills in 7d window (TREND-grade).
**Time:** 2-3 days to reach n≥50. **Cost:** $0.
**Success metric:** NO mk(>2h) > 0 → extend BAND_PAIR_RECLAIM_AGE_S beyond 8h (let NO bids rest toward full market life, improving co-fill probability).
**Decision-if-NO-degrades-with-age:** Apply 2h directional reclaim to NO legs matching YES protection. This would increase NO turnover at cost of queue priority.

### Experiment C: Clean-window band_net_attribution (VPS, 2-3 days)
**Hypothesis:** The trimmed config (BAND_PX_CEIL=0.30, favNO rank-0, d+2 YES priority) generates different YES net attribution than the 2-week confounded history. The [0.10,0.22] YES slice (prior +35% realized) survives; the [0.22,0.30] slice is neutral-to-positive; YES net overall ≥ −1%.
**Data:** `band_net_attribution.py` on post-Jun-19-00:30 UTC window only (current clean-window = 37h). n≥40 YES legs resolved needed (TREND-grade; ~2 days at current fill rate to reach n≥100).
**Time:** 2-3 days. **Cost:** $0.
**Success metric:** YES net > −3% at n≥100 → keep current YES config. YES net < −5% at n≥100 → cut YES further (raise PX_CEIL to 0.22 matching the prior +35% zone boundary, or disable YES entirely outside d+2 mode).
**Decision-if-rejected (YES net < −10%):** Structural YES bleed persists. Redirect YES capital entirely to NO breadth and RECYCLE099 + NEG_RISK_ARB. This would be a Phase 1 redesign — major.

---

## 7. SINGLE BEST ACTION: Run Gate 2 resolution join on VPS (within 12h)

**Cited reports:** gatekeeper_report (Gate 2 n=105 crossed threshold, CI blocked only by Gamma 403 from container); exec_audit (Jun 20 NO $ share = 62.3%, NO engine demonstrably working after favNO-top-rank deploy); calib_monitor (dispersion inverted for 7 reports — YES-taker correctly OFF, maker NO is the active structural edge candidate).

**Why this over all alternatives:** Gate 2 is the decision that unlocks every other NO-related action. The NO scale-up (§2a cap relaxation), breadth investigation, and co-fill strategy all require knowing whether Gate 2 is READY or REJECTED. Running the resolution join converts 12 days of passive accumulation into a binary decision in under an hour. The system cannot compound on the NO leg without this verdict; it can only repeat fills at the current cap-constrained pace.

The compounding impact × P(success) / effort calculation: P(Gate 2 READY) is moderate-high given aggregate +7.2% (n=97), but adverse fill could eat it — the experiment resolves this uncertainty. Effort: one terminal command on VPS.

**Concrete first step:**
```bash
# On QuantVPS Dublin:
python3 analysis/weather/band_resolution_join.py \
  --gate 2 \
  --since 2026-06-15 \
  2>&1 | tee /tmp/gate2_$(date -u +%Y%m%dT%H%MZ).log
```
If Gamma 403 persists on VPS (unlikely — VPS has direct access), fall back to CLOB `/data?condition_id=` for winner flags. Report CI95 result back to this branch via state_log entry.

---

## PROPOSED ACTIONS (human review — not implemented)

1. **[GATE 2 — URGENT, <1h, VPS]** Run `band_resolution_join.py` for BAND_NO_PAIR_FAV (n=105). Get CI95. Decision tree in §6 Experiment A.

2. **[GATE 5 — KILL CANDIDATE, VPS next evaluation]** THERMO_MAKER_NO: 0 fires 8+ days, CI upper +0.7%, unconfirmed 4th adverse fill pending. Declare REJECTED if Paris NO fill confirms adversely. No code change needed — BAND_TAILNO_VALIDATED=False already gates it OFF.

3. **[NO CAP — CONDITIONAL on Gate 2 READY]** Raise BAND_NO_CAP_FRAC 0.30→0.40 (cap $84.80 at current capital). +~$20/day NO capacity. Do not implement before Gate 2 verdict.

4. **[DATA INFRA — VPS, today]** Disk at 86% full — likely cause of daily mirror freeze at midnight. Clear old logs to create headroom. Risk: another freeze tonight will stall pnl_ledger again and mask Jun 20 P&L.

5. **[ISOTONIC CRON — VPS, low urgency]** Check if live-refit cron is active (n_live frozen 11 days). Do not deploy current candidate regardless — ceiling collapse from 0.63→0.37 worsens high-confidence calibration.

---

## NULL FINDING REGISTER

- **cash_preskip $134:** Correctly deployed in positions. Not idle. No action.
- **YES_MAX_OFF=2 wiring:** Verified working (12,200 off2 shadow legs). No action.
- **RECYCLE099:** Jun 19 $78.58 confirms active and scaling. No change warranted.
- **Kill-switch proximity:** Capital $211.59 vs $75 floor — safe, 182% margin. No halt.
- **Phase 1 no_resv=0.40:** Confirmed in STRUCT-BAND-Q 13:24-13:44 UTC. Reversed ladder deployed correctly.
- **Fee schedule:** No changes detected Jun 12-19. No action.

---

*Anti-sycophancy check: YES net = −4.9% (n=299, 2-week confounded). Clean window is 37h — too short for a verdict. Dispersion gauge has fired 7 consecutive alerts. The system may be sound as a maker-spread + favNO engine; it is NOT validated as a YES directional engine. Gate 2 is the one decision that changes this picture. Absent Gate 2 READY, the correct posture is: null day on strategy changes, collect data, run experiments.*
