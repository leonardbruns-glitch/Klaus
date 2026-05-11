# Alpha Scout Report — 2026-05-11 00:22 UTC

**Method:** Codebase audit — VPS SSH unreachable (48th consecutive scout session)
**Connectivity:** SSH binary absent in sandbox; TCP port 22 egress blocked at network boundary. `trades.jsonl` and `post_exit.jsonl` inaccessible.
**Data sources used:** git log (HEAD=5d03a25 → prior scout 0f3fc21); full codebase reads of `strategy/discover_strategy.py`, `data/shadow/discover_signal.py`, `data/shadow/timeline.py`, `analytics/signal_analysis.py`, `analytics/discover/grid.py`; `logs/bankroll.json`; `state_log.md`; `logs/audit_report.md`.
**Bankroll snapshot (bankroll.json, ts=1778268412 / 2026-05-08 19:26 UTC):** capital=$84.61, total_trades=2,605, total_pnl=+$87.87. Stale — same as prior session.

---

## STRATEGY PIVOT NOTICE — BOND DISABLED

**BOND strategy disabled 2026-05-10 21:25 UTC (commit a9fbbfc).**
`BOND_ENABLED = False` in `strategy/window_sniper.py`. DISCOVER strategy activated in its place.

**All four mandated investigations are scoped to BOND fields** (`pre_entry_momentum_pct`, `term_tok_tick_count_5s`, `term_token_delta_5s`, `binance_price_at_entry`). These fields are:
1. Not logged by the DISCOVER strategy path
2. Not present in any accessible log file (SSH blocked)
3. Will not accumulate going forward while BOND is disabled

This scout reports all four investigations INCONCLUSIVE (strategy no longer active) and documents what the relevant DISCOVER investigations should be for the next cycle.

---

## DISCOVER Strategy — Current Live State (as of 2026-05-11 00:22 UTC)

| Parameter | Value | Source |
|---|---|---|
| Strategy | DISCOVER only (BOND=False) | window_sniper.py:133 |
| Signal class | S2 only (S3 pulled back 2026-05-10 22:35) | discover_strategy.py:138 |
| Direction | DOWN only | discover_strategy.py:172 |
| arb_sum_yes_no gate | < 0.99 (and > 0.0) | discover_strategy.py:193 |
| Ask range | 0.10 – 0.55 | discover_strategy.py:174 |
| rem window | 60 – 180s | discover_strategy.py:172 |
| Stake | $3 (target; floor=max($1, 5×ask)) | discover_strategy.py:199 |
| Assets | BTC + ETH only (SOL blocked) | discover_strategy.py:150 |
| Exit | T-15 asyncio task (primary); PT95 (bid≥0.95); DISCOVER_DEADLINE T-5 (safety net) | |
| Killswitches | Disabled per user instruction | discover_strategy.py:75-78 |
| Live since | 2026-05-10 21:25 UTC (~3h ago) | state_log.md |

**Known live outcomes (state_log.md, 2026-05-10 22:05 UTC):**
- T04076_ETH: ep=0.55 → exit=0.84 hold=64s PnL=+$0.71 (exited via INVERTED_TP — now gated off)
- T04078_BTC: ep=0.48 → exit=0.67 hold=37s PnL=+$1.10 (exited via INVERTED_TP — now gated off)

Both exited before T-15 through INVERTED_TP. Gate removed commit 1ddf911. Post-fix behavior unknown — SSH blocked.

---

## Investigation 1: Cross-Exchange Lead-Lag

HYPOTHESIS: Positive Binance spot velocity in the 5s before entry (`pre_entry_momentum_pct`) predicts YES resolution.
RESULT: n=0 — BOND disabled; field not computed or logged by DISCOVER path.
MATH: pre_entry_momentum_pct = (spot_now − spot_5s_ago) / spot_5s_ago × 100 (main.py:3441, BOND-only path)
CONCLUSION: INCONCLUSIVE
FAILURE_MET: Cannot evaluate. BOND disabled 2026-05-10 21:25 UTC. `pre_entry_momentum_pct` and `binance_price_at_entry` are BOND terminal scanner fields. They are not computed in the DISCOVER entry path. The `binance_vel_5s_pct` shadow field deployed prior cycle continues accumulating in `market_timeline.jsonl` on VPS but cannot be joined to outcomes without SSH access.

