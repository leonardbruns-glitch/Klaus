# Research Audit — 2026-08-06T1030Z

**STALL (day 13) — ABORT condition met: `system_status.txt` shows `failed/unknown` (not active). Owner-disabled daily/liveness timers; loop WEEKLY-ONLY since 2026-07-26 EVOLVE. Analysis below uses today's specialist reports + shadow data; no fabrication on dead strategy data.**

---

## Specialist Reports

| Report | Timestamp | Status |
|---|---|---|
| exec_audit_report.md | 2026-08-06T07:10Z | ABORT — systemd failed day 13; no fills; all band/maker/STWA paths disabled |
| calib_monitor_report.md | 2026-08-06T08:11Z | ABORT — no pricer_eval data (band loop dead 13d); DISPERSION GAUGE last=0.781 (11d stale) |
| gatekeeper_report.md | 2026-08-06T09:07Z | ABORT — STALL day 17; band dark day 31; capital $88.75 < ruin_floor $89.16 (−$0.41) |
| pnl_ledger_report.md | 2026-08-05T23:37Z | STALL — 17 consecutive zero-fill days; capital $88.750373 unchanged |

All four reports within 36h window. No raw-mirror fallback required.

---

## 1. Primary Bottleneck

**Equity deployed = $0 — every factor in the compounding formula is zero simultaneously.**

Ranking: equity deployed (0) > turns/day (0) > ROI/turn (unmeasurable) > fills (0).

