# Research & Optimization Audit — 2026-07-09

Generated: 2026-07-09T18:30Z | Snapshot: 2026-07-09T18:03Z (0.4h — FRESH) | System: active  
Capital: $163.93 | Daily start: $83.93 | Delta today: +$80.00 (+95.3%) | HW: $222.90  
BAND_LIVE: False (re-cut 07-08 22:05) | PAIR_FAV_ENABLED: True | Open positions: 0 + 2 ladder shots

**Report freshness:**
| Report | Generated | Age | Status |
|---|---|---|---|
| exec_audit_report | 2026-07-08T07:06Z | 35.4h | OK |
| calib_monitor_report | 2026-07-08T08:12Z | 34.3h | OK |
| gatekeeper_report | 2026-07-07T09:03Z | 57.5h | **STALE — gate ledger from raw mirror** |
| pnl_ledger_report | 2026-07-07T23:37Z | 42.9h | **STALE — P&L from bankroll.json + maker_fills_recent.log** |

---

## §1 — Primary Bottleneck for Compounding

**Bottleneck: EQUITY DEPLOYED = $0 (band dark 43h, turns/day = 0.0)**

Ranking applied: equity deployed → turns/day → ROI/turn. All three are zero for the band engine. The band generated ~$35/day (16 fills/$70.73 over Jul 5-6) when live; the compounding multiplier is entirely absent while BAND_LIVE=False. Sprint ladder provides one-off binary returns (today +$80 from a 0.399→0.992 winner), but these are not compounding velocity — they are capital-preservation shots, not systematic turns.

