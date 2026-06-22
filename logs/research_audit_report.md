# Klaus Research Audit — 2026-06-22
**Generated:** 2026-06-22T11:36Z  
**Snapshot freshness:** exec_audit cites 2026-06-22T06:57Z (<15 min at run time); calib_monitor cites 2026-06-22T07:57Z (13 min at run time); gatekeeper cites snapshot age 0.2h (FRESH). `data-mirror` branch absent from remote; freshness confirmed via specialist reports, all of which confirm `klaus systemd: active`. Capital: $232.59 (gatekeeper, 09:11 UTC).  
**Specialist reports consumed:** exec_audit (07:07 UTC, Jun22 ✓), calib_monitor (08:10 UTC, Jun22 ✓), gatekeeper (09:11 UTC, Jun22 ✓), pnl_ledger (23:37 UTC Jun21 — 12h old ✓, within 36h gate).  
**Day-of-month mod 3:** 22 mod 3 = 1 → **Market intelligence: Market census (new cities/products, depth changes)**

---

## 1. PRIMARY BOTTLENECK: DATA — Gate 2 CI blockage (BAND_NO running blind at $5/stake, day 3 past n=100)

**Verdict:** The compounding equation is not primarily blocked by turns/day or ROI/turn today. It is blocked by an **information vacuum at the system's highest-dollar deployment stream.** Gate 2 (BAND_NO_PAIR_FAV) crossed n=100 on Jun20 and has now completed **two consecutive gatekeeper runs** (n=128 → n=144) above threshold without a CI verdict. BAND_NO is LIVE at $5/stake. The NO side is **42% of all fill dollars ($265 of $397, 7d)** per exec_audit. This is not a data-collection situation — n=144 exceeds the decision threshold and the join is structurally blocked by Gamma 403 from container, requiring VPS execution. Every day this runs blind accumulates ~14 more NO positions at $5/stake without validation.

**Why not ROI/turn or turns/day?**
- Jun21 P&L was +$37.93 (+19.0%) with RECYCLE099 at 2.47× resolution drag (pnl_ledger). ROI/turn recovered from Jun20's negative session.
- Turns/day (0.55–0.67) is below the 1.0 badatmath benchmark but improving (Jun21 was the highest fill day: 82 fills, $154.9). Not acutely blocked.
- Equity: $232.59 cash + $593 SELL_EXIT resting (50 positions at ~0.99). Capital deployment is functioning.

**The risk to continued compounding is structural, not operational:** if BAND_NO held-to-resolution EV is negative (exec_audit proxy shows 42% WR on 0.50–0.85 entry vs 63% break-even; this pool is biased toward losers by RECYCLE099 exits, but the direction is concerning), the NO resolution drag will erode RECYCLE099 gains on days with high NO resolution volume. Gate 2's CI verdict determines whether BAND_NO should hold at $5, reduce, or halt.

---

## 2. EXISTING-SYSTEM OPTIMIZATION

### A. Gate 2 VPS resolution join [URGENT, 3rd consecutive recommendation]
**Finding (gatekeeper):** n=144, 2nd consecutive run above n=100 with CI blocked by Gamma 403. BAND_NO_ENABLED=True, BAND_NO_STAKE=$5 LIVE.  
**Expected delta:** Binary decision with immediate capital consequence. CI95 lower > 0 → NO validated, hold $5; CI spans zero → reduce stake to $2 immediately; CI upper < 0 → disable BAND_NO_ENABLED.  
**Confidence:** High (data exists on VPS, join algorithm exists). **Effort:** ~1h VPS run.

### B. Dispersion gauge reference audit [NEW, HIGH information value]
**Finding (calib_monitor):** The 1.3°C reference in CLAUDE.md yields disp_ratio = 0.928/1.3 = **0.714** → edge inverted (alert day 3+). But the **data-derived true sigma from 149 settled city-days = 0.961°C**. Against this empirical baseline, the ratio is 0.928/0.961 = **0.966** — approximately parity, NOT inverted. The critical assumption "market prices narrower than true volatility" depends entirely on which baseline is correct.  
**Expected delta:** If 0.961°C is the correct reference, the continuous DISPERSION_ALERT may be based on a stale benchmark, and the YES band edge is approximately neutral (not −30% inverted as currently implied). This would change the framing of the Jun20 loss and Jun21 recovery substantially.  
**Confidence:** Medium (methodology question — need to understand how the 1.3°C reference was originally derived). **Effort:** ~30 min VPS query on stwa_city_state.json or original calibration scripts.

