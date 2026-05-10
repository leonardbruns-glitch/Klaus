# Alpha Scout Report — 2026-05-10 00:24 UTC

**Method:** Commit-embedded analysis + shadow pipeline codebase audit — VPS SSH unreachable (44th consecutive scout session)
**Connectivity:** SSH binary absent in sandbox; TCP port 22 egress blocked at network boundary. No direct trades.jsonl or post_exit.jsonl retrievable.
**Data sources used:** git log (commits since last scout 6d9a2d2 2026-05-09 10:15 UTC → HEAD 1465c0f 2026-05-10 00:04 UTC; 9 commits); main.py + data/shadow/ codebase audit; signal_analysis.py + gate_relaxation.py source review; state_log.md; bankroll.json; commit message embedded results from VPS shadow pipeline runs.
**Bankroll snapshot (bankroll.json in repo):** capital=$84.61, total_trades=2605, total_pnl=+$87.87, saved_ts≈2026-05-08 19:26 UTC. Stake cap at $7/trade (active drawdown mode).

---

## Changes Since Last Scout Report (2026-05-09 10:15 UTC)

9 commits landed in 14 hours. Key deployments:

| Commit | Time (UTC) | Change | Evidence base |
|---|---|---|---|
| `8d9e755` | 05-09 12:33 | entry: revert terminal zone 25-120s → 25-90s | rem 90-120s: n=55 WR=58% net=-$53.97; rem 25-90s: n=42 WR=71% net=+$17.09 (May 8-9) |
| `69d4028` | 05-09 13:32 | gate: ob_imb floor 0.20 → 0.0 | signal_analysis n=2614 dirty cohort: solo-fail YES=89.9% vs pass=76.0% |
| `990b7f6` | 05-09 19:49 | gate: ask_max 0.95 → 0.93 (UP) | shadow n=56: 14.3% of entries in [0.93,0.96) dead zone; ≤+2.15% upside at ask=0.93 |
| `2584a13` | 05-09 20:07 | analytics: gate_relaxation v2 + multi_exit_replay full-cohort | PT95 +4.32% > PT97 +3.86% full-cohort (clean); HOLD_TO_CLOSE +1.70% > PT95+fallback +1.19% (dirty) |
| `849b768` | 05-09 20:13 | analytics: Phase 2 contamination audit fixes (C1-C4+H1-H2) | clean re-run: joined rows 3292→1037; gate-PASS YES 84.6%→92.7%; ob_imb solo-fail n=141 YES=80.1% |

**Critical finding from contamination audit (849b768):**
The dirty cohort (n=3292) included v1+v2 shadow versions and rem up to 120s. The clean cohort (n=1037: v2 only, rem 25-90s, post-config-from-19:49 UTC) shows:
- Gate-PASS YES rate: **92.7%** (was dirty 84.6%)
- ob_imb solo-fail (ob_imb < 0.0, all other gates pass): **n=141, YES=80.1%**

This means the ob_imb=0.0 floor IS adding value on clean data (12.6pp gap: 92.7% pass vs 80.1% blocked). The gate removal from 0.20→0.0 was the right direction (the 0.0-0.20 zone was incorrectly blocked in dirty analysis), but the floor at 0.0 is correctly placed: negative-imbalance tokens genuinely resolve YES less often.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot velocity in the 5s before entry (`pre_entry_momentum_pct`) predicts YES resolution.
**MATH:** `pre_entry_momentum_pct = (spot_now − spot_5s_ago) / spot_5s_ago × 100`

**STATUS: INCONCLUSIVE — n=0 from trades.jsonl (SSH blocked). Shadow pipeline gap persists.**

**Structural findings (codebase audit, this cycle):**
- The `_binance_ret` method in `data/shadow/timeline.py:448` already supports arbitrary time windows and reads from `feed._price_history`. A 5s variant is one additional call:
  ```python
  binance_vel_5s = self._binance_ret(asset_up, now, 5)  # already works
  ```
- Current shadow fields: `binance_ret_30s_pct`, `binance_ret_60s_pct`, `binance_ret_5m_pct`, `binance_ret_1m_pct`, `binance_ret_60m_pct` — none are 5s.
- All Binance return fields are in `PLACEHOLDER_ZERO_FIELDS` (excluded from signal_analysis when value=0). A 5s field would also need to be in that set (price history ring buffer may not always have a 5s-ago entry).
- `signal_analysis.py` CONTINUOUS_SIGNALS list does NOT include a 5s Binance velocity field.

