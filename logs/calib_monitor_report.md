# Klaus Calibration & Dispersion Monitor — 2026-08-11T08:09Z

**STALL — systemd: failed/unknown (day 18). Abort condition met. No calibration or dispersion metrics computable.**

## Abort Reason

`system_status.txt` reads `failed unknown` for `## klaus systemd:` — not `active`. Abort condition met per monitor rules. Snapshot freshness: 2026-08-11T08:08:42Z — current (within 6h) ✓.

## System Context

- **Stall duration**: Day 18 (last active: 2026-07-24 10:09:19 UTC)
- **Snapshot freshness**: 2026-08-11T08:08:42Z — current ✓
- **Data-mirror status**: Working (force-pushed every 15 min; 8228 trade rows mirrored, unchanged from prior)
- **Bankroll**: $88.750373, 0 open positions
- **All live paths**: DISABLED — BAND_LIVE=False, BAND_NO_ENABLED=False, STWA_REGULAR_YES=False, STWA_REGULAR_NO=False
- **Shadow loggers**: Active through 08:08 UTC (badatmath_watch: 1165 rows today, maker_flow: 192,908 rows today, minmax_coherence: 491 rows today, count_lock: 98 rows today, flb_screener: through 08:07 UTC)

The shadow data collection apparatus is alive. Only the main trading service (klausbot systemd unit) is dead.

## Last Known Metrics (from 2026-07-26, carried forward — day 18)

| Metric | Last known value | Alert threshold | Status |
|---|---|---|---|
| brier7 | 0.055 | >0.15 | OK (last computed 2026-07-26) |
| ece7 | ~0.0 | >0.05 | OK (last computed 2026-07-26) |
| rho7 | not recorded | <+0.15 | unknown |
| disp_ratio7 | **0.781** | <1.10 | **ALERT — STILL FIRING (16+ consecutive runs)** |

## 1. Settled Lane

No new settled labels since last active run (2026-07-26). Cannot compute 7d Brier, ECE, or rank-rho. All prior metric values null.

## 2. Proxy Lane

Cannot compute p_cal vs mid divergence without a live pricer log. Shadow loggers (maker_flow, minmax_coherence) are running but do not carry p_cal values. No proxy-lane divergence computable.

## 3. Dispersion Gauge

Cannot compute implied/realized width ratio without new resolved market-days. Last known disp_ratio7 = 0.781 (measured 2026-07-26). That value is 29% below the 1.10 alert floor.

**Plain statement**: The dispersion premium the band strategy harvests appears to have compressed materially below its validated level. The edge premise (implied sigma > realized sigma, ratio ≥ 1.10) is unverified and has been so for 18 consecutive days. Whether this is temporary regime or permanent structural shift cannot be determined without new settled pricer_eval rows, which require the system to be running.

## 4. Isotonic Staleness

Cannot re-check candidate vs deployed without repo checkout (git fetch timed out this run). Carrying forward last noted data from 2026-08-06: candidate showed +0.055 shift at grid[0.95] and +0.168 at grid[1.0] vs deployed isotonic. Deployed isotonic not updated. 18 days without recalibration.

## 5. State Diff

No metric transitions. All live metrics null. disp_ratio alert still firing (sustained, no new data). vs yesterday (2026-08-10): no change in system status, no new settled rows, no metric movement. Shadow loggers continuing to collect.

**Notable from shadow_summary**: `hot/2026-08-05/badatmath_watch.jsonl` and `hot/2026-08-05/count_lock.jsonl` both show 0 rows (gap day in badatmath coverage). All other days are populated. This gap pre-dates the current monitoring period and is noted for record only.

## ALERTS (pre-registered, fired)

1. **DISPERSION RATIO BELOW 1.10**: Last known disp_ratio7 = 0.781. Alert threshold 1.10. Status: sustained, unresolvable while system is down. 16+ consecutive monitor runs with this alert active.

---
_Recommendations (report-only — no code edits made)_
- SSH VPS → `sudo systemctl start klausbot` (or equivalent restart command)
- After restart, allow 1–2 settled days to recompute disp_ratio with fresh labels before resuming any live paths
- The data-mirror and all shadow loggers are functioning; only the trading service needs attention
- 18 days of shadow data (minmax_coherence, badatmath_watch) have accumulated and will provide calibration signal immediately upon restart
