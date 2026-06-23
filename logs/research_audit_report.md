# Klaus Research Audit — 2026-06-23
**Generated:** 2026-06-23T11:45Z  
**Snapshot freshness:** SNAPSHOT.md ts=2026-06-23T11:28Z (age 17 min ✓). `klaus systemd: active` (uptime since 06:12 UTC). Capital: $214.23 (bankroll.json 11:28 UTC). 7,918 trade rows live.  
**Specialist reports consumed:**
- exec_audit_report.md — 2026-06-23T07:07Z (age 4.6h ✓, filed 07:32 UTC)
- calib_monitor_report.md — 2026-06-23T08:10Z (age 3.6h ✓)
- gatekeeper_report.md — 2026-06-22T09:11Z (age 26.6h ✓, within 36h gate)
- pnl_ledger_report.md — 2026-06-22T23:37Z (age 12.1h ✓)

**Day-of-month mod 3:** 23 mod 3 = 2 → **Market intelligence: Platform mechanics (fee schedule / maker-rebate / liquidity-rewards changes)**

**Data access note:** git fetch network-blocked in this container. All data via GitHub MCP API. stwa_ladder_book.jsonl (2.5MB) inaccessible — dispersion ratio not computable today (carried forward from Jun 22: 0.714). maker_fills_recent.log (>1MB) and state_log.md (>1MB) returned via tail extraction.

---

## PRE-FLIGHT CHECKS

| Check | Result |
|---|---|
| SNAPSHOT.md age ≤ 6h | ✓ 17 min |
| `klaus systemd: active` | ✓ confirmed system_status.txt |
| Specialist reports ≤ 36h | ✓ all pass |
| ABORT condition | NOT triggered — proceeding |

---

## 1. PRIMARY BOTTLENECK: ROI/TURN — Band resolution deeply negative, consistent with 4-day dispersion inversion

**Verdict:** The binding constraint on compounding today is not capital deployment (phantom breaker fix freed $35 at 06:12) nor turns/day (0.39 Jun 22, structural at current capital size). It is **ROI/turn, which is −81.7% on the day's resolution batch (pnl_ledger §2).** Compounding formula = ROI/turn × turns/day × equity deployed. When ROI/turn is negative, increasing equity deployed or turns/day accelerates losses, not gains.

**The numbers:**

| Period | Band resolutions | RECYCLE099 | Net |
|---|---|---|---|
| Jun 21 | −$46.45 (27 resolutions, ~7% WR) | +$114.77 (15 exits) | **+$37.93** |
| Jun 22 | −$72.37 (30 resolutions, 6.7% WR) | +$37.18 (10 exits) | **−$35.19** |
| 2-day total | **−$118.82** | +$151.95 | **+$33.13** |

Jun 21 RECYCLE099 was large enough to mask the band hemorrhage (+2.47× the resolution drag). Jun 22 it was not (only 0.51×). The direction has flipped: when RECYCLE099 throughput drops and band losses persist, the system is net-negative for the day.

**Why the band is losing:** calib_monitor confirms dispersion ratio = 0.714 (implied sigma 0.928°C vs true sigma 0.961°C data-derived, or 1.3°C CLAUDE.md reference). The band's NO edge is predicated on "market overestimates temperature dispersion → sell off-mode NO at a premium." With implied sigma < true sigma, the market actually underprices dispersion — off-mode NO is not at a premium; it's at or below fair value. pnl_ledger §2 confirms: NO win rate Jun 22 = **1/10 (10%)** vs design expectation ~65–70%. Nine consecutive NO resolution losses at $5/stake = −$44.09. This is coherent with the dispersion signal — not noise.

**Kill-switch proximity (pnl_ledger §4):** WR<30%, PF<0.8, and day PnL >−$10 thresholds all triggered Jun 22. Capital $198.27 → $214.23 (recovered intraday via RECYCLE099 and early NO resolutions). Capital floors not breached ($214 vs $75 weekly floor, $50 ruin floor). Taker-era kill thresholds don't apply cleanly to the maker architecture (20% WR by design on cheap YES), but the **NO win rate (10%) is a signal within the maker model itself** — NO at 0.52–0.66 should win >50% of the time regardless of architecture.

