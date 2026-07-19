# Klaus Research Audit — 2026-07-19T10:13Z

**Generated:** 2026-07-19T10:13Z (automated)
**Reports consumed:**
- exec_audit_report.md — 2026-07-19T07:09Z ✓ (age 3h)
- calib_monitor_report.md — 2026-07-19T08:16Z ✓ (age 2h)
- gatekeeper_report.md — 2026-07-19T09:19Z ✓ (age 54min)
- pnl_ledger_report.md — 2026-07-18T23:37Z ✓ (age 11h, <36h)

**Snapshot:** 2026-07-19T10:11:16Z (age < 6h ✓) | **System:** `active` ✓
**Capital:** $21.495 (bankroll.json 08:02Z) | **Band:** DARK day 13 | **Sniper kill-watch:** BROKEN — consecutive_wins=0 (first loss confirmed)
**Sole live revenue engine:** UPDOWN sniper

---

## ⚠ PRIMARY ALERT — Capital Collapse Jul 19 Intraday

**Capital: $37.569 (daily start) → $21.495 (08:02Z) = −$16.07 (−42.8%)**

Five sniper TAKER BUYs between Jul-18 23:19Z and Jul-19 07:59Z (from gatekeeper fill tape):

| Fill | Price | Shares | Deployed $ | P(YES gain) | P(NO loss) |
|---|---|---|---|---|---|
| Jul-18 23:19Z | 0.98 | 19.5 | $19.11 | +$0.39 | −$19.11 |
| Jul-19 00:24Z | 0.88 | 21.3 | $18.74 | +$2.56 | −$18.74 |
| Jul-19 02:44Z | 0.91 | 22.75 | $20.70 | +$2.05 | −$20.70 |
| Jul-19 03:24Z | 0.98 | 22.0 | $21.56 | +$0.44 | −$21.56 |
| Jul-19 07:59Z | 0.94 | 23.5 | $22.09 | +$1.41 | −$22.09 |
| **Total** | | | **$102.20** | **+$6.85** | **−$102.20** |

Best-fit resolution accounting for −$16.07 net: **4/5 resolved YES (+$6.85 gross), 1 resolved NO at approximately $20.70-$21.56 (fills 3 or 4)**. Exact identity requires updown_sniper snap data lookup. The 5-fill window WR = 80% vs break-even ≥95.83% (gatekeeper slice data). This single NO outcome wiped approximately 30+ prior sniper wins at comparable clip sizes.

bankroll.json `saved_ts`=1784448173 → 08:02Z Jul-19 (write mechanism has recovered vs Jul-18 deficiency). Capital figure is current. consecutive_wins=0 confirmed.

---

## 1. Primary Compounding Bottleneck

**RISK FRAME — sniper asymmetric loss exposure, now empirically demonstrated.**

Compounding equation status post-loss (updated from prior audit):

| Lever | Prior audit (Jul-18) | Today (Jul-19) | Change |
|---|---|---|---|
| ROI/turn (win) | +3.62–4.46% | Unchanged (edge intact if WR recovers) | No change |
| ROI/turn (loss) | Not yet observed | −80–98% of deployed per loss | **NEW — first loss** |
| Turns/day | 3–12 (cadence was primary) | Cadence demoted | Deprioritized |
| Fill rate | 78.3% (5 FOK misses/day) | Same structural issue | Secondary |
| Equity deployed | $37.57 growing | **$21.49 declining** | Deteriorating |
| Stake vs capital | Kelly ≈ 50% of daily-start | $20 clips on $21.50 base = 93% | **CRITICAL** |

**The prior primary bottleneck (FOK fill rate, −$2.90/day drag) is irrelevant when one loss destroys $16+.** The binding constraint today is the sniper's terminal tail risk: at $21.50 capital with $20-clip fills, a single additional NO resolution leaves $1.50 — ruin for any future operation.

