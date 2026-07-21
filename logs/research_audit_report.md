# Klaus Research Audit — 2026-07-21

**Generated:** 2026-07-21T11:05Z  
**Specialist reports read:** exec_audit 07:07Z · calib_monitor 08:12Z · gatekeeper 09:07Z · pnl_ledger 23:37Z Jul-20  
**Snapshot:** 2026-07-21T10:22:24Z (age: 0.7h — FRESH ✓)  
**System:** `active` ✓  
**Data access:** GitHub MCP API (git fetch blocked by network proxy)  

**ABORT CRITERIA:** Snapshot age < 6h ✓; `active` present in system_status.txt ✓. Proceeding.

---

## 1. PRIMARY BOTTLENECK

**Zero deployed equity — all live paths disarmed. Compounding rate is literally 0×.**

This is not a turns/ROI/fill/calibration problem. There is no active strategy deploying capital. The compounding equation is:

> *Return = ROI/turn × turns/day × equity deployed*

Equity deployed = $0. The product is $0 regardless of the other terms.

**Evidence from specialist reports:**
- *exec_audit (07:07Z)*: "band wound down 2026-07-06... UPDOWN sniper is the sole active strategy — no sniper trades logged on Jul 20; capital flat at $21.495."
- *pnl_ledger (23:37Z Jul-20)*: "Day PnL: $0.00... Binding constraint: all live paths disarmed."
- *gatekeeper (09:07Z)*: "Structural posture: UPDOWN_STOP active (cut 2026-07-19T11:26Z) | Band dark day 15 (BAND_LIVE=False since Jul-06)."
- *bankroll.json*: capital $21.495; total_pnl −$75.40 over 3,093 trades. No change since Jul-19.

**Path to re-engagement — critical CI math:**  
The only operative gate is G8 UPDOWN_CROSSING (n=38, ETA n=100 ~Jul-23). The CI arithmetic makes PASS geometrically unavailable from the current position:
- Current: 37W/1L, CI-lo = 86.5%, BE = 97.0% (gap: 10.5pp)
- At n=100 with 0 more losses (best case): Clopper-Pearson CI-lo ≈ 93.3% — still 3.7pp below BE
- At n=100 with 1 more loss: CI-lo ≈ 91.6%

**KILL is the most likely outcome at n=100.** BTC sub-class (n=95 at Jul-20 22:05Z) is the only per-asset path that could clear independently, but its CI-lo (0.911) also does not clear BE (0.966). Tonight's EVOLVE --refetch will push BTC past n=100.

**Runner-up bottlenecks (all secondary and unactionable while equity=0):** ROI/turn (undefined), turns/day (0), dispersion gauge (inverted day 19 — but band disarmed for separate capital-floor reason).

---

## 2. EXISTING-SYSTEM OPTIMIZATION

All four reports describe a system in complete shadow-only mode. The optimization surface is narrow.

| Item | Source | Expected Delta | Confidence | Effort |
|---|---|---|---|---|
| **Disk management (urgent)** | exec_audit, system_status | 89% used (11G free). Shadow JSONL accumulation ~3–4G/day. Service hits critical disk in ~3–4 days (~Jul-24) if unmanaged. Prior EVOLVE (Jul-19) cleared 95%→83% via journal vacuum 3.0G + gzip shadow/hot Jul-10..12 (9.2G→616M). Inaction = service interruption. | HIGH | LOW |
| **Isotonic candidate promotion** | calib_monitor S4 | Deployed isotonic 45d old. Candidate refit Jul-20 (n_live=3,247, 8d OOS). Material change: p_raw=1.0→p_cal=1.0 (vs deployed 0.6316 under-shrinkage at tail). OOS brier_cal=0.0601 vs brier_raw=0.0589 — candidate adds slight negative value in aggregate but this is masked by the plateau (85.6% of rows in 0–10% bin). Tail-subset validation needed before promoting. Zero P&L impact while band is dark. | MEDIUM | LOW (human execute after review) |
| **STWA overdue positions** | pnl_ledger | Jul-17 (d+3 overdue) and Jul-18 (d+2 overdue) unresolved as of 23:34Z Jul-20. Jul-19 position (token=5717613767097074, 146.33sh@0.02, cost $2.93) resolves TODAY Jul-21 — confirmed by maker_fills_recent.log. If YES: +~$143.40 inflow; if NO: −$2.93. Monitor wallet. | HIGH (time-sensitive today) | NONE (auto-resolution) |
| **bankroll.json write-cadence fix** | pnl_ledger | File not written on no-fill days (stale since Jul-19 midnight). Requires dual CLOB-actual manual checks as workaround. Systemic fix needed on VPS write-loop trigger. | MEDIUM | MEDIUM (VPS code change) |

