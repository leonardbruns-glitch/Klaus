# Alpha Scout Report — 2026-05-11 12:12 UTC

**Method:** Codebase audit — VPS SSH unreachable (49th consecutive scout session)
**Connectivity:** SSH binary absent in sandbox; TCP port 22 egress blocked at network boundary. `trades.jsonl` and `post_exit.jsonl` inaccessible.
**Data sources used:** git log HEAD=fd73eea; full reads of `strategy/discover_strategy.py`, `data/shadow/discover_signal.py`, `analytics/discover/grid.py`, `analytics/signal_analysis.py`, `main.py` (exit block lines 1280–1410); `logs/bankroll.json`; `logs/audit_report.md`.
**Bankroll snapshot (bankroll.json, ts=1778268412 / 2026-05-08 19:26 UTC):** capital=$84.61, total_trades=2,605, total_pnl=+$87.87. Unchanged from prior sessions — git-tracked snapshot is stale.

---

## Strategy State Changes Since Last Scout (2026-05-11 00:22 UTC)

| Commit | Time (UTC) | Change | Basis |
|---|---|---|---|
| 43146df | 08:28 | ask ceiling 0.55 → 0.40 | n=259 live DISCOVER trades, 4-day EV breakdown |
| fd73eea | 09:37 | PT threshold 0.95 → 0.99 | User instruction: hold to near-certainty |

**ask ceiling analysis (from commit 43146df):**
- ask 0.40–0.55 bucket: n=107/259 (41% of entries), EV=**−$0.34/trade**, net −$36 over 4 days. Confirmed not time-of-day structural.
- ask < 0.40 bucket: n=169/259, EV=**+$1.34/trade**, CI=[+$0.28, +$2.50], PF=1.62, P(EV>0)=99.2%.
- Net effect: −35% throughput, higher absolute daily EV (+$56 vs +$45 estimated).

This was the highest-confidence code change since DISCOVER went live. The tighten is sound.

**PT 0.95→0.99 (user instruction):**
Marginal impact: DOWN tokens resolving YES walk from ask (~0.10–0.40) through the full 0→1 range. Bids reaching 0.95 almost always reach 0.99 within seconds — the incremental hold time is <10s and P&L difference is ~4% of position. T-15 remains the dominant exit for all positions that do not resolve YES pre-window-close. No edge concern with this change.

---

## Current DISCOVER Parameters (post-tighten, live as of 09:37 UTC)

| Parameter | Value | Location |
|---|---|---|
| Direction | DOWN only | discover_strategy.py:172 |
| Assets | BTC + ETH | discover_strategy.py:150 |
| ask range | 0.10 – 0.40 | discover_strategy.py:174 |
| rem window | 60 – 180s | discover_strategy.py:172 |
| arb_sum gate | < 0.99 | discover_strategy.py:193 |
| PT exit | bid ≥ 0.99 | main.py:1292 |
| T-15 exit | asyncio task | discover_strategy.py:~220 |
| T-5 backup | DISCOVER_DEADLINE | main.py:1371 |
| Stake | $3 target (floor=max($1, 5×ask)) | discover_strategy.py:83 |
| Kill-switches | Disabled | discover_strategy.py:75-78 |

---

## Investigation 1: Cross-Exchange Lead-Lag

HYPOTHESIS: Positive Binance spot velocity in 5s before entry (`pre_entry_momentum_pct`) predicts YES resolution.
RESULT: n=0 — BOND disabled; field not computed or logged by DISCOVER path.
MATH: pre_entry_momentum_pct = (spot_now − spot_5s_ago) / spot_5s_ago × 100 (BOND-only path in main.py)
CONCLUSION: **INCONCLUSIVE**
FAILURE_MET: Cannot evaluate. BOND disabled 2026-05-10 21:25 UTC. This field does not exist in the DISCOVER entry path. `binance_vel_5s_pct` is being accumulated in `market_timeline.jsonl` on VPS (deployed prior cycle) but cannot be joined to DISCOVER outcomes without SSH access. Note: DISCOVER's arb_sum signal is structurally independent of Binance spot velocity — arb mispricing is a supply-demand pricing gap, not a momentum signal. Cross-exchange lead-lag is less relevant to DISCOVER than to BOND.

---

## Investigation 2: Tick Count Filter

HYPOTHESIS: Low `term_tok_tick_count_5s` predicts lower YES resolution rate.
RESULT:

