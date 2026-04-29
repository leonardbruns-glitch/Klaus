# Alpha Scout Report — 2026-04-29 12:11 UTC

**Method:** Commit-embedded analysis — VPS SSH unreachable (9th consecutive session)
**Data:** Commit messages `9d974e2`→`bf6dafb` (Apr 29 00:34–10:40 UTC) + bankroll.json + codebase audit
**Known gap:** No `trades.jsonl` retrieved. All investigations below rely on commit-embedded n counts and prior-session summaries.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Binance spot price change in the 5s before entry (not the 1m kline) predicts YES token direction. Positive 5s momentum → higher YES resolution rate.

**STATUS: INCONCLUSIVE — field not yet logged**

- `pre_entry_momentum_pct` in the log records 1m kline delta, not 5s spot delta — wrong granularity for this investigation.
- `binance_spot_5s_delta` was mandated in the previous two scout cycles but never implemented.
- **This cycle: `term_spot_delta_5s` added to logging schema** (commit in this session).
  - Source: `_hist_delta(_price_history, 5)` — same per-asset spot price history deque already in use for 30s/60s deltas.
  - Field name in TradeRecord: `term_spot_delta_5s` (float, % change).
  - Logged in `trades.jsonl` starting from this deploy.

**Proxy evidence from 1m version** (commit `89f853a`, reverted `0ddb49e`):
- Both Binance 1m + 5m positive ("both-rising" UP-window): n=43, WR=51%, E=+$0.41/trade
- Other regimes: WR=75–87%
- WR delta = 24–36pp; gate reverted at n=43 (threshold: n≥100)

**MATH:** `term_spot_delta_5s = (spot_now - spot_5s_ago) / spot_5s_ago * 100`
**PROPOSED FIELD:** `term_spot_delta_5s` — now live in logging.

**CONCLUSION:** INCONCLUSIVE
**FAILURE_MET:** No — investigation cannot be run without the field. Mandate accumulate n≥100 with `term_spot_delta_5s` non-zero before bucketing.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low tick count (thin market, dead flow) predicts lower YES resolution rate. High tick count = informed active flow = edge.

**STATUS: INCONCLUSIVE — insufficient bucket n**

- 5s window (`term_tok_tick_count_5s`): DISCARD — prior cycle confirmed zero separation (wins and losses both median=8).
- 30s window (`term_tok_tick_count_30s`): field added in commit `b5fdc62` (~34h old as of this report).
- No bucket-level data in any commit since `b5fdc62`. n per bucket unknown.
- Estimated n with this field: ~34h × ~2 trades/hour = ~68 total trades. Across 4 buckets (0–2, 3–5, 6–10, 11+), expected n per bucket ≈ 10–25 — likely under the 20-trade floor for some buckets.

**PROPOSED_GATE:** min_tick_count_30s = TBD — no conclusion possible yet.

**CONCLUSION:** INCONCLUSIVE
**FAILURE_MET:** Not applicable — n per bucket unverifiable without raw trades.jsonl. Re-run when trades.jsonl is accessible or n≥80 total with new field is confirmed via commit.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Entries where token price was flat in the 30s before entry (|term_token_delta_30s| < 0.5%) underperform active entries. Dead markets → no genuine buyer conviction → lower resolution rate.

**STATUS: SIGNAL_CANDIDATE (carried forward from prior cycle, not yet gateable)**

| Bucket | WR | Source |
|---|---|---|
| Flat token \|d30\| < 0.5% | 53% | commit `b5fdc62` n=~subset of 677 |
| Overall TERMINAL | 65% | commit `b5fdc62` baseline |

- WR gap = 12pp. Exceeds 5pp monitoring threshold.
- `term_tok_decel_ratio` (d5s/d30s, near 0 = momentum stalled) added in `b5fdc62` (~34h old). No n count from commits.
- Prior DISCARD (`3c981f4`) was based on TREND-era data misapplied to TERMINAL population. Signal reversed when using correct population.

**Do not gate yet.** Flat-drift TERMINAL entries are a minority (~11% of entries based on `ba2b2f7` context). In 34h of data: ~8–12 flat-drift entries — well below n≥40 threshold.

**CONCLUSION:** SIGNAL_CANDIDATE (carry forward)
**Action:** Re-evaluate at n≥40 flat-drift TERMINAL trades with `term_tok_decel_ratio` populated. Flag if `term_tok_decel_ratio < 0.10` WR is more discriminating than raw `|d30|`.

---

## Investigation 4: Asset-Specific Edge

**STATUS: INCONCLUSIVE — no per-asset commit data this cycle**

Carry forward from Apr-28 manual report:

| Asset | PF | Net PnL | Notes |
|---|---|---|---|
| BTC | 1.31 | + | Weakest historical WR, consistent PF |
| SOL | 1.16 | + | Consistent across sessions |
| ETH | 1.01 | + | Driven by 0.79–0.81 bucket; marginal |

