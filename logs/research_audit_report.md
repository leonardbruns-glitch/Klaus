# Research Audit Report — 2026-07-15

**Generated:** 2026-07-15T10:45Z (automated)
**Snapshot:** 2026-07-15T10:17:46Z (age ≈ 27 min — FRESH ✓)
**System:** `klaus systemd: active` ✓ — uptime since 2026-07-15T02:40:11Z
**Capital:** $36.54 | **Ruin floor:** $89.16 | **Cap/floor:** 41.0%
**Band dark:** Day 9 (BAND_LIVE=False since 2026-07-06T22:08Z)
**Specialist reports read:**
- exec_audit_report.md — 2026-07-15T07:07Z ✓ (<36h)
- calib_monitor_report.md — 2026-07-15T12:00Z ✓ (<36h)
- gatekeeper_report.md — 2026-07-15T09:15Z ✓ (<36h)
- pnl_ledger_report.md — 2026-07-14T23:42Z ✓ (<36h)

---

## §1 — PRIMARY COMPOUNDING BOTTLENECK

**Bottleneck: Equity deployed.** Capital $36.54 is 41.0% of the engine ruin floor ($89.16), which mechanically blocks every band strategy path regardless of gate status, dispersion recovery, or calibration. No other bottleneck matters until this is crossed.

**Evidence from specialist reports:**

- *Gatekeeper*: "Capital $36.54 < engine ruin_floor $89.16 — all band paths mechanically blocked regardless of gate status." All seven active gates are frozen at their current state.
- *PnL Ledger*: Capital $34.13 (EOD Jul 14) → $36.54 (Jul 15T09:15Z) = +$2.41 in ~9.5h from UPDOWN-SNIPER. Extrapolated ~$5.80/day if sustained; CAVEAT: some fires logged after snapshot may not have resolved yet.
- *Exec Audit*: Band turns/day = 0.0. SNIPER turns/day ≈ 2.50. Deployed capital per turn: $2 clip.
- *PnL Ledger kill-switch table*: Capital breaches all three floors — ruin ($50), weekly ($75), 50%·HWM ($111.45). BAND_LIVE re-enable condition is $111.45 minimum; current is 32.8% of that.

**Compounding path:** SNIPER accumulates capital until (a) capital crosses ruin floor → band gates become unblocked, AND (b) dispersion S3 recovers. These are parallel constraints; neither alone unblocks the band. At current sniper rate, ruin floor crossing is ~13 days out (rough estimate Jul 28); dispersion S3 has shown no recovery signal in 13 days.

**Rank of remaining blockers (after capital):** dispersion edge (S3 day 13) > data collection (all gates frozen) > calibration (S4 confirmed) > fills (SNIPER untracked) > reliability (tracker blindness) > NO-parity (N/A offline) > turns/day (constrained by clip size).

---

## §2 — EXISTING-SYSTEM OPTIMIZATION

What the four reports collectively imply — items ranked by expected delta × confidence / effort:

### 2A. Sniper Position-State Persistence at Restart (HIGH priority)
- *Source*: Exec Audit ALERT-2, state_log Jul-14 22:04Z
- *Finding*: Tracker blindness on restart caused the orphan-sweep bug ($11.63 measured impact, fixed Jul-14). Fix routes around positions in `logs/updown_sniper_state.json`. But state_log notes the fix is "fail-open" — if the JSON file is missing at restart, the skip logic has no effect.
- *Expected delta*: Prevent recurrence of the orphan-sell bug. The Jul 14 pre-fix tape shows -$11.63 booked vs -$1.91 true over 21 positions — $9.72 drag from a single bug cycle.
- *Confidence*: HIGH. Root cause confirmed, fix mechanism clear.
- *Effort*: LOW — verify state file is persisted to disk after every new fill open and loaded correctly on startup.

### 2B. Deploy Isotonic Candidate to Band Shadow (NOT live)
- *Source*: Calib Monitor S4 CONFIRMED
- *Finding*: Candidate curve (Jun 9, n=1,037) lowers p_cal at p_raw=1.0 from 0.6316 → 0.3739 (Δ = −0.2577). Deployed curve is 36 days stale. Candidate has been sitting unreviewed since Jun 9 — a 36-day supervision gap.
- *Expected delta*: Shadow EV estimates become more realistic before band re-enables. Lower ceiling p_cal means fewer shadow fires classified as "high confidence" by a stale, optimistic ceiling — better pre-conditions for G1/G7 gate recalibration.
- *Confidence*: MEDIUM. Candidate validated on n=1,037 but predates July data. Direction is correct (market does not pay 0.63 at near-certainty because liquidity collapses post-peak).
- *Effort*: MEDIUM. Shadow-only swap; no live capital impact.

