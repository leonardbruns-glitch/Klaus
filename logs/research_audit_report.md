# Research Audit — 2026-07-14

**Run time**: 2026-07-14T~10:00Z
**Specialist reports read**: exec_audit (07:07Z ✓), calib_monitor (08:07Z ✓), gatekeeper (09:15Z ✓), pnl_ledger (23:37Z Jul 13 ✓) — all within 36h threshold
**Snapshot freshness**: Gatekeeper confirms 2026-07-14T08:59:16Z (age 16 min) — **PASS**
**System status**: `klaus systemd: active` per gatekeeper 09:15Z — **PASS**
**Data access note**: git fetch timed out (network-blocked in sandbox); raw mirror files obtained via GitHub MCP after exec_audit cutoff. data-mirror SNAPSHOT.md ts: 2026-07-14T10:15:16Z — PASS. Fill tape below incorporates data through 10:15Z (beyond exec_audit's 06:57Z view). Calib monitor independently flagged same MCP/network issue.
**Band flags (from band_config.txt, data-mirror 10:15Z)**: BAND_LIVE=False (line 284), BAND_NO_ENABLED=False (line 432), BAND_PAIR_FAV_ENABLED=True (line 512, gated by BAND_LIVE). UPDOWN-SNIPER live since Jul 13 10:46Z on owner floor waiver.
**Bankroll (data-mirror 10:15Z)**: capital $34.4446, daily_start $34.7427, total_pnl −$75.397.

---

## 1. PRIMARY BOTTLENECK FOR COMPOUNDING

**Bottleneck: ROI/turn on UPDOWN-SNIPER — the only active revenue engine.**

Compounding formula: equity × ROI/turn × turns/day.

| Dimension | Value | Source |
|---|---|---|
| Equity deployed | $34.69 (< ruin_floor $89.16) | exec_audit §6 |
| Turns/day | ~1.71× Jul 13 | pnl_ledger §2 |
| ROI/turn | **~−40%** Jul 13 | pnl_ledger §2 |
| Jul 14 net (midnight–10:15Z) | **−$0.30** | data-mirror bankroll.json |

The turns/day (1.71×) already match or exceed the badatmath benchmark (~1.0×). The equity level ($34.69) is constrained but not zero. The binding failure is ROI/turn: negative returns are being turned 1.71× per day, compounding the drawdown.

The Jul 13 ROI/turn figure (−40%) was dominated by SPRINT_LADDER (estimated −$46.79 from 2 shots, 0W/7L confirmed disarmed). Stripping the ladder, sniper-only Jul 13: 1W/5L visible, net ~−$4.60 (pnl_ledger §1). UPDOWN-SNIPER post-SIG_FLOOR (22:06Z Jul 13 restart): floored tape 6W/0L +$0.83, Jul 14 post-fix observable round-trips 4W/3L +57% WR (n=7, data-collection).

**The bottleneck resolves when sniper ROI/turn is confirmed positive.** The gatekeeper pre-registered gate for this is n≥100 fill-sim, ETA ~Jul 15 10:00Z (~25h from exec_audit time). This is the only live gate accumulating data today.

Dispersion premium inversion (calib_monitor S3, day 12) keeps the band dark independently. But the band is not the current compounding engine — the sniper is. The sniper's edge is calibration-independent (certainty-cell taker), so the dispersion inversion is not the active bottleneck today; it is a band-specific blocking condition.

---

## 2. EXISTING-SYSTEM OPTIMIZATION

**A. SIG_FLOOR fix (0.5bp/√s) — already deployed at 22:06Z Jul 13.** No action.
- Pre-fix: 7W/1L −$4.02 on sniper fills (exec_audit §4 note, gatekeeper context); settle-bug also contaminated labels.
- Post-fix floored tape: 6W/0L +$0.83 (exec_audit §4). A materially different result but n<10.
- Expected delta: unknown until n≥40. Confidence: low. Effort: done.

**B. Day-stop status (corrected from exec_audit ALERT 1).** Passive monitor only.
- Exec_audit ALERT 1 measured −$4.71 of −$6.00 from *go-live* (Jul 13 10:49Z) spanning the midnight boundary — a multi-day figure. Jul 14 day-stop resets at midnight UTC.
- Bankroll.json (data-mirror 10:15Z): daily_start $34.7427, capital $34.4446 = **−$0.30 of −$6.00 (5%) consumed today**. No urgency.
- Additional fills observed 09:34–09:49Z (beyond exec_audit window): MAKER NO cell (win), 0.98→0.95 (−$0.16), 0.92→0.88 (−$0.22, 3-second adverse exit). Net: roughly −$0.30 for Jul 14. Day-stop not at risk today.
- The 0.92→0.88 exit in 3 seconds is notable: "hold to redemption, never sell" policy from state_log 10:46Z entry appears to have a stop mechanism overriding it (same pattern as pre-fix 16:49 exit). UNKNOWN mechanism — monitor. Not a crisis at current loss magnitude.
- Delta: preserving trading day. Confidence: high. Effort: monitor.

**C. Certainty-cell NO maker positions (0.03–0.04 prices, multiple per day).** Not a leak.
- Two MAKER fills at extreme prices; expected rebate $0.013 total (pnl_ledger §3). Negligible.
- These appear to be sniper sub-strategy (NO certainty cells) operating alongside YES entries.
- No optimization available; position sizing and selection is already correct for fee avoidance at extremes.

**D. PAIR_FAV (n=9 post-guard, frozen).** No action while BAND_LIVE=False.
- Gatekeeper: G2b/G2c need n≥100; at ~50 posts/day when live = 8.3d from re-enable.
- Three independent blockers precede re-enable: G3 cross-tab, pair n≥40, explicit owner instruction. None close.

**E. D+1 market slate fully sum-gated (exec_audit §2).** Data only, not actionable.
- All 10 cities blocked for Jul 15 (Σask 0.89–1.014 inside band width). Only d+2 (Jul 16) viable (7 shadow fires seen).
- Confirms posting volume tomorrow = zero even if band re-enabled today.

**F. SPRINT_LADDER: correctly disarmed.** 0W/7L −$164.7 all-time. No rehabilitation path. Leave dark.

**Summary**: No execution or parameter optimization is available until SIG_FLOOR data matures to n≥40. The correct posture is monitor-only. The single adjustable knob is sniper stake size — see §7.

---

## 3. GATE PIPELINE REVIEW

From gatekeeper_report (09:15Z). Zero state transitions in 24h. All band gates frozen.

| Gate | Status | n | Primary blocker | Nearest acceleration lever |
|---|---|---|---|---|
| G1 BAND_YES | AMBIGUOUS | 934 | G3 cross-tab unresolved + disp_ratio inverted | G3 cross-tab (Experiment B) |
| G2a BAND_NO | AMBIGUOUS (live WR 39.2% = REJECTED) | 115 live / 0 new | live WR below threshold; BAND_NO_ENABLED=False | None — live WR is the verdict |
| G2b/G2c PAIR_FAV | COLLECTING | 9 post-guard | BAND_LIVE=False; frozen | Cannot accelerate without band re-enable |
| G3 FILLED_VS_FIRED | WATCH_ITEM | 75 filled | Co-fill cross-tab under clip-guard pending since Jul-11 | VPS operator 2h analysis |
| G5 THERMO | REJECTED | 125 | Done | — |
| G6 M1_BETA | REJECTED | 31 | Done | — |
| G7 SUM_POSTED | AMBIGUOUS | 382 | CI spans zero; BAND_LIVE frozen | CI blocker; n is sufficient |
| **UPDOWN-SNIPER** | **PRE-REGISTERED** | **~40-50 est.** | **n≥100 fill-sim unmet** | **Passive accumulation; ~Jul 15 10:00Z** |

**Nearest gate transition: UPDOWN-SNIPER n≥100, ETA ~Jul 15 10:00Z.**

Acceleration without degrading expectancy:
- Do **not** increase stake size to generate more fires — this amplifies losses at a potentially-negative ROI before edge is confirmed.
- Do **not** expand sniper scope (add assets) without backtesting — breadth without validation degrades expectancy.
- The fill-sim offline approach is correct design. The gate will clear by natural accumulation.
- The n=25 Experiment A tripwire (§6) provides an intermediate checkpoint ~22h out.

**Post-SIG_FLOOR sniper counting note (gatekeeper §context)**: The settle-bug fix (22:05Z Jul 13) corrected 84/196 prior resolution labels. The gatekeeper records day-1 net as 4W/1L −$4.29 (post-settle-fix accounting), while exec_audit counts 2W/5L (observable tape round-trips). Both cover different windows. For gate purposes, the clean post-SIG_FLOOR post-restart tape (from 22:06Z Jul 13) is the canonical data series; prior results are dead data.

---

## 4. ASSUMPTION ATTACK

**Load-bearing assumptions of the band system today:**

### Assumption 1: Dispersion premium persists (implied width > realized width)
**STATUS: FAILED**

calib_monitor S3 FIRES (day 12): disp_ratio7 ≤ 0.80 for 12 consecutive days. The ratio is not merely below the 1.10 threshold — it is inverted (market-implied temperature band width is *less* than realized bucket spread). The band market-maker is on the wrong side of dispersion risk at current prices.

Evidence supporting failure: exec_audit confirms 0 live posts since Jul 06 (band posting nothing is the mechanical consequence of the sum_gate blocking inverted-premium markets); research audit Jul 13 explicitly named S3 d11 as primary bottleneck; calib_monitor confirms identical values for 2 consecutive days (stability, not transient noise).

What could recover it: seasonal variance widening in late-July temperature distributions; LP repricing after sustained mispricing. Neither has a reliable ETA. The 12-day persistence eliminates transient-noise hypothesis.

**Verdict: This assumption is broken today. Band re-enable requires ≥3 consecutive days above 1.10. No credible evidence for near-term recovery.**

### Assumption 2: Fills are not adversely selected
**STATUS: THREATENED**

G3 WATCH_ITEM (n=75, trend-grade): realized band-leg ROI −75.8% vs simulated all-fires +7.6% = **−83.4pp adverse-selection gap** (exec_audit §4 carry). The band fills when the market moves against the quote, sits unfilled when it moves for. This is adverse selection, not execution noise.

UPDOWN-SNIPER shows the same pattern in miniature at n<40 (not conclusive): worst exit token 6224974 (entry 0.97, exit 0.73 = −24.7%) and token 7664067 (entry 0.99, exit 0.92 = −7.1%) — both entered at certainty-signal trigger and experienced immediate adverse moves.

SIG_FLOOR fix hypothesis: σ-collapse entries (fills occurring when volatility is collapsing = predictably adverse) are now gated by the 0.5bp/√s floor. Post-fix observable round-trips (22:06Z Jul 13 through 10:15Z Jul 14, data-mirror tape): 4W/3L (57% WR, n=7) — wins at +3.3%, +1.0%, resolution +$0.05, resolution +$0.05; losses at −2.1%, −3.1%, −4.3%. The 09:49 exit (0.92→0.88 in 3 seconds) is the worst post-fix loss and shares the "immediate adverse" pattern from pre-fix. n=7 = data-collection; 57% WR is above the 40% target but CI is wide. The 09:49 trade also reveals an unknown exit mechanism ("never sell" policy may have a stop override — worth VPS inspection).

**Verdict: Adverse selection is the systemic defect across both strategies. SIG_FLOOR is the current mitigation; early post-fix data (n=7, 57% WR) is trending positive but not decision-grade.**

### Assumption 3: Recycle velocity scales (RECYCLE099 convergence sells drive capital utilization)
**STATUS: N/A — untestable**

RECYCLE099 requires BAND_LIVE=True and resting positions on the book. Zero resting positions since Jul 06 (exec_audit §5: `maker_resting_state.json = {}`). Band shadow fires average 11–19/day (gatekeeper shadow table), suggesting volume would exist if band were live — but the mechanism is idle.

**Verdict: Cannot evaluate. Moot until Assumptions 1 and 2 are resolved.**

---

## 5. MARKET INTELLIGENCE (day 14 mod 3 = 2 — Platform Mechanics)

*Note: docs.polymarket.com and Polymarket announcements inaccessible from this sandbox (same network block that prevented git fetch). The following is derived from fill tape and specialist reports only. Delta vs state_log knowledge:*

**Maker rebate — most material finding:**
Two maker fills in 24h tape: 0.030 (35.17sh, $1.06) and 0.040 (40sh, $1.60). Expected rebate: ~$0.013 total (pnl_ledger §3: `shares × 0.05 × p × (1−p) × 0.25`). Near-extreme maker positions earn effectively zero rebate — the quadratic `p(1−p)` factor collapses below 0.03 at p=0.03.

**Cumulative rebate flag (pnl_ledger §3)**: Expected cumulative rebate $3.40 through Jul 13 exceeds $1.00 pUSD payout threshold. If no pUSD received since Jun 17 band start, eligibility or category-mapping issue may exist with Polymarket's maker-rebate pool. **This is a potential free capital leak requiring user verification.**

**Taker fee rates (observable, unchanged):** Sniper entries at 0.92–0.99 prices correctly target extreme zones where fee rate approaches 0% (consistent with CLAUDE.md and the 2026-03-30 fee reform documentation). No new fee category changes observed in the tape. The 8 new categories added 2026-03-30 appear stable; updown rates ~1.56% at 50% implied odds remain unchanged.

**No new weather cities, products, or platform mechanism changes detected in observable data.** Live site verification blocked — no delta can be confirmed from external announcements.

---

## 6. THREE EXPERIMENTS

### Experiment A: Post-SIG_FLOOR WR breakpoint at n=25 (~22h horizon)
**Hypothesis**: SIG_FLOOR fix eliminated σ-collapse adverse entries. If WR ≥40% holds at n=25 post-fix (22:06Z Jul 13 onward), this is the first falsifiable positive-edge signal.

| Item | Detail |
|---|---|
| Data | maker_fills_recent.log: post-22:06Z Jul 13 entries only; classified by SIG_FLOOR version flag |
| Time | Naturally accumulates; n=25 ETA ~Jul 15 08:00Z at 6–8 fires/day |
| Cost | $0 — passive observation |
| Success metric | Post-fix WR ≥40%, n=25, 90% CI lower-bound ≥0% |
| Decision-yes | Proceed to n=100 gate; no stake change. Begin documenting READY conditions |
| Decision-no (WR<30% at n=25) | Alert owner; consider sniper halt before more capital depleted |

### Experiment B: Winner's-curse co-fill cross-tab under Jul-05 clip-guard (2h VPS)
**Hypothesis**: The −83.4pp G3 adverse-selection gap is driven by a specific fill pattern fixable by the Jul-05 clip-guard (co-fills when market is already moving against quote). If co-fill rate under clip-guard < 30%, the guard closes the gap and band re-enable becomes discussable contingent on dispersion recovery.

| Item | Detail |
|---|---|
| Data | VPS: band_resolution_join.py output + STRUCT-BAND-Q fill logs Jul 01–06 (with/without clip-guard applied) |
| Time | 2h VPS operator analysis; gate-keeper has flagged this since Jul-11 22:15Z (4 days pending) |
| Cost | $0 capital; ~2h VPS operator time |
| Success metric | Co-fill rate under clip-guard < 30% of total fills |
| Decision-yes | Clip-guard closes adverse-selection gap → band re-enable becomes unblocked on G3 dimension (still requires disp_ratio recovery + pair n≥40 + owner instruction) |
| Decision-no | Adverse selection persists with clip-guard → band requires architectural change (passive limit orders only; no aggressive crossing) |

### Experiment C: Define disp_ratio recovery tripwire (0h — define today)
**Hypothesis**: The disp_ratio inversion may reverse seasonally (late-July temperature variance widening). Defining a precise numeric tripwire now eliminates ambiguity and delay when/if recovery occurs.

| Item | Detail |
|---|---|
| Data | calib_monitor disp_ratio7 daily values (already tracked; currently day 12 ≤0.80) |
| Time | 0h to define; tripwire is evaluated automatically in daily calib_monitor |
| Cost | $0 |
| Success metric | disp_ratio7 > 1.10 for **3 consecutive calendar days** |
| Decision-yes | Combined with G3 cross-tab (Experiment B) complete + pair n≥40 → publish dated BAND_LIVE re-enable proposal. Do not re-enable on dispersion alone. |
| Decision-no (remains inverted) | Maintain band dark indefinitely. Do not attempt re-enable for "morale." Data wins. |

---

## 7. SINGLE BEST ACTION

**Reduce UPDOWN-SNIPER per-fire position size to $2.00/fire (from current ~$5.30/fire) to extend the data-collection runway to the n≥100 gate without triggering the day-stop.**

**Compounding impact × P(success) / effort:**
- Impact: high — prevents day-stop from wiping 24h data accumulation windows; triples the number of observable fires before halt fires
- P(success): high — mechanical change with no model dependency; stake reduction cannot degrade WR
- Effort: low — single config parameter change

**Justification from specialist reports:**
- *Exec_audit ALERT 1* + *data-mirror bankroll*: Jul 14 day P&L = −$0.30 (5% of −$6 stop; day-stop urgency was a go-live-to-cutoff figure, not Jul 14). However, the 09:49Z fill (0.92→0.88, −$0.22) shows the sniper still generates adverse exits post-SIG_FLOOR. At $5.30/fire, a −24.7% exit (pre-fix worst) costs −$1.30; at $2.00/fire it costs −$0.49.
- *Gatekeeper*: n≥100 gate ETA ~Jul 15 10:00Z assumes continuous sniper operation. Each day-stop fired = 24h of data lost = ETA slips by a day while capital erodes at ~$0.05-1.30/halt-event.
- *PnL ledger §1*: The two largest sniper losses Jul 13 (−$2.89 on 39sh entry, and −$1.39 on 5.4sh entry) were stake-amplified. At $2/fire, these would have been −$0.15 and −$0.52 respectively.
- *Post-fix evidence* (data-mirror tape, n=7 post-fix): 4W/3L 57% WR is above target but n<40. This is not yet the evidence base for maintaining current stake. Stake should match data confidence level.

**Concrete first step (PROPOSED ACTION — human review required):**
Edit sniper configuration `per_fire_stake` (or equivalent) from ~$5.50 to $2.00. Restart with live traffic. Run to n=25 (Experiment A checkpoint, ~22h). If WR ≥40% at n=25: maintain $2 to n=100. If WR ≥40% confirmed at n=100: restore to $5 for full capital deployment.

---

## PROPOSED ACTIONS (human review)

1. **[IMMEDIATE — SNIPER SIZING]** Reduce per-fire stake to $2.00 until n=25 post-SIG_FLOOR validates WR ≥40% (see §7). Cited: exec_audit ALERT 1, gatekeeper sniper gate ETA, pnl_ledger §1 stake-amplified losses.

2. **[IMMEDIATE — REBATE VERIFICATION]** Verify pUSD wallet for maker rebate deposits since Jun 17. Cumulative expected $3.40 > $1.00 payout threshold per pnl_ledger §3. If zero received, contact Polymarket support with maker category mapping evidence. Free capital.

3. **[2H VPS — BAND GATE]** Complete G3 co-fill cross-tab under Jul-05 clip-guard (Experiment B). This is the mandatory prerequisite for any BAND_LIVE re-enable discussion. Pending since Jul-11 22:15Z (4 days overdue). Blocking the entire band gate pipeline.

4. **[PASSIVE — BAND MONITOR]** Lock in Experiment C tripwire: disp_ratio7 > 1.10 for ≥3 consecutive calendar days = trigger for BAND_LIVE re-enable proposal. Requires *also*: G3 cross-tab complete + pair n≥40 + owner instruction. Do not re-enable on dispersion signal alone.

5. **[VPS INSPECTION — SNIPER STOP MECHANISM]** Policy spec (state_log 10:46Z): "hold to redemption, never sell." But fill tape shows mid-window SELL exits in 3–17 seconds in multiple pre- and post-fix trades. Inspect updown_sniper.py for any stop-loss or consecutive-loss halt that forces a market-sell mid-window. If this mechanism exists and triggers prematurely, it is likely the primary driver of sniper losses — stops are harvesting adverse noise in positions that would redeem at 1.0. Low effort, high VoI. Cross-reference the 09:49Z exit (0.92→0.88 in 3s) and 16:49Z pre-fix exit (0.97→0.73 in 3s) as specific examples.

6. **[NO ACTION — SPRINT_LADDER]** Confirmed disarmed, 0W/7L, no rehabilitation path. Leave dark.

---

*Research audit by research-agent@Klaus — 2026-07-14*
*Primary bottleneck: UPDOWN-SNIPER ROI/turn (post-SIG_FLOOR n=7 57% WR — early positive but not decision-grade; stop mechanism unknown) | Best action: reduce sniper stake to $2/fire + inspect stop-sell mechanism*