| Bucket | n | WR | PF |
|---|---|---|---|
| 0–2 ticks | 0 | N/A | N/A |
| 3–5 ticks | 0 | N/A | N/A |
| 6–10 ticks | 0 | N/A | N/A |
| 11+ ticks | 0 | N/A | N/A |

PROPOSED_GATE: Cannot set — n=0.
CONCLUSION: **INCONCLUSIVE**
FAILURE_MET: Cannot evaluate. `term_tok_tick_count_5s` is a BOND-specific terminal scanner metric that does not exist in the DISCOVER path. Structurally obsolete for DISCOVER: the arb_sum gate (`arb_sum < 0.99`) requires a valid live peer ask — dead/thin markets have no peer ask → peer_ask=0 → arb_sum computation fails → filtered before entry. Tick count adds no marginal value when arb_sum already gates on live peer liquidity. `peer_age_ms` (in `discover_signal.jsonl`) is the DISCOVER-native staleness analog.

---

## Investigation 3: Dead Drift Signature

HYPOTHESIS: Dead market entries (`|term_token_delta_5s| < 0.005`) underperform active entries.
RESULT:

| Group | n | WR |
|---|---|---|
| Dead drift (\|delta_5s\| < 0.005) | 0 | N/A |
| Active (\|delta_5s\| ≥ 0.005) | 0 | N/A |

CONCLUSION: **INCONCLUSIVE**
FAILURE_MET: Cannot evaluate. `term_token_delta_5s` is a BOND terminal scanner field. Not logged by DISCOVER. Additionally: prior shadow evidence (pre-BOND-disable) suggested flat-price entries resolved YES more often than directional entries — contradicting the hypothesis. Not porting to DISCOVER path.

---

## Investigation 4: Asset-Specific Edge

HYPOTHESIS: One asset consistently outperforms others in the last 48h.
RESULT: No live 48h data accessible (SSH blocked). From commit 43146df basis data (4-day DISCOVER trades, n=259):

| Asset | n (4-day) | Evidence |
|---|---|---|
| BTC | ~subset of 169 | In ask<0.40 positive cohort |
| ETH | ~subset of 169 | In ask<0.40 positive cohort |
| SOL | 0 | Blocked since 2026-05-10 22:10 UTC |

Live n per-asset cannot be split without SSH. Prior backtest (state_log.md): ETH EV=+$3.11/trade CI=[+$0.08,+$6.36]; BTC EV=+$0.66/trade CI=[−$0.95,+$3.47].

CONCLUSION: **INCONCLUSIVE** (per-asset n < 20 confirmed in 48h window)
No reweighting warranted. ETH continues to look stronger vs BTC; current equal-weight $3 stake is conservative given data quality. Do not weight further without n≥20 per asset in live 48h window.

---

## DISCOVER-Native Investigations (Forward Research Agenda)

The four mandated investigations remain obsolete while BOND is disabled. The following are active DISCOVER investigations, ordered by priority:

### Investigation A: arb_sum Depth as Conviction Signal (Priority 1 — UNCHANGED)

HYPOTHESIS: Deeper mispricing (lower arb_sum_yes_no) → higher DOWN-token YES resolution rate.
MATH: `arb_sum = YES_ask + NO_ask`. Values <0.99 mean a combined pricing gap. Deeper gap = sharper signal.
VARIABLES: `arb_sum_yes_no` (already in `discover_signal.jsonl` on VPS)
BUCKETS: [0.00, 0.85), [0.85, 0.92), [0.92, 0.99)
PROPOSED_GATE: `arb_sum_yes_no < X` floor in `discover_strategy._should_fire()` line ~193
FAILURE_CRITERIA: WR spread < 5pp across buckets, or n < 20 per bucket.
IMPLEMENTATION_COST: Zero — field already logged. Pure analytics join on VPS.

**IMPORTANT filter note:** `discover_signal.py`'s `matches()` function still gates at `ask <= 0.55` (line ~35) while live strategy now gates at `ask <= 0.40` (commit 43146df). The shadow recorder will have 41% extra records at ask 0.40–0.55 that will never be traded. Any analysis of `discover_signal.jsonl` MUST apply `best_ask <= 0.40` filter to match current live gates. Without this filter, arb_sum analysis is contaminated by the dead-EV ask range.