### 2C. Shadow Recorder Continuity Verification
- *Source*: Gatekeeper §Observations (SNIPER n≥100 gate, ~Jul 20)
- *Finding*: Post-fix clean tape started Jul-14T22:04Z. At 7 confirmed fires in 9.5h today = ~17.7 fills/day, the informal n≥100 gate is expected around Jul 20. Pre-fix tape is VOID. If the shadow recorder (`updown_shadow` service) has gaps, gate data is irrecoverable.
- *Expected delta*: Gate reaches n≥100 on schedule and provides a formal re-enable decision point. If shadow is dark, gate slips by days.
- *Confidence*: HIGH that this matters; UNKNOWN if shadow is running (not confirmed in any specialist report today).
- *Effort*: LOW — one VPS status check.

### 2D. Sniper Clip Ceiling Calibration (deferred to n≥50 clean fills)
- *Source*: PnL Ledger (true 17W/1L WR = 94.4%), Exec Audit (turns/day 2.50 at $2/clip)
- *Finding*: At $2/clip, EV per trade ranges from +$0.09 (entry 0.90, 94% WR) to −$0.08 (entry 0.98, 94% WR). The fill entry price distribution is the swing variable. Positive net +$2.41 today is encouraging but n is small and some fills unresolved.
- *Decision*: Collect 50 clean post-fix settled fills before any clip change. NOT an action for today.
- *Confidence*: LOW until n≥50.

---

## §3 — GATE PIPELINE REVIEW

From gatekeeper_report — all gate n-counts are frozen (BAND_LIVE=False since Jul 6, zero new band resolutions).

| Gate | Status | n | CI95 | ETA / Notes |
|---|---|---|---|---|
| G1 BAND_YES | AMBIGUOUS | 934 | [−10.9, +21.1] | n≥threshold; CI straddles 0; winner's curse = upper bound; band dark prevents new data |
| G2a BAND_NO d+1 | AMBIGUOUS (effective REJECTED) | 115 shadow / 51 live | [−11.9, +12.7] | Live WR 39.2% → REJECTED in practice; capital floor also blocks |
| G2b PAIR_FAV YES | COLLECTING | 9 | — | ~8.3d from band re-enable; rate 11/day frozen |
| G2c PAIR_FAV NO | COLLECTING | 9 | — | CF CI=[+12.6, +85.5] at n=32 — winner's curse blocker applies |
| G3 FILLED_vs_FIRED | WATCH_ITEM | 75 | [−75.0, −34.2] | Winner's curse CONFIRMED; filled ROI −75.8% vs sim +7.6%; frozen at n=75 |
| G5 THERMO | REJECTED | 125 | [−9.0, +2.0] | Done |
| G6 M1_BETA | REJECTED | 31 | [−20.6, +24.4] | Done (EVOLVE Jul-04) |
| G7 SUM_POSTED [0.70,0.85] | AMBIGUOUS | 382 | [−11.4, +38.9] | n≥threshold; CI straddles 0; winner's curse = upper bound |
| **SNIPER n≥100** | COLLECTING (informal) | ~17+ post-fix | — | Clean data from Jul-14T22:04Z; est. n=100 by ~Jul 20 |

**No gates newly READY or REJECTED this run.**

**Nearest progression gate**: SNIPER n≥100 (informal). Only gate that can reach a decision threshold within 7 days — it requires no band re-enable and accumulates purely from live SNIPER operation. **Do NOT accelerate by widening SNIPER thresholds** — that changes the distribution being tested and voids the offline calibration.

**G1/G7 unblock condition**: Winner's curse G3 must be resolved first (requires co-fill cross-tab with exec auditor, per gatekeeper). G3 is frozen at n=75 until band posts again. The G3 → G1/G7 dependency chain means band-YES re-enable is at minimum 13+ days out.

---

## §4 — ASSUMPTION ATTACK

**Three load-bearing assumptions of the band system as of today:**

### Assumption A: Dispersion premium persists (market prices wider distributions than realized)
**Status: CURRENTLY FALSE. S3 CRITICAL day 13.**
- Calib Monitor: disp_ratio7 ≤ 0.80 for 13 consecutive days (July 3–15). Market-implied temperature distributions are *tighter* than realized. The band-YES edge thesis depends on implied > realized; this is inverted.
- Model quotes today (Wuhan, Chengdu d+2): implied σ = 1.20–1.27°C vs reference true σ = 1.30°C. Inversion persists.
- No recovery signal. Calib Monitor recommends no band re-enable until disp_ratio7 > 1.10 for 3+ consecutive days.
- **Threat level**: HIGH. Band correctly dark.

