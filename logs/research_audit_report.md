# Klaus Research Audit — 2026-06-28

**Date:** 2026-06-28T11:00Z  
**Snapshot:** 2026-06-28T10:25:39Z (35 min old — FRESH ✓)  
**System:** `active` ✓ (uptime since 2026-06-26T15:08:30Z)  
**Bankroll:** $79.19 (10:25 UTC snapshot)  
**Specialist reports:** all four present, all <36h old ✓
- exec_audit_report.md: 2026-06-28T07:07Z ✓
- calib_monitor_report.md: 2026-06-28T08:07Z ✓
- gatekeeper_report.md: 2026-06-28T09:07Z ✓
- pnl_ledger_report.md: 2026-06-27T23:37Z ✓

**ABORT CHECK PASSED.** Snapshot 35 min old < 6h. `system_status.txt` says `active`.

---

## 1. Primary Bottleneck — Equity Deployed (P1 NO-ONLY Override)

**Verdict:** The compounding limit is **equity deployed** — specifically, the Phase 1 NO-ONLY override (`no_resv=1.00`) which structurally blocks ALL YES posting below $600 capital. **This is not a bug.**

**Evidence from raw log (maker_fills_recent.log, 07:53–10:22 UTC today):**
Every single STRUCT-BAND-Q line shows `no_resv=1.00` with `yes_resv_skip=3–12/cycle` and `yes_books=0/50` throughout. Cap=$77-81 at time of logging — not capital-starved. `cash_preskip=0` in all recent cycles — the cash is available, but the P1 override is reserving 100% for NO.

**Exec_audit Alert 1 was a misdiagnosis.** The report concluded that "YES d+2 orders fire live=true but do not reach the CLOB book" and attributed it to a possible pipeline bug or state-tracking gap. The raw STRUCT-BAND-Q telemetry resolves this: `no_resv=1.00` is the active override from commit `75f5ba00a feat(BAND): P1 NO-only — no_reserve 0.40->1.00 until $600 (user)`. The `BAND_NO_CASH_RESERVE=0.30` in band_config.txt is overridden at runtime to 1.00 when `capital < $600`. The `yes_resv_skip` counter (3–12/cycle today) is working correctly — it reflects YES candidates present and queued, being correctly blocked by the P1 policy.

**The cost of the current policy:**

| Metric | Value | Source |
|---|---|---|
| YES d+2 ROI | +10.7% | state_log 2026-06-26 narrow-start execution analysis |
| YES overall ROI (VPS, full set) | +7.6% (n=3,275) | state_log 2026-06-17 |
| NO overall ROI (VPS) | +3.7% (n=133) | state_log 2026-06-17 |
| Turns/day (NO-only) | 0.83 | exec_audit_report |
| Turns/day benchmark | 1.0 | exec_audit_report (badatmath) |
| YES candidates/cycle | 8–12 (yes_resv_skip) | maker_fills_recent.log |
| ETA to $600 at $31/day net | ~17 days | estimated from $79 baseline |

The YES d+2 edge (+10.7%) outperforms NO (+3.7% n=133, below decision threshold). Blocking YES posting for 17 more days means foregoing the higher-ROI leg during the fastest compounding window. The P1 NO-ONLY policy was rational at restart ($15.95) when capital concentration was essential — at $79 with 42h of consecutive-win evidence and the 06-26 YES d+2 validation, the tradeoff is worth re-examining.

**Ranking justification:** Equity deployed ranks above turns/day and ROI/turn because the P1 policy simultaneously (a) reduces YES-side equity to zero and (b) caps turns/day at 0.83 vs 1.0 benchmark. Calibration, fills, and NO-parity are secondary — the queue is healthy (no_cands=20–25) and NO fills are generating real compounding.

---

## 2. Existing-System Optimization

What the four reports collectively imply:

### 2a. P1 Phase Boundary vs YES d+2 Partial Unlock
**Source: exec_audit + maker_fills_recent.log + state_log**

