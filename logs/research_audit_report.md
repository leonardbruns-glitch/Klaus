# Research Audit — 2026-07-31T1025Z — STALL day 8: systemd failed, 0 live paths, capital $0.41 below ruin floor | best action: VPS restart + NEG_RISK triage + $0.41 injection

**ABORT trigger**: `system_status.txt` shows `failed / unknown` — does not contain `'klaus systemd: active'`.  
**Snapshot**: 2026-07-31T10:19:16Z (fresh, < 1h — data mirror active despite service failure).  
**System dead**: 2026-07-24T10:09:19Z (owner-directed shutdown, ~166h / 7d down, day 8 of abort streak).  
**Loop mode**: WEEKLY-ONLY (daily + liveness timers owner-disabled 2026-07-24; EVOLVE 2026-07-26 `ddbcecdd1`).  
**Capital**: $88.750373 | **Ruin floor**: $89.16 | **Below floor by $0.41** — all band paths mechanically blocked.  
**Open positions**: 0 | **Fires since cut**: 0 | **PnL this week**: $0.00.

All four specialist reports ran today and reached ABORT/STALL. No new trading data exists since 2026-07-19 (sniper cut). Analysis is structural only — no fabrication.

---

## 1. PRIMARY BOTTLENECK — COMPOUNDING

**All three compounding levers are zero: ROI/turn = 0, turns/day = 0, equity deployed = 0.**

The binding constraint is not a parameter — it is the complete absence of eligible live paths:

