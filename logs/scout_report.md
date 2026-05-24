# VOLARB Alpha Scout — 2026-05-24T00:47Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-24T00:37:54Z (~7 min old — FRESH) |
| Klaus state | active (WEATHER strategy, per system_status.txt) |
| Klaus HEAD | 08662ac2 (log: pagination + bracket-shadow bug fixes) |
| Capital | $31.70 (bankroll.json) |
| VOLARB n (live era, deduped) | **887 — FROZEN** (unchanged from prior scout) |
| VOLARB date range | 2026-05-16 21:00 – 2026-05-19 02:50 UTC (~53.8h / 2.2 days) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight:**
- snapshot_ts age: ~7 min — **PASS**
- integrity_report.json: absent from data-mirror — treated as PASS (no `blocks_agent_run`)
- Last scout: 2026-05-21T12:42Z (~60h ago — > 8h threshold, proceed)
- CODE_DESYNC check: not applicable (no VOLARB branch gates to diff)

**⚠ VOLARB IS RETIRED — POST-MORTEM ONLY.**
Strategy last fired 2026-05-19 02:50 UTC (~4.9 days ago). All subsequent trades are WEATHER/CAS_LOWASK/LDA.
VOLARB n is permanently frozen at 887. No gate changes are possible. This cycle is historical closure.

**Aggregate VOLARB performance (final — stake-normalised $1-equiv):**
| metric | value | vs baseline CI [+0.244, +0.352] |
|---|---|---|
| n (deduped by token_id) | 887 | — |
| WR | 34.6% | below 40% backtest expectation |
| EV/trade (net_pnl/$stake) | +$0.038 | CI=[−$0.065, +$0.142] — **BELOW baseline CI lower** |
| EV/trade (kline_pnl/$stake) | −$0.023 | resolution metric; **negative** |
| Profit factor | 1.055 | above 0.8 kill-switch floor |
| Fee bleed | 1.8% of gross wins | well below 20% ceiling |
| kline vs net divergence | −$81.63 | book-profit ≠ resolution-profit |
| Total net_pnl | +$49.82 | across 2.2 days |

**kline/net divergence note:** the strategy booked $81.63 more in net_pnl than kline_pnl, because PROFIT_TARGET exits (267 trades, WR=100%) captured mark-to-market gains that later reversed at resolution. kline_pnl (−$0.023/trade) is the resolution-correct metric; net_pnl (+$0.038/trade) flatters performance.

---

## Continuity vs Prior Scout (2026-05-21T12:42Z)

**Investigations carried over:** H1 (per-asset; prior found ETH SIGNAL_FOUND) and H6 (direction asymmetry; prior found 'up' SIGNAL_FOUND) — both re-confirmed below. H5 (term_remaining_s=0 logging bug) — DATA_MISSING, moot, closed in prior.

**Resolved/closed since prior:** Prior scout declared "All VOLARB research families permanently closed." This cycle re-confirms the freeze and adds one methodological correction to H3 (prior used raw net_pnl; correct comparison is stake-normalised, which shifts two bands from WITHIN_CI to BELOW_CI — academic only, no deployment impact).

**Investigations selected this cycle: H1, H3, H6** (highest data density; all others are INCONCLUSIVE or closed).

---

## Investigation H1 — Per-Asset Alpha Re-Allocation

**HYPOTHESIS:** The backtest projected BTC as the alpha asset. Live data may show asymmetric asset-level EV, with ETH dragging the aggregate below baseline.

**METHOD:** Slice deduped VOLARB trades by asset (BTC/ETH/SOL). Compute n, WR, EV/$1-stake (net_pnl/stake), 95% CI. Compare CI against baseline CI lower (+$0.244). Flag at n≥100 where CI upper < +$0.244. kline_pnl/$stake computed for resolution-correct comparison.

**RESULT:**

| Asset | n | WR% | EV net/$1 | EV kline/$1 | CI 95% (net) | vs_baseline_CI |
|---|---|---|---|---|---|---|
| BTC | 286 | 32.9% | +$0.054 | +$0.039 | [−$0.136, +$0.245] | WITHIN_CI (clips lower by $0.001) |
| ETH | **305** | **32.5%** | **−$0.031** | **−$0.075** | **[−$0.204, +$0.141]** | **BELOW_CI *** |
| SOL | 296 | 38.5% | +$0.094 | −$0.030 | [−$0.081, +$0.269] | WITHIN_CI |