### Assumption B: Fills are not adversely selected (winner's curse is manageable)
**Status: CONFIRMED VIOLATED. G3 WATCH_ITEM at n=75.**
- Gatekeeper: Filled ROI = −75.8%, CI [−75.0, −34.2]. Sim ROI = +7.6%. Gap = 82.6 pp. CI does NOT straddle zero — winner's curse is real and structural, not statistical noise at n=75.
- Gatekeeper: "Sim ROI is an UPPER BOUND. G1 and G7 AMBIGUOUS CI cannot serve as re-enable evidence."
- Zero new fills since Jul 6; sample frozen at n=75. No path to resolve this while band is dark.
- **Threat level**: HIGH. Requires co-fill cross-tab analysis to identify adversely selected legs.

### Assumption C: Recycle velocity scales with capital deployment
**Status: VOID. Zero RECYCLE099 events since Jul 6.**
- PnL Ledger: exit099_live.jsonl absent Jul 14. Exec Audit: zero recycled events.
- Cannot evaluate while band is dark. Last validated during Jun–Jul 5 active band window.
- **Note**: When band re-enables, recycle velocity is the first assumption to verify — any positive rate is unambiguously favorable, but the current base rate is zero.

---

## §5 — MARKET INTELLIGENCE (Day mod 3 = 0: Competitor Posture)

**Badatmath activity today (00:00–10:16Z UTC)** — from `data/shadow/badatmath_watch.jsonl` (snapshot 10:17Z):

- **Fill count**: 2,776 fill_join records in 10.3h = **270 fills/hour, 4.5/minute**
- **USDC deployed**: $7,681 total, avg $2.77/fill, max $15.00/fill (run rate ~$18.5K/day)
- **Price range**: 0.022–0.884, median 0.22 — predominantly cheap YES (<0.45) on non-mode buckets
- **Detect lag**: avg 78.5s, min 20.3s, max 153.0s

**City coverage** (last hour of tape): Seoul (repeated 3 fills, 0.10 YES for d+2 Jul 17), Warsaw (0.21), Busan (0.15 + 0.23), Mexico City (0.44 mode bucket), Austin (0.18 + 0.07), Sao Paulo (0.137), San Francisco (0.189), London (0.24 d+2 Jul 17), Helsinki (0.712 NO), Chicago (0.21).

**Structural deltas vs prior state_log knowledge:**

1. **Scale unchanged/increasing**: $7.7K in 10h = ~$18.5K/day. Prior reference (hot/Jul-05) showed comparable deployment. No reduction in activity.

2. **Detect lag degraded 2.5×**: Jul-05 hot file shows avg detect lag ~32s inferred from batch timestamps. Today: avg 78.5s. Our watcher is observing competitor fills 2.5× slower. This has no impact on our strategy (we are not racing him on maker bids) but reduces the quality of the badatmath intelligence signal.

3. **Pattern consistent**: Median price 0.22, bulk YES on non-mode buckets, same cities as prior state_log entries. No observable strategy shift.

4. **Helsinki NO fill at 0.712** (last-hour tape): This is a NO bet on the mode bucket, consistent with his documented favorite-NO overlay. Price 0.712 implies expected YES ~0.288. His NO fill here means he's betting this bucket does NOT win.

**Leaderboard teardown**: Direct leaderboard API access unavailable in this environment. Last known figure ($4.2M/yr, state_log research) cannot be updated today. Delta: no new information.

---

## §6 — THREE EXPERIMENTS

### Experiment 1: Verify post-fix SNIPER WR on first 30 clean settles
- **Hypothesis**: True WR on post-fix sniper (Jul-14T22:04Z onward) ≥ 88% on a clean n≥30 sample, confirming orphan-sweep fix restored expected edge.
- **Data**: `logs/updown_sniper_state.json` + resolution outcome join via Gamma API (VPS). Pre-registered MOVE_FLOOR=6bp, SIG_FLOOR.
- **Time**: ~3 days to accumulate (n=30 at ~10/day → Jul 18)
- **Cost**: 0 (observation)
- **Success metric**: WR ≥ 88%, avg entry ≤ 0.95, EV per $2 clip > $0.00
- **Decision-if-yes**: Propose clip increase to $3 when n≥50, pending n≥100 formal gate
- **Decision-if-no**: Stop sniper immediately, investigate signal or entry-price distribution. 6%+ loss rate at $2/clip with 0.90–0.98 entries → -EV strategy, not a calibration rounding error.