---

## Investigation 2: Tick Count as Toxicity Filter

HYPOTHESIS: Low `term_tok_tick_count_5s` predicts lower YES resolution rate.
RESULT:

| Bucket | n | WR | PF |
|---|---|---|---|
| 0-2 ticks | 0 | N/A | N/A |
| 3-5 ticks | 0 | N/A | N/A |
| 6-10 ticks | 0 | N/A | N/A |
| 11+ ticks | 0 | N/A | N/A |

PROPOSED_GATE: Cannot set — n=0.
CONCLUSION: INCONCLUSIVE
FAILURE_MET: Cannot evaluate. `term_tok_tick_count_5s` is a BOND-specific metric (main.py:2558). DISCOVER does not compute it. Structurally obsolete: DISCOVER's arb gate requires a live peer quote (arb_sum requires peer_ask > 0) — dead/thin markets have no peer ask → arb_sum=0 → filtered before entry. Tick count adds no marginal value in the DISCOVER path. `peer_age_ms` is the DISCOVER-native analog (see New Investigation B below).

---

## Investigation 3: Dead Drift Signature

HYPOTHESIS: Dead market entries (`|term_token_delta_5s| < 0.005`) underperform active entries.
RESULT:

| Group | n | WR |
|---|---|---|
| Dead drift (\|delta_5s\| < 0.005) | 0 | N/A |
| Active (\|delta_5s\| >= 0.005) | 0 | N/A |

CONCLUSION: INCONCLUSIVE
FAILURE_MET: Cannot evaluate. `term_token_delta_5s` is a BOND terminal scanner field (main.py:2657). Not computed in DISCOVER path. Additionally: prior 30s analog evidence contradicted the hypothesis (flat entries resolved YES more often). Not porting to DISCOVER.

---

## Investigation 4: Asset-Specific Edge

HYPOTHESIS: One asset (BTC/ETH/SOL) consistently outperforms others in the last 48h.
RESULT (from state_log.md DISCOVER S2 backtest, n sufficient):

| Asset | n (backtest) | EV/trade | CI | Live Status |
|---|---|---|---|---|
| BTC | 63 | +$0.66 | [-$0.95, +$3.47] | Active (whitelisted) |
| ETH | 69 | +$3.11 | [+$0.08, +$6.36] | Active (whitelisted) |
| SOL | 54 | +$0.32 | not reported | Blocked (marginal EV) |
| Combined | 95 | +$1.95 | [+$0.31, +$3.85] | — |

CONCLUSION: SIGNAL_FOUND (action already taken this cycle)
SOL blocked commit 9513b40 (2026-05-10 22:10 UTC). BTC+ETH whitelisted. ETH dominates EV; BTC passes only combined bar. No additional reweighting warranted — live n too small to split further.
FAILURE_MET: No. n≥20 per asset met in backtest data (63/69/54). Structural finding confirmed. Live 48h window has n=0 from SSH block, but the backtest provides sufficient ground truth for current configuration.

---

## DISCOVER-Specific Investigations — Forward Research Agenda

The four mandated investigations are obsolete while BOND is disabled. The following replace them for DISCOVER:

### New Investigation A: arb_sum Depth as Conviction Signal
HYPOTHESIS: Deeper mispricing (lower arb_sum_yes_no) → higher DOWN-token YES resolution rate.
MATH: arb_sum = YES_ask + NO_ask. Values <0.99 mean market prices sum to <$1 (a pricing gap). Deeper gap = stronger signal.
VARIABLES: `arb_sum_yes_no` (in discover_signal.jsonl, already logged)
BUCKETS: [0.00, 0.85), [0.85, 0.92), [0.92, 0.99)
FAILURE CRITERIA: WR spread < 5pp across buckets, or n < 20 per bucket.
IMPLEMENTATION COST: Zero. Field already in discover_signal.jsonl. Pure analytics join on VPS.