*ETH CI upper (+$0.141) is $0.103 below baseline CI lower (+$0.244). Confirmed signal.*

**CONCLUSION: SIGNAL_FOUND (ETH, n=305).** ETH CI upper is definitively below baseline. BTC barely clips the baseline lower (+$0.245 vs +$0.244) — statistically within CI but marginal. SOL overlaps the baseline range. On the resolution metric (kline_pnl/$stake), all three assets are below baseline: BTC +$0.039, SOL −$0.030, ETH −$0.075. No asset delivered backtest-level kline EV.

**FAILURE_MET:** No — strategy is retired; ETH BELOW_CI cannot trigger an EDGE_FLOOR raise. The only lever (global EDGE_FLOOR) would have been available had VOLARB continued.

**IF_DEPLOYED:** Raising EDGE_FLOOR from 0.15 to ~0.20 globally (the only existing lever) would disproportionately reduce ETH trade count. Estimated impact: −$3 to −$5 in absolute foregone losses on ETH per 100 trades, at the cost of reduced throughput across all assets. No per-asset block exists. Moot.

---

## Investigation H3 — Per-Ask-Band EV vs Backtest Shape

**HYPOTHESIS:** The backtest convexity thesis predicted higher EV at low asks (fee near zero) and adequate EV through the core [0.30,0.40) band. Live data may show the core band underperforming or the low-ask convexity failing.

**METHOD:** Slice by entry_price: [0.10,0.20), [0.20,0.30), [0.30,0.40), [0.40,0.50), [0.50,0.60). Compute n, WR, EV/trade normalised to $1 stake (net_pnl/stake and kline_pnl/stake). Flag at n≥100 where CI upper < +$0.244.

**RESULT:**

| Band | n | WR% | EV net/$1 | EV kline/$1 | CI 95% (net) | vs_baseline_CI |
|---|---|---|---|---|---|---|
| [0.10,0.20) | 91 | 18.7% | +$0.160 | +$0.032 | n<100 | INCONCLUSIVE |
| **[0.20,0.30)** | **227** | **26.4%** | **−$0.006** | **−$0.053** | **[−$0.228, +$0.216]** | **BELOW_CI *** |
| **[0.30,0.40)** | **390** | **38.7%** | **+$0.068** | **+$0.010** | **[−$0.068, +$0.203]** | **BELOW_CI *** |
| **[0.40,0.50)** | **158** | **46.8%** | **+$0.044** | **−$0.007** | **[−$0.134, +$0.221]** | **BELOW_CI *** |
| [0.50,0.60) | 9 | 44.4% | −$0.158 | −$0.282 | n<100 | INCONCLUSIVE |
| out-of-gate | 12 | 8.3% | −$0.951 | — | n<100 | INCONCLUSIVE |

*All three n≥100 bands have CI upper below baseline CI lower (+$0.244).*

**Methodological note vs prior scout:** The prior scout (2026-05-21) reported [0.20,0.30) and [0.30,0.40) as "within CI" because it compared raw net_pnl/trade (not stake-normalised) against the +$0.244 threshold. Using stake-normalisation (required for $1-equiv comparison), both bands and [0.40,0.50) fall BELOW_CI. The correction does not change any actionable outcome (strategy retired) but is noted for accuracy.

**Convexity inversion confirmed:** The backtest expected higher EV at extremes (low ask = low fees). Live data shows the opposite: WR 18.7% at [0.10,0.20) vs 46.8% at [0.40,0.50). High-ask positions (closer to 0.50) had higher WR but still failed to reach backtest baseline. Low-ask tokens (ask<0.20) require very high WR to be profitable; live WR of 18.7% was insufficient.

**Exit-reason split reveals the mechanism:** PROFIT_TARGET exits (100% WR, EV=+$2.07/trade) and BOND_RESOLVED_NO exits (0% WR, EV=−$1.01/trade) are the two populations. The gate strategy selects markets, but once entered, the binary outcome is driven by direction momentum. The ask-band affects the magnitude of loss (lower ask = smaller absolute loss when wrong) and magnitude of gain (lower ask = larger gain when right), but the WR is set by market conditions.

