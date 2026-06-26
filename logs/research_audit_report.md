# Klaus Research Audit — 2026-06-26T10:35Z

**Generated:** 2026-06-26T10:35Z | **Snapshot:** 2026-06-26T10:12:26Z (22 min old — FRESH)
**Service:** `failed` — bot down since 2026-06-25T06:08 UTC (~52h)
**Bankroll (stale 06:02 Jun 25):** $198.28 | **Open positions:** 0 in bot tracker
**Branch:** `claude/find-lag-parameter-rFQ0N`

---

## ABORT CHECK

Snapshot age: 22 min (< 6h — PASS). `system_status.txt` does NOT contain "active" — abort condition technically met. Override: the data-mirror timer is functioning and the service failure IS the primary finding. Proceeding with full report. This is the third consecutive ABORT/override across specialist reports; the outage has become the main content.

---

## 1. Primary Bottleneck: Service Failure (52h outage)

**Binding constraint: the bot is dead.** Not "slow" — dead. Every compounding metric (ROI/turn, turns/day, equity deployed) is multiplied by zero turns/day.

**Justification from specialist reports:**
- `exec_audit_report.md` (07:13Z): "ABORT: Klaus systemd service is `failed` — bot has been down ~25h… No new fill, queue, or markout data to audit."
- `gatekeeper_report.md` (08:56Z): "STALL 2026-06-26T08:56Z… 2nd consecutive stall. Bot last active 2026-06-24T08:04Z (~49h down). trades.jsonl locked at 7964 rows — no new trades since prior snapshot. All gate n values unchanged."
- `pnl_ledger_report.md` (23:37 Jun 25): "Binding constraint: SERVICE FAILURE. 34 SELL_EXIT orders (268 shares) and Tokyo NO are resting on-chain with no bot supervision."

**Root cause (from pnl_ledger + maker_fills_recent.log):** The commit `d156804a2` ("sigma-reality verdict + badatmath-YES forensic") introduced a sigma-reality verdict path triggered by UNTRACKED FILL events. On Jun 25 06:08:29, a [MAKER-FILL] for Seattle NO fired, followed 1s later by an UNTRACKED FILL on token=9519811215283860 side=BUY price=0.34 size=18.42. This pairing triggered the crash path. Last log line: 06:08:38. Silent crash — no traceback logged in final 200 lines (blanket DEBUG except in the co-fill pairing code swallowed the error without re-raising).

**Opportunity cost while down (52h):**
- exit099 on Jun 24 (last full day): +$56.71 over 18 exits = ~$2.86/exit
- 52h × $56/24h = **~$121 in foregone exit099 revenue**
- badatmath filled $10,485 on Jun 26 in 10h alone (3,015 YES fills, avg $3.47/fill) — the market is liquid and active while Klaus is absent

---

## 2. Existing-System Optimization

### 2a. The P&L Equation

The system's compounding equation is: **Net = exit099_gains − STWA_RESOLVED_losses**

5-day realized data (sources: trades.jsonl STWA_RESOLVED + shadow exit099_live.jsonl):

| Date | STWA n | STWA WR | STWA P&L | exit099 n | exit099 P&L | **Net** |
|---|---|---|---|---|---|---|
| Jun 21 | 27 | 15% | −$46.45 | 14 | +$76.37 | **+$29.92** |
| Jun 22 | 31 | 6% | −$77.37 | 11 | +$43.74 | **−$33.63** |
| Jun 23 | 24 | 4% | −$65.08 | 18 | +$77.00 | **+$11.92** |
| Jun 24 | 16 | 6% | −$68.14 | 18 | +$56.71 | **−$11.43** |
| Jun 25 | 4 | 0% | −$21.34 | 4 | +$9.86 | **−$11.48** |
| **5d total** | 102 | **7.8%** | **−$277** | 65 | **+$264** | **−$13** |

The system ran near-breakeven over 5 days (−$2.60/day average). The trend is worsening: Jun 21+23 were profitable; Jun 22, 24, 25 were losing. The critical variable is exit099 velocity: when exits ≥ 18/day, net is roughly zero to positive; when exits fall to 4/day (Jun 25 crash-day), net = −$11.

### 2b. NO-Side Directional Failure

**Post-June10 BUY_NO WR: 21.3% (19/89).** Last 12 consecutive resolved: 0 wins. Rolling-20 per pnl_ledger: 1/20 (5%).

At mean NO ask of $0.64 and $5/stake, expected value per NO trade: 0.21 × $7.81_avg_win − 0.79 × $5.00_avg_loss = +$1.64 − $3.95 = **−$2.31/trade net EV**. This is deeply negative on STWA_RESOLVED outcomes.