**Ranking:** equity deployed > turns/day > ROI/turn is the normal priority order. Today ROI/turn must be ranked first because it is negative — fixing it before scaling deployment is the correct sequencing.

---

## 2. EXISTING-SYSTEM OPTIMIZATION

### A. no_resv=1.00 is starving the RECYCLE099 pipeline [HIGH URGENCY — capital consequence in 3–5 days]

**Finding (exec_audit §3):** The P1 NO-only commit (≥Jun 22 11:47 UTC restart) set no_resv=1.00, consuming 100% of cycle headroom for NO reservations. As of the 06:12 restart today, no_resv=1.00 on all 81 logged cycles. Result: yes_books=0/50 every cycle, yes_resv_skip avg 13.3/cycle (max 57), **0 YES posts since restart.** The bot is in a functional YES blackout.

**Why this is urgent:** RECYCLE099 depends on YES inventory entering at cheap prices. Current resting book has 33 SELL_EXIT orders (at ~$0.99, $423.78 total) from pre-restart positions. These are the last inventory. At ~10 RECYCLE099 exits/day (Jun 22 pace), this inventory depletes in **3–4 days.** After that, with 0 new YES posts, RECYCLE099 exits → 0/day → the sole positive-ROI engine in the system goes dark. The capital floor then rests entirely on NO resolution wins at the current 10% rate.

**Config context (band_config.txt):** `BAND_NO_CASH_RESERVE=0.30` was the setting before the P1 commit. State log 06:12 entry: "P1 NO-only — no_reserve 0.40→1.00 until $600." The intent is to prioritize NO deployment in Phase 1 (capital <$600), but the effect kills the YES-band inventory pipeline simultaneously.

**Expected delta if no_resv restored to 0.40:** YES queue resumes posting, ~8–12 YES fills/day resume, RECYCLE099 inventory replenishes, +$37–115/day RECYCLE099 restored on a 3–5 day lag. Negative: NO daily deployment reduces by ~60% from current level.

**Confidence:** High (mechanism is confirmed by exec_audit log; math is deterministic). **Effort:** Config change at next restart.

---

### B. Phantom breaker fix deployed 06:12 today [COMPLETE — positive]

**Finding (state_log 06:12, system_status commits):** `if status is None` bug in `_maker_reconcile_fills_locked` caused 25 dead order IDs ($33.53 phantom exposure) to persist in the resting tracker. Gate `tracked+stake ≤ 0.9×wallet` rejected ~150 cands/cycle while $33 free cash sat idle. Fix: `if not status` catches `status=""` (dead orders) correctly. 25 entries pruned, breaker exposure reset $68.68→$35.15. Post-fix: first cycle deployed freed cash into favNO positions (Seattle/Denver/Paris/Seoul NO). Capital now fully deployed (~$8 = intentional 10% buffer idle).

**Residual watch:** Phantom can't re-accumulate with the fix, but old-format dead orders from prior restarts could re-appear on the next restart if `maker_resting_state.json` file still contains pre-fix entries. The backup file (`maker_resting_state.json.bak.1782195092`) exists; confirm the live file was pruned before restart, not after.

---

### C. Gate 2 at $5/stake LIVE for day 4 past n=100 threshold [ONGOING, escalating]

**Finding (gatekeeper §Gate 2):** n=144, above threshold since Jun 20, 2nd consecutive gatekeeper run without CI verdict. Today is day 4. BAND_NO_ENABLED=True, BAND_NO_STAKE=$5, BAND_NO_DAILY_CAP=$40 live. ~14–20 NO fires/day × $5 = $70–100/day deployed unvalidated. With Jun 22 NO WR at 10% (design 65%), this is the largest single-cell risk position in the system running without a validated gate. *(Detailed in §7 — single best action.)*

---

### D. BAND_EV_MIN=0.08 admits positions the model no longer supports [WATCH]

**Finding (band_config.txt, pnl_ledger §4):** BAND_EV_MIN was lowered 0.15→0.08 on 2026-06-05 "against model advice, unvalidated; daily halt is the only backstop" (per band_config comment). EV calculation uses calibrated sigma as input. With dispersion inverted (ratio 0.714), the sigma input to the EV formula is stale — EV calls of "0.08" may be negative in expectation. The 0.08 threshold was a user override on a model flag. With the 2-day loss pattern, the original 0.15 threshold deserves reconsideration, but this requires the VPS Gate 1 resolution join to confirm by EV bucket (n≥100 per cell required first).

