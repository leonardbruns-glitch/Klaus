# Klaus Research Audit
**Date:** 2026-06-24 | **Run:** 2026-06-24T14:00Z (approx)
**Snapshot:** 2026-06-24T13:30:21Z -- age <1h -- PROCEED
**System:** `active` (uptime since 2026-06-24 08:04:37 UTC)
**Capital:** $234.32 (13:30 snapshot) -- up from $211.95 (exec_audit 07:07 UTC)

### Report freshness
| Report | Timestamp | Age | Status |
|---|---|---|---|
| exec_audit_report | 2026-06-24T07:07Z | 6.9h | OK |
| calib_monitor_report | 2026-06-23T08:10Z | 29.8h | OK (<36h) |
| gatekeeper_report | 2026-06-24T12:15Z | 1.8h | OK |
| pnl_ledger_report | 2026-06-23T23:37Z | 14.4h | OK |

### Post-report commit alert
Commit `d156804a2` ("sigma-reality verdict + badatmath-YES forensic: widen d+1/d+2 ceil to 0.45, steepen bell, unblock co-fill pairing") landed **after** all four specialist reports. band_config.txt (13:30 snapshot) is the authoritative post-commit state. maker_fills_recent.log confirms runtime still shows `no_resv=1.00` through 13:29 UTC -- P1 phase override (cap < BAND_PHASE2_CAPITAL=$600) is independent of the BAND_NO_CASH_RESERVE=0.30 parameter value; the bot applies 100% NO reservation until the phase threshold is crossed. YES posts remain blocked at $234 capital.

### Pre-flight notes
- **integrity_report.json:** `blocks_agent_run=false`. HIGH-severity flags (AGED_NO_RESOLUTION, MISSING_DEDUP_KEYS) target LDA-era fields absent in band trades -- false positives for this system. No abort.
- **research_status.md:** Updated 2026-05-16 (LDA era). Stale for band system.
- **state_log.md:** File exceeds 430KB API limit; tail not fully extracted. Analysis draws on band_config.txt inline timestamps and commit history instead.
- **badatmath_watch.jsonl:** 4.5MB, inaccessible inline; summary-level competitor data sourced from shadow_summary.json.

---

## Section 1: Primary Bottleneck

**EQUITY DEPLOYED** is the binding constraint. All other metrics are downstream.

**Evidence:**

| Metric | Value | Benchmark |
|---|---|---|
| Capital turns/day (4d avg) | **0.53x** | ~1.0x (badatmath) |
| Capital turns last 24h | 0.93x | ~1.0x |
| % cycles posting zero | **93%** (Jun 24, 82 cycles) | low |
| yes_resv_skip per cycle | 14-62 (Jun 24) | 0 (if YES active) |
| SELL_EXIT backlog | $399 (37 orders, 403 sh @ 0.99) | recycling freely |
| cash_preskip mean (Jun 24) | $124 | <$50 |

The compounding equation is: ROI/turn x turns/day x equity deployed. Turns are suppressed below benchmark for two structural reasons, both operating simultaneously today:

**Blocker A -- P1 NO-only phase.** BAND_PHASE2_CAPITAL=$600; current capital=$234 (39% of threshold). Runtime applies no_resv=1.00, blocking all YES posts. The maker_fills_recent.log shows yes_resv_skip=14-62 per cycle (14-62 viable YES candidates skipped per 5-min cycle, zero posted). Confirmed continuous through 13:29 UTC. YES posting will not resume until ~$366 more capital is accumulated under the current P1 logic. At the Jun 24 intraday pace (+$22/6h = +$88/day), the $600 threshold is ~4 days away, assuming the pace holds.

**Blocker B -- SELL_EXIT backlog not turning over.** 37 resting SELL_EXIT orders (403 shares @ $0.99) had matched=0 at the 06:56 snapshot. At least 1 position is confirmed >=48h old (119 shares). Maker_fills_recent.log confirms these are clearing gradually (UNTRACKED fills at 0.98-0.999 throughout the day, each adding $2-5 to capital), but the queue is recycling slowly. $399 in pending SELL_EXITs represents 1.7x today's liquid capital sitting idle as resting makers.

**What has changed today (post all specialist reports):** commit d156804a2 raised BAND_PX_CEIL from 0.30->0.45 (d+1/d+2) and steepened the bell. These changes expand the YES post universe when YES is eventually re-enabled. They do NOT affect today's NO-only throughput.