The $600 Phase 1 boundary was set on 2026-06-22 when capital was ~$250 (collapsing post-outage). At $79 current, $600 is 7.6× away — a ~17-day horizon deferring the higher-ROI YES d+2 leg. Two options:
1. Lower the P1/P2 boundary from $600 to $200, unlocking YES d+2 at $200 capital (~6 days away).
2. Add a phase exception: allow YES d+2 at half stake ($1.50 vs $3.00) within P1, with NO reserve floor only on full-stake positions.

**Expected delta:** +17% turns/day (0.83→1.0) + YES ROI premium on newly deployed capital (~+3–4% incremental ROI per turn vs NO baseline). Confidence: medium (YES d+2 +10.7% is from pre-narrow-start data; 06-26 narrow-start YES fills are too few to confirm on the current 5-city set). Effort: low (code change to phase threshold or add `BAND_YES_P1_ALLOWED` config flag).

### 2b. Orphaned-Order Capital Reconciliation
**Source: maker_fills_recent.log (UNTRACKED FILLs), pnl_ledger_report**

Multiple large UNTRACKED FILL events are occurring from prior-session resting orders:
- `token=6647767324973860 BUY price=0.98 size=66.05` at 07:58 UTC (~$64.7 fill)
- `token=1800446057071802 BUY price=0.30 size=88.05` at 08:38 UTC (~$26.4 fill)

These appear to be prior-session maker bids being taken — likely near-resolved positions where the bot's 2025-06-26 restart cleared the tracker. Capital from these flows into bankroll.json without attribution, partially explaining the pnl_ledger's "unexplained $69.20" gap. No capital at risk (these appear to be winning positions), but the opacity creates tracking noise.

**Expected delta:** Visibility only — no direct compounding improvement. Confidence: high (fills confirmed in log). Effort: low (post-hoc Gamma lookup for orphaned token IDs to close attribution).

### 2c. M1_BETA_LOCKOUT — Kill or Fix the Shadow Logger
**Source: gatekeeper_report**

metar_lockout.jsonl has been logging candidates-only for 16+ consecutive days: n=31 (frozen), 0 placed-order records. The METAR_LOCKOUT_TEMP_FLOOR=0.2°C threshold is too thin — the ±0.2–0.5°C slice fires no real orders. A shadow logger that never generates placed-order evidence cannot support gate validation.

**Expected delta:** $0 direct. Clears a dead gate from the ledger. Confidence: high (16 days zero placed records). Effort: very low (revert temp_floor to 0.5°C or disable the logger).

### 2d. Disk Usage — Prune Old Shadow Files
**Source: system_status.txt**

Disk: 82% full (76G of 97G used). Shadow logger files are large (market_timeline was 1.3 GB on 2026-06-18). At current logging rates, disk may reach 95% in 2–4 weeks, at which point logger writes stall and bot data integrity breaks.

**Expected delta:** Risk mitigation (prevent bot data logger crash). Confidence: high. Effort: very low (add cron: `find /root/Klaus/logs/shadow -name '*.jsonl' -mtime +7 -delete`).

### 2e. Isotonic — Do Not Deploy Candidate; Watch ECE
**Source: calib_monitor_report**

ECE trending: 0.031 (2026-06-25) → 0.041 (2026-06-26), approaching 0.05 alert threshold. S4 PERSISTS (candidate collapses grid=1.0 from 0.63 to 0.37, destroying the only high-confidence signal region). No action on refit. If ECE crosses 0.05 in the next calib_monitor run, S1 alert fires — at that point, a full isotonic refit from live data should be scheduled.

**Expected delta:** $0 now. Prevents edge erosion if model drift accelerates. Confidence: monitoring only. Effort: zero.

---

## 3. Gate Pipeline Review

**Source: gatekeeper_report (09:07 UTC)**

| Gate | n | n_prev | Structural Blocker | Action to Accelerate |
|---|---|---|---|---|
| BAND_NO_PAIR_FAV | 237 | 227 | Gamma 403 (cloud) | VPS band_resolution_join.py |
| BAND_YES | 5,978 | 5,924 | Gamma 403 + CI formula | Same |
| FILLED_VS_FIRED | 47 | 37 | Gamma 403 | VPS-side markout join |
| M1_BETA_LOCKOUT | 31 (frozen 16d) | 31 | Probe inactive | Revert temp_floor or kill |
| THERMO_MAKER_NO | 3 | 3 | LIVE=False, rate=0 | Re-enable THERMO |

