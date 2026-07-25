# Research Audit — 2026-07-25T1019Z

**STALL: `system_status.txt` = "failed / unknown" — abort condition met. One-line header; analysis sections not re-run. Prior full audit (2026-07-24T1028Z) remains the most recent valid report.**

---

**Generated:** 2026-07-25T10:19Z  
**SNAPSHOT:** 2026-07-25T10:19:25Z (< 1 min old — FRESH ✓; data-mirror timer still running)  
**System:** `failed / unknown` ⚠ — SERVICE DOWN ~24 HOURS (last active: 2026-07-24T10:09:19 UTC)  
**Equity:** $21.495442 (unchanged; all paths disarmed, burn rate zero)  
**Specialist reports:** All four STALL — no new data computed today

---

## Abort Rationale

Snapshot is fresh. System is NOT active. All four sibling routines triggered their own abort conditions:

| Report | Run time | Status |
|---|---|---|
| exec_audit_report.md | 2026-07-25T07:07Z | ABORT (one line) |
| calib_monitor_report.md | 2026-07-25T08:12Z | STALL (prior state carried) |
| gatekeeper_report.md | 2026-07-25T09:03Z | STALL (prior state carried) |
| pnl_ledger_report.md | 2026-07-24T23:40Z | STALL (prior day, <36h) |

No new fill data, no new calibration computation, no gate resolutions confirmed, no P&L events. Sections 1–7 from the 2026-07-24T1028Z audit stand unchanged as the authoritative analysis. This report records the delta and escalates two time-sensitive items.

---

## Delta vs Prior Audit (2026-07-24T1028Z)

| Item | Yesterday | Today | Change |
|---|---|---|---|
| Service state | `failed` (crash ~10:09 UTC, ~15 min after restart) | `failed` (continuous, ~24h) | **ESCALATED — not a crash-loop, sustained failure** |
| Band dark days | 18 | 19 | +1, no change in status |
| G8 n (confirmed) | 88 (authoritative Jul-23 22:08Z) | **~98–112 (estimated; unconfirmed)** | Kill-formalization may have already crossed n≥100 |
| disp_ratio7 | 0.781 (S3 day 22) | 0.781 (carried; S3 day ~23) | +1 inversion day, no new computation |
| Capital | $21.495442 | $21.495442 | Unchanged (zero burn) |
| Specialist reports | All executed, full pipelines | All STALL | Degraded observability |

### G8 Kill Math Update

Last authoritative count: n=88 (84W/4L) at 2026-07-23T22:08Z. Time elapsed: ~36h. Historical accrual rate: ~7–16 settles/day.

| Scenario | n estimate | vs BE 96.49% | Status |
|---|---|---|---|
| Conservative (+7/day × 1.5d) | ~98 | still below | Kill-LOCKED, not yet at threshold |
| Mid (+11/day × 1.5d) | ~105 | below | **Kill fires if count confirmed** |
| Prior window rate (+16/day × 1.5d) | ~112 | below | Kill fired; likely already crossed |

**The kill is mathematically inevitable in all scenarios.** Best-case at threshold (96/100 = 96.00%) is still below BE 96.49%. The only open question is whether n=100 has been formally crossed. shadow_grade.py (VPS-side script) is required to confirm. System failure has frozen this count.

---

## PROPOSED ACTIONS (human review — all from prior audit, now escalated)

### URGENT — Day 2 (system down ~24h, no automated recovery)

**Action 1: SSH to VPS immediately**

Service failed at some point after 2026-07-24T10:09:19 UTC and has not recovered for ~24 hours. Burn rate is zero (all paths disarmed), so no capital risk — but shadow accrual, watchdog, and gate_ledger refreshes have all been paused. G8 kill-formalization cannot complete without `shadow_grade.py --refetch`.

```bash
# Diagnose failure
journalctl -u klaus.service --since "2026-07-24 10:00" --no-pager | tail -100
systemctl status klaus.service
df -h   # check disk — prior reclaim rounds: 94%→87%→71%→75% (current); may have filled again
```

Likely causes in priority order:
1. **Disk full** — was 75% (24GB free) as of snapshot; shadow logging at ~828 rows/h × 24h = significant accrual; prior reclaim rounds triggered at 85–94%; if a large agent/shadow write ran, could have filled.
2. **Python exception in shadow-only scan path** — crash-at-restart pattern on 07-24 suggests a code path that only runs post-startup; service has no watchdog restart since 07-14 per prior state.
3. **OOM** — less likely given disk reclaims, but 24h of shadow buffering without rotation could spike RSS.

Fix if disk full: `gzip -1 data/shadow/2026-07-*/` (prior method); do NOT delete files without checking log windows.

**Action 2: Confirm G8 n-count and execute kill if n≥100**

```bash
python3 shadow_grade.py --refetch  # authoritative count
```

If output shows n≥100 and WR < 96.49%: formally CLOSE UPDOWN_CROSSING class. Per state_log pre-registration (2026-07-19T14:30Z): "Point WR < BE at n≥100 → recommend class CLOSED." Set `UPDOWN_CROSSING_ENABLED = False`; record in state_log; remove UPDOWN_STOP after kill is logged. Do NOT re-enable without fresh pre-registration and clean candidate pool.

**Action 3: Verify pUSD rebate** (same session)

Check Polymarket wallet for pUSD balance. Accrued estimate: $3.917 (pre-Jul-6 maker fills). At $21.50 equity, this is an 18% immediate capital recovery if claimed. No new band fills since Jul-6 — this balance will not grow further; claim or close.

---

### Non-Urgent (unchanged from prior audit)

4. **Dispersion regime dating** — full rolling disp_ratio on stwa_pricer_eval_s50.jsonl; structural break test. Establishes whether S3 inversion is cyclical or permanent. Next VPS session after service recovery.

5. **Isotonic candidate — hold** — brier_cal (0.0638) ≥ brier_raw (0.0637); material tail diffs at p=0.95 and p=1.0. Do not promote without human review of tail behavior. Deployed curve now ~49d stale.

6. **Competitor posture rotation** (day 25 mod 3 = 1: market census — new weather cities/products) — blocked by network constraints in remote env. Run on VPS or next full-pipeline day.

---

## No-Analysis Summary (per anti-sycophancy rule)

This is a null day. All five sibling routines (including this one) triggered stall conditions. No new edge data exists. The prior full audit (Jul-24T1028Z) is the current authoritative analysis. The only productive outputs today are operational:

- **Service has been down ~24h. SSH is required.**
- **G8 kill-formalization is likely already at n≥100 but unconfirmed. SSH confirms it.**
- **Everything else is unchanged.** Capital $21.495, all paths disarmed, no live orders, no new gate data.

A second consecutive null day without SSH action means the G8 gate will remain KILL-LOCKED-but-unformalized, shadow accrual will remain interrupted, and disk state will be unverified. None of these have capital consequences today. They do have tracking and data-integrity consequences for future sessions.

---

*Research audit is REPORT-ONLY. No strategy code or flags were modified.*  
*Run: 2026-07-25T10:19Z | System: failed/unknown (day 2) | Prior full audit: 2026-07-24T10:28Z*