### C. Bot restart reliability [WATCH]
**Finding (pnl_ledger):** Bot restarted at 16:38 UTC Jun21. 72 RESTING orders placed after restart; no fills yet at 23:37. The exec_audit Jun22 07:00 snapshot shows only 8 fills ($15.2) for the day — consistent with early morning and post-restart catchup still running.  
**Risk:** If the restart gap caused inventory depletion in the SELL_EXIT queue, Jun22 RECYCLE099 throughput may be lower. The $593 SELL_EXIT resting (50 positions) as of 07:00 suggests inventory is NOT depleted — these are from pre-restart positions queued at 0.99.  
**Action:** Monitor Jun22 EOD fills vs Jun21 EOD (82 fills/$154.9). If <40 fills/$60 by 16:00 UTC, investigate root cause.

### D. Ghost quotes cleanup [LOW priority]
**Finding (exec_audit):** 9 entry orders >48h (threshold: 20 before alert). Oldest = 113.7h on Moscow Jun17–18 resolved market (99.8% matched = ghost). Not consuming live capital but polluting book scan (BAND_RECLAIM_AGE_S=2h should have cleaned these).  
**Expected delta:** Minor — frees book slot count clarity. Monitor vs 20 threshold.

### E. Isotonic refit [DEFERRED from Jun21]
**Finding (calib_monitor):** Deployed isotonic 16 days old; no fresher candidate in 13 days. Do NOT deploy candidate (ceiling moves wrong direction: 0.6316 → 0.3739 at p_raw=1.0; ECE confirms p_cal ≈ 0.63 rows have 99.1% actual win rate). Fresh refit needed, not promotion.  
**Unchanged from Jun21 recommendation. Effort:** ~30 min VPS cron trigger.

---

## 3. GATE PIPELINE

| Gate | n | +24h | Status | ETA | Accelerator |
|---|---|---|---|---|---|
| 4. BASKET_EXIT | 33 | +17 | **VOID (retired)** | Gate dead | None — 4 fatal flaws (see below) |
| 2. BAND_NO_PAIR_FAV | 144 | +16 | COLLECTING ★★n≥100 (day 3) | **BLOCKED** | VPS: `band_resolution_join.py --reason fire_no pair_fav pair_samebucket --start 2026-06-19T00:30` |
| 3. FILLED_VS_FIRED | 110 | +2 | COLLECTING | BLOCKED (VPS CID join) | Jun18 fills age out in ~4d — time-sensitive |
| 1. BAND_YES | 5,419 | +265 | COLLECTING | BLOCKED (Gamma 403) | Same VPS join as Gate 2; ~235 legs/day |
| 7. SUM_POSTED [0.70,0.85] | 2,643 | +170 | COLLECTING | BLOCKED (Gamma 403) | Same VPS join; fraction of YES fires rising 47%→68% post-Jun18 config |
| 5. THERMO_MAKER_NO | 3 | +0 | STALLED (day 10+) | INFINITE | Diagnose phase-lock: BAND_NO_MAX=0.85 + BAND_TAILNO_VALIDATED=False likely blocks all 9,099 candidates |
| 6. M1_BETA_LOCKOUT | 31 | +0 | STALLED (day 12+) | INFINITE | Provenance unverified; VPS reset to n=1 if unverifiable |

**Gate 4 VOID:** State_log 2026-06-22T07:35 declared Gate 4 fatally flawed on four independent grounds: (1) WR=100% tautological (all_green defined as cash>cost by construction); (2) 18/19 closers are n_legs=1 single YES legs — RECYCLE099 relabeled as baskets; (3) CI internally inconsistent (prior CI[+11.5%,+34%] incompatible with Denver +3087%/Beijing +509% outliers in n=16; on n=33 verified baskets CI = [−45.1%, +336.1%] straddles zero); (4) wrong metric (exit-vs-cost, not exit-vs-hold; cash/max_hold median = 0.920, holding always pays more). Gate 4 is NOT nearest-READY; it is dead.