### New Investigation B: peer_age_ms as Quote-Staleness Filter
HYPOTHESIS: Stale peer quotes (high peer_age_ms) produce spurious arb_sum < 0.99 — bot buys DOWN at T-120s but peer quote is 30s stale, actual sum ≥ 1.0. These entries underperform.
MATH: `peer_age_ms = int((now − peer_ob.ts) × 1000)` — time since last WS update on peer token OB.
VARIABLES: `peer_age_ms` (in discover_signal.jsonl, already logged)
BUCKETS: [0, 100ms), [100ms, 500ms), [500ms+]
FAILURE CRITERIA: WR spread < 5pp across age buckets.
IMPLEMENTATION COST: Zero. Field already in discover_signal.jsonl.

### New Investigation C: rem Sub-Bucket Edge
HYPOTHESIS: Within 60-180s rem window, entry timing matters. Nearer to resolution = less variance but also less mispricing decay time.
VARIABLES: `seconds_to_resolution` (in discover_signal.jsonl)
BUCKETS: [60, 90s), [90, 120s), [120, 180s)
FAILURE CRITERIA: WR spread < 5pp, or n < 20 per bucket.

### New Investigation D: T-15 Exit vs Resolution Hold
HYPOTHESIS: High-conviction arb entries (arb_sum < 0.90) leave money on the table exiting at T-15 vs holding to resolution at 1.00.
VARIABLES: requires live DISCOVER trade data with entry arb_sum and exit timing.
STATUS: Cannot evaluate — SSH blocked and strategy only 3h old.

---

## Priority Signal for Next Implementation

**Investigation A (arb_sum depth) is the highest-priority actionable signal, subject to n≥20 per bucket.**

When VPS data becomes accessible, run this directly on VPS:

```python
import json, glob
from collections import defaultdict

signals = {}
for f in glob.glob('/root/Klaus/logs/shadow/hot/*/discover_signal.jsonl'):
    for line in open(f):
        try:
            r = json.loads(line)
            k = (r['token_id'], int(r.get('window_end_ts', 0)))
            if k not in signals:
                signals[k] = r
        except Exception:
            pass

resolutions = {}
for f in glob.glob('/root/Klaus/logs/shadow/hot/*/window_resolution.jsonl'):
    for line in open(f):
        try:
            r = json.loads(line)
            k = (r.get('condition_id', ''), int(r.get('window_end_ts', 0)))
            resolutions[k] = r
        except Exception:
            pass

buckets = defaultdict(lambda: {'n': 0, 'wins': 0})
for (tid, wend), sig in signals.items():
    cid = sig.get('condition_id', '')
    res = resolutions.get((cid, wend))
    if not res:
        continue
    outcome = res.get('resolved_yes')  # True = DOWN token resolved YES (correct call)
    if outcome is None:
        continue
    arb = sig.get('arb_sum_yes_no', 0.0) or 0.0
    b = '<0.85' if arb < 0.85 else ('0.85-0.92' if arb < 0.92 else '0.92-0.99')
    buckets[b]['n'] += 1
    if outcome:
        buckets[b]['wins'] += 1

for b, v in sorted(buckets.items()):
    wr = v['wins'] / v['n'] if v['n'] else 0
    print(f"{b}: n={v['n']} WR={wr:.1%}")
```

If WR spread ≥ 5pp and n ≥ 20 per bucket: add `arb_sum_yes_no < X` floor gate to `discover_strategy._should_fire()` at line ~193. One line, zero risk.

**If no sync by next cycle:** No actionable signals this cycle — continue data collection.

---

## Implementation Summary — This Cycle

**No code changes.** Rationale:
1. All four mandated investigations are obsolete — BOND disabled.
2. DISCOVER went live ~3h ago — no gates warranted on 2-trade sample.
3. Prior shadow fields (`arb_sum_yes_no`, `binance_vel_5s_pct`) accumulating but not readable without SSH.

---

## Infrastructure Alert — SSH (48 consecutive sessions)

Root cause unchanged: TCP port 22 egress blocked at sandbox network boundary. SSH binary absent. VPS IS active — DISCOVER live-trading confirmed by state_log.md entries at 22:05 UTC.

Manual sync (30s on VPS):
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl 2>/dev/null || true
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "log sync $(date -u +%Y-%m-%dT%H:%M)"
git push origin claude/find-lag-parameter-rFQ0N
```

**DISCOVER is only ~3h old. Even with a sync, n≥20 per bucket thresholds may not be met until 48h of live data accumulate. Correct posture: collect, then analyse in one session.**
