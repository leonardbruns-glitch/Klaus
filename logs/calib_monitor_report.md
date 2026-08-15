# Klaus Calibration & Dispersion Monitor — 2026-08-15T08:05Z

**STALL — systemd: failed/unknown (day 22). Abort condition met. No calibration or dispersion metrics computable.**

## Abort Reason

`system_status.txt` reads `failed unknown` for `## klaus systemd:` — not `active`. Abort condition met per monitor rules. Snapshot freshness: 2026-08-15T08:05:16Z — current (within 6h window) ✓.

---

## System Context

| Field | Value |
|---|---|
| Stall duration | Day 22 (last active: 2026-07-24 10:09:19 UTC) |
| Snapshot freshness | 2026-08-15T08:05:16Z ✓ |
| Bankroll | $88.750373 (unchanged; 0 open positions) |
| Trade rows | 8228 (unchanged since stall) |
| All live paths | DISABLED (BAND_LIVE=False, BAND_NO=False, STWA_YES/NO=False) |

**Shadow loggers active today (through 08:05 UTC)**:
- `flb_screener.jsonl`: 1,262,560 rows (through 08:03 UTC) — market screener running continuously
- `maker_flow.jsonl` (hot/2026-08-15): 36,855 rows (through 08:03 UTC) — CLOB order-book polling
- `badatmath_watch.jsonl` (hot/2026-08-15): 11 rows (through 08:04 UTC, partial day; all ladder type, 0 fill_joins yet)
- `minmax_coherence.jsonl` (hot/2026-08-15): 522 rows (through 08:00 UTC)
- `count_lock.jsonl` (hot/2026-08-15): 582 rows (through 08:00 UTC)
- `updown_sniper/snap_20260815.jsonl`: 67,627 rows (through 08:05 UTC) — updown sniper running

Weather markets are actively resolving (badatmath_watch fill_join records in prior days confirm real outcomes). The data gap is entirely on the STWA pricer/calibration side, which requires the VPS klausbot service to be running.

---

## 1. SETTLED LANE

**Blocked.** No `stwa_pricer_eval_s50.jsonl` files exist in any `data/shadow/<date>/` subdirectory for any date since 2026-07-24. Shadow subdirectories (hot/2026-08-05 through hot/2026-08-15) each contain only non-pricer loggers (badatmath_watch, maker_flow, minmax_coherence, count_lock). The STWA pricer has produced zero output since the service failed 2026-07-24. Cannot compute 7d Brier, ECE, or rank-rho.

**Last known (2026-07-26, carried forward — day 22)**:
- brier7: 0.055 (alert threshold >0.15) — OK, but 20 days stale
- ece7: ~0.0 (alert threshold >0.05) — OK, but 20 days stale
- rho7: not recorded

---

## 2. PROXY LANE

**Blocked.** No p_cal values available — pricer not running. `minmax_coherence.jsonl` records market ladder structure but does not carry p_cal. Cannot compute proxy-lane divergence or spike vs 7d baseline.

---

## 3. DISPERSION GAUGE ← PRIMARY EDGE VARIABLE

**Blocked — alert sustained (20th consecutive run).** No resolved market labels with p_cal since 2026-07-26. Cannot compute 7d implied/realized width ratio.

**Last known disp_ratio7: 0.781** (from 2026-07-26). Alert threshold: 1.10. This is the **20th consecutive monitor run** with the dispersion alert firing.

The dispersion premium — the central load-bearing assumption of the band strategy (implied sigma > realized sigma, ratio ≥ 1.10) — has not been verified for 22 days. The last confirmed value of 0.781 is materially below threshold. Whether it has recovered, stayed flat, or compressed further is unknown. Silence is not absolution. The edge is unverified and last-known-below-threshold.

**Regional breakdown**: Cannot update. Last known breakdown carried from 2026-07-26 report.

**Trend**: Unknown. Stall has fully occluded any trend signal since 2026-07-26.

---

## 4. ISOTONIC STALENESS

No change from prior reports. Both files remain readable from repo:

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

Candidate fit: n_live=3,392 over 8 live calendar days (refit 2026-07-23). Deployed: n_live=0 (hist-only, refit 2026-06-06). **70 days without isotonic promotion** (was 69 yesterday).

**Interpretation**: Candidate shifts p_cal UP materially at the high end of the raw-score distribution. High-confidence STWA signals calibrated ~0.44 (candidate) vs ~0.38 (deployed). Promotion blocked while service is down. Recommend promoting immediately upon VPS restart before any live trading resumes.

---

## 5. STATE

No metric transitions vs prior report (2026-08-14). All live metrics null. disp_ratio alert still firing (sustained, 20th consecutive run). Isotonic gap: 70 days. No change in system status. No change in bankroll. No change in open positions.

**Diff vs prior state**:
- `stall_day`: 21 → 22
- `disp_ratio_alert_run`: 19 → 20
- `isotonic_days_since_promotion`: 69 → 70
- all else: no change

---

## ALERTS (pre-registered, fired)

### ALERT 1: DISPERSION RATIO BELOW 1.10

Last known disp_ratio7 = **0.781** vs threshold 1.10. Alert has fired on every monitor run since at least 2026-07-10. This is the **20th consecutive firing**.

The dispersion edge — the one quantity this monitor exists to guard — has not been verified for 22 days. The edge premise (implied sigma > realized sigma by ≥10%) was last measured below threshold. The strategy's live paths are all disabled, so there is no active bleed. But resumption planning must treat disp_ratio as **unknown and last-known-below-threshold** until fresh data is computed after VPS restart.

---

## Recommendations (report-only — no code edits made)

1. **SSH VPS → restart service**: 22 days of downtime with shadow loggers accumulating data. Fresh pricer-eval rows will start accruing immediately upon restart.
2. **Allow 1–2 settled market-days before live-path resumption**: Need resolved labels to compute fresh disp_ratio before trusting the edge premise.
3. **Promote isotonic candidate on restart**: Candidate (refit 2026-07-23, n_live=3,392) is materially better-fitted than deployed (refit 2026-06-06, n_live=0). Material upward shift at grid[0.95, 1.0]. Promote on restart before live trading.
4. **disp_ratio is the gate**: Do not re-enable BAND_LIVE or any live path until fresh disp_ratio7 ≥ 1.10 is confirmed over ≥7 resolved days.