**Nearest actionable gate:** Gate 2 (n=144, data exists on VPS, join runnable today). All other blockages are the same VPS-side Gamma join. No gate is near READY without the VPS run.

**Accelerating data accumulation without degrading expectancy:**
- Gates 1 and 7 are accumulating at 235 and 155 legs/day respectively. No change needed; rate is healthy.
- Gate 3 is time-sensitive (Jun18 fills age out in ~4 days). VPS join needed before the window closes.
- Gates 5 and 6 cannot accumulate more data without resolving the phase-lock/route issue.

---

## 4. ASSUMPTION ATTACK

### Assumption A: Dispersion premium persists (YES band edge)
**Status: INVERTED per current reference (0.714), BUT reference may be stale.**

Today's calib_monitor data:
- Market-implied PRE_PEAK sigma: **0.928°C** (n=16 cities, 08:10 UTC)
- CLAUDE.md reference: 1.3°C → ratio = **0.714** (alert fires, edge inverted)
- **Data-derived true sigma (n=149 settled city-days): 0.961°C** → ratio = **0.966** (≈ parity, no alert)

The dispersion alert has fired continuously for 3+ sessions. The ratio is recovering (+0.043/day: 0.584→0.671→0.714). BUT: the critical question is whether the 1.3°C reference is empirically correct. The 0.961°C data-derived value suggests the market may be pricing volatility close to realized, not below it. Until the reference is audited against its original derivation, the gauge is ambiguous.

Positive signal: **Cape Town (1.080°C), London (1.051°C), Kuala Lumpur (1.029°C)** exceed the data-derived reference of 0.961. These 3 PRE_PEAK cities show implied sigma above realized — i.e., the dispersion PREMIUM is present for these cities specifically. This is the edge for yes-band posts in those markets.

ECE bin [0.2, 0.3): actual win rate 16.3% vs model p_cal 25.1% — shoulder over-prediction by **8.5pp** (calib_monitor). This is the structural YES-shoulder drag: the model overstates shoulder probability, placing bids where the market is more efficiently priced than we assume.

### Assumption B: Fills are not adversely selected
**Status: SUPPORTED by current data (fills and exit099).**

exec_audit finding: fill rate 80–98% (Jun19–21), exit099 PnL +$425 across 94 exits in 6 days, NO-share recovering to 44% (Jun21). Specifically:
- If adverse selection were systematic, fill rate would be LOW (takers cherry-pick our best quotes). Observed 80–98% indicates indiscriminate market clearing.
- exit099 by price band: 0.50–0.85 (NO) generates +63% avg ROI on 23 exits → NO positions successfully converging.
- n=214 fills in 7d at 42% NO share matches posting ratio → no side-specific cherry-picking.

The held-to-resolution proxy (42% WR on 0.50–0.85, break-even 63%) is a biased sample (winners exit via RECYCLE099 before resolution). Not a winner's-curse signal per se, but confirms the resolve-vs-exit decision is structurally important.

**Inconclusive flag remains:** Gate 3 (FILLED_VS_FIRED, n=110) cannot compute authoritative fill-vs-all-fires ROI without VPS join. Circumstantial evidence leans against adverse selection, but definitional verification requires VPS.

### Assumption C: RECYCLE099 velocity scales with deployed capital
**Status: SUPPORTED — dominant positive engine confirmed on Jun21.**

pnl_ledger: Jun21 RECYCLE099 = +$114.77 (15 exits) vs resolution drag = −$46.45 (27 resolutions). Ratio 2.47×. Directional breakdown by entry band from exec_audit: YES cheap-tail (0.10–0.30) produces highest ROI/turn (+428% on n=37 exits), NO favorites (0.50–0.85) produce +63% on n=23 exits. Both streams feed RECYCLE099.