Three co-equal blockers prevent any deployment:
1. **System down** (13 days) — no turns possible
2. **Capital $88.75 < ruin_floor $89.16** (−$0.41) — mechanical engine block even if system restarted
3. **No validated live path** — BAND_LIVE=False (day 31), UPDOWN_STOP permanent (graveyard #15), BAND_NO_ENABLED=False (7d realized WR 39.2%)

These are not independent. Even resolving #1 and #2, there is no path to capital deployment because the band system requires a winner's-curse-aware redesign (G3: filled ROI −75.8% vs sim +7.6%, n=75, CI=[−75.0%, −34.2%]) before naked YES/NO band legs can resume.

PAIR_FAV is the sole surviving band path with co-fill logic that is theoretically adverse-selection-resistant (both legs fill together or neither fills). n=9 post-guard, COLLECTING, accrual rate zero while band dark.

---

## 2. Existing-System Optimization

No new fills in 17 days. No optimization signal is actionable. Two structural observations from available data:

**A. Candidate isotonic curve has material tail shift (+16.8pp at grid 1.0)**
From calib_monitor §4: deployed curve (2026-06-06, age 61 days) vs candidate (2026-07-23 fit, n=3,392): material diffs at 0.95 (+5.5pp) and 1.00 (+16.8pp). The candidate raises calibrated probability for near-certain events — relevant if/when band trading resumes at extreme odds (BAND_ASK_MIN=0.05 end of ladder). Expected delta: small (those tail cells are rare), confidence: medium (isotonic fit direction credible), effort: zero (VPS cron deploys automatically on restart).

**B. ruin_floor $89.16 — static or dynamic?**
If floor is derived from a high-water mark that hasn't updated since 07-24 (system down, zero trades), it may have drifted below $88.75 without the loop knowing. If static, $0.42 injection is the cheapest possible unblock. This determination costs one grep on VPS. Current audit cannot resolve it. Expected delta: unlocks all band paths IF static and injected (or dynamic and already below $88.75). Confidence: N/A pending check. Effort: 10 min.

---

## 3. Gate Pipeline Review

From gatekeeper_report (2026-08-06):

| Gate | n | WR | Status | Notes |
|---|---|---|---|---|
| G1 BAND_YES | 934 | 15.3% | AMBIGUOUS | Sim ROI UB only (winner's curse G3) |
| G2a BAND_NO d1 | 115 | 68.7% | AMBIGUOUS | NO disabled; adverse selection unresolved |
| G2b PAIR_FAV YES | 9 | — | COLLECTING | n<<40; band dark day 31 |
| G2c PAIR_FAV NO | 9 | — | COLLECTING | n<<40; band dark day 31 |
| G3 FILLED-vs-FIRED | 75 | 17.3% filled | WATCH_ITEM | Winner's curse confirmed |
| G5 THERMO_MAKER | 125 | — | REJECTED | Human directive |
| G6 M1_BETA_LOCKOUT | 31 | 74.2% | REJECTED | Human directive |
| G7 SUM_POSTED | 382 | — | AMBIGUOUS | Sim ROI UB only |
| G8 UPDOWN_CROSSING | 127 | 95.3% | REJECTED | Graveyard #15 (killed 07-26) |

**No gate is near READY.** G2b/c PAIR_FAV are the only COLLECTING gates, accrual rate zero. ETAs paused indefinitely (band dark + system failed).

To accelerate accumulation without degrading expectancy: PAIR_FAV needs band restart first. Breadth (additional cities in BAND_CITY_ALLOW) would speed G2b/c accrual when live, but the band restart decision precedes that optimization.

**The multiasset updown_sniper shadow review was due 2026-08-02** per state_log 07-26 ("multiasset cells stay COLLECTING as graveyard-contradiction ledger only (review 08-02)"). That review never ran (daily timers disabled). 11 additional days of shadow data have accrued (snap files through 08-05, ~200k snaps/day). This review is overdue and should be a standing item for the next weekly EVOLVE.

---

## 4. Assumption Attack

### A. Dispersion premium persists
**UNVERIFIABLE — pre-existing alert carried, worsening.**
Last disp_ratio7 = 0.781 (2026-07-26, 11 days stale). Alert threshold: 1.10. Last 5 monitored days (07-17..07-22): 2/5 cleared 1.10 — band trigger NOT met. The 11-day gap is the longest unmonitored stretch since the band went dark (07-06). Without pricer_eval data (band loop dead), the gauge cannot update.

Shadow evidence (indirect): today's minmax_coherence shows min_sum_ask across cities of 1.056–1.47, suggesting the market IS pricing uncertainty (sum_ask > 1.0 means dispersion exists). Miami d+1 at 1.056 is tight (near 1.0, implying market sees little uncertainty → low disp_ratio for that city). Tokyo d+2 at 1.468 and Paris d+2 at 1.470 imply wider distributions. This is consistent with disp_ratio being heterogeneous across cities/days — some cells may have recovered above 1.10, others may not.

**Risk**: the 11-day gap means the band trigger could have been met and missed.

### B. Fills are not adversely selected
**FALSIFIED (G3, n=75, CI=[−75.0%, −34.2%]).**
Winner's curse confirmed on-fill. Exception: co-filled PAIR_FAV (Σ locks riskless payout regardless of which leg fills first). PAIR_FAV is the one structural path that avoids this failure mode. All other naked YES/NO band legs remain adverse-selection-blocked until a structural fix is validated on live fills.

### C. Recycle velocity scales
**UNTESTABLE.** RECYCLE099 requires live band posts. Band dark day 31 → zero data → velocity unmeasurable. Assumption neither confirmed nor refuted.

---

## 5. Market Intelligence — Competitor Posture (day 6 mod 3 = 0)

**badatmath_watch fills today (shadow, by 10:28 UTC):**

| Metric | Value |
|---|---|
| Total fills (today) | 124 |
| Unique events | 27 |
| Lag: <30s | 16 (13%) |
| Lag: 30–60s | 21 (17%) |
| Lag: 60–120s | 44 (35%) |
| Lag: >120s | 28 (23%) |
| Median detect lag | 91s |
| Average price | 0.307 |
| Average size | 29.9 sh |
| Max size | 129 sh |
| Total volume | 4,035 sh |

**Key deltas vs state_log 07-26 last known:**
- badatmath fill rate unchanged (~10-15 fills/hr at this time of day); still active in the band's YES-taker zone (0.20–0.50 price range = 93/124 fills)
- Detect lag median 91s — squarely in our theoretical edge window (30–120s post-fill detection); we are not structurally outpaced on lag
- Cities active today: Amsterdam, Lucknow, Beijing, Chengdu, Chicago, Helsinki, Madrid, Tokyo, Shanghai, Miami. Of these, Chengdu, Beijing are in BAND_CITY_ALLOW — badatmath is filling in our city subset
- Lucknow: 169.5 sh fill @ 0.26, lag 128s — large fill in a city outside our allow set; suggests opportunity we are not monitoring

**Leaderboard wallet teardown**: data-api not accessible from sandbox. Carrying forward last known from state_log: top badatmath-linked wallet ~$4k–10k/day volume; strategy unchanged (YES-taker on morning price moves, hold-to-redeem pattern). No new on-chain data available this run.

**Delta from prior week**: shadow data shows continuous fill activity through the entire 13-day system outage. The market did not pause. Estimated badatmath volume in our absence: ~124 fills/day × 13 days = ~1,600 fills in our cities we did not compete on. At their avg fill size $9/fill (29.9 sh × $0.307), that's ~$14k in band territory. Our queue position in those markets is unfilled and unmonitored.

---

## 6. Experiments

**EXP-A: Ruin_floor derivation (cheap/fast/blocking)**
Hypothesis: ruin_floor $89.16 is either (a) static, requiring $0.42 injection, or (b) dynamic (HWM-based), already ≤$88.75 due to 13 days without a HWM update.
Data: `grep -n ruin_floor strategy/stwa_engine.py` on VPS.
Time: 10 min. Cost: $0.
Success metric: static constant vs formula.
Decision-if-static: deposit $0.42 or amend charter. Decision-if-dynamic-already-below: restart unblocks capital dimension immediately.
**Status: Deferred (VPS SSH required).**

**EXP-B: Overdue multiasset updown_sniper shadow review**
Hypothesis: post-kill shadow accrual (11 days, ~200k snaps/day, 5 assets) provides enough data to confirm or reject the multiasset cells as graveyard-contradiction evidence; one asset (eth, last known 35/35W) may have regressed.
Data: shadow_grade.py --refetch on snaps from 07-27..08-05.
Time: 15 min. Cost: $0.
Success metric: per-asset WR/CI vs breakeven; any clean asset is graveyard-contradiction evidence (but per-registered: "multiasset cells stay COLLECTING as graveyard-contradiction ledger only").
Decision-if-clean-cell-deteriorates: class kill fully confirmed, no rescue instrument. Decision-if-clean-cell-holds (eth): update experiments.jsonl, no live effect.
**Status: Deferred (VPS SSH required).**

**EXP-C: dispersion_ratio recovery check via settled data**
Hypothesis: the 11-day unmonitored window may have produced ≥2 consecutive days at disp_ratio ≥1.10, meeting the pre-registered band restart trigger.
Data: settled_disp_ratio.py reading hot shadow dirs 07-27..08-05 (data exists — minmax_coherence and maker_flow loggers continued running).
Time: 30 min (re-run script on VPS). Cost: $0.
Success metric: disp_ratio7 for each settled date, trend.
Decision-if-trigger-met (≥2/5 ≥1.10): capital/system block still applies, but adds urgency. Decision-if-not-met: band dark status confirmed correct.
**Status: Deferred (VPS SSH required).**

---

## 7. Single Best Action

**SSH to VPS → check ruin_floor derivation → if static, deposit $0.42 to clear the capital block.**

From gatekeeper_report: capital $88.75 < ruin_floor $89.16 (−$0.41), all band paths mechanically blocked.

Rationale: The $0.41 gap is the shallowest blocker — cheaper to resolve than any strategy change, code commit, or gate wait. If ruin_floor is static at $89.16, a $0.42 USDC deposit eliminates it and makes service restart the only remaining first-order action. No code changes, no gate waits, no strategy decisions required for that step. If ruin_floor is dynamic and already ≤$88.75, the capital block doesn't exist and restart alone suffices.

Prior recommendation (08-05 audit) was identical. No action has been taken. The opportunity cost of continued system downtime accumulates: badatmath fills ~124/day in our markets; disp_ratio unmonitored 11 days; multiasset shadow review overdue since 08-02.

Concrete first step: `SSH 45.85.251.173 → grep -n ruin_floor strategy/stwa_engine.py`

---

## PROPOSED ACTIONS (human review)

1. **EXP-A: SSH → check ruin_floor derivation** (10 min) — determines if $0.42 injection is required; highest-leverage action.
2. **EXP-B: Run overdue multiasset updown_sniper shadow review** (15 min, weekly item since 08-02).
3. **EXP-C: Run settled_disp_ratio.py for 07-27..08-05** (30 min) — 11-day blind spot; band trigger may have been met.
4. **If restarting**: capital first (EXP-A), then `systemctl start klaus`; no code changes required for restart; candidate isotonic curve deploys automatically via VPS cron.
5. **If not restarting**: next weekly EVOLVE (tentatively 08-09) should cover items 2–3 as standing agenda.

_No strategy code or gate changes implemented. All items above require owner SSH access and/or human decision._