**Key note on maker_fills_recent.log**: All 6 untracked fills (Jul-18/19) are legacy STWA resting orders and near-resolution sniper buys, not band-maker fills. The MAKER@0.02 fill (Jul-19 02:14, 146.33sh) is the Jul-19 STWA d+1 position resolving today. The 0.88–0.98 taker fills are consistent with automated near-resolution buys on Jul-17/18 positions. No tracker entries exist for any of these — all UNTRACKED.

---

## 3. GATE PIPELINE REVIEW

**Source: gatekeeper_report 09:07Z**

| Gate | Status | n | ETA | Next decision |
|---|---|---|---|---|
| G8 UPDOWN_CROSSING post-cut | COLLECTING | 38 (21:59Z Jul-20) | ~Jul-23 | KILL (likely) or continued COLLECTING |
| G1 BAND_YES | AMBIGUOUS (frozen) | 934 | N/A (band dark) | Frozen; all sim-CI blocked by G3 |
| G2a BAND_NO d1 | AMBIGUOUS (frozen) | 115 | N/A | Frozen |
| G2b PAIR_FAV_YES | COLLECTING (frozen) | 9 | Indeterminate | Frozen |
| G2c PAIR_FAV_NO | COLLECTING (frozen) | 9 | Indeterminate | Frozen |
| G3 WINNER'S CURSE | WATCH_ITEM (confirmed) | 75 | N/A | Permanent blocker on all G1/G7 sim-CI arguments |
| G5 THERMO | REJECTED | 125 | N/A | Dead |
| G6 M1_LOCKOUT | REJECTED | 31 | N/A | Dead (human decision) |

**G8 detailed analysis:**  
Rate = ~26.4 events/day (multi-asset shadow enabled Jul-19 19:05Z: ETH/SOL/XRP/DOGE now accruing). WR 97.4% (37W/1L) at n=38. Point WR recovered above BE (was 0.960 at n=25, 11:30Z Jul-20; recovered to 0.9737 by 21:59Z Jul-20).

Composite CI math at n=100:
- 0 additional losses (perfect): CI-lo ≈ 93.3% — BELOW BE 97.0%
- 1 additional loss: CI-lo ≈ 91.6% — BELOW BE
- Implication: **no path from current 37W/1L clears CI-lo > BE at n=100**. Gatekeeper confirms: "the likely outcome at n=100 is continued COLLECTING or KILL, not PASS."

**BTC sub-class (per-asset gate — the last viable path):**  
n=95 at 21:59Z Jul-20; ~5 events from n=100 at 2–3 BTC events/day. Tonight's EVOLVE --refetch will grade overnight fires and likely push BTC to n≥100. Gate values: WR=0.968, CI-lo=0.911, BE=0.966. Narrow miss (4.5pp gap on CI-lo). p≥0.995 sub-slice: n=56, CI-lo=0.879, BE=0.965 — wider gap.

**What would accelerate accumulation without degrading expectancy:** Breadth expansion already occurred (Jul-19 multi-asset). No further levers while sniper is CUT. Only remaining lever is prompt EVOLVE --refetch execution tonight to capture Jul-20→Jul-21 overnight fires.

**Acceleration lever available this session: NONE.** The gate moves at the pace of shadow resolution (~26/day). No parameter changes or code changes can speed it up.

---

## 4. ASSUMPTION ATTACK

Three load-bearing assumptions of the band system as of today:

### A. Dispersion premium persists
*The band harvests implied-σ > realized-σ across the temperature bucket distribution.*

**Status: THREATENED (day 19 consecutive, approaching decision-grade n)**

