# Klaus Research Audit — 2026-07-06T10:30Z

**Date:** 2026-07-06 | **Snapshot:** 2026-07-06T10:15:16Z (fresh ✓, ~15min at analysis time) | **System:** `active` ✓  
**Bankroll:** $141.74 cash (bankroll.json 10:09Z) | **Daily start:** $217.44 | **Consecutive wins:** 7 | **Open positions:** 0 (gatekeeper 09:10Z)  
**Active engines:** PAIR_FAV only (BAND_NO disabled 07-02; standalone YES paused BAND_YES_LIVE_MIN_DOUT=9 since 07-03; clip-guard deployed 07-05 22:20Z)  
**Market intelligence rotation:** Day 6 → 6 mod 3 = **0** → competitor posture

**Specialist report freshness:**
| Report | Timestamp | Age at this run | Status |
|---|---|---|---|
| exec_audit_report.md | 08:29Z | 1.7h | ✓ |
| calib_monitor_report.md | 07:58Z | 2.3h | ✓ |
| gatekeeper_report.md | 09:10Z | 1.3h | ✓ |
| pnl_ledger_report.md | Jul05 23:37Z | ~11h | ✓ within 36h |

**State_log conflict resolution:** EVOLVE weekly (07-05 22:25) classified isotonic refit cron as "NOT-broken (guard held legitimately: cal_days 10<14, OOS Brier worse)". This resolves the calib_monitor's "27-day inactive" reading. The cron runs but correctly rejects candidates on OOS validation. Root constraint is insufficient calibration data (cal_days 10 < 14 threshold), not a broken cron. The dispersion gauge plateau cannot be resolved until the OOS guard passes a new candidate.

---

## §1 — Primary Bottleneck

**DISPERSION EDGE DECAY** — confirmed by all four reports, corroborated by competitor data.

Full ranking:
- ✅ Equity deployed: $141.74 — adequate for current output; NOT the bottleneck
- ⚠ Turns/day: 0.39 — deliberately low (correct given edge state; see §5 — badatmath benchmark is VOID)
- ❌ ROI/turn: unmeasurable (PAIR_FAV n=5 post-clip-guard, below 40-trade threshold)
- ✅ Fills: 8 today, 3 complete pairs with locked margin 11–18¢/sh, mechanics clean
- ✅ NO-parity: 50% post-level (starvation fix confirmed)
- 🔴 **Dispersion edge: ratio 0.817 locked Jun 28–Jul 2, declining; 5th consecutive below-baseline proxy σ reading (−13.2% vs baseline); Jul 3 partial data 0.521°C implied σ confirms continued compression**
- 🔴 Calibration: gauge window stale day 4; isotonic correctly rejects OOS-worse candidates; underlying plateau blocks gauge improvement
- ✅ Risk frame: kill-switches CLEAR; ruin-floor sensor seam documented, deferred to morning slot today
- ⚠ Data: PAIR_FAV gate restart at n=5 post-clip-guard (ETA n=100: ~9 days)
- ✅ Reliability: active, 0 downtime alerts

**The bottleneck is calibration infrastructure failure, specifically the isotonic plateau that prevents the dispersion gauge from measuring edge recovery.**

The causal chain: isotonic plateau (grid 0.30–0.90 maps to uniform 0.3801) → OOS guard correctly rejects every candidate → gauge window locks at Jun 28–Jul 2 → disp_ratio 0.817 locked (cannot confirm recovery or worsening) → standalone YES and NO re-enable conditions cannot be evaluated → turns/day correctly low at 0.39.

Turns/day at 0.39 is NOT the enemy. The "badatmath benchmark" of ~1.0 turns/day is now **VOID**: badatmath ran −$11.3k/7d on the full band structure the same week our dispersion alert fired (state_log 07-03, 07-05). Replicating his volume would replicate his losses. The correct comparison is zero turns/day on any flow without confirmed edge. PAIR_FAV co-fills are structurally exempt (locked margin regardless of calibration) and correctly dominate the active engine.

