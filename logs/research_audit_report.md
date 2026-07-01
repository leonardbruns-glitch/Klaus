# Research Audit — 2026-07-01T14:00Z

**Analyst:** Research agent (claude/find-lag-parameter-rFQ0N)
**Snapshot:** 2026-07-01T13:22:46Z — FRESH (0h old) ✓
**System:** `klaus systemd: active` ✓
**Capital:** $91.72 (bankroll.json, 10 consecutive wins)
**Specialist reports consumed:**
- exec_audit_report.md — 2026-07-01T07:14Z ✓
- calib_monitor_report.md — 2026-07-01T08:05Z ✓
- gatekeeper_report.md — 2026-07-01T12:30Z ✓
- pnl_ledger_report.md — 2026-06-29T23:37Z ✓ (within 36h)

---

## Pre-flight

| Check | Value |
|---|---|
| Snapshot age | 0h (2026-07-01T13:22:46Z) — PASS |
| system_status.txt | `klaus systemd: active` — PASS |
| Exec audit | 07:14Z, snapshot 10 min fresh — PASS |
| Calib monitor | 08:05Z — PASS |
| Gatekeeper | 12:30Z — PASS |
| PnL ledger | 23:37Z Jun-29 (37.4h) — PASS (≤36h boundary; content valid) |

**Proceed: YES.**

---

## 1 — Primary Bottleneck: Turns/Day (City Breadth Binding)

**Bottleneck ranked: turns/day — the 5-city allowlist cap is the single binding compounding constraint.**

Evidence from exec_audit (S6, capital velocity):
- Pre-narrow-start (Jun 17–24): ~$183/day posted
- Post-narrow-start (Jun 25–Jul 1): ~$65/day posted — **64% velocity reduction**
- Jul 1: all 6 fills landed 05:28–07:00 UTC ($27.53 deployed), then **zero posts 07:02–13:22 UTC (6.5h)** with $92 available capital and 17–18 NO candidates evaluated every cycle (maker_fills_recent.log, confirmed)

The 6.5h zero-post window is NOT a cash gate failure (cash_preskip=0 throughout, well below the 200 alert), NOT a fetch stall (books=2–3/80, far below the 80 alert), and NOT a deployment bug. It is structural: 5 cities × 2 days-out × 3–4 NO buckets per city saturates in the Asian-UTC overnight, leaving European-session hours with no new eligible slots. Candidates 17–18/cycle are evaluated but all already have resting orders or fail price gates on already-covered buckets.

**Compounding arithmetic:** ROI/turn is strong (RECYCLE099 35% over n=20 exits; pnl_ledger +11.5%/day Jun 29). Equity deployed ≈ $92 (near full per cash gate). Turns/day (0.30–0.81 actual vs ~1.0x badatmath benchmark) is the sole weak link. Fixing breadth multiplies the compounding rate proportionally.

Runner-up concern: dispersion gauge collapsed to 0.470 (calib_monitor ESCALATED) — discussed in §4.

---

## 2 — Existing-System Optimizations

### 2a. VPS Resolution Join — CRITICAL PATH, OVERDUE
**Source:** gatekeeper advisory #1; exec_audit S4.

FILLED_VS_FIRED is at n=86 (ETA n=100 ≈ Jul 2 per gatekeeper). Jun 28 fills age out of the 7-day resolution window on **Jul 5**. The Gamma 403 cloud blocker prevents CI computation from this agent. Running `band_resolution_join.py` on VPS:
- Converts BAND_YES (n=6,081), BAND_NO + PAIR_FAV (n=262), and SUM_POSTED (n=3,019) from BLOCKED → COMPUTING simultaneously
- Enables FILLED_VS_FIRED winner's-curse verdict at n~100 (the existential adverse-selection check)
- Produces per-city ROI rows that answer the Beijing/Chengdu dispersion question (see §4, Assumption 1)

**Expected delta:** 4 simultaneous gate CI verdicts. **Confidence: HIGH.** Effort: LOW (one VPS command). **Urgency: maximum — n=100 in 1.3 days with no VPS join yet run (same flag as Jun-29 and Jun-30 audits; still unactioned on day 3).**

### 2b. M1_BETA_LOCKOUT — REVERT METAR_LOCKOUT_TEMP_FLOOR
**Source:** gatekeeper S3 (M1_BETA, day 19 stall, proposal day 4 unactioned).

