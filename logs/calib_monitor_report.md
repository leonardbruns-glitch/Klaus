# Calibration & Dispersion Monitor — 2026-06-25

**STALL: `klaus systemd: failed` (not active) — ABORT condition triggered. Analytics pipeline abbreviated; dispersion gauge computed from available data.**

> Snapshot taken at 2026-06-25T07:56:21Z (15 min before run, not stale). Bot last entered active: 2026-06-24 08:04:37 UTC. Data exists for today through ~07:56 UTC (shadow timer is a separate service). Calibration lanes (Sections 1–2) could not be updated: pricer_eval_s50 files exceed API size limit and resolution join requires a live environment. Carry-forward values from 2026-06-24 report for Brier/ECE/rho.

---

## Section 1 — Settled Lane (Brier / ECE / rank-ρ)

**Status: CARRY-FORWARD from 2026-06-24. Not updated due to abort.**

| Metric | Value | Source | Threshold |
|---|---|---|---|
| 7d rolling Brier | 0.0199 | 2026-06-24 report | ALERT if > 0.15 |
| 7d ECE (10-bin) | 0.031 | 2026-06-24 report | ALERT if > 0.05 |
| 7d rank-ρ (p_cal vs outcome) | 0.607 | 2026-06-24 report | ALERT if < 0.15 |

No calibration alerts from carried-forward values. Verification deferred until service is restored.

---

## Section 2 — Proxy Lane (unsettled, p_cal vs market mid)

**Status: NOT COMPUTED — abort condition. Prior baseline: d+1 median |p_cal − mid| = 0.0084 (7d rolling).**

Today's snapshot contains 84,656 rows in `hot/2026-06-25/stwa_pricer_eval.jsonl` (up to 07:56 UTC), but the resolution join and full proxy computation require a live environment. No spike can be confirmed or denied.

---

## Section 3 — Dispersion Gauge ⚠️ ALERT

**This is the load-bearing quantity. It has not recovered.**

### Methodology
Proxy: median weighted-std of bucket midpoints (weight = ask price) across all band-quoted events per log-day, from `band_struct_lite.jsonl`. Confirmed methodology via 2026-06-23 recompute (1.049 vs prior 1.050 — match within rounding). 2026-06-25 is partial (service stopped ~07:56 UTC; 66 band events available — sufficient for proxy).

True sigma reference: canonical 1.300°C (validated 2026-06).

### Per-Day Implied Sigma

| Date | Implied σ (°C) | Source |
|---|---|---|
| 2026-06-19 | 1.118 | prior state |
| 2026-06-20 | 1.012 | prior state |
| 2026-06-21 | 1.109 | prior state |
| 2026-06-22 | 1.124 | prior state |
| 2026-06-23 | 1.049 | recomputed (confirmed) |
| 2026-06-24 | 1.101 | recomputed (confirmed) |
| 2026-06-25 | 1.051 | partial day (n=66 events, 07:56 UTC cutoff) |

### 7-Day Rolling Summary

| Metric | Value | Prior (2026-06-24) | Change |
|---|---|---|---|
| 7d median implied σ | 1.101°C | 1.105°C | −0.004°C |
| True σ (canonical) | 1.300°C | 1.300°C | — |
| **Ratio (implied/true)** | **0.847** | **0.850** | **−0.003** |
| Alert threshold | < 1.10 | — | — |
| Consecutive alert days | **6** | 5 | +1 |
| Last ladder-book ratio | 0.714 (2026-06-22) | 0.714 (2026-06-22) | unchanged |

### Verdict

The dispersion edge is **absent and not recovering**. The ratio has been below 1.0 for six consecutive days. The implied sigma (1.101°C) remains materially below the canonical true sigma (1.300°C), meaning the market is pricing temperature uncertainty **tighter** than reality. The band's dispersion premium — the structural rationale for the strategy — is not present in current market data.

The ratio ticked down marginally (0.850 → 0.847). No upward trend. The ladder-book method last yielded 0.714 on 2026-06-22 — even weaker than the proxy.

**Regional breakdown**: Not computed (pricer files inaccessible). All prior per-day values available are aggregate across US/EU/Asia.

---

## Section 4 — Isotonic Staleness

Both files are **unchanged** from the 2026-06-24 report (same fit timestamps).

| File | Fit date | Age today |
|---|---|---|
| `config/stwa_isotonic.json` (deployed) | 2026-06-06T22:27Z | 19 days |
| `config/stwa_isotonic_candidate.json` (candidate) | 2026-06-09T09:30Z | 16 days |

**Material difference at p_model = 1.0:**
- Deployed: 0.6316
- Candidate: 0.3739
- Delta: **−0.2577** (candidate would sharply depress p_cal at very high model confidence)

At all other grid points the delta is < 0.01 in magnitude. The sole material shift is the ceiling. Neither file has been updated since the prior report. The live-refit cron appears blocked or not producing a new candidate — consistent with the service being in a failed state.

**Direction of change if candidate were deployed**: p_cal at extreme model confidence (p_model near 1.0) would drop from ~0.63 to ~0.37. This would reduce band firing at high-confidence model moments. Whether that is better or worse depends on whether high model-confidence events are currently over- or under-betting — cannot determine from available data.

---

## Section 5 — State

### System Status
- `klaus systemd`: **failed** (was active; entered active 2026-06-24 08:04 UTC)
- Open positions: 0 (safe)
- Bankroll: $198.28 (as of snapshot)
- Disk: 87% used (13 GB free) — monitoring recommended

### State Transitions vs Prior (2026-06-24)
| Field | Prior | Today | Transition |
|---|---|---|---|
| brier7 | 0.0199 | carry-forward | no change |
| ece7 | 0.031 | carry-forward | no change |
| rho7 | 0.607 | carry-forward | no change |
| disp_ratio7 | 0.850 | **0.847** | −0.003 |
| disp_alert_day_count | 5 | **6** | +1 |
| Service status | active | **failed** | **NEW** |

---

## ALERTS

### ALERT 1 (pre-registered): DISPERSION_ALERT — Day 6 of 6
`disp_ratio7 = 0.847 < 1.10`

**Implied σ 1.101°C < canonical true σ 1.300°C. Dispersion premium has been absent for six consecutive days. No upward trend.**

The last authoritative ladder-book measurement (2026-06-22): 0.714 — even lower than the proxy. The band posts YES bids on wing buckets. For this to be profitable, the market must be pricing those wing buckets above their true probability. The data says the opposite: the market's implied distribution is narrower than realized outcomes. The dispersion premium is not there.

Recommendation (non-binding): Consider halting band YES leg (STWA_REGULAR_YES_ENABLED is already False; BAND_LIVE is True but NO-only focus). Review whether the NO-only strategy retains edge independent of the dispersion gauge. The dispersion gauge was designed specifically to protect the YES wing purchases; the NO strategy has a separate rationale.

### ALERT 2 (non-pre-registered, informational): Service failure
`klaus systemd: failed` — service was active as of 2026-06-24 08:04 UTC and is currently not running. Today's data generation halted at ~07:56 UTC. This is an infrastructure event, not a signal event. Requires manual restart on VPS.