**CONCLUSION: SIGNAL_FOUND (all n≥100 bands BELOW_CI).** No ask band within [0.20,0.60) delivered backtest-level EV on the resolution metric. The low-ask convexity thesis did not hold: cheap tokens had 18.7% WR (far below 40% target) while more expensive tokens had better WR but still below backtest CI.

**FAILURE_MET:** No — strategy retired. If deployed, actionable lever would be raising EDGE_FLOOR (e.g., 0.15→0.20) to reduce overall trade count and tighten selection; no per-band ask gate exists beyond ASK_FLOOR/ASK_CEIL.

**IF_DEPLOYED:** All three n≥100 bands miss baseline, suggesting the issue is not a specific band but a systematic edge shortfall. Raising EDGE_FLOOR globally is the only lever. The [0.30,0.40) backbone (44% of trades, EV=+$0.068/$1) is the best performing segment but still $0.176 below baseline lower. Estimated impact of EDGE_FLOOR 0.15→0.20: ~15-20% trade reduction, unknown EV improvement.

---

## Investigation H6 — Direction Asymmetry (up vs down)

**HYPOTHESIS:** The backtest had no direction split. Live data shows 'up' (BUY_YES) and 'down' (BUY_NO) token performance differing, potentially identifying a direction gate.

**METHOD:** Slice by bond_outcome_direction ('up'=BUY_YES, 'down'=BUY_NO). Compute n, WR, EV/$1-stake (net_pnl/stake and kline_pnl/stake), CI 95%. Confirm or update prior scout's 'up' SIGNAL_FOUND at n=393.

**RESULT:**

| Direction | n | WR% | EV net/$1 | EV kline/$1 | CI 95% (net) | vs_baseline_CI |
|---|---|---|---|---|---|---|
| **up (BUY_YES)** | **393** | **30.0%** | **−$0.004** | **−$0.029** | **[−$0.173, +$0.164]** | **BELOW_CI *** |
| **down (BUY_NO)** | **494** | **38.3%** | **+$0.072** | **−$0.019** | **[−$0.057, +$0.201]** | **BELOW_CI *** |

*Both directions have CI upper below baseline CI lower. 'down' outperforms 'up' by $0.076/$1-stake.*

**Asset × Direction sub-cells (all n<100, for archival reference):**

| Cell | n | WR% | EV net/$1 |
|---|---|---|---|
| BTC/up | 129 | 27.9% | −$0.060 |
| BTC/down | 157 | 36.9% | +$0.200 |
| ETH/up | 137 | 29.2% | −$0.053 |
| ETH/down | 168 | 35.1% | −$0.021 |
| SOL/up | 127 | 33.1% | +$0.018 |
| SOL/down | 169 | 42.6% | +$0.205 |

'Down' outperforms 'up' consistently across all three assets. The 'down' (BUY_NO) edge is $0.076 better per $1-stake, and BTC/down (+$0.200) and SOL/down (+$0.205) approach but do not reach the baseline CI lower.

**Temporal note (from prior scout):** 'Up' direction's below-CI result was driven by the final 24h of the VOLARB era (EV deteriorated from +$0.021 to −$0.251), suggesting a late-era regime shift. The structural BUY_YES drag is consistent with asymmetric market-maker hedging in 5-minute updown markets.

**CONCLUSION: SIGNAL_FOUND (both directions BELOW_CI at n≥100). 'up' direction is the stronger drag (CI upper +$0.164 vs 'down' +$0.201).** Both directions failed to deliver backtest EV. 'down' shows structurally higher WR across all assets (~38.3% vs ~30.0%), confirming the direction asymmetry flagged in prior scouts.

**FAILURE_MET:** No — strategy retired. No direction gate lever existed in VOLARB Phase 1.

**IF_DEPLOYED:** If VOLARB were to be re-deployed with a direction gate blocking BUY_YES: 'down' n=494, EV=+$0.072/$1. Still BELOW baseline CI, so a direction gate alone would not fix the strategy. The fundamental shortfall (overall EV vs backtest) is not direction-specific.