**No action today** — requires Gate 1 resolution join output. Flag for VPS operator.

---

## 3. GATE PIPELINE

| Gate | n | Status | ETA to verdict | Accelerator |
|---|---|---|---|---|
| **2. BAND_NO+PAIR_FAV** | **144** | **COLLECTING ★★ n≥100 day 4** | **BLOCKED — VPS Gamma join** | `band_resolution_join.py --start 2026-06-19T00:30 --reason fire_no pair_fav pair_samebucket` |
| 1. BAND_YES | 5,419 | COLLECTING | BLOCKED — Gamma 403 | Same VPS join; ~235 legs/day accumulating |
| 3. FILLED_VS_FIRED | 110 | COLLECTING | BLOCKED — VPS CID join | Jun18 fills age out in ~3 days now — TIME-SENSITIVE |
| 4. BASKET_EXIT | 33 | **VOID (retired Jun22T07:35)** | Dead — 4 fatal flaws | No action; gate closed |
| 7. SUM_POSTED [0.70,0.85] | 2,643 | COLLECTING | BLOCKED — Gamma 403 | Same VPS join; fraction of YES fires rising 47%→68% |
| 5. THERMO_MAKER_NO | 3 | **STALLED — 0 fills/day, CI upper barely positive** | INFINITE | Near-REJECTED: 1 more loss pushes CI fully negative |
| 6. M1_BETA_LOCKOUT | 31 | **STALLED — 0 fires/day, provenance unverified** | INFINITE | Provenance: VPS verify n=31 basis or reset to n=1 |

**Gate 2 is the nearest-READY gate** — data exists, script exists, threshold passed. No other gate is actionable without the same VPS Gamma join.

**Gate 5 (THERMO_MAKER_NO) is near-REJECTED:** n=3, WR=33%, ROI=−66%, CI95=[−132.6%, +0.7%]. CI upper bound = +0.7% — one more loss pushes it below zero and gate should be formally REJECTED. BAND_TAILNO_VALIDATED=False already gates live deployment, so no capital is at risk from this stall. **Consider recommending kill to free ledger overhead** — this gate has been stalled for 10+ days with 0 fills/day and ETA INFINITE. A stalled near-negative gate consumes monitoring resources without hope of advancing.

**Gate 6 (M1_BETA_LOCKOUT) provenance issue (from gatekeeper):** n=31 basis unverifiable from available data; only 1 confirmed M1-style trade in trades.jsonl (May-26 Moscow). VPS operator: if n=31 is unverifiable, reset to n=1 and treat as data-collection. At n=1, this gate is a minimum 100 fires away from decision, and fires are currently at 0/day.

**To accelerate data accumulation without degrading expectancy:**
- Gates 1, 2, 7: accumulation rate is healthy (235/155/170 per day). Breadth of city coverage is the lever — more cities = more fires. At current 51-city coverage this is already at practical maximum.
- Gate 3: rate 2/day (fills), time is the constraint not breadth. Cannot accelerate without artificially inflating fill count.
- Gates 5 & 6: blocked by structural fire-rate issue (BAND_NO_MAX=0.85 and phase-lock respectively), not data breadth. Fixing the stall requires diagnosing why candidates never convert to fires, not adding cities.

---

## 4. ASSUMPTION ATTACK

### Assumption 1: Dispersion premium persists (band edge)
**Status: THREATENED — inverted for 4 confirmed sessions, 2-day loss pattern coherent with inversion.**

| Metric | Value | Source |
|---|---|---|
| Implied sigma (PRE_PEAK, 16 cities) | 0.928°C | calib_monitor §3, Jun 22 |
| True sigma (data-derived, 149 city-days) | 0.961°C | calib_monitor §3 |
| True sigma (CLAUDE.md reference) | 1.3°C | CLAUDE.md |
| Dispersion ratio (vs 0.961) | **0.966** (~parity) | derived |
| Dispersion ratio (vs 1.3°C) | **0.714** (inverted, alert fires) | calib_monitor |
| 7-day trend | 0.584 → 0.671 → 0.714 → not computed | improving ~+0.04/day |

