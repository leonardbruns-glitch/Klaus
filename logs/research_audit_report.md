# Klaus Research Audit — 2026-07-05T10:45Z

**Date:** 2026-07-05 | **Snapshot:** 2026-07-05T10:23:06Z (fresh ✓) | **System:** `active` ✓  
**Bankroll:** $115.99 cash (gatekeeper 09:30 UTC; daily_start $87.17) | **Open positions:** 0  
**Active engines:** PAIR_FAV only (BAND_NO disabled 07-02; standalone YES paused 07-03)  
**Market intelligence rotation:** Day 5 → 5 mod 3 = **2** → platform mechanics  

**Specialist report freshness:**
| Report | Timestamp | Age at this run | Status |
|---|---|---|---|
| exec_audit_report.md | 07:11 UTC | 3.6h | ✓ |
| calib_monitor_report.md | 08:10 UTC | 2.6h | ✓ |
| gatekeeper_report.md | 09:30 UTC | 1.25h | ✓ |
| pnl_ledger_report.md | 00:39 UTC Jul 4 (covers Jul 3) | ~34h | ✓ within 36h |

---

## §1 — Primary Bottleneck

**Bottleneck: Equity deployed = near zero.** Ranking: **equity deployed** > turns/day > ROI/turn > fills > calibration > dispersion edge.

The exec audit (07:11 UTC) is unambiguous: **2026-07-05 is a posting collapse day** — 0.053 posts/cycle, 4 posts and 1 fill ($0.44 notional) in 7 hours. Zero resting maker capital (sole resting order is a SELL_EXIT, not an active maker bid). This is the system floor.

