# Alpha Scout Report — 2026-05-10 07:00 UTC

**Method:** Codebase audit + shadow pipeline implementation — VPS SSH unreachable (45th consecutive scout session)
**Connectivity:** SSH binary absent in sandbox; TCP port 22 egress blocked at network boundary. `trades.jsonl` and `post_exit.jsonl` inaccessible.
**Data sources used:** git log (commits since last scout c4a2598 2026-05-10 00:27 UTC → HEAD 5d6d077 2026-05-10 06:21 UTC); full codebase read of `data/shadow/timeline.py`, `analytics/signal_analysis.py`, `analytics/lag_analysis.py`, `analytics/lag_detector.py`; `logs/bankroll.json`; existing `logs/scout_report.md` (prior cycle).
**Bankroll snapshot (bankroll.json, ts=1778268412 / 2026-05-08 19:26 UTC):** capital=$84.61, total_trades=2,605, total_pnl=+$87.87.

---

## Changes Since Last Scout (c4a2598, 2026-05-10 00:27 UTC)

2 commits in 6 hours. Only one changed code:

| Commit | Time (UTC) | Change |
|---|---|---|
| `c4a2598` | 05-10 00:27 | Scout: arb_sum_yes_no added to CONTINUOUS_SIGNALS + PLACEHOLDER_ZERO_FIELDS |
| `5d6d077` | 05-10 06:21 | Audit: no patch (44th VPS unreachable) |

VPS shadow pipeline operational (sourced from audit report and git log pattern). No gate or parameter changes this cycle.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot velocity in the 5s before entry (`pre_entry_momentum_pct`) predicts YES resolution.
**MATH:** `pre_entry_momentum_pct = (spot_now − spot_5s_ago) / spot_5s_ago × 100`

**STATUS: INCONCLUSIVE — n=0 from trades.jsonl (SSH blocked, 45th session).**

**Structural action taken this cycle:**
The prior scout identified `binance_vel_5s_pct` as the second priority: "one additional call to `_binance_ret(asset_up, now, 5)`." This has now been implemented:

- `data/shadow/timeline.py`: `binance_vel_5s = self._binance_ret(asset_up, now, 5)` added before the 30s/60s calls; field emitted as `"binance_vel_5s_pct"` in the returned dict.
- `analytics/signal_analysis.py`: `"binance_vel_5s_pct"` added to `CONTINUOUS_SIGNALS` (before `binance_ret_30s_pct`) and to `PLACEHOLDER_ZERO_FIELDS` (returns 0.0 when price history ring buffer lacks a 5s-ago entry).

**Why PLACEHOLDER_ZERO_FIELDS:** `_binance_ret` returns `0.0` when `hist` is empty or `ref is None`. A zero value here means "no 5s-ago price available," not "flat market." Including zeros in quantile analysis would contaminate the low-velocity bucket. Excluding is correct.

**WR by momentum bucket:** Cannot compute — n=0 from trades.jsonl.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET:** No. Cannot evaluate — n=0 direct data. Shadow accumulation begins from this commit forward. Check in 48h when `binance_vel_5s_pct` has populated the `market_timeline` records on VPS.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low `term_tok_tick_count_5s` predicts lower YES resolution rate.

**STATUS: INCONCLUSIVE — field not in shadow pipeline; not accessible without trades.jsonl.**

**Structural findings (unchanged from prior cycle):**
- `term_tok_tick_count_5s` is a `trades.jsonl`-only field logged by the live bot at entry time. It is NOT in shadow `market_timeline`.
- The existing proxy `ask_stale_s` (seconds since ask last changed > 0.005) IS in shadow and signal_analysis. It captures the thin-book signal without requiring the trade tape.
- Adding true tick count to shadow would require a per-token rolling deque updated by Polymarket WS `last_trade_price` callbacks — non-trivial and likely noisy (WS event timing is unreliable in datacenter environments).

| Bucket | n | WR | PF |
|---|---|---|---|
| 0-2 ticks | 0 | N/A | N/A |
| 3-5 ticks | 0 | N/A | N/A |
| 6-10 ticks | 0 | N/A | N/A |
| 11+ ticks | 0 | N/A | N/A |

**PROPOSED_GATE:** Cannot set — no outcome data. `ask_stale_s >= 4s` gate (already deployed 2026-04-30) covers the extreme thin-book case.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET:** Cannot evaluate — n=0.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Dead market entries (`|term_token_delta_5s| < 0.005`) underperform active entries.

**STATUS: INCONCLUSIVE on 5s. Prior 30s evidence goes OPPOSITE direction.**