The calib_monitor alert fires against the 1.3°C reference. Against the empirical 0.961°C reference, the ratio is ~parity. The ambiguity between these two references is unresolved (Experiment 2 below). **However, the 2-day band resolution loss pattern (-$118.82, NO WR 10% vs design 65%) is consistent with dispersion being at or below fair value for the off-mode NO positions the bot is taking.** The loss pattern is the harder evidence; the ratio is the model signal. Both point the same direction.

The recovery trajectory (+0.04/day) puts the alert-cleared threshold (1.10 vs 1.3°C, or any ratio >1.0 vs 0.961°C) at approximately 9–10 sessions away if the trend holds. One adverse reversal (as occurred Jun 14, reported in Jun 22 audit) could reset it.

**Threat to compounding:** With ROI/turn negative on band resolutions and RECYCLE099 as the only positive engine, the dispersion premium is the mechanism linking these two observations. If it stays inverted, band resolutions continue to bleed. If RECYCLE099 throughput also drops (due to YES inventory depletion from no_resv=1.00), there is no positive offset. **This is the existential scenario for the current config.**

### Assumption 2: Fills are not adversely selected (winner's curse)
**Status: UNVERIFIABLE — Gamma API 403 blocks the authoritative join. Proxy evidence mixed.**

- exec_audit §4: 64 RECYCLE099 exits at $0.99, all positive PnL ($304.45/$246.28 cost = +123.6% gross ROI on winners). This is the survivor-biased sample — only winners visible here.
- exec_audit §4: All-fires YES mean bid $0.178 (n=1,826 legs); resolved winner mean entry $0.455 (median $0.550). Resolved winners average entry well above the all-fires mean — fills are concentrating in more expensive (higher-fill-probability but lower-odds) buckets. This is a mild adverse-selection signal for YES (filling where fill-probability is high but EV is lower).
- NO fills: 9/10 losses Jun 22 at entry 0.52–0.66. The question is whether the fills concentrated in buckets that were precisely the mode buckets at resolution. This requires the resolution join to determine.
- No "reaped dead entry" lines in 7d fill tape (exec_audit §5): either all filled positions resolved as winners before 2h reclaim timeout, or losers expired naturally without leaving a reap trace. This is neutral — no adverse-selection reap-trigger signal.

**n<40 in YES resolved winner set — DATA-COLLECTION per decision rules.** The adverse-selection verdict for YES requires Gate 3 (filled-vs-fired, n=110 fills). For NO, it requires Gate 2 (resolution join). Both blocked.

### Assumption 3: RECYCLE099 velocity scales with deployed capital
**Status: THREATENED — yes_inventory pipeline severed by no_resv=1.00.**

- Jun 22 RECYCLE099: +$37.18 (10 exits) — down from Jun 21 +$114.77 (15 exits). The step-down is partly from the bot restart at 11:47 UTC Jun 22 (cutting afternoon posting), partly from inventory draw.
- exec_audit §1: resting book has 33 SELL_EXIT orders @ ~$0.99 ($423.78 potential). This is the remaining inventory.
- exec_audit §3: 0 YES posts since 06:12 restart today. no_resv=1.00 consuming 100% of headroom.
- At 10 RECYCLE099 exits/day: **33 orders ÷ 10/day = 3.3 days before inventory exhaustion.** After that, RECYCLE099 revenue → $0/day until YES queue resumes.
- **Current state: RECYCLE099 is drawing down finite inventory with no replenishment. This is the load-bearing positive-ROI engine of the system and it has a ~3-day remaining runway under current config.**

The velocity assumption held on Jun 21 (+$114.77 from 15 exits) and partially held on Jun 22 (+$37.18 from 10 exits). It will NOT hold on Jun 25+ unless no_resv is reduced and YES queue is restored.

---

## 5. MARKET INTELLIGENCE: Platform Mechanics (day-of-month mod 3 = 2)

**Scope:** Fee schedule, maker-rebate program, and liquidity-reward changes since last known state. Container cannot access Polymarket directly; sourced from web search (current session) and state_log knowledge.

### Fee schedule — current state (no new changes detected)

