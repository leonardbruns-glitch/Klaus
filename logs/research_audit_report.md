# Research Audit — 2026-06-30
**Generated:** 2026-06-30T10:35Z | **Run by:** research-agent | **Snapshot:** 2026-06-30T10:21:22Z (14 min old — FRESH)
**System:** `active` (uptime since 2026-06-29T13:28:08Z, ~21h) | **Bankroll:** $94.043178 (+$13.06 vs 09:06 gatekeeper; +16.1% 24h)

---

## Pre-flight

| Check | Result |
|---|---|
| SNAPSHOT.md age | 14 min — PASS |
| System status | `active` — PASS |
| Specialist reports | exec_audit (08:45 Jun-30), calib_monitor (08:xx Jun-30), gatekeeper (09:14 Jun-30), pnl_ledger (23:37 Jun-29) — all within 36h |
| Git fetch | FAILED (network timeout) — all data read via GitHub MCP directly from data-mirror |

**Note:** `data/agent_context/research_status.md` last updated 2026-05-16, describes retired LDA strategy. Treated as background only. Specialist reports + band_config.txt are authoritative. This is the fourth consecutive report flagging this staleness.

**Delta vs prior report (Jun-29 10:30Z):**
- Capital: $80.86 → $94.04 (+16.4%) — extraordinary; driven by overnight native resolutions from Jun-28/29 NO positions
- Cash freeze: avg cash_preskip 7–13 (Jun-29) → 4.5 (Jun-30) — substantially resolved; turns/day by cash = 1.008 (AT benchmark)
- FILLED_VS_FIRED: n=60 → n=74 (+14); ETA to n=100 shortened to **1.9 days (≈ Jul 2)**
- Dispersion ratio: 1.096 → **1.061** (deteriorated −0.035); newest Jun-29 d+2 records at **0.971°C** — BELOW threshold
- M1_BETA_LOCKOUT: 17 days stalled → **18 days** — prior proposal still unactioned
- BAND_NO_CASH_RESERVE=0.30: prior proposal to lower to 0.20 unimplemented; less urgent given preskip improvement
- Bot restarted Jun-29 13:28Z (was running since Jun-26 15:08Z prior day)

---

## 1 — Primary Bottleneck: Resolution Data Blackout at FILLED_VS_FIRED Decision Gate

**Rank basis:** By the compounding hierarchy (equity deployed, turns/day, ROI/turn, fills, NO-parity, calibration, dispersion edge, risk frame, **data**, reliability), data ranks #9. I elevate it here over dispersion edge (#7) for three reasons:
1. The dispersion edge alert cannot be properly interpreted without outcome data — realized σ is carried/stale (resolution data unavailable); the gauge may be measuring the wrong edge metric per the Jun-24 sigma_reality analysis (n=211, concluded "dispersion premise DEAD/inverted; real edge = MAKER spread-capture + underpricing").
2. The blockage is time-sensitive: FILLED_VS_FIRED hits n=100 at **≈ Jul 2 (1.9 days)** — the winner's-curse verdict is the most important pending question in the system, and CI computation is blocked by Gamma 403 from cloud containers.
3. All gate verdicts are blocked by the same structural gap: Gamma API accessible from VPS, not from cloud. One VPS execution unblocks 4 simultaneous verdicts.

**Evidence from specialist reports:**
- Exec audit: "n≈38 tokens, below 40-trade threshold. Winner's curse undetermined. Run `band_resolution_join.py` post-2026-07-01."
- Gatekeeper: "FILLED_VS_FIRED n=74 → n=100 in ~1.9 days (≈ Jul 2). Exec Auditor must schedule VPS-side resolution join NOW. The cloud container cannot reach Gamma API. Without VPS-side join at n=100, winner's-curse detection is blind when it matters most."
- Calib monitor: "6th consecutive cycle DARK." ECE7=0.041 frozen. Brier frozen. Both require outcome data.
- Current resolved fills: n≈38 (exec audit), below the 40-trade floor for any trend claim.

**Capital growth ($94, consecutive_wins=2) is strongly positive but insufficient.** At n=38, p(12 clean wins at true_WR<50%) is not negligible at this fill count. The winner's-curse test at n=100 is the proper signal.

**If not addressed:** The system will cross the FILLED_VS_FIRED threshold with no ability to compute CI, city expansion decisions will be deferred indefinitely, and dispersion compression cannot be evaluated vs fill quality.

