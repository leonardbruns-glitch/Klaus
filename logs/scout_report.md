# VOLARB Alpha Scout — 2026-05-20T12:41Z

## Snapshot + Baseline

| field | value |
|---|---|
| snapshot_ts | 2026-05-20T12:33:49Z (~8 min old — FRESH) |
| Klaus state | active |
| Capital | $49.35 (bankroll.json) |
| VOLARB n (live era, deduped) | 887 |
| VOLARB date range | 2026-05-16 21:00 – 2026-05-19 02:50 UTC (~53.8 h / 2.2 days) |
| $1-equiv baseline CI | [+$0.244, +$0.352]/trade |

**Pre-flight:**
- snapshot_ts age: ~8 min — PASS
- integrity_report.json: absent (no `blocks_agent_run` — treated as PASS, file added to open requests)
- Code sync check: SNAPSHOT.md HEAD=9edb6a75 — noted

**⚠ research_status.md CONTRADICTION:**
`research_status.md` (last updated 2026-05-16 12:50 UTC) states "Active strategy: LDA." But live `trades.jsonl` contains 887 `bond_entry_class=='VOLARB'` records, ALL with `ts_open >= 1778965200` (2026-05-16 21:00 UTC). VOLARB was activated ~8 h after the last research_status update. The contradiction is raised here per §0; VOLARB analysis proceeds as mandated by this prompt.

**⚠ HEADLINE: Overall VOLARB EV is BELOW backtest CI.**
- Live: n=887, EV=+$0.056/trade (net_pnl), CI95=[−$0.097, +$0.210]
- Backtest baseline: CI=[+$0.244, +$0.352]
- Live CI upper (+$0.210) < baseline CI lower (+$0.244) → aggregate performance is outside the predicted range at n=887.
- kline_pnl (held-to-resolution metric): EV=−$0.036/trade, total=−$31.81. Net_pnl total=+$49.82. Discrepancy = $81.63. Flagged for Auditor: if kline_pnl is the reliable metric, the strategy may be losing money in aggregate.

---

## Continuity vs Prior Scout

- Prior scout file: absent (first run on this branch)
- Investigations carried over: none
- Resolved/closed since prior: n/a

---

## Investigations

### H1 — Per-Asset Alpha Allocation

**HYPOTHESIS:** Backtest had BTC as alpha asset (projected EV +$14.81 vs ETH +$2.53, SOL +$1.30). Live data may show asset-level divergence from that shape.

**METHOD:** Filter `bond_entry_class=='VOLARB' AND ts_open >= 1778965200`, deduplicate by first-fire per token_id, compute EV/WR/CI95(net_pnl) per asset. Flag cells at n≥100 with CI upper < baseline CI lower (+$0.244).

**RESULT:**

| Asset | n | WR | EV (net_pnl) | EV (kline_pnl) | CI95 (net) | vs baseline |
|---|---|---|---|---|---|---|
| BTC | 286 | 32.9% | +$0.083 | +$0.059 | [−$0.181, +$0.347] | within CI |
| **ETH** | **305** | **32.5%** | **−$0.035** | **−$0.088** | **[−$0.302, +$0.231]** | **BELOW CI** |
| SOL | 296 | 38.5% | +$0.125 | −$0.074 | [−$0.143, +$0.392] | within CI |

Note on SOL: net_pnl is positive but kline_pnl is −$0.074/trade (total −$21.87). Largest net/kline split of any asset. SOL was LDA-blocked (2026-05-15); trades freely in VOLARB.

**CONCLUSION: SIGNAL_FOUND (ETH below CI)**
ETH n=305 ≥ 100. CI upper +$0.231 < baseline lower +$0.244 — live CI does not overlap backtest CI. ETH is the primary drag asset: WR=32.5%, EV=−$0.035 net / −$0.088 kline. BTC is within CI but WR=32.9% is below the 40% backtest expectation.