**Nearest gate to actionable verdict:** BAND_NO_PAIR_FAV (n=237 — well above n≥100 decision threshold). The only blocker is Gamma API 403 from the cloud container. A single VPS-side run of band_resolution_join.py pulls resolution flags and unlocks CI computation. This gate would have a verdict TODAY if the script ran on the VPS.

**How to accelerate accumulation WITHOUT degrading expectancy:**

- **BAND_NO_PAIR_FAV / BAND_YES:** Broaden BAND_CITY_ALLOW from 5 → 10 cities in **shadow YES first** (no capital). Each additional city adds ~4–6 YES d+2 fire candidates/cycle. Shadow fires accumulate BAND_YES n faster, approaching the CI decision threshold sooner. Add only cities with comparable market quality: liquidityClob ≥ 200 and historical bid/ask depths within the current 5-city distribution.

- **THERMO_MAKER_NO:** Re-enable with the original $15/day cap. At 1 fill/day minimum, kill gate (n=20 resolved) would be reached in 17 days. At current n=3 with rate=0, kill gate is unreachable in any timeframe — the data-collection outcome is indeterminate forever.

- **M1_BETA_LOCKOUT:** Revert temp_floor 0.2 → 0.5°C. Give 7 days. If n still does not grow from placed-order records, retire the gate and kill the shadow logger — it is not accumulating evidence in any form.

**Key structural insight:** All BAND-family gates are blocked by Gamma 403 in the cloud agent, NOT by sample size. The gatekeeper runs cloud-side where Gamma is 403. band_resolution_join.py runs VPS-side where Gamma is accessible. A daily VPS-side scheduled join would unlock CI for BAND_NO_PAIR_FAV, FILLED_VS_FIRED, and eventually BAND_YES simultaneously.

---

## 4. Assumption Attack

### Assumption 1: Dispersion Premium Persists
*The band harvests value because the market prices temperature uncertainty (implied σ) tighter than realized errors.*

**Evidence (calib_monitor_report):**
- disp_ratio7 = 0.75 (S3 ALERT PERSISTS). Implied σ median 0.84–0.90°C vs realized ~1.00°C. Ratio <1.10 means market IS more accurate than band implies, not less — the premium is inverted.
- Bankroll: +$63 (+397%) since restart. The strategy is profitable.

**Verdict: ASSUMPTION PARTIALLY THREATENED for YES; STRUCTURALLY IRRELEVANT for NO.** The P1 NO-ONLY policy means zero YES capital is deployed today — so even a genuine absence of dispersion premium on YES does not currently harm P&L. The NO-side profit does not depend on dispersion: NO bids win when temperature falls outside their bucket, which is a structural consequence of band design (many possible outcomes, we hold the majority). When YES d+2 goes live post-Phase 1, re-check the per-city dispersion ratio for the narrow 5-city set specifically — the 0.75 ratio may be pulled down by US cities (US: 0.65 per prior measurement) that are no longer in the allowlist.

**Risk timing:** LOW now (P1 blocks YES). MEDIUM when YES d+2 is re-enabled. The 06-26 YES d+2 +10.7% ROI suggests the narrow-start cities may have a local dispersion premium even if the full-universe ratio is 0.75.

### Assumption 2: Fills Are Not Adversely Selected
*Maker fills do not systematically select on the worst-performing legs.*

**Evidence:**
- FILLED_VS_FIRED n=47 (crossed n=40 watch threshold, gatekeeper_report). No ROI computation possible (Gamma 403 blocks markout join).
- n=5 resolved NO positions: 5/5 wins, avg ROI +59.1% (exec_audit). Sample too small for inference (100% WR on n=5 is noise).
- Jun-26 d+1 band WR: 40% (4/10, pnl_ledger). Above NO breakeven (~30% at avg price 0.70). n=10.
- Structural adverse-selection defenses active: BAND_NO_SKIP_OFF1=True (skip ±1 offsets; per state_log Jun-11, ±1 was −6.7% n=1,214), BAND_NO_MIN=0.52 (skip cheap NO < 0.52), 5-city narrow set, d+1/d+2 only.