**Asymmetry math at current entry prices:** The Jul-19 fills entered at 0.88–0.98. A YES win at 0.98 returns +$0.02/share (+2%). A NO loss returns −$0.98/share (−98%). Required WR to break even with taker fees: (loss)/(gain+loss) ≈ 0.98/(0.02+0.98) = 98% at 0.98 entries; 88% at 0.88 entries. Average across these 5 fills ≈ 93% required WR. Observed 5-fill WR: 80%. Expected value per dollar deployed in this window: 0.80×0.065 − 0.20×0.937 ≈ +0.052 − 0.187 = **−0.135** (−13.5% per dollar deployed in this session). This is negative EV even before taker fees.

**Source:** gatekeeper capital alert (§ "Capital Alert — −$16.07 −42.8% intraday"); pnl_ledger Jul-18 (kill-watch slice n=55 WR=1.000 CI-lo 0.9347 vs BE 0.9583 COLLECTING); bankroll.json (capital=$21.495, consecutive_wins=0).

---

## 2. Existing-System Optimization

What the four reports collectively imply (no code edits; items for human review):

### a. Stake Re-sizing at $21.50 Capital [CRITICAL, IMMEDIATE]
- **What:** At bankroll $21.50, filling $18–22 clips means 84–100% of capital per fire. If Kelly sizing uses the pre-loss capital ($37.57), it overestimates safe stake by 1.75×. The bot has $21.50 available; one $20 loss = $1.50 remaining = ruin.
- **Expected delta (of fixing):** Correctly sized Kelly at $21.50 × 0.50 × (WR-BE)/p_loss ≈ $3–$6/clip. Reduces per-fire P(ruin) by ~70% vs current clip size.
- **Confidence:** High (the math is deterministic; only unknown is whether bot recalibrated after loss).
- **Effort:** Inspect EVOLVE kill-watch code for capital reference point; confirm bankroll.json is being read fresh at each fire decision.

### b. Sniper Loss Forensics — Identify the Losing Fill [HIGH priority]
- **What:** One of the five Jul-19 fills resolved NO (best-fit: fill 3 at $20.70 or fill 4 at $21.56). The updown_sniper snap file (`hot/2026-07-19/updown_sniper.jsonl` or `updown_sniper/snap_20260719.jsonl`, n=44,742 at snapshot) likely contains condition_id, resolution outcome, and entry metadata.
- **Expected delta:** Identifies whether the loss was in a specific hour, asset, or price tier that could be filtered without sacrificing turns.
- **Confidence:** High the data exists; medium that a filter is available.
- **Effort:** 1h data pull from snap file.

### c. G3 Anomalous MAKER SELL Classification [GATE-UNBLOCKING, OVERDUE — day 3]
- **What:** PA-1 from prior two audits, still unresolved. Tokens 1399483673820402 (Jul-16 SELL@0.96×147sh = $141.17) and 2664940529472113 (Jul-18 SELL@0.92×9.3sh = $8.57) unclassified. G3 n=75 frozen. Also: 4th orphan MAKER BUY@0.02 (Jul-19 02:14Z, token 5717613767097074) added to pattern.
- **Expected delta:** Unblocks G3 n accumulation. Clarifies whether winner's curse gap is structural (band permanently compromised) or a classification artifact.
- **Confidence:** High — 30min lookup, high-binary-value outcome.
- **Effort:** 30min Polymarket UI lookup.

### d. PA-2 Shadow-Maker Fill Resolutions (d+1 today) [RESOLVE NOW]
- **What:** Three BUY@0.02–0.06 fills from Jul-17 ($8.06 total: tokens 4095117562509625, 1055101008834022, 1046907088381323) were d+1/d+2 unresolved as of Jul-18 pnl_ledger. d+1 resolves today (Jul-19). d+2 resolves tomorrow. Outcomes determine whether shadow-maker is +EV or adversely selected.
- **Effort:** Check resolution on Polymarket for these 3 tokens; 15min.
- **Note:** exec_audit Jul-18 BUY@0.08×44.9sh token 7094108612094851 also pending.