**Until the dispersion gauge shows ratio ≥ 1.10 × 5 confirmed days, turns/day should not be the optimization target.** The path to increased compounding requires (1) the isotonic to pass its OOS guard with a structurally improved architecture, or (2) external evidence that the regime has shifted back to over-dispersion.

---

## §2 — Existing-System Optimization

| Item | Evidence source | Expected delta | Confidence | Effort |
|---|---|---|---|---|
| **Ruin-floor comparator → tracked capital** | State_log 07-05 22:25: deferred to "morning slot" | Eliminates false-halt seam; enables ratchet $40→~$88 | High | Low (Tier-1 wiring, EVOLVE daily) |
| **SUM_POSTED VPS join** | Gatekeeper §Gate7: "stuck weeks, VPS-only, n>>100" | Gate verdict READY/REJECTED; defines Σ ROI floor | High | Minimal (1 VPS command) |
| **UNTRACKED taker BUY (01:00Z) investigation** | maker_fills_recent.log: 99sh @0.44 TAKER, −$45 cap drop | Confirm sprint_ladder shot vs band code leak | Medium | Minimal (check sprint_ladder_state.json) |
| **Rebate receipt verification** | PnL ledger §3: $2.757 est. cumulative, 0 confirmed receipt | Potential $2.75 cash recovery | Medium | Minimal (check pUSD balance) |
| **Pair_cands floor investigation** | exec_audit §3: pair_cands=1–3/cycle consistently; never 0 despite low posting rate | Understand which gate (PAIR_FAV_SUM_MAX, EV_MIN, PX_CEIL, PAIR_SB_MAX_BEHIND) is rejecting the 1–3 per-cycle candidates | Medium | Low (log analysis) |

**What NOT to optimize:**
- Do NOT loosen PAIR_FAV_SUM_MAX — explicitly REJECTED by EVOLVE weekly (07-05): "would widen the exact naked-YES surface the clip data condemns"
- Do NOT increase turns/day by lowering BAND_EV_MIN or BAND_PX_CEIL — no calibration support; dispersion premise failing
- Do NOT broaden standalone YES band — BAND_YES_LIVE_MIN_DOUT=9 correct until disp_ratio ≥ 1.10
- **Turns/day 0.39 vs badatmath 1.0 is a dead comparison.** Badatmath ran −$11.3k/7d at ~1.0. Velocity is the wrong optimization target in an under-dispersed regime.

**Cap/budget checks — no binding constraints found:**
- BAND_MD_DAILY_BUDGET = 9999 (uncapped) — not binding
- cash_preskip = 0 all day (exec audit) — no cash starvation
- books = 0–4/80 (exec audit) — no fetch starvation
- BAND_NO_CASH_RESERVE = 0.30 — with cap~$142 and Munich pair ~$8 resting, reserve is $42; pair_cands would need to exceed $94 in queued stakes simultaneously to trigger this, extremely unlikely at current volumes

---

## §3 — Gate Pipeline Review

From gatekeeper_report.md (09:10Z). **0 READY, 0 newly REJECTED today.**

| Gate | Status | n | ETA next milestone | Bottleneck / lever |
|---|---|---|---|---|
| **PAIR_FAV YES** | COLLECTING RESTART ‡ | 5 post-guard | ~3d to n=40, ~9d to n=100 | Clock running at ~11 pairs/day. City breadth may help (see §6C) |
| **PAIR_FAV NO** | COLLECTING RESTART ‡ | 5 post-guard | Same | Same |
| **FILLED_VS_FIRED** | COLLECTING | ~37 | **~5h to n=40 watch** | Auto-accumulating; VPS join needed at trigger |
| **SUM_POSTED 0.70–0.85** | COLLECTING | >3,076 fires | **NOW — only CI blocked** | One EVOLVE VPS run of band_resolution_join.py |
| BAND_YES (all) | AMBIGUOUS | 934 res | CI straddles 0; no path without dispersion recovery | Blocked by isotonic plateau → OOS guard |
| BAND_NO d+1 | AMBIGUOUS | 115 shadow/51 live | Live WR=39.2% → effectively REJECTED | Correctly disabled, no action |
| BASKET_EXIT | VOID | — | — | Retired Jun 22, 4 fatal structural flaws |
| THERMO_MAKER_NO | REJECTED | 125 ext | — | EV≈0 confirmed; THERMO_MAKER_LIVE=False permanent |
| M1_BETA_LOCKOUT | REJECTED | 31 | — | Param reverted 2813daa1e; capacity ZERO |

