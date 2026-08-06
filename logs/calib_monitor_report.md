# Calib Monitor Report — 2026-08-06T08:11:53Z

**STALL — ABORT: `system_status.txt` shows `failed/unknown` — not 'active'. Systemd down day 14 (since 2026-07-24).**

No pricer_eval_s50 data exists in any shadow subdirectory. Pipeline stages 1–3 cannot run. Section 4 (isotonic staleness) is computed from repo files and is reported below.

---

## Data Availability

| Item | Status |
|---|---|
| data-mirror snapshot | Fresh: 2026-08-06T08:11:53Z ✓ |
| system_status.txt | `failed/unknown` — abort condition |
| stwa_pricer_eval_s50.jsonl (dated dirs) | **Absent** — checked 2026-08-01 through 2026-08-05; each subdir contains only `badatmath_watch.jsonl` (some empty) |
| stwa_pricer_eval_s50.jsonl (live) | **Absent** — not in `data/shadow/` |
| shadow_summary.json loggers | badatmath_watch, count_lock, maker_flow, minmax_coherence, updown_sniper/snap — no pricer_eval |
| Last pricer data | Last generated prior to 2026-07-24 (system down) |

**Root cause**: VPS systemd service has been dead since 2026-07-24. The STWA band engine (which generates pricer_eval rows) has not run in 13 days. Other loggers (badatmath_watch, maker_flow) are still alive via separate processes or crons, but the main band loop that produces pricer eval is dead.

---

## §1 Settled Lane — SKIPPED

n=0 resolved pricer_eval rows available for any date window. Cannot compute Brier, ECE, or rank-rho.

Last known (2026-07-26, 11 days stale): **brier7=0.055**.

Alerts: none fired today (no data). Prior state: brier7=0.055 was within the 0.15 threshold; ECE and rho were not computed in prior stall runs.

---

## §2 Proxy Lane — SKIPPED

No pricer_eval data → no p_cal rows → no proxy divergence computation possible.

---

## §3 Dispersion Gauge — CARRIED / PRE-EXISTING ALERT ACTIVE

Cannot recompute — no pricer_eval data.

Last known value (from 2026-07-26 commit): **disp_ratio7 = 0.781**.

This is below the 1.10 alert threshold. The alert has been active since at least 2026-07-24 when the system went down. This value has not been updated in 11 days and may have drifted further in either direction during the outage.

**PRE-REGISTERED ALERT — CARRIED (cannot confirm or clear):**
> disp_ratio7 = 0.781 < 1.10 threshold. The dispersion premium harvested by the band strategy is compressed. If the ratio has continued declining during the outage, the edge erosion is worse than last reported.

**Why this matters**: The band strategy's entire rationale rests on implied dispersion exceeding realized dispersion (validated 2026-06: true σ ~1.3°C < implied). A ratio below 1.10 signals that the market is pricing distributions that are already close to or at realized width — the spread the band earns on each YES-NO pair is shrinking. With 13 days of missing data, we cannot confirm whether the edge has partially recovered or continued to decay.

Regional breakdown and trend vs prior: **not computable** (no resolved rows).

---

## §4 Isotonic Staleness — COMPUTED

| Grid (raw) | Deployed (2026-06-06) | Candidate (2026-07-23) | Diff | Material? |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0042 | +0.0042 | no |
| 0.05 | 0.0695 | 0.0708 | +0.0013 | no |
| 0.10 | 0.1340 | 0.1255 | −0.0085 | no |
| 0.15 | 0.1828 | 0.1831 | +0.0003 | no |
| 0.20 | 0.2663 | 0.2697 | +0.0034 | no |
| 0.25 | 0.3557 | 0.3373 | −0.0184 | no |
| 0.30–0.85 | 0.3801 | 0.3748 | −0.0053 | no |
| 0.90 | 0.3801 | 0.3919 | +0.0118 | no |
| **0.95** | **0.3822** | **0.4374** | **+0.0552** | **YES** |
| **1.00** | **0.6316** | **0.8000** | **+0.1684** | **YES** |

**Material differences found at 2 grid points (threshold >0.05 absolute).**

**Direction**: The candidate raises p_cal at extreme high raw predictions (grid 0.95–1.0). This means the deployed curve is underestimating probability when the raw model is highly confident. The candidate would assign higher calibrated probabilities to near-certain events.

**Candidate metadata**: n_live=3,392 rows, 8 calendar days of live data, n_live_no_region=2,543. brier_live_oos_raw=0.0637, brier_live_oos_cal=0.0638 (negligible improvement from calibration on the live slice — the curve adds almost nothing on OOS live data, which may indicate the live slice is dominated by the flat 0.3748 region). near_identity_maxdev dropped 0.568→0.513 (curve slightly less flat).

**Deployed curve age**: 61 days (fit 2026-06-06). No live data incorporated.

**Recommendation (non-binding)**: The VPS-side refit cron should deploy the candidate on restart. The tail behavior at 0.95–1.0 is the most impactful change; the flat middle region shift (−0.005) is immaterial to live trading given the band strategy avoids 0.35–0.65 range.

---

## §5 State

Prior committed state (2026-08-05): all null (data-mirror had been fully absent).

Today's computed values: none (stall). Carrying last known from 2026-07-26:
- brier7: 0.055 (stale 11d)
- ece7: null (never computed in stall window)
- rho7: null (never computed in stall window)
- disp_ratio7: 0.781 (stale 11d)

State written: see `logs/calib_monitor_state.json`.

---

## ALERTS

### ALERT S3 — DISPERSION RATIO BELOW THRESHOLD (CARRIED, UNREFRESHABLE)
- **Metric**: disp_ratio7 = 0.781 (last computed 2026-07-26)
- **Threshold**: < 1.10
- **Status**: Pre-existing; cannot confirm or clear without pricer_eval data
- **Action**: This alert cannot be resolved until the VPS systemd service is restarted and generates new pricer_eval rows. Do not assume it has cleared.

### NOTE — ISOTONIC STALENESS (non-alert, material finding)
- **Metric**: max absolute diff between candidate and deployed = 0.168 (at grid 1.0)
- **Threshold**: > 0.05 at any grid point
- **Status**: Material at grid[0.95] (+0.055) and grid[1.0] (+0.168)
- **Action**: Candidate should be deployed on VPS restart. This is a recommendation; the guarded live-refit cron owns the decision.

---

*Report-only. No code or config edits. Calib-agent, 2026-08-06.*