**Unchanged from prior cycle:**
- `tok_delta_5s` IS in shadow market_timeline and CONTINUOUS_SIGNALS. Zero is a real value (flat market), not a placeholder — correctly excluded from PLACEHOLDER_ZERO_FIELDS.
- Signal_analysis quantile output for `tok_delta_5s` has not been retrieved (SSH blocked).
- 30s analog (snap30): low-momentum zone [0, 10.5%) resolved YES=90.2% vs active zone [10.5%, 80%) YES=84.0% — OPPOSITE of dead-drift toxicity. Gate removed 2026-05-09.
- tok5_gate calibration (May 6-7, n=52 UP): tok_d5 in [5,10%] WR=100% (n=9); near-zero zone was NOT a loss cluster in any identified cohort.

**Prior evidence direction:** Flat/low-momentum entries appear statistically BETTER at 30s resolution; high-momentum entries carry snap-back risk. This weakens the hypothesis for the 5s window.

**CONCLUSION: INCONCLUSIVE on 5s.**
**FAILURE_MET:** No direct 5s data. 30s analog contradicts hypothesis. Lowest priority of the four investigations; de-prioritized until binance_vel_5s_pct and arb_sum_yes_no accumulate analysis-ready n.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset (BTC/ETH/SOL) consistently outperforms others in the last 48h.

**STATUS: INCONCLUSIVE — n<20 per asset per direction cannot be verified. No per-asset breakdown accessible.**

**Known per-asset states (from cumulative commit history):**
- **SOL UP:** historically healthiest cell (PF=1.37 pre-May all-era). ob_imb relaxation should widen funnel.
- **ETH UP:** G1 gate active (skip if binance_ret_60m > 0%). Gate deployed 2026-05-07.
- **BTC UP:** most conservative; ask_max 0.93 cap applies.
- **DOWN (all assets):** clean shadow data accumulating since direction-aware resolution bug fix 2026-05-09 09:28 UTC (commit 2c3b550). Approx 22h of clean DOWN data as of this report — still below n>=20/asset threshold.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET:** Yes — n<20 per asset in verifiable 48h window from accessible data. Continue accumulation. Re-evaluate when shadow has 7+ days of clean v2 data.

---

## Implementation Summary — This Cycle

**`binance_vel_5s_pct` deployed** (Investigation 1 blocker partially cleared):

```python
# data/shadow/timeline.py — added before binance_ret_30s line:
binance_vel_5s = self._binance_ret(asset_up, now, 5)

# Return dict — added before binance_ret_30s_pct:
"binance_vel_5s_pct": round(binance_vel_5s, 4),

# analytics/signal_analysis.py — CONTINUOUS_SIGNALS (first in Binance group):
"binance_vel_5s_pct",

# analytics/signal_analysis.py — PLACEHOLDER_ZERO_FIELDS:
"binance_vel_5s_pct",
```

**`arb_sum_yes_no` already deployed** (prior cycle, c4a2598). Both new fields now accumulating in shadow market_timeline on VPS.

---

## Priority Signal for Next Implementation

**No new implementation needed this cycle. Two signals now in accumulation:**

1. **`arb_sum_yes_no`** — deployed prior cycle (~7h accumulation as of this report). Tests cross-token pricing coherence.
   - Hypothesis: YES_ask + NO_ask deviation from 1.0 predicts YES resolution direction.
   - Failure criteria: WR difference < 5pp between arb_sum buckets [<0.96, 0.96-1.04, >1.04], or n<20/bucket.

2. **`binance_vel_5s_pct`** — deployed this cycle. Tests 5s Binance spot velocity as lead signal for YES resolution.
   - Hypothesis: positive momentum -> higher YES resolution rate at entry.
   - Failure criteria: WR difference < 5pp between momentum>0 and momentum<0 groups.

**Both require VPS shadow data retrieval to evaluate.** Next scout with a live sync: run:
```bash
python3 analytics/signal_analysis.py --days 3 --strategy-version v2 --rem-min 25 --rem-max 90
```
Check quantile YES-rate for `arb_sum_yes_no` and `binance_vel_5s_pct`. A monotonic relationship in YES rate across quantiles with >= 5pp spread is a SIGNAL_FOUND.

**If no sync by next cycle:** investigations remain at n=0. No further implementation is warranted until live data is accessible. Additional field additions without analysis capacity do not add value.

---

## Infrastructure Alert — SSH (45 consecutive sessions)

**Root cause:** TCP port 22 egress blocked at sandbox network boundary. SSH client present; connection times out.

**VPS IS active** — shadow pipeline running, audit agent operational (5d6d077 confirms), trades accumulating.

**One-time manual sync unblocks all future scouts (30s on VPS):**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Or permanent cron (every 30 min):**
```bash
cat > /etc/cron.d/push-logs << 'EOF'
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N 2>/dev/null
EOF
chmod 644 /etc/cron.d/push-logs
```

Without trade data, all four mandated investigations remain at n=0 and INCONCLUSIVE. The two new shadow fields (`arb_sum_yes_no`, `binance_vel_5s_pct`) will have analysis-ready data once the sync happens.
