# Research Audit — 2026-07-26T1030Z

**⚠ STALL DAY 3 — `systemd: failed/unknown` since ~2026-07-24T10:09 UTC**

| Field | Value |
|---|---|
| Snapshot (UTC) | 2026-07-26T10:23:23Z — FRESH (< 1h) |
| System | **FAILED/UNKNOWN** (day 3; last active 2026-07-24T10:09:19 UTC) |
| Capital | $21.495442 (unchanged; zero burn; all paths disarmed) |
| BAND_LIVE | False (wind-down 2026-07-06, day 20 dark) |
| Open positions | 0 |
| G8 n-estimate | **≈105–127** (auth n=88 at 2026-07-23T22:05Z + ~59h × [7,16]/day) |
| disp_ratio7 | 0.781 (carried; S3 alert **day ~24**) |
| Zero-fill streak | Day 6+ |

**Specialist reports (all STALL, no new data this run):**

| Report | Timestamp | Status |
|---|---|---|
| exec_audit_report.md | 2026-07-26T07:13Z | ABORT — `fills=0`, `maker_fills_recent.log: 0 bytes` |
| calib_monitor_report.md | 2026-07-26T08:07Z | STALL — `brier7=0.055 disp_ratio=0.781 CARRIED`; S3 day ~24, S4 isotonic ~50d stale |
| gatekeeper_report.md | 2026-07-26T09:07Z | STALL — G8 n≈105–127, **KILL-LOCKED**; 6th consecutive stall |
| pnl_ledger_report.md | 2026-07-25T23:37Z | STALL day 2 — P&L $0.00, turns=0, ROI/turn=N/A |

All four sibling routines aborted on the same condition. This report synthesizes carried state only. No execution, calibration, fill, or P&L data is new since 2026-07-23.

---

## 1. Primary Bottleneck: Infrastructure Reliability

Ranking applied: equity deployed → turns/day → ROI/turn → fills → NO-parity → calibration → dispersion edge → risk frame → data → **reliability**.

**Reliability is currently first**, not last, because it zeroes every upstream dimension:

- Turns/day: **0** (bot dead; BAND_LIVE=False; UPDOWN_STOP active)
- Equity deployed: **$0** (all paths disarmed)
- ROI/turn: **N/A**
- Fills: **0** (6th consecutive zero-fill day)

The compounding rate is $0/day by construction. Nothing in sections 2–7 changes this — strategy optimization is moot until the service is restored AND a viable trading path exists. At $21.50 capital (24.1% of the $89.16 wind-down floor that triggered the EVOLVE halt), no band path may be re-activated on risk rules alone regardless of service state.

**Justification from reports**: exec_audit (07:13Z) — `"fabricating metrics on empty execution state is not permitted"`; gatekeeper (09:07Z) — `"Sixth consecutive stall (systemd failed since after 2026-07-24T10:09:19Z)"`; pnl_ledger (23:37Z) — `"P&L delta: $0.00. Unexplained: $0.00."`

---

## 2. Existing-System Optimization

With four stall reports and zero execution data, no optimization metrics are computable. Carried known-state only:

| Item | Current State | Expected Delta | Confidence | Effort |
|---|---|---|---|---|
| G8 kill-formalization | KILL-LOCKED, unconfirmed at n≥100 | Clears gate ledger; closes UPDOWN_CROSSING | High (kill math immutable; BE=96.49%, max achievable 96.0%) | 15 min SSH |
| Service restart | Dead day 3 | Unblocks G8 confirm + shadow data flow | Medium (crash cause unknown) | 1–2h SSH |
| Dispersion monitoring (passive) | S3 alert day 24, ratio=0.781 | Trajectory data for band re-enable decision | Ongoing | None |
| Winner's curse G3 | WATCH_ITEM n=75, CI all-negative | Hard block on G1/G7 re-enable; holds | High | None |

**No caps to loosen, no queue to tune, no stake to adjust.** BAND_DAILY_BUDGET, BAND_BASE_STAKE, BAND_CELL_WEIGHTS, queue priorities — all irrelevant while BAND_LIVE=False and capital is below BAND_PHASE2_CAPITAL ($600). Do not paper-optimize a live system that is not running.

---

## 3. Gate Pipeline Review

From gatekeeper_report (09:07Z, 6th consecutive stall). All gate data frozen at 2026-07-25T09:03Z:

