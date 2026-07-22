# Klaus Research Audit — 2026-07-22

**Run UTC**: 2026-07-22T10:45Z  
**Snapshot**: 2026-07-22T10:18:46Z (age: ~27 min) ✓ VALID  
**System**: `klaus systemd: active` ✓  
**Capital**: $21.495442 (bankroll.json, last_utc_day=20656, saved 10:00Z)  
**Band dark**: day 16 (BAND_LIVE=False since 2026-07-06)  
**UPDOWN_STOP**: active (since 2026-07-19T11:26Z, day 3)  
**LDA**: STOP (rolling-20 worst = -$36.39 < -$30 threshold)  
**Open positions**: 0 tracked (3 untracked STWA positions pending — see §2)  
**Total PnL**: -$75.397 (cumulative, bankroll.json)  
**Specialist reports read**: exec_audit 07:07Z ✓ | calib_monitor 08:10Z ✓ | gatekeeper 09:07Z ✓ | pnl_ledger 23:37Z Jul-21 ✓  

---

## 1. PRIMARY BOTTLENECK FOR COMPOUNDING

**Equity deployed: $0.00 of $21.50 available.**

The compounding formula (ROI/turn × turns/day × equity deployed) has its rightmost factor zeroed by policy. Nothing downstream matters. Per exec_audit §6: turns/day=0.0, resting $=0, fills_7d=$0. Per gatekeeper FLAG-4: all four active revenue paths (UPDOWN sniper, BAND, LDA, THERMO/M1) are simultaneously halted. Per pnl_ledger §2: deployed fraction via STWA untracked positions = 40.4% ($14.58 cost/$36.07 equity estimate) — but these positions are overdue for resolution (Jul-20 horizon) and unconfirmed; the bot is blind to them.

The bind is bilateral:
1. **Charter kernel floor** ($40): Capital at $21.50 is 46.2% below the minimum re-arm threshold. Owner approval required for any path re-enable even if a gate passes.
2. **All gate paths blocked**: G8 (the only collecting re-enable gate) cannot pass at n=100 (see §3). BAND_LIVE trigger requires 2/5 days disp_ratio ≥ 1.10 — not seen in 20 consecutive days (see §4). LDA net -$36.39 vs -$30 floor.

No amount of parameter-tuning or gate-accelerating changes this: **zero compounding is occurring and will continue until the capital floor and at least one gate are resolved.** The correct output for today is operational triage, not strategy expansion.

---

## 2. EXISTING-SYSTEM OPTIMIZATION

With BAND_LIVE=False and capital below all charter floors, the standard optimization levers (cap adjustments, queue thresholds, stake sizing) are inert. Three structural items emerge from the four reports:

### 2a. DISK — SAME-WEEK SERVICE THREAT [URGENT]

| Metric | Value | Source |
|---|---|---|
| Disk free (10:18Z Jul-22) | **7 GB** | system_status.txt |
| Disk free (23:37Z Jul-21) | 8.4 GB | pnl_ledger §4 |
| Delta | -1.4 GB in 10.7h | computed |
| Burn rate (observed) | **3.1 GB/day** | computed (vs prior 1.94 GB/day estimate) |
| Time to crash at current rate | **~2.3 days (~Jul-24 16:00 UTC)** | extrapolation |

The pnl_ledger estimated +2%/day. Observed rate (+1.4 GB/10.7h) is **~60% faster** than that estimate. Primary consumers identified by pnl_ledger: shadow snap files (snap_20260721.jsonl = 75 MB, snap_20260720 = 78 MB) and rolling shadow logger jsonl files. The shadow engine is active and writing continuously (exec_audit §3: band_struct_lite entries every ~300s).

**If disk fills, Klaus crashes, G8 accumulation stops, and the null trading period extends indefinitely.** This is the only thing that can make the current situation actively worse without any trading exposure.