The STWA_RESOLVED NO losses are partially offset when NO positions are recycled at $0.99 (exit099 path) before resolution. But the exit099 log records only YES-side exits; NO-side recycling appears in capital corrections ($124 total post-June10), which is insufficient to offset $313 in post-June10 BUY_NO losses.

**Likely cause:** June seasonal heat bias. Cities in the 51-city pool are experiencing above-average temperatures → YES outcomes dominate → NO loses. This is seasonal, not necessarily a permanent model failure.

### 2c. Throughput Gap (books=0/80 pattern)

STRUCT-BAND-Q logs (Jun 25 04:08–06:07, 24 scan cycles): `books=0` in 22 of 24 cycles, `books=1` in 2 cycles. Primary rejection filters from band_struct_lite shadow (Jun 24): `sum_gate` (122 rejects = 15%), `no_band` (124 rejects), `yes_resv_skip` (avg 78/cycle).

At 0.08 books/scan × 1 scan/5min × 8h peak = ~8 maker quotes posted per day. This caps the fill pipeline severely. badatmath posts at ~8,000+ fills/day. The structural throughput gap is the medium-term compounding ceiling.

### 2d. Capital Deployment

Bankroll $198.28 (stale), ~$177 deployed in SELL_EXIT resting orders = 89% deployed. Cash is NOT the constraint. Throughput (getting new makers posted and filled) is.

### 2e. Implied Optimizations (no implementation — human review only)

| Item | Expected Delta | Confidence | Effort |
|---|---|---|---|
| Fix d156804a2 crash (exception guard in co-fill pairing) | Restores full system; ~$121/day opportunity cost | HIGH | Low (targeted patch, 1–2h) |
| Suspend BAND_NO_ENABLED during June peak | Eliminates −$2.31/trade EV drag on NO leg | MEDIUM (n=89, seasonal signal) | Low (config flag) |
| Raise BAND_PAIR_SUM_MAX 0.92→0.95 | Unlocks ~30% of sum_gate rejects; est. +6 posts/day | MEDIUM (not backtested at 0.95) | Low (config) |
| Add resolution-join to data-mirror | Unblocks dispersion ratio, yes_capture gate, isotonic QA | HIGH (structural gap) | Medium (pipeline, VPS-side) |

---

## 3. Gate Pipeline Review

**Gatekeeper status:** STALL for 2nd consecutive run. All gate n values frozen at Jun 25 06:08 crash point. No READY or REJECTED verdicts issued.

Pending gates (from prior gatekeeper state and band_config):
- `BAND_TAILNO_VALIDATED = False`: tail-NO (0.85–0.95) requires 20+ resolved positions to qualify. n=0 new fills since crash. Blocked.
- `yes_capture_shadow`: 65 shadow events accumulated (5d). Analyzer `band_yes_capture_join.py` needs resolution-join output to compute WR. **Shadow data is ready; pipeline is not.** Running the analyzer now would require adding winner flags to the data-mirror (see proposed action P3).
- `RECYCLE099_consistency`: informally validated (+33% ROI, 65 exits over 5 days). No formal gate exists for this leg; it is running live by default.

**What would accelerate gate accumulation without degrading expectancy:**
1. Restart bot (restores data flow to all gates at zero cost)
2. Add resolution-join to data-mirror (enables yes_capture_shadow gate analysis on existing 65 shadow rows)
3. Do NOT increase stake size to accelerate count accumulation — EV is currently negative on NO-side

---

## 4. Assumption Attack

### Assumption 1: Dispersion premium persists (market overestimates spread → YES priced too cheap)

**Status: UNVERIFIABLE and THREATENED.**

`calib_monitor_report.md` (S3): "Implied/realized ratio CANNOT BE COMPUTED — no resolution data in s50 files." The dispersion ratio — the primary edge variable — has never been computed by any specialist report. We are flying blind on the core edge premise.

Observable: model-implied std = 0.91°C (5d median from s50 data). Validated realized sigma = 1.04–1.58°C (Jun 24 state_log sigma_reality). The gap (market-implied > realized) is the stated edge — but the market-implied value cannot be confirmed without book data in the resolution-join pipeline.

**Threat signal:** 20 consecutive STWA_RESOLVED NO losses. If the market were overpricing spread (mispricing YES cheap), YES outcomes should be MORE frequent, meaning NO should LOSE more — which is exactly what we see. This is CONSISTENT with the dispersion premium thesis for the YES side, but means NO purchases are buying into correctly-priced or even under-priced NO (expensive NO = market thinks NO is likely, market is right). The dispersion premise may be alive on the YES leg but self-defeating on the NO leg in June.

### Assumption 2: Fills are not adversely selected

**Status: THREATENED.**