---

## 2 — Existing-System Optimizations

### 2a. VPS Gamma Resolution Join (band_resolution_join.py) — carried, still unactioned

- **Source:** Gatekeeper structural blocker #1 — identical to prior audit. BAND_NO+PAIR_FAV (n=253), BAND_YES (n=6,044), SUM_POSTED (n=3,001), FILLED_VS_FIRED (n=74) all blocked by Gamma 403 from cloud
- **Expected delta:** 4 simultaneous CI verdicts; winner's-curse detection at n=74–100; city allowlist expansion justification or adverse-selection investigation
- **Confidence:** HIGH — data accumulated; only network path missing
- **Effort:** LOW (VPS shell command, 30 min total)
- **Urgency:** ELEVATED — FILLED_VS_FIRED at n=74, decision gate in 1.9 days; was 3 days yesterday, not run

### 2b. M1_BETA_LOCKOUT — REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5°C

- **Source:** Gatekeeper §6 — n=31, 0 fires in 18 consecutive days, standing rule triggered day 18 (threshold was 14d)
- **Expected delta:** Resumes M1 gate accumulation; at prior candidate rate, would reach n=100 within 5–8 weeks. No capital risk (gate not live).
- **Confidence:** HIGH (the floor revert is the identified cause; the gate fires during the freeze window per prior config)
- **Effort:** LOW (single config value change)
- **Risk:** Zero — gate not live, only accumulating data

### 2c. YES d+2 live activation assessment (BAND_YES_LIVE_MIN_DOUT)

- **Source:** Exec audit §2 — yes_books=0 in 840/840 STRUCT-BAND-Q cycles; Gatekeeper §1 — BAND_YES n=6,044 (+45 in last day) shadow-only at d+2
- **Status:** 29 d+2 shadow YES fires Jun-30; these are informational (BAND_YES_LIVE_MIN_DOUT=2 → live YES posts DO fire at d+2, but shadow records accumulate faster). The gate n=6,044 >> 100 threshold but CI blocked.
- **Expected delta (if CI confirms positive):** YES d+2 live adds revenue stream alongside NO; exec audit notes avg YES fill 0.484 → gross ROI per YES-win ≈ +107%
- **Confidence:** MEDIUM (positive outcome likely given RECYCLE099 trajectory, but CI must clear first)
- **Effort:** ZERO (already enabled; blocked on CI)
- **Next step:** VPS resolution join unlocks this automatically

### 2d. BAND_BASE_STAKE floor check (dispersion guard)

- **Source:** Calib monitor §3 — if d+2 ratio falls below 1.00 in next cycle, calib_monitor recommends reducing BAND_BASE_STAKE or widening sigma floor
- **Current:** BAND_BASE_STAKE=3.0, BAND_SIGMA_FLOOR=0.90
- **Trigger condition (not yet met):** d+2 implied_std < 1.00°C for 2 consecutive cycles
- **Expected delta:** Reduces YES band exposure if dispersion edge evaporates; does NOT affect NO band (dominant revenue stream)
- **Confidence:** CONDITIONAL (only act if d+2 ratio < 1.00 confirmed next cycle)
- **Effort:** LOW (config change)

| Optimization | Delta | Confidence | Effort | Priority |
|---|---|---|---|---|
| VPS Gamma join | 4 gate verdicts, winner's-curse at n=100 | HIGH | LOW | 1 (urgent) |
| M1 floor revert | unblock 18d stall, resume accumulation | HIGH | LOW | 2 |
| YES d+2 live CI check | +YES revenue stream | MEDIUM | ZERO (unblock) | 3 |
| Stake floor guard | protect vs dispersion collapse | CONDITIONAL | LOW | 4 |

---

## 3 — Gate Pipeline Review

**Source:** gatekeeper_report.md (09:14 UTC Jun-30)

