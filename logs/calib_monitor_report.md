# Klaus Calibration & Dispersion Monitor — 2026-08-12T08:20Z

**STALL — systemd: failed/unknown (day 19). Abort condition met. No calibration or dispersion metrics computable.**

## Abort Reason

`system_status.txt` reads `failed unknown` for `## klaus systemd:` — not `active`. Abort condition met per monitor rules. Snapshot freshness: 2026-08-12T08:16:06Z — current (4 min, within 6h window) ✓.

## System Context

- **Stall duration**: Day 19 (last active: 2026-07-24 10:09:19 UTC)
- **Snapshot freshness**: 2026-08-12T08:16:06Z — current ✓
- **Data-mirror status**: Working (force-pushed every 15 min; 8228 trade rows mirrored, unchanged from prior)
- **Bankroll**: $88.750373, 0 open positions
- **All live paths**: DISABLED — BAND_LIVE=False, BAND_NO_ENABLED=False, STWA_REGULAR_YES=False, STWA_REGULAR_NO=False
- **Shadow loggers (today, through 08:16 UTC)**: badatmath_watch: 127 rows (through 07:14), maker_flow: 44,656 rows, minmax_coherence: 509 rows, count_lock: 99 rows

## Last Known Metrics (from 2026-07-26, carried forward — day 19)

| Metric | Last known value | Alert threshold | Status |
|---|---|---|---|
| brier7 | 0.055 | >0.15 | OK (last computed 2026-07-26) |
| ece7 | ~0.0 | >0.05 | OK (last computed 2026-07-26) |
| rho7 | not recorded | <+0.15 | unknown |
| disp_ratio7 | **0.781** | <1.10 | **ALERT — STILL FIRING (17+ consecutive runs)** |

## 1–5. All Lanes

All five pipeline sections are blocked. No new settled labels since 2026-07-26. No pricer_eval files exist. Cannot compute 7d Brier, ECE, rank-rho, proxy-lane divergence, or dispersion ratio. System has been down 19 consecutive days. Shadow loggers (badatmath_watch, maker_flow, minmax_coherence, count_lock) continue collecting market-structure data but do not carry p_cal values or resolution labels — they cannot substitute for pricer_eval.

**Isotonic staleness**: Cannot re-check candidate vs deployed without a live repo checkout. Carrying forward last noted data from 2026-08-06: candidate showed +0.055 shift at grid[0.95] and +0.168 at grid[1.0] vs deployed isotonic. 19 days without recalibration.

**State diff**: No metric transitions. All live metrics null. disp_ratio alert still firing (sustained, no new data). vs yesterday (2026-08-11): no change in system status, no new settled rows, no metric movement.

## ALERTS (pre-registered, fired)

1. **DISPERSION RATIO BELOW 1.10**: Last known disp_ratio7 = 0.781. Alert threshold 1.10. The dispersion premium the band strategy relies on is unverified for 17+ consecutive monitor runs. If the ratio has stayed at 0.781 or compressed further, the edge premise (implied sigma > realized sigma, ratio ≥ 1.10) is decaying. This cannot be confirmed or denied while the system is down — but silence is not absolution. 19 days without a new resolved data point is a material evidence gap.

---
_Recommendations (report-only — no code edits made)_
- SSH VPS → `sudo systemctl start klausbot` (or equivalent restart command)
- After restart, allow 1–2 settled market-days before any live path resumption, to recompute disp_ratio with fresh labels
- 19 days of shadow data (minmax_coherence, badatmath_watch, count_lock, maker_flow) have accumulated and will provide calibration signal immediately upon restart