**Rank of remaining constraints (after equity deployed):**
2. Turns/day (0.53x, improving with SELL_EXIT clearance)
3. NO-parity (not a constraint -- 100% NO is intentional P1 design)
4. Resolution gate data gap (Gamma 403 blocking all WR/ROI verdicts)
5. Dispersion edge (ratio 0.714, below 1.10 threshold, alert day 4+)
6. Calibration (within thresholds, no alert)

---

## Section 2: Existing-System Optimization

What the four reports collectively imply -- prioritized by expected delta and confidence.

### 2a. Run band_resolution_join.py on VPS (HIGH urgency)
- **Gap:** Gates 1, 2, 3, 7 are collectively at n=5,905 / 213 / 97 / 2,954 and cannot produce WR/ROI verdicts because Gamma API returns 403 from container. The script exists and was validated to produce 1,489 deduped legs (gatekeeper Section-Resolution Blocker).
- **Expected delta:** Gate 2 (BAND_NO, n=213) alone controls $5/NO-stake x ~30 fires/day = $150/day of capital deployment. A READY verdict gives confidence to maintain or scale; a REJECTED verdict stops deploying capital into a losing segment. Either is more valuable than indefinite COLLECTING.
- **Confidence:** HIGH (script runs, needs VPS exec only).
- **Effort:** 10 min VPS session.

### 2b. daily_start_capital = $15.95 is stale (OPERATIONAL RISK)
- **Gap:** bankroll.json shows `daily_start_capital: 15.95`. pnl_ledger notes if the bot uses this for daily-halt logic, the trigger fires at $15.95 - $3 = $12.95 capital -- well below any meaningful threshold and never triggered at current $234. This field should reflect the prior day's EOD capital (~$212).
- **Root cause:** Not reset on restart. The PnL ledger flagged this (Section 4). research_status.md confirms "daily_start_capital field is stale; ignore" -- but the bot code may not ignore it.
- **Expected delta:** Avoids a false daily-halt trigger if capital were to drop near the stale baseline.
- **Confidence:** HIGH (field value confirmed stale).
- **Effort:** LOW (restart-time reset or hardcode from bankroll.capital).

### 2c. Dispersion gauge dark for 4+ consecutive sessions (MONITORING GAP)
- **Gap:** The load-bearing edge variable (implied sigma vs true sigma ratio) cannot be computed from any agent container because stwa_ladder_book.jsonl is 2.5MB (above the 1MB GitHub API inline limit and git fetch is network-blocked). Last confirmed ratio: 0.714 (Jun 22, below threshold 1.10). Direction was improving +0.043/session but recovery was slow: ~9 more sessions needed at that pace to reach 1.10.
- **Fix:** Instrument VPS to write `data/sigma_daily_summary.json` (<5KB) at each 15-min snapshot: per-city implied sigma + ratio + ts. Resolves the dark period permanently.
- **Expected delta:** Restores visibility on the strategy's core edge assumption without any code changes to the trading system.
- **Confidence:** HIGH (the computation already runs on VPS; output just is not written).
- **Effort:** MEDIUM (VPS code change, ~30min).

### 2d. Isotonic calibration: do NOT deploy candidate (HOLD)
- **Status (calib_monitor Section 4):** Deployed curve: p_cal at p_raw=1.0 = **0.6316**. Candidate: **0.3739** at p_raw=1.0. Delta = -0.258. Empirical win rate at the terminal signal (p_raw=1.0 rows) is ~99.1%. Deploying the candidate would set p_cal=0.374 for a bucket the data shows wins 99% of the time -- severe underprice.
- **Both maps share the flat-top defect** (all p_raw 0.30-0.95 collapse to ~0.38). The deployed curve is the lesser defect. A full refit with live-data weighting targeting the flat-top specifically is the correct next step, not swapping in the candidate.
- **Expected delta:** No action today = no downside from miscalibrated exits.

### 2e. Disk at 87% -- accelerating shadow log accumulation (MONITORING)
- **Data:** system_status.txt: 80GB used / 97GB = 87%. Shadow logs growing: metar_lockout.jsonl alone adds 22-44MB/day (10 days = ~270MB total in shadow_summary). badatmath_watch adds ~3-4MB/day. band_struct adds ~7MB/day. At this rate, 13GB free implies ~2-3 weeks before critical zone, assuming current logging rates.
- **No action required today.** Flag for user: implement shadow log rotation (archive >7d to compressed) before reaching 95%.

