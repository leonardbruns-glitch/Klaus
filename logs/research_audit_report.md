# Research Audit — 2026-08-02T1030Z — STALL day 10 / EVOLVE day: systemd failed, 0 live paths, capital $0.41 below ruin floor

**ABORT**: `system_status.txt` shows `failed / unknown` — does not contain `'klaus systemd: active'`.  
**Abort day**: 10 consecutive (last active 2026-07-24T10:09:19Z; owner-directed shutdown 2026-07-24; daily + liveness timers disabled; WEEKLY-ONLY loop per EVOLVE commit `ddbcecdd1`).  
**Snapshot**: 2026-08-02T10:15:12Z — **FRESH** (< 1h old at run time).  
**Today is the weekly EVOLVE day.** Path decision is due.  
**Protocol**: stall header + structural delta from today's specialist reports. No fabricated analysis.

---

## Structural State (all four specialist reports filed today — ABORT/STALL confirmed)

| Dimension | Value | Source |
|---|---|---|
| Capital | $88.750373 | bankroll.json (unchanged since EVOLVE 2026-07-26) |
| Ruin floor | $89.16 | gatekeeper_report.md |
| Below floor | **$0.41** — all band paths mechanically blocked | gatekeeper_report.md |
| Open positions | 0 | system_status.txt |
| Resting orders | 0 | system_status.txt |
| Consecutive zero-fill days | 14 | pnl_ledger_report.md |
| Bot dead hours | ~214h (day 10) | calib_monitor_report.md |
| BAND_LIVE | False — day 27 dark (wind-down 2026-07-06) | band_config.txt |
| BAND_NO_ENABLED | False — rail-halt 2026-07-02, 7d WR 39.2% | band_config.txt |
| G8 UPDOWN_CROSSING | KILLED — graveyard #15 (EVOLVE 2026-07-26) | gatekeeper_report.md |
| UPDOWN_STOP | Active (sniper cut 2026-07-19, PF 0.79) | gatekeeper_report.md |
| LDA | STOP (rolling-20 worst −$36.39 < −$30 floor) | pnl_ledger_report.md |
| disp_ratio7 | 0.781 — INVERTED, day ~31 consecutive, all regions <1.0 | calib_monitor_report.md S3 CARRIED |
| Winner's curse G3 | CONFIRMED n=75, filled WR 17.3%, CI entirely negative | gatekeeper_report.md G3 |
| Gates READY | 0 | gatekeeper_report.md |
| Gates REJECTED (new) | 0 | gatekeeper_report.md |
| Gate accumulation | Frozen — no shadow data since 2026-07-24T10:09Z | gatekeeper_report.md |
| Isotonic deployed | ~57d stale (2026-06-06); candidate OOS brier_cal ≥ brier_raw — do NOT deploy | calib_monitor_report.md S4 CARRIED |
| Expected maker rebate | ~$3.917 (unverified; user must check Polymarket wallet) | pnl_ledger_report.md |

**No live path exists.** NEG_RISK_ARB is the only path not hard-rejected; cannot be assessed while system is down.

---

## Delta vs Prior Audit (2026-08-01)

| Counter | 08-01 | 08-02 | Change |
|---|---|---|---|
| System dead | day 9 | **day 10** | +1 |
| BAND dark | day 26 | **day 27** | +1 |
| Dispersion inversion | day ~30 | **day ~31** | +1 |
| Stall (gatekeeper) | stall #12 | **stall #13** | +1 |
| Zero-fill days | day 13 | **day 14** | +1 |
| Gate counts | all +0 | all +0 | no change |
| EVOLVE due | no | **YES (weekly)** | action pending |

No structural transitions. All alerts persist unchanged.

---

## EVOLVE Day Summary (weekly — all paths remain closed)

The 08-01 audit sections 1–7 remain the live analysis; no re-computation is warranted on stale data.

**Path status as of EVOLVE 2026-08-02:**
- All taker paths hard-rejected (G8 killed, G5/G6 REJECTED, UPDOWN_STOP, LDA_STOP).
- Band maker paths blocked by: (a) capital $0.41 below charter ruin floor, (b) dispersion inversion day ~31, (c) BAND_LIVE=False / wind-down still active, (d) winner's curse confirmed in G3.
- NEG_RISK_ARB: only surviving path. Not assessable while system is down. Last confirmed sighting 2026-07-23T21:54Z; 9+ days without a live reading.
- Gate accumulation: entirely frozen since system went down. No gate can approach READY without shadow data flowing.

**Dispersion edge assessment**: disp_ratio7 = 0.781 for 31 consecutive days across all three regions. The band's core assumption (implied spread > realized spread) is not satisfied. Even if BAND_LIVE were re-enabled, the regime does not support profitable band execution.

---

## PROPOSED ACTIONS (human review — EVOLVE day)

1. **SSH VPS → diagnose service → `sudo systemctl start klaus`**: Zero-cost prerequisite for any recovery. Monitor `journalctl -fu klaus` for 15 min — if NEG_RISK_ARB events appear, the one remaining path is live.
2. **Inject ≥$0.41 USDC**: Clears band ruin-floor mechanical block. Required before any band path can re-engage. Cost: trivial.
3. **EVOLVE path decision today**:
   - If NEG_RISK_ARB shows activity after restart → define daily cap, monitor 7d, set n≥50 gate.
   - If NEG_RISK_ARB shows 0 sightings in 15 min of live operation → no autonomous revenue path exists. Options: capital injection + strategy redesign (dispersion regime must first reverse), or orderly shutdown + capital withdrawal.
   - The dispersion inversion (day ~31, ratio 0.781, all regions) is the decisive blocker for any band revival. It is not a parameter problem; it is a market-regime problem.
4. **Verify maker rebate payout**: Expected ~$3.917 in Polymarket wallet (pUSD). Unverified. Check before any capital injection decision.
5. **Do NOT deploy isotonic candidate**: OOS brier_cal ≥ brier_raw; 2 material tail diffs. S4 alert carried. Human review required.
6. **No gate/param changes**: 0 READY, 0 new REJECTED, no data. No action.
