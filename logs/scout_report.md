# VOLARB Alpha Scout — 2026-05-21T12:42Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-21T12:33:41Z (~8 min old — FRESH) |
| Klaus state | active (CAS_LOWASK strategy) |
| Capital | $68.07 (bankroll.json, saved 2026-05-21T09:56Z) |
| VOLARB n (live era, deduped) | **887 — FROZEN** |
| VOLARB date range | 2026-05-16 21:00 – 2026-05-19 02:50 UTC (~53.8h / 2.2 days) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight:**
- snapshot_ts age: ~8 min — PASS
- integrity_report.json: absent — treated as PASS (no `blocks_agent_run`)
- Last scout: 2026-05-20T12:41Z (~24h ago — > 8h threshold, proceed)

**⚠ CRITICAL: VOLARB IS RETIRED.**
Strategy switched from VOLARB → CAS_LOWASK on 2026-05-19 02:50 UTC. The most recent 10 trades in trades.jsonl are all `bond_entry_class='CAS_LOWASK'` (latest: 2026-05-21T09:29Z). VOLARB n is permanently frozen at 887. All findings this cycle are **post-mortem** — no deployment action is possible against VOLARB gates. Report is filed for historical closure and shadow-logger hygiene.

**Aggregate VOLARB performance (final):**
| metric | value | vs baseline |
|---|---|---|
| n (deduped) | 887 | — |
| WR | 34.5% | below 40% backtest expectation |
| EV/trade (net_pnl) | +$0.056 | CI=[−$0.097, +$0.210] — **BELOW baseline CI lower (+$0.244)** |
| EV/trade (kline_pnl) | −$0.036 | CI=[−$0.189, +$0.117] — **negative on resolution metric** |
| Total net_pnl | +$49.82 | 887 trades, $1 stake |
| Total kline_pnl | −$31.81 | kline_pnl is the reliable resolution metric |

**kline_pnl vs net_pnl divergence (+$81.63 total):** net_pnl is based on mark-to-market at exit; kline_pnl reflects actual resolution. The strategy book-profited while losing on resolution — consistent with selling into liquidity before resolution reversed. This discrepancy is the core pathology.

---

## Continuity vs Prior Scout

**Prior scout:** 2026-05-20T12:41Z

- Investigations carried over: H1 (per-asset alpha), H6 (direction asymmetry) — both SIGNAL_FOUND in prior, confirmed below
- H5 (seconds-to-resolution logging bug) — DATA_MISSING in prior, **now moot (VOLARB retired)**
- New investigations this cycle: **H2** (per-hour EV), **H3** (per-ask-band shape), **H7** (watchlist trajectories for ETH and 'up' direction)
- Resolved/closed since prior: VOLARB strategy itself is retired — all open VOLARB research families close with this report

---

## Investigations

---

### H2 — Per-Hour UTC EV Breakdown

**HYPOTHESIS:** Backtest said no hours needed blocking. Live data may reveal hour-level EV variation below the baseline CI, justifying ex-post hour gate recommendations.

**METHOD:** Split deduped VOLARB trades by UTC hour. Compute n, WR, EV/trade, CI95(net_pnl). Flag at n≥100.

**RESULT:**

| Hour | n | WR% | EV/trade | CI95 | vs_CI |
|---|---|---|---|---|---|
| H00 | 39 | 35.9% | +$0.320 | [−$0.419, +$1.058] | n<100 |
| H01 | 66 | 48.5% | +$0.784 | [+$0.159, +$1.410] | n<100 |
| H02 | 64 | 40.6% | +$0.196 | [−$0.403, +$0.795] | n<100 |
| H03 | 37 | 43.2% | +$0.302 | [−$0.496, +$1.100] | n<100 |
| H04 | 37 | 32.4% | −$0.146 | [−$0.900, +$0.607] | n<100 |
| H05 | 35 | 14.3% | −$0.861 | [−$1.450, −$0.271] | n<100 |
| H06 | 36 | 30.6% | −$0.054 | [−$0.804, +$0.696] | n<100 |
| H07 | 31 | 19.4% | −$0.439 | [−$1.178, +$0.300] | n<100 |
| H08 | 35 | 28.6% | +$0.409 | [−$0.447, +$1.264] | n<100 |
| H09 | 28 | 14.3% | −$0.563 | [−$1.153, +$0.027] | n<100 |
| H10 | 38 | 34.2% | +$0.141 | [−$0.530, +$0.811] | n<100 |
| **H11** | **71** | **35.2%** | **+$0.191** | [−$0.363, +$0.744] | n<100 |
| H12 | 36 | 36.1% | −$0.033 | [−$0.797, +$0.730] | n<100 |
| H13 | 36 | 33.3% | +$0.023 | [−$0.737, +$0.783] | n<100 |
| H14 | 47 | 29.8% | −$0.107 | [−$0.713, +$0.498] | n<100 |
| H15 | 36 | 30.6% | −$0.124 | [−$0.946, +$0.699] | n<100 |
| H16 | 30 | 16.7% | −$0.715 | [−$1.362, −$0.068] | n<100 |
| H17 | 21 | 38.1% | −$0.387 | [−$1.973, +$1.198] | n<100 |
| H18 | 25 | 60.0% | +$0.301 | [−$0.526, +$1.128] | n<100 |
| H21 | 39 | 51.3% | +$0.607 | [−$0.069, +$1.283] | n<100 |
| H22 | 40 | 32.5% | −$0.137 | [−$0.808, +$0.534] | n<100 |
| H23 | 57 | 33.3% | +$0.004 | [−$0.588, +$0.597] | n<100 |