*Expected delta*: Deleting shadow files >7d and snap files >2d should free 5–15 GB, extending safe runway by 1.5–5 weeks. **Confidence: high. Effort: trivial (two shell commands).**

### 2b. STWA POSITION RESOLUTION — CAPITAL UNCERTAINTY [HIGH VALUE]

Three STWA positions entered Jul-17/18/19 are past their resolution horizons (all d+1 to d+3 = Jul-20) but show as "unresolved" in the Jul-21 23:37Z ledger. Bankroll.json shows $21.495 unchanged through today's 10:18Z snapshot — but because these positions are **untracked** by the bot, both gains and losses bypass bankroll.json.

| Position | Entry | Horizon | Cost | Upside if YES |
|---|---|---|---|---|
| Jul-17 d+3 | Jul-17 | Jul-20 | $8.060 | small (high price) |
| Jul-18 d+2 | Jul-18 | Jul-20 | $3.590 | small (high price) |
| Jul-19 d+1 | Jul-18 02:14Z | Jul-20 | $2.926 (146.33 sh @ $0.02) | **+$143.40** |

If the Jul-19 $0.02 sniper filled YES: true wallet balance ≈ **$165+**, crossing the $40 kernel floor, the $50 ruin floor, and the $89.16 ruin floor referenced by the gatekeeper. All charter blocks on re-arming dissolve. This is a one-API-call verification with asymmetric information value.

Historical context: UPDOWN_STOP was triggered at PF=0.79 over 27 settles, implying sniper win rate substantially below the ~97% breakeven — so probability of YES on the $0.02 position is low. But not zero, and the cost of not checking is operating on a wrong capital baseline.

*Expected delta*: Resolves capital uncertainty. If YES: transforms the governance picture. If NO: confirms $21.495 baseline and rules out the upside scenario. **Confidence in verification: 100%. Effort: one CLOB API call.**

### 2c. ISOTONIC S4 — CANDIDATE REVIEW PENDING [MODERATE, HUMAN REVIEW]

Deployed isotonic: 46 days stale (refit 2026-06-06). Candidate: freshly refit 2026-07-21 (n_live=3,733, 8-day OOS). Calib_monitor S4 alert:
- Material diff at p_raw=1.0: candidate p_cal=1.000 vs deployed 0.6316 (+0.3684) — removes all tail shrinkage
- Near-threshold diff at p_raw=0.95: +0.0483 (just under 0.05 threshold)
- OOS: brier_cal (0.0603) slightly worse than brier_raw (0.0595) — isotonic adding marginal negative value on 8d OOS

Promotion is not recommended without human review of tail behavior. The +0.3684 shift at p_raw=1.0 removes all Bayesian shrinkage for the highest-confidence buckets. On a dataset where the isotonic plateau already dominates (p_raw 0.30–0.85 → p_cal≈0.374), the tail behavior change is the only material difference. OOS evidence slightly disfavors the candidate.

*Expected delta*: Correct deployment improves ECE at extremes. Incorrect deployment (premature tail de-shrinkage) adds overconfidence. **Confidence: requires human judgment. Effort: low.**

---

## 3. GATE PIPELINE

| Gate | n | WR | ROI | CI95 | Status | Note |
|---|---|---|---|---|---|---|
| G1 BAND_YES | 934 | 15.3% | +4.0% | [-10.9, +21.1] | AMBIGUOUS | Frozen, band dark |
| G2a band_no_d1 | 115 | 68.7% | +1.3% | [-11.9, +12.7] | AMBIGUOUS | BAND_NO disabled |
| G2b pair_fav_YES | 9 | N/A | N/A | — | COLLECTING | Frozen, band dark |
| G2c pair_fav_NO | 9 | N/A | N/A | — | COLLECTING | Frozen, band dark |
| G3 FILLED_VS_FIRED | 75 | 17.3% | -75.8% | [-75.0, -34.2] | WATCH_ITEM ⚠ | CI entirely negative |
| G4 BASKET_EXIT | VOID | — | — | — | RETIRED | — |
| G5 THERMO_MAKER | 125 | N/A | 0.0% | [-9.0, +2.0] | **REJECTED** | — |
| G6 M1_BETA_LOCKOUT | 31 | 74.2% | -0.6% | [-20.6, +24.4] | **REJECTED** | — |
| G7 SUM_POSTED [0.70,0.85] | 382 | N/A | +11.5% | [-11.4, +38.9] | AMBIGUOUS | Frozen, band dark |
| **G8 UPDOWN_CROSSING** | **~57** | **98.2%** | **+0.61%** | **[90.7%, 99.5%]** | **COLLECTING** | **See FLAG-1** |

