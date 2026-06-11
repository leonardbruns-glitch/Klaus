# Klaus Research Audit — 2026-06-11T10:30Z

**Capital:** $91.77 | **Snapshot:** 2026-06-11T10:12:46Z (fresh, <18 min) | **Bot:** `active` (uptime since 2026-06-10 21:43 UTC)  
**Strategy:** STWA-ONLY (badatmath full mirror deployed 2026-06-10 21:43 UTC — current config baseline)  
**Data primacy note:** 214 of 216 resolved STWA trades are pre-Jun-9-21:55 oracle-integrity bugfix. Per standing rule, pre-fix losses are dead data and NOT cited as current expectancy below.

---

## DATA PRIMACY CHECK

**WEATHER_STWA resolved trades by config era (trades.jsonl):**

| Era | n | WR | PnL | Status |
|---|---|---|---|---|
| Pre-Jun-9 10:25 (pre-M1β) | 0 | — | — | Dead |
| Jun-9 10:25–21:55 (post-M1β, 3 oracle bugs present) | 214 | 35.6% | −$149.56 | Dead |
| Jun-9 21:55–Jun-10 21:43 (oracle-clean, pre-band) | 0 | — | — | No resolved fills |
| Jun-10 21:43+ (CURRENT CONFIG: d+0 live + fav-NO + oracle-clean) | 2 | 0% | −$1.72 | n=2, data-collection |

**Conclusion:** Current-config resolved data n=2 (both STRUCT_BAND losses at $0.63+$1.09 stake). EV/WR for the current config is unmeasurable. The 214 pre-fix records include three compounding oracle bugs (NWS5 contamination, midnight reset wipe, backfill-wipe) that produced false lockouts and should not be cited.

**WEATHER_M1_PROBE (pre-fix, all 31 trades):** WR=74.2%, net PnL=−$2.37, PF=0.97 on n=31 stake=$389.90. Near-breakeven despite false lockouts. Structure is correct; losses concentrated in high-ask entries during the oracle bug window (Jun-9 20:56 @ ask=0.813 is the identified KSFO NWS5 false lockout; Jun-9 21:20 @ ask=0.083 also suspect). DEAD DATA — informative only.

**Today's live activity (Jun-11 00:00–10:12 UTC, post-current-config):**
- RECYCLE099 exits: 6 fills, +$9.83 total (entries at 0.35, 0.69, 0.72, 0.74, 0.97, 0.99 → exits at 0.99/0.999). The 0.35-entry fill (+$5.50) is likely an oracle-clean M1β cheap-NO from Jun-10. Proof that exit mechanism is working.
- Band posts: 18 RESTING orders, $38.40 stake, 11 cities (Seoul, Wellington, Tokyo, Qingdao, SF, Beijing, Jeddah, Ankara, Moscow, Chengdu, Cape Town). 15 YES + 3 NO.
- M1β lockout candidates: 1,624 "both" (WS+REST) fires on 13 unique tokens. Depth: deep(≥0.5°C)=822, shallow(<0.2°C)=802. Zero thin-margin fires today.
- System telemetry: 0 queue drops, flush p50=1.85ms, RSS=865 MB. Healthy.

---

## SECTION 1: PRIMARY BOTTLENECK

**Bottleneck: Capital utilization (capital scale constraining fill breadth)**

Rank justification (frequency > coverage > fills > **capital-util** wins):
- Band capacity: today 18 resting orders at $38.40 stake. Badatmath at comparable config deploys ~$1,750 max working capital at 19% ROI = ~$332/mo. At $91.77 we project ~$17/mo band-edge if ROI transfers. The 10-19× gap is bankroll.
- Frequency is NOT the binding constraint: 602 sub-0.70-Σask shadow band candidates fire today, but the band only posts when it can collateralize. The rest waits on resolution recycle.
- Fill rate confirmed working: 6 RECYCLE099 exits today prove fills are landing. Cash recycling from the 0.35-entry position (+$5.50) is the right mechanism.
- The Jun-10 09:00 audit confirmed: free USDC ~$49.7, band posted $50.10 resting → Polymarket swept all 18 legs. The cash/breaker mismatch (MAKER_BREAKER_MAX_EXPOSURE_USD=150 > free USDC) was the confirmed failure mode.