**Causal chain:**
1. PAIR_FAV is the sole posting engine; it fires only when `qy + qn ≤ 0.90` simultaneously for both legs of a city/day slot.
2. Today, `sum_gate` is the dominant rejection reason — market-bid sums for qualifying city/day pairs are ≥ 0.90 (efficient pricing, tight spreads in July heat markets).
3. Neither alternative engine can compensate: BAND_NO_ENABLED=False (live n=51 WR 39.2% — winner's-curse confirmed, gatekeeper Advisory §1); standalone YES paused at BAND_YES_LIVE_MIN_DOUT=9 (live/shadow gap fatal: shadow +8% vs live −45% Jun 26–Jul 3, gatekeeper §Gate1).
4. Root cause of no alternative: dispersion gauge is **broken for 3 consecutive days** (calib_monitor Alerts S3/S4). The YES re-enable condition (disp_ratio ≥ 1.10 × 5 days) cannot be evaluated — the gauge produces degenerate output due to isotonic plateau.

The bottleneck is therefore a **two-layer stall**: operational (sum_gate starving pair_fav) atop structural (gauge broken, alternatives correctly locked). Fixing the operational layer without the structural fix would mean re-enabling edges that remain unconfirmed.

The metric that resolves both: **isotonic refit** → gauge restored → disp_ratio measurable → YES/NO re-enable decision path re-opens.

---

## §2 — Existing-System Optimization

From the four specialist reports, five items with expected delta, confidence, and effort:

### 2a. RECYCLE099 pipeline seeding
- **Finding (pnl_ledger):** RECYCLE099 was 90% of Jul 3 P&L (+$10.42, 4 exits at 31–36¢/sh spread). Today's exec audit shows 0 resting positions — pipeline empty, nothing to converge.
- **Root cause:** Pair_fav posting collapse = no new positions being opened = RECYCLE099 idle.
- **Expected delta:** If posting rate returns to Jul 3 levels (0.787 posts/cycle), RECYCLE099 would generate ~$8–12/day in convergence exits based on Jul 3 actuals.
- **Confidence:** High (Jul 3 validated the mechanism). **Effort:** Indirectly requires fixing sum_gate starvation (§2b).

### 2b. PAIR_FAV_SUM_MAX sensitivity (requires shadow analysis first)
- **Finding (exec_audit §3):** sum_gate is the 2nd-most-common md_shadow reject reason. BAND_PAIR_FAV_SUM_MAX = 0.90 may be over-tight if average rejected qy+qn falls in the 0.90–0.93 range (still ≥7¢/sh locked spread).
- **Expected delta:** 3–5× fire rate increase if gate is over-tight; zero EV degradation if rejected pairs cluster near 0.90. At Jul 3 fill rate (~7/day), this could push to 20–35 fills/day and materially increase turns/day toward the 1.0× badatmath target.
- **Confidence:** Unknown — requires shadow-log analysis of rejected-sum distribution before acting. **Effort:** Low (VPS shadow join, ~2h). **Capital risk: zero** (shadow analysis only).

### 2c. City expansion marginal value (SPRINT30)
- **Finding (state_log 07-03, exec_audit):** Universe expanded 5→10 cities for pair_fav. Yet exec_audit shows posting collapse today. Breadth is not the constraint — sum_gate is.
- **Expected delta:** Additional cities provide no lift when sum_gate blocks all slots in all cities. Zero marginal value until sum structure relaxes.
- **Confidence:** High. **Action:** None — over-expanded universe does not hurt but is not the lever today.

### 2d. SUM_POSTED 0.70–0.85 slice validation
- **Finding (gatekeeper §Gate7):** ~3,056 fires in this sub-range. CI blocked (VPS Gamma join not run). If this slice outperforms, it validates current gate calibration. If it underperforms, tighter gating may improve ROI/turn.
- **Expected delta:** Potentially 5–15% ROI/turn shift depending on direction. High value-of-information.
- **Confidence:** Blocked — needs VPS. **Effort:** Medium (VPS resolution join, ~4h).

### 2e. Maker rebate pUSD verification
- **Finding (pnl_ledger §3):** Expected cumulative rebate $2.49 (> $1 minimum since at least Jun 29). No confirmed payout logged across 3+ reporting cycles.
- **Expected delta:** $2–$3 recovery if unreceived. Small but zero-effort.
- **Confidence:** Medium. **Effort:** 5 minutes (wallet check). **Action candidate.**

---

## §3 — Gate Pipeline Review

From gatekeeper_report.md (09:30 UTC). **0 READY gates today.**

| Gate | Status | n | What would accelerate to READY |
|---|---|---|---|
| PAIR_FAV YES | COLLECTING | 9 res | ~2 fires/day. ETA n=40: ~15d. Relaxing sum_gate (§2b) shortens ETA if validated. |
| PAIR_FAV NO | COLLECTING | 9 res | Same. Point estimate +3.7% ROI (less compelling than YES +20.7%); both n=9 noise. |
| FILLED_VS_FIRED | COLLECTING | 24 fills | Passive. **ETA n=40: ~2.3 days.** Nearest to threshold — no action needed. |
| BAND_YES | AMBIGUOUS | 934 res | CI straddles 0. Live/shadow gap fatal. Re-enable requires: gauge repaired + disp_ratio ≥ 1.10 × 5d + fill-confirmed no winner's-curse. All three blocked. |
| BAND_NO d+1 | AMBIGUOUS | 115 shadow / 51 live | Shadow AMBIGUOUS masks live WR=39.2% → winner's curse. Effectively REJECTED on live data. BAND_NO_ENABLED=False correct indefinitely. |
| SUM_POSTED 0.70–0.85 | COLLECTING | ~3,056 fires | VPS slice-join is the sole blocker. n not the bottleneck. |
| THERMO | REJECTED | n=125 | Complete — no action. |
| M1β | REJECTED | n=31 | Complete (param reverted 2813daa1e) — no action. |

**Nearest to action:** FILLED_VS_FIRED at n=24/40 (~2.3 days). When crossed, EVOLVE VPS must run fill-vs-fire ROI divergence check. This passively accumulates; no breadth action required.

**What not to do:** Do NOT relax sum_gate before shadow analysis (§2b) confirms rejected pairs still lock positive spread. The current ~15-day PAIR_FAV ETA is driven by low fire rate, not poor data quality.

---

## §4 — Assumption Attack

### Assumption A: Dispersion premium persists (implied-σ < realized-σ)
- **Load-bearing for:** All band YES/NO legs. The band earns by selling overpriced probability wings relative to actual temperature dispersion.
- **Today's evidence (calib_monitor):**
  - Direct gauge: disp_ratio 7d median = 0.817 (measured Jun 28–Jul 2, 5 points all < 1.0). Threshold = 1.10.
  - Proxy σ cleaned (Jul 5): 0.885°C vs 0.994°C baseline = **−10.9%. Fourth consecutive below-baseline day** (trend: −4.4%, −8.9%, −10.9%).
  - Gauge broken for 3 consecutive degenerate days (Jul 3–5: 0/16 finite ratio pairs today).
- **Threat: HIGH.** Both measured ratio (0.817 over 5 days) and proxy trend (monotonically declining) are hostile. Gauge breaking at this moment prevents confirming recovery or worsening since Jul 2. July heat-wave (Munich proxy σ = 1.795°C, genuine wide uncertainty) could cut either way — the market may correctly price that wide uncertainty, not under-price it.

### Assumption B: Fills are not adversely selected (winner's-curse absent)
- **Load-bearing for:** PAIR_FAV YES fills specifically.
- **Today's evidence (exec_audit, gatekeeper):**
  - Fill-side YES dominance: 79% by count and notional, persistent across 3.5 days.
  - **BAND_NO live/shadow gap: WR 39.2% live vs 68.7% shadow at comparable quotes (~0.655–0.678). This is a 29.5pp gap** — the clearest winner's-curse signal in the system. The live WR implies EV ≈ −42% vs shadow +1.3%. (gatekeeper Advisory §1)
  - FILLED_VS_FIRED gate at n=24/40: measurement mechanism exists but threshold not crossed yet.
- **Threat: MEDIUM-HIGH.** The BAND_NO gap is damning. The analogous PAIR_FAV YES measurement is pending (n=9 resolved). If the same pattern manifests for YES, the pair_fav engine needs quote widening. Monitor at n=40.

### Assumption C: RECYCLE099 velocity scales (pipeline seeds and converges predictably)
- **Load-bearing for:** 90% of Jul 3 realized gains (+$10.42).
- **Today's evidence (exec_audit, state_log):**
  - 0 resting maker orders today. RECYCLE099 pipeline empty — nothing to converge.
  - Jul 5 lowest-fire session: 4 posts, 1 fill ($0.44) in 7h.
  - The Jul 3 RECYCLE099 gains were pre-existing positions from earlier periods — not fresh Jul 3 seeding. Today's zero-posting collapses tomorrow's RECYCLE099 pipeline.
  - SPRINT_LADDER contributed on Jul 4: Shanghai shot WON (+$63.50 net per state_log Jul04 22:16), explaining the $44.92→$115.99 capital jump between exec_audit (07:11) and gatekeeper (09:30) snapshots.
- **Threat: HIGH TODAY, structural.** Circular dependency: pair_fav feeds RECYCLE099; RECYCLE099 generates P&L; sum_gate blocks pair_fav. A posting collapse day also drains next-day RECYCLE099 pipeline.

---

## §5 — Market Intelligence (Platform Mechanics)

**Rotation: Day 5 mod 3 = 2 → [2] Fee schedule / maker-rebate / liquidity-rewards changes.**

*Note: Direct docs.polymarket.com / Discord access unavailable from this agent environment. Reporting deltas visible in data vs prior state_log knowledge.*

**Delta vs known state:**

1. **BTC daily-range ladders dead** (state_log Jul03 sweep): makerBaseFee=takerBaseFee=1000bps confirmed. This market class carries ~20% round-trip fee — systematically unviable. Do not revisit.

2. **NEG_RISK_ARB: Σask = 1.000 for 9+ consecutive days** (state_log Jul03). No-arb probe active today (shadow_summary: 610 rows, last 10:21 UTC). Zero arbitrage opportunities detected across the scanning window. This appears structural — Polymarket market makers have tightened NEG_RISK markets efficiently. No allocation warranted.

3. **Maker rebate (pUSD) — action required**: Cumulative expected $2.49 per pnl_ledger. Minimum payout threshold ($1 pUSD) exceeded since Jun 29 report. Three consecutive reporting cycles with no confirmed receipt. Owner: verify pUSD wallet balance. If unreceived, submit cf-ray headers from relevant fills to Polymarket Discord #support. The BAND_MERGE fills (p ≈ 0.45–0.50, peak p(1-p)) are the rebate-earning entries; RECYCLE099 at p=0.99 earns near zero per-share.

4. **Weather binary fee structure**: No fee-spike events detected in today's fill tape (exec_audit: no network error alerts, all 24 fills completed). Fee structure appears unchanged vs last known state.

5. **Cloudflare WAF posture**: No CF-block events in today's shadow data. curl_cffi + QuantVPS stack operational.

**Knowledge gap:** Cannot confirm if Polymarket announced maker-rebate structure changes or new weather city additions since Jun 30. Owner should check Discord #announcements and docs.polymarket.com/makers for any July fee/reward changes before the next city-expansion decision.

---

## §6 — Experiments

### Experiment A: PAIR_FAV Sum-Gate Sensitivity Scan
- **Hypothesis:** BAND_PAIR_FAV_SUM_MAX = 0.90 is over-restrictive — the majority of rejected pairs have qy+qn in the 0.90–0.93 range (still locking 7–10¢/sh spread), and relaxing to 0.87 would increase fire rate 3–5× without degrading per-fire EV.
- **Data:** Extract all sum_gate=REJECT rows from md_shadow or band_struct_lite logs on the VPS. Compute distribution of (qy+qn) for rejected events. Compare shadow EV on rejected-boundary vs accepted-core pairs.
- **Time/Cost:** 2h VPS analysis. Zero capital.
- **Success metric:** ≥50% of rejected pairs have (qy+qn) ≤ 0.93 AND shadow EV on that slice clears zero at n≥40 simulated posts.
- **Decision if YES:** Lower BAND_PAIR_FAV_SUM_MAX 0.90 → 0.87 in shadow first; validate at n=40 shadow fills before live. Expected: turns/day 0.38× → ~0.8–1.0× (approaching badatmath benchmark), which refills RECYCLE099 pipeline.
- **Decision if NO:** Gate correctly calibrated. Accept current posting rate as market-structural. Shift focus entirely to Experiment B (isotonic refit).

### Experiment B: Isotonic Refit Cron Diagnosis + Manual Refit
- **Hypothesis:** The VPS live-refit cron is broken — n_live frozen at 1,037 for 26 days (zero increments). A manual refit with current live data breaks the 0.30–0.90 isotonic plateau, restores non-degenerate dispersion gauge output, and re-opens the YES re-enable decision tree.
- **Data:** VPS cron status + single refit run with live data. Validate on held-out resolved data (Jun–Jul window).
- **Time/Cost:** 2–4h VPS owner time. Zero capital.
- **Success metric:** (1) n_live increments post-refit; (2) isotonic grid 0.30–0.90 shows ≥3 distinct calibrated values (plateau broken); (3) next calib_monitor run produces non-degenerate POST_PEAK ratio pairs for ≥50% of allowlist cities; (4) disp_ratio computed for at least one day with non-degenerate result.
- **Decision if YES:** Dispersion gauge restored. Schedule daily refit. Disp_ratio measurement resumes; the 5-day re-enable clock for YES can start ticking. Highest-value unlock in the system.
- **Decision if NO (data pipeline broken, not cron):** Diagnose live-data ingestion separately. Assess if band system can operate on proxy-σ alone — not recommended given proxy σ is also declining 4 consecutive days.

### Experiment C: FILLED_VS_FIRED Divergence Check at n=40
- **Hypothesis:** Filled pair_fav YES positions have a realized win rate materially lower than the shadow (all-fires) YES win rate — confirming winner's curse on YES fills analogous to the BAND_NO gap (shadow 68.7% vs live 39.2%).
- **Data:** n=24 fills currently. ETA n=40: ~2.3 days at ~6.9 fills/day (passive). Run EVOLVE VPS band_resolution_join.py sliced to filled positions vs all simulated fires for same market class.
- **Time/Cost:** 2.3 days passive + 1h VPS analysis. Zero capital.
- **Success metric:** |filled-WR − fires-WR| > 5pp with CI lower bound excluding zero.
- **Decision if confirmed (adverse selection):** Widen pair_fav YES bid quotes. Investigate whether specific cities or days_out drive the gap. Decision-grade evidence to adjust BAND_PAIR_FAV_YES_MIN/MAX.
- **Decision if not confirmed:** Fill quality clean. YES-fill dominance (79%) is structural, not adversarial. Current aggressiveness appropriate.

---

## §7 — Single Best Action

**Action: VPS owner to diagnose and run the isotonic refit cron (Experiment B).**

**Justification from specialist reports:**
- calib_monitor Alert S4 (explicit recommendation): *"Recommended action (VPS owner): verify live-refit cron health; run manual plateau-breaking refit with current live data; validate on held-out resolved data before deploying."* Deployed config 29 days stale; candidate 26 days stale. n_live frozen at 1,037 for 26 days.
- calib_monitor Alert S3: *"Re-enable condition cannot be evaluated until the gauge is restored."* Third consecutive degenerate day. The gauge is not measuring; it is reporting a stale historical reading.
- gatekeeper §Gate1 + §Gate2: Both BAND_YES and BAND_NO re-enables contingent on disp_ratio ≥ 1.10 × 5 days. Structurally impossible to evaluate without a working gauge.
- pnl_ledger §2: turns/day = 0.33× vs 1.0× badatmath. Binding lever = additional posting engines, which requires dispersion confirmation.

**No gates hit READY this run** (0 READY per gatekeeper). The two newly-REJECTED gates (THERMO, M1β) are already actioned by EVOLVE. The default candidate per audit instructions is therefore the highest compounding-impact structural unlock.

**Impact × P(success) / effort:**
- Impact: Unlocks the entire YES/NO re-enable decision tree. Estimated 0.5–1.0× additional turns/day from YES+NO band posting if disp_ratio recovers.
- P(success): ~75%. The 26-day n_live freeze most likely indicates a cron misconfiguration. The isotonic algorithm is demonstrably functional at grid=1.0 (ECE=0.019 confirms calibration in the high-confidence zone).
- Effort: 2–4h VPS owner time.

**Concrete first step:** `systemctl status <live-refit-cron-unit>` on the VPS. If dead/stopped: `systemctl restart`, then `python3 live_refit.py --dataset live --validate held-out` manually. Report n_live before/after. If n_live remains frozen after restart, investigate the live-data ingest pipeline feeding the refit script.

---

## PROPOSED ACTIONS (human review)

*No strategy code changes proposed. All items require human review or VPS-owner action.*

| Priority | Action | Source | Capital risk | Effort |
|---|---|---|---|---|
| 1 | Diagnose VPS live-refit cron; run manual isotonic refit with current live data; validate before deploying. | calib_monitor S3+S4 | Zero | 2–4h VPS |
| 2 | Run PAIR_FAV sum-gate sensitivity scan on VPS (md_shadow rejected-sum distribution). If rejected qy+qn clusters at 0.90–0.93, evaluate SUM_MAX 0.90→0.87 in shadow first. | exec_audit §3 | Zero (shadow) | 2h VPS |
| 3 | Verify pUSD maker rebate receipt ($2.49 est. cumulative). Raise with Polymarket #support if not received. | pnl_ledger §3 | Zero | 5 min |
| 4 | At n=40 fills (~2.3 days): run FILLED_VS_FIRED divergence check on VPS. Adverse selection confirmation or clearance determines quote aggressiveness for pair_fav YES. | gatekeeper §Gate3 | Zero | 1h VPS at trigger |
| 5 | Confirm METAR_LOCKOUT_TEMP_FLOOR revert (0.2→0.5°C, commit 2813daa1e) is active in live config; acknowledge 7-day standing item closed. | gatekeeper §Gate6 | Zero | 5 min |
| 6 | Review SPRINT_LADDER sleeve posture. State_log Jul03 honest logging: P(reach $10k) ≈ 1–3%, modal = sleeve lost days 1–5. Ensure reserve floor ($20 free-USDC) and daily-loss halt (wired in commit 2813daa1e) are both active and correctly parameterized. | state_log | Low (sleeve-bounded) | Review only |

---

*research-agent@klaus | 2026-07-05T10:45Z | Branch: claude/find-lag-parameter-rFQ0N*