**G8 is the sole gate with any re-enable path. It cannot pass at n=100.**

From gatekeeper FLAG-1: with 1 loss in the record (56W/1L), Wilson CI-lo at n=100 = 94.6% < BE=97.01%. Scenario table:

| n | W/L | CI-lo | vs BE=97.01% | Verdict |
|---|---|---|---|---|
| 100 | 99W/1L | 94.6% | −2.4pp | **FAIL** |
| 100 | 100W/0L | 96.3% | −0.7pp | **FAIL** |
| 200 | 199W/1L | ~97.2% | +0.2pp | PASS |

Minimum n for pass with 1 existing loss: **~200**. At current forward rate (~4/day, post-catchup): ETA n=200 ≈ **Aug 26** (35 days).

**Human decision required by ~Jul-25** (before n reaches 100 in ~10 days at 4/day):
- **Option A — KILL**: Label G8 CLOSED. Frees cognitive overhead; signals sniper strategy needs redesign if/when capital recovers.
- **Option B — EXTEND to n=200**: Set Aug 26 as the formal pass/kill decision date. Requires capital to remain above service floor (disk cleanup is a prerequisite).
- **Option C — AMBIGUOUS-EXTEND at n=100**: Fall-through; gate classifies ambiguous; defers the decision without a clear horizon.

Accelerating G8 accumulation is not possible (UPDOWN_STOP active; the sniper fires 5-min updown markets which are currently halted).

G2b/G2c (pair_fav) are collecting but blocked by BAND_LIVE=False. Their n=9 each is immaterial; no breadth change unblocks them without a band re-arm. Not a viable near-term gate.

---

## 4. ASSUMPTION ATTACK

### A. Dispersion premium persists → SEVERELY THREATENED (day 20)

The band's entire edge rests on the market overestimating temperature dispersion vs Chainlink-resolved outcomes. Per calib_monitor §3:

| Window | disp_ratio7 | n eligible | Inversion? |
|---|---|---|---|
| 07-16 | 1.196 | ~8 | No (above 1.10) |
| 07-17 | 0.927 | ~8 | Yes |
| 07-18 | 0.485 | ~8 | Yes |
| 07-19 | 0.925 | ~8 | Yes |
| 07-20 | 0.779 | 18 | Yes |
| 07-21 | **0.783** | **27** | **Yes** |
| **7d median** | **0.854** | **~77** | **Yes (day 20)** |

Only 1 of 6 settled days exceeds 1.10. US/Other is the worst sub-region (07-21 median 0.584). Asia is near-neutral (0.970). EU re-entered eligibility after 07-20 full mode-hit saturation (6 cities, median 0.854). The 07-22 early Asian read (0.452, 4 cities only) is the worst early-morning signal in the window — not yet settled, but alarming if sustained.

**This alert is not noise**. The dispersion ratio has been below 1.10 for 20 consecutive days. If BAND_LIVE were armed, the current market regime would generate systematic losses on the YES band. Band dark status is inadvertently correct capital protection.

**Counter**: 07-16 shows the edge can return; n=77 city-days is only trend-grade (<100 for decision). But the direction is consistently wrong for 19 of 20 days.