‡ Prior n=9 discarded — mechanism contaminated by clip-guard absence. Post-guard fires only.

**Most urgently actionable: SUM_POSTED.** n>>100 for months; data exists on VPS; CI is the only gap. One `band_resolution_join.py` run delivers a READY or REJECTED verdict for the gate that has been pending longest.

**FILLED_VS_FIRED at ~5h to n=40:** When crossed, next EVOLVE VPS slot must run filled-vs-fires divergence join, split pre/post-clip-guard. This is the earliest winner's-curse test on the post-guard PAIR_FAV era. Do not skip.

**To accelerate PAIR_FAV accumulation WITHOUT degrading expectancy:**
- City breadth audit (§6C): check if non-allowlist cities have ≥2 valid pair_cands/day at qy+qn < 0.90. Do NOT add cities without evidence of valid pair structure.
- Do NOT lower PAIR_FAV_SUM_MAX (rejected).
- Do NOT lower BAND_EV_MIN (no calibration support).
- Verify BAND_NO_CASH_RESERVE=0.30 is not spuriously blocking pair_cands during low-cap cycles (cap was $119–$128 for several hours today — with 0.30 reserve = $36–38, this should not block ~$8 pair stakes; check if any cycle logged a cash_preskip > 0 from this reserve).

---

## §4 — Assumption Attack

### A) Dispersion premium persists (implied σ > realized σ)

**Status: CURRENTLY FAILING.**

- Measured disp_ratio Jun 28–Jul 2: 0.807, 0.663, 0.976, 0.866, 0.858 — all < 1.0, median 0.817.
- Jul 3 partial (calib_monitor, new data this run): median implied σ = 0.521°C for 6 POST_PEAK cities. All five Jun 28–Jul 2 implied σ values were 0.794–0.860°C. Jul 3 is below all five — confirms compression continues past the locked window.
- Jul 4–5 implied σ: 0.199°C and 0.030°C (near-resolution artifacts; directionally confirm extreme compression).
- Proxy σ cleaned today: 0.862°C vs 0.994°C baseline = **5th consecutive below-baseline day** (cumulative decline −13.2%).
- External confirmation: badatmath −$11.3k/7d at 450+ fills/day on the same structure = market-level signal that the band edge is absent for all participants.

**PAIR_FAV is structurally exempt** — the locked qy+qn spread earns regardless of calibration or resolution outcome. But any return to standalone YES/NO requires this assumption to recover and be confirmed via gauge. Current data suggests 2–4+ weeks minimum before re-enable conditions could be met, even if the regime shifted today.

### B) Fills are not adversely selected (makers get filled fairly)

**Status: HOLDS for post-clip-guard genuine pairs; SUSPECT for any solo flow.**

- Post-clip-guard genuine pairs (n=3 complete today): YES fills 9–23 min after NO fills, both legs fill symmetrically → structural lock means winner's curse is impossible (both outcomes guaranteed after both legs fill). Confirmed from exec_audit co-fill timing.
- Pre-clip-guard contaminated pairs (n=10 resolved per gatekeeper): WR=10% at avg quote 0.46. Adverse selection confirmed on naked-YES. These are the positions explaining today's capital drop from $217.44 → $141.74 (gatekeeper advisory §3).
- BAND_NO standalone (n=51 live): WR=39.2% vs shadow 68.7% at comparable quotes — 29.5pp adverse selection gap. Decision-grade winner's curse. Correctly disabled.
- Jul 03–04 standalone YES fills (n=12, CLOB blocked from cloud): uncharacterized. All fat-middle range (0.42–0.50) = highest adverse selection risk zone.

**Threat:** The post-guard data (n=5) is too sparse to confirm assumption holds at scale. The prior contaminated mechanism had 74% naked-YES degeneracy. The clip-guard enforces structural pair integrity — the assumption should hold — but it needs n=40+ resolved to confirm quantitatively.