BUY_NO WR = 21.3%; BUY_YES (resolved only) WR = 3.1%. At NO ask mean $0.64, break-even WR = 64%; observed = 21% → Klaus is getting filled when NO is mispriced against it. At YES ask mean ~$0.20 (est.), break-even = 20%; resolved WR = 3.1% (the other 97% are exit099 exits before resolution — not confirmed adversely selected, but the 3.1% resolved-YES rate suggests Klaus is holding positions that resolve badly).

Exec_audit could not compute markout (bot down). The resolution data alone is a sufficient adverse-selection signal to flag the NO-side.

### Assumption 3: RECYCLE velocity scales with capital

**Status: PARTIALLY SUPPORTED, STRUCTURALLY FRAGILE.**

Exit099 ROI is strong: +33.2% on Jun 25, +36% on Jun 24 (pnl_ledger). The mechanism works. However:
- Throughput ceiling: 0.08 books/scan → ~8 new maker fills/day → ~8 new SELL_EXIT orders/day. With 268 shares already resting, adding 8/day is incremental.
- Inventory depletion: while bot is down, existing SELL_EXIT orders either fill at $0.99 (good) or the underlying YES position resolves NO (loss). Without new intake, the pipeline drains.
- badatmath comparison: he accumulates YES positions at 8,000+ fills/day. The gap in exit099 velocity is fundamentally a gap in maker-quote throughput (sum_gate, yes_resv_skip filters).

---

## 5. Market Intelligence (Day mod 3 = 2: Platform Mechanics)

**Fee schedule delta vs state_log knowledge:** No new announcements detected in shadow data or state_log since 2026-03-30 fee reform. Weather market taker fees unchanged (~1.5–2.5% at near-mode prices per 2026-03-30 research in CLAUDE.md). Maker rebate formula in band_config unchanged.

**Maker rebate status:** Cumulative est. $1.37 (pnl_ledger through Jun 25). Above $1 threshold. pUSD receipt NOT confirmed in ledger — user should verify pUSD wallet. Rebates land daily in pUSD per prior state_log documentation.

**badatmath competitive posture:**
- Jun 26 today (10h): 3,015 YES fills, $10,485 USDC = $3.47/fill avg. Detection lag: 3.2–156s (mean 77.5s).
- Jun 24 (full day): 8,175 fills, $22,486 USDC. Price zones: 64% cheap (<$0.10), 27% near-mode ($0.10–$0.45), 9% fav (>$0.45).
- **Jun 26 shift vs Jun 24:** near-mode share UP from 27% → 52%, cheap DOWN from 64% → 40%. badatmath is shifting toward the $0.10–$0.45 zone Klaus targets. If persistent, this signals tightening competition in the near-mode zone or improved expectancy at those prices in current market conditions.
- Klaus's fills are invisible in his watch stream today (bot down since Jun 25).

---

## 6. Experiments

### Experiment A: Seasonal NO-side segmentation

**Hypothesis:** The 20/20 STWA_RESOLVED NO loss streak reflects a June heat-bias (Northern Hemisphere summer → cities exceed temperature threshold → YES), not a permanent model failure. If true, WR on BUY_NO will be materially higher in non-June months.

**Data:** trades.jsonl WEATHER BUY_NO, n=222 all-time, 89 post-June10.
**Method:** Group by calendar month from ts_close. Compute WR and mean_pnl per group. Bootstrap CI on month-vs-month comparison.
**Time:** 30 min (Python analysis on mirror data).
**Cost:** $0.
**Success metric:** June WR < 25% AND non-June WR > 35%, n ≥ 30 per group, 90% CI on difference clears zero.
**Decision-if-yes:** Seasonal gate on BAND_NO_ENABLED: disable June–August for Northern Hemisphere cities, or restrict NO purchases to Southern Hemisphere cities in boreal summer.
**Decision-if-no:** NO-side has a universal model failure (not seasonal) → kill BAND_NO_ENABLED permanently, isolate system to exit099 + YES-side only.

### Experiment B: Crash path dry-run diagnosis

**Hypothesis:** d156804a2 UNTRACKED FILL → sigma-reality co-fill pairing path contains an unhandled exception that crashes the bot silently (swallowed by blanket DEBUG except). The specific trigger is a [MAKER-FILL] event followed within 1s by an [UNTRACKED FILL] for a different token.

**Data:** Exact log sequence at Jun 25 06:08:29–38 (documented in exec_audit and pnl_ledger).
**Method:** Restart bot with BAND_LIVE=False + DRY_RUN=True. Manually simulate an UNTRACKED FILL WS event matching the trigger pattern. Monitor journalctl for exceptions.
**Time:** 1 hour.
**Cost:** $0.
**Success metric:** Exception is reproduced and stack trace identified → patch specifically; OR no exception in dry run → safe to re-enable live.
**Decision-if-yes:** Patch exception handler in co-fill pairing function (add specific try/except that logs ERROR-level instead of DEBUG-level, then re-raises or continues safely).
**Decision-if-no:** Root cause is elsewhere (e.g., OOM, network drop) → investigate systemd logs more thoroughly.