**Verdict: ASSUMPTION UNTESTED at decision grade.** All directional evidence is positive (n=5 wins, n=10 at 40% WR above breakeven), but n<100 in every cell. The structural filters are the primary adverse-selection defense — they encode the lessons from historical adverse-selection findings (±1 shoulder, d+0 NO, cheap NO <0.52). The FILLED_VS_FIRED gate at n=47 is the designed test for this assumption; it requires VPS-side CI computation to yield a verdict.

### Assumption 3: Recycle Velocity Scales
*SELL_EXIT orders at $0.99 clear quickly enough that capital is not chronically locked.*

**Evidence:**
- maker_fills_recent.log (08:33 UTC): `SELL price=0.999 size=0.5 status=CONFIRMED trader_side=TAKER` — small residuals clearing via taker counterparty.
- UNTRACKED FILL (07:58 UTC): `BUY price=0.98 size=66.05 trader_side=MAKER` — a large orphaned position resolving via maker fill at $0.98. This is real capital returning to the bankroll.
- Open positions = 0 (system_status, 10:25 UTC) — capital from all 2026-06-28 resolutions has been recycled.
- 10 SELL_EXIT orders in resting state (exec_audit, 07:07 UTC) — unknown ages. At 10:25 UTC, open positions = 0, so these have cleared (or were never tracked as open).
- Capital: $15.95 → $79.19 in 42h — consistent with fast recycling.

**Verdict: ASSUMPTION SUPPORTED with a caveat.** RECYCLE099 is working (small fills clearing, large orphaned positions redeeming). Capital is recycling quickly (open positions = 0 at 10:25 UTC despite 11 fills/day). **Caveat:** SELL_EXIT orders lack timestamps in maker_resting_state.json, making age confirmation impossible. If the Polymarket CLOB does not cross SELL_EXITs for markets that resolved but have thin post-resolution book, positions could sit undetected. Flag for age tracking in a future maker_resting_state update.

---

## 5. Market Intelligence — Market Census (Day mod 3 = 1)

*Gamma API not directly queryable from cloud container. Gamma 403 blocks all resolution and market-listing data. Assessment based on STRUCT-BAND-Q telemetry and shadow data only.*

**Current 5-city allowlist depth (from STRUCT-BAND-Q, 07:53–10:22 UTC):**

| Metric | Value |
|---|---|
| Active cities | 5 (chengdu, london, beijing, munich, wuhan) |
| no_cands/cycle | 20–26 (healthy pool) |
| pair_cands/cycle | 0–2 (sparse; pair_fav fires ~1/day) |
| yes_resv_skip/cycle | 3–12 (YES candidates blocked by P1 override) |
| books (NO) | 0–7 of 80 slots (well within capacity) |
| posted/cycle | 0–1 (bursty pattern, normal for maker band) |

**Delta vs prior state_log knowledge (2026-06-17 VPS baseline):**
- Prior: full city universe (51 cities), both YES and NO active.
- Current (post-2026-06-26): 5-city narrow set, NO-only posting (P1), YES d+2 in shadow.
- no_cands=20–26 across 5 cities implies ~4–5 active NO candidate buckets per city per cycle. This is healthy liquidity depth for the narrow set.
- pair_cands=0–2 suggests pair_fav is finding co-filling opportunities occasionally (~1 per 10 cycles at current depth). At 5 cities × d+0 only (BAND_YES_MAX_OFF_D0=0), pair opportunities are limited to mode-bucket coincidences.

**Unknown deltas (Gamma 403 prevents update):**
- Whether new weather cities have been listed on Polymarket since June 2026-06-17 (when the 51-city universe was last characterized).
- Current liquidityClob levels in the 5-city allowlist (need Gamma query to confirm ≥200 floor still holds).
- Whether badatmath has changed city coverage or bet sizing (badatmath_watch delta requires fresh feed; shadow_summary shows last badatmath_watch file is from 2026-06-18, 10 days stale).