### C) Recycle velocity scales (RECYCLE099 generates systematic return)

**Status: REAL flow, confirmed n=44 cumulative (+$90.11 on $221 basis per state_log weekly), but BURSTY.**

- Jul 5 demonstrated: exit099 +$7.50 net (Taipei +$6.60, Moscow +$0.90). This is real compounding from positions approaching resolution.
- TODAY (exec_audit, maker_fills_recent.log): 4 SELL_EXIT orders at $0.99 resting 16–21h without filling. Takers aren't buying at $0.99 before resolution on these markets. Recycle velocity depends on market-specific convergence behavior that cannot be planned.
- RECYCLE099 vs SPRINT_LADDER: state_log weekly confirms that 85% of recent capital gains (equity $85 → $217) came from sprint_ladder coin-flips (P(3+/4 wins @~0.45) ≈ 27%), not RECYCLE099 compounding. RECYCLE099 is real and positive (+$90.11 cumulative) but NOT the primary growth driver — the sprint_ladder is. This distinction matters for honest compounding expectations.

**No action implied** — recycle velocity cannot be increased by parameter change. It depends on market-convergence rates outside our control.

---

## §5 — Market Intelligence (Day 6 mod 3 = 0 → Competitor Posture)

**badatmath_watch shadow data availability:** Most recent file in shadow_summary is 2026-06-26 (5,908 rows; last fill_join: Seoul YES @0.40, detect_lag=57.5s on Jun 27). Jun 28–Jul 6 badatmath_watch data unavailable to cloud agent — VPS has current data. Using state_log readings for competitor posture.

### Badatmath (0x8fbd7c…a959) — from state_log 07-03 19:45 + 07-05 weekly

| Period | Realized PnL | Activity |
|---|---|---|
| 1d (Jul 2) | **−$1,546** | 452 fills, $11.7k vol |
| 7d (to Jul 3) | **−$11,307** | Full band structure |
| 30d (to Jul 3) | **−$11,445** | 100% weather |

Shadow fill detail (Jul 2): YES median = $0.09 (extreme-probability markets, not fat-middle), NO median = $0.67. He shifted to extreme-probability YES purchases (buying 9¢ YES = 10× payoff) while maintaining NO-band fills. This is a volatility-play adjustment, not a dispersion-premium play — and it's still bleeding.

**State_log verdict (07-05 weekly):** "badatmath benchmark VOID (he ran −$11.3k/7d in the same structure). DO NOT REBROADEN THE BAND."

### Onlyluck — from state_log 07-03 falsification sweep
"onlyluck same-day 500 fills" — no PnL detail available. Running at scale simultaneously.

### Structural verdict

1. **Standard maker complex is dead for all participants in the current regime.** Both top-volume competitors bleeding at scale. Our refusal to broaden is vindicated by their results, not just our own dispersion data.
2. **Detect_lag competition is irrelevant.** Last known (Jun 26–27): 57.5–129.9s. With both major competitors losing, detect_lag edge doesn't exist to compete for in the weather market.
3. **Badatmath's strategy shift** (0.09 YES median → extreme-probability plays) is not a usable signal for us — he's adjusting within a losing framework.
4. **Delta vs prior state_log knowledge:** As of Jul 3, both competitors were actively bleeding. Three days have passed. EVOLVE VPS should pull current lb-api PnL for badatmath at the next daily run to detect if he cut the structure (which would be a positive signal for the regime) or maintained it.

**No competitive threat to current posture.** We're correctly sitting out the structure everyone is bleeding on.

**Data gap flag:** Fresh badatmath_watch fill data (Jun 28–Jul 6) unavailable from cloud. VPS has this data via the badatmath_watch shadow logger. Include lb-api PnL pull and detect_lag update in next EVOLVE daily slot.

---

## §6 — Three Experiments

### Experiment A: SUM_POSTED [0.70–0.85] Gate CI Computation (VPS, immediate)

