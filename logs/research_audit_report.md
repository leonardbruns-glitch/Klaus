# Research Audit 2026-08-09T1030Z — STALL-20, day 16

**⚠ ABORT CONDITION MET:** `system_status.txt` present but shows `failed/unknown` (not `active`). Specialist reports are fresh; underlying market data frozen since 2026-07-24T10:09Z. Analysis is synthesized from current specialist reports (not fabricated), clearly flagged by data age.

---

## Specialist Reports Read

| Report | Timestamp | Status |
|---|---|---|
| exec_audit_report.md | 2026-08-09T07:13Z | ABORT — systemd failed day 16, 0 fills |
| calib_monitor_report.md | 2026-08-09T08:16Z | STALL — data files absent from data-mirror (first run issue) |
| gatekeeper_report.md | 2026-08-09T09:14Z | STALL-20 — all 7 gates COLLECTING, n=null frozen |
| pnl_ledger_report.md | 2026-08-08T23:37Z | STALL day 15 — 20 consecutive zero-fill days, $0.00 |

**System heartbeat:** data-mirror timer alive (SNAPSHOT.md 2026-08-09T08:59Z, 31 min old, FRESH). Background monitors live: badatmath_watch, maker_flow, flb_screener, updown_sniper, minmax_coherence, count_lock. Core trading service: FAILED.

---

## System Baseline (all values frozen since 2026-07-24)

| Metric | Value | Source |
|---|---|---|
| Capital | $88.750373 | bankroll.json (unchanged 16d) |
| Capital composition | $21.50 CLOB + $67.25 owner-manual | EVOLVE weekly ddbcecdd1 2026-07-26 |
| Total lifetime PnL | −$75.40 | bankroll.json (total_pnl) |
| Total lifetime trades | 3,093 | bankroll.json |
| Consecutive zero-fill days | 20 | pnl_ledger |
| Service last active | 2026-07-24T10:09:19Z | system_status.txt |
| Open positions | 0 | exec_audit, pnl_ledger |
| BAND_LIVE | False (since 2026-07-06) | pnl_ledger state |
| BAND_NO_ENABLED | False (since 2026-07-02) | pnl_ledger state |
| G8 certainty-taker | FORMALLY KILLED | EVOLVE weekly ddbcecdd1 (n=127, WR 0.9528 < BE 0.9651) |
| All live paths | NONE — loop WEEKLY-ONLY | owner directive 2026-07-24 |
| disp_ratio7 | 0.781 (carried, last measured 2026-07-26) | calib_monitor_state |
| brier7 | 0.0548 (carried, last measured 2026-07-24) | calib_monitor_state |
| Isotonic calibration age | ~73 days stale | calib_monitor (48d stale on 07-24, +16d) |
| Maker rebate accrued (upper bound) | $3.917 | pnl_ledger state — **unverified in wallet** |

---

## 1. Primary Bottleneck

**OWNER ACTION REQUIRED — service restart + path re-enable decision.**

Every compounding metric is zero:
- equity deployed = $0 (no open positions)
- turns/day = 0 (no live path)
- ROI/turn = undefined

The bottleneck is NOT execution quality, calibration, or dispersion — all of those are secondary. The service has been intentionally stopped since 2026-07-24 per owner directive ("daily+liveness timers disabled → loop WEEKLY-ONLY"). 20 research audits have issued the same recommendation (SSH restart) with no visible response. This is now a persistence-of-halt issue, not a diagnostic one.

**Secondary bottleneck (relevant once service restarts):** All band paths require disp_ratio7 ≥ 1.10 before live re-enable. Last reading was 0.781 on 07-26, having been sub-threshold for 37+ consecutive days with all 3 geographic regions sub-1.0. This condition is not self-correcting and must be freshly measured on restart.

---

## 2. Existing System Optimization

No optimizations can be applied while system is halted. The four reports collectively imply:

| Potential Optimization | Expected Delta | Confidence | Effort | Blocking Condition |
|---|---|---|---|---|
| Service restart (shadow-only) | Unfreeze gate accumulation, refresh disp_ratio | HIGH | Low (SSH + systemctl) | Owner SSH action |
| Isotonic refit (candidate from 07-23 is ready) | Brier calibration improvement; 2 material tail diffs | HIGH (already computed) | Low (run deploy script) | Needs live system to deploy |
| band_struct_lite creation | Unblocks canonical G1/G2/G7 validator | HIGH | Medium (new file format) | Needs service running |
| Maker rebate verification ($3.917 upper bound) | $0–$3.92 recovered capital, immediate | MEDIUM | Low (Polymarket wallet check) | None — purely manual |

The last item (maker rebate check) is the only action available **right now without SSH**. Do it today.

---

## 3. Gate Pipeline Review

From gatekeeper_report.md (2026-08-09):