| Gate | n (auth) | Status | Nearest action | Acceleration |
|---|---|---|---|---|
| G8 UPDOWN_CROSSING | 88 auth / **≈105–127 est** | **KILL-LOCKED** | Confirm n at SSH | `shadow_grade.py --refetch` today |
| G3 FILLED_vs_FIRED | 75 | WATCH_ITEM | Blocks G1/G7 re-enable | None (informational) |
| G5 THERMO_MAKER_NO | 125 | **REJECTED** | No reconsideration without human directive | N/A |
| G6 M1_BETA_LOCKOUT | 31 | **REJECTED** | No reconsideration without human directive | N/A |
| G1 BAND_YES | 934 | AMBIGUOUS | Band dark; G3 winner's curse hard-blocks | Requires equity recovery + dispersion recovery + G3 resolution |
| G2a BAND_NO | 51 live | Effectively REJECTED | Live WR=39.2% on live n=51; shadow n=115 AMBIGUOUS | Do not re-enable on shadow CI alone |
| G2b/c PAIR_FAV | 9 live | COLLECTING | Band dark; no new data | Inert while BAND_LIVE=False |
| G7 SUM_POSTED 0.70–0.85 | 382 | AMBIGUOUS | Band dark; G3 winner's curse blocker | Inert |

**Nearest READY gate: none.** The only gate requiring action is G8 — a KILL, not a promotion. Breadth expansion (more cities, more market types) is irrelevant while capital is $21.50 and BAND_LIVE=False. Accumulation breadth does not apply when zero data flows.

**G8 kill math (immutable):**
- BE: 96.49% (implied by updown market structure)
- Best-case at n=100: 96W/4L = 96.0% < BE
- Min-n-to-clear: **114** (requires zero further losses from n=88 — unrealistic given 4 losses already)
- Current estimate: n≈105–127; BTC cell already REJECTED at n=134
- Conclusion: kill is mathematically certain regardless of accrual rate

---

## 4. Assumption Attack

The three load-bearing assumptions of the band system, assessed against today's data:

### A. Dispersion premium persists (edge source)
**Status: THREATENED — S3 alert, day 24 of inversion**

`disp_ratio7 = 0.781` (carried from calib_monitor). This is the ratio of actual dispersion in Polymarket weather quotes vs the band's pricing model. A ratio >1.0 means the market disperses enough that our YES band captures a real premium. At 0.781, the market is tighter than our model expects — the presumed edge has not materialized for 24 consecutive days.

What today's data supports: calib_monitor (08:07Z) — `"S3 dispersion inversion day ~24, 0/6-above-1.10 ratio-declining."` Not a single sample in the last 6 above 1.10 (the robust threshold); the trend is declining, not mean-reverting.

What threatens it: if badatmath (mirror) has structurally tightened their bands in response to market compression, or if the underlying weather market has become more efficient (more participants, narrower spread), the dispersion premium may be permanently eroded, not cyclically depressed.

**Anti-sycophancy check**: 24 days of below-1.0 dispersion with a declining trend is not a "temporary regime." At day 30, if no recovery, this assumption requires structural reclassification.

### B. Fills are not adversely selected (winner's curse)
**Status: CONFIRMED THREAT — G3 WATCH_ITEM at n=75, CI entirely negative**

From gatekeeper (09:07Z): `"fill WR 17.3% vs sim WR 7.6%, gap −83.4pp. CI entirely negative."` Our GTC limit orders are preferentially filled when adverse movement follows. Simulated fire WR is 7.6%; actual fill WR is 17.3% but in the wrong direction — the filled subset wins at only 17.3% vs what the simulated population suggests.

This is a hard structural blocker. It means the band model's simulated edge (used to justify G1/G7 CI) may be entirely illusory once conditional on fill. Parameter tuning cannot fix adverse selection — it is a property of GTC limit order mechanics when quoted at predictable prices.

What today's data supports: G3 CI is `[−75.0, −34.2]` — entirely negative, n=75. This is not noise.

**Anti-sycophancy check**: Do not use simulation CI to argue for G1 or G7 re-enable. Gatekeeper states this explicitly. Any argument citing `sim_WR` or `band_struct` ROI without accounting for adverse selection is invalid.

### C. Recycle velocity scales (RECYCLE099 compounds ROI)
**Status: UNTESTABLE — band dark day 20**