**Re-enable conditions (reconstructed from exec_audit §6 + state_log 07-08 22:05 + today's bankroll.json):**

| Condition | Threshold | Today | Status |
|---|---|---|---|
| Equity ≥ 50%×HW | ≥$111.45 | $163.93 (73.6% HW) | ✅ CLEARED |
| −14% freeze expiry | 07-10 21:53Z | 26h remaining | ⏳ Tomorrow evening |
| Pair n trend | ≥40/side | ≈9/side (rate=0 with band dark) | ❌ 31 fires short |
| Dispersion ratio | ≥1.10 ×5d (advisory) | 0.817, stale 7d | ⚠ Stale — not measurable |

The equity rail cleared today, driven by ladder win (token 4409657373007951: BUY 129sh@0.399 → SELL 129sh@0.992, net +$76.50). Two ladder shots remain open: token 9106278428823737 (37sh@0.38, $14.06) and token 3360836802715119 (10sh@0.53, $5.30).

The freeze is the closest mechanical gate (clears tomorrow, 07-10 21:53Z). The pair n gate starts accumulating the moment BAND_LIVE flips True — at shadow fire-rate ~11/side/day, n=40 would be reached ~2.8 days after re-enable. The dispersion ratio gate is stale (cannot confirm recovery without fresh outcome labels); see §2-B and §6.

---

## §2 — Existing System Optimization

Three idle or incomplete optimizations identified from specialist reports:

**A. VPS band_resolution_join.py — G7 gate unresolved, 5+ days overdue**
*(gatekeeper URGENT advisory; exec_audit §4 markout deferred; calib_monitor §1 settled lane locked)*

Shadow SUM_POSTED [0.70, 0.85] has n>>100 dedup'd fires; CI is the only remaining blocker for G7 (gatekeeper). A single VPS run of `band_resolution_join.py` delivers a READY/REJECTED verdict. If READY, firing breadth for pair_fav YES expands by ~15% (sum_ask acceptance from <0.85 extends to [0.70, 0.85]). Blocked by Gamma API 403 from cloud; VPS only. Confidence: high. Effort: one EVOLVE slot.

**B. Settled lane outcome labels — dispersion ratio locked at Jun 28-Jul 2, 7 days stale**
*(calib_monitor §3 S3-ALERT persisting; proxy sigma 7th consecutive below-baseline)*

Jul 3-9 resolved in reality but unlabeled in the calibration pipeline. Fresh outcome labels would either confirm edge inversion persists (hold BAND_LIVE=False) or show recovery (support re-enable). Without this, the 07-10 21:53Z re-enable decision defaults to "stale, hold" — foregone compounding at ~$35/day. Same VPS job as item A (band_resolution_join.py executes the Gamma/CLOB join). Confidence: high (VPS API access confirmed in prior runs). Effort: same EVOLVE slot as A — combinable.

**C. Isotonic map freshness — 32-33 days stale, degenerate mid-range plateau**
*(calib_monitor §4: deployed + candidate maps flat at ~0.38 for ALL market prices 0.30-0.90)*

The model assigns identical ~38% probability regardless of whether the market prices 30%, 50%, or 90% — no discriminative power across the operating range. A fresh refit on Jul data would restore gradient or confirm structural flatness. Expected delta: better p_cal → band EV filter more accurate, directionally reduces winner's-curse exposure at mid-range (Moscow NO at BAND_NO_MAX=0.85 being the canary). Confidence: medium (depends on whether Jul resolved rows add signal). Effort: 1-2h VPS compute; can combine with weekly EVOLVE slot Jul 13, or advance to Jul 10.

**Shadow pipeline health (from raw mirror, 07-09 18:02Z):** Demand is genuine. band_struct n=6,075 today, last fire: Chengdu d+1 (Jul 11) sum_ask=0.815, live=false. stwa_pricer_eval n=298,452 (pricing running). maker_shadow n=74,283 (maker quoting shadow active). Every hour dark is real foregone supply.

---

## §3 — Gate Pipeline Review

*(gatekeeper stale 57.5h — reconstructed from raw mirror + state_log. No band fires since Jul 6 22:08 → all n counts frozen.)*

| Gate | n (Jul 7 report) | n (today est.) | Status | Nearest action |
|---|---|---|---|---|
| G1 BAND_YES (dout=9, paused) | 934 resolved | 934+ shadow accrual | AMBIGUOUS | VPS join needed; disp_ratio block |
| G2a BAND_NO (disabled Jul 2) | 51 live | 51 live | **REJECTED** | None — disabled |
| G2b PAIR_FAV_YES | 9 | **9** (rate=0) | COLLECTING | Clock restarts at BAND_LIVE=True |
| G2c PAIR_FAV_NO | 9 | **9** (rate=0) | COLLECTING | ~8.3d to n=100 from re-enable |
| G3 FILLED_VS_FIRED | 37 | **37** (rate=0) | COLLECTING | 3 fills to n=40; immediate on restart |
| G4 BASKET_EXIT | VOID | VOID | **VOID** | Retired Jun 22 |
| G5 THERMO_MAKER_NO | 125 | 125 | **REJECTED** | Done |
| G6 M1_BETA_LOCKOUT | 31 | 31 | **REJECTED** | Done |
| G7 SUM_POSTED [0.70,0.85] | >>100 shadow | >>100 shadow | **COLLECTING (CI blocked)** | **VPS join — today is day 5+ overdue** |

**Gate nearest READY without new accumulation: G7.** It already has sufficient n; the only action is the VPS join. G3 needs 3 fills — these will arrive within hours of band restart.

**How to accelerate G2b/G2c WITHOUT degrading expectancy:** Breadth, not stake. 11 cities in BAND_CITY_ALLOW → ~11 pair_fav events/cycle when live. BAND_BASE_STAKE and BAND_NO_STAKE are unchanged; the bottleneck is event frequency. Increasing the city allowlist (if data supports additional cities) would increase accumulation rate faster than any stake change.

---

## §4 — Assumption Attack

**Assumption 1: Dispersion premium persists (implied σ > realized σ)**
*Status: THREATENED — data does not support this assumption on any confirmed day in current window*

calib_monitor §3 (34.3h old, locked Jun 28-Jul 2): All 5 confirmed days inverted. Ratios: 0.807, 0.663, 0.976, 0.866, 0.858 — none exceeds 1.10. The premise that the market overprices temperature dispersion (creating our buying edge on cheap-ask bands) has not been empirically supported on any day we can verify. Proxy lane (day 7, σ=0.831) is the 7th consecutive below-baseline reading; the +0.009 uptick from day 6 is within methodology noise and does not constitute a confirmed reversal.

Threatening scenario: summer (Jul-Aug) weather regimes have higher realized variance than winter, systematically inverting the dispersion premium seasonally. If structural, the band edge is absent until cooler months. Cannot confirm or deny without fresh outcome labels for Jul 3-9 — see §6 Experiment 2.

If the Jul 3-9 join shows continued inversion, the correct output is to extend BAND_LIVE=False until the ratio recovers, regardless of equity or freeze status.

**Assumption 2: Fills are not adversely selected**
*Status: MONITORING (n=1 warning, no decision possible)*

exec_audit §4 identifies Moscow NO (n=1): entry 0.840 near BAND_NO_MAX=0.85, next-day DCA at 0.060 = 93% adverse price move. Classic adverse selection — takers knew the outcome direction and sold NO into our maker quote at near-certainty pricing. n=1 is below the 40-trade decision floor; this is a PLAUSIBLE flag. BAND_NO_ENABLED=False independently (WR 39.2%, n=51), so this assumption only matters if BAND_NO is re-evaluated.

For pair_fav YES (the active-when-live path), adverse selection is structurally less likely: both YES and NO legs are posted simultaneously on the same bucket, so takers must fill both sides to create adverse selection, which requires the bucket to resolve in neither YES nor NO direction (impossible in binary markets). The structural design partially protects against this on the pair path.

**Assumption 3: Recycle velocity scales with deployed capital**
*Status: MOOT (band dark 43h); last data too thin to validate*

The design premise: more capital → more resting legs → higher fill-collision probability → more merges/day. Last active data (Jul 5-6): 32 fills / $70.73 / ~16/day (2 active days). This is insufficient to validate any scaling curve. Base rate (16 fills/day) is the only confirmed number; the scaling component has zero empirical data points. Threatening scenario: maker queue saturation — if top-of-book is price-competitive (badatmath et al.), adding our orders doesn't increase fill probability linearly. This is non-linear and may not manifest until higher capital; cannot assess at n=2 active days.

---

## §5 — Market Intelligence: Competitor Posture
*(Day 2026-07-09 → 9 mod 3 = 0 → competitor posture)*

**badatmath_watch (raw mirror, hot/2026-07-09/badatmath_watch.jsonl):**
- n=1,478 rows today, mtime 18:02Z — actively scanning
- Record composition: ALL "ladder" (book scan) records; ZERO "fill_join" records
- Last scan: `highest-temperature-in-ankara-on-july-10-2026` — bids at [0.002, 1.47] and [0.001, 204.xx], essentially an empty book near zero probability
- Contrast: Jun 29 file had explicit `fill_join` records showing active fills

**Delta vs state_log knowledge:**
- badatmath is in scanning mode today, not active filling (at least in our tracked markets)
- Ankara July 10 is not one of our primary markets; the scan suggests broader reconnaissance rather than targeted competition in our city set (Beijing, Chengdu, Munich, London, etc.)
- No evidence of badatmath fills in our core cities today — but band_struct shows genuine market demand (Chengdu d+1 sum_ask=0.815 with a band fire shadow), suggesting someone IS filling those markets

**Leaderboard wallet teardown:** Not executable from cloud environment. Gamma/Polymarket API returns 403 from datacenter IPs. No quantitative delta vs prior state available.

**NEG_RISK_ARB probe (no_arb_probe, 07-09 18:02Z, Seoul, N=11):**
- real_edge = $0.0018 per share ($0.13 on 7-leg partial sweep)
- 7 of 11 legs fillable; all_legs_fillable=false
- Near-zero edge, no fire conditions met. Seoul NEG_RISK_ARB not active today.

**Summary:** 43h of band darkness = uncaptured maker supply in our core cities. With 0 resting bids from us, badatmath or other makers are likely taking our share. Urgency of re-enable grows with each dark day.

---

## §6 — Experiments

**Experiment 1: Conditional BAND_LIVE re-enable at 07-10 21:53Z (freeze expiry)**
- Hypothesis: equity ($163.93) + freeze-lift creates net-positive expected value from resuming pair_fav, even with disp_ratio stale, because the pair_fav YES leg edge (locking Σ≤0.90 on band) is mechanically distinct from the dispersion premium assumption (it does not require implied > realized σ; it requires only that the market posts the band legs cheap enough to lock a margin)
- Data required: EVOLVE 07-10 21:53Z to recompute equity rail, confirm freeze lifted, check disp_ratio proxy lane
- Time to run: 26h (already scheduled EVOLVE slot)
- Cost: $0 setup; the only risk is capital deployment into a potentially adverse regime
- Success metric: BAND_LIVE flips True AND ≥1 live pair_fav fire within 24h
- Decision-if-yes (equity clear + freeze lifted + G7 result from Exp 2 available): flip BAND_LIVE=True with PAIR_FAV_ENABLED=True only, NO_ENABLED=False (hold), YES_LIVE_MIN_DOUT=9 (hold)
- Decision-if-no (equity dipped intraday OR dispersion join shows continued inversion all 7 days): hold BAND_LIVE=False, set explicit 5-day re-eval after next dispersion recovery signal

**Experiment 2: Run band_resolution_join.py on VPS to resolve G7 AND refresh settled lane**
- Hypothesis: the VPS has Gamma/CLOB API access; one run delivers (a) SUM_POSTED [0.70,0.85] CI verdict for G7 and (b) disp_ratio update for Jul 3-9 (7 unlabeled days)
- Data required: EVOLVE to execute `band_resolution_join.py --start 2026-07-03 --end 2026-07-09`; commit to logs/evolve/gate_ledger_latest.md
- Time to run: 07-10 11:23Z morning slot (12h from now)
- Cost: ~$0; VPS compute and Gamma API quota
- Success metric: gate_ledger_latest.md has G7 verdict (READY or REJECTED) AND calib_monitor can compute disp_ratio for Jul 3-9 at next cycle
- Decision-if-G7 READY + disp_ratio recovered (≥1.10): full re-enable including SUM_POSTED range extension; unlock Experiment 1 with high confidence
- Decision-if-G7 REJECTED or disp_ratio inverted through Jul 9: maintain BAND_LIVE=False; re-run join in 7 days when new settled data available

**Experiment 3: Isotonic refit freshness test — does Jul data restore mid-range discriminative power?**
- Hypothesis: 32-day-stale isotonic maps are flat at ~0.38 for market prices 0.30-0.90 (confirmed, calib_monitor §4). A refit on Jul resolved rows would either restore gradient (usable calibration signal) or confirm structural flatness (model architecture limitation → reduce band's reliance on p_cal for mid-range gate decisions)
- Data required: EVOLVE to run refit script on Jul-only resolved rows; compare new grid to deployed (7538ab7)
- Time to run: Jul 10 or Jul 13 weekly EVOLVE slot; not time-critical vs Experiments 1-2
- Cost: 1-2h VPS compute; zero capital risk
- Success metric: new isotonic grid shows |delta| > 0.05 on ≥3 points in the 0.30-0.90 range
- Decision-if-yes: deploy new map; re-run calib metrics
- Decision-if-no: flat plateau is structural; consider removing p_cal from mid-range EV gates, relying only on sum_ask as entry signal; flag to owner as model architecture item

---

## §7 — Single Best Action

**EVOLVE should run `band_resolution_join.py` at the 07-10 11:23Z morning slot — BEFORE the 07-10 21:53Z freeze-expiry re-enable decision.**

**Rationale (compounding impact × P(success) / effort):**

- **Impact**: The 07-10 21:53Z EVOLVE slot must decide whether to flip BAND_LIVE=True. The two critical inputs are (1) G7 SUM_POSTED verdict and (2) disp_ratio for Jul 3-9. Both come from a single VPS script run. Without this, the re-enable decision is made blind on the most important edge variable (dispersion). The downside of re-enabling into inverted dispersion is systematic bleed; the downside of holding dark for another 7 days waiting for more labels is ~$245 foregone P&L (7 days × $35/day).
- **P(success)**: High. The VPS runs this script successfully in prior cycles; it's a known-working data pipeline. The only previous blocker was "cloud agents can't call Gamma API" — and EVOLVE on the VPS is explicitly not cloud.
- **Effort**: One EVOLVE slot, one command. No code changes, no risk, no capital deployment.

**This has been the #1 advisory item from the gatekeeper for 5+ consecutive reports. It has not been executed. The freeze expiry tomorrow creates the time-sensitive forcing function: run the join in the morning, make the re-enable decision with data in the evening.**

Concrete first step:
```bash
# EVOLVE 07-10 11:23Z morning slot:
python3 analysis/weather/band_resolution_join.py --start 2026-07-03 --end 2026-07-09
# Commits output → logs/evolve/gate_ledger_latest.md
# Cloud calib_monitor picks up fresh disp_ratio at 08:07Z Jul 11
# EVOLVE 07-10 21:53Z evening slot uses the result for BAND_LIVE re-enable decision
```

Cited evidence: exec_audit §6 ("10+ shadow d+2 markets converged but undeployable — shadow demand exists"), gatekeeper G7 advisory ("Escalating priority: every day without this join leaves a potentially-valid slice unscaled"), calib_monitor §3 ("Re-enable condition: disp_ratio ≥ 1.10 for 5 consecutive confirmed days. Not measurable without outcome labels.").

---

## PROPOSED ACTIONS (human review)

**[FOR EVOLVE — no human input needed if charter permits]:**
- **PA-1 (07-10 11:23Z morning):** Run `band_resolution_join.py` for Jul 3-9. Commit results to `logs/evolve/gate_ledger_latest.md`. This is a read-only analytics run; no live config changes.
- **PA-2 (07-10 21:53Z evening):** Conditional re-enable — flip BAND_LIVE=True with PAIR_FAV_ENABLED=True only IF (equity ≥$111.45) AND (freeze lifted) AND (G7 READY from PA-1 OR disp_ratio shows recovery ≥1.10 on any Jul 3-9 day). Hold BAND_NO_ENABLED=False, BAND_YES_LIVE_MIN_DOUT=9.
- **PA-3 (Jul 10-13):** Isotonic refit on Jul data; compare before deploying.

**[MONITORING — no action needed today]:**
- Maker rebate: cumulative expected ≈$3.17 > $1 threshold. Verify pUSD receipt in Polymarket account; if absent, post wallet address to #market-makers Discord.
- Moscow NO adverse selection (n=1): monitor if BAND_NO ever re-evaluated; no action today.
- Pair n gate: n=9/side, clock frozen; restarts automatically at BAND_LIVE=True. ETA ~2.8d from re-enable to n=40 trend threshold.
- LDA rolling-20 net: −$19.71, approaching −$36.39 STOP (per pnl_ledger Jul 7, stale). Verify this threshold applies to band-maker book or was set for LDA-era; likely stale threshold.

**NULL DAY for autonomous changes.** No gate newly READY or REJECTED. No code changes warranted. Capital rail cleared, freeze timer running. Correct posture: preserve capital, run VPS join tomorrow morning, make data-driven re-enable call tomorrow evening.

---

*Report generated 2026-07-09T18:30Z. Snapshot age: 0.4h (fresh). System: active. gatekeeper_report STALE (57.5h) — gate ledger reconstructed from raw mirror (no n-count changes since Jul 7: band dark). pnl_ledger_report STALE (42.9h) — P&L derived from bankroll.json ($163.93) + maker_fills_recent.log (ladder attribution). REPORT-ONLY — no strategy code or gate changes made.*