From calib_monitor (08:12Z):
- disp_ratio7 ≈ 0.88 (estimate); daily median Jul-20 = **0.779** (worst non-crash day in 6d window)
- n = 59 city-days (trend grade: 40–99; **41 city-days from decision grade 100**)
- Every daily median Jul-15..Jul-20 is below 1.10 threshold:
  - Jul-15: 1.038 / Jul-16: 1.196 / Jul-17: 0.927 / Jul-18: 0.485 / Jul-19: 0.925 / Jul-20: 0.779
- EU cities: 100% mode-hits (0 eligible, implied_std ≈ 0) — market prices European temperatures near-perfectly
- Asia median: 0.958 (slight inversion); US/Other median: 0.768 (stronger inversion)
- S3 alert firing continuously since 19 days ago

**Plausible explanation**: Midsummer regime. EU peak summer temperatures are predictable (low variance); Polymarket market implied-σ has not compressed commensurately, OR the STWA Kalman σ estimates are themselves summer-compressed (BAND_SIGMA_FLOOR=0.90 may be binding and preventing σ from reflecting true low-variance environment). The 07-17 (0.927) and 07-19 (0.925) readings suggest partial recovery attempts that fail to sustain — this is a suppressed-edge environment, not a clean off/on switch.

**Danger level**: HIGH. n=59 reaching 100 in ~4 days at 6.6 city-days/day. At n=100 with median still below 1.0, this crosses from trend to decision grade. Band is off for a separate reason (capital floor) so no immediate P&L exposure, but the edge thesis is under serious challenge.

### B. Fills are not adversely selected (no winner's curse)
*Markets where the band gets filled are representative of the full fire population.*

**Status: CONFIRMED NEGATIVE (G3, n=75, permanent watch item)**

From gatekeeper_report:
- Filled WR: 17.3%; sim WR (upper bound): unknown but gap CI entirely negative [-75.0%, -34.2%]
- n=75, well above the 40-fill interpretation threshold
- Interpretation: the markets where band quotes got taken were materially, decisively worse than the full shadow population
- This blocks all G1 (BAND_YES) and G7 (SUM_POSTED) sim-CI arguments permanently
- G1 sim ROI +4.0% and G7 sim ROI +11.5% are UPPER BOUNDS that likely overstate live edge

**Danger level**: HIGH. This is a structural architectural problem, not a configuration issue. The band systematically gets filled on the markets where it is wrong, and passes on the markets where it is right. No configuration change fixes adverse selection; the quoting logic or the market filter would need redesign. Cannot be re-evaluated until band re-arms and fresh fill data accrues.

### C. Recycle velocity scales
*RECYCLE099 convergence sells generate incremental ROI above cost-of-capital.*

**Status: UNTESTABLE — band dark day 15**

- exit099_live.jsonl absent for Jul-20: $0 recycle events
- Zero live fires since Jul-6; all RECYCLE099 records are pre-wind-down
- The mechanism is theoretically sound (sell at convergence to 0.99 before last-cent territory), but it has zero validation in the current config era
- Shadow logs contain would-fire records, not fills; no winner's curse or ROI data exists for RECYCLE099 specifically

**Danger level**: MEDIUM. If dispersion recovers and band re-arms, this would generate data quickly (~26 city-days/day). Until then, recycle is a config parameter with no live backing.

---

## 5. MARKET INTELLIGENCE

**Day-of-month 21 mod 3 = 0 → Competitor posture (badatmath_watch + leaderboard)**

**Data limitation — stale competitor tape:** badatmath_watch JSONL in shadow_summary shows `hot/2026-07-13/badatmath_watch.jsonl` (mtime: 2026-07-13T23:56Z, n=4,035 rows). This is 8 days stale. No fresh fill-join data is available via MCP read without a live shadow runner. I cannot compute fresh deltas vs prior knowledge.

**From state_log / band_config standing knowledge (no deltas this session):**
- badatmath reference: YES band mode ± 2+ offsets; NO stake median $5.16/fill
- We mirror at: BAND_YES_MAX_OFF=2, BAND_NO_STAKE=5.0, BAND_PX_CEIL=0.45 (d+1/d+2), BAND_PX_CEIL_D0=0.25
- His detect_lag_s (fill-join lag) was ~129s in the Jul-13 tape (single observed entry) — within our 30s–2min edge window estimate
- Our capital ($21.50) precludes competitive positioning regardless of his activity; we cannot post at his scale