**FAILURE_MET:** No. ETH EV is negative but no per-asset kill switch exists; strategy-level thresholds not triggered.

**IF_DEPLOYED:** Raising EDGE_FLOOR globally is the only lever for per-asset exposure reduction. At $1 stake, ETH drag = −$10.68 net / −$26.89 kline over 2.2 days. Auditor action required: check ETH edge distribution vs BTC/SOL before any EDGE_FLOOR patch.

---

### H5 — Seconds-to-Resolution Slice

**HYPOTHESIS:** Phase 1 gate REM_MIN_S=60 / REM_MAX_S=280 was set from backtest. Live EV may vary by time-to-resolution bucket.

**METHOD:** Slice `term_remaining_s` into [60–100s), [100–160s), [160–220s), [220–280s); compute EV/CI per slice. Requires n≥100/slice.

**RESULT:**

| Slice | n | EV | CI95 |
|---|---|---|---|
| [60–100s) | 0 | — | — |
| [100–160s) | 0 | — | — |
| [160–220s) | 0 | — | — |
| [220–280s) | 0 | — | — |

`term_remaining_s`: 887/887 field present, all = 0.0. **Logging bug.** Field written but never populated at VOLARB entry time. `sniper_lag_remaining` is identically 0.0 for all 887 records. Neither field captures seconds-to-resolution.

**CONCLUSION: DATA_MISSING**
H5 cannot be evaluated. REM_MIN_S=60 / REM_MAX_S=280 gate is unvalidated against live data. Shadow recorder spec proposed below.

**FAILURE_MET:** N/A — data absent.

**IF_DEPLOYED:** N/A. Proposed shadow recorder:
- Fix `term_remaining_s = window_end_ts − ts_entry` at VOLARB entry in `strategy/volarb.py`
- Alternatively: shadow logger `data/shadow/volarb_rem_shadow.jsonl`
- Schema: `{ts, trade_id, token_id, asset, bond_outcome_direction, entry_price, seconds_to_resolution_at_entry, net_pnl (filled at close), kline_pnl (filled at close)}`
- Pre-register n=100 per slice for H5 validation

---

### H6 — Direction Asymmetry (up vs down)

**HYPOTHESIS:** Backtest had no direction split. Live may show systematic asymmetry — 'up' tokens (BUY_YES on bullish move) vs 'down' tokens.

**METHOD:** Split `bond_outcome_direction ∈ {up, down}`, compute EV/WR/CI95(net_pnl) per direction. n≥100 required.

**RESULT:**

| Direction | n | WR | EV (net_pnl) | EV (kline_pnl) | CI95 (net) | vs baseline |
|---|---|---|---|---|---|---|
| **up** | **393** | **30.0%** | **−$0.032** | **−$0.070** | **[−$0.257, +$0.192]** | **BELOW CI** |
| down | 494 | 38.3% | +$0.127 | −$0.008 | [−$0.083, +$0.336] | within CI |

Per-asset breakdown (all n<100 — INCONCLUSIVE at this level, directional consistency noted):

| Asset / Dir | n | WR | EV (net) |
|---|---|---|---|
| BTC / up | 129 | 27.9% | −$0.060 |
| BTC / down | 157 | 36.9% | +$0.200 |
| ETH / up | 137 | 29.2% | −$0.053 |
| ETH / down | 168 | 35.1% | −$0.021 |
| SOL / up | 127 | 33.1% | +$0.018 |
| SOL / down | 169 | 42.6% | +$0.205 |

The 'up' underperformance is consistent across all three assets (WR 27.9/29.2/33.1% vs 36.9/35.1/42.6% for 'down').

**CONCLUSION: SIGNAL_FOUND ('up' direction below CI)**
'up': n=393 ≥ 100. CI upper +$0.192 < baseline lower +$0.244. Live CI does not overlap backtest CI. WR=30.0% is at the strategy-level warning floor. 'down' is within CI and EV-positive.