### B. Fills are not adversely selected → UNCERTAIN / WATCH_ITEM CONFIRMED

G3 (n=75, gatekeeper): Filled WR = 17.3% vs simulation WR = 7.6%. Fills DO arrive on better-than-average markets (positive WR selection). But ROI = -75.8% with CI entirely below zero.

This combination — positive WR selection, catastrophically negative ROI — is consistent with **winner's curse on fill price**: we buy at higher ask prices than the simulation because the book moves against us between signal and fill. We're correctly identifying good markets but overpaying to get into them.

Corroborating evidence from calib_monitor §1: ECE overconfidence in [0.3–0.4) bin (mean_p=0.370 vs mean_o=0.284, n=67 rows, 18.2% of sample). This is the isotonic plateau bin — the exact price range where most band fills occur. The model systematically overestimates resolution probability in the mode-adjacent range. Combined with positive WR selection: we're buying overpriced probability with a positive tilt, which generates small gains on WR but structural losses on price.

G3 CI entirely negative is a structural finding at n=75 (trend-grade, not decision-grade). At n=100 this becomes a decision-grade disqualifier for any band re-enable that relies on G3 improvement.

### C. Recycle velocity scales → N/A

Zero open positions. RECYCLE099 had zero exit099_live records (exec_audit). Cannot assess. This assumption requires live positions to evaluate; not applicable in current state.

---

## 5. MARKET INTELLIGENCE — MARKET CENSUS (22 mod 3 = 1)

*Direct Gamma API blocked by network proxy; census based on shadow engine output from exec_audit and gatekeeper.*

**Depth by horizon (band_struct_lite, Jul-22 as of 07:01 UTC)**:

| Horizon | Status | Sum_ask range | Shadow fires |
|---|---|---|---|
| d+0 | `converged` / `no_band` | N/A | 0 (saturated/thin) |
| d+1 | `sum_gate` **all cities** | > 0.85 | 0 (priced out) |
| d+2 | `fire` (live=false) | 0.57–0.845 | 8 fires |

**d+2 fires on Jul-22** (gatekeeper G7 note, 5 in [0.70, 0.85]):
- Seoul d+1: sum_ask 0.845 (gate cell)
- London d+2: 0.750
- Shanghai d+2: 0.715
- Tokyo d+2: 0.825
- Chengdu d+2: 0.845

**Delta vs state_log knowledge**: d+1 showing `sum_gate` on all cities is new vs the Jun/early-Jul pattern where d+1 had viable entries. Two candidate explanations: (1) summer market regime (higher implied temperature dispersion at 1-day horizon, efficient pricing); (2) structural shift in market maker behavior post-Jun-30 fee reform. Sample too small to distinguish. The BAND_MD_HORIZON=2 (d+0/d+1/d+2) design was built when d+1 was viable; if d+1 is now consistently gated, the effective horizon collapses to d+2 only, reducing turn frequency by ~33%.

**BAND_CITY_ALLOW active**: 10 cities in shadow as of this report (chengdu, london, beijing, munich, wuhan + at least 5 others from config). No new cities observed vs 51-city allow-list. d+2 book depth appears healthy (sum_ask 0.57–0.845 = within BAND_SUM_MAX=0.85 range for most).

**Competitor posture** (badatmath_watch): Delta unavailable — shadow_summary.json too large for direct read, network blocks git fetch. Prior state_log baseline (Jun-22): badatmath geometry = YES bell (mode-centered, 37.4% of YES$ at off0) + NO shoulder (83.8% of NO$ off-mode). His 60/40 YES/NO split, 38.4% co-fill cells. No confirmed delta since Jun-22.

---

## 6. EXPERIMENTS