Maximum hour n = H11 (n=71). No hour reaches n≥100.

**CONCLUSION: DATA_MISSING (n ceiling — max n=71 across all hours)**
The 53.8h VOLARB era could not produce n≥100 for any single hour. H05 and H16 show alarming WR (14.3%/16.7%) and negative EV CIs touching negative territory throughout, but both are n<40 — watchlist-only. H01 shows strong positive EV (+$0.784) at n=66 but INCONCLUSIVE.

**FAILURE_MET:** No — n threshold never reached for any hour.

**IF_DEPLOYED:** N/A — VOLARB retired; post-mortem only. Informational: H05 (WR=14.3%) and H16 (WR=16.7%) were the worst hours in the window, consistent with H05 being LDA-blocked in the prior strategy. If VOLARB had continued, these would be first candidates for hour gating at n≥40 watchlist.

---

### H3 — Per-Ask-Band EV vs Backtest Shape

**HYPOTHESIS:** Backtest EV was modeled across the full ask range [0.10, 0.60). The convex backtest shape (higher EV at extremes due to fee structure) may have inverted or shifted live. Identifying the drag band guides EDGE_FLOOR or ASK gate tightening.

**METHOD:** Slice deduped trades by entry_price band: [0.10,0.20), [0.20,0.30), [0.30,0.40), [0.40,0.50), [0.50,0.60). Compute n, WR, avg_ask, EV/trade (net_pnl), CI95. Flag bands at n≥100 where CI_hi < baseline CI lower (+$0.244).

**RESULT:**

| Band | n | WR% | avg_ask | EV/trade | CI95 | total net | vs_CI |
|---|---|---|---|---|---|---|---|
| [0.10,0.20) | 91 | 18.7% | 0.160 | +$0.149 | [−$0.336, +$0.635] | +$13.60 | n<100 |
| **[0.20,0.30)** | **227** | **26.4%** | **0.250** | **−$0.003** | **[−$0.279, +$0.272]** | **−$0.73** | **within CI** |
| **[0.30,0.40)** | **390** | **38.7%** | **0.347** | **+$0.120** | **[−$0.112, +$0.353]** | **+$46.99** | **within CI** |
| [0.40,0.50) | 158 | 46.8% | 0.428 | +$0.071 | [−$0.306, +$0.448] | +$11.17 | n<100 |
| [0.50,0.60) | 9 | 44.4% | 0.522 | −$0.435 | [−$2.147, +$1.276] | −$3.92 | n<100 |
| out-of-gate | 12 | 8.3% | — | −$1.441 | [−$3.641, +$0.760] | **−$17.29** | n<100 |

Only [0.20,0.30) and [0.30,0.40) reach n≥100. Both are "within CI" (CI_hi overlaps baseline CI lower). Key observations:

- **[0.20,0.30) is the worst performing meaningful band at n≥100**: WR=26.4% vs 38.7% for [0.30,0.40); EV near zero (−$0.003). CI upper (+$0.272) exceeds baseline lower (+$0.244) by only $0.028 — within CI by margin, not actionable by the strict rule.
- **[0.30,0.40) is the strategy's backbone** (44% of all trades): EV=+$0.120, WR=38.7%, total=+$46.99.
- **Backtest shape inverted in the low-ask zone**: The backtest projected higher EV at extremes (fees near zero). Live data shows [0.10,0.20) WR=18.7% vs [0.30,0.40) WR=38.7%. The cheap-ask convexity thesis did not hold for VOLARB.
- **Out-of-gate leakage bug**: 12 trades with ask < 0.10 or > 0.60 slipped through ASK_FLOOR/ASK_CEIL. Prices observed: 0.01, 0.02, 0.03, 0.04, 0.05, 0.08, 0.09, 0.684, 0.694. Total loss: −$17.29 (WR=8.3%, avg −$1.44/trade).