### e. Isotonic Refit (S4, day 44) [PREREQUISITE FOR BAND REVIVAL]
- **What:** Deployed isotonic curve unchanged since Jun-06 (43d). Neither curve has OOS validation. Plateau collapse (p_raw [0.30–0.95] → p_cal ≈ 0.38) is the structural root cause of the S3 dispersion inversion. Fresh refit with Jun–Jul resolution data required.
- **Expected delta:** May reduce dispersion ratio inversion; direct prerequisite for any future BAND_LIVE re-enable argument.
- **Confidence:** Medium (plateau may be a market feature, not calibration artifact — can't determine without fresh data).
- **Effort:** 1 data session.

### f. Disk Space [RESOLVED, MONITOR]
- **What:** Disk recovered from ~97% (3GB free, prior audit) to 93% (7GB free, today snapshot). No immediate action required.
- **At current shadow log volume:** 7GB free / ~5GB/day estimate ≈ 1.4-day buffer. Still needs monitoring.

---

## 3. Gate Pipeline Review

**From gatekeeper_report 2026-07-19T09:19Z. No gates READY, REJECTED, or changing status.**

| Gate | Status | Live n | +24h | CI95 | Blocker |
|---|---|---|---|---|---|
| G1 BAND_YES | AMBIGUOUS | 934 | 0 | [−10.9, +21.1] | WC confirmed; BAND_LIVE=False |
| G2a BAND_NO | AMBIGUOUS ‡ | 115 | 0 | [−11.9, +12.7] | Live WR 39.2% = effectively REJECTED |
| G2b PAIR_FAV_YES | COLLECTING | 9 | 0 | — | n=9, needs BAND_LIVE |
| G2c PAIR_FAV_NO | COLLECTING | 9 | 0 | — | n=9, needs BAND_LIVE |
| G3 FILLED_VS_FIRED | WATCH_ITEM | 75 (frozen) | 0 | [−75.0, −34.2] | Anomalous SELLs unclassified (PA-1, 3d overdue) |
| G5 THERMO_MAKER | REJECTED | 125 | 0 | [−9.0, +2.0] | Inert |
| G6 M1_BETA_LOCKOUT | REJECTED | 31 | 0 | [−20.6, +24.4] | Inert |
| G7 SUM_POSTED [0.70,0.85] | AMBIGUOUS | 382 | 0 | [−11.4, +38.9] | WC confirmed; BAND_LIVE=False |

‡ G2a: shadow CI straddles zero BUT live n=51 WR=39.2% is an effective rejection. Do not re-enable BAND_NO on shadow CI alone.

**Capital gap to band re-enable:** $21.495 vs ruin floor $89.16 = gap of $67.67 (+315%). At today's sniper daily rate of +7.1% (Jul-18) or negative today, recovery is non-linear. One loss scenario: $21.50 → ~$1.50 = irreversible. Two consecutive wins at $5 clip: ~$21.50 + $0.50 + $0.52 → $22.52. The band path is structurally distant and deteriorating with today's loss.

**To accelerate accumulation WITHOUT degrading expectancy:** Classify G3 anomalous SELLs (PA-1, 30min). Only unblocked gate action available. BAND_LIVE=False forecloses all other band-gate paths.

**Shadow accumulation (counterfactual):**
- G1 shadow: 163 fires total since wind-down (+9 in 24h: Beijing d+1, Wuhan d+1, Tokyo/Taipei d+2, Wuhan/Chongqing/Beijing d+2, Munich d+2, London d+1). G1 shadow cadence normal (~13/day).
- G7 subset: 107 fires (of G1 total, in [0.70,0.85] window, +7 in 24h). No resolution truth flowing while band dark.

---

## 4. Assumption Attack

Three load-bearing assumptions of the band system today:

### A. Dispersion premium persists (market-implied sigma > realized deviation)
- **Evidence:** S3 Day 17. disp_ratio7 = 0.742 (calib_monitor). 07-18 daily median = 0.541 — **new worst in the 7-day window.** 3d trailing avg 0.675 < 7d avg 0.749: WORSENING trend.
- **Jul-17 recovery signals did NOT persist.** Wuhan/Chengdu ratios cited last session; Jul-18 saw those cities absent from top-ratio rows. The worst Jul-18 cases: London −4°C miss (ratio=0.200, model narrow at 0.8°C, realized 4°C), Milan −3°C miss (ratio=0.298), LA +2.2°C (ratio=0.241). These are NOT market mispricing — they are temperature model errors of 4–5σ.
- **Region breakdown (fresh 5d):** Asia median 0.558 (was best region, now worst). EU median 0.812 (improved but driven by Jul-17 outliers). Only 7 of 56 rows (12.5%) exceed 1.10 threshold.
- **Verdict: DETERIORATING. THREATENED.** Not just at the band-edge threshold — the underlying temperature model is producing multi-sigma misses (London −4°C). BAND_LIVE=False is the correct posture. No revision possible until S3 clears.

### B. Fills are not adversely selected vs simulated fires
- **Evidence:** G3 n=75 WATCH_ITEM, filled ROI −75.8% vs sim +7.6%, CI [−75.0, −34.2]. Unchanged from prior.
- **No new band fills to assess** (BAND_LIVE=False day 13; 0 band fills in all audit windows).
- **Verdict: BREACHED (frozen state).** No new data; no revision possible.

### C. Recycle velocity scales
- **Evidence:** vacuous — BAND_LIVE=False day 13. Shadow: 14-19 fires/day (exec_audit shadow engine rates normal per band_struct projected 7,750 rows/day).
- **Verdict: UNTESTABLE.** No change.

| Assumption | Verdict | Key number | Trend vs prior |
|---|---|---|---|
| Dispersion premium | DETERIORATING/THREATENED | disp_ratio7=0.742; Jul-18 daily=0.541 (new low) | Worse ↓ |
| Fills adversely selected | BREACHED (frozen) | filled ROI −75.8% vs sim +7.6% | Unchanged |
| Recycle velocity | UNTESTABLE | BAND_LIVE=False day 13 | Unchanged |

---

## 5. Market Intelligence — Market Census (day 19 mod 3 = 1)

**Reporting delta vs state_log knowledge. Data source: shadow_summary.json loggers by date.**

### City/Product Universe

**Band_struct logger** (counts every shadow-eligible quote regardless of whether live or dark):
- Jul 10-18 full-day range: 7,586–7,757 rows/day
- Jul 19 at snapshot (10:11Z, ~43% of day): 3,412 rows → projected **7,935/day** (slightly above range)
- **Interpretation:** city universe is STABLE. No new cities added or removed. The marginally higher Jul-19 pace is within normal variance and may reflect additional d+2 shadow windows opening.

**Window_resolution logger** (actual market resolutions, ground-truth count):
- Prior full-day range: 1,147–1,152 rows/day
- Jul 19 at snapshot (43% of day): 504 rows → projected **1,172/day** — normal, consistent with ~51 cities × ~23 resolution events/day average.
- **Interpretation:** 51-city universe unchanged. No new weather markets detected.

**Badatmath_watch** (competitor posting cadence proxy):
- Jul 15-16 peak: 5,812–5,937 rows/day
- Jul 17-18: 4,157–4,038 (step down from peak)
- Jul 19 projected: ~5,330 (partial rebound from Jul-17/18 trough)
- **Delta vs state_log:** No structural change. Competitor posting stable. Minor cadence variation (10–20%) within normal weekly rhythm. No evidence of competitor strategy change.

### Shadow Logger Anomaly — ob_delta and token_trade absent from Jul-19

**Observation:** `ob_delta.jsonl` and `token_trade.jsonl` are absent from the `hot/2026-07-19/` logger list in shadow_summary.json. On Jul-18 these were n=172,402 and n=33,729 respectively; on Jul-16 ob_delta was n=580,050. All prior days (Jul-10 through Jul-18) show both loggers with substantial row counts.

Their absence today could indicate:
1. These loggers were disabled/renamed as part of the wedge-watchdog deploy (`ee014ba92`) or a subsequent cleanup
2. They are logging to a new path not yet mirrored
3. A logging restart failure that the shadow_telemetry logger (n=622, normal rate) should have caught

**Significance:** ob_delta was the primary microstructure signal source; its absence removes real-time book-delta visibility. token_trade was trade-tape logging. If disabled intentionally (not a failure), this is a resource decision (disk space). If unintentional, it is a logging gap that will reduce the sniper's data quality.

**Thermo_maker depressed:** n=10,563 at 43% of day → projected 24,007/day. Jul-10–18 range: 24,956–44,432. Below normal range for the second consecutive day (Jul-18 was 24,956). Consistent with exec_audit observation of thermo at reduced rate.

**No new weather cities, no new product types identified.** Market census STABLE except ob_delta/token_trade logging gap flagged.

---

## 6. Three Experiments

### Experiment 1 — Sniper Loss Identification via Snap Data [HIGHEST priority, 1h]
- **Hypothesis:** The losing Jul-19 fill has a distinguishing feature (market hour, asset, entry price tier ≤0.92, or specific city/token type) that a prospective filter could exclude while retaining ≥80% of winning fills.
- **Data:** `updown_sniper/snap_20260719.jsonl` (n=44,742; already in shadow_summary mirror). Join snap rows to the 5 fills in gatekeeper tape on condition_id or token_id. Identify which fill has outcome=NO and extract: hour_utc, asset, entry_px, days_to_resolution, market_type.
- **Time:** 1h (data pull + join).
- **Cost:** $0 capital; read-only.
- **Success metric:** The NO-fill has a feature that is present in <10% of YES fills with n≥20 in that cell.
- **Decision if YES:** Propose a prospective gate (e.g., skip fills with entry_px<0.92, or skip specific hours). Expected outcome: reduces tail-loss frequency.
- **Decision if NO:** No distinguishing feature → loss was random noise at the tail of the sniper's statistical distribution. Accept and continue; revise Kelly sizing to reflect true BE WR.

### Experiment 2 — True Sniper Break-Even WR Accounting [HIGH priority, 2h]
- **Hypothesis:** The sniper's nominal BE WR (0.9583, from gatekeeper slice data) does NOT fully account for taker fee drag at these entry prices, meaning the true required WR is higher.
- **Data:** Extract taker fee schedule from platform mechanics (CLAUDE.md notes ~3.15% at p=0.50, near 0% at extremes). At p=0.94 entries, fee ≈ 0.05% per dollar (p×(1-p)×taker_rate curve). Compute BE WR = (loss + fee)/(gain − fee) for each entry price in [0.88,0.98].
- **Time:** 2h.
- **Cost:** $0.
- **Success metric:** Computed BE WR differs from 0.9583 by >1pp → the gatekeeper is using an incorrect floor.
- **Decision if YES:** Update the kill-watch BE WR threshold. May require adjusting P_MIN floor upward (e.g., from current threshold to entry_px ≥ 0.96 only).
- **Decision if NO:** Fee drag is negligible at extreme odds (consistent with CLAUDE.md) → current BE WR is correct.

### Experiment 3 — Isotonic Refit with Jul Resolution Data [MEDIUM priority, 4h]
- **Hypothesis:** Refitting with 40+ days of Jul resolution outcomes (currently excluded from both deployed and candidate isotonic curves, S4 alert) will reduce plateau collapse in the 0.30–0.95 p_raw range and improve dispersion ratio above 1.10 on held-out test data.
- **Data:** stwa_state.jsonl + window_resolution.jsonl from shadow (both available and current). Withold last 14 days as OOS validation set.
- **Time:** 4h (refit + OOS run + compare).
- **Cost:** $0 (no live capital).
- **Success metric:** OOS Brier improvement >0.02 vs current deployed curve AND OOS dispersion ratio improvement >0.10 AND plateau collapse reduced (p_raw 0.60 → p_cal >0.50 rather than flat at 0.38).
- **Decision if YES:** Deploy candidate (requires Tier 2 commit with data citation). Pre-condition for any band re-enable argument.
- **Decision if NO:** Plateau is a structural market feature, not a calibration artifact. Band edge recovery requires a different approach (e.g., d+0 mode-only, region filtering).

---

## 7. Single Best Action

**Verify sniper Kelly sizing is reading bankroll.json fresh ($21.495) — not stale pre-loss capital ($37.569). STOP further $18-22 clip fires until confirmed.**

- **Why:** At $21.495 remaining capital, a single sniper fill at the current $18–22 clip size deploys 84–102% of bankroll. The EVOLVE kill-watch system was calibrated at 21/21W on $37.57 capital with Kelly 0.50×. After today's loss (consecutive_wins=0), the Kelly multiplier should have dropped, but if the bankroll.json reference is the daily_start ($37.57) rather than the live capital ($21.495), the bot is firing at 1.75× the correct stake. One NO resolution = ruin ($1.50 remaining).
- **Concrete first step:** Read `stwa_engine.py` or the EVOLVE sniper module; find the capital reference passed to Kelly sizing. Confirm it reads `bankroll.json` `capital` field (not `daily_start_capital`). If correct, confirm the loaded value at the last fire was ~$21.50, not ~$37.57.
- **Source:** gatekeeper_report capital alert "−$16.07 −42.8% intraday"; bankroll.json (capital=$21.495, consecutive_wins=0, daily_start=$37.569); pnl_ledger "CAVEAT: bankroll.json was last written at 02:46 UTC, capturing only the first of three sniper wins" — the Jul-18 write deficiency was confirmed resolved (saved_ts→08:02Z Jul-19), but the risk of sizing on stale capital must be verified.
- **Compounding impact × P(success) / effort:** Preventing a single additional $20 NO loss at $21.50 capital saves the entire remaining bankroll with certainty if the misfire occurs. P(next fire resolves NO) ≈ 20% based on today's 5-fill session. Expected value of this check: 0.20 × $21.50 / 30min = **$4.30/hour** — highest of any available action.

---

## PROPOSED ACTIONS (human review)

| # | Action | Urgency | Effort | Expected impact |
|---|---|---|---|---|
| **PA-1** | Verify sniper Kelly reads live capital ($21.495), not daily_start; confirm clip size ≤$5–$7 at current capital | **CRITICAL** | 30min code read | Prevents ruin from next loss |
| PA-2 | Investigate Jul-19 sniper loss via snap data: which fill resolved NO and why | HIGH | 1h data pull | May unlock loss-avoidance filter |
| PA-3 | Classify G3 anomalous MAKER SELLs (tokens 1399483673820402, 2664940529472113) + 4th orphan BUY@0.02 (5717613767097074) | HIGH (3d overdue) | 30min UI lookup | Unblocks G3 gate progression |
| PA-4 | Confirm resolution of Jul-17 shadow-maker fills (tokens 4095117, 1055101, 1046907, 7094108) — d+1/d+2 resolved today | HIGH (time-sensitive) | 15min | Closes Jul-17 pending fills |
| PA-5 | Investigate ob_delta / token_trade logging absence (shadow Jul-19 gap) | MEDIUM | 15min SSH check | Prevents silent data blindspot |
| PA-6 | Isotonic full refit with OOS validation (S4 alert, day 44) | MEDIUM (band dark) | 4h data session | Prerequisite for any future band re-enable |
| PA-7 | Compute true sniper BE WR including fee schedule at p=0.88–0.98 | MEDIUM | 2h | May indicate P_MIN floor too low |

*PA-1 is time-critical: every additional sniper fire at current capital and current clip size has 84–100% ruin exposure if it resolves NO. No other action takes priority until clip size is verified safe.*

---

*Research agent: research-agent@klaus | Snapshot: 2026-07-19T10:11:16Z | Capital: $21.495 (08:02Z) → −$16.07 intraday | Sniper: consecutive_wins=0 (first loss) | Band: dark day 13 | S3 Day 17 dispersion inversion (0.742, worsening) | Primary bottleneck: risk frame — $20 clips on $21.50 capital, one loss from ruin*