Possible mechanism: Polymarket MMs may price bullish tokens more efficiently (lower taker alpha on 'up' moves), or the 2026-05-16–19 macro regime had asymmetric downward resolution that the backtest's longer window averaged away.

**FAILURE_MET:** No. 'up' WR=30.0% is exactly at the 30% warning floor (kill switch triggers at <30% over 20 trades). Not yet triggered but on the boundary.

**IF_DEPLOYED:** No direction gate exists in PHASE 1 parameters — requires code change (Tier 2 patch). If 'up' entries were eliminated: −393 trades × $0.032 drag = +$12.58 net saved over 2.2 days (~+$69/month at current rate). Highest single-lever opportunity identified this cycle.

---

## Priority Signal for Next Implementation

**Strongest signal: H6 — 'up' direction EV below backtest CI (n=393, CI95 upper +$0.192 < baseline lower +$0.244, WR=30.0% at kill-switch boundary).**

No lever exists in current PHASE 1 parameters to gate by direction. Requires Tier 2 patch. Until then, the only available global knob is EDGE_FLOOR.

**Secondary signal: H1 ETH — EV below backtest CI (n=305, CI95 upper +$0.231 < baseline lower +$0.244).** Lever: EDGE_FLOOR raise, contingent on ETH signal clustering at lower edge values (Auditor to verify).

**Headline concern:** At n=887, overall VOLARB CI=[−$0.097, +$0.210] is already below backtest baseline CI lower (+$0.244). The strategy has not demonstrated backtest-level EV in live trading. Too early to halt (2.2 days), but direction asymmetry (H6) and ETH drag (H1) are both statistically established.

---

## Closed-Family Confirmations

- BOND/LDA strategies: 0 records in VOLARB activation window — correctly filtered
- SNIPER/MOM/DISCOVER: 0 records in VOLARB activation window

---

## Open Requests for Auditor / Shadow Validator

**Auditor watchlist (cells at n≥100 with EV below CI):**
1. ETH (H1): n=305, EV below CI — check ETH edge distribution vs BTC/SOL; if ETH signals cluster at lower edge values, EDGE_FLOOR raise is actionable
2. 'up' direction (H6): n=393, EV below CI — check direction × edge distribution; if 'up' signals cluster lower, EDGE_FLOOR preferentially sheds 'up' trades

**Cells trending to n≥100 within next 24h (Auditor watch):**
- BTC/down: n=157 → ~100 more trades needed (~18h at current rate ~5.5 trades/hr BTC)
- ETH/down: n=168 → similar timeline
- SOL/down: n=169 → similar timeline

**Shadow loggers needing deployment:**
1. **`term_remaining_s` fix (CRITICAL):** Logging bug — field is 0.0 for all 887 VOLARB records. Must fix `strategy/volarb.py` to populate `term_remaining_s = window_end_ts − ts_entry` before H5 is evaluable. REM_MIN_S/REM_MAX_S gates are currently unvalidated live.
2. **`volarb_longshot_shadow.jsonl` (Phase 2 gate):** ABSENT. Logger never deployed. Phase 2 (ask<0.10) gated on n≥100 OOS — currently 10 records at ask<0.10 in live data but unlogged. Spec above (H5 section).
3. **`integrity_report.json`:** Absent from data-mirror. Ops should confirm this is intentional for the VOLARB era.

**kline_pnl vs net_pnl discrepancy (urgent clarification needed):**
- net_pnl total: +$49.82 | kline_pnl total: −$31.81 | delta: $81.63
- Prompt specifies net_pnl as win metric for VOLARB ("holds to resolution"). research_status.md specifies kline_pnl for LDA. Which is canonical for VOLARB? If kline_pnl is correct, the strategy is in aggregate loss, which changes the urgency of the H1/H6 signals above.

**research_status.md update needed:**
File is stale (2026-05-16 12:50 UTC). Should reflect VOLARB as active strategy, activation ts 1778965200, and the LDA → VOLARB transition with updated open research candidates.