`exit099_live.jsonl` has had zero data flow since BAND_LIVE=False (Jul-06). The recycle mechanism (re-quoting converging positions) was the primary ROI/turn multiplier in the BAND-V3 design. No live data exists to assess whether it saturates, scales, or has its own adverse selection.

What today's data supports: nothing — shadow logger is frozen along with the bot.

**Anti-sycophancy check**: The recycle edge is an untested hypothesis at any meaningful n. It was cited as a feature of the system before the wind-down. Its contribution to compounding is unknown.

---

## 5. Market Intelligence — Platform Mechanics (Day 26 mod 3 = 2)

*Direct platform access unavailable from this sandbox (no VPS, no live network to docs.polymarket.com). Reporting delta vs known state only.*

**Known state (no changes detected via available data):**
- Taker fee schedule: ~3.15% at 50% odds, ~0% at extremes — confirmed 2026-03-30, no state_log update since
- Maker rebates: 100% of taker fees redistributed to makers — no change flagged
- Liquidity-rewards program: no state_log entry documenting a change
- Weather market universe: 51 cities active per FLB screener (still running independently; 947k rows as of Jul-25T23:27Z per pnl_ledger)
- Updown market structure: 5-min and 15-min windows, Chainlink snapshot resolution — no change flagged
- Cloudflare WAF posture: unknown post-service-failure; QuantVPS Dublin + curl_cffi still required per prior research

**Gap**: Cannot detect fee restructure, new market products, maker-rebate threshold changes, or platform announcements without VPS SSH access to run live checks. FLB screener IS running and would surface new market slugs if new cities appeared — no alert in shadow_summary (size too large to read in full; no novel slug pattern flagged in recent commits).

**Platform mechanics status: NO KNOWN CHANGES — unverifiable from sandbox.**

---

## 6. Three Experiments

**E1 — Service crash triage (immediate, $0, high VoI)**
- **Hypothesis**: The systemd failure after 2026-07-24T10:09Z is a recoverable crash (OOM, disk-full, Python exception) not hardware failure.
- **Data**: `journalctl -u klaus.service --since '2026-07-24 10:00' -n 200` + `df -h` + `systemctl status`
- **Time**: 30 min SSH. Cost: $0.
- **Success metric**: Error message identifies a root cause resolvable in <1h; `systemctl start klaus` succeeds and holds for >30 min.
- **Decision if yes**: Restart, monitor, run E2 immediately.
- **Decision if no (hardware / unresolvable)**: Full infrastructure audit; assess QuantVPS instance health; consider new VPS spin-up. Capital $21.50 does not justify extended infrastructure spend — evaluate cost vs expected revenue.
- **Prior pattern**: Service crashed ~15 min after restart on Jul-24 (started 10:09Z, failed shortly after). Likely a startup-path exception (config load, import error, file-not-found) not a runtime crash — priority diagnosis target.

**E2 — G8 kill confirmation (15 min post-E1, $0, decisive)**
- **Hypothesis**: n ≥ 100 authenticated UPDOWN_CROSSING events confirm; WR still below BE 96.49%; kill is formal.
- **Data**: `python3 analysis/crypto/shadow_grade.py --refetch` on VPS after service stabilizes.
- **Time**: 15 min. Cost: $0.
- **Success metric**: Script outputs n ≥ 100 and WR < 96.49%.
- **Decision if yes (n≥100, WR<BE)**: Close UPDOWN_CROSSING class permanently. Set gate status = REJECTED in gate ledger. Do not re-enable without fresh pre-registration, different market cohort, and human directive. Remove UPDOWN_STOP flag only after kill is logged.
- **Decision if no (n<100 — unlikely)**: Continue collecting; re-run at next session.
- **Decision if no (WR≥BE somehow)**: Do not close; report as anomaly; re-examine candidate cohort contamination.

**E3 — Dispersion recovery trajectory (14-day passive, $0, high long-run VoI)**
- **Hypothesis**: disp_ratio=0.781 (S3 alert day 24) is a transient regime that recovers above 1.0 within 14 days (by 2026-08-09), not a structural band-edge collapse.
- **Data**: Daily calib_monitor disp_ratio reading over 14 samples. FLB screener runs independently of bot service; band_struct logger requires bot restart (E1 prerequisite for richer data).
- **Time**: 14 days of monitoring. Cost: $0 cash; requires E1 bot restart for full logger data.
- **Success metric**: disp_ratio ≥ 1.0 sustained ≥ 5 consecutive days within the 14-day window.
- **Decision if yes**: Band YES re-enable conditions include dispersion recovery as a prerequisite — this gates re-assessment.
- **Decision if no (ratio stays <1.0 at day 38, approximately 2026-08-09)**: Formally reclassify band YES/NO edge hypothesis as structurally broken. Archive BAND_LIVE path. Do not re-enable. Pivot evaluation to maker-rebate-only strategy or strategy discontinuation.