**Threatening sub-assumption:** RECYCLE099 inventory depends on the band posting rate. Bot restart at 16:38 UTC Jun21 created a book-darkening gap, but $593 SELL_EXIT resting at 07:00 Jun22 shows pre-restart inventory is still queued. New inventory (72 posts after restart) is resting but unfilled as of late Jun21.

**Key risk signal:** If Jun22 exit099 throughput is significantly below Jun21 baseline (14 exits/$76 baseline → target ≥10 exits/$50 by 16:00 UTC), book replenishment is lagging. Jun22 partial: only 2 exit099 exits ($8.37) in first 7 hours — early morning exit rate is always lower; not yet concerning.

---

## 5. MARKET INTELLIGENCE: Market Census (day mod 3 = 1)

**Scope:** Depth changes in our 51 cities; new weather products on Gamma. Container cannot query Gamma API (network restricted). Working from available shadow data.

### Depth monitor (51-city book)

From exec_audit queue health (avg_books/80, active books per cycle):

| Date | avg_books/80 | max_books | avg_yes/50 | max_yes | Headroom |
|---|---|---|---|---|---|
| Jun 19 | 0.4 | 4 | 0.2 | 2 | 95% |
| Jun 20 | 0.4 | 8 | 0.2 | 4 | 90% |
| Jun 21 | 0.4 | 12 | 0.2 | 6 | 85% |
| Jun 22 (07:00) | 0.2 | 7 | 0.1 | 4 | 91% |

Depth is stable. Max books trended up Jun19→Jun21 (4→8→12) consistent with inventory buildup; Jun22 early morning at 7 (partial day, pre-peak). **The 51-city book has ~85–95% headroom — not near capacity saturation.** Posting capacity is not a limiting factor.

Jun21 avg_posted/cycle spike (1.2 vs 0.2 baseline) was a post-restart burst: 349 total posts vs 47–50 on normal days. This confirms the bot can post significantly faster when qualifying markets are available in bulk — the constraint is market availability, not posting throughput.

### New cities / products

From Jun21 WEATHER_MAKER resolutions: Chengdu, Chongqing, Dallas, Houston, Seoul, Taipei, Tokyo — all known 51-city markets. No new cities appeared in fill tape or resolution data.

YES fires rate stable at ~230–260/day (Gate 1); SUM_POSTED [0.70,0.85] fraction rising 47%→68% over Jun17–22 (Gate 7) — this reflects the post-Jun18 PX_CEIL 0.30 config filtering out high-price YES more aggressively, not new cities entering.

**Delta vs prior knowledge:** No new cities or product lines identified from available data. To confirm no Gamma additions in the last 7 days, VPS operator should run:  
```
python3 analysis/weather/gamma_market_scan.py --check-new-cities --since 2026-06-15
```
If new cities are present, they represent free additional qualifying markets that improve turns/day at zero configuration cost.

### Depth quality note
The exec_audit YES fill distribution shows 39 fills in the <0.10 band (all YES, $21.84 in 7d) — these are extreme-tail YES positions (single-digit cent bids). These represent the lowest-probability YES legs that almost never win at resolution but occasionally become RECYCLE099 exits at extreme ROI (ex: n=3 exit099 in <0.10 band at +1783% avg ROI). The depth in this band is real but the per-fill dollar is low ($0.56 avg). No depth concern.

---

## 6. THREE EXPERIMENTS

### Experiment 1: Gate 2 VPS Resolution Join (carried from Jun21 — still unactioned)
**Hypothesis:** BAND_NO_PAIR_FAV legs (fire_no/pair_fav, post-Jun19T00:30 clean window) have ROI > 0% with CI95 lower bound > 0.  
**Data:** Gamma winner flags for ~144 NO legs in band_struct_lite.jsonl. Band_resolution_join.py exists on VPS.  
**Time:** Same day (VPS run). **Cost:** Zero.  
**Success metric:** CI95 lower > 0 → READY; spans zero → AMBIGUOUS (reduce stake); upper < 0 → REJECTED (disable BAND_NO_ENABLED).  
**Decision-yes:** Hold BAND_NO at $5/stake; continue current queue priority (d+1-NO-first).  
**Decision-no:** Cut BAND_NO_STAKE from $5 to $1 immediately; diagnose whether NO edge is inverted on current markets or only on pre-clean-window data.