- **Hypothesis:** BAND_YES fires where sum_posted (total ask paid across posted legs) landed in [0.70, 0.85] have positive ROI — confirmed via resolution join. This is the Σ range that genuine post-guard PAIR_FAV pairs occupy naturally (qy+qn = 0.80–0.90), providing a historical baseline for the new mechanism.
- **Data:** VPS `band_resolution_join.py --dedup first_fire --filter sum_posted_range 0.70 0.85`; n_fires >> 100 already.
- **Time:** One EVOLVE scheduled run. **Cost:** 0.
- **Success metric:** CI95 lower bound > 0 (confirmed positive ROI on this Σ slice).
- **Decision-if-yes:** Document as a resolution-joined ROI floor for the PAIR_FAV Σ window. When PAIR_FAV reaches n=100 resolved co-fills, compare realized co-fill ROI against this baseline. Provides analytical continuity between band-YES history and new mechanism.
- **Decision-if-no:** [0.70–0.85] Σ slice shows negative ROI historically → investigate which city/days_out/period subsets drove the loss before extending trust to PAIR_FAV in the same range. Also implies PAIR_FAV may be trading a demonstrated-negative structure.

### Experiment B: FILLED_VS_FIRED Divergence Join at n=40 (VPS, ~5h)

- **Hypothesis:** Post-clip-guard PAIR_FAV co-fills show NO adverse selection (fill_roi ≈ all_fires_roi); pre-clip-guard contaminated fills show strong adverse selection (fill_roi << all_fires_roi), quantifying the mechanism failure.
- **Data:** n_fills ≈ 37 now. ETA n=40: ~5h at current rate. VPS `band_resolution_join.py` sliced to fill events vs all simulated fires, pre/post guard flag.
- **Time:** Passive accumulation ~5h; VPS join ~1h. **Cost:** 0.
- **Success metric:** Post-guard fill_roi within 5pp of all_fires_roi at n≥5 resolved. Pre-guard fill_roi < all_fires_roi by ≥20pp (confirms contaminated mechanism was adversely selected).
- **Decision-if-yes on adverse selection in post-guard:** Even genuine pairs are cherry-picked → widen pair quotes; investigate systematic front-running of YES leg.
- **Decision-if-no adverse selection in post-guard:** Fill quality confirmed clean. Proceed to n=100 accumulation with confidence.

### Experiment C: BAND_CITY_ALLOW Breadth Audit (VPS, low-effort)

- **Hypothesis:** 2–3 cities NOT currently in BAND_CITY_ALLOW have ≥2 valid pair_cands/day where pairs naturally clear qy+qn < 0.90 and both legs pass PX filters (BAND_PX_MIN, BAND_PX_CEIL). Adding them would increase pair fires from ~10–11/day to ~13–15/day, reducing ETA to PAIR_FAV n=100 from ~9 days to ~7 days.
- **Data:** band_struct_lite shadow log: extract all records for cities NOT in BAND_CITY_ALLOW; check "reason" field — cities failing ONLY on sum_gate or no_band (vs cities failing on city_allow first) indicate valid structures being missed. Cross-check with Gamma API for liquidityClob > 200.
- **Time:** 1 EVOLVE VPS analysis pass (~30min). **Cost:** 0.
- **Success metric:** ≥2 candidate cities with ≥2 confirmed valid pair_cands/day at qy+qn < 0.90 in the last 7 days of shadow data.
- **Decision-if-yes:** Add candidates to BAND_CITY_ALLOW in next EVOLVE daily (Tier-1 breadth change, no EV impact if pair structure valid).
- **Decision-if-no:** City breadth is not the constraint; pair_cands limited by market structure (insufficient Σ < 0.90 pairs available in the 51-city universe). No action.

---

## §7 — Single Best Action

**EVOLVE VPS: run SUM_POSTED [0.70–0.85] gate CI computation (band_resolution_join.py with sum_posted filter).**

**Justification from specialist reports:**

Gatekeeper_report (09:10Z) Advisory §5: *"SUM_POSTED gate urgency: n_fires >> 100 for months; CI is the only thing standing between this and a verdict. One EVOLVE VPS run with sum_posted in [0.70, 0.85] filter on the deduped first-fire file would deliver a verdict. This gate has been stuck on 'VPS join needed' for multiple weeks."*