**CONCLUSION: INCONCLUSIVE for formal blocking (no band hits BELOW_CI at n≥100). Bug flag: out-of-gate leakage.**
No band is definitively below CI. [0.20,0.30) near-zero EV at n=227 is structurally concerning but within CI. The gate-leakage bug (12 trades, −$17.29) is actionable as an engineering fix.

**FAILURE_MET:** No (all n≥100 bands within CI).

**IF_DEPLOYED:** Gate-leakage fix: 12 trades lost $17.29 (avg −$1.44/trade). Moot for VOLARB (retired). Auditor should verify CAS_LOWASK enforces its ask bounds without similar leakage.

---

### H7 — Watchlist Cell Trajectories

**HYPOTHESIS:** Prior scout (2026-05-20) flagged ETH overall below CI [CI_hi=+$0.231 < +$0.244] and 'up' direction below CI [CI_hi=+$0.192 < +$0.244]. With the VOLARB era now closed, compare the last-24h-of-era slice vs the prior segment to check for divergence.

**METHOD:** Split deduped trades at T = era_end − 86400 (2026-05-18T02:50Z). Compute EV/CI per segment for ETH and 'up' direction. Flag cells diverging >2σ from prior segment. Additionally compute all 6 asset×direction sub-cells.

**RESULT — ETH trajectory:**

| Window | n | WR% | EV/trade | CI95 |
|---|---|---|---|---|
| Full VOLARB era | 305 | 32.5% | −$0.035 | [−$0.302, +$0.231] |
| Prior to last 24h (days 1–1.2) | 258 | 31.8% | −$0.057 | [−$0.349, +$0.235] |
| Last 24h of era (day 2.2) | 47 | 36.2% | +$0.081 | [−$0.573, +$0.736] |

ETH slightly recovered in the final 24h (EV: −$0.057 → +$0.081), but n=47 is INCONCLUSIVE. No statistically significant divergence.

**RESULT — 'up' direction trajectory:**

| Window | n | WR% | EV/trade | CI95 |
|---|---|---|---|---|
| Full VOLARB era | 393 | 30.0% | −$0.032 | [−$0.257, +$0.192] |
| Prior to last 24h (days 1–1.2) | 316 | 30.7% | +$0.021 | [−$0.230, +$0.272] |
| Last 24h of era (day 2.2) | 77 | 27.3% | −$0.251 | [−$0.759, +$0.258] |

'Up' direction worsened sharply in the final 24h: EV dropped from +$0.021 → −$0.251 (Δ = $0.272). Full-era below-CI signal is driven almost entirely by the last 24h. Prior-to-last-24h 'up' EV (+$0.021) was within CI. The Δ/$0.272 vs prior-segment SE (~$0.13) ≈ **2.1σ** — borderline flag.

**RESULT — Asset × Direction sub-cells (all n<100):**

| Cell | n | WR% | EV (net) | CI95 | n-status |
|---|---|---|---|---|---|
| BTC/up | 129 | 27.9% | −$0.060 | [−$0.443, +$0.323] | n<100 |
| BTC/down | 157 | 36.9% | +$0.200 | [−$0.162, +$0.563] | n<100 |
| ETH/up | 137 | 29.2% | −$0.053 | [−$0.443, +$0.337] | n<100 |
| ETH/down | 168 | 35.1% | −$0.021 | [−$0.386, +$0.345] | n<100 |
| SOL/up | 127 | 33.1% | +$0.018 | [−$0.379, +$0.415] | n<100 |
| SOL/down | 169 | 42.6% | +$0.205 | [−$0.158, +$0.567] | n<100 |

'Up' drag is consistent across all three assets (WR 27.9/29.2/33.1% vs 36.9/35.1/42.6% for 'down'). No sub-cell reaches n≥100.

**CONCLUSION: INCONCLUSIVE at sub-cell level (all n<100). 'up' direction shows ~2.1σ terminal deterioration.**
The below-CI signal for 'up' direction in the prior scout was confirmed to be a late-era phenomenon — the prior-to-last-24h window was within CI (+$0.021). The final 24h was the driver of the aggregate signal. Archived as pathology note for future strategy design.