---

## Section 3: Gate Pipeline Review

Source: gatekeeper_report (12:15 UTC Jun 24).

| Gate | n | Rate | Status | Next step |
|---|---|---|---|---|
| 1 BAND_YES per slice | 5,905 | +229/24h | COLLECTING -- Gamma 403 | VPS: band_resolution_join.py |
| 2 BAND_NO + PAIR_FAV | **213** | +36/24h | COLLECTING -- Gamma 403 | VPS: band_resolution_join.py (**nearest ready**) |
| 3 FILLED_VS_FIRED | 97 | +33/24h | COLLECTING -- Gamma 403 | VPS: join (note side-shift caveat below) |
| 4 BASKET_EXIT | -- | 0 | VOID (retired Jun 22) | None |
| 5 THERMO_MAKER_NO | 3 | 0 | COLLECTING but frozen | VOID or resume (see below) |
| 6 M1_BETA_LOCKOUT | 31 | 0 | COLLECTING but stalled | Revert per standing rule |
| 7 SUM_POSTED [0.70-0.85] | 2,954 | +130/24h | COLLECTING -- Gamma 403 | VPS: band_resolution_join.py |
| YES_CAPTURE_SHADOW | 330 | ~285/24h | Unregistered, accumulating | Run band_yes_capture_join.py Jun 26-27 |

**Gate 2 (BAND_NO) is nearest READY.** n=213 clears the 100-decision threshold 2x over. No accumulation bottleneck -- +36/24h with $5/NO-stake x ~30 fires/day = $150/day deployed on unvalidated expectancy. Blocking factor is only Gamma 403.

**Gate 3 (FILLED_VS_FIRED) methodology caveat.** Since Jun 23 12:29 UTC, all new fills are NO (YES fills = 0). When the join runs, the comparison will be filled-YES-ROI vs all-fires-YES-ROI with the filled subset being nearly empty. This selection bias may invalidate the gate's YES comparison. The NO-only comparison remains clean. Recommend separating the join into YES and NO sub-gates when the script runs.