### Experiment 1: STWA position wallet reconciliation
**Hypothesis**: At least one of the 3 overdue STWA positions has resolved YES, raising true wallet balance above the $40 charter kernel floor.  
**Data**: Single CLOB API call (`py_clob_client.get_balance()` or `GET /positions?user=<addr>`) against the Polymarket wallet. Check USDC balance directly vs bankroll.json $21.495.  
**Time**: 30 minutes including diagnosis.  
**Cost**: $0.  
**Success metric**: Confirmed resolution direction for all 3 positions + reconciled wallet balance to ±$0.10.  
**Decision if any YES**: Update capital baseline; if wallet > $40, owner can authorize re-arm of any gate that passes (G8 extension becomes meaningful). If Jul-19 YES: +$143.40, true capital ~$165 — clears all charter floors.  
**Decision if all NO**: Confirms true capital = $21.495. Rules out upside scenario. Owner focuses on the single path forward: G8 kill/extend decision with $21.50 as the operating baseline.  
**Note**: The existing "untracked" posture means this information gap persists indefinitely without explicit verification. Even a NO confirmation has value (removes the uncertainty from capital planning).

### Experiment 2: G8 exact CI threshold for extension
**Hypothesis**: With 1 loss in the record, the minimum n for CI-lo ≥ BE=97.01% is n≈200 (pre-confirmed by gatekeeper FLAG-1 via 199W/1L = CI-lo≈97.2%), and the rate of 4/day gives ETA Aug 26.  
**Data**: Wilson CI formula; current record 56W/1L; gatekeeper FLAG-1 pre-confirmation.  
**Time**: 15 minutes (Python one-liner).  
**Cost**: $0.  
**Success metric**: Confirm exact n* (minimum n where Wilson CI-lo ≥ 97.01% given 1L), and whether the math holds for 2L and 3L scenarios (kill triggers).  
**Decision if n*≈200**: Propose extending threshold to n=200; Aug 26 horizon; requires disk cleanup to survive that long.  
**Decision if n*>250**: Opportunity cost too high; recommend kill now, save 35 days of shadow accumulation overhead.  
**Kill trigger**: 2L in record → re-run CI analysis; point WR approaches BE; likely kill regardless of n*.  

### Experiment 3: Regional dispersion decomposition (7-day settled)
**Hypothesis**: Asia cities (Beijing, Tokyo, Seoul, Shanghai, Chengdu, etc.) maintain disp_ratio > 1.10 on ≥3 of 7 settled days while US/Other drives the systemic inversion; a city-filtered band has a valid dispersion edge.  
**Data**: shadow/YYYY-MM-DD/band_struct_lite_shadow.jsonl for Jul-16..Jul-21 (6 settled days). Calib_monitor §3 already provides Jul-21 per-city table (27 cities); extend backward. Compute per-city 7d median disp_ratio.  
**Time**: 2–3 hours (data join across 6 daily shadow files + aggregation).  
**Cost**: $0 (data exists in data-mirror).  
**Success metric**: ≥3 Asia cities with 7d median disp_ratio > 1.10 AND US/Other median < 0.85; Mann-Whitney separation p < 0.10.  
**Decision if yes**: Propose narrowing BAND_CITY_ALLOW to Asia-only subset for human consideration when capital recovers; provides the evidentiary basis that the band edge exists in a geographic sub-slice.  
**Decision if no**: Confirms uniform inversion; band thesis structurally invalid across all geographies; strengthens the case for not re-arming the band even if capital recovers. Redirects effort toward sniper redesign or different market type.

---

## 7. SINGLE BEST ACTION

**Disk cleanup (VPS SSH — today, before Jul-24).**