**FAILURE_MET:** No — VOLARB retired; no active kill switch.

**IF_DEPLOYED:** 'up' direction terminal drag: final-day incremental loss vs prior run rate ≈ −$19.33. Structural lesson for successor strategies: BUY_YES (bullish) tokens in 5m windows exhibited structurally lower WR than BUY_NO (bearish), consistent with asymmetric market-maker hedging behavior. Successor strategies should validate direction asymmetry early (n≥100 each within the first week).

---

## Priority Signal for Next Implementation

**VOLARB is retired. No deployment action is possible on VOLARB gates.**

Strongest findings from this cycle at n≥100:
- **H3 out-of-gate bug** [n=12, −$17.29]: Ask bounds (ASK_FLOOR=0.10, ASK_CEIL=0.60) were not fully enforced — 12 trades slipped through at prices 0.01–0.09 and 0.684–0.694. Not a strategy signal; a gate enforcement bug. **Moot for VOLARB, verify in CAS_LOWASK.**
- **H3 [0.20,0.30) near-zero EV** [n=227, EV=−$0.003, within CI]: The low-ask band (avg ask $0.25) produced near-zero EV in live trading, vs the backtest convexity thesis predicting higher EV at extremes. This pattern should be monitored in CAS_LOWASK (ask range 0.05–0.50).

**Net verdict: No actionable VOLARB signal this cycle — era closed, n_VOLARB frozen=887.**

---

## Closed-Family Confirmations

Re-validated as null or permanently closed this cycle:

- **H2 per-hour**: all n<100, no formal signal. Max hour n=71 (H11). Closed with VOLARB retirement.
- **H3 per-ask-band**: [0.20,0.30) within CI at n=227; [0.30,0.40) within CI at n=390. No BELOW_CI band. Out-of-gate leakage bug (12 trades) noted. Closed.
- **H5 term_remaining_s logging bug**: field all=0.0, never populated at entry. Moot — VOLARB retired. Closed.
- **H7 'up' direction**: final-24h deterioration confirmed (~2.1σ vs prior era, driven by last 24h). ETH slightly improved in final 24h (n=47, inconclusive). Both archived; no lever exists.
- **VOLARB overall (final post-mortem)**: kline EV=−$0.036/trade; net EV=+$0.056/trade. Strategy did not deliver backtest baseline on the resolution metric. Discrepancy attributable to mark-to-market profits unwinding at resolution. **All VOLARB research families permanently closed.**

---

## Open Requests for Auditor / Shadow Validator

**Cells trending to n≥100 within next 24h:**
- None. VOLARB n is frozen. No VOLARB-specific cells will reach threshold.

**Shadow loggers past threshold for CAS_LOWASK era:**
- `exit_policy_shadow` (2026-05-19: n=2428; 2026-05-20: n=2535; 2026-05-21: n=1364 through noon): all well above the 500-row pre-registration threshold. Shadow Validator should run CAS_LOWASK exit candidate validation against these batches.
- `hold_path` (2026-05-19: n=126,334; 2026-05-20: n=133,183; 2026-05-21: n=70,146): far past any threshold. Primary source for exit candidate evaluation in CAS_LOWASK era.

**Phase 2 longshot recorder (VOLARB ask < 0.10):**
- Status: **NOT DEPLOYED** (shadow file empty, absent from shadow_summary).
- **CLOSED — MOOT**: VOLARB retired 2026-05-19. Do not build.
- Sub-0.10 final performance: n=10, WR=0.0%, EV=−$0.911/trade (n too small, but directionally correct for keeping ASK_FLOOR≥0.10).

**Gate-leakage audit (for Auditor — CAS_LOWASK):**
- 12 VOLARB trades slipped below ASK_FLOOR (0.01–0.09) and above ASK_CEIL (0.684–0.694), losing −$17.29. Auditor should verify CAS_LOWASK enforces `0.05 ≤ ask ≤ 0.50` (or 0.60 with range_pos>0.8) without similar leakage. Check `strategy/cas_lowask.py` ask gate enforcement.

**research_status.md is stale (last updated 2026-05-16 12:50 UTC):**
- Still describes "Active strategy: LDA." Current active strategy is CAS_LOWASK (since 2026-05-19).
- Recommended update: add VOLARB to §2 "Closed research families": `VOLARB strategy | retired 2026-05-19 | replaced by CAS_LOWASK; final n=887, kline EV=−$0.036/trade, net EV=+$0.056/trade; strategy did not deliver backtest baseline on resolution metric`.
- Update §1 active strategy to CAS_LOWASK with current parameters.