### Experiment 2: Isotonic candidate shadow-only deployment
- **Hypothesis**: Deploying the Jun-9 candidate curve to band shadow fires will reduce median shadow EV by 10–35% (0.6316 → 0.3739 ceiling) without changing fire rate, producing more realistic G1/G7 pre-conditions.
- **Data**: Candidate file exists (Jun 9, n=1,037). Today's band_struct shadow: ~10 fires/day.
- **Time**: 2–3 days of shadow comparison (Jul 17–18)
- **Cost**: 0 (shadow only, no live capital)
- **Success metric**: Shadow EV shifts predictably, fire rate unchanged
- **Decision-if-yes**: Deploy candidate permanently; schedule a fresh Jul-data refit before band re-enable
- **Decision-if-no** (fire rate collapses or EV inverts): Candidate has a fitting artifact. Request fresh refit from Jun-9 + July data merge.

### Experiment 3: Dispersion gauge daily trend watch
- **Hypothesis**: disp_ratio7 crosses 1.10 within 5–7 days if July weather variance reverts to seasonal norms. A positive trend (3 consecutive daily increases) would justify pre-positioning band capital decisions now.
- **Data**: Daily calib_monitor readings (already automated)
- **Time**: 5–7 days (end date ~Jul 20–22)
- **Cost**: 0 (observation)
- **Success metric**: disp_ratio7 > 1.10 on 3 consecutive days, confirmed with direct book data (not carry-forward)
- **Decision-if-yes**: Initiate capital planning for band re-enable — pair_fav YES first (lowest winner's-curse exposure), NO-band excluded pending G2a re-evaluation
- **Decision-if-no** (S3 persists through Jul 22): Assess structural regime shift. Consult badatmath fill prices vs Kalman model forecasts. The band thesis may require a seasonal adjustment.

---

## §7 — SINGLE BEST ACTION

**Verify the UPDOWN-SNIPER shadow recorder (`updown_shadow` service) is running and logging clean fires into `logs/shadow/updown_sniper/`.**

**Why this action, why now**: The gatekeeper_report identifies the SNIPER n≥100 offline gate as the only gate that can reach a decision threshold in the current window (~Jul 20). This gate is the earliest possible formal re-enable evidence for the only active revenue path. All band gates are frozen. The SNIPER gate is accumulating live — but only if the shadow recorder is running.

The exec_audit_report confirms all sniper fills are UNTRACKED in the main bot. The shadow recorder is the sole system generating fill-sim data for the offline gate. If it went down at the Jul-14T22:04Z restart — a plausible failure mode given the concurrent bot restart — over 24h of gate-accumulating data are already unrecoverably lost.

**Concrete first step**: `systemctl status updown_shadow` on VPS. Check `logs/shadow/updown_sniper/` for today's records. If running: no action needed. If dark: restart immediately. The gate data missed while dark cannot be reconstructed.

**Expected impact**: 0 effort if healthy. Prevents a 2–4 day slip in the Jul-20 gate date if shadow has been dark since restart.

*Sources: Gatekeeper §Observations (sniper n≥100 gate), Exec Audit ALERT-2 (tracker blindness), state_log Jul-13T10:35Z (INVARIANTS #2 shadow-first requirement).*

---

## PROPOSED ACTIONS (human review)

*None of the following are implemented. All require owner review.*

1. **Verify `updown_shadow` service on VPS** (§7). Zero risk; potentially irrecoverable gate data loss if dark.

2. **Verify `logs/updown_sniper_state.json` is persisted to disk on every fill open and loaded on startup**. The orphan-sweep fix is fail-open — missing state file at restart = bug recurs.

3. **Review isotonic candidate (Jun-9) for shadow deployment** (Experiment 2). 36-day supervision gap flagged by S4 alert. No live capital at risk.

4. **Do NOT re-enable any band strategy** until all three pre-registered conditions are met: (a) capital > $89.16 ruin floor, (b) disp_ratio7 > 1.10 for 3+ consecutive days, (c) partial resolution of G3 winner's-curse cross-tab. All three are currently active blockers. Single-condition re-enable violates pre-registered criteria.

5. **Wallet verification** (PnL Ledger §1 flag): Confirm Polymarket pUSD balance ≈ $36.54. The $360 MAKER SELL of 367.66 shares (Jul-14T15:49Z) is untracked — if proceeds are not in bankroll.json, true wallet may show ~$370+. Discrepancy > $5 = escalate immediately.

---

*Data sources: exec_audit_report.md (07:07Z ✓), calib_monitor_report.md (12:00Z ✓), gatekeeper_report.md (09:15Z ✓), pnl_ledger_report.md (23:42Z Jul-14 ✓), data-mirror SNAPSHOT.md (10:17Z), band_config.txt, bankroll.json ($36.54), state_log.md, maker_fills_recent.log (186 lines, Jul 12–15), shadow/badatmath_watch.jsonl (2,776 fill_joins, 10:17Z). All specialist reports within 36h ✓. No raw log recomputation where specialist report already covered the measurement.*