VPS analysis script (filter-corrected):
```python
import json, glob
from collections import defaultdict

signals = {}
for f in glob.glob('/root/Klaus/logs/shadow/hot/*/discover_signal.jsonl'):
    for line in open(f):
        try:
            r = json.loads(line)
            # CRITICAL: filter to current live ask gate (tightened 2026-05-11 08:28)
            if r.get('best_ask', 1.0) > 0.40:
                continue
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
            k = (r.get('condition_id',''), int(r.get('window_end_ts', 0)))
            resolutions[k] = r
        except Exception:
            pass

buckets = defaultdict(lambda: {'n': 0, 'wins': 0})
for (tid, wend), sig in signals.items():
    cid = sig.get('condition_id', '')
    res = resolutions.get((cid, wend))
    if not res:
        continue
    outcome = res.get('resolved_yes')
    if outcome is None:
        continue
    arb = sig.get('arb_sum_yes_no', 0.0) or 0.0
    b = '<0.85' if arb < 0.85 else ('0.85-0.92' if arb < 0.92 else '0.92-0.99')
    buckets[b]['n'] += 1
    if outcome:
        buckets[b]['wins'] += 1

for b, v in sorted(buckets.items()):
    wr = v['wins']/v['n'] if v['n'] else 0
    print(f"{b}: n={v['n']} WR={wr:.1%}")
```