**CONCLUSION:** INCONCLUSIVE — n per asset in current parameter window (ask 0.80–0.88, OB imb≥0.20) unverifiable.
**Threshold:** n≥20 per asset required. Flag only if ETH PF stays <1.00 at n≥40.

---

## New Signals This Cycle (from commits since last scout, 00:34–10:40 UTC Apr 29)

### Signal A: BC Depth-Ratio Discriminator (commit `9d974e2`, implemented)

n=70 matched BC wick events.

| depth_ratio bucket | Definition | FP rate | Action |
|---|---|---|---|
| < 0.60 | Crash >40% below entry | 52% | Exit immediately (no wick wait) |
| 0.60–0.77 | Mid-crash | — | wick_wait=15s (neutral) |
| > 0.77 | Shallow crash <23% | 88% | wick_wait=20s (extend window) |

- `depth_ratio = known_min_price / entry_price`
- Also: hard bypass (remaining<10s) was 79% FP at n=29 events → threshold reduced from 15s to 10s.
- **Status:** IMPLEMENTED. Sub-bucket n not yet at n≥100 per bucket — hypothesis mode. Monitor via `wick_events.jsonl`.

### Signal B: SNAP Gate Correction (commit `d3ac233`, shadow only)

n=6 logged SNAP events. Prior logic (`snap_60 < 0` alone) was flagging 3/6 events with positive `snap_30` (momentum surges, not dead drift — inverted signal).

- Corrected gate: `snap_60 < 0 AND snap_30 < 0` → true dead-drift decelerating entries.
- Gate remains **observability-only**. Would-block events accumulating in `logs/snap_shadow.jsonl`.
- **Threshold for activation:** n≥30 would_block events with resolved trade outcomes.
- **Status:** SIGNAL_CANDIDATE. Too early for any conclusion (n=6).

### Signal C: BC Overall FP Rate (commit `d3ac233`)

n=114 resolved BC exits: **66.7% false positive rate**. Net BC effect across all events: -$15.99 (wick filter insufficient, not over-fitted — wicks are genuine).

- Mid-bucket reversal at 16.4s post-exit (confirms 10s wick wait was too short).
- Fast-bucket reversal at 20.2s post-exit (confirms 15s is still insufficient for fast crashes).
- Not a new gate — reinforces existing wick extension logic.

---

## Schema Actions Outstanding

| Field | Status | Priority | Threshold |
|---|---|---|---|
| `term_spot_delta_5s` | **ADDED this cycle** | — | Accumulate n≥100 non-zero |
| `term_tok_tick_count_30s` | Live since `b5fdc62` (~34h) | Medium | Accumulate n≥80 total |
| `term_tok_decel_ratio` | Live since `b5fdc62` (~34h) | Medium | Accumulate n≥40 flat-drift TERMINAL |
| `binance_spot_5s_delta` | Implemented as `term_spot_delta_5s` | Done | — |

---

## Priority Signal for Next Implementation

**`term_spot_delta_5s` — Binance 5s spot momentum at entry**

Now logging. Bucket analysis (positive vs negative vs near-zero) to run at n≥100 non-zero records.

```python
# Proposed gate (DO NOT implement until n>=100):
# term_spot_delta_5s = (spot_now - spot_5s_ago) / spot_5s_ago * 100
# Hypothesis: delta > +0.05% → favorable for YES (spot rising into window)
# Hypothesis: delta < -0.05% → adverse for YES (spot falling = YES at 0.84 overpriced)

# Analysis snippet for next cycle:
import json, statistics
trades = [json.loads(l) for l in open("logs/trades.jsonl")]
bond = [t for t in trades if t.get("signal_source") == "BOND" and t.get("is_live")]
with_5s = [t for t in bond if t.get("term_spot_delta_5s", 0.0) != 0.0]
# Bucket: positive / near-zero / negative
pos   = [t for t in with_5s if t["term_spot_delta_5s"] > 0.05]
neg   = [t for t in with_5s if t["term_spot_delta_5s"] < -0.05]
flat  = [t for t in with_5s if abs(t["term_spot_delta_5s"]) <= 0.05]
for label, bucket in [("pos", pos), ("neg", neg), ("flat", flat)]:
    wins = [t for t in bucket if t["net_pnl"] > 0]
    print(f"{label}: n={len(bucket)} WR={len(wins)/len(bucket):.1%}" if bucket else f"{label}: n=0")
```

**Failure criteria:** If WR difference between `pos` and `neg` buckets < 5pp at n≥100, discard.

---

## Infrastructure Alert — Persistent (9 sessions)

VPS SSH still unreachable from sandbox (TCP port 22 EAGAIN, HTTP proxy blocks arbitrary-IP egress).
Estimated lost analysis records: ~1,600+ trades since first failure.

**Recommended immediate action (Option A):** Push recent trades.jsonl to git every 30 min from VPS:
```bash
# /etc/cron.d/push-logs (on VPS)
*/30 * * * * root cd /root/Klaus && tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && git add logs/live_trades_recent.jsonl logs/bankroll.json && git commit -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && git push origin claude/find-lag-parameter-rFQ0N
```