### Experiment 2: Dispersion Reference Calibration (NEW)
**Hypothesis:** The CLAUDE.md 1.3°C sigma reference is overstated. Data-derived true sigma (0.961°C, n=149 settled city-days) is the empirically correct baseline, meaning the YES band edge is approximately neutral (not inverted by ~30%) at current implied sigma of 0.928°C.  
**Data:** Original source derivation of the 1.3°C reference (likely stwa_city_state.json or a prior research note). Compare methodology: std(final_max − mode_center) vs whatever metric the 1.3°C was derived from. Also check seasonal variation — 1.3°C may be winter calibrated (wider natural spread), not summer.  
**Time:** 1–2h VPS analysis. **Cost:** Zero.  
**Success metric:** If original derivation method matches the data-derived method AND data-derived sigma ≠ 1.3°C by >0.2°C, update the reference in calib_monitor_state.json and re-evaluate alert threshold. If original derivation method is different (e.g., 30-day climatological spread vs resolution deviation), the two values are measuring different things and both may be correct for their purpose.  
**Decision-yes:** Update reference to 0.961°C; current ratio 0.966 is neutral → DISPERSION_ALERT suspends; YES band posting continues without the structural headwind framing.  
**Decision-no:** 1.3°C reference is correct for the relevant metric → dispersion truly inverted; YES band shoulder posting is structurally at a disadvantage; consider per-city dispersion gate (post only cities with implied σ ≥ 1.0°C: Cape Town, London, Kuala Lumpur, Warsaw, Jeddah, Moscow).

### Experiment 3: Per-City Dispersion Stratification (conditional on Exp 2 verdict)
**Hypothesis:** YES band resolution WR and RECYCLE099 capture rate are higher for cities where implied sigma ≥ 0.961°C (the data-derived true sigma) than for low-sigma cities (<0.8°C).  
**Data:** Join calib_monitor_state sigma per city vs band_resolution_join.py YES WR per city (requires same VPS run as Gate 1). Today's PRE_PEAK high-sigma cities: Cape Town (1.08), London (1.05), Kuala Lumpur (1.03), Warsaw (0.98), Jeddah (0.97), Moscow (0.96). Low-sigma: Lucknow (0.646), Tel Aviv (0.719), Amsterdam (0.761).  
**Time:** Dependent on Gate 1 resolution join (same VPS run). **Cost:** Zero.  
**Success metric:** High-sigma YES WR ≥ 1.5× low-sigma WR on n≥30 per bucket.  
**Decision-yes:** Implement per-city dispersion filter: YES posting only when city implied sigma ≥ 0.90°C (would keep ~10 of 16 PRE_PEAK cities). Reduces YES posting breadth by ~38% but concentrates capital in cities with confirmed edge.  
**Decision-no:** City-level sigma has no predictive power for YES WR → dispersion route is not the edge signal; continue posting all 51 cities at current config.

---

## 7. SINGLE BEST ACTION

**Run the Gate 2 VPS resolution join for BAND_NO_PAIR_FAV legs. This is the third consecutive session where this action has been the #1 recommendation and remains unactioned.**

**Why Gate 2 and not the dispersion reference audit:**  
The dispersion reference question (Exp 2) is strategically important but has no immediate capital consequence — YES posting continues either way. Gate 2 has an immediate, direct capital consequence: $5/stake × ~14 NO fires/day = ~$70/day deployed without validated edge. At n=144 with 3 days of post-threshold accumulation, every additional day adds resolution exposure to unvalidated positions.