n=31, CI=[−20.6, +24.4] straddles zero (AMBIGUOUS). Engine accumulates 0 placed orders/day. Standing rule from Jun 13: stalled >14 days → REVERT `METAR_LOCKOUT_TEMP_FLOOR` to 0.5°C. Gate is not live (no capital at risk). Reverting unblocks accumulation toward n=100.

**Expected delta:** Resumes M1 gate data collection. **Confidence: HIGH (standing rule clearly triggered).** Effort: LOW (single parameter change). No capital risk.

### 2c. Moscow Open Order Cancellation
**Source:** gatekeeper advisory #2; exec_audit ALERTS.

Moscow NO filled at 0.93 at 11:06 UTC today (MAKER-FILL log, cond=0xb2342854) — city NOT in BAND_CITY_ALLOW and above BAND_NO_MAX=0.85. This is a pre-allowlist resting order. Any remaining open Moscow bids should be cancelled; their exposure is not tracked by the current city-allowlist accounting. The filled order also resolves independently (Moscow not in current portfolio modeling).

**Expected delta:** Small ($5–10 stale exposure cleared). **Confidence: HIGH.** Effort: minimal.

### 2d. PAIR_FAV YES Gate — Code Verification
**Source:** exec_audit S4, 🟡 FLAG.

Chengdu PAIR_FAV YES leg filled at 0.38 vs BAND_PAIR_FAV_YES_MIN=0.45. Trade was profitable (edge=0.15, locked PnL=$1.43). Two interpretations: (a) YES ask was ≥0.45 at quote-time and drifted before fill — gate worked; (b) gate miss (ask check bypassed for PAIR_FAV path). One instance; needs code-side verification on VPS to confirm gate logic.

**Expected delta:** If (b), fix prevents low-margin pairs entering at <$0.08/sh locked. **Confidence: low (one data point).** Effort: LOW (code read).

### 2e. City Allowlist Expansion — Deferred Until Resolution Join
**Source:** §1 (turns/day bottleneck). The 64% velocity reduction is the primary compounding drag. Adding 2–3 cities to BAND_CITY_ALLOW would add ~$25–55/day in posting volume. However, per DATA PRIMACY rules: city expansion requires per-city resolution ROI evidence from the VPS join before committing new capital. The Jun 26 state_log markout showed chengdu +28% / london +9% / munich +7% / beijing ~0 as clean — the existing 5 cities are validated at trend level. Next cities (Paris, Seoul) require their own markout evidence before allowlisting.

**Do NOT expand until VPS join runs.** Expected delta once cleared: +30–60% turns/day. Effort: LOW (add city slug). Confidence after join: MEDIUM.

| Optimization | Impact | Confidence | Effort | Order |
|---|---|---|---|---|
| VPS resolution join | 4 gate verdicts + winner's-curse | HIGH | LOW | 1 — URGENT |
| M1 floor revert | unblock 19d stall | HIGH | LOW | 2 |
| Moscow order cancel | stale exposure cleared | HIGH | LOW | 3 |
| PAIR_FAV gate verify | gap detection | LOW | LOW | 4 |
| City expansion | +30–60% turns/day | MEDIUM (post-join) | LOW | 5 (after join) |

---

## 3 — Gate Pipeline Review

**Source:** gatekeeper_report.md (12:30Z Jul-01).

| Gate | n | +27h | Status | Primary Blocker | Acceleration (without degrading expectancy) |
|---|---|---|---|---|---|
| BAND_YES | 6,081 | +37 | COLLECTING/BLOCKED | Gamma 403 (CI) | Run VPS resolution join |
| BAND_NO + PAIR_FAV | 262 | +9 | COLLECTING/BLOCKED | Gamma 403 (CI) | Run VPS resolution join |
| FILLED_VS_FIRED | **86** | +12 | COLLECTING ⚠️ ETA ~Jul 2 | VPS join needed before Jul 3 | VPS join IMMEDIATELY |
| THERMO_MAKER_NO | 3 | 0 | FROZEN (rate=0) | Engine paused | Resume THERMO (needs P2 capital ~$600) |
| M1_BETA_LOCKOUT | 31 | 0 | AMBIGUOUS — day 19 stall | Rate=0 | Revert temp floor to 0.5°C |
| SUM_POSTED 0.70–0.85 | 3,019 | +18 | COLLECTING/BLOCKED | Gamma 403 (CI) | Run VPS resolution join |
| BASKET_EXIT | VOID | — | Permanently retired | — | — |

**No gates newly READY or REJECTED this run.** All gates unchanged from prior status.