| Gate | n | Status | Nearest path to READY | ETA |
|---|---|---|---|---|
| G1 BAND_YES | null (frozen) | COLLECTING | Restart service → re-enable BAND_LIVE → 100+ band fires | ∞ |
| G2 BAND_NO + PAIR_FAV | null (frozen) | COLLECTING | Restart + re-enable BAND_NO_ENABLED (WR 39.2%, n=51 was kill-level) | ∞ |
| G3 FILLED-vs-FIRED | null (frozen) | COLLECTING | Restart + any fills | ∞ |
| G4 BASKET EXIT | null (frozen) | COLLECTING | Restart + basket-exit shadow (33d dark) | ∞ |
| G5 THERMO | null (frozen) | COLLECTING | Restart + thermo_maker (15d dark) | ∞ |
| G6 METAR LOCKOUT | null (frozen) | COLLECTING | Restart + metar_lockout (15d dark) | ∞ |
| G7 SUM-POSTED | null (frozen) | COLLECTING | Restart + band_struct (15d dark) | ∞ |

**No gate is near READY.** All shadow data files are dark. The structure is sound — none of these gates have been falsified — but zero accumulation is possible while the service is down.

**Structural gap identified:** `band_struct_lite.jsonl` has **never existed** in the data-mirror shadow directory. This is the source file for the canonical G1/G2/G7 validator (`analysis/weather/band_resolution_join.py`). Even after service restart, this file needs to be created and populated before G1/G2/G7 can run properly.

**To accelerate accumulation WITHOUT degrading expectancy:** restart in shadow-only mode (no BAND_LIVE=True yet), let all shadow loggers run for 7+ days, assess disp_ratio fresh, then make BAND_LIVE decision from a data-backed position rather than from a 37-day-stale reading.

---

## 4. Assumption Attack

The three load-bearing assumptions of the band system, against today's data:

### Assumption 1: Dispersion premium persists
**Status: THREATENED**

disp_ratio7 = 0.781 (last measured 2026-07-26, carried for 16 days).
- Sub-threshold (< 1.10) for at least 37 consecutive days (estimated from S3 alert history)
- All 3 geographic regions sub-1.0 simultaneously as of 2026-07-24 (Asia collapsed 1.215 → 0.743)
- This is NOT normal short-term noise. 37 days constitutes a regime signal.
- **Threat:** The band system's edge is derived from dispersion > 1.0 between model forecasts and market odds. If dispersion has genuinely inverted and sustained, the entire YES-band and NO-band entry logic has no edge. This is the highest-confidence risk in the system today.

### Assumption 2: Fills are not adversely selected
**Status: UNKNOWN — no new data**

Last trades.jsonl entry: 2026-07-19 (21 days old). Last fill: predates the dispersion inversion signal being S3-level. The markout/winner's-curse analysis from exec_audit is blank (no fills). Cannot assess.

**Threat level:** UNKNOWN. The prior concern was that limit order flow might be adversely selected (we post, better-informed takers hit us). With 0 fills, this cannot be measured. Not confirmed threatening, but not confirmed healthy either.

### Assumption 3: Recycle velocity scales
**Status: UNKNOWN — no active positions**

RECYCLE099 requires active positions cycling through the system. Capital locked = 0. There is no evidence for or against recycle velocity because the system has not been trading.

**Threat level:** LOW (cannot be threatened if not deployed). The mechanism is sound in design. Risk is whether there are enough markets per unit time when trading resumes.

---

## 5. Market Intelligence [0]: Competitor Posture

*(Day 2026-08-09, month-day 9 mod 3 = 0 → competitor posture)*

**badatmath_watch:** Running live as of 2026-08-09T09:10Z (confirmed by gatekeeper). Data available in shadow_summary.json on data-mirror but not readable from git (binary/non-tracked format). The watch monitor is current. Specific deltas vs. last recorded state_log cannot be extracted from git alone — requires live VPS read.

**Leaderboard wallet teardown:** Not possible this session without API access. Data-mirror shadow files (maker_flow, updown_sniper) are running, but their content is not in the git object store.

**State-log carry-forward (from 2026-07-26 EVOLVE context):** Prior research noted 170+ active Polymarket bots; top-tier bots in the $4M+/yr category are not competing in the weather market vertical (different product). Our weather-market competitive moat (Kalman/STWA 51-city model) remains structurally intact — but zero value while service is down.

**Delta vs. prior state_log:** No new intelligence this session. Monitor is live but contents inaccessible from this agent's read path.

---

## 6. Three Experiments