As of March 30, 2026 (last confirmed expansion):
- **Weather** category: taker fees enabled. Maker rebate = **25% of taker fees**, distributed daily in USDC.
- Finance: 50% maker rebate (highest category — likely a liquidity bootstrapping incentive for the newly-fee-bearing category).
- Crypto markets: 20% rebate.
- Geopolitics/world events: 0% fee (only free category remaining).
- Fee level: dynamic 0–3.15% at 50% odds, near-0% at extremes (same as known since March 30; no evidence of further rate changes).

**No structural changes detected since March 30, 2026 from available sources.** Web search finds no announcements of fee schedule revisions between March 30 and June 23, 2026.

### Maker rebate verification [OUTSTANDING FLAG]

pnl_ledger §3 reports cumulative expected rebate = **$5.95** (through Jun 22), up from $5.40 prior. At 25% rebate rate on weather taker fees, at Klaus's fill volumes, expected ~$0.55/day in USDC. This has been flagged since Jun 21 (pnl_ledger §3: "⚠ REBATE VERIFICATION FLAG: Cumulative expected rebate $5.95 >> $1 minimum accrual threshold").

The pnl_ledger notes this is an **upper bound** (assumes Klaus is sole market maker in each category, which is not true — actual rebate is proportional to maker share). Realistic rebate is likely 5–20% of $5.95 depending on competitive maker share. Still, **>$0 USDC should be receivable.** VPS operator: verify via wallet transaction history (Polymarket distributes daily). If no receipt has appeared, post to Polymarket Discord #support with wallet address and `cf-ray` header from a recent API response.

**Delta vs state_log knowledge:** No new platform mechanics changes observed. Rebate flag is carry-forward from Jun 21 entry; unverified as of this session.

---

## 6. THREE EXPERIMENTS

### Experiment 1: Gate 2 VPS Resolution Join [CARRY-FORWARD, DAY 4]
**Hypothesis:** BAND_NO+PAIR_FAV legs (fire_no / pair_fav / pair_samebucket events in band_struct_lite, post-Jun19T00:30 clean window) have positive ROI with CI95 lower bound > 0, meaning the NO edge is real and current 2-day losses are weather-regime variance, not structural edge failure.

**Data required:** Gamma winner-flag resolution join for ~144 NO legs. Script: `analysis/weather/band_resolution_join.py` on VPS.  
**Time:** Same-day VPS run. **Cost:** Zero capital.  
**Success metric:** CI95 lower > 0 on the full NO set (and specifically on the 0.52–0.66 entry-price bucket where Jun 22 losses concentrated, n≥30 per slice).  
**Decision-yes (CI lower > 0):** Band NO edge confirmed on clean-window data. Current losses are regime variance. Hold BAND_NO at $5/stake; monitor dispersion ratio recovery. Flag Jun 22 result as an outlier and continue.  
**Decision-no (CI spans zero or upper < 0):** Band NO edge is absent or negative. Immediately reduce BAND_NO_STAKE from $5 to $1 (or set BAND_NO_ENABLED=False pending dispersion recovery above 1.10). 2-day loss pattern is structural bleed, not variance.

**Concrete first step:**
```bash
# On VPS — from band_struct_lite files
python3 analysis/weather/band_resolution_join.py \
  --start 2026-06-19T00:30 \
  --reason fire_no pair_fav pair_samebucket \
  --min-n 30
# Post CI output to state_log immediately
```

---

### Experiment 2: RECYCLE099 Inventory Depletion Timeline (PASSIVE)
**Hypothesis:** With no_resv=1.00 blocking YES queue, the 33 remaining SELL_EXIT resting orders exhaust within 3–4 days (at ~10 exits/day pace), after which RECYCLE099 revenue drops below $5/day and becomes an insufficient offset to any band resolution losses.

**Data required:** Count SELL_EXIT entries in maker_resting_state.json daily (via data-mirror), compare against RECYCLE099 exit counts in exit099_live.jsonl.  
**Time:** Passive — results available in 3–5 days. Zero effort.  
**Success metric (confirming hypothesis):** RECYCLE099 exits/day drops below 3/day by Jun 27–28.  
**Decision-yes:** RECYCLE099 inventory confirmed depleting. Trigger review of no_resv parameter: either restore YES queue (no_resv →0.40) or accept that the system is now a pure NO-resolution system and size accordingly. At NO WR 10%, pure NO is a −$35/day drift.  
**Decision-no (RECYCLE099 stays >5/day despite YES blackout):** RECYCLE099 is drawing from a source not captured in maker_resting_state.json (e.g., pre-restart positions in a different log path). Investigate alternative inventory source; NO-only strategy is more durable than assumed.