**Annual $ impact:** At badatmath's observed ROI and $91.77 compounding to $200-400 by year-end vs $400-800 at 2× current capital, the bottleneck costs ~$50-150/yr in forgone compounding. Not fatal, but limits velocity.

---

## SECTION 2: EXISTING-SYSTEM OPTIMIZATION

### 2a. Dynamic band cash cap — HIGH priority
**Issue:** MAKER_BREAKER_MAX_EXPOSURE_USD=150 > free USDC causes full-surface sweep (all legs cancelled) when band over-quotes. Confirmed Jun-10 09:00. Today's 18 posts are RESTING (free USDC > $38.40 currently), but risk persists intraday as positions consume capital.  
**Fix:** Dynamic cap = `min(150, free_USDC * 0.9)` computed at band-post time from balance endpoint. Leg prioritization: d+2/lowest-Σ first.  
**Δtrade-count:** 0 (same legs). **Δexpectancy:** prevents ~1-4 full-surface wipes/month = recovers ~$15-40/month opportunity cost. **Confidence:** High. **Effort:** 30 min.

### 2b. On-chain MERGE recycling — MEDIUM priority
**Issue:** Band YES+NO fills accumulate; each redeems independently at resolution. CLOB `convertPositions` could pair them instantly and free USDC same-day (badatmath does ~6-7× recycle/wk via this mechanism). Not yet built per state log.  
**Δtrade-count:** 0 (same trades, faster recycle). **Annual $:** ~+$50-150 from compounding acceleration. **Confidence:** Medium (untested live). **Effort:** 2-4 hrs. Requires explicit user authorization.

### 2c. research_status.md is 26 days stale — LOW risk
**Issue:** `data/agent_context/research_status.md` last updated 2026-05-16, references LDA as active strategy. Scheduled agents (Scout, Auditor, Watchdog) will run wrong analysis against BOND/LDA schema. No live bot impact, but agent compute is wasted.  
**Fix:** Update to reflect STWA-only, current shadow loggers (metar_lockout, band_struct, thermo_maker, temporal_lock, count_lock), M1β monitor mandate. **Effort:** 30 min.

### 2d. Band d+0 fav-NO first fills — WATCH
**Status:** 3 NO posts today at ask 0.69–0.72 (Seoul, Wellington, Tokyo). First d+0 fav-NO resolution expected Jun-11 local midnight. band_resolution_join cron 09:45 is accumulating. No action; watch.

---

## SECTION 3: FREQUENCY EXPANSION

### 3a. PeakScalp (P5 temporal lock) — awaiting Phase 0 GO
**Status:** Proposed 2026-06-10 20:45; research complete; user chose badatmath mirror as priority. Shadow Phase 0 still untriggered.  
**Edge:** OOS WR=98.84% n=346 (gate=0.985), survivorship-free, model-free, calibration-free. Capacity: $350-598/day market-wide (EV-priced). Long tail of 40+ cities has no sub-obs-speed competitor.  
**Δtrade-count:** +3-8/day. **Annual $:** $50-200 at current capital. **Confidence:** High on edge, medium on fillability (Phase 0 test resolves this). **Effort for Phase 0 shadow:** 2-4 hrs.

### 3b. Cities — HK (VHHH), Singapore (WSSS), Tokyo (RJTT) unblocked
**Status:** All unblocked Jun-9 with oracle census verification. Live M1β monitoring VHHH via HKO feed (debounced 1-min). Impact: +5 fillable lockouts/day capacity confirmed for HK alone.

### 3c. Min-lockout family — SHADOW ONLY
**Status:** 16,452 records Jun-11 in metar_min_lockout.jsonl. Zero "both" fires today. Physics validated (temporal_lock_backtest.py). Oracle-provenance rule applies. Per user directive: shadow only until ≥2 weeks of snapshots. On track.

---