### Experiment A — Shadow restart (no capital risk)
**Hypothesis:** Restarting klausbot in shadow-mode (BAND_LIVE=False maintained, service running) would restart band_struct.jsonl, thermo_maker.jsonl, and metar_lockout.jsonl shadow loggers within 2 hours, unfreezing gates G1–G7 and allowing 7-day accumulation without any capital exposure.
- **Data needed:** system_status.txt showing `active` after restart
- **Time:** 1 hour (SSH + systemctl start + verify)
- **Cost:** $0 capital risk; ~$42 VPS time already sunk
- **Success metric:** band_struct.jsonl timestamp < 3h in data-mirror within 2h of restart
- **Decision if yes:** Proceed to 7-day shadow run, then make BAND_LIVE decision at end
- **Decision if no (service won't start):** Crash forensics required (crash loop, not just stale PID)

### Experiment B — Dispersion regime probe post-restart
**Hypothesis:** disp_ratio7 may have recovered during the 16-day outage. Weather prediction markets continue to trade; model accuracy may have recalibrated against actual outcomes. A fresh computation may show disp_ratio > 1.10.
- **Data needed:** 7 days of fresh band_struct.jsonl after service restart
- **Time:** 7 days after Experiment A succeeds
- **Cost:** $0 (shadow only)
- **Success metric:** disp_ratio7 ≥ 1.10 on fresh computation (all 3 regions above 1.0)
- **Decision if yes:** Candidate for BAND_LIVE re-enable; proceed to gate accumulation with small stake
- **Decision if no:** Band system has no edge in current regime; maintain BAND_LIVE=False, consider strategy pause until dispersion recovers

### Experiment C — Maker rebate verification
**Hypothesis:** $3.917 accumulated maker rebate upper bound has been sitting in the Polymarket wallet uncollected since 2026-07-06 (34 days). Verifying and claiming it would add up to $3.92 to working capital.
- **Data needed:** Polymarket wallet → pUSD balance check
- **Time:** 5 minutes (manual web check)
- **Cost:** $0
- **Success metric:** pUSD balance > $0 in Polymarket wallet
- **Decision if yes:** Withdraw to increase CLOB liquid capital from $21.50 by up to +18%
- **Decision if no:** Upper-bound estimate was incorrect; recalibrate expected rebate model

---

## 7. Single Best Action

**Verify maker rebate in Polymarket wallet (Experiment C) — do this today.**

This is the only action that requires no SSH, no risk, and can be done in 5 minutes. $3.917 upper bound: even 50% realization adds $1.95 to liquid CLOB capital immediately. More importantly, it establishes ground truth on the rebate model, which has been an open "TODO" for 34+ days.

**Then immediately after:** SSH to VPS → `systemctl start klausbot` — the gate accumulation clock has been at zero for 16 days. Every day without shadow data is a day of pure opportunity cost with no information gain. Shadow restart costs $0 and produces 7 days of fresh dispersion, calibration, and gate data that cannot be obtained any other way.

**Basis in specialist reports:**
- gatekeeper_report (09:14 UTC): confirms all gate shadow sources are dark; band_struct_lite never existed — structural repair needed
- exec_audit (07:13 UTC): confirms 0 fills, 0 open positions, SNAPSHOT fresh — VPS is responsive
- pnl_ledger_state: $3.917 rebate upper bound explicitly flagged as "exceeds $1 min accrual — user must verify pUSD receipt"

If gatekeeper had shown a gate at READY or REJECTED, promoting/killing it would be the default candidate. No gate has reached n>0. The prerequisite for any gate transition is service restart.

---

## PROPOSED ACTIONS (human review)

**No strategy code changes proposed. System is not running. State-altering recommendations:**

1. **[Immediate, 5 min, no SSH]** Check Polymarket wallet pUSD balance. Expected $0–$3.92 rebate accrued from pre-07-06 maker activity. If present, withdraw to CLOB.

2. **[Owner decision gate]** SSH to VPS → `sudo systemctl start klausbot`. Verify `system_status.txt` shows `active` within 15 minutes. Confirm service starts in shadow mode (BAND_LIVE remains False, no capital deployed). Check for crash-loop in `journalctl -u klausbot -n 50` before restarting if prior restarts failed.

3. **[After shadow restart, 7-day wait]** Run fresh disp_ratio7 computation from 7 days of new band_struct.jsonl. Do NOT re-enable BAND_LIVE until disp_ratio7 ≥ 1.10 with all 3 regions above 1.0.

4. **[Structural, medium effort]** Create `band_struct_lite.jsonl` file format in the shadow logger so canonical G1/G2/G7 validator can run. This is a permanent gap — file has never existed.

5. **[Post-restart]** Deploy isotonic refit candidate from 2026-07-23. Refit is ready; 2 material tail corrections identified (p_raw=0.95 +0.0552, p_raw=1.0 +0.1684). Deploy only after fresh OOS Brier confirms cal < raw on held-out data.

---

*Run: 2026-08-09T10:30Z | Stall count: 20 | Service down since: 2026-07-24T10:09Z (16 days) | Capital: $88.750373 (unchanged) | Active paths: NONE*