| Gate | n | +24h | CI | Status | ETA / blocker |
|---|---|---|---|---|---|
| BAND_NO + PAIR_FAV | 253 | +10 | BLOCKED | COLLECTING | VPS join |
| BAND_YES | 6,044 | +45 | BLOCKED | COLLECTING | VPS join |
| SUM_POSTED 0.70–0.85 | 3,001 | +19 | BLOCKED | COLLECTING | VPS join |
| FILLED_VS_FIRED | 74 | +14 | BLOCKED | **⚠️ ~Jul 2** | **1.9 days — urgent** |
| M1_BETA_LOCKOUT | 31 | 0 | AMBIGUOUS | **STALLED 18d** | Human: revert floor |
| THERMO_MAKER_NO | 3 | 0 | n/a | FROZEN | Re-arm or kill |
| BASKET_EXIT | VOID | — | — | Retired Jun-22 | — |

**No gate newly hit READY or REJECTED this cycle.** State unchanged from prior run.

**Structural blockers (same as yesterday, now day 2 unresolved):**
1. Gamma 403 from cloud container — blocks CI for all four major gates
2. THERMO_MAKER_LIVE=False — n=3 kill gate unreachable
3. M1_BETA_LOCKOUT stalled 18d — n=31 AMBIGUOUS, 0 placed orders

**What accelerates WITHOUT degrading expectancy:**

*Breadth over stake.* The 5-city allowlist ({chengdu, london, beijing, munich, wuhan}) generates ~13.8 BAND_NO legs/day per gatekeeper SUM_POSTED data. Adding a 6th city raises BAND_NO fire rate ~+20% and shortens FILLED_VS_FIRED ETA from 1.9 days to ~1.5 days — reaching n=100 ~10h earlier. Gate: city must show markout trend ≥ −1.2% (Beijing floor in current set). This would not affect expectancy per existing city (no stake change, no existing-city interference).

*M1 floor revert* does NOT risk expectancy — gate is not live. It only unblocks data flow.

*Caution:* Do NOT expand cities based on this analysis alone. City expansion requires VPS-side CI confirmation per n=243 BAND_NO verdict, or the Jun-24 markout dataset (n=1,421 fills, trend-grade per prior audit). Neither has been formally cleared since the narrow-start cutover.

---

## 4 — Assumption Attack

Three load-bearing assumptions of the BAND system today:

### Assumption 1: Dispersion premium persists

**What the system assumes:** Market-implied daily std ≥ realized std (ratio ≥ 1.10) → YES buckets are overpriced → buying YES at discount is +EV.

**Today's data (calib_monitor):**
- All records: implied_std = 1.061°C / ratio = 1.061 (BELOW 1.10 threshold) ⚠️
- d+2 only: 1.100°C / ratio = 1.100 (AT threshold) ⚠️
- Newest d+2 (Jun-29): 1.098°C / 0.971°C — two of four most recent records BELOW 1.00
- Mode_ask trend: 0.419 (Jun-25) → 0.322 (Jun-29), −23% in 4 days
- Prior ratio: 1.096 → today 1.061, −0.035 (deteriorated)

**Critical context:** Jun-24 sigma_reality analysis (state_log, n=211 city-days) concluded: "Market is UNDER-dispersed (implied 0.81 < realized 1.1–1.6) — dispersion premise DEAD/inverted; real edge = MAKER spread-capture + 0.25–0.45 underpricing + MERGE-LOOP velocity." If this verdict holds, the dispersion gauge is measuring the wrong edge metric. Implied_std rising from 0.81 → 1.061 is actually positive direction under the Jun-24 framework.

**For NO band specifically:** The calib_monitor proxy uses ±2-leg weights and systematically underestimates true implied_std. NO fills at avg 0.706 are far-outlier bets — these are NOT the mode buckets where dispersion compression most hurts. The mode_ask declining from 0.419 → 0.322 primarily affects YES-band entries near mode (which are shadow-only per BAND_YES_LIVE_MIN_DOUT=2). **The NO-dominant revenue stream is less directly exposed to this risk than the gauge implies.**

**Threat level: MEDIUM-HIGH for YES band (shadow, no live capital). LOW for NO band (live, dominant).** Calib_monitor is correct to flag this — but the direction of the risk is narrower than it appears. If d+2 ratio falls below 1.00 for 2 consecutive cycles, reduce BAND_BASE_STAKE (YES exposure guard).

### Assumption 2: Fills are not adversely selected

**What the system assumes:** Takers who fill our NO bids at 0.65–0.85 do not have systematically better information. Winner's-curse: our fills concentrate on markets where the true resolution is adverse.

