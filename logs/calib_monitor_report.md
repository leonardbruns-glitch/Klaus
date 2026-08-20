# Calib Monitor Report — 2026-08-20

**STALL — ABORT:** `data-mirror` snapshot is 4 days stale (last: 2026-08-16T11:26:01Z; limit: 6h). Klaus systemd status: `failed/unknown` since 2026-07-24 (day 27+). Owner shutdown confirmed in EVOLVE commit 2026-07-26 (`daily+liveness timers disabled → loop WEEKLY-ONLY`). No new pricer, band, or trade data since prior stall series. Cannot evaluate any pipeline section.

## Last Known Values (from commit trail, 2026-07-26 — **25+ days stale**)

| Metric | Value | Threshold | Status |
|---|---|---|---|
| brier7 | 0.055 | <0.15 | OK (stale) |
| ece7 | ~0 | <0.05 | OK (stale) |
| rho7 | n/a | >+0.15 | unknown |
| disp_ratio7 | **0.781** | ≥1.10 | **ALERT (stale)** |

## ALERTS (pre-registered, carried from 2026-07-26)

- **DISP_RATIO_COMPRESSION:** Last confirmed 7d median dispersion ratio = 0.781, below the 1.10 floor. The band's implied > realized width premium has been compressing. Edge decay finding stands until fresh data shows otherwise. This alarm predates the shutdown.

## Sections Not Evaluated

1. **SETTLED LANE** — no resolved pricer rows available (no shadow data in mirror)
2. **PROXY LANE** — no today's p_cal rows available
3. **DISPERSION GAUGE** — cannot recompute; last known ratio 0.781 (alert threshold ≥1.10)
4. **ISOTONIC STALENESS** — cannot diff; no fresh candidate file in mirror
5. **STATE** — written with last-known values carried forward, marked stale

## Action Required

SSH to VPS and investigate service restart. Until Klaus is live and the data-mirror resumes, calibration monitoring cannot function. The dispersion ratio alert from day 23–26 of the prior stall series is unresolved.