| Stream | Status | Blocker |
|---|---|---|
| UPDOWN certainty-taker | STOP permanent | G8 KILLED 2026-07-26 (WR 95.3% < BE 96.51%, graveyard #15) |
| BAND YES maker | Dark day 25 | BAND_LIVE=False; dispersion inverted day 29; capital below ruin floor |
| BAND NO maker | Effectively REJECTED | Live n=51 WR 39.2% (G2a shadow ambiguous; live reality is rejected) |
| PAIR_FAV | Frozen | Band dark; n=9 each side (COLLECTING, accumulation halted) |
| NEG_RISK_ARB | Unknown | System down since 07-24; last known alive 07-23 21:54Z; ruin_floor status unclear |
| LDA | STOP | Rolling-20 worst −$36.39 < −$30 threshold |

The compounding equation cannot increase until the owner makes at minimum two decisions: (a) restart the VPS service, and (b) define which product stream, if any, is eligible to re-arm. No autonomous path exists.

Source: exec_audit_report.md (07:07 UTC, confirmed 0 fills), gatekeeper_report.md (09:15 UTC, 0 gate accumulation), pnl_ledger_report.md (23:37 prior day, $0 day 6 STALL).

---

## 2. EXISTING-SYSTEM OPTIMIZATION (exec + calib + gatekeeper + pnl)

No live execution to optimize. The four reports collectively imply:

| Item | Status | Expected Delta | Confidence | Effort |
|---|---|---|---|---|
| Capital injection $0.41 to clear ruin floor | Prerequisite for band paths | Unlocks mechanical band block | 100% (deterministic) | Minimal (owner action) |
| VPS restart (systemd) | Prerequisite for all accumulation | Resumes NEG_RISK + RECYCLE + shadow data | 100% (deterministic) | Low (SSH) |
| Isotonic refit deployment | S4 alert carried, deployed 55d stale | Reduces tail miscalibration (grid 1.0 diff +0.168) | OOS brier NOT better — do NOT deploy | Medium |
| Dispersion-based band re-enable | S3 alert day 29, ratio 0.781 | Cannot be triggered — edge INVERTED | Alert confirmed 29+ consecutive days; no path forward | N/A |

No actionable parameter changes possible while system is down. All items above require owner action or conditions outside system control.

---

## 3. GATE PIPELINE REVIEW (gatekeeper_report.md 09:15 UTC)

**0 gates newly READY or REJECTED this run. All counts frozen at 0 +24h accrual.** Nearest-to-READY assessment:

| Gate | n | Status / ETA |
|---|---|---|
| G2b PAIR_FAV_YES | 9 | COLLECTING — frozen (band dark day 25); ETA indeterminate |
| G2c PAIR_FAV_NO | 9 | COLLECTING — frozen; CF ROI +52.9% biased by winner's curse |
| G1 BAND_YES | 934 | AMBIGUOUS — G3 winner's curse (n=75, filled WR 17.3%) confirms ROI is ceiling, not expectancy |
| G7 SUM_POSTED | 382 | AMBIGUOUS — same G3 blocker; band dark |

What would accelerate accumulation without degrading expectancy: restart VPS for PAIR_FAV shadow data only. G1/G7 cannot accumulate validly until G3 winner's curse is resolved (requires live fills under adversely selected conditions). **No breadth expansion recommended** while winner's curse unresolved.

G8 UPDOWN_CROSSING: KILLED (graveyard #15). G5 THERMO_MAKER_NO: REJECTED. G6 M1_BETA_LOCKOUT: REJECTED. These verdicts are permanent absent explicit human override.

---

## 4. ASSUMPTION ATTACK — BAND SYSTEM TODAY

**Assumption A — Dispersion premium persists (market prices MORE implied spread than actually resolves):**  
**THREATENED — day 29 consecutive inversion.** disp_ratio7 = 0.781 (threshold > 1.10). All three regions below 1.0 (EU 0.789, Asia 0.743, US/Other 0.789). 0/6 days above threshold in last computed window (07-18..07-23). No fresh data since system went down 07-24. BAND_LIVE=False since 07-06 independently confirmed correct by this monitor. **No resumption case exists while ratio < 1.10 is sustained.** — *Source: calib_monitor_report.md S3 alert carried day 29.*

**Assumption B — Fills are not adversely selected:**  
**CONFIRMED VIOLATED — G3 winner's curse, decision-grade n=75.** Filled WR 17.3% vs sim join WR 7.6%. CI entirely negative [−75.0, −34.2]%. Same-era sim ROI +7.6% YES / +3.7% NO vs filled ROI −75.8%. The gap is per-cell. G1 ROI (+4.0%) and G7 ROI (+11.5%) are ceiling estimates only. Any band re-enable argument citing sim ROI is inadmissible. — *Source: gatekeeper_report.md G3 row, state_log 2026-07-11 22:15 UTC.*

**Assumption C — Recycle velocity scales:**  
**UNOBSERVABLE** — no data since 07-24 system halt. Last known state: RECYCLE alive 07-23 21:54Z, ruin_floor-blocked at $89.16. Cannot assess velocity without live data. The assumption is neither confirmed nor threatened — simply dark.

---

## 5. MARKET INTELLIGENCE — [1] Market Census (day mod 3 = 1)

Live Gamma scraping not possible (system down). Observable from shadow data only:

- **`flb_screener.jsonl` still writing**: mtime 2026-07-31T10:15:00Z, n=1,036,140 rows (639 MB). Last entry: WTI crude oil July high $100 market (`in_play: false`). This passive screener appears to run independently of the main service (separate process or cron). Weather and other binary markets are still being scanned live.
- **`hot/2026-07-21/` is the last active hot directory** (mtime ~23:59 on 07-21). No hot directories for 07-22 through 07-31 (main bot logging halted at UPDOWN_STOP 07-19, band_struct last active 07-21).
- **`badatmath_watch.jsonl`**: Data-mirror commit shows 10 rows added for 07-26..07-30. Competitor activity on weather markets is being passively tracked despite system downtime — this means badatmath is still posting fills to weather markets.
- **No census data on new cities or depth changes** without live Gamma scrapes. Cannot report deltas vs state_log knowledge.

Key delta: badatmath fills confirmed 07-26..07-30 → weather market structurally active despite our absence. The band opportunity may still exist at the market level even if our system is dark and dispersion edge is inverted.

---

## 6. EXPERIMENTS — 3 CHEAP, FAST, FALSIFIABLE

**E1 — Passive badatmath activity analysis (zero capital, system-off safe)**  
*Hypothesis*: badatmath is still posting fills to weather markets at ≥ 2/day rate → market is structurally active and worth resuming if dispersion recovers.  
*Data*: `data/shadow/badatmath_watch.jsonl` rows for 07-26..07-30 (10 rows per data-mirror commit). Parse fill_join vs ladder record type and fill rate.  
*Time*: 1h analyst session. *Cost*: $0.  
*Success metric*: ≥ 5 fill_join events in 5d → active. 0 fill_join → market dried up.  
*Decision-if-yes*: Weather market active → restart + $0.41 injection justified when dispersion recovers. *Decision-if-no*: Market death adds fourth structural blocker to band thesis.

**E2 — NEG_RISK_ARB survival check (first 15 min after VPS restart)**  
*Hypothesis*: NEG_RISK_ARB is alive and not ruin-floor-blocked; it is the only revenue path available now.  
*Data*: First 15 min of RECYCLE/NEG_RISK shadow log after `systemctl start klaus`.  
*Time*: 15 min runtime after restart. *Cost*: $0 (shadow only — no capital risk if ruin floor blocks live posting).  
*Success metric*: ≥ 3 NEG_RISK opportunities sighted → path alive. Zero → market structure changed.  
*Decision-if-yes*: NEG_RISK is the sole live revenue path; restart justified without capital injection. *Decision-if-no*: No revenue path; restart adds no value; document and leave stopped.

**E3 — Dispersion ratio 5-day recovery test (post-restart passive)**  
*Hypothesis*: The dispersion inversion (0.781, day 29) is Northern Hemisphere summer seasonal compression — actual high/low ranges narrow vs market expectations during peak summer. Expected recovery by late August.  
*Data*: disp_ratio daily for 5 calendar days post-restart (auto-computed by calib_monitor).  
*Time*: 5 calendar days. *Cost*: $0.  
*Success metric*: 3/5 days disp_ratio ≥ 1.10 → seasonal thesis supported. 0/5 ≥ 1.10 → structural model-market divergence.  
*Decision-if-yes*: Start BAND re-enable gate sequence with dispersion as primary criterion. *Decision-if-no*: Commission Kalman re-fit for changed summer regime.

---

## 7. SINGLE BEST ACTION

**SSH to VPS (45.85.251.173), start service, triage NEG_RISK_ARB in first 15 minutes.**

NEG_RISK_ARB is the only eligible revenue path that bypasses (a) dispersion inversion, (b) UPDOWN_STOP, (c) winner's curse on band, and (d) isotonic staleness. It is calibration-independent — it pays 1.0 from sum ≤ 1.0 regardless of model accuracy. It was alive as of 07-23 21:54Z. The gap in accumulation is 7 days; structural availability is unlikely to have changed if the neg-risk market structure on Polymarket is intact.

Concrete first step: `ssh 45.85.251.173` → `sudo systemctl start klaus` → `journalctl -u klaus -f` for 15 min — watch for RECYCLE/NEG_RISK events. If alive: this is the active path, restart is justified. If ruin-floor-blocked: inject $0.41 USDC, confirm floor clears, monitor for first fill. If zero sightings: market dried up, document and leave stopped pending strategy redesign.

*Sources*: gatekeeper_report.md §structural blockers (NEG_RISK only path not hard-rejected), exec_audit_report.md (all execution flags disabled confirming full halt), state_log 2026-07-23 22:08 UTC (last confirmed NEG_RISK alive), calib_monitor S3 (confirms dispersion-independent edge required).

---

## PROPOSED ACTIONS (human review)

1. **SSH VPS → `sudo systemctl start klaus` → NEG_RISK triage**: Sole autonomous revenue path. First action. (Owner)
2. **Inject $0.41 USDC**: Clears ruin floor mechanically; required before any band path engages. Cost trivial. (Owner)
3. **Owner path decision**: G8 dead (no updown), BAND dispersion inverted + winner's curse (no weather maker), G5/G6 rejected. If NEG_RISK is also dead, bot has no live edge. Owner must decide: inject capital + redesign, or document shutdown. (Owner decision)
4. **Do NOT deploy isotonic candidate**: OOS brier_cal ≥ brier_raw. No calibration benefit; 2 material tail diffs (grid 1.0: +0.168). Human review required before any promotion.
5. **No gate parameter changes**: All gates frozen. No new data. No promotions or kills warranted. G8 kill already executed.