**Today's data:**
- Exec audit: n≈38 fills — data collection tier, below 40-trade floor for ANY trend claim
- FILLED_VS_FIRED n=74 approaching n=100; CI blocked by Gamma 403
- NO fill composition: 74% in 0.65–0.85 price band; avg 0.706 (exec audit)
- At 0.706 NO fill, gross ROI per win = +41.6%; breakeven win rate = 70.6%
- Capital +16.1% in 24h, consecutive_wins=2 — indirect positive evidence

**Threat level: UNVERIFIABLE at n=38 (data collection).** The capital trajectory is consistent with genuine edge, but sample is too small to distinguish edge from variance. CI at n=100 (Jul 2) is the definitive test. **This is the existential question. Do not expand cities or stakes before CI clears.**

**Gap:** One VPS execution of band_resolution_join.py resolves this question. It has been flagged for two consecutive audit cycles without action.

### Assumption 3: Recycle velocity scales

**What the system assumes:** SELL_EXIT queue converts to cash (via RECYCLE099 or native resolution) fast enough to avoid prolonged cash lock-up that starves new maker posts.

**Today's data:**
- PnL ledger Jun-29: 11 RECYCLE099 exits (100% WR, +$22.046 gross, 41.8% ROI/turn)
- Native resolutions: ~$14.90 unattributed Jun-29, ~$19.758 Jun-28 — confirmed two consecutive sessions of healthy on-chain settlement (KNOWN LOGGING GAP; not adverse)
- Cash preskip: 4.5 avg (Jun-30) vs 7–13 (Jun-28 evening) — cycle shows IMPROVEMENT
- Turns/day: 1.008 by cash (exec audit, AT benchmark); 0.50 by conservative equity (PnL ledger)
- Active SELL_EXIT: 14-15 orders (exec/gatekeeper) awaiting resolution

**Threat level: LOW.** Recycle is scaling. Capital grew $75→$94 over 2 days. The cash-freeze identified in the Jun-29 report has materially eased (preskip 4.5 vs 7–13). The discrepancy between cash turns (1.008) and equity turns (0.50) is a denominator artifact: SELL_EXIT cost basis (~$65) inflates the equity denominator while that capital is fully deployed and earning via convergence. Velocity is healthy.

**Minor risk:** Moscow NO @0.93 (pre-allowlist, 1 fill, exec audit) — resolving at $1.00 yields only +$0.07/sh pre-fee (marginal). However, this is a legacy outlier and no new Moscow posts are possible under current config.

---

## 5 — Market Intelligence (Day mod 3 = 0: Competitor Posture)

**Data source:** band_config.txt comments (inferred); badatmath_watch.jsonl unavailable (file too large for cloud read; VPS-side access required).

**Direct data gap:** No badatmath_watch deltas this cycle. The shadow file is unavailable from this agent's network path. This is the same gap as prior audit.

**Inferred competitor posture from band_config.txt:**
- Badatmath NO fill median: $5.16/fill (per BAND_NO_STAKE comment — our config mirrors his)
- Badatmath runs ≥ city set > 5 (our narrow-start is a subset of his cities)
- His d+0 YES noted as "his bleed" (BAND_YES_MAX_OFF_D0=0 comment) — he apparently takes d+0 YES losses; we don't
- His YES_MAX_OFF = 2+ (we cap at 2 — same coverage)
- BAND_NO_DAILY_CAP=40 comment: "his NO = HALF the book at equal per-event" — he deploys ~2× our NO stake per city

**Competitive positioning delta vs prior state_log knowledge:**
1. **No new leaderboard wallet data.** Unchanged from prior audit.
2. **Our NO stake gap:** At $5.0 vs his median $5.16, we are near-parity per fill. At 5 cities vs his broader set, our daily throughput is ~50–60% of his. The breadth gap (cities) is the primary competitive disadvantage, not stake per fill.
3. **Moscow fill (Jun-28, legacy):** Pre-dates narrow-start. Moscow is apparently in badatmath's active set (he generates fills there). This is relevant if a city expansion decision is made — Moscow historical data exists, even if pre-allowlist.
4. **badatmath_watch.jsonl:** Must be read on VPS for delta analysis. Agent-level competitor posture is structurally incomplete without VPS access for this file. Standing request: add competitor_posture delta to data-mirror agent_context on each snapshot.

---

## 6 — Experiments