## SECTION 4: EXECUTION AUDIT

**Fill probability:**
- M1β: 1,624 "both" (WS+REST) fires on 13 unique tokens today. WS path + REST scan both operational. RECYCLE099 evidence confirms actual fills landing (6 exits today).
- Maker exercise: 2 records Jun-11 (Tokyo, no_bid=0.982/0.997, q_price=0.97/0.99). These are M1β deep-lockout maker mirrors where no_ask is already 0.985/0.999 — small delta from 1.0, appropriate not to post.
- Band: 18 posts, all RESTING. No balance sweeps today. Selective-cancel on restart confirmed working since Jun-10 08:35 (kept 15-17 tracked orders per deploy).

**RECYCLE099 performance today:** 6 fills at avg entry 0.743 → avg exit 0.990/0.999. Net +$9.83. The tick-aware 0.999 is working (one fill: entry=0.97, exit=0.999, +$0.054 on 5 shares).

**FillTracker PING:** No 60s-silence reconnect events since Jun-10 08:22. Confirmed healthy.

**NMS feeds:** obs_receipt 2,003 records Jun-11, 0 failures. Feed pipeline clean.

**Shadow telemetry (latest 10:12 UTC):** 0 drops, ~3,015 rows/min, queue 0.05% full, flush p50=1.85ms. No congestion.

---

## SECTION 5: ASSUMPTION ATTACK

### A1: Oracle provenance is clean post-Jun-9-21:55
**Load-bearing for:** Every M1β fill. A false lockout at ask=0.90 costs $9 on $10 stake.  
**Why it could be wrong:** Three separate oracle bugs found on a SINGLE day (Jun-9). Manila and Lucknow were recently added to the city set without the same oracle census depth as RJTT/WSSS. The Open-Meteo gridpoint proxy re-introduced 1-2°C false errors in minmax_coherence until fixed Jun-10.  
**Cheapest test:** Run oracle_census_blocked.py (60 resolved Gamma days vs IEM METAR) on Manila and Lucknow before any M1β live fills from those cities. 30 min/city. PA-3 below.

### A2: Band ROI from badatmath ground truth transfers to Klaus
**Load-bearing for:** BAND_LIVE=True being the right call at all.  
**Why it could be wrong:** (a) Mode-containment gate was missing in one execution path until Jun-10 00:05 — could have admitted -96% dist-1 legs in the cleanup period. (b) His MERGE recycling means his capital-ROI denominator is 6-7× smaller than ours at equivalent gross profit. Our apparent ROI/week at equal gross profit is lower.  
**Cheapest test:** band_resolution_join.py output at n≥100. Currently: n=2 post-current-config. ETA ~25 days at current fill rate.

### A3: RECYCLE099 maker asks get filled before resolution
**Load-bearing for:** The exit strategy. If asks queue behind competitors, cash stays tied up longer.  
**Why it could be wrong:** HighTempTation and Weatherstappen both rest 0.99 asks on convergence buckets (peak-window scalp, archetype confirmed Jun-9 22:00 research). They arrived at obs+1min vs our post-band posting. First-posted wins at equal price.  
**Cheapest test:** Monitor fill latency (post → fill ts) from user_ws.jsonl. Currently: 148 WS records today with no trade events parsed (schema gap — event_type field not populated). Recommend checking user_ws schema to confirm fills are logging correctly.

---

## SECTION 6: EXTEND EXISTING EDGE

### 6a. PeakScalp (P5) — highest ROI/effort, pending Phase 0
$350-598/day market-wide capacity (EV-priced), calibration-free, OOS-validated. Phase 0 shadow answers fillability in 3-5 days. The only edge that bypasses the capital constraint (small fixed stakes per city). P(Phase 0 confirms fillability) ≈ 70%.

### 6b. Min-lockout daily minimum — ongoing shadow
Daily minimum markets (100 open, confirmed Jun-9 22:00 venue scan). DNA identical to M1β: running_min monotonically non-increasing, dawn-lock is symmetric. 2 weeks of shadow data needed per directive. On track.