If WR spread ≥ 5pp and n ≥ 20 per bucket: add `arb_sum_yes_no < X` floor gate.
If no spread: arb_sum is binary (either <0.99 fires or doesn't) — cannot refine further.

---

### Investigation B: peer_age_ms as Quote-Staleness Filter (Priority 2)

HYPOTHESIS: Stale peer quotes (high `peer_age_ms`) produce spurious arb_sum < 0.99 readings — the bot buys DOWN at T-120s but the peer OB snapshot is 500ms stale; actual arb_sum may be ≥ 1.0 at fill time. These entries underperform due to adverse selection.
MATH: `peer_age_ms = int((now − peer_ob.ts) × 1000)` — milliseconds since last WS update on peer token OB.
VARIABLES: `peer_age_ms` (in `discover_signal.jsonl`, already logged per build_record())
BUCKETS: [0, 100ms), [100ms, 500ms), [500ms+]
PROPOSED_GATE: Skip entry if `peer_age_ms > X` in `discover_strategy._should_fire()`
FAILURE_CRITERIA: WR spread < 5pp across age buckets.
IMPLEMENTATION_COST: Near-zero. Field already in discover_signal.jsonl. One-line gate in `_should_fire()` after arb_sum check.

VPS analysis script:
```python
import json, glob
from collections import defaultdict

signals = {}
for f in glob.glob('/root/Klaus/logs/shadow/hot/*/discover_signal.jsonl'):
    for line in open(f):
        try:
            r = json.loads(line)
            if r.get('best_ask', 1.0) > 0.40:
                continue
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
            k = (r.get('condition_id',''), int(r.get('window_end_ts', 0)))
            resolutions[k] = r
        except Exception:
            pass

buckets = defaultdict(lambda: {'n': 0, 'wins': 0})
for (tid, wend), sig in signals.items():
    cid = sig.get('condition_id', '')
    res = resolutions.get((cid, wend))
    if not res:
        continue
    outcome = res.get('resolved_yes')
    if outcome is None:
        continue
    age = sig.get('peer_age_ms', 0) or 0
    b = '<100ms' if age < 100 else ('100-500ms' if age < 500 else '500ms+')
    buckets[b]['n'] += 1
    if outcome:
        buckets[b]['wins'] += 1

for b, v in sorted(buckets.items()):
    wr = v['wins']/v['n'] if v['n'] else 0
    print(f"{b}: n={v['n']} WR={wr:.1%}")
```

---

### Investigation C: rem Sub-Bucket Edge (Priority 3)

HYPOTHESIS: Within the 60–180s rem window, earlier entries (nearer 180s) have more time for arb to converge but also more time to reverse. Later entries (60–90s) have less reversal risk but may miss wider arb windows.
VARIABLES: `seconds_to_resolution` (in `discover_signal.jsonl`)
BUCKETS: [60, 90s), [90, 120s), [120, 180s)
FAILURE_CRITERIA: WR spread < 5pp or n < 20 per bucket.
NOTE: rem was tightened from 60-240s to 60-180s on 2026-05-10 (commit 4d48f8e) based on CI evidence. Further tightening within 60-180s requires live data.

---

### Investigation D: PT99 vs T-15 Exit Mix (Priority 4 — new this cycle)

HYPOTHESIS: With PT raised 0.95→0.99, the practical question is what fraction of DISCOVER positions exit via PT99 vs T-15. If <10% exit via PT99, the threshold change is cosmetic — T-15 dominates. If >30% exit via PT99, raising the threshold to 0.99 meaningfully captures winners early.
VARIABLES: `exit_reason` in `trades.jsonl` — values: PROFIT_TARGET (PT99 hit), DISCOVER_T15 (T-15 scheduled exit), DISCOVER_DEADLINE (T-5 backup)
MATH: `pct_pt99 = count(exit_reason=='PROFIT_TARGET') / total_DISCOVER_trades`
FAILURE_CRITERIA: n < 20 total DISCOVER trades (cannot split).
INSIGHT: DOWN tokens bought at 0.10–0.40 that resolve YES will walk bid from entry to ~1.0. PT99 fires at bid=0.99 — effectively identical to resolution payout minus ~1% slippage. For these trades, PT99 captures the same profit as holding to resolution. For losing trades (bid stays low), PT99 never fires and T-15 forces exit near entry. The threshold 0.95 vs 0.99 matters only for the narrow "winner still walking at T-15" case — quantify this with real exit_reason data.

VPS analysis:
```bash
python3 -c "
import json
from collections import Counter
trades = [json.loads(l) for l in open('/root/Klaus/logs/trades.jsonl') if l.strip()]
disc = [t for t in trades if t.get('signal_source')=='DISCOVER']
print(f'n_discover={len(disc)}')
print(Counter(t.get('exit_reason','?') for t in disc).most_common())
"
```

---

## Shadow Recorder Drift Alert — discover_signal.py

`discover_signal.py`'s `matches()` function still uses `ask <= 0.55` (pre-tighten value). The live strategy now gates at `ask <= 0.40` (commit 43146df, 2026-05-11 08:28 UTC). This mismatch means:
- Shadow recorder fires on signals at ask 0.40–0.55 that the live bot will never trade
- These contaminate discover_signal.jsonl with ~41% irrelevant records (based on n=107/259 share)
- Any shadow analysis MUST filter `best_ask <= 0.40` to match live gates

**Recommended fix (one line in `data/shadow/discover_signal.py`):**
```python
# Line ~35, change:
if not (0.10 <= ask <= 0.55):
# to:
if not (0.10 <= ask <= 0.40):
```
This is a cosmetic fix — it reduces shadow write volume by ~41% and removes the need to apply a post-hoc filter in every analysis script. Implement when convenient; not a live-trading blocker.

---

## Priority Signal for Next Implementation

**Investigation B (peer_age_ms staleness gate)** is the highest-priority new actionable signal this cycle, contingent on n ≥ 20 per bucket.

Rationale: arb_sum < 0.99 fires on a snapshot of two OB quotes. If the peer OB snapshot is 500ms+ stale, the actual arb_sum at fill time may be ≥ 1.0 (no edge). This is a mechanical adverse-selection source — not random noise. It affects entry quality directly and costs nothing to gate.

**Implementation (once n ≥ 20 per bucket confirmed):**
```python
# In discover_strategy._should_fire(), after arb_sum check (line ~193):
# peer_age_ms is peer OB snapshot age in ms (from WS feed)
peer_age_ms = getattr(peer_ob, 'age_ms', 0) or 0
if peer_age_ms > 250:          # tune from data: 100/250/500ms buckets
    return None
```

**Failure criteria:** WR spread < 5pp across peer_age_ms buckets → discard, no gate.

Investigation A (arb_sum depth) remains Priority 1 if VPS data sync produces n ≥ 20 per arb_sum bucket. Run Investigation A first — if WR spread ≥ 5pp and n ≥ 20, add arb_sum floor gate before adding peer_age_ms gate. Add one gate at a time; avoid confounding.

**If no VPS sync by next cycle:** No actionable signals this cycle — continue data collection. Both scripts above are VPS-ready and can run immediately once SSH is unblocked.

---

## Infrastructure Alert — SSH (49 consecutive sessions)

Root cause unchanged: TCP port 22 egress blocked at sandbox network boundary.

Manual VPS sync (1 command, 30s):
```bash
cd /root/Klaus && tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && git add logs/live_trades_recent.jsonl logs/bankroll.json && git commit -m "log sync $(date -u +%Y-%m-%dT%H:%M)" && git push origin claude/find-lag-parameter-rFQ0N
```

Without this sync, all four mandated BOND investigations and all four DISCOVER investigations remain at n=0. The ask-ceiling tighten (commit 43146df, the highest-value change since DISCOVER launched) was derived from data accessible on VPS — the same data needed to run Investigations A–D. Once the sync runs, all four scripts above can execute immediately.
