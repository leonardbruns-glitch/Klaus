# Klaus Calib Monitor — 2026-08-17 — STALL (day 24)

**ABORT: snapshot_ts `2026-08-16T11:26:01Z` is >24h old (limit: 6h); `systemd: failed/unknown` — no metrics computable. One-line stall header, exiting.**

---

## ABORT REASON

Both pre-flight abort conditions triggered:

| Condition | Value | Threshold | Status |
|---|---|---|---|
| snapshot age | >24h (2026-08-16T11:26:01Z) | ≤6h | FAIL |
| systemd status | `failed / unknown` | `active` | FAIL |

System has been down continuously since **2026-07-24T10:09:19Z** (24 days). No stwa_pricer_eval_s50 data is available in any `data/shadow/<date>/` subdirectory through today (confirmed via data-mirror shadow_summary.json, consistent with prior 23 stall runs).

---

## CARRIED METRICS (last valid state: 2026-07-26)

No new computation possible. Metrics below are carried forward unchanged.

| Metric | Last Known | Alert Threshold | Status |
|---|---|---|---|
| brier7 | 0.055 | >0.15 | OK |
| ece7 | ~0.000 | >0.05 | OK |
| rank-rho | — | <+0.15 | unknown |
| **disp_ratio7** | **0.781** | **<1.10** | **ALERT (day 22)** |

---

## SECTIONS (stub — all require live data)

### 1. SETTLED LANE
No pricer_eval_s50 data. Cannot compute.

### 2. PROXY LANE
No today's pricer rows. Cannot compute.

### 3. DISPERSION GAUGE (critical)
**ALERT (pre-registered, 22nd consecutive run):** `disp_ratio7 = 0.781 < 1.10`. The dispersion premium the band strategy harvests is compressing — or more precisely, has been unobservable for 24 days while the last measured value was already below threshold. This alert has been sustained since the first measurement below 1.10. The edge premise (implied sigma > realized sigma) is unconfirmed. **The edge may be decaying or already gone.**

No new data to update the ratio. Carried at 0.781.

### 4. ISOTONIC STALENESS
Candidate not promoted. As of last check (2026-07-26):

| Grid point | Deployed | Candidate | Delta | Material |
|---|---|---|---|---|
| 0.95 | 0.3822 | 0.4374 | +0.0552 | YES |
| 1.00 | 0.6316 | 0.8000 | +0.1684 | YES |

- Candidate refit: 2026-07-23T09:30:44Z
- Deployed refit: 2026-06-06T22:27:08Z
- **Days since promotion: 72 days** — the candidate calibration is materially different and aging. When the system comes back up, the live-refit cron on the VPS should promote this.

### 5. STATE DIFF
No transitions vs prior run (2026-08-16). `disp_ratio_alert_consecutive_runs` incremented 21 → 22.

---

## ALERTS (pre-registered only)

**[ACTIVE] DISPERSION RATIO ALERT — 22nd consecutive run**
`disp_ratio7 = 0.781 < 1.10` (last known). The dispersion edge premise is not confirmed live. This is not a "pending" situation — 22 consecutive monitoring runs without a reading above threshold. If the system restarts and the ratio does not recover above 1.10 on fresh data, the band strategy's core edge claim is falsified and trading should halt.

---

## RECOMMENDATIONS (report-only; do NOT edit configs)

1. **VPS restart required.** System has been dead 24 days. SSH to VPS, check `systemctl status klaus`, restart service.
2. **Pricer eval pipeline.** Once live, confirm `stwa_pricer_eval_s50.jsonl` is writing to `data/shadow/<date>/` — it has been absent for all 24 stall days.
3. **Isotonic candidate promotion.** 72 days since last promotion; candidate delta is material (+0.168 at grid 1.0). The VPS live-refit cron should promote when it next runs post-restart.
4. **Dispersion ratio.** First metric to recompute when data resumes. If it does not recover above 1.10 within 7 trading days, escalate to strategy review.
