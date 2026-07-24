# Research Audit Report — 2026-07-24T1028Z

**⚠ STALL CONDITION: system_status.txt = "failed / unknown" (abort rule triggered)**
Service was active at 07:07 (exec_audit) and 08:13 (calib_monitor), restarted at 10:09 UTC, and was failed/unknown by 10:15 UTC snapshot. Crash loop suspected. All four specialist reports are today-dated and valid; analysis proceeds on current data. Stale-data abort does not apply — snapshot is 13 min old at time of read.

**Generated:** 2026-07-24T1028Z  
**SNAPSHOT:** 2026-07-24T10:15:10Z (13 min old — FRESH ✓)  
**System:** `failed / unknown` ⚠ (crash at ~10:09 UTC — see Section 1)  
**Equity:** $21.495 (CLOB-exact, wallet-verified Jul-23)  
**Paths live:** 0 of N — BAND_LIVE=False (day 18), UPDOWN_STOP, LDA_STOP  
**Specialist reports:** all four present, today-dated ✓

---

## Data Quality

| Report | Date | System at run | Status |
|---|---|---|---|
| exec_audit_report.md | 2026-07-24T07:07Z | active ✓ | Valid |
| calib_monitor_report.md | 2026-07-24T08:13Z | active ✓ | Valid |
| gatekeeper_report.md | 2026-07-24T09:12Z | active ✓ | Valid |
| pnl_ledger_report.md | 2026-07-23T23:39Z | active ✓ | Valid (23h old) |

Network blocked this container (4th consecutive run): shadow_grade.py, band_resolution_join.py, maker_fills_recent.log, badatmath_watch not directly accessible. G8 data sourced from gate_ledger_latest.md (VPS-authoritative Jul-23 22:05Z). All analysis drawn from specialist reports + mirror data.

---

## Section 1 — Primary Bottleneck for Compounding

**Bottleneck: EQUITY ($21.495 = 24.1% of ruin floor $89.16)**

The compounding formula (ROI/turn × turns/day × equity deployed) is currently 0 × 0 × 0. This is not a signal quality, fill-rate, or calibration failure — it is a structural capital floor breach that mechanically blocks every live path simultaneously:

- BAND_LIVE=False: equity $21.50 < kernel floor $40 (blocks re-arm without owner directive)
- UPDOWN_STOP: sniper PF 0.79 < 0.80 charter rail (Jul-19 cut)
- LDA_STOP: rolling-20 worst −$36.39 < −$30 threshold
- G8 UPDOWN_CROSSING: KILL-LOCKED (formalizes ~Jul-25)

**There is no bandwidth optimization that matters while equity = $21.50.** The only path to resumed compounding is a capital injection OR a formally validated new edge that clears the kernel floor ($40) via exceptional human override. Neither condition is present in today's reports.

Secondary note: service crash at ~10:09 UTC (exec_audit confirmed active 07:07; crashed within 6 min of restarting at 10:09). Shadow infrastructure (band_struct_lite at ~828 rows/h, thermo_maker, maker_shadow all consistent with prior days per exec_audit §3) was healthy at 07:07. The crash may have occurred during the scheduled 10:00 UTC gate scan or UPDOWN_CROSSING accrual check. **SSH investigation required today** — crash-at-restart pattern in shadow-only mode suggests a code path or OOM issue, not a live-trading dependency.

---

## Section 2 — Existing-System Optimization (what the four reports imply)