### 6c. NHC hurricane count-lock — research done, no GO
101 markets, $8.4M vol, fixed NHC advisory cadence. Same DNA as count-lock family (shadow-only per directive). User has not authorized shadow or live. **Annual $:** $10-50 (event-dependent, season June-November). Requires explicit authorization.

### 6d. Maker rebates accrual
Rebate rate: 25% of taker fees, paid daily pro-rata by `fee_equivalent = C · feeRate · p(1-p)`. Currently near zero (lifetime ~$10 band fills → cents below $1 floor). Will accrue at scale. No action now; passive.

---

## SECTION 7: PROPRIETARY EDGE RESEARCH

**Dense-obs forecast KILLED (Jun-9):** Coastal +3.1% improvement over market baseline = 10× below fee floor. The market is efficient on public NWP+official current temp. This door is closed.

**Only open proprietary edge:** PeakScalp information lag (obs → lockout → market lag 1-32 min). This is structural, not forecast-based. Already in the validation pipeline.

**UMA description-edit watcher:** P(edge) ≈ 20%. Most weather markets resolve mechanically without description changes. Cost of monitoring: non-trivial. Defer until another edge is exhausted.

**No new proprietary research warranted.** Compound the proven structural edges first.

---

## SECTION 8: EXPERIMENTS (3, exactly)

### E1: PeakScalp Phase 0 shadow (3-5 days)
**Hypothesis:** Our NMS feeds identify gate-pass (q ≥ 0.985) within T+1-5 min of obs, and the real book shows a YES ask ≤ 0.20 at T+0 for ≥50% of gate-pass events.  
**Data needed:** Shadow logger: (city, ts_gate_pass, q, real_yes_ask_T0, real_yes_ask_T1min, HighTempTation presence), joined to resolution 24h later.  
**Time:** 3-5 days shadow + 1 day analysis. **Cost:** Zero.  
**Success metric:** ≥50% of gate-pass events have fillable YES asks ≤ 0.20 at T+1 min, AND realized WR of those events ≥ 95%.  
**Decision-if-yes:** GO Phase 1 ($5 stakes, ≤3 concurrent, kill switch WR<95% over 50 fills).  
**Decision-if-no:** Defer PeakScalp; the latency window is narrower than model assumed.

### E2: Band resolution validator first 100 legs
**Hypothesis:** d+1/d+2 YES band bids resolve at ROI > 0 per badatmath ground truth (+14.4/+22.8%).  
**Data needed:** band_resolution_join.py output (cron 09:45, already running). Needs n≥100.  
**Time:** ~25 days at current fill rate. **Cost:** Zero (already running).  
**Success metric:** n≥100 resolved YES band legs, ROI > 0, lower 95% CI > 0.  
**Decision-if-yes:** Keep BAND_LIVE=True, increase stake and breadth.  
**Decision-if-no (ROI < 0):** Set BAND_LIVE=False; audit by days-out and city.

### E3: Post-fix M1β WR accumulation
**Hypothesis:** With all oracle bugs fixed (post Jun-9 21:55), M1β fills achieve ≥ 90% WR on resolved WEATHER_M1_PROBE entries.  
**Data needed:** trades.jsonl, filter `bond_entry_class == 'WEATHER_M1_PROBE'` AND `ts_open ≥ 1781042100`. Today n=0; needs ~20 days at current signal rate (~5 fires/day).  
**Time:** ~20 days. **Cost:** Zero (already live).  
**Success metric:** n≥40 post-fix M1β fills, WR ≥ 90%.  
**Decision-if-yes:** Confirm edge; proceed to thin-margin slice validation.  
**Decision-if-no (WR < 90%):** Audit by city and depth band; look for new oracle bug class in recently added cities.

---

## SECTION 9: SINGLE BEST ACTION

**Recommendation: Authorize PeakScalp Phase 0 shadow build (PA-1)**

