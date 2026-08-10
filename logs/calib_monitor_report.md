# Klaus Calibration & Dispersion Monitor — 2026-08-10T08:17:16Z

**STALL — systemd: failed/unknown (day 17). Abort condition met. No calibration or dispersion metrics computable.**

## Abort Reason

`system_status.txt` present in data-mirror (data pipeline now working, unlike yesterday's run) but reads `failed unknown` for `## klaus systemd:` — not `active`. Abort condition met per monitor rules.

## System Context

- **Stall duration**: Day 17 (last active: 2026-07-24 10:09:19 UTC)
- **Snapshot freshness**: 2026-08-10T08:17:16Z — current (within 6h) ✓
- **Data-mirror status**: Working (force-pushed every 15 min; 8228 trade rows mirrored)
- **Bankroll**: $88.750373, 0 open positions
- **All live paths**: DISABLED — BAND_LIVE=False, BAND_NO_ENABLED=False, STWA_REGULAR_YES=False, STWA_REGULAR_NO=False
- **Shadow loggers**: Running — maker_flow (46k rows today), minmax_coherence (439 rows), badatmath_watch (1229 rows) through 08:17 UTC

The shadow collection apparatus is alive. Only the main trading service (klausbot systemd unit) is dead.

## Last Known Metrics (from 2026-07-26, carried forward)

| Metric | Last known value | Alert threshold | Status |
|---|---|---|---|
| brier7 | 0.055 | >0.15 | OK (last computed) |
| ece7 | ~0 | >0.05 | OK (last computed) |
| rho7 | not recorded | <+0.15 | unknown |
| disp_ratio7 | **0.781** | <1.10 | **ALERT — STILL FIRING** |

## Dispersion Alert (pre-registered, sustained)

The 7-day median implied/realized dispersion ratio has been at 0.781 since at least 2026-07-26 — well below the 1.10 alert floor. This alert has fired for 15+ consecutive calib-monitor runs. No new settled data is computable while the system is down.

Plain statement: the dispersion premium the band strategy harvests appears to have compressed materially below its validated level. Whether this is temporary regime or permanent shift cannot be determined without new pricer_eval settlements. The edge premise is unverified and has been so for 17 days.

## Isotonic Staleness (Section 4 — carried)

Last noted on 2026-08-06: candidate showed +0.055 shift at grid[0.95] and +0.168 at grid[1.0] vs deployed. Deployed isotonic not updated. Cannot re-check candidate vs deployed without repo checkout (git fetch timed out this run).

## What Changed vs Yesterday

- **Data-mirror is now populated** — yesterday (2026-08-09) the run aborted because data-mirror had no files. Today system_status.txt, SNAPSHOT.md, band_config.txt, and shadow_summary.json are all present.
- **System still failed** — the stall condition itself is unchanged at day 17.

## State Diff

No metric transitions. All nulls carried. disp_ratio alert still firing (no new data to resolve it).

## ALERTS (pre-registered, fired)

1. **DISPERSION RATIO BELOW 1.10**: Last known disp_ratio7 = 0.781. Alert threshold 1.10. Status: sustained, unresolvable while system is down.

---
_Recommendations (report-only — no code edits made)_
- SSH VPS → `sudo systemctl start klausbot` (or equivalent restart command)
- After restart, allow 1–2 settled days to recompute disp_ratio with fresh labels before resuming any live paths
- The data-mirror pipeline is working; only the trading service needs attention