---

## 7. Single Best Action

**SSH to VPS today: diagnose service failure, restart, run `shadow_grade.py` to confirm G8 kill.**

*Justification from specialist reports*: Gatekeeper (09:07Z) — `"G8 n=100 LIKELY CROSSED. shadow_grade.py required to confirm. Kill math immutable. KILL-LOCKED."` PnL ledger (23:37Z Jul-25) — `"SSH to VPS. Diagnose systemd failure."` Exec audit (07:13Z) — ABORT due to dead service. All four reports converge on the same single action.

**Concrete first step**:
```bash
journalctl -u klaus.service --since '2026-07-24 10:00' -n 200 --no-pager
df -h
systemctl start klaus.service && sleep 120 && systemctl status klaus.service
# After stable:
python3 analysis/crypto/shadow_grade.py --refetch
```

**Why not something else**:
- No band path to re-enable (equity $21.50 < all capital floors, dispersion inverted, winner's curse confirmed)
- No gate to promote (all non-G8 gates are AMBIGUOUS/REJECTED/COLLECTING with band dark)
- No capital at risk from current downtime
- No strategy change warranted (insufficient evidence; existing data anti-thesis of re-activation)

The single productive outcome from today's session is a formalized G8 kill. Compounding impact = clarified gate ledger + closed path; P(success) = high (kill math immutable); effort = one SSH session.

---

## PROPOSED ACTIONS (human review)

1. **SSH VPS TODAY** — diagnose `systemd` failure (`journalctl -u klaus -n 200`). Check disk (`df -h`). Restart if recoverable. Crash pattern: failed ~15 min after Jul-24T10:09 restart suggests startup-path exception.

2. **G8 KILL** — after service restart, run `python3 analysis/crypto/shadow_grade.py --refetch`. If n≥100 and WR<96.49%: formally CLOSE UPDOWN_CROSSING class; set gate REJECTED; log in state_log; remove UPDOWN_STOP kill file. No re-enable without human directive and fresh cohort.

3. **No capital deployment** — equity $21.495 is 24.1% of the $89.16 wind-down floor. No band path activatable on risk rules alone. Do not lift BAND_LIVE on strategy grounds while below floor.

4. **Dispersion watch gate** — if disp_ratio does not recover above 1.0 by approximately 2026-08-09 (day 38 of S3 alert), formally archive band YES/NO edge hypothesis. Do not let "it might recover" defer the structural determination indefinitely.

5. **Winner's curse (G3) is a hard block** — do not re-open G1 or G7 on simulation CI arguments. n=75, CI entirely negative. Any argument that ignores G3 is invalid.

6. **pUSD rebate verify** (same SSH session) — cumulative estimated $3.917 from pre-Jul-6 maker fills. At $21.50 equity this is 18% immediate capital recovery if present. Check Polymarket wallet for pUSD balance.

---

## Delta vs Prior Audit (2026-07-25T1019Z)

| Dimension | Yesterday | Today | Change |
|---|---|---|---|
| Service state | `failed` day 2 | `failed` **day 3** | Escalated — no auto-recovery |
| G8 n-estimate | 95–111 (est) | **105–127 (est)** | +10 upper/lower; kill more certain |
| disp_ratio S3 | Day ~23 | **Day ~24** | +1 inversion day; no recovery signal |
| Capital | $21.495442 | $21.495442 | Unchanged |
| Specialist reports | All STALL (day 2) | All STALL **(day 3)** | Degraded observability continues |
| G3 winner's curse | WATCH_ITEM n=75 | WATCH_ITEM n=75 | No change (band dark, no new fills) |

---

*Research audit is REPORT-ONLY. No strategy code or gate flags were modified.*  
*Run: 2026-07-26T10:30Z | Snapshot: 2026-07-26T10:23:23Z (fresh) | System: failed/unknown (day 3)*  
*Prior full audit: 2026-07-24T10:28Z | Specialist reports: exec=STALL, calib=STALL (0.781 carried), gatekeeper=STALL (G8 KILL n≈105-127), pnl=STALL day 2*