**No fresh deltas available.** Next research audit should explicitly load `hot/2026-07-21/badatmath_watch.jsonl` (or the current week directory) if this section is to be populated. The Jul-13 data is outside the delta-reporting window.

---

## 6. THREE EXPERIMENTS

### E1: BTC sub-class per-asset gate resolution (tonight's EVOLVE)
*Hypothesis*: Overnight Jul-20→Jul-21 shadow fires have pushed BTC post-cut graded n past 100, enabling a per-asset decision independently of the composite gate.  
*Data needed*: `shadow_grade.py --refetch` + `updown_asset_grade.py`, BTC sub-slice CI-lo vs BE=0.966.  
*Time*: <30min in tonight's EVOLVE run.  
*Cost*: $0.  
*Success metric*: BTC n≥100 AND CI-lo > 0.966.  
*Decision-if-yes*: Take to owner for BTC-only min-size restart vote ($1 stake, explicit daily cap, sniper STOP file must be removed by owner, not agent). This is the ONLY path to any live trading before ~Jul-23.  
*Decision-if-no*: BTC sub-class is heading toward per-asset KILL. Close BTC sub-class and prepare for composite KILL at ~Jul-23. The UPDOWN CROSSING class closes permanently.  
*Value of information*: **HIGH**. This is the only experiment that could unlock revenue in the next 24h. All other experiments have zero near-term P&L impact.

### E2: Midsummer dispersion seasonality backtest
*Hypothesis*: The 19-day dispersion inversion (disp_ratio < 1.0) is a recurring seasonal pattern (EU peak summer = predictable temps) that recovers by ~Aug-1, not a structural market-learning event.  
*Data needed*: Kalman s50 archive or trades.jsonl implied_std / realized_dev fields by month for Jul/Aug 2025 (pre-band era). If records exist, compute median dispersion ratio by calendar week.  
*Time*: 2–4h (scripted query on historical s50 or trades data on VPS).  
*Cost*: $0.  
*Success metric*: At least one prior July window shows ≥5 consecutive days of disp_ratio < 1.0 followed by recovery to >1.10 within 14 days.  
*Decision-if-yes*: Seasonal noise confirmed. Set a dispersion watch date ~Aug-1; no architecture changes. The band premise holds; the current inversion is weather-regime, not market-learning.  
*Decision-if-no*: Structural break. The market has learned to price temperatures as well as or better than the Kalman/STWA model. Full band-premise review required — consider retiring the maker-first system permanently in favor of the UPDOWN sniper class (pending its own gate decision).  
*Value of information*: **HIGH for capital allocation**. If the edge is structural rather than seasonal, the correct posture after the G8 KILL (likely) is not to wait for band recovery — it's to stop all band development and focus resources elsewhere.

### E3: Isotonic tail-subset validation before candidate promotion
*Hypothesis*: The Jul-20 candidate isotonic (p_raw=1.0→p_cal=1.0) improves calibration in the p_raw≥0.85 tail without degrading mid-range Brier, making it safe to promote the 45-day-stale deployed curve.  
*Data needed*: Re-run candidate OOS brier split by p_raw range: tail (p_raw≥0.85) vs mid-range (p_raw 0.30–0.75). Available in the OOS window already computed.  
*Time*: <1h (add p_raw filter to existing OOS brier computation; calib agent or VPS script).  
*Cost*: $0.  
*Success metric*: Candidate tail brier ≤ deployed tail brier (strict), AND mid-range brier degradation < 0.005.  
*Decision-if-yes*: Promote candidate (human executes deploy). Improves accuracy for any future strategy operating in the tail (THERMO revival, BAND_TAILNO if re-examined). Zero risk if tail metric passes.  
*Decision-if-no*: Extend candidate observation to 30 days before re-evaluation. The 8-day OOS (n_live=3,247) may be insufficient for tail-mapping confidence given the material p_raw=1.0 change (OOS brier_cal=0.0601 > brier_raw=0.0589 already shows slight negative value from isotonic in aggregate).  
*Value of information*: MEDIUM. Zero impact while band is dark; high impact if band re-arms, since THERMO-style NO tail quoting relies on calibration quality at p_raw≥0.85.

---