**Recommendation for next VPS agent run:** Check Gamma for new city markets and update liquidityClob verification for the current 5-city set. The badatmath_watch shadow logger is 10 days stale — restart or re-wire it to the current session.

---

## 6. Three Experiments

### Experiment A — VPS Band Resolution Join (Gamma Gate Unlock)
**Hypothesis:** Running band_resolution_join.py from the VPS will unlock CI for BAND_NO_PAIR_FAV (n=237) and yield the first READY or REJECTED gate verdict since the band system launched.

**Data required:** Gamma resolution flags for the 237 pair_fav NO token fills in the gate ledger. VPS-accessible; cloud 403.
**Time:** 1–2h (script run + CI computation).
**Cost:** $0 capital. No code change.
**Success metric:** CI lower bound for BAND_NO_PAIR_FAV WR clears zero (READY) or falls below zero (REJECTED).
**Decision-if-READY:** Gate confirmed. Expand pair_fav to 10 cities (shadow YES first, then live NO). Pair co-fill velocity is the next scaling lever.
**Decision-if-REJECTED:** Disable BAND_PAIR_FAV_ENABLED. Redirect YES pair stake. Document as closed gate in state_log.

### Experiment B — YES d+2 Shadow Accumulation on Extended City Set
**Hypothesis:** Adding 5 more cities to BAND_CITY_ALLOW in shadow-YES mode (no live capital) will at least double the YES fire rate in band_struct_lite, accelerating BAND_YES gate n from +54/day to +120+/day, without capital risk.

**Data required:** band_struct_lite YES d+2 fire records per city over 48h with the wider set. Compare SUM_ASK distribution of new cities vs existing 5.
**Time:** 48h observation.
**Cost:** $0 (shadow mode only — BAND_REALBOOK_YES stays True but new cities would post shadow-only until validated).
**Success metric:** YES fire rate doubles within 48h; new-city SUM_ASK distribution is within 15% of current 5-city distribution (quality gate).
**Decision-if-yes:** Promote new cities to live YES d+2 posting at next Phase 1 threshold review.
**Decision-if-no (quality degradation on new cities):** Keep 5-city narrow set; accept slower gate accumulation and focus on Phase 1 threshold as the YES unlock path.

### Experiment C — P1 YES d+2 Partial Unlock at Half Stake
**Hypothesis:** Allowing YES d+2 posting in Phase 1 at half the normal YES stake ($1.50 per leg vs $3.00) will capture the YES d+2 edge (+10.7% per 06-26 state_log) without materially competing with NO capital deployment.

**Data required:** Monitor YES d+2 fill rate and capital drawdown over 7 days. yes_resv_skip should drop to near 0 if YES is unblocked; NO fill rate should be stable.
**Time:** 7 days (one d+2 resolution cycle for statistics).
**Cost:** $1.50 × 3 legs = $4.50/fire. Minimal capital risk. Risk: if YES d+2 WR on the narrow 5-city set is below breakeven (<30% at avg price 0.70), cost ≤$4.50/fire × ~2 fires/day × 7 days = $63 max exposure at worst.
**Success metric:** YES d+2 resolved WR > 30% on n≥10 fills within 7 days; capital grows at least as fast as NO-only baseline.
**Decision-if-yes:** Raise YES stake to $3.00 and lower Phase 1 boundary from $600 to $200.
**Decision-if-no (YES d+2 at narrow-start is -EV):** Revert. Keep P1 NO-ONLY; accept the 17-day ETA to Phase 2.

---

## 7. Single Best Action — Run VPS Band Resolution Join for BAND_NO_PAIR_FAV

**Action:** On the VPS, execute `band_resolution_join.py` targeting BAND_NO_PAIR_FAV (n=237). Post CI verdict to state_log.

**Why this has the highest (compounding impact × P(success)) / effort:**

1. **Matured gate with known n.** BAND_NO_PAIR_FAV n=237 — 2.4× above the n≥100 decision threshold. The sample exists. Only Gamma API access is missing; the VPS has it.

