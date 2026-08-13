# Klaus Calibration & Dispersion Monitor — 2026-08-13T08:30Z

**STALL — systemd: failed/unknown (day 20). Abort condition met. No calibration or dispersion metrics computable.**

## Abort Reason

`system_status.txt` reads `failed unknown` for `## klaus systemd:` — not `active`. Abort condition met per monitor rules. Snapshot freshness: 2026-08-13T08:07:16Z — current (within 6h window) ✓.

---

## System Context

| Field | Value |
|---|---|
| Stall duration | Day 20 (last active: 2026-07-24 10:09:19 UTC) |
| Snapshot freshness | 2026-08-13T08:07:16Z ✓ |
| Bankroll | $88.750373 (unchanged; 0 open positions) |
| Trade rows | 8228 (unchanged since stall) |
| All live paths | DISABLED (BAND_LIVE=False, BAND_NO=False, STWA_YES/NO=False) |

**Shadow loggers active today (through 08:07 UTC)**:
- `badatmath_watch.jsonl`: 405 rows (through ~08:04 UTC) — fill-join and ladder records
- `maker_flow.jsonl`: 39,117 rows (through ~08:06 UTC) — CLOB order-book polling
- `minmax_coherence.jsonl`: 493 rows (through ~08:00 UTC)
- `count_lock.jsonl`: 98 rows (through ~08:05 UTC)
- `flb_screener.jsonl`: 1,232,003 rows (through 08:04 UTC) — market screener running

Market data is flowing. Weather markets are resolving (badatmath_watch fill_join records confirm this). The data gap is entirely on the STWA pricer/calibration side, which requires the VPS service to be running.

---

## 1. SETTLED LANE

**Blocked.** No `stwa_pricer_eval_s50.jsonl` files exist in any `data/shadow/<date>/` subdirectory for 2026-08-08 through 2026-08-12. Shadow subdirectories each contain only `badatmath_watch.jsonl`. The STWA pricer has not written any output since the service failed on 2026-07-24. Cannot compute 7d Brier, ECE, or rank-rho.

**Last known (2026-07-26, carried forward — day 20)**:
- brier7: 0.055 (alert threshold >0.15) — OK, but 20 days stale
- ece7: ~0.0 (alert threshold >0.05) — OK, but 20 days stale
- rho7: not recorded

---

## 2. PROXY LANE

**Blocked.** No p_cal values available — pricer not running. `minmax_coherence.jsonl` records market ladder structure but does not carry p_cal. Cannot compute proxy-lane divergence or spike vs 7d baseline.

---

## 3. DISPERSION GAUGE ← PRIMARY EDGE VARIABLE

**Blocked — alert sustained.** No resolved market labels with p_cal since 2026-07-26. Cannot compute 7d implied/realized width ratio.

**Last known disp_ratio7: 0.781** (from 2026-07-26). Alert threshold: 1.10. This is the 18th consecutive monitor run with the alert firing.

The dispersion premium — the central load-bearing assumption of the band strategy (implied sigma > realized sigma, ratio ≥ 1.10) — has not been verified for 20 days. The last confirmed value of 0.781 is materially below threshold. Whether it has recovered, stayed flat, or compressed further is unknown. Silence is not absolution.

**Regional breakdown**: Cannot update. Last known breakdown carried from 2026-07-26 report.

**Trend**: Unknown. Stall has fully occluded any trend signal since 2026-07-26.

---

## 4. ISOTONIC STALENESS

Direct comparison performed (both files readable from repo):

| grid | deployed (2026-06-06) | candidate (2026-07-23) | delta | material? |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0042 | +0.0042 | no |
| 0.05 | 0.0695 | 0.0708 | +0.0013 | no |
| 0.10 | 0.1340 | 0.1255 | -0.0085 | no |
| 0.15 | 0.1828 | 0.1831 | +0.0003 | no |
| 0.20 | 0.2663 | 0.2697 | +0.0034 | no |
| 0.25 | 0.3557 | 0.3373 | -0.0184 | no |
| 0.30–0.85 | 0.3801 (flat) | 0.3748 (flat) | -0.0053 | no |
| 0.90 | 0.3801 | 0.3919 | +0.0118 | no |
| **0.95** | **0.3822** | **0.4374** | **+0.0552** | **YES** |
| **1.00** | **0.6316** | **0.8000** | **+0.1684** | **YES** |

Candidate fit: n_live=3,392 over 8 live calendar days (refit 2026-07-23); OOS Brier raw=0.0637, calibrated=0.0638 (calibration nearly inert on this sample).

Deployed: n_live=0 (hist-only, refit 2026-06-06). 68 days without isotonic promotion.

**Interpretation**: The candidate shifts p_cal UP materially at the high end of the raw-score distribution (grid 0.95, 1.0). High-confidence STWA signals would be calibrated ~0.44 (candidate) instead of ~0.38 (deployed). This expands the effective confidence range for near-certain calls. Direction of shift: p_cal increases for high raw scores. This would increase band fire-rate on high-confidence events if applied and if the service were running. Candidate shows no degradation in Brier vs deployed baseline (reference 0.114; candidate OOS 0.064 on live slice only).

Promotion of the candidate is blocked anyway while the service is down. Recommend promoting immediately upon VPS restart, before any live trading resumes.

---

## 5. STATE

No metric transitions vs prior report (2026-08-12). All live metrics null. disp_ratio alert still firing (sustained, 18th consecutive run). Isotonic gap: 68 days. No change in system status.

---

## ALERTS (pre-registered, fired)

### ALERT 1: DISPERSION RATIO BELOW 1.10

Last known disp_ratio7 = **0.781** vs threshold 1.10. Alert has fired on every monitor run since at least 2026-07-10. This is the 18th consecutive firing.

The dispersion edge — the one quantity this monitor exists to guard — has not been verified for 20 days. The edge premise (implied sigma > realized sigma by ≥10%) was last measured below threshold. The strategy's live paths are all disabled, so there is no active bleed. But resumption planning must treat disp_ratio as **unknown and last-known-below-threshold** until fresh data is computed after VPS restart.

---

## Recommendations (report-only — no code edits made)

1. **SSH VPS → restart service**: 20 days of downtime with shadow loggers accumulating data. The market data gap cannot be recovered, but fresh pricer-eval rows will start accruing immediately upon restart.
2. **Allow 1–2 settled market-days before live-path resumption**: Need resolved labels to compute fresh disp_ratio before trusting the edge premise.
3. **Promote isotonic candidate on restart**: Candidate (refit 2026-07-23, n_live=3,392) is materially better-fitted than deployed (refit 2026-06-06, n_live=0). Material upward shift at grid[0.95, 1.0]. Promote on restart before live trading.
4. **disp_ratio is the gate**: Do not re-enable BAND_LIVE or any live path until fresh disp_ratio7 ≥ 1.10 is confirmed over ≥7 resolved days.