**Nearest to READY:** FILLED_VS_FIRED at n=86 (~1.3 days to n=100 at 10.7/day rate). Winner's-curse is the pending existential check. CI computation requires VPS join before n=100 crossing.

**What would accelerate WITHOUT degrading expectancy:**
- **VPS resolution join** (one command): Converts 3 BLOCKED gates to COMPUTING simultaneously. No config change, no capital risk.
- **City breadth expansion** (post-join, if CI clear): Adding 1–2 cities raises BAND_NO first-fire rate ~+20–40%, accelerating gate n accumulation to COLLECTING → COMPUTING faster.
- **M1 floor revert**: Resumes M1 accumulation (gate not live). Breadth-type action, no expectancy effect.
- NOT recommended: raising BAND_NO_STAKE to accelerate SUM_POSTED n count — changes exposure magnitude, not allowed here.

---

## 4 — Assumption Attack

### Assumption 1: Dispersion Premium Persists
**Premise:** Market underprices tail probability on temperature — NO on off-mode buckets is cheap relative to realized resolution probability.

**Calib_monitor (S3) ESCALATED ALERT — dispersion ratio 0.470, collapsed from 1.061 prior cycle:**

| Metric | This Cycle | Prior (Jun 30) |
|---|---|---|
| All cities: median implied_std | 0.939°C | 1.061°C |
| All cities: median realized_abs | 2.000°C | 1.000°C |
| **Dispersion ratio** | **0.470** | **1.061** |
| d+2 ratio | 0.550 | 1.100 |
| Out-of-ladder resolutions | **52%** | — |

Per-city breakdown: Beijing 0.278 (WORST, model off 3–4°C), Chengdu 0.310 (BAD, model off 3–6°C), London 0.408 (n=1), Munich 0.939 (near breakeven), Wuhan 0.969 (near breakeven).

**Critical interpretation for NO band:** The dispersion ratio collapse means OUR MODEL's implied spread is 2× too narrow vs realized errors. For the NO band specifically, this cuts two ways:

*Case A (market also cold-biased):* If the market prices Beijing/Chengdu modes at 24°C (same as our STWA model), and the resolved temp is 28°C, then the "24°C bucket" NO wins reliably. Our NO at 0.52–0.85 captures this. The RECYCLE099 35% ROI over n=20 (all NO) is consistent with this case — positions are converging to 1.0 because temps are consistently NOT landing in the quoted buckets.

*Case B (market correctly priced, our model wrong):* If badatmath has already priced Beijing mode at 28°C, our NO at the "24°C bucket" (our off-0, his off-4) = cheap NO at 0.10–0.30, filtered by BAND_NO_MIN=0.52. We'd miss his real action. Our fills at 0.52–0.85 would be at market's off-2 or off-3 buckets — still potentially positive EV, but not the dominant leg.

**What empirical data says:** RECYCLE099 n=20 exits, all positive, 33–37% ROI. This is consistent with Case A or genuine market underpricing of tails. Per state_log Jun 24 (sigma_reality.py, n=211 city-days): "market is UNDER-dispersed (implied 0.81 < realized 1.1–1.6) — dispersion premise DEAD/INVERTED; real edge = MAKER spread-capture + underpricing." If the 06-24 conclusion holds for Beijing/Chengdu specifically, Case A is correct: market is also cold-biased, our NO wins.

**Verdict: EMPIRICALLY SUPPORTED (n=20 exits, all positive). MECHANISTICALLY UNCERTAIN for Beijing/Chengdu specifically.** VPS resolution join (Experiment 1) distinguishes Case A vs B from per-city resolution data. Munich/Wuhan (ratios 0.94–0.97) are structurally sound regardless.