**WR by momentum bucket:** Cannot compute — n=0 from trades.jsonl.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET:** Cannot evaluate — n=0 direct data. The infrastructure gap (no 5s Binance velocity in shadow) is the blocker. Adding it requires 3 lines of code.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low `term_tok_tick_count_5s` (thin/dead book pre-entry) predicts lower YES resolution rate.

**STATUS: INCONCLUSIVE — field is trades.jsonl-only; not in shadow market_timeline.**

**Structural findings:**
- Shadow pipeline captures `token_trade` records (Polymarket CLOB last_trade_price events per the schema in `data/shadow/_schema/v1.json`). These are written to `logs/shadow/hot/<date>/`. They contain `(token_id, ts_ms_local, price, size)`.
- The `token_trade` records are written to disk but NOT accumulated in a live ring buffer accessible to `TimelineSampler._build_record`. Computing a rolling 5s trade count at `_build_record` time would require maintaining a per-token deque updated by Polymarket WS callbacks — a non-trivial addition.
- **Deployed proxy**: `ask_stale_s` (seconds since ask last changed >0.005) IS in shadow market_timeline and CONTINUOUS_SIGNALS. Gate `ask_stale_s >= 4s` was deployed on 2026-04-30. This captures the thin-book signal (no price movement = no activity) without requiring trade tape.
- The `ask_stale_s` proxy and the tick-count hypothesis are testing the same underlying construct (market activity level). If `ask_stale_s` shows a signal in signal_analysis output, the tick-count hypothesis is validated by proxy.

| Bucket | n | WR | PF |
|---|---|---|---|
| 0–2 ticks | 0 | N/A | N/A |
| 3–5 ticks | 0 | N/A | N/A |
| 6–10 ticks | 0 | N/A | N/A |
| 11+ ticks | 0 | N/A | N/A |

**PROPOSED_GATE:** Cannot set — no direct outcome data. The `ask_stale_s >= 4s` gate already captures the extreme thin-book case.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET:** Cannot evaluate — n=0 from trades.jsonl. Proxy signal (`ask_stale_s`) already deployed and gating the most extreme thin-book entries.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Dead market entries (`|term_token_delta_5s| < 0.005`) underperform active entries.

**STATUS: INCONCLUSIVE on 5s specifically. 30s analog CONTRADICTS hypothesis direction.**

**New finding this cycle:**
The `tok_delta_5s` field IS in shadow market_timeline as `tok_delta_5s` AND is in signal_analysis CONTINUOUS_SIGNALS (NOT in PLACEHOLDER_ZERO_FIELDS, so zero values are included). The clean cohort (n=1037) should have enough data for quantile analysis in signal_analysis.py. However, the contamination audit commit (849b768) does not report the signal_analysis quantile output — only the marginal gate contribution data.

**Available evidence:**
- 30s analog: snap30 gate removed 2026-05-09 because low-momentum zone [0,10.5%) resolved YES=90.2% vs active zone [10.5%,80%) YES=84.0% — OPPOSITE of dead-drift toxicity.
- tok5_gate calibration (May 6-7, n=52 UP): tok_d5 in [5,10%] = 100% WR (n=9); tok_d5 > 10% = reversal/snap-back risk. The near-zero zone was NOT identified as a loss cluster.
- Dead drift zone (|tok_d5| < 0.5%) was not separated in any commit-embedded analysis.

**Prior evidence direction:** Flat/low-momentum entries appear statistically BETTER at 30s resolution; active/high-momentum entries carry snap-back risk. This weakens the dead-drift-toxicity prior for the 5s version.

**CONCLUSION: INCONCLUSIVE on 5s. Available 30s evidence goes the OPPOSITE direction.**
**FAILURE_MET:** No direct 5s data. 30s analog contradicts hypothesis. Lowest priority of the four investigations.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset (BTC/ETH/SOL) consistently outperforms others in the last 48h.

**STATUS: INCONCLUSIVE — n<20 per asset per direction cannot be verified. No per-asset breakdown in commit messages.**

**Structural context:**
- Shadow pipeline records `asset` field in market_timeline, gate_trace, and window_resolution.
- Clean cohort total n=1037 — if evenly distributed across 6 cells (3 assets × 2 directions), that's ~173 per cell. In practice, BTC/ETH/SOL UP/DOWN are not evenly distributed.
- DOWN direction: direction-aware resolution join bug fixed 2026-05-09 09:28 (commit 2c3b550). Clean DOWN data has been accumulating since then (~15h by this report, est. 300-600 DOWN records in shadow).
- The contamination audit clean cohort used `--config-effective-from` at the last threshold-change ts (ask_max 19:49 UTC). This constrains to ~4h of data, not 48h.