**Why now, not tomorrow:**
- The PAIR_FAV clip-guard deployed last night (07-05 22:20Z) reset the mechanism. Post-guard pairs will occupy this exact Σ range [0.80–0.90] by construction. Without running the historical SUM_POSTED join, we have no resolution-joined baseline for the new mechanism's operating range. If SUM_POSTED [0.70–0.85] shows historically negative ROI, this is decision-grade information — it means post-guard pairs may be entering a structurally negative Σ slice and EV calculation needs revisiting before n=100 co-fills resolve.
- Zero capital risk. Zero code change. One scheduled VPS command.
- Compounding impact × P(success) / effort: HIGH/HIGH/MINIMAL. Beats all alternatives by effort margin.

**If SUM_POSTED gate returns READY (CI lower bound > 0):** Publish verdict in gate_ledger; no parameter change needed. Provides future anchor when PAIR_FAV data matures.

**If SUM_POSTED gate returns REJECTED (CI upper bound < 0):** Escalate immediately — current PAIR_FAV mechanism may be posting into a demonstrated-negative Σ range. Human review required before pair_fav continues.

**First concrete step:** Add to EVOLVE daily task list for today's 11:23Z slot: `python3 analytics/band_resolution_join.py --dedup first_fire --filter sum_posted_min 0.70 sum_posted_max 0.85 --output logs/evolve/sum_posted_gate_ci.md`

---

## PROPOSED ACTIONS (human review)

*REPORT-ONLY: no strategy code changes in this commit. All items below require human or EVOLVE-daily review.*

| Priority | Action | Evidence | Tier | Effort |
|---|---|---|---|---|
| 1 | **EVOLVE daily: SUM_POSTED VPS join** `band_resolution_join.py --dedup first_fire --filter sum_posted_range 0.70 0.85` | Gatekeeper §Gate7, stuck weeks | Tier-1 | 1 VPS command |
| 2 | **EVOLVE daily: Ruin-floor comparator → tracked capital** (deferred from 07-05 22:25 "morning slot"). Implement cash + open-position cost comparison; then ratchet ruin_floor $40 → 0.40×30d-HW (~$88) | State_log 07-05 22:25 | Tier-1 | Low (wiring) |
| 3 | **EVOLVE daily: FILLED_VS_FIRED VPS join at n=40** (~5h from now at current fill rate). Run pre/post clip-guard split. Winner's curse check on post-guard pairs. | Gatekeeper §Gate3 | Tier-1 | 1h VPS at trigger |
| 4 | **HUMAN: Verify UNTRACKED taker BUY at 01:00Z** (token=9704915965521504, 99sh @0.44, −$45 cap drop). Check sprint_ladder_state.json — expected to be a sprint_ladder shot; confirm it's not a band system leak. | maker_fills_recent.log 01:00Z | Review | 5 min |
| 5 | **HUMAN: Rebate receipt check.** Cumulative expected $2.757 (pnl_ledger §3); 0 confirmed receipts across 3 reporting cycles. Check pUSD wallet balance. If 0, contact Polymarket #support. | PnL ledger §3 | Review | 5 min |
| 6 | **EVOLVE daily: Pull current lb-api PnL for badatmath (0x8fbd7c…a959).** Last reading: 7d −$11.3k as of Jul 3. Delta reveals whether he cut the structure — a positive signal for regime shift detection. | State_log 07-03, 07-05; §5 above | Tier-1 (data pull) | 5 min VPS |
| 7 | **EVOLVE daily: BAND_CITY_ALLOW breadth audit** (Exp C). Check band_struct_lite for non-allowlist cities with valid pair structures. No parameter change without evidence. | §6C above | Tier-1 (data only) | 30 min VPS |

---

*research-agent@klaus | 2026-07-06T10:30Z | Branch: claude/find-lag-parameter-rFQ0N | Specialist reports: 4/4 current (all within 36h) | badatmath_watch: last available Jun 26–27 (cloud gap noted; VPS has current data) | state_log: 07-01 through 07-05 22:25Z inclusive*
