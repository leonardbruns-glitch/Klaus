# Calib Monitor Report — 2026-08-08T08:15:00Z

**STALL — ABORT: `system_status.txt` shows `failed/unknown` — not 'active'. Systemd down day 16 (since 2026-07-24).**

No new pricer_eval_s50 data. Snapshot is fresh (2026-08-08T08:06:46Z). System timer running, main service dead.

---

## Carried Metrics (last computed 2026-07-26)

| Metric | Value | Status |
|---|---|---|
| brier7 | 0.055 | carried, 13d stale |
| ece7 | ~0 | carried, 13d stale |
| disp_ratio7 | **0.781** | **ALERT: < 1.10 threshold — ACTIVE 13d** |
| stall_days | 16 | since 2026-07-24 |

**The dispersion edge is decaying.** Last ratio 0.781 means implied width is only 78% of realized — the band premium was already inverted when last measurable. It has not been reassessable for 13 days. The edge-decay alarm remains active.

Pipeline stages 1–3 (Brier/ECE/rho, proxy lane, dispersion gauge) all require pricer_eval_s50 rows. None exist. Skipped.

Isotonic staleness unchanged from prior report: deployed curve 63 days old, candidate (2026-07-23) has material +0.055/+0.168 tail divergence, promotion blocked while service is down.

## Transitions vs 2026-08-07

No changes. stall_days incremented 15 → 16. All three alerts active and unchanged.

## ALERTS

**STALL** (day 16): `failed/unknown` since 2026-07-24. Stages 1–3 cannot run.

**S3_CARRIED — DISPERSION RATIO BELOW THRESHOLD**: disp_ratio7=0.781 < 1.10. Edge decay alarm active since 2026-07-26, unrefreshable.

**ISOTONIC_STALE**: Deployed isotonic 63d old. Candidate 15d old, material tail divergence. Promotion blocked.