## 7. SINGLE BEST ACTION

**Ensure tonight's EVOLVE explicitly runs `shadow_grade.py --refetch` + `updown_asset_grade.py` and reports BTC sub-class CI-lo vs BE at n≥100.**

**Source citation**: gatekeeper_report (09:07Z): "BTC n=95, ~5 events from n=100 at ~2-3 BTC/day; tonight's EVOLVE run will include next --refetch grade. Watch for BTC sub-slice to cross n=100 independently — even then, per-asset CI gate has its own BE and must clear independently before any per-asset promotion vote."

**Why this and not something else:**

The composite G8 gate will almost certainly not pass at n=100 — the CI geometry makes it impossible from 37W/1L at n=38. When the composite KILLS (~Jul-23), Klaus is left with:
- Capital: $21.50 (24.1% of ruin floor)
- All band paths off (capital floor + adverse selection + dispersion inversion)
- UPDOWN CROSSING class closed
- No live revenue stream

BTC sub-class at n≥100 tonight is the **only scenario** that produces a re-enable before total strategic shutdown. If BTC CI-lo clears 96.6% at n≥100, the owner can authorize a BTC-only min-size restart (explicit vote required — owner must remove UPDOWN_STOP, agent cannot). Even at $1/fire with 26 fires/day, that's ~$26/day deployed — enough to compound from $21.50 with a 97%+ WR strategy.

**Concrete first step**: In tonight's EVOLVE prompt, add explicit instruction: "Run `updown_asset_grade.py --refetch` for BTC. Report: n_post_cut, WR, CI-lo (95%), BE. If CI-lo > BE, include a formal per-asset restart vote request for owner."

If BTC CI-lo does not clear BE at n=100, the correct posture is to prepare the KILL report for the composite gate and begin the Experiment E2 seasonality backtest to determine whether the band system has a future.

---

## PROPOSED ACTIONS (human review)

1. **[URGENT — today] STWA Jul-19 position (146sh@$0.02) resolves Jul-21 — monitor wallet.** Confirmed via maker_fills_recent.log (fill 02:14Z Jul-19, MAKER side). If YES: +~$143.40 net inflow, capital would recover to ~$164.90 — potentially above the $89.16 ruin floor and possibly above the $75 weekly floor. This single resolution could structurally change the band re-arm calculus. If NO: −$2.93, capital to ~$18.57.

2. **[URGENT — ~Jul-24] Disk management.** Journal vacuum + gzip shadow/hot files older than 5 days before disk hits critical. At 89% with 3–4G/day accrual, service interruption is ~3–4 days away. Prior EVOLVE approach worked (95%→83% via specific gzip ops). Do not delete lag_ws_events.jsonl (owner-only per escalation).

3. **[Tonight EVOLVE] BTC sub-class per-asset gate check at n≥100.** As detailed in Section 7 and Experiment E1. This is the operative decision of the next 24h.

4. **[Tonight EVOLVE] Composite G8 KILL preparation.** Prepare owner communication that composite PASS at n=100 is geometrically unavailable from current 37W/1L position. Frame the Jul-23 decision correctly: the question is whether to extend collection to n=200 or KILL the class.

5. **[Low urgency — band dark] Isotonic candidate promotion.** Run tail-subset brier validation (Experiment E3), promote if it passes. Zero P&L impact now; needed before any future band re-arm.

6. **[Medium urgency — research] Midsummer dispersion seasonality backtest** (Experiment E2). Run before the S3 alert reaches n=100 (~4 days). The answer determines whether the band system has a future after this trough.

7. **[Structural — VPS] bankroll.json write-cadence fix.** Investigate and fix the write-loop trigger to avoid MODEL DEFICIENCY flags on no-fill days. Low urgency but prevents data quality degradation over extended zero-fill periods.

---

*Report generated by Research Audit agent at 2026-07-21T11:05Z. Data: exec_audit_report.md (07:07Z), calib_monitor_report.md (08:12Z), gatekeeper_report.md (09:07Z), pnl_ledger_report.md (23:37Z Jul-20), data-mirror snapshot (10:22:24Z), maker_fills_recent.log, bankroll.json, band_config.txt, system_status.txt. Git fetch blocked by network proxy — all reads via GitHub MCP API.*