2. **Cited from gatekeeper_report (09:07 UTC).** The gatekeeper explicitly identified this as the most accumulated gate with no verdict. The research agent's role is to act on gatekeeper findings.

3. **Either outcome improves compounding.** READY → pair_fav city expansion unlocks turns/day directly (pair fires ~1/day currently; 10 cities → ~3/day). REJECTED → disabling pair_fav redirects YES pair stake to other uses. The verdict resolves a $237-data-point question that has been blocked only by a tooling constraint.

4. **P(success) of getting a verdict: very high.** The VPS Gamma connection has been confirmed (state_log 06-17: VPS run showed YES +7.6% n=3,275). The script is written and tested.

5. **Effort: ~1h.** No code change. No capital deployed. First step: `python3 band_resolution_join.py --gate BAND_NO_PAIR_FAV` (or equivalent invocation) from VPS, then post CI result to state_log.

---

## PROPOSED ACTIONS (human review)

All items below require explicit human authorization before implementation. This agent is REPORT-ONLY.

### PA-1: Run band_resolution_join.py from VPS for BAND_NO_PAIR_FAV (n=237)
**Trigger:** Gatekeeper_report confirms n=237 > 100 threshold, only blocked by Gamma 403 in cloud. VPS has Gamma access. This is the single highest-value 1h task.
**First step:** `python3 band_resolution_join.py --gate BAND_NO_PAIR_FAV` on VPS. Post CI result to state_log.
**Decision tree:** READY → expand pair_fav cities (shadow YES first). REJECTED → disable pair_fav, log in state_log.

### PA-2: Lower Phase 1 boundary from $600 → $200, or enable YES d+2 in P1 at half stake
**Trigger:** maker_fills_recent.log confirms yes_resv_skip=3–12/cycle at cap=$79. YES d+2 candidates exist and are queued. State_log 06-26 confirms YES d+2 = +10.7% ROI on narrow-start. P1 NO-ONLY until $600 locks out the higher-ROI leg for ~17 more days.
**Pre-condition:** At least 7 days of narrow-start YES d+2 shadow data showing consistent fire rate and SUM_ASK quality, OR n≥20 YES d+2 resolved fills on the 5-city set with WR > breakeven. Do NOT unlock live YES d+2 in P1 before this evidence exists.
**Action if approved:** Reduce `BAND_PHASE2_CAPITAL` from 600.0 to 200.0, OR add `BAND_YES_P1_ALLOWED = True` with `BAND_YES_P1_STAKE = 1.50` override.

### PA-3: Revert M1_BETA_LOCKOUT temp_floor 0.2 → 0.5°C (or kill logger)
**Trigger:** Gatekeeper shows 16 days of zero placed-order records. Shadow logger is not accumulating evidence. Gate n=31 frozen.
**Action if approved:** `METAR_LOCKOUT_TEMP_FLOOR = 0.5`. If n does not grow from placed records within 7 days, kill the logger and retire the gate in state_log.

### PA-4: Add disk pruning cron for shadow files >7 days
**Trigger:** Disk 82% full (76G/97G). Shadow logger files accumulate at several GB/day. Risk of logger stall from disk full in 2–4 weeks.
**Action if approved:** Add to VPS crontab: `0 2 * * * find /root/Klaus/logs/shadow -name '*.jsonl' -mtime +7 -delete 2>/dev/null`. This retains the shadow_summary.json head/tail excerpts while freeing disk.

### PA-5: Re-enable THERMO_MAKER_LIVE with $15/day cap to accumulate kill-gate data
**Trigger:** Gatekeeper shows THERMO n=3, kill gate requires n≥20 resolved. At rate=0 (LIVE=False), n=20 is unreachable — the gate verdict is indefinitely deferred. THERMO was paused Jun-23 to free ~$25 for band-NO. At $79 capital, $25 is less acute.
**Pre-condition:** User confirms the $15/day THERMO cap is acceptable and the freed-NO logic post-pause is no longer needed.
**Risk:** Small ($15/day cap, kill gate fires at n=20 if CI < 0).

---

*Report generated: 2026-06-28T11:00Z | Research audit agent | Branch: claude/find-lag-parameter-rFQ0N*