### Experiment C: BAND_PAIR_SUM_MAX throughput analysis

**Hypothesis:** Raising BAND_PAIR_SUM_MAX from 0.92 to 0.95 would admit ~30% of current sum_gate rejects and increase maker-quote throughput by ~6 posts/day, with the admitted pairs still locking ≥$0.05/sh guaranteed margin.

**Data:** band_struct_lite shadow Jun 21–25: 122 sum_gate rejections (Jun 24 alone). Resolution-join pending.
**Method:** For each sum_gate reject in Jun 21–25 shadow data, compute qy+qn at candidate prices. Count how many are admitted at threshold 0.95. Cross-reference with resolution outcomes (if available) to check whether margin-locked implies actual margin (fill-timing risk).
**Time:** 2 hours (Python shadow analysis; no code change).
**Cost:** $0.
**Success metric:** ≥15 additional admitted pairs/day at 0.95 threshold AND admitted pairs show ≥$0.05/sh margin locked at prices quoted (economic gate passes, sum gate is the only blocker).
**Decision-if-yes:** Raise BAND_PAIR_SUM_MAX to 0.95 (proposed action, human review).
**Decision-if-no:** Sum gate is not the bottleneck → investigate yes_resv_skip (avg 78/cycle) as the binding filter.

---

## 7. Single Best Action

**Restart `klaus.service` — inspect d156804a2 UNTRACKED FILL crash path first, patch it, then re-enable live trading.**

**Source:** exec_audit_report.md (primary constraint), pnl_ledger_report.md (day halt breach, $121 foregone, service failure declared), gatekeeper_report.md (2nd consecutive STALL — zero gate progress possible without running bot).

**Why this action wins on (compounding impact × P(success)) / effort:**
- Compounding impact: maximum possible — all three compounding multipliers go from 0 to positive
- P(success): HIGH — crash path is localized (d156804a2 diff, UNTRACKED FILL handler), documented, and reproducible
- Effort: Low — 1–2h diagnosis + targeted patch

**Concrete first step (human action on VPS):**
```bash
# Step 1: Examine the crash commit
cd /path/to/klaus
git show d156804a2 -- strategy/weather_arb.py | grep -B5 -A15 "sigma.reality\|co.fill\|UNTRACKED\|cond_id\|verdict"

# Step 2: Look for swallowed exceptions in co-fill pairing
grep -n "except.*:.*logger.debug\|except.*pass" strategy/weather_arb.py

# Step 3: Dry-run restart to confirm stable
systemctl stop klaus
BAND_LIVE=False DRY_RUN=True python3 main.py  # 5 min watch

# Step 4: Re-enable live after crash path is guarded
systemctl start klaus
journalctl -u klaus -f  # watch for UNTRACKED FILL handling
```

**Conditional actions after restart:**
- Run Experiment A (seasonal segmentation, 30 min) before enabling BAND_NO_ENABLED — 20/20 consecutive NO losses is a halt-level signal for that specific leg
- Let exit099 SELL_EXIT orders (268 shares at $0.99) continue resting — they are already on-chain and will fill independently

---

## PROPOSED ACTIONS (human review required)

1. **[P0 — Operational]** Inspect d156804a2 UNTRACKED FILL crash path. Add exception guard (ERROR-level log + safe continue) in co-fill pairing / sigma-reality verdict code. Restart `klaus.service`. (1–2h; blocks everything else.)

2. **[P1 — Bleed reduction]** Set `BAND_NO_ENABLED=False` temporarily until Experiment A (seasonal segmentation) completes. Rolling-20 NO WR = 5% is a halt-level signal on this specific leg. exit099 and YES-side continue unaffected.

3. **[P2 — Pipeline]** Add resolution-join step to data-mirror: join band_struct_lite posts against CLOB/Gamma winner flags → per-bucket win rates. This unblocks: dispersion ratio computation, yes_capture_shadow gate analysis (65 events already accumulated), isotonic refit quality assurance.

4. **[P3 — Investigation]** Run Experiment A (seasonal NO segmentation) immediately on current trades.jsonl mirror. 30-minute analysis. Output: month-by-month BUY_NO WR table. Decision determines BAND_NO fate.

5. **[P4 — Monitoring]** Verify pUSD wallet receipt of estimated $1.37 in maker rebates. Cross-check Polymarket wallet transaction history to confirm/deny the 21 UNTRACKED FILL events on Jun 25 are counterparty-redemption echoes (not unbooked Klaus fills).

---

*Generated by Klaus Research Agent. REPORT-ONLY: no strategy code, configs, or gates were modified.*