**Supporting citations:**
- **Gatekeeper:** "BAND_NO_ENABLED=True, BAND_NO_STAKE=$5 LIVE. 2nd consecutive run above n=100 with no CI verdict — urgent."
- **Exec_audit:** NO fills = 42% of all fill dollars ($265/$397 in 7d); NO entry band 0.50–0.85 fully separated from YES (<0.30) — system is functioning as designed; validation is the only missing piece.
- **Calib_monitor:** Calibration is improving (Brier 0.0475, ECE 0.0255), meaning resolution truth is becoming more reliable for the join. The join result will be cleaner today than it would have been 3 days ago.
- **pnl_ledger:** Jun21 WEATHER_MAKER NO: 4/20 WR = 20%. This includes pre-clean-window legs; post-Jun19T00:30 legacy data must be excluded. The join's clean-window enforcement is critical.

**Concrete first step:**
```bash
# On VPS
python3 analysis/weather/band_resolution_join.py \
  --start 2026-06-19T00:30 \
  --reason fire_no pair_fav pair_samebucket \
  --min-n 30
# Post CI95 output to state_log with timestamp
```

---

## PROPOSED ACTIONS (human review)

**[P1 — URGENT, day 3, zero capital risk]** Gate 2 VPS resolution join. Run `band_resolution_join.py --start 2026-06-19T00:30 --reason fire_no pair_fav pair_samebucket`. CI branches: lower>0 → validated (hold $5 stake); spans zero → reduce BAND_NO_STAKE from $5 to $2 immediately; upper<0 → set BAND_NO_ENABLED=False. Decision must happen today — n is now large enough that each delay adds funded risk, not useful data.

**[P2 — HIGH information value, 1–2h VPS]** Audit the 1.3°C dispersion reference origin. If the data-derived method (std of final_max−mode_center on 149 settled city-days = 0.961°C) matches the reference derivation method, update the calib_monitor threshold and re-evaluate the DISPERSION_ALERT. If it's a different measurement, clarify what each measures and whether both belong in the monitor.

**[P3 — ADMIN, no code change]** Formally close Gate 4 in gatekeeper ledger. State_log declared it VOID on Jun22 07:35 with 4 fatal flaws. Remove from active-experiment count. gatekeeper_state.json already reflects VOID status; confirm human sign-off so the ledger isn't counted as "6 active gates" when it's 5+1void.

**[P4 — LOW effort, data quality, time-sensitive]** Gate 3 filled-vs-fired join on VPS before Jun18 fills age out (~4 days). n=110 fills (YES=66, NO=44). Join per (token, side) to all-fires per slice for winner's-curse verdict.

**[P5 — LOW effort, competitor visibility]** Restart badatmath_watch shadow logger. Fill tape dark since Jun11 (11 days). Without visibility, cannot detect if badatmath has changed city coverage, YES ceiling, or NO composition since Jun12.

**[P6 — WATCH, no action]** Dispersion ratio: 0.714 (+0.043 from Jun21, improving for 3rd session). At current recovery rate (~0.04/day), ratio reaches 1.0 in ~7 days. Do NOT act on this alone — a single-session reversal is possible (Jun14 spike 0.620→0.835 reversed immediately). Requires confirmation from Exp 2 reference audit before any YES posting changes.

**[NO CHANGE]** BAND_YES config (PX_CEIL=0.30, BAND_YES_MAX_OFF=2, strict-rank queue, BAND_BASE_STAKE=$3): frozen from Jun19T00:30 clean-window. Gates 1 and 7 blocked on Gamma 403. Hold ≥2 more days minimum.

**[NO CHANGE]** Capital above all kill-switch floors by wide margin ($232.59 vs $50 ruin floor, $75 weekly floor). Rolling20 WR/PF metrics are inapplicable to maker YES architecture (20% WR is by design on cheap-tail bids; taker-era thresholds don't apply). No halt or stake reduction warranted.

---

*All claims sourced from: exec_audit (07:07 UTC Jun22), calib_monitor (08:10 UTC Jun22), gatekeeper (09:11 UTC Jun22), pnl_ledger (23:37 UTC Jun21), gatekeeper_state.json, calib_monitor_state.json, pnl_ledger_state.json — all read this session. `data-mirror` branch absent; freshness verified via specialist report timestamps. No speculation from n<40 data. Gate 4 void per state_log 2026-06-22T07:35. Report agent: REPORT-ONLY, no strategy code or gate parameters modified.*