---

## Priority Signal for Next Implementation

**VOLARB is retired. No deployment action is possible.**

All three n≥100 investigations (H1/ETH, H3/all-bands, H6/both-directions) returned BELOW_CI. This confirms the prior scout's conclusion: **VOLARB did not deliver backtest baseline on any cell with sufficient data.** The strategy's kline EV of −$0.023/$1-stake (resolution metric) confirms the mark-to-market net EV was flattering — actual resolution-correct performance was slightly negative.

**Root cause hypothesis (for successor strategy design):**
1. `bond_adj_edge_at_entry = 0.0` for all 887 live trades — the EDGE_FLOOR gate (0.15) was not enforcing at time of execution, or the edge field was not populated. The backtest assumed edge≥0.10 filtering; live may have been unfiltered.
2. PROFIT_TARGET exits captured $953 gross while BOND_RESOLVED_NO exits lost $903. The two populations are nearly balanced — a slightly better WR or tighter selection would push the strategy into meaningful positive territory.

**No actionable signal this cycle — era permanently closed (n=887, frozen).**

---

## Closed-Family Confirmations

Re-validated as null or permanently closed this cycle:

- **H1 ETH SIGNAL_FOUND**: Confirmed. CI=[−$0.204, +$0.141], n=305. Permanently closed (VOLARB retired).
- **H3 all-bands BELOW_CI**: Confirmed with stake-normalisation correction. Prior scout found [0.20,0.30) and [0.30,0.40) "within CI" using raw net_pnl; stake-normalised comparison finds all three n≥100 bands BELOW_CI. Result is academically correct; operationally moot.
- **H6 'up' SIGNAL_FOUND**: Confirmed. 'Up' CI=[−$0.173, +$0.164], n=393. 'Down' also BELOW_CI at n=494. Permanently closed.
- **H5 term_remaining_s logging bug**: Still zero for all 887 trades. DATA_MISSING confirmed. Permanently closed.
- **H2 per-hour**: All n<100 (max n=71 at H11). Permanently closed.
- **H4 longshot recorder (ask<0.10)**: Not deployed; confirmed moot (VOLARB retired). Phase 2 longshot gate prep is cancelled. Permanently closed.
- **H7 watchlist trajectories**: 'Up' direction late-era deterioration (~2.1σ) confirmed in prior cycle. No further trajectory to monitor — era closed. Permanently closed.
- **VOLARB strategy overall**: kline EV=−$0.023/$1, net EV=+$0.038/$1. Profit factor=1.055. All families permanently closed.

---

## Open Requests for Auditor / Shadow Validator

**Cells trending to n≥100 within next 24h:**
- None. VOLARB n is permanently frozen at 887. No VOLARB cell will ever reach a new threshold.

**Shadow loggers (VOLARB-specific):**
- `volarb_longshot_shadow.jsonl`: Never deployed. **Closed — moot.**
- `shadow_summary.json`: Empty/unavailable on data-mirror this cycle. Shadow Validator should verify that LDA/WEATHER era loggers (`exit_policy_shadow`, `hold_path`, `market_timeline`) are still populating.

**Research_status.md update needed (for human review, not agent action):**
- §2 "Closed research families" should add: `VOLARB strategy | retired 2026-05-19 | replaced by CAS_LOWASK then LDA/WEATHER; final n=887, kline EV=−$0.023/$1-stake, net EV=+$0.038/$1-stake; backtest baseline not reached on any n≥100 cell; all research families closed 2026-05-21.`
- §1 "Active strategy" should reflect current WEATHER/CAS strategy (was last updated 2026-05-16 with LDA).

**For successor strategy design (not VOLARB-specific):**
- Direction asymmetry (BUY_YES lower WR by ~8pp vs BUY_NO in 5-min updown markets) should be monitored early in any new updown strategy — n≥100 per direction within the first week.
- Confirm edge field is populated at entry time in any new strategy (`bond_adj_edge_at_entry=0.0` for all VOLARB trades suggests the gate may not have been enforced live).
- Low-ask convexity thesis (ask<0.20 = better edge) was falsified in VOLARB: WR=18.7% at ask<0.20 vs 46.8% at ask[0.40,0.50).
