# Research Audit — 2026-08-03T1030Z — STALL day 11: systemd failed, 0 live paths, capital $0.41 below ruin floor

**ABORT**: `system_status.txt` shows `failed / unknown` — does not contain `'klaus systemd: active'`.  
**Stall day**: 11 consecutive (last active 2026-07-24T10:09:19Z; owner-directed shutdown; daily+liveness timers disabled; WEEKLY-ONLY per EVOLVE commit `ddbcecdd1`).  
**Snapshot**: 2026-08-03T10:21:06Z — FRESH (< 1h old).  
**Protocol**: one-line stall header + delta from today's specialist reports. No fabricated analysis.

---

## Specialist Report Status

| Report | Timestamp | Status |
|---|---|---|
| exec_audit_report.md | 2026-08-03T07:04Z | ABORT — systemd failed day 11 |
| calib_monitor_report.md | 2026-08-03T08:05Z | ABORT — day 11 consecutive abort |
| gatekeeper_report.md | **2026-08-02T09:11Z** (yesterday — 25h old; within 36h threshold) | STALL #13 |
| pnl_ledger_report.md | 2026-08-02T23:37Z | ABORT — day 9 at filing |

---

## Structural State (from today's specialist reports)

| Dimension | Value | Source |
|---|---|---|
| Capital | $88.750373 | bankroll.json |
| Ruin floor | $89.16 | gatekeeper_report.md |
| Below floor | **−$0.41** — all band paths mechanically blocked | gatekeeper_report.md G4 |
| Open positions | 0 | system_status.txt |
| Consecutive zero-fill days | 14+ | pnl_ledger_report.md |
| Bot dead | ~238h (~9.9 days) | calib_monitor_report.md |
| BAND_LIVE | False — day 28 dark (wind-down 2026-07-06) | band_config.txt |
| BAND_NO_ENABLED | False — rail-halt 2026-07-02 | band_config.txt |
| G8 UPDOWN_CROSSING | KILLED — graveyard #15 (EVOLVE 2026-07-26) | gatekeeper_report.md |
| UPDOWN_STOP | Active (sniper cut 2026-07-19, PF 0.79) | gatekeeper_report.md |
| LDA_STOP | Active (rolling-20 worst −$36.39 < −$30 floor) | gatekeeper_report.md |
| disp_ratio7 | 0.781 — INVERTED, day ~32 consecutive, all regions <1.0 | calib_monitor_report.md S3 CARRIED |
| Winner's curse G3 | CONFIRMED n=75, filled WR 17.3%, CI entirely negative | gatekeeper_report.md G3 |
| Gates READY | 0 | gatekeeper_report.md |
| Gates REJECTED (new) | 0 | gatekeeper_report.md |
| Gate accumulation | Frozen — no shadow data since 2026-07-24 | gatekeeper_report.md |
| Isotonic deployed | ~58d stale; candidate OOS brier_cal ≥ brier_raw — do NOT deploy | calib_monitor_report.md S4 |
| Expected maker rebate | ~$3.917 (upper bound, unverified in Polymarket wallet) | pnl_ledger_report.md |

**No live path exists.** NEG_RISK_ARB is the only path not hard-rejected; cannot be assessed while system is down. No shadow data flowing since 2026-07-24.

---

## Delta vs Prior Audit (2026-08-02)

| Counter | 08-02 | 08-03 | Change |
|---|---|---|---|
| System dead | day 10 | **day 11** | +1 |
| BAND dark | day 27 | **day 28** | +1 |
| Dispersion inversion | day ~31 | **day ~32** | +1 |
| Gate stall count | #13 | **#14 (est)** | +1 |
| Zero-fill days | 14 | **14+ (static)** | frozen |
| Capital | $88.750373 | $88.750373 | **unchanged** |
| Below ruin floor | −$0.41 | −$0.41 | **unchanged** |
| Gate counts | all +0 | all +0 | no change |

No structural transitions. All three calib alerts (SYSTEM, S3 dispersion, S4 isotonic) persist unchanged.

---

## Sections 1–7: SUPPRESSED

Full audit sections suppressed per abort protocol (no live system = no execution data, no calibration data, no gate movement). Yesterday's full sections in the 08-02 report remain the live analysis; the structural state above constitutes the complete incremental update.

---

## PROPOSED ACTIONS (human review)

*No new actions vs 08-02 report. Repeated here for completeness.*

1. **SSH VPS → `sudo systemctl start klaus`**: Zero-cost prerequisite. Watch `journalctl -fu klaus` for 15 min — if NEG_RISK_ARB events appear, the one surviving path is live.
2. **Inject ≥$0.41 USDC**: Clears band ruin-floor mechanical block. Required before any band path can re-engage after a restart.
3. **Dispersion regime check**: disp_ratio7 = 0.781 (need >1.10), day ~32 inverted across all regions. Even after restart + injection, no band edge exists in this regime. The dispersion inversion is a market-regime issue, not a parameter issue.
4. **Verify maker rebate**: ~$3.917 upper-bound unverified in Polymarket wallet (pUSD). Check before any capital decision.
5. **Do NOT deploy isotonic candidate**: OOS brier_cal ≥ brier_raw; 2 material tail diffs at grid 0.95/1.0. S4 alert held.
6. **No gate/param changes**: 0 READY, 0 new REJECTED, frozen data. Nothing to action.