**Why #1:**
1. Highest P(success) of any untried lever: OOS WR=98.84% n=346 is the only directional weather proof to pass n≥100 in this project. All other new edges are either shadow-only (min-lock, count-lock) or unvalidated.
2. Answers the key remaining question (fillability) in 3-5 days vs 20-25 days for M1β/band validation.
3. Zero capital risk (shadow-only Phase 0). Can run in parallel with band compounding and M1β accumulation.
4. Bypasses the capital bottleneck: Phase 1 is $5/city, fits within daily M1β budget.
5. Competition gap is real: HighTempTation covered 8/372 city-days = 2.2% of potential surface. We have feeds on 16 cities.

**Upside:** Phase 1 at $5/city × 3 concurrent × ~5 gates/day × 98.84% WR ≈ $3-8/day net added expectancy at current scale. Compounding: $91 → $120+ in 30 days with this running.  
**Confidence:** 70% Phase 0 clears; 50% Phase 1 reaches steady state.  
**First concrete step:** User types GO for Phase 0. Build shadow logger in weather_arb.py: on q-table gate-pass, log record to temporal_lock.jsonl with real-book snapshot. 2-4 hrs.

---

## M1β MONITOR — Thin-Margin [0.2, 0.5)°C Lockout Slice

**Mandate (deployed 2026-06-09 10:25):** MIN_DEPTH_C and FATEDGE_MIN_DEPTH_C lowered 0.5→0.2°C to admit thin-margin band. Backtest: 24/24 = 100% WR (n=24-28, explicit user override of n≥100 rule). WS fast-path widened to NO_ASK_MIN(0.05).

**Live thin-margin status — post-fix (ts_open ≥ 1781042100, Jun-9 21:55):**
- Resolved WEATHER_M1_PROBE trades: **n = 0** (zero fills have resolved post-bugfix)
- Today's metar_lockout depth distribution: shallow(<0.2°C)=802, deep(≥0.5°C)=822, **thin[0.2-0.5)°C = 0**
- Total WEATHER_M1_PROBE resolved lifetime (all pre-fix): n=31, WR=74.2%, net −$2.37

**Why zero thin-margin fires today:** Jun-11 00:00–10:12 UTC covers Asia/Pacific early morning and European morning. In these hours, official_running_max has not yet accumulated sufficiently above bucket ceilings in most mid-latitude cities (peak hours are 13-21 local). Thin-margin fires will appear in the 10-20 UTC window when US and EU peak hours run.

**DECISION: DATA-COLLECTION. n < 40 post-fix. No action on thin-margin slice. Report trend only.**

**Risk flag:** After 30 days, if thin-margin filled trade count remains < 5, the oracle provenance filter (official_running_max only, no ASOS fallback in [0.2,0.5)°C band) may be over-excluding. Audit the metar_lockout fill_path distribution for depth=[0.2,0.5)°C at US peak hours specifically.

---

## PROPOSED ACTIONS (human review required — REPORT-ONLY session)

| # | Action | Evidence | Risk | Effort |
|---|---|---|---|---|
| **PA-1** | **Authorize PeakScalp Phase 0 shadow** | OOS WR=98.84% n=346, zero capital cost | None | 2-4 hrs |
| **PA-2** | **Dynamic band cash cap**: `min(150, free_USDC * 0.9)` | Jun-10 09:00 full-surface sweep ($49.7 free, 18 legs swept) | Low | 30 min |
| **PA-3** | **Oracle census Manila and Lucknow** before any M1β live fills from those cities | Open-Meteo false 1-2°C errors found Jun-10 in minmax scan | Medium if skipped | 30 min/city |
| **PA-4** | **Update research_status.md** to STWA-only, current loggers | 26-day stale, scheduled agents running LDA schema | Low | 30 min |
| **PA-5** | **On-chain MERGE recycling** (convertPositions) | Badatmath 6-7× recycle confirmed; our band holds pairs to resolution | Low-medium | 2-4 hrs |
| **PA-6** | **User WS schema check**: confirm fill events are parsing (event_type field) | 148 WS records today, 0 trade events parsed — may be schema miss | Low | 15 min |

---

*Audit 2026-06-11T10:30Z. Primary bottleneck: capital utilization. Best action: PeakScalp Phase 0 (PA-1).*