---

### Experiment 3: Dispersion Sigma Reference Audit (VPS, 1–2h)
**Hypothesis:** The CLAUDE.md 1.3°C sigma reference is empirically overstated (likely derived in a different season or using a different statistical definition). The data-derived sigma (0.961°C, n=149 settled city-days from calib_monitor) is the empirically correct baseline, meaning the current dispersion ratio (0.928/0.961 = 0.966, near-parity) does NOT indicate edge inversion — only the gap from 0.966 to 1.0 needs closing, not 0.714 to 1.10.

**Data required:** Original derivation method of the 1.3°C reference (likely in `strategy/stwa_engine.py` comments, prior research notes, or `analysis/weather/sigma_calibration.py` on VPS). Also seasonal check: run std(resolved_outcome − mode_center) by calendar month to detect summer-vs-winter sigma variation.  
**Time:** 1–2h VPS analysis. **Cost:** Zero.  
**Success metric:** If original method = std(final_max − mode_center) on settled markets (same as calib_monitor's data-derived method) AND yields 0.961°C not 1.3°C, the reference is stale and should be updated. If original method is different (e.g., climatological 30-year percentile spread), the values measure different things and the calib_monitor gauge needs a methodology note.  
**Decision-yes (reference confirmed stale, 0.961°C correct):** Update `true_sigma` reference in calib_monitor_state.json to 0.961; recalculate disp_ratio7 as 0.966; DISPERSION_ALERT suspends; YES band reassessed as near-neutral, not inverted. Does not explain the 2-day loss pattern (loss mechanism was NO win rate, not YES performance) but removes the structural framing that the edge is inverted.  
**Decision-no (1.3°C reference correct for its purpose):** Dispersion alert is accurate; NO edge may be structurally inverted in current summer regime; consider per-city dispersion gate (post only cities with implied σ ≥ 0.961°C — today: Cape Town 1.08, London 1.05, Kuala Lumpur 1.03, Warsaw 0.98, Jeddah 0.97, Moscow 0.96 — 6 of 16 PRE_PEAK cities pass).

---

## 7. SINGLE BEST ACTION

**Gate 2 VPS resolution join — day 4 past threshold. BAND_NO is LIVE at $5/stake, NO WR ran 10% on Jun 22. Run the join today.**

**Why Gate 2 and not restoring YES queue (§2A):**
Both are urgent, but they are sequenced. The Gate 2 join determines whether BAND_NO should be continued at all. If the join returns CI-negative, BAND_NO should be halted — and in that scenario, restoring YES queue becomes the priority. If the join returns CI-positive, the 2-day loss is confirmed as weather-regime variance, and the question of YES queue restoration (via no_resv) can be framed correctly: RECYCLE099 is reducing, but the NO engine is validated, so the capital allocation between YES and NO is a calibrated choice, not an emergency. **Resolving Gate 2 is the prerequisite decision that informs everything else.**

**Why not dispersion reference audit first:**
Dispersion ambiguity (Experiment 3) has no immediate capital consequence — YES posting is already halted by no_resv=1.00 regardless. Gate 2 has $5/stake × ~17 fires today = ~$85 being deployed right now without a validated edge verdict.

**Supporting citations:**
- **gatekeeper_report:** "n=144: 2nd consecutive run above n=100 with no CI verdict — urgent. BAND_NO_ENABLED=True, BAND_NO_STAKE=$5 LIVE. The NO engine runs without a validated edge gate."
- **pnl_ledger §2:** "NO win rate 1/10 (10%). Design expectation ~65–70%… indicates temperatures landed in the specific mode bucket at 90% rate." Two-day pattern: 9/10 and presumably similar Jun 21 (implied from −$46.45 resolution losses on Jun 21).
- **calib_monitor §3:** "The edge inversion on off-mode NO remains the operative assumption until a fresh compute confirms otherwise." Dispersion ratio 0.714 (Day 4 alert continuous).
- **exec_audit §3:** "no_cands running 174–184 today (vs ~20 earlier in the week)" — NO candidate pool is large, meaning the join will have ample data to work with if run now. The longer the delay, the more capital accumulates in the unvalidated position.

**This is the fourth consecutive session this action has been recommended and not yet completed. Each day of delay adds ~$85–100 in newly unvalidated NO exposure.**

---

## PROPOSED ACTIONS (human review)

**[P0 — TODAY, URGENT, Gate 2 is blind at day 4]** VPS: run `python3 analysis/weather/band_resolution_join.py --start 2026-06-19T00:30 --reason fire_no pair_fav pair_samebucket`. Post CI95 output to state_log immediately. Branch: CI lower > 0 → hold $5 NO; CI spans zero → reduce BAND_NO_STAKE $5→$2; CI upper < 0 → set BAND_NO_ENABLED=False.

**[P1 — HIGH, RECYCLE099 runway ~3 days]** Decide on no_resv before Jun 26: current 33 SELL_EXIT inventory exhausts at ~10 exits/day. If YES queue stays dark, RECYCLE099 → $0/day. Options: (a) restore no_resv 1.00→0.40 to re-enable YES queue alongside NO; (b) accept YES blackout and size for NO-only P&L. Option (a) is preferred if Gate 2 returns CI-positive (NO edge confirmed, YES adds compounding upside). Option (b) is appropriate only if Gate 2 returns CI-negative AND the bot should run NO-only in reduced-stake mode during dispersion recovery.

**[P2 — MEDIUM, 1–2h VPS, no capital risk]** Dispersion sigma reference audit (Experiment 3). Determine if the 1.3°C reference is stale. If data-derived 0.961°C is correct, DISPERSION_ALERT suspends and YES band framing changes from "inverted edge" to "neutral, improving." Does not fix the NO win rate issue but removes the structural negative framing.

**[P3 — TIME-SENSITIVE, ~3 days remain]** Gate 3 filled-vs-fired join on VPS before Jun18 fills age out. n=110 (YES=66, NO=44). Join per (token, side) against all-fires per slice for winner's-curse verdict.

**[P4 — LOW effort, ADMIN]** Formally close Gate 5 consideration. n=3, STALLED 10+ days, CI upper barely +0.7%, fill rate 0/day (INFINITE ETA). One more loss pushes CI fully negative. BAND_TAILNO_VALIDATED=False already blocks live capital; no action on capital. But consider retiring Gate 5 from active ledger to avoid monitoring overhead. Human sign-off needed to formally REJECT vs STALL.

**[P5 — ADMIN, confirm]** Gate 4 BASKET_EXIT is VOID per state_log Jun22T07:35. Confirmed in this report as dead. Human: confirm Gate 4 is fully closed with no basket-exit executor planned; remove from active gate count.

**[P6 — VERIFY, platform mechanics]** Maker rebate: cumulative expected $5.95 in USDC unverified. VPS operator: check wallet transaction history for daily USDC rebate payments from Polymarket. If unreceived, contact Polymarket #support with wallet + recent cf-ray header.

**[NO CHANGE]** Capital $214.23, above all floors ($75 weekly, $50 ruin). STWA_REGULAR_YES_ENABLED=False, STWA_REGULAR_NO_ENABLED=False per band_config (calibration-curve-based systems off). Isotonic: deployed curve (17d old) is the lesser defect vs candidate; do NOT deploy candidate (terminal ceiling delta −0.258 at p_raw=1.0 severely underprices 99% empirical WR bucket). Band YES config frozen at Jun19T00:30 clean window; gates 1/7 still collecting.

---

*All claims sourced from: exec_audit (07:07 UTC Jun23 ✓), calib_monitor (08:10 UTC Jun23 ✓), gatekeeper (09:11 UTC Jun22 ✓ within 36h), pnl_ledger (23:37 UTC Jun22 ✓), state_log.md tail (Jun23 06:12 entry), band_config.txt (11:28 UTC Jun23), bankroll.json (11:28 UTC Jun23). Web search: Polymarket fee schedule 2026. No analysis drawn from n<40 data. No strategy code or gate parameters modified by this agent. REPORT-ONLY.*