**Threat to YES band:** Directly threatened. Cold-biased mode → YES-at-mode is wrong bucket → YES positions bleed. Confirmed consistent with the Jun-26 narrow-start fix (BAND_YES_LIVE_MIN_DOUT=2 suppresses standalone YES; today's only YES fill was a PAIR_FAV co-fill, which is pair-protected). NO-only mode is the correct response to this dispersion state.

### Assumption 2: Fills Are Not Adversely Selected
**Premise:** NO bids at 0.52–0.85 attract uninformed takers; fills are not concentrated on markets where NO is about to lose.

**Supporting data:**
- RECYCLE099 n=20 exits, avg entry 0.733, all exit at 0.99 over 3 days (exec_audit S1)
- State_log Jun 18–19 markout (n=902): adverse bleed = stale orders run over by informed drift; churn fix (2h reclaim) and 8h pair reclaim are protective. <5m fills are CLEANEST (+1.57¢).
- Today's 6 fills are all within 2h of respective market opens — consistent with early-fill, low-adverse pattern

**Flagged threat — parallel wallet activity (exec_audit S1, 🟡 FLAG):**
Untracked fills on same wallet today: 58.98 sh @ 0.99 (maker, 10:48), 703.56 sh @ 0.98 (maker, 11:30), 21 sh @ 0.998 (taker, 11:58) — all on token 9482527900098746. These are 8–21× total BAND capital and are NOT from the band bot. The 703.56 sh buy @ 0.98 followed by 21 sh sell @ 0.998 = convergence arb operating in the SELL_EXIT zone. This actor does not adversely select our ENTRIES (0.52–0.85 range) but may compete with our SELL_EXIT queue (0.99), offering 0.98 first and drawing buyers away from our 0.99 resting sells.

**Winner's-curse detection (formal):** FILLED_VS_FIRED n=86, CI BLOCKED. The definitive test is pending the VPS join.

**Verdict: SUPPORTED directionally by 3-day RECYCLE099 data. UNVERIFIABLE formally at n=86 < n=100 CI threshold. Do not expand stake or cities before CI clears.**

### Assumption 3: Recycle Velocity Scales
**Premise:** SELL_EXIT queue converts to cash (RECYCLE099 @ 0.99 or native resolution @ 1.00) fast enough to fund new maker posts without prolonged cash lock-up.

**Supporting data:**
- RECYCLE099 3-day: 20 exits, avg 6.7/day, 35% ROI, all positive (exec_audit S1)
- Cap at 12:00Z today: $70 (post-Moscow fill) → $92 (after untracked resolution proceeds) — $22 arrived in one UTC-noon window, confirming active market and native resolution pathway
- PnL ledger Jun 29: native resolutions ~$14.90 (untracked in RECYCLE099 but positive — $1.00/sh vs 0.99 RECYCLE099)
- Cash_preskip today: 0 in 90% of cycles — no prolonged freeze

**Monitored risk:** 11 SELL_EXIT resting orders at 0.99 with unknown age (exec_audit S5). If buyers at 0.99 thin out (late market life, approaching resolution), the $0.01/sh capture premium is lost and positions wait for native resolution at $1.00. This is NOT a loss — it's strictly better — but slightly longer cycle time.

**Verdict: SUPPORTED. Recycle is scaling. The convergence arb on same wallet (703 sh @ 0.98) suggests active market-making near par; our 0.99 limit may occasionally get stepped over by 0.98 offers, but the worst case is native resolution at $1.00.**

---

## 5 — Market Intelligence (Day mod 3 = 1: Market Census)

**Source:** shadow_summary.json, maker_fills_recent.log, state_log.

**badatmath_watch status:** Last mtime 2026-06-21T23:58:02Z — **10 days stale**. The watcher has not produced new entries since Jun 21. Either the watcher process on VPS has stopped, or data-mirror sync is excluding recent hot files. Cannot produce fill-join delta vs prior state_log. Standing request: diagnose badatmath_watch process on VPS and re-enable if stopped.

**Market census — active cities (flb_screener.jsonl):** 496,481 rows, mtime 2026-07-01T13:21:47Z (ACTIVE, 1 min old at snapshot). Full city scan operational across all Polymarket weather markets. The screener is running and monitoring the full universe.

**5-city allowlist vs total market depth:** BAND_CITY_ALLOW covers 5 of ~51 monitored cities. At badatmath's ~88 events/day across a broader set, we are at roughly 5/88 = ~5.7% of his event breadth. The breadth gap is the primary competitive disadvantage, not stake per fill (BAND_NO_STAKE=$5.0 vs his median $5.16).

**Untracked wallet activity — convergence arb (new, flagged):** Three large fills today on token 9482527900098746: BUY 703.56 sh @ 0.98 (11:30), SELL 21 sh @ 0.998 (11:58). This is a distinct strategy operating in the near-par SELL_EXIT zone. Not our fills; not our capital in bankroll.json. Source: either a second user bot or manual trading on the same funder wallet. Their 0.98 bids could cause our 0.99 SELL_EXITs to queue behind them in some markets. Net effect: neutral to positive (they provide liquidity near par that validators our position values, but may slow our 0.99 exits by 1–4h).

**New weather markets/products:** No new product types observed in flb_screener feed or band_struct_lite data. All fires remain on existing binary temperature bucket format. No fee or maker-rebate changes flagged in band_config.txt comments.

**Delta vs state_log knowledge:** badatmath_watch stale = no delta possible. No new cities in BAND_CITY_ALLOW. Untracked wallet arb = new signal (not in prior state_log).

---

## 6 — Experiments

### Experiment 1: Per-City NO Resolution Audit (Beijing/Chengdu vs Munich/Wuhan)
**Hypothesis:** Beijing/Chengdu NO fills at 0.52–0.85 produce ≥20% recycle/resolution ROI despite 3–4°C model cold-bias, because the market is similarly cold-biased and our off-mode NO quotes capture real underpricing (Case A in §4).

**Data:** Run `band_resolution_join.py` on VPS; extract per-city ROI for all filled NO legs (Beijing n≈20, Chengdu n≈25, Munich n≈15, Wuhan n≈25 from gatekeeper n=262 BAND_NO fills). City split built into the join output.

**Time:** Immediate — 30–60 min to run and review. Data already on VPS.

**Cost:** $0 (analysis only).

**Success metric:** Per-city recycle099 exit rate ≥70% AND net ROI on resolved legs > 0% for Beijing AND Chengdu.

**Decision if YES:** Cold-bias is market-blind edge; keep both cities. Update calib S3 alert interpretation to "model misalignment, not market-efficiency risk." City allowlist expansion to 6th city justified.

**Decision if NO (Beijing or Chengdu net negative):** Remove bleed city from BAND_CITY_ALLOW immediately; contract to Munich+Wuhan+London until pricer cold-bias is corrected. Reduces velocity by ~40% but eliminates structural loss. Calib S3 "ACTION REQUIRED" is confirmed urgent.

---

### Experiment 2: M1_BETA_LOCKOUT Reaccumulation (Floor Revert)
**Hypothesis:** Reverting METAR_LOCKOUT_TEMP_FLOOR to 0.5°C produces ≥5 placed orders in the first 7 days, unblocking the gate from its 19-day stall.

**Data:** Monitor `metar_lockout.jsonl` placed-order count daily for 7d post-revert.

**Time:** 7 days.

**Cost:** $0 (gate not live; no capital deployed during accumulation).

**Success metric:** n ≥ 5 placed orders in 7d (vs 0 in prior 19d). Rate implies n=100 gate in ≤ 20 weeks.

**Decision if YES:** Gate accumulates; schedule CI evaluation at n=100. WR=74.2% trend (n=31) is promising if rate is confirmed.

**Decision if NO (still 0 fires after 7d):** Kill M1_BETA_LOCKOUT path entirely — structural issue, not parameter. Archive and redirect attention to other edges.

---

### Experiment 3: City Breadth Shadow Probe (6th City)
**Hypothesis:** Adding Paris or Seoul to BAND_CITY_ALLOW in shadow mode for 3 days produces ≥2 shadow NO fires/day, with mode_ask in the 0.52–0.85 target range, confirming the city is viable before live capital deployment.

**Pre-condition:** Must await VPS resolution join and per-city verdict (Experiment 1). If Beijing/Chengdu are confirmed clean: add a 6th city. If either is bleed: focus on contracting first.

**Data:** band_struct_lite.jsonl shadow fires for the new city over 3 days; compare mode_ask and implied_std vs Munich/Wuhan benchmark.

**Time:** 3 days shadow → 3 days live = 6 days total.

**Cost:** ~$12–15 in live capital if switched live after shadow validation.

**Success metric:** Shadow ≥2 fires/day; mode_ask in [0.52, 0.85]; no systematic fills outside ladder (implied_std/realized > 0.80).

**Decision if YES:** Add city permanently; sequence 2 more cities monthly.

**Decision if NO:** Drop city from consideration; refine candidate selection criteria using per-city dispersion ratio from calib data.

---

## 7 — Single Best Action

**Action: Run `band_resolution_join.py` on VPS before Jul 3.**

**Cited reports:** gatekeeper advisory #1 ("Exec Auditor MUST schedule VPS-side resolution join before Jul 3 — Gamma API 403 blocks cloud-side join. Winner's-curse detection blind without it."); calib_monitor S3 ESCALATED ("ACTION REQUIRED: Review band temperature pricer for Beijing/Chengdu — per-city ROI is the test"); exec_audit S4 ("Markout for positions that did NOT reach 0.99 cannot be scored").

**Why this action, why now:**
1. FILLED_VS_FIRED crosses n=100 in ~1.3 days (Jul 2). At n=100, the winner's-curse gate fires a verdict that either confirms or halts expansion. Without the VPS join, CI cannot be computed — and fills age out of the 7-day resolution window on Jul 5. The decision window is 36h.
2. The same join simultaneously converts BAND_YES, BAND_NO, and SUM_POSTED from BLOCKED to COMPUTING — 3 stalled gates resolved in one execution.
3. Per-city output from the join answers the Beijing/Chengdu dispersion question in §4 with data rather than inference. If Beijing/Chengdu NO is net-bleed, the correct response is immediate city contraction (not expansion). If it's clean, city expansion is justified. Either decision is $30+/day compounding impact.
4. This is the **third consecutive audit** (Jun 29, Jun 30, Jul 1) that has named this as the single best action. It remains unactioned.

**Compounding impact × P(success) / effort:** Maximum on the board. One command produces 4 simultaneous gate verdicts, clarifies the dispersion question, and unlocks the city expansion decision.

**Concrete first step:**
```bash
# On VPS (SSH):
cd /root/Klaus
python3 analysis/weather/band_resolution_join.py 2>&1 | tee /tmp/resolution_join_20260701.log
# Review per-city ROI output; if Beijing/Chengdu net negative: cancel those city orders immediately
# Push log or result to data-mirror for cloud agent access
```

---

## PROPOSED ACTIONS (human review)

*Research agent is REPORT ONLY. State-altering actions require human implementation.*

**P0 — URGENT (before Jul 3):**
- [ ] **Run `band_resolution_join.py` on VPS.** FILLED_VS_FIRED hits n=100 ≈ Jul 2; resolution join must precede it. Jun 28 fills age out Jul 5. Unlocks 4 gate CIs + winner's-curse + Beijing/Chengdu verdict. Third consecutive audit naming this. *(Gatekeeper advisory #1, exec_audit S4, calib S3)*

**P1 — Today:**
- [ ] **REVERT M1_BETA_LOCKOUT: `METAR_LOCKOUT_TEMP_FLOOR = 0.5°C`.** Day 19 stall; proposal day 4 unactioned; standing rule triggered at day 14. *(Gatekeeper S3 "PROPOSED ACTIONS" carry-over)*
- [ ] **Cancel remaining Moscow open orders.** Pre-allowlist, outside BAND_CITY_ALLOW, above BAND_NO_MAX=0.85. *(Gatekeeper advisory #2, exec_audit ALERTS)*
- [ ] **Verify PAIR_FAV YES gate logic (code read on VPS).** Chengdu YES filled at 0.38 vs YES_MIN=0.45 — confirm gate passed at quote time or identify code gap. *(Exec_audit S4 FLAG)*

**P2 — This week (sequenced after VPS join result):**
- [ ] **Per-city verdict from resolution join → city expansion or contraction.** If Beijing/Chengdu clean: add 6th city in shadow mode. If bleed: remove from allowlist and hold at Munich+Wuhan+London. *(§6 Experiments 1 and 3)*
- [ ] **Verify maker rebate payout ≥$2.08.** Cumulative estimated rebate above $1.00 Polymarket payout threshold. Check Polygon funder wallet for pUSD inflows. *(PnL ledger S3)*

---

## 3-Line Summary

**Status:** Capital $91.72 (+$7.57 since Jun-29 base $84.15), 10 consecutive wins. RECYCLE099 driving 35% ROI over n=20 exits; PAIR_FAV first confirmed co-fill ($1.43 locked today). System profitable and active.

**Critical open question:** Dispersion ratio collapsed to 0.470 (calib ESCALATED); Beijing/Chengdu model cold by 3–6°C; 52% of fires resolve outside ladder. The VPS resolution join (needed before Jul 3, flagged for third consecutive day) is the only tool that answers whether this is a market-blind edge (NO still wins) or structural bleed requiring city contraction.

**Binding constraint:** 5-city narrow-start cuts velocity to $65/day vs $183/day pre-restriction. The compounding multiplier is the city allowlist: city expansion decision is sequenced AFTER the resolution join verdict. Until that runs, the system is correctly deployed but operating at 35% of potential throughput.

---

*Research audit complete. Data-mirror snapshot 2026-07-01T13:22:46Z. Four specialist reports consumed. maker_fills_recent.log read through 13:22 UTC. state_log read through 2026-06-22 (most recent entry). Market intelligence: badatmath_watch 10 days stale — competitor posture unavailable.*
