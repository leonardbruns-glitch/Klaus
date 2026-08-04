# Research Audit — 2026-08-04T1030Z — STALL day 11: systemd failed, 0 live paths, capital $0.41 below ruin floor

**ABORT**: `system_status.txt` shows `failed / unknown` — does not contain `'klaus systemd: active'`.  
**Stall day**: 11 consecutive (last active 2026-07-24T10:09:19Z; owner-directed shutdown; daily+liveness timers disabled; WEEKLY-ONLY per EVOLVE commit `ddbcecdd1`).  
**Snapshot**: 2026-08-04T10:25:56Z — FRESH (< 1h old).  
**Protocol**: one-line stall header + delta from today's specialist reports. No fabricated analysis.

---

## Specialist Report Status (all four present, all fresh)

| Report | Timestamp | Status |
|---|---|---|
| exec_audit_report.md | 2026-08-04T07:08Z | ABORT — systemd failed/unknown day 11 |
| calib_monitor_report.md | 2026-08-04T08:09Z | STALL day 12 consecutive abort; disp_ratio=0.781 INVERTED day 33 |
| gatekeeper_report.md | 2026-08-04T09:10Z | STALL #15; 0 READY, 0 REJECTED, all counts frozen |
| pnl_ledger_report.md | 2026-08-03T23:37Z | ABORT — day 10 at filing; 15 consecutive zero-fill days |

All four within the 36h freshness threshold. No report missing.

---

## Structural State (from today's specialist reports)

| Dimension | Value | Source |
|---|---|---|
| Capital | $88.750373 | bankroll.json (static) |
| Ruin floor | $89.16 | gatekeeper_report.md |
| Below ruin floor | **−$0.41** — band paths mechanically blocked | gatekeeper_report.md |
| Open positions | 0 | system_status.txt |
| Consecutive zero-fill days | **16** (day 15 as of 08-03; +1 today) | pnl_ledger_report.md |
| Bot dead | ~262h (~10.9 days) | calib_monitor_report.md |
| BAND_LIVE | False — day 29 dark (wind-down 2026-07-06) | band_config.txt |
| BAND_NO_ENABLED | False — rail-halt 2026-07-02 | band_config.txt |
| G8 UPDOWN_CROSSING | KILLED — graveyard #15 (EVOLVE 2026-07-26) | gatekeeper_report.md |
| UPDOWN_STOP | Active (sniper cut 2026-07-19, PF 0.79) | gatekeeper_report.md |
| LDA_STOP | Active (rolling-20 worst −$36.39 < −$30 floor) | gatekeeper_report.md |
| disp_ratio7 | 0.781 — INVERTED, day 33 est, all 3 regions <1.0 | calib_monitor_report.md S3 CARRIED |
| Winner's curse G3 | CONFIRMED n=75, filled WR 17.3%, CI entirely negative | gatekeeper_report.md G3 |
| Gates READY | 0 | gatekeeper_report.md |
| Gates newly REJECTED | 0 | gatekeeper_report.md |
| Gate accumulation | Frozen — no shadow data since 2026-07-24 | gatekeeper_report.md |
| Isotonic deployed | ~59d stale; candidate OOS brier_cal ≥ brier_raw — do NOT deploy | calib_monitor_report.md S4 |
| Expected maker rebate | ~$3.917 upper bound (unverified in Polymarket wallet) | pnl_ledger_report.md |

**No live path exists.** NEG_RISK_ARB is the only path not formally killed; it cannot be assessed while the system is down and no fill data is flowing.

---

## Delta vs Prior Audit (2026-08-03)

| Counter | 08-03 | 08-04 | Change |
|---|---|---|---|
| System dead | day 11 | **day 11** (~262h) | static count; +24h elapsed |
| BAND dark | day 28 | **day 29** | +1 |
| Dispersion inversion | day ~32 | **day ~33** | +1 (estimate; no fresh compute) |
| Gate stall count | #14 (est) | **#15** (confirmed) | +1 |
| Zero-fill days | 15 | **16** | +1 |
| Capital | $88.750373 | $88.750373 | **unchanged** |
| Below ruin floor | −$0.41 | −$0.41 | **unchanged** |
| Gate counts | all +0 | all +0 | frozen |
| Calib alerts | 3 active | 3 active | no transitions |

No structural transitions. All three calib alerts (SYSTEM, S3 dispersion, S4 isotonic) persist unchanged.

---

## Sections 1–7: SUPPRESSED

Full audit sections suppressed per abort protocol. No live system = no execution data, no calibration inputs, no gate movement. Yesterday's full-analysis sections in the 08-03 audit remain the live analysis; the structural state above is the complete incremental update.

---

## PROPOSED ACTIONS (human review)

*Unchanged from 08-03. Repeated for completeness.*

| # | Action | Why |
|---|---|---|
| 1 | **SSH VPS → `sudo systemctl start klaus`** | Zero-cost prerequisite for any path forward. Watch `journalctl -fu klaus` 15 min — if NEG_RISK_ARB events appear, the one surviving path may be live. |
| 2 | **Inject ≥$0.41 USDC** | Clears band ruin-floor mechanical block ($88.75 < $89.16). Required before any band path can re-engage after restart. |
| 3 | **Verify maker rebate receipt** | ~$3.917 upper-bound unverified in Polymarket pUSD wallet. Confirm before any capital decision. |
| 4 | **Dispersion regime decision** | disp_ratio7 = 0.781 (need >1.10), day ~33 inverted, all regions below 1.0. Even after restart + injection, no band edge in this regime. The inversion is a market-structure issue, not a parameter issue. |
| 5 | **Do NOT deploy isotonic candidate** | OOS brier_cal ≥ brier_raw; 2 material tail diffs (grid 0.95: +0.055; grid 1.0: +0.168). S4 alert held. |
| 6 | **No gate/param changes** | 0 READY, 0 new REJECTED, all data frozen since 07-24. Nothing to action. |