**Known per-asset states (from state_log.md and commits, cumulative):**
- SOL UP: historically healthiest cell (PF=1.37 pre-May all-era). ob_imb gate relaxation should widen entry funnel.
- ETH UP: G1 gate active (skip if binance_ret_60m > 0%). Gate was deployed 2026-05-07 but shadow labels for UP are clean throughout.
- BTC UP: most conservative historically; ask_max 0.93 cap applies.
- DOWN (all assets): clean shadow data accumulating since 09:28 UTC 2026-05-09. No DOWN-specific gate changes since bug fix.

**CONCLUSION: INCONCLUSIVE — n<20 per asset in verifiable 48h window.**
**FAILURE_MET:** Cannot meet n≥20 criterion from accessible data. Continue data collection. Check again when shadow accumulates 7+ days of clean v2 data.

---

## Critical Embedded Finding — ob_imb Gate Contamination Reversal

From commit 849b768 (Phase 2 contamination audit, 2026-05-09 20:13 UTC):

**Dirty cohort analysis (n=2614, v1+v2 mixed, rem 25-120s):**
- ob_imb solo-fail YES rate: **89.9%**
- Gate-PASS YES rate: **76.0%**
- Action taken: remove ob_imb floor → relaxed to 0.0 (2026-05-09 13:32, commit 69d4028)

**Clean cohort analysis (n=1037, v2 only, rem 25-90s, post-config-drift filter):**
- ob_imb solo-fail YES rate: **80.1%** (n=141)
- Gate-PASS YES rate: **92.7%**
- Implication: **gate adds 12.6pp value on clean data**

The relaxation from 0.20→0.0 was the correct direction — the 0.0–0.20 zone (positive but low imbalance) was wrongly blocked by the dirty analysis. The current floor at 0.0 is correctly placed: truly negative-imbalance tokens (ask-heavy) do resolve YES 12.6pp less often than gate-passers.

**Action: No change to current gate (ob_imb = 0.0 floor is correct). Log this as validated.**

---

## New Variable for Investigation — arb_sum_yes_no

**Field:** `arb_sum_yes_no` in shadow market_timeline (logged since Phase 1, 2026-05-08 07:40 — ~48h of accumulation)
**Status:** NOT in signal_analysis.py CONTINUOUS_SIGNALS. Zero bytes of analysis done.
**Schema doc:** "best_ask + peer_ask; 1.0 = no arb signal, deviation = pricing inefficiency"

**HYPOTHESIS:** For YES token entries at ask 0.78–0.93, `arb_sum_yes_no` near 1.0 indicates efficient two-sided pricing and predicts higher YES resolution. Deviations indicate informed order flow or pricing anomalies.

**MATH:**
```
arb_sum = YES_ask + NO_ask  (sister tokens of same condition_id)

arb_sum ≈ 1.0  → efficient: market prices YES and NO as complementary
arb_sum > 1.05 → both sides overpriced (spread capture, active two-sided trading)
arb_sum < 0.95 → one side underpriced (potential informed flow selling the cheap side)
```

At typical TERMINAL entry (YES_ask ≈ 0.85):
- NO_ask ≈ 0.18 → arb_sum ≈ 1.03 (normal: slight spread premium)
- NO_ask ≈ 0.08 → arb_sum ≈ 0.93 (anomaly: NO is very cheap, bearish for YES)
- NO_ask ≈ 0.28 → arb_sum ≈ 1.13 (anomaly: both sides expensive, illiquid)

**Why non-obvious:**
- All existing signals look at one side: token price/momentum (tok_delta_5s, snap30) or spot price (binance_ret_*) or OB state (ob_imb).
- arb_sum is a cross-token consistency check: it asks whether the market is pricing both sides coherently.
- Very low arb_sum (< 0.95) at high YES_ask means the NO side is not being supported by liquidity providers — potentially because informed traders are pulling NO asks (believing it will resolve YES), OR because the NO side has no activity (ghost liquidity on YES side only).
- Both interpretations have different directionality predictions, making it genuinely informative.

**Python snippet to add:**
```python
# In analytics/signal_analysis.py, CONTINUOUS_SIGNALS list — add after "ask_stale_s":
"arb_sum_yes_no",
```