**Why this wins on (compounding impact × P(success)) / effort**:
- *Compounding impact*: Preserves the only productive activity in the system — G8 shadow accumulation at ~4 ticks/day. Without Klaus running, accumulation stops entirely. A disk-full crash at 7 GB free (burning 3.1 GB/day) would occur around **Jul-24 16:00 UTC**, erasing any path to a G8 decision by the Aug 26 ETA. It would also prevent the STWA resolution audit, the G8 threshold computation, and any future re-arm. The disk is the only thing that can make the current null state actively worse.
- *P(success)*: Near 100%. File deletion is deterministic. No strategy risk, no market dependency.
- *Effort*: Two shell commands (SSH to VPS).
- *Cited evidence*: exec_audit §3 (shadow engine writing every 300s), system_status.txt (94%, 7 GB free at 10:18Z), pnl_ledger §4 (disk alert confirmed, original +2%/day now observing +3.1 GB/day).

**First concrete step** (human executes on VPS):
```bash
# identify large consumers
du -sh /path/to/data/shadow/* | sort -hr | head -20
# delete shadow snap files older than 2 days
find /path/to/data/shadow -name 'snap_*.jsonl' -mtime +2 -delete
# delete shadow daily dirs older than 7 days  
find /path/to/data/shadow -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +
# confirm recovery
df -h
```
Target: reclaim ≥5 GB; confirm ≥12 GB free after cleanup for 4-week safe runway at 3.1 GB/day.

All compounding-path decisions (G8 kill/extend, STWA audit, isotonic promotion) are downstream of Klaus staying alive. Disk cleanup is the prerequisite.

---

## PROPOSED ACTIONS (human review)

All items below require owner approval or action. No code or flag changes implemented by this report.

**[URGENT — today]** Disk cleanup: SSH to VPS; delete shadow snap files >2d and daily shadow dirs >7d; target ≥12 GB free. Prevents service crash by Jul-24.

**[HIGH — this week]** STWA resolution audit: Run `py_clob_client.get_balance()` or check Polymarket wallet directly to reconcile $21.495 bookkeeping vs true USDC balance. If Jul-19 position (146.33 sh @ $0.02) resolved YES: true capital ~$165, all charter floors cleared.

**[HIGH — by Jul-25]** G8 gate decision: With n≈57 (56W/1L) and a mathematical impossibility of passing at n=100, owner must decide:
- KILL G8 now (close out the shadow experiment)
- EXTEND to n=200 (Aug 26 horizon, ~35 more days at 4/day rate)
If 2 more losses appear at any point, kill is the dominant option regardless of n.

**[MEDIUM — within 1 week]** Isotonic S4 review: Human review of candidate (n_live=3,733, refit 2026-07-21) tail behavior (p_raw=1.0 → p_cal=1.000, removes all shrinkage) before promoting. OOS brier_cal slightly worse than raw — not disqualifying but warrants scrutiny on tail buckets.

**[LOW — data collection only]** Experiment 3 (regional dispersion decomposition): Run calib analysis across 7d shadow files by city/region. No live capital at risk; pure information.

---

## ANTI-SYCOPHANCY CHECKS

- The last 10 commit messages show zero fills, zero trades, $0 PnL for 2+ consecutive days. The strategy is not working — it is stopped.
- disp_ratio7=0.854 < 1.10 for 20 consecutive days. The dispersion edge does not exist in current market conditions. This is not a calibration artifact; it is 5 of 6 inverted.
- G3 winner's curse (ROI CI entirely negative at n=75) is a structural finding, not noise. No band re-enable may cite G1/G7 ambiguous-positive CI as overriding evidence.
- Capital at $21.495 ($21.495/$300 = 7.2% of original) is deep into ruin territory. No language in this report implies a recovery path exists without explicit owner intervention and capital injection or a rare favorable STWA resolution.
- G8 cannot pass at n=100. Stating this is not pessimism — it is Wilson CI arithmetic.

---

*Sources: exec_audit_report.md (07:07Z), calib_monitor_report.md (08:10Z), gatekeeper_report.md (09:07Z), pnl_ledger_report.md (23:37Z Jul-21). Raw mirror: data-mirror branch SHA f267ecfa, snapshot 10:18:46Z. All analysis is this session — no prior state carried forward except where specialist reports explicitly carry it.*