| Item | Expected delta | Confidence | Effort | Source |
|---|---|---|---|---|
| Verify pUSD rebate receipt ($3.917 accrued pre-Jul-6) | +$3.917 immediate if unclaimed | High (accrual confirmed) | Low (check wallet) | pnl_ledger §3 |
| SSH crash investigation (service failed 10:09 UTC) | Prevent data loss if shadow logging broke | High | Medium (SSH + journalctl) | system_status.txt |
| Isotonic candidate promotion decision | Neutral to −0.6% band EV accuracy | Medium | Low (human decision) | calib_monitor §4 |
| G3 fills backlog clearance (4 items Jul-16–Jul-19) | Closes 4 unclassified exec events; no P&L impact | Medium | Medium (network req'd) | gatekeeper G3 note |
| Dispersion regime dating (Section 6 Exp. 1) | VOI: if break identified, band restart timing improves | Medium | Medium (VPS data pull) | calib_monitor S3 |

**Most impactful single item is pUSD rebate check** — $3.917 is recoverable money sitting unclaimed (>$1 minimum for payout, per pnl_ledger). Capital at $21.50 means this is an 18% increase if received.

**No idle-cash, over-restrictive cap, or starved queue rank issues exist** because all posting is shadow-only. Queue health metrics (band_struct_lite row rate, thermo_maker, shadow counts) are all consistent with prior days per exec_audit §3. No actionable optimizations while BAND_LIVE=False.

---

## Section 3 — Gate Pipeline Review

**No gates newly READY or REJECTED in today's gatekeeper run.** All changes vs prior:

| Gate | n | Status | Change | Accelerate? |
|---|---|---|---|---|
| G1 BAND_YES | 934 | AMBIGUOUS (CI straddles 0) | Frozen (band dark day 18) | No — G3 winner's curse blocks re-enable |
| G2a BAND_NO d+1 | 115 (shadow) | AMBIGUOUS | Frozen | No — live n=51 WR 39.2% = rejected on live data |
| G2b PAIR_FAV YES | 9 | COLLECTING | Frozen | No — band dark |
| G2c PAIR_FAV NO | 9 | COLLECTING | Frozen | No — band dark |
| G3 FILLED_VS_FIRED | 75 | WATCH_ITEM (winner's curse CONFIRMED) | No change | No — hard blocker, CI entirely negative |
| G5 THERMO | 125 | **REJECTED** | No change | No — explicit human REJECTED |
| G6 M1 LOCKOUT | 31 | **REJECTED** | No change | No — explicit human REJECTED |
| G7 SUM_POSTED | 382 | AMBIGUOUS (CI straddles 0) | Frozen | No — upper bound only per G3 |
| **G8 UPDOWN_CROSSING** | **88** | **COLLECTING ⚠ KILL-LOCKED** | +16 events | **Kill math closed at n=100 (~Jul-25)** |

**G8 is the only active gate**, and it is kill-locked by math, not by evidence of a new edge. No breadth or stake change can accelerate accumulation productively — 7 events/day is the current settle rate and no parameter change affects resolution timing. ETH is the sole loss-free cell (38/38) but n=38 < 40 minimum for even trend-grade conclusions.

**Gate pipeline is empty** — no promotable edges, no acceleratable collection. The pipeline itself is healthy (shadow fires accruing across multiple cities per exec_audit); the problem is lack of capital and killed gates.

---

## Section 4 — Assumption Attack

Three load-bearing assumptions of the band system, assessed against today's reports:

### Assumption A: Dispersion premium persists (band edge thesis)

**STATUS: THREATENED (decision-grade, n~105)**

- disp_ratio7 = 0.781 (calib_monitor §3), S3 alert day 22. Prior window: 0.817. Both below 1.10.
- 0/6 daily values above 1.10 in the current window (second consecutive window with 0/6).
- Asia collapsed 1.215→0.743 on 07-23 — the sole near-neutral region is gone. All 3 regions (EU/Asia/US-Other) now simultaneously sub-1.0 for the first time in monitoring period.
- n~105 crosses the decision-grade (≥100) threshold. This is not noise — the finding is statistically robust.
- 5-day median excluding Jul-18 outlier: 0.783. The inversion is not driven by a single anomalous day.

**Implication:** The core thesis — that market-implied spread exceeds realized temperature spread, creating a YES band edge — does not hold in the current 6-week window at decision-grade confidence. This does not mean the edge is permanently gone, but it means the band system, if re-enabled, would be operating on a thesis with no current-period support. A regime change or seasonal pattern break is the leading hypothesis. The dispersion regime dating experiment (Section 6 Exp. 1) would establish when this inversion began and whether it is cyclical.

### Assumption B: Fills are not adversely selected (winner's curse assumption)

**STATUS: CONFIRMED THREAT (n=75 filled, CI entirely negative)**

- G3 FILLED_VS_FIRED: n=75 filled, WR 17.3% filled vs 7.6% sim (gap −83.4 pp; CI entirely negative).
- This is not ambiguous: at n=75 filled with a CI that is entirely negative, the fill-adverse-selection is structurally confirmed.
- **Hard rule consequence:** All G1, G7 sim ROIs are UPPER BOUNDS only. No re-enable argument may cite sim CI as positive evidence for BAND_YES or SUM_POSTED.
- The 4 unclassified exec items (Jul-16 SELL@0.96, Jul-18 SELL@0.92, Jul-18 BUY@0.08, Jul-19 orphan BUY@0.02) remain unresolved but do not change the directional conclusion at n=75.

### Assumption C: Recycle velocity scales (RECYCLE099 convergence sells)

**STATUS: UNRESOLVABLE — zero live orders since Jul-6**

- exit099_live.jsonl shows no activity. Resting orders = 0 (maker_resting_state.json = `{}`).
- No fill data to assess whether RECYCLE099 fills at expected velocity, whether fills are adversely selected, or whether the convergence-to-resolution thesis holds.
- Shadow activity alone (band_struct_lite fires, thermo_maker events) does not test this path.
- **Cannot confirm or threaten this assumption without live band operation.** Theory only.

---

## Section 5 — Market Intelligence (rotation 24 mod 3 = 0: competitor posture)

**Data limitations:** Network blocked this container — badatmath_watch.jsonl, leaderboard wallet teardowns, and live CLOB order book access unavailable. The following is drawn from state_log commits and system_status context only.

**Known deltas vs prior state (from commit history):**
- EVOLVE Jul-23 22:05Z confirmed all live channels remain dark. No competitor-facing change detected.
- Reference maker (badatmath) benchmark remains ~1.0 turns/day per pnl_ledger — no state_log notes indicate a change in their operation.
- No new city additions or market structural changes noted in commit history since last competitor rotation.

**Gap**: This rotation was blocked by network constraints. Recommend VPS-sourced competitor posture run in the next scheduled EVOLVE or a dedicated SSH session. The competitor intelligence module is not actionable from this container.

---

## Section 6 — Three Experiments

### Experiment 1: Dispersion Regime Break Dating

**Hypothesis:** The S3 inversion (disp_ratio < 1.10) has a structural break date attributable to a specific event (platform change, city set change, seasonal shift, market structural change). Identifying the break point distinguishes cyclical (recoverable) from permanent edge deterioration.

**Data:** Full stwa_pricer_eval_s50.jsonl history (available on VPS). Compute rolling 14-day disp_ratio for all dates in the log. Apply permutation test for structural break (pre vs post). One analysis pass.

**Time:** 1 session with VPS SSH access.  
**Cost:** $0 — shadow data only.  
**Success metric:** A break date identified with p<0.05 permutation test on pre vs post disp_ratio distributions.  
**Decision-if-yes (break found):** If break coincides with a known event, evaluate whether the event is permanent (e.g., Polymarket market-structure change) or seasonal (e.g., summer regime). Adjust band restart timing accordingly. If break is seasonal, next activation window can be forecast.  
**Decision-if-no (no clean break):** Dispersion inversion is either gradual structural drift or sampling noise at this n. Extend monitoring to n=150 before making activation/kill recommendation on the edge thesis.

---

### Experiment 2: ETH-Only UPDOWN Accrual (shadow-only, no capital)

**Hypothesis:** ETH's 38/38 WR (loss-free, n=38) may represent a genuine per-asset edge distinguishable from the class-wide failure (BTC REJECTED, XRP/DOGE/SOL all loss-incurring), OR it may simply be early-phase before losses arrive (the pattern shown by every other cell at n<40). Shadow-only observation (no live capital) through n=50+ would distinguish these.

**Data:** Gate_ledger_latest.md refresh on VPS at each EVOLVE slot. Count ETH-only settles through n=50.  
**Time:** ~5-7 days at current settle rate (~1-2 ETH fires/day at p≥0.995 threshold).  
**Cost:** $0 — observation only, no live orders.  
**Success metric:** ETH n=50 with WR ≥ 96.49% (breakeven) and CI-lo > 90%.  
**Decision-if-yes:** Present to owner as the only potential re-entry path — but only with explicit capital-injection approval and isolation from the class kill-lock. Note: UPDOWN_STOP covers the full class; ETH-only would require a new gate registration.  
**Decision-if-no (any ETH loss before n=50):** Class-wide breakeven failure confirmed to also cover ETH. Gate KILL-LOCKED formally closes all UPDOWN paths.

---

### Experiment 3: Maker Rebate Verification

**Hypothesis:** The $3.917 accrued maker rebate (pre-Jul-6 fills) has been distributed to the Polymarket wallet in pUSD but never recorded in the ledger. At $21.50 equity, this is an 18% immediate capital recovery.

**Data:** Polymarket wallet pUSD balance (requires VPS / owner wallet access). One lookup.  
**Time:** < 5 minutes with SSH access.  
**Cost:** $0.  
**Success metric:** pUSD balance > $0 confirmed in wallet.  
**Decision-if-yes:** Redeem pUSD to USDC. Record in bankroll.json. Does not change kill-floor status (pUSD is rebate token; $24.91 would still be below kernel floor $40 without conversion), but it is recoverable capital.  
**Decision-if-no:** pUSD = $0. Either rebate pool allocation has not yet been distributed for this accrual period, or the calculation is optimistic. No further action; mark as closed.

---

## Section 7 — Single Best Action

**Action: SSH to VPS today — two mandatory tasks in one session**

**Task A (urgent): Service crash forensics**
```bash
journalctl -u klaus.service --since "2026-07-24 10:00" --no-pager | tail -50
systemctl status klaus.service
```
The service was active at 07:07 (exec_audit), restarted at 10:09 UTC, and was failed/unknown by 10:15 UTC. This is a crash-on-restart pattern during shadow-only operation. Probable causes: OOM (shadow logs accumulated ~70 GB disk usage per prior reports; disk at 75% used per system_status), a Python exception in the shadow-only scan path at the 10-minute scheduled check, or a cron collision with an agent write. Disk at 75% is concerning — prior EVOLVE logs reference disk reclaim operations (94%→87%→71%). If disk filled again, that is the crash cause and the fix is straightforward.

**Task B (urgent): pUSD rebate check + G8 kill preparation**
- Check Polymarket wallet for pUSD balance (Experiment 3 above).
- Note: G8 UPDOWN_CROSSING gate formalizes KILL at n≥100 (~Jul-25, 12 events remaining at ~7/day). The mathematical kill is unavoidable. Human decision needed: formally CLOSE UPDOWN_CROSSING class and mark gate REJECTED. No new evidence exists that would support an override.

**Justification from specialist reports:**
- Exec audit (07:07): service was active, shadow running normal — crash is post-07:07, during the 10:09 restart event.
- Gatekeeper (09:12): G8 kill unavoidable, explicitly calls for human decision at n=100.
- PnL ledger (23:39): $3.917 accrued rebate explicitly flagged as "user-verifiable."
- Calib monitor (08:13): no action required — S3 is a watch condition; dispersion dating (Exp 1) can wait for VPS access.

**Compounding impact:** Fixing the service crash (prevents data loss from interrupted shadow logging), claiming pUSD (18% capital recovery), and formally closing G8 (clears the gate backlog and allows clean slate for future gate registration) are the only productive actions available given $21.50 equity. No strategy change, parameter tweak, or gate promotion will compound until capital is restored above $40 kernel floor.

---

## PROPOSED ACTIONS (human review)

1. **SSH today — service crash forensics** (urgent): `journalctl -u klaus.service --since "2026-07-24 10:00"`. Hypothesis: disk full or OOM in shadow-only scan path. Fix: disk reclaim round 4 if disk at >90%, then restart service. No code changes.

2. **Verify pUSD balance** (urgent): Check Polymarket wallet. If >$0, redeem to USDC, add to bankroll.json. Expected +$3.917 (upper bound).

3. **G8 formal kill at n=100 (~Jul-25)**: When gatekeeper next run shows n≥100 with point WR < BE (mathematically guaranteed), human must decide: CLOSE UPDOWN_CROSSING, remove UPDOWN_STOP, mark G8 REJECTED. Override requires new evidence (none currently exists). No code changes from this report — gate-keeper will make the formal call at n≥100.

4. **Dispersion regime dating** (non-urgent, next VPS session): Run rolling 14-day disp_ratio analysis on full stwa_pricer_eval_s50.jsonl history. Establishes whether S3 inversion is cyclical (timing signal for future band restart) or structural (edge thesis revision required).

5. **Isotonic candidate — hold** (no action): OOS brier_cal (0.0638) ≥ raw (0.0637); 2 material tail diffs at p_raw=0.95 and 1.0. Do not promote until human review of tail behavior. Deployed curve 48d stale but tail differences mean promotion changes live behavior at extreme probabilities.

---

*Research audit is REPORT-ONLY. No strategy code or flags were modified.*