**Note:** `arb_sum_yes_no = 0.0` when `peer_token_id` is empty (no sister token discovered). This needs to be in PLACEHOLDER_ZERO_FIELDS to exclude undetected-peer rows from analysis:
```python
# In PLACEHOLDER_ZERO_FIELDS set:
"arb_sum_yes_no",
```

**Data availability:** Has been logged in market_timeline since 2026-05-08 07:40 (~48h). The clean cohort n=1037 should have sufficient arb_sum values (peer token is discovered for most BTC/ETH/SOL windows since both UP and DOWN tokens are tracked). Peer discovery rate is not directly visible, but `peer_token_id != ""` is a logged field.

**Failure criteria:** WR difference < 5pp between arb_sum buckets [<0.96, 0.96-1.04, >1.04], or n < 20 per bucket.

---

## HOLD_TO_CLOSE Signal (Incidental Finding from multi_exit_replay)

From commit 2584a13 (dirty cohort), multi_exit_replay full-cohort results:
- `HOLD_TO_CLOSE` (hold until last tick): **+1.70% avg**
- `PT95+fallback` (current architecture): **+1.19% avg**
- `PT97+fallback`: **+2.22% avg**
- `T20/T30 time exits`: **+4.78% / +3.87% avg** (best, but n<500 flag)

Clean cohort (849b768): PT95 +4.32% > PT97 +3.86% (full-cohort, clean). HOLD_TO_CLOSE was NOT re-reported on clean cohort.

**Interpretation:** The HOLD_TO_CLOSE > PT95+fallback finding from the dirty run may be an artifact of contaminated hold_path positions (pre-revert rem 90-120s positions inflating HOLD_TO_CLOSE). The `--fire-rem-max 90` filter was added in 849b768 to address this. Whether HOLD_TO_CLOSE still outperforms PT95 on the clean cohort is unknown — flagged for n≥500 validation per commit message.

**Action: No change until clean n≥500. Monitor.**

---

## Priority Signal for Next Implementation

**Add `arb_sum_yes_no` to CONTINUOUS_SIGNALS and PLACEHOLDER_ZERO_FIELDS — 2 lines, immediate analysis.**

Data has been accumulating for ~48h. This is the only field in market_timeline schema that:
1. Has been logged since Phase 1
2. Tests a cross-token pricing consistency hypothesis
3. Is completely unanalyzed (NOT in CONTINUOUS_SIGNALS)

The change:
```python
# analytics/signal_analysis.py

# In CONTINUOUS_SIGNALS list, after "ask_stale_s":
"arb_sum_yes_no",

# In PLACEHOLDER_ZERO_FIELDS set:
"arb_sum_yes_no",
```

After 24h accumulation on clean cohort, run:
```bash
python3 analytics/signal_analysis.py --days 3 --strategy-version v2 --rem-min 25 --rem-max 90
```

Check: Is arb_sum quantile YES rate monotonic? Is the spread ≥ 5pp between extreme buckets (<0.96 vs >1.04)?

**Second priority (unchanged from prior cycle):** Add `binance_vel_5s_pct` to shadow timeline by calling existing `_binance_ret(asset_up, now, 5)` method and adding it to `CONTINUOUS_SIGNALS` + `PLACEHOLDER_ZERO_FIELDS`. One additional line in `_build_record` return dict; one line in signal_analysis.

**Negative result of note:** Dead drift hypothesis (Investigation 3) continues to be weakened by all available evidence. The 30s analog showed flat entries are BETTER, not worse. The dead-drift investigation should be de-prioritized until arb_sum and velocity_5s accumulate data.

---

## Infrastructure Alert — SSH (44 consecutive sessions)

**Status:** TCP port 22 egress blocked at sandbox network boundary.
**VPS IS active** — 9 VPS-authored commits in 14 hours (shadow pipeline operational, gate changes deploying, analytics running clean re-runs).

**Manual sync still needed (30s on VPS, unblocks all future scouts):**
```bash
cd /root/Klaus && tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
git add logs/live_trades_recent.jsonl logs/bankroll.json && \
git commit -m "manual log sync $(date -u)" && git push origin claude/find-lag-parameter-rFQ0N
```

**Without this, all four mandated investigations remain structurally blocked at n=0.**
The arb_sum and binance_vel_5s_pct proposals are actionable from shadow alone and do not require trades.jsonl.
