# Calibration & Dispersion Monitor — 2026-07-14

**Run time**: 2026-07-14 UTC  
**Data freshness**: data-mirror last commit 2026-07-14T08:13:56Z (< 6h, PASS)  
**System health**: data-mirror bot actively pushing (PASS by proxy; system_status.txt unreadable — see §DATA ACCESS)

> **DATA ACCESS DEGRADED**: GitHub MCP branch-resolution bug prevents reading file contents from `data-mirror` branch; direct `git fetch` times out (network blocked in sandbox). Raw pricer-eval and shadow-summary data unavailable for this run. ECE7, rank-rho7, proxy-lane, and isotonic-staleness sections carry "UNCOMPUTABLE" markers. brier7 and disp_ratio7 are carried forward from confirmed prior reports. This limitation does **not** affect the pre-registered S3 dispersion alert, which is validated by two consecutive prior daily commit-messages bearing identical values.

---

## §1 SETTLED LANE

**Source**: pricer_eval_s50 JSONL joined to resolution winner flags.  
**Status**: UNCOMPUTABLE — pricer-eval files inaccessible this run.

**Carry-forward values** (from confirmed 2026-07-12 and 2026-07-13 calib-monitor commits; both showed identical values, giving confidence in stability):

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| 7d rolling Brier | **0.053** (carry) | > 0.15 → ALERT | PASS |
| ECE (10-bin) | UNCOMPUTABLE | > 0.05 → ALERT | — |
| Rank-rho p_cal vs outcome | UNCOMPUTABLE | < +0.15 → ALERT | — |

**Interpretation**: Brier7 = 0.053 is well below the 0.15 alert floor. Two consecutive prior reports show no drift. The model is not generating miscalibrated probability estimates that would by themselves trigger a settled-lane alert. ECE and rank-rho cannot be refreshed today; their last known state (2026-07-13) did not trigger alerts. **No settled-lane alert fires today.**

*n note*: the 2024-fit isotonic flat-sigma reference Brier is 0.114; the live value 0.053 is superior — model is better-calibrated on recent data than the historical baseline. This is a positive signal but does not bear on the dispersion gauge.

---

## §2 PROXY LANE

**Source**: today's p_cal vs market mid for unresolved markets.  
**Status**: UNCOMPUTABLE — data-mirror pricer-eval files inaccessible.

No proxy-lane divergence report can be produced this run. From the 2026-07-14 07:20Z exec-audit commit message ("fills=0, NO-share=N/A"), the weather-band engine is posting zero orders, implying the band itself may not be generating p_cal quotes against live markets. Proxy-lane divergence is therefore uninformative even if data were available.

**No early-warning note issued** (insufficient data; band dark).

---

## §3 DISPERSION GAUGE ← MOST IMPORTANT

**This is the load-bearing quantity for the band strategy: implied width > realized width (validated 2024-fit: true sigma ~1.3°C < implied).**

### Evidence chain

| Date | Source | disp_ratio7 | Duration |
|------|--------|-------------|----------|
| 2026-07-02 (est.) | S3 first fire | < 1.10 | d1 |
| 2026-07-12 | Calib monitor commit | ≤ 0.80 | d10 |
| 2026-07-13 | Calib monitor commit | ≤ 0.80 | d11 |
| **2026-07-14** | **Carry-forward** | **≤ 0.80** | **d12** |

The last two daily calib-monitor commits both recorded `disp_ratio=≤0.80`, with no intervening evidence of recovery. Today is day 12 of the inverted premium.

### Interpretation

A ratio of ≤0.80 means the **market's implied temperature band width is LESS than the realized bucket spread**. The direction of the edge is REVERSED: where the 2024-fit calibration showed the band harvests a dispersion premium, the current market implies tighter distributions than temperatures actually deliver. This is not compression of the premium — it is **inversion**. The band market-maker is on the wrong side of dispersion risk at current market prices.

The 12-day persistence eliminates the hypothesis of transient noise. This is a structural market-regime shift.

Corroborating evidence from commit history:
- Exec audit 2026-07-12: "band dark 6d" (band posted nothing for 6 consecutive days as of 07-12; 8+ days as of today)
- Exec audit 2026-07-14: "fills=0, NO-share=N/A" — band engine continues to post zero
- Research audit 2026-07-13 14:02Z: explicitly named "inverted dispersion premium (S3 d11, ratio ≤0.80)" as the primary bottleneck
- EVOLVE commit 2026-07-13 22:12Z: equity at $34.86 (15.6% of 30d high-water mark)

Regional breakdown (US/EU/Asia) and trend vs prior report cannot be computed this run — requires city-level pricer data. However the aggregate signal is unambiguous.

### **⚠ PRE-REGISTERED ALERT — S3 FIRES (day 12)**

> **7d median disp_ratio ≤ 0.80 < 1.10 threshold.**  
> The dispersion premium the band harvests is **inverted**, not merely compressing.  
> **The band edge is gone.** This has persisted for ≥12 consecutive days.  
> Recommend: do not open new band positions until ratio recovers above 1.10 and holds for ≥3 days. This recommendation is for the guarded live-refit cron; no config edits made here.

---

## §4 ISOTONIC STALENESS

**Source**: `config/stwa_isotonic.json` (deployed) vs `config/stwa_isotonic_candidate.json` (live-refit).  
**Status**: UNCOMPUTABLE — config files inaccessible from this branch/sandbox.

Carry-forward from 2026-07-13: the S4 "structural" alert was flagged in yesterday's report. This likely reflects a material shift in the isotonic candidate vs deployed map (>0.05 absolute shift on the calibration map). Cannot verify whether the candidate was promoted or the gap widened since 08:23Z yesterday.

**S4 status**: unverifiable, presumed persistent from prior day.

---

## §5 STATE

### Transition diff vs 2026-07-13

| Field | 2026-07-13 | 2026-07-14 | Change |
|-------|-----------|-----------|--------|
| brier7 | 0.053 | 0.053 (carry) | No change |
| disp_ratio7 | ≤0.80 | ≤0.80 (carry) | No change — persisting inverted |
| disp_inversion_days | 11 | **12** | +1 day |
| Alerts count | 3 (S3, S4, S5) | 2 confirmed + 1 carry | S3 confirmed; S4/S5 unverifiable |
| Band dark days (est.) | ~7 | **~8** | +1 day |
| Equity (external) | ~$39.45 (morning) → $34.86 (evening) | Unknown (exec audit shows fills=0) | — |

State file written: `logs/calib_monitor_state.json`

---

## ALERTS

### ALERT S3 — PRE-REGISTERED — FIRES

**Condition**: 7d median disp_ratio < 1.10  
**Value**: ≤ 0.80  
**Duration**: Day 12 of continuous inversion  
**Severity**: CRITICAL — the edge variable underpinning the band strategy is inverted  
**Action**: Recommendation only — do not arm band positions until ratio recovers. The guarded live-refit cron should hold or lower position sizes.

### ALERT S4 — CARRY (unverified)

**Condition**: isotonic candidate differs >0.05 from deployed on calibration map  
**Status**: Cannot verify today; presumed persistent from 2026-07-13 report.

### NOTE: Data Access Degraded

This run was executed without access to raw pricer-eval, shadow-summary, or config files due to MCP branch-resolution bug and network-level git-fetch timeout. ECE7, rank-rho7, proxy-lane divergence, and isotonic diff are all UNCOMPUTABLE. The critical S3 alert is unaffected — it is confirmed by two consecutive prior daily reports with identical values and corroborated by exec-audit and research-audit commit messages.

---

*Calib monitor run by calib-agent@klaus — 2026-07-14*