**Gate 5 (THERMO_MAKER_NO): limbo.** Engine paused Jun 23 18:40 to free $25 cash. n=3, ROI=-66%, CI=[-132.6%, +0.7%] -- upper bound straddles zero by a hair; one more loss would push CI firmly negative. The gate will never accumulate at n=0 rate. Current state (neither resumed nor VOID'd) is a dead weight on the gate ledger. Decision required: VOID (accepts that $25 free cash was the correct call and THERMO has no clear edge at n=3) or resume at minimal stake (1 fire/day x 17 more = ~17 days to n=20). See PROPOSED ACTIONS.

**Gate 6 (M1_BETA_LOCKOUT): revert per standing rule.** n=31/100, engine stalled, standing rule from Jun 09: "at n>=100, WR>=95% AND +EV = keep; else REVERT to 0.5C floors." n will never reach 100 at 0 rate. Reversion is the conservative default per rule. One M1_PROBE SELL_EXIT still resting at 0.99 (20 shares). See PROPOSED ACTIONS.

**YES_CAPTURE_SHADOW: approaching join window.** n=330 first-fires (62 in the new 0.25-0.45 zone unlocked by d156804a2). At ~285/24h pace, join target n>=100 for the 0.25-0.45 zone alone is already met. `band_yes_capture_join.py` target: Jun 26-27 (per gatekeeper). Recommend registering this as Gate 8 now so the join has an official threshold and decision rule.

**How to accelerate gate accumulation WITHOUT degrading expectancy:**
- Gates 1/2/3/7 are purely Gamma-blocked, not accumulation-constrained. No breadth or stake changes needed; these will resolve the moment VPS runs the join script.
- YES_CAPTURE_SHADOW will self-accumulate; join can run Jun 26-27 without any intervention.
- No parameter changes recommended to speed up gate data collection.

---

## Section 4: Assumption Attack

The band system's compounding rests on three load-bearing assumptions. Each is evaluated against today's data.

### Assumption 1: Dispersion premium persists (implied sigma > true sigma)

**Meaning:** The market overestimates temperature dispersion -> off-mode NO prices are above fair value -> band edge. Confirmed edge when implied sigma / true sigma > 1.0.

**Today's data (calib_monitor Section 3):**
- Last confirmed implied sigma: 0.928C (Jun 22, PRE_PEAK, 16 cities)
- True sigma (data-derived, 149 city-days): 0.961C
- Ratio: 0.928 / 0.961 = **0.966** (implied BELOW true)
- Full dispersion ratio (calib_monitor metric): **0.714** vs threshold 1.10 -- alert day 4+
- Trend: 0.584 (Jun 20) -> 0.671 (Jun 21) -> 0.714 (Jun 22) -> not computed (Jun 23-24, file too large)

**Verdict: THREATENED.** The dispersion edge was inverted through at least Jun 22. Improving trend (+0.04/day) is encouraging but at that pace the ratio does not recover to 1.10 for ~9 more sessions. The favNO-on-mode pivot is the directionally correct response to this inversion: when off-mode NO is not premium-priced, the mode bucket (which has the highest probability mass) is where the edge lives. The BAND_NO_SKIP_OFF1=True setting (skip +/-1 shoulders, their -6.7% at n=1214) reflects the same logic. Strategy IS adapted to the dispersion inversion; the risk is that the inversion persists or worsens and the mode-favNO edge also erodes.

**Without a fresh dispersion ratio (sigma_daily_summary gap), this is the single biggest known unknown today.**

### Assumption 2: Fills are not adversely selected (maker quality)

**Meaning:** Makers being taken against are not systematically on the losing side of informed order flow.

**Today's data (exec_audit Section 4):**
- n=46 RECYCLE099 exits (4d window): 100% wins by construction (right-censored -- only logs successful 0.99 sells)
- 1 confirmed adverse outcome Jun 24 06:20: token 6132737408678472, 497.94 shares at $0.01 (MINED + CONFIRMED). At any typical NO entry of $0.55-0.70, this represents a loss of ~$270-345 on that position. Not in exit099 (untracked from prior session).
- Jun 22 band NO win rate (pnl_ledger Section 4): 1/10 (10% vs design 65-70%). FLAGGED but single day, n too small to distinguish luck from regime.
- Jun 23-24 NO fill tape: 19 NO fills Jun 23 (d+1 resolution pending), 27 fills Jun 24 by 07:07. Outcomes not computable without Gamma API join.

**Verdict: INCONCLUSIVE at current n.** n=46 exits is right-censored wins-only. The Jun 22 NO-win-rate anomaly (1/10) is a warning signal but single-day n is too small. The Jun 24 untracked adverse (497 shares at $0.01) confirms losses exist outside the exits-only view. The critical unknown is whether today's 27 NO fills (d+0/d+1) resolve at the design 65-70% win rate or continue the Jun 22 pattern. This resolves when VPS runs the join.

**Watchdog trigger if Jun 23-24 NO win rate comes back <40%: consider stake reduction or BAND_NO pause pending investigation.**

### Assumption 3: Recycle velocity scales with capital

**Meaning:** As the book grows (more positions, more days-out), RECYCLE099 exit velocity scales proportionally, maintaining turns/day as capital increases.

**Today's data (exec_audit Section 6, pnl_ledger Section 1-2, exit099_live):**
- RECYCLE099 drove $77 of $84 estimated equity gain on Jun 23 (18 exits, 100% win rate by design)
- Jun 24 through 13:30 UTC: 10 exits logged, capital $211->$234 (+$22.37, ~+$2.2/exit)
- Daily exit counts (shadow_summary): 10-26/day across 11 days; today on pace for ~18
- SELL_EXIT backlog: 37 orders, $399 notional -- these are future RECYCLE099 exits waiting to be taken
- Maker_fills_recent.log: UNTRACKED fills at 0.98-0.999 arriving throughout the day (multiple per hour) as the backlog clears

**Verdict: SUPPORTED but paced by taker arrival, not bot action.** RECYCLE099 velocity is healthy and growing (more positions from larger stake = more eventual exits). The $399 backlog represents ~4-5 days of current exit volume, acting as a buffer. The constraint is taker liquidity at $0.99, not bot throughput. This assumption holds as long as Polymarket takers continue to clear these positions (either by buying near-resolution or via market settlement). No adverse signal today.

---

## Section 5: Market Intelligence -- Competitor Posture

**Day-of-month:** 24. 24 mod 3 = 0 -> competitor posture rotation.

**badatmath_watch activity (shadow_summary.json, Jun 24 snapshot at 13:30 UTC):**

| Date | n_rows | Notable |
|---|---|---|
| Jun 14 | 3,534 | Normal |
| Jun 15 | 2,416 | Normal |
| Jun 16 | 3,937 | Normal |
| Jun 17 | **1** | Scraper outage (single ladder row, no fill_joins) |
| Jun 18 | 2,697 | Normal |
| Jun 19 | 3,251 | Normal |
| Jun 20 | 4,304 | Normal |
| Jun 21 | 5,411 | Elevated |
| Jun 22 | 2,166 | Lower (partial day; mtime 21:32 vs typical 23:58) |
| Jun 23 | 4,715 | Normal-high |
| Jun 24 | **5,518** (through 13:30) | **Elevated -- on pace for 10,000+ rows** |

**Jun 24 activity is unusually high.** At 5,518 rows by 13:30 (54% of day), today is on track for >10,000 rows -- 2-3x any prior full day. This could reflect: more weather markets open today (higher city/date coverage = more ladder snapshots), increased fill activity, or a wider monitoring perimeter. Without row-level analysis of record types (fill_join vs ladder), cannot distinguish.

**First detected fill today (shadow_summary excerpt):**
```
ts: 1782259201.49 (~00:00 UTC Jun 24)
record: fill_join
title: "Will the highest temperature in Los Angeles be between 68-69[F] on June 24?"
outcome: Yes
price: $0.162
size: 4.01 shares
detect_lag_s: 146.5
```
- Entry price $0.162 on a YES bucket = cheap probability, d+0 market
- detect_lag_s = 146.5 seconds (2.44 minutes from fill to our detection) -- aligns with the 30s-2min information lag window
- Outcome field shows "Yes" as the outcome chosen -- he bought the Yes token at $0.162

**Pattern delta vs prior research:** Last d156804a2 commit title explicitly states "badatmath-YES forensic" -- user independently analyzed his YES fill pattern and concluded the BAND_PX_CEIL raise to 0.45 (d+1/d+2) is supported. His cheap-YES strategy (buying YES at 0.10-0.45 on d+0/d+1/d+2) is now our explicit mirror target. The BAND_PX_CEIL_D0=0.25 (same-day YES cap) and BAND_PX_CEIL=0.45 (d+1/d+2 YES cap) encode this forensic. No evidence of strategy change from his side; we are catching up to what he has been doing.

**leaderboard wallet teardown:** Cannot access data-api from container. No delta to report on wallet-level breakdown. Available via VPS curl.

**Jun 17 scraper outage (1 row):** Single record_type=ladder row for Kuala Lumpur. No fill_joins. Outage was internal to our scraper, not badatmath cessation -- his trading would have continued; we just lost visibility for that day.

---

## Section 6: Three Experiments

### Experiment 1: Band NO win-rate audit via resolution join (VPS, immediate)

**Hypothesis:** The Jun 22 band NO win-rate anomaly (1/10 = 10% vs design 65-70%) is a single-day outlier, not a structural regime shift. Gate 2 (n=213 NO fills over ~7 days) will show WR >= 55% when resolved against outcomes.

**Data:** Run `band_resolution_join.py` on VPS against the current ~213-leg Gate 2 fill set.

**Time:** 10 min VPS session (script exists, validated).

**Cost:** $0 (analysis only; no capital at risk).

**Success metric:** Gate 2 produces WR >= 55% with CI lower bound > 0% -> READY verdict. Or WR < 45% with CI upper bound < 0% -> REJECTED verdict. Either outcome advances the gate.

**Decision-if-yes (READY):** Maintain BAND_NO_STAKE=$5, consider raising BAND_NO_MAX ceiling toward 0.87 (unlocking higher-priced NO bids).

**Decision-if-no (REJECTED):** Pause BAND_NO or tighten BAND_NO_MIN to 0.60 (cut the 0.52-0.60 range that may be driving losses). Do not scale until WR recovers.

**Value-of-information:** $150/day deployed on unverified expectancy. This experiment resolves uncertainty that has been accumulating for 7+ days.

---

### Experiment 2: SELL_EXIT clearance rate at 0.97 vs 0.99 target

**Hypothesis:** Some of the 37 stuck SELL_EXIT orders (403 shares @ $0.99, matched=0 at 06:56 snapshot) have no book at $0.99 but active bids at $0.97-0.98. Lowering the exit floor by 2 cents would materially increase clearance rate with minimal impact on ROI.

**Data needed:** Query the CLOB book for each of the 37 SELL_EXIT token_ids (on VPS where Gamma/CLOB is accessible). Check if best_bid >= 0.97.

**Time:** 1 VPS session, ~15 min.

**Cost:** If yes -> at most 403 shares x $0.02 = $8.06 forgone on early exits at 0.97 vs 0.99.

**Success metric:** >= 10 of 37 tokens have CLOB bids >= 0.97 when checked. Confirms stuck-at-0.99 as the cause of the backlog.

**Decision-if-yes:** Lower BAND_RECYCLE099_TARGET from 0.99 to 0.97 (Tier 2 -- >20% change to effective ROI threshold requires data citation in commit). Expected effect: faster capital recycling, 0.93 turns/day -> closer to 1.0x, at cost of 2% per-share ROI on early exits.

**Decision-if-no:** Tokens do not have buyers at 0.97 either -> the backlog is stuck due to illiquidity or upcoming resolution (positions that will pay $1.00 at expiry automatically). No action needed; wait for market resolution.

---

### Experiment 3: sigma_daily_summary.json -- dispersion gauge infra fix

**Hypothesis:** Adding a <5KB `data/sigma_daily_summary.json` file to the VPS data-mirror output script resolves the 4-consecutive-session dispersion gauge dark period permanently.

**Contents:** `{ts, implied_sigma_mean, true_sigma_ref, disp_ratio, n_cities_used, alert: true/false}` -- computed from stwa_ladder_book.jsonl at snapshot time, written alongside the existing files.

**Time:** ~30 min VPS code change.

**Cost:** Negligible (one extra 5KB file per 15-min push).

**Success metric:** Next research agent run computes `disp_ratio` directly from `data/sigma_daily_summary.json` without accessing the 2.5MB ladder book. Alert fires/clears correctly.

**Decision-if-ratio-recovers-above-1.10:** Alert clears. Off-mode NO edge thesis reconfirmed. Consider piloting a small off-mode NO tranche (|off|=1) once Gate 2 WR is validated.

**Decision-if-ratio-stays-below-1.10:** Current favNO-on-mode pivot continues. Alert informs strategy; at least it is no longer invisible.

---

## Section 7: Single Best Action

**VPS operator runs `band_resolution_join.py` on the live VPS.**

This is the critical-path action that simultaneously unblocks Gates 1, 2, 3, and 7 -- all stalled at COLLECTING despite being far above their n thresholds. Every day of delay is capital deployed on unvalidated expectancy:

- Gate 2 (BAND_NO): n=213, $5/NO x ~30 fires/day = **$150/day deployed without a WR verdict**
- Gate 3 (FILLED_VS_FIRED): n=97, approaching 100
- Gate 7 (SUM_POSTED): n=2,954 -- largest accumulation, informing YES posting risk in the 0.70-0.85 sum_posted window

The gatekeeper_report (Section-Resolution Blocker) confirms: the script runs cleanly through dedup (1,489 legs confirmed), then hangs at the Gamma fetch step. VPS resolves both the ASN block and the latency constraint.

**Cited reports:** gatekeeper_report Section-Gate Ledger (n=213, +36/24h rate), gatekeeper_report Section-Resolution Blocker (script validated, Gamma 403 root cause), exec_audit_report Section 6 (BAND_NO_STAKE=$5, ~30 fires/day from posted deployment data).

**Concrete first step:**
```bash
ssh vps 'cd /root/Klaus && python3 analysis/weather/band_resolution_join.py 2>&1 | tail -50'
```

If READY on Gate 2: maintain or consider staged stake increase to $6 (Tier 1, <20% change). If REJECTED: pause BAND_NO, investigate which no_off or price slice is driving losses. Either outcome unlocks compounding decisions that are currently blocked.

---

## PROPOSED ACTIONS (human review)

**These require explicit human approval before implementation.**

### PA-1: Mark Gate 5 (THERMO_MAKER_NO) as VOID
**Rationale:** n=3, engine paused Jun 23 18:40 to free $25 cash. Gate frozen; n will never accumulate at 0 rate. CI upper bound barely positive (+0.7%) at n=3 -- statistically meaningless. Current state is neither collecting nor closed, which produces misleading ledger reads. If THERMO is shelved, formalize it. If resumed: restart engine at $1/fire (Tier 1), collect 17 more resolutions, then apply the CI gate.
**Options:** VOID (clean break, accept $25 cash benefit) or RESUME-SMALL (17 more fires, ~17 days, $1/fire = $17 max risk).

### PA-2: Revert M1_BETA_LOCKOUT to 0.5C floors (Gate 6)
**Rationale:** n=31/100, engine stalled. Standing rule from Jun 09 stated "at n>=100, WR>=95% AND +EV = keep; else REVERT." At 0 accumulation rate, n will never reach 100. ROI=-0.6% at n=31 (not negative enough to trigger REJECTED, not positive enough to keep). The standing rule's else-branch applies: revert to 0.5C floor. One M1_PROBE SELL_EXIT still resting at 0.99 (20 shares); can coexist with revert until it clears.
**Conservative default (no new data -> revert).**

### PA-3: Register YES_CAPTURE_SHADOW as Gate 8
**Rationale:** n=330 first-fires, growing at ~285/24h. Join window Jun 26-27. Currently unregistered -- no decision rule, no threshold, no official mandate for the analyst script. Without a gate entry, it is invisible to the gatekeeper and could accumulate past join readiness without action.
**Suggested gate spec:** n>=100 per price zone (0.10-0.25 and 0.25-0.45 separately). Run `band_yes_capture_join.py`. READY if ROI>0% with CI lower bound > 0%. Decision-if-READY: enable YES posting (already re-enabled by d156804a2 when P1 phase ends); decision-if-REJECTED: keep BAND_PX_CEIL at 0.30 (revert the d156804a2 change).

### PA-4: Add sigma_daily_summary.json to data-mirror output (infra)
**Rationale:** Dispersion gauge has been dark 4 consecutive sessions. Load-bearing edge variable. Fix: one-time VPS code change to write a <5KB daily sigma summary file. See Experiment 3 for spec.
**Not urgent today but blocks future monitoring.**

---

## Operational Alerts (non-blocked, for awareness)

| Alert | Status | Detail |
|---|---|---|
| UNTRACKED fills pervasive | Informational | 17+ UNTRACKED events by 13:30 UTC -- all from pre-restart positions. Cash reconciles correctly; position accounting is opaque. |
| Moscow NO position entry=0.9042 | Watch | 26.5 shares @ avg $0.9042; includes fills above current BAND_NO_MAX=0.85 (from prior config era). At $0.9042 average, loss-if-wrong = ~$24. |
| Disk 87% used | Monitor | 80GB/97GB. Shadow logs growing ~35-50MB/day. At this rate: critical zone (~95%) in ~2-3 weeks. Archive logs >7d. |
| Bot restarted 3x in 24h | Watch | Uptime timestamps imply restarts at ~00:10, ~08:04 UTC today plus the Jun 23 19:44 crash. Each restart wipes in-memory tracker -> UNTRACKED events grow. |

---

## State Summary

| Metric | Value | Source |
|---|---|---|
| Capital | $234.32 | bankroll.json 13:30 UTC |
| Consecutive wins | 6 | bankroll.json |
| Jun 24 gain (07:07->13:30) | +$22.37 (+10.6%) | exec_audit vs snapshot |
| Jun 23 day gain | +$14.70 (+7.41%) | pnl_ledger Section 1 |
| RECYCLE099 Jun 23 | 18 exits, +$76.997 | pnl_ledger Section 1 |
| RECYCLE099 Jun 24 (through 13:30) | 10 exits | exit099_live shadow_summary |
| Active NO bids (resting) | 4 | exec_audit Section 2 |
| SELL_EXIT backlog | 37 orders, 403 sh, $399 notional | exec_audit Section 5 |
| Phase gate | P1 (YES blocked until $600) | band_config BAND_PHASE2_CAPITAL, maker_fills log |
| Kill-switch proximity | SAFE ($159.32 buffer vs $75 floor) | pnl_ledger Section 4 |
| Dispersion alert | DAY 4+ (ratio 0.714 < 1.10) | calib_monitor Section 3 |
| Calibration alerts | None (Brier 0.0266, ECE 0.0372) | calib_monitor Section 1 |
| Gatekeeper transitions | None since Jun 23 | gatekeeper_report |