### Experiment A: VPS Resolution Join → Winner's-Curse Verdict at n=74 (pre-threshold)

**Hypothesis:** FILLED_VS_FIRED CI at current n=74 already clears zero (lower CI > 0%), confirming NO-band fills are net-positive and adverse selection is not material at current price range (0.65–0.85).

**Data:** Run `band_resolution_join.py` on VPS; extract per-leg ROI for n=74 filled legs; compute CI95 bootstrap; split by NO price band (0.65–0.85 vs 0.85+).

**Time:** Immediate — 30 min to run. Results available before Jul 2 n=100 crossing.

**Cost:** Zero capital.

**Success metric:** CI95_lower > 0.0% at n=74 AND at n=100 when reached; NO fills in 0.65–0.85 band show positive mean ROI.

**Decision if yes:** City allowlist expansion justified as next action; begin 6th-city breadth probe; YES d+2 live promotion deferred until CI also clears for BAND_YES.

**Decision if no (CI straddles zero or lower < 0):** Adverse selection active. Investigate by city (which city's fills are drag?), by price sub-band (0.65–0.75 vs 0.75–0.85), by days_out (d+1 vs d+2). Halt city expansion. Consider tightening BAND_NO_MIN from 0.52 to 0.60 to reduce low-confidence fills.

---

### Experiment B: M1_BETA_LOCKOUT Floor Revert (metar_lockout_temp_floor → 0.5°C)

**Hypothesis:** The metar_lockout gate fires at ≥5/week when METAR_LOCKOUT_TEMP_FLOOR is restored to 0.5°C, unblocking 18d of stalled accumulation toward the n=100 decision threshold.

**Data:** Monitor `metar_lockout.jsonl` placed-order count for 7d after config change; current candidates-only count = 5,231/day (ample). Current WR=74.2%, ROI=−0.6% at n=31 (AMBIGUOUS).

**Time:** 7 days post-change.

**Cost:** Zero (gate not live — accumulating data only, no capital deployed).

**Success metric:** ≥5 placed orders in first 7d (vs 0 in prior 18d).

**Decision if yes:** Gate accumulates toward n=100 within weeks; schedule CI evaluation at n=100. WR=74.2% current trend is promising but n<40, data-collection only.

**Decision if no (still 0 fires after 7d):** The stall is structural (not the floor parameter). Archive M1_BETA_LOCKOUT; investigate what other condition prevents fires (lockout temp threshold, METAR data feed, or gate interaction with other active gates).

---

### Experiment C: Per-City Mode_Ask Decomposition (Dispersion Stability Probe)

**Hypothesis:** The mode_ask compression (0.419 → 0.322 in 4d) is concentrated in ≤2 specific cities (likely Asian: Chengdu, Wuhan, Beijing where summer temperatures are less uncertain) while EU cities (London, Munich) maintain mode_ask ≥ 0.38. If true, city composition rather than a universal market-efficiency shift explains the compression.

**Data:** Compute per-city median mode_ask from `band_struct_lite.jsonl` fire records, last 7d (data on VPS). Split by {Chengdu, Wuhan, Beijing} vs {London, Munich}. Each city likely has n≥20 fire records in 7d.

**Time:** 24h analysis (data exists; 1–2h VPS-side script).

**Cost:** Analysis only; zero capital.

**Success metric:** Asian city median mode_ask ≤ 0.28 AND EU city median mode_ask ≥ 0.38 (≥10% separation confirming regime heterogeneity).

**Decision if yes:** Rotate BAND_CITY_ALLOW to weight EU cities more heavily (London, Munich + 1–2 new EU cities) where dispersion remains robust. d+2 YES live promotion safe for EU cities even if dispersion compressing in Asia.

**Decision if no (compression uniform across all 5 cities):** Universal compression — market-wide efficiency improvement or summer weather regime shift. Reduce BAND_BASE_STAKE (YES exposure guard). Do NOT reduce NO stake (NO edge is distinct from dispersion assumption). Flag for next strategy review cycle.

---

## 7 — Single Best Action

**Run `band_resolution_join.py` on the VPS immediately — do not wait for Jul 2.**

**Justification (three specialist reports agree):**
- Gatekeeper: "Exec Auditor must schedule VPS-side resolution join NOW. The cloud container cannot reach Gamma API. Without VPS-side join at n=100, winner's-curse detection is blind when it matters most." (Verbatim advisory, Jun-30 09:14Z)
- Exec audit: "Run `band_resolution_join.py` on VPS post-2026-07-01. Markout will reach trend-tier (n≥40) once Jun 27–29 outcomes are logged." At n≈38 today, one day's resolutions clears the threshold.
- Calib monitor: 6th consecutive cycle dark on settled/proxy lanes — both can be partially rehydrated with resolution join output.

**Compounding impact:** At current trajectory (fills $78.50/day, ROI/turn 41.8%), the system is growing well. City expansion would proportionally increase throughput; the CI verdict is the prerequisite. BAND_NO (n=253, 2.5× gate threshold) and BAND_YES (n=6,044) have been sitting above n=100 for multiple cycles with no verdict. The join converts this accumulated data into actionable verdicts immediately.

**P(success):** 0.90 — script exists on VPS, data accumulated, Gamma API accessible from VPS (confirmed by system architecture; exec_audit was unable to run it only from cloud audit path).

**Effort × compounding impact ratio:** Maximum of all available actions. One VPS shell command produces 4 simultaneous gate verdicts and city expansion authority.

**Concrete first step:**
```bash
# On the VPS (SSH from local or equivalent):
python3 analysis/weather/band_resolution_join.py --help
# Confirm it loads, then:
python3 analysis/weather/band_resolution_join.py
# Push any new resolution files to data-mirror, or grep the output for CI bounds directly
```

**If the join confirms CI_lower > 0% for BAND_NO fills at n=74:** proceed to 6th city breadth addition (Experiment A decision-if-yes path) within same session.

**If the join shows CI straddles zero:** do NOT expand cities; immediately investigate by city/price-band (Experiment A decision-if-no path). Capital at $94 is safe but do not add exposure without CI clearance.

---

## PROPOSED ACTIONS (human review)

1. **[URGENT — SINGLE BEST] Run `band_resolution_join.py` on VPS** — FILLED_VS_FIRED crosses n=100 in 1.9 days; join MUST run before then. Same action as Jun-29 audit #1. Still unactioned. Concrete first step: §7.

2. **[DAY 18 — STALLED] M1_BETA_LOCKOUT — REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5°C** — standing rule triggered at >14d stall; now day 18. Gate accumulates 0 data per day without this. Low-effort, zero capital risk. Gatekeeper §6 has the verbatim proposal text. Human must implement; this agent does NOT touch strategy code.

3. **[CONDITIONAL — MONITOR] BAND_BASE_STAKE reduction if dispersion d+2 < 1.00 next cycle** — calib_monitor S3 reports newest d+2 records at 0.971°C; if next cycle (Jun-30 08:xx +24h) confirms d+2 ratio < 1.00, reduce BAND_BASE_STAKE from 3.0 to 2.0 as YES exposure guard. Not warranted yet — trigger condition not met.

4. **[VERIFY] pUSD rebate receipt** — cumulative estimated rebate $2.080 (PnL ledger) above $1.00 payout threshold. PnL ledger Jun-29 flagged this for wallet verification. Check Polygon funder wallet for pUSD inflows since Jun 10.

5. **[INFORMATIONAL] Dispersion city-level decomposition** — run Experiment C on VPS to determine if mode_ask compression is city-specific. Results clarify whether city rotation or stake reduction is the correct response. 2h effort, high VOI.

---

## Staleness Notes

- `data/agent_context/research_status.md`: Updated 2026-05-16, LDA era, obsolete for all band-era analysis. Any agent using it for briefing will receive incorrect strategy context. Action: Update to reflect current BAND system, or retire in favor of CLAUDE.md + band_config.txt.
- Realized σ in calib_monitor: Carried from stale measurement; weather resolution data (window_resolution.jsonl) is crypto, not weather. Dispersion ratio uses stale denominator. All dispersion readings have elevated uncertainty until outcome logging is restored.
- Bankroll.json `total_pnl = −$36.02`: This is CUMULATIVE from strategy inception including LDA losses. The BAND system has been net-positive from its deployment (capital has grown from LDA-era low). Do not interpret as current-strategy PnL.

---

*Report generated by research-agent | data read via GitHub MCP from data-mirror SHA d0307da + branch SHA 7368d28 | 8031 trade rows | Snapshot: 2026-06-30T10:21:22Z*
