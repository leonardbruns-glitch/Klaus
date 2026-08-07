# Calib Monitor Report — 2026-08-07T08:48:00Z

**STALL — ABORT: `system_status.txt` shows `failed/unknown` — not 'active'. Systemd down day 15 (since 2026-07-24).**

No pricer_eval_s50 data exists in any shadow subdirectory. Pipeline stages 1–3 cannot run. Section 4 (isotonic staleness) is computed from repo files only and is reported below.

---

## Data Availability

| Item | Status |
|---|---|
| data-mirror snapshot | Fresh: 2026-08-07T08:17:33Z ✓ (< 1h old) |
| system_status.txt | `failed/unknown` — ABORT condition met |
| stwa_pricer_eval_s50.jsonl (dated dirs) | **Absent** — checked 2026-08-01 through 2026-08-06; each subdir contains only `badatmath_watch.jsonl`, `count_lock.jsonl`, `maker_flow.jsonl`, `minmax_coherence.jsonl` |
| stwa_pricer_eval_s50.jsonl (live) | **Absent** — not in `data/shadow/` |
| shadow_summary.json loggers | badatmath_watch, count_lock, maker_flow, minmax_coherence — no pricer_eval |
| Last pricer data | Prior to 2026-07-24 (system down 15 days) |

**Root cause**: VPS systemd service has been dead since 2026-07-24. The STWA band engine (which generates pricer_eval rows) has not run in 14 days. Other loggers (badatmath_watch, maker_flow) continue via separate crons, but the main band loop that produces pricer_eval is offline.

---

## §1 Settled Lane — SKIPPED

n=0 resolved pricer_eval rows available. Cannot compute Brier, ECE, or rank-rho.

**Carried forward (2026-07-26, 12 days stale): brier7=0.055** — was within the 0.15 threshold when last computed.

---

## §2 Proxy Lane — SKIPPED

No unsettled pricer rows available. Cannot compute p_cal vs market mid divergence.

---

## §3 Dispersion Gauge — SKIPPED (ALERT CARRIED)

Cannot compute implied/realized width ratio. No resolved pricer_eval rows available since service went down.

**Carried forward (2026-07-26): disp_ratio7=0.781**

This is below the 1.10 alert threshold. The dispersion premium that the band harvests is measured at 0.781 — meaning implied width is only 78% of realized width, a reversal of the edge condition. The band edge was already decaying when last measured; it cannot be reassessed until the VPS service is restored and pricer_eval resumes.

**The edge is decaying. This is not smoothed over — the last observed ratio is sub-threshold and has been unrefreshable for 12 days.**

---

## §4 Isotonic Staleness

| | Deployed | Candidate |
|---|---|---|
| refit_utc | 2026-06-06 (62 days ago) | 2026-07-23 (15 days ago) |
| n_hist | 76,617 | 76,617 |
| n_live | 0 | 3,392 (live_weight=8) |
| brier_live_oos_raw | N/A | 0.0637 |
| brier_live_oos_cal | N/A | 0.0638 (negligible cal gain on live) |
| near_identity_maxdev | 0.568 | 0.513 |

**Grid comparison (deployed vs candidate, material = |diff| > 0.05):**

| grid | deployed | candidate | diff | |
|---|---|---|---|---|
| 0.00 | 0.0000 | 0.0042 | +0.004 | |
| 0.05 | 0.0695 | 0.0708 | +0.001 | |
| 0.10 | 0.1340 | 0.1255 | −0.009 | |
| 0.15 | 0.1828 | 0.1831 | +0.000 | |
| 0.20 | 0.2663 | 0.2697 | +0.003 | |
| 0.25 | 0.3557 | 0.3373 | −0.018 | |
| 0.30–0.85 | 0.3801 | 0.3748 | −0.005 | |
| 0.90 | 0.3801 | 0.3919 | +0.012 | |
| **0.95** | **0.3822** | **0.4374** | **+0.055** | **MATERIAL** |
| **1.00** | **0.6316** | **0.8000** | **+0.168** | **MATERIAL** |

**Direction**: the candidate shifts p_cal **upward** at the top of the probability range (grid 0.95 and 1.00). For the 0.30–0.85 range (the dense band-trading zone), the shift is negligible (−0.005). The material movement at grid[0.95] and grid[1.00] affects near-certainty buckets where few fills occur; practical trading impact is low, but the calibration divergence at the tail has persisted since the prior refit (2026-07-23, 15 days ago).

The deployed isotonic curve is 62 days old. The candidate exists but the live-refit cron's output is stranded — it cannot be promoted while the main service is down.

**Recommendation** (observe-only): When the VPS service is restored, the live-refit cron should promote the candidate to deployed. The material diffs are confined to grid[0.95–1.00] and do not distort band pricing in the normal operating range.

---

## §5 State

| Metric | Value | Source |
|---|---|---|
| date | 2026-08-07 | today |
| brier7 | null (system down) | — |
| ece7 | null (system down) | — |
| rho7 | null (system down) | — |
| disp_ratio7 | null (system down) | — |
| brier7_carried | 0.055 | from 2026-07-26 |
| disp_ratio7_carried | 0.781 | from 2026-07-26 |
| stall_days | 15 | since 2026-07-24 |

**Transitions vs prior state (2026-08-06)**: No changes. All three alert conditions remain active and unchanged. Stall day count incremented from 14 to 15.

---

## ALERTS

The following pre-registered alerts are active (all carried, not freshly computable):

**STALL**: `system_status.txt` shows `failed/unknown`. Systemd has been down 15 days (since 2026-07-24). No pricer_eval data generated in that window. Stages 1–3 cannot run. This alert fires every run until the service is restored.

**S3_CARRIED — DISPERSION RATIO BELOW THRESHOLD**: Last measured disp_ratio7=0.781 (2026-07-26). This is below the 1.10 alert floor. The dispersion premium the band relies on was compressing and has not been reassessable since. Cannot confirm whether it has recovered or deteriorated further. This is the edge-decay alarm — it has been active since 2026-07-26 (12 days).

**ISOTONIC_STALE**: Deployed isotonic curve is 62 days old (refit 2026-06-06). Candidate is 15 days old (refit 2026-07-23). Material divergence at grid[0.95] (+0.055) and grid[1.00] (+0.168). Candidate shifts p_cal up at the tail. Promotion blocked while service is down.
