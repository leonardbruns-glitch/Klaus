# Alpha Scout Report — 2026-05-12 12:08 UTC

**Method:** Codebase audit — VPS SSH unreachable (50th consecutive scout session)
**Connectivity:** SSH binary absent in sandbox; TCP port 22 egress blocked at network boundary. `trades.jsonl` and `post_exit.jsonl` inaccessible.
**Data sources used:** git log HEAD=302b771; full reads of `state_log.md` (last 10 entries), `logs/bankroll.json`, `logs/scout_report.md` (prior cycle).
**Bankroll snapshot (bankroll.json, ts=1778268412 / 2026-05-08 19:26 UTC):** capital=$84.61, total_trades=2,605, total_pnl=+$87.87. This snapshot predates the oracle_sweep disaster by ~3 days — actual live capital unknown.

---

## CRITICAL ALERT: Oracle Sweep Catastrophe (2026-05-11 18:50 UTC)

**This is the highest-priority item in this report.**

oracle_sweep was deployed, run, disabled, and postmortemed within a single session (2026-05-11). State log records: "$487 spent today, all unredeemable." Two structural flaws:

1. **Wrong candle timeframe:** A1 entry gate used `feed._spot_open_5m` (5-min momentum) but fired on 15m windows. At 15:30–15:45 UTC BTC was −0.136% (15m DOWN) but A1 saw +0.017% 5m — bought the wrong direction.
2. **Adverse selection on cheap asks:** Stale cheap asks at T+0 exist only on the losing side. MMs cancel winner-side asks before window close. The sweep systematically bought the side the market already priced as a loser.

**Impact:** $487 in positions entered, all resolved against. At $84 bankroll (last known), this implies either the VPS was trading with funds not reflected in `bankroll.json`, or the snapshot was already stale and bankroll was larger. Either way, the oracle_sweep episode represents a structural analysis failure — the mechanism was not validated before deployment.

**Current state:** oracle_sweep and gap_sweeper disabled (commits a252bc7, b79fdad). DISCOVER is the sole active strategy.

**VPS sync needed:** Run `tail -200 logs/bot.log | grep -E "(bankroll|capital|equity)"` on VPS to get current capital figure before any new strategy deployment.

---

## Strategy State Changes Since Last Scout (2026-05-11 12:12 UTC)

| Commit | Time (UTC) | Change | Basis |
|---|---|---|---|
| f7bbef4 | ~12:30 | DISCOVER: block BTC, ETH-only whitelist | User instruction |
| b53cb32 | ~13:00 | Tier 1 order lifecycle recorder + wallet tagger | Passive research |
| bf2f4fa | ~13:30 | Tier 1 passive recorders: ob_delta + token_trade schema | Passive research |
| f5b25af | ~14:00 | oracle_sweep + liquidation logger + ob_delta depth | Research/deploy |
| b885d10 | ~14:30 | A1 + B2: flat-market tie-rule pre-entry + MM gap sweeper | Experimental |
| 5d4a4f8–eebcd8b | ~15:00–16:00 | gap_sweeper: 5 bug fix commits | Debug spiral |
| 28f2e14 | ~16:30 | Speed: WS kline + WS book (300ms latency cut) | Perf |
| 1d2a3d0 | ~17:00 | oracle_sweep: raise logs to INFO | Observability |
| 4609a39 | ~17:30 | oracle_sweep: log actual book state | Debug |
| 0552cd8 | ~17:45 | A1: require signed_pct >= 0 | Attempted fix |
| d9635f4 | ~18:00 | A1: 5m windows only + guard sub-minimum exit | Attempted fix |
| a252bc7 | ~18:20 | **KILL: oracle_sweep + gap_sweeper disabled** | Direction bug |
| b79fdad | ~18:40 | KILL confirmed: direction inversion | Postmortem |
| 9cd7e3b | 18:50 | state_log: oracle_sweep postmortem | Record |
| 828f397 | 20:17 | Research: market creation lifecycle monitor | Research |
| 302b771 | 20:22 | Fix: clobTokenIds JSON parse in monitor | Bug fix |

**Pattern:** 9 commits in ~4 hours trying to salvage oracle_sweep after it started losing. This is the classic revenge-fixing spiral. The structural flaw (wrong candle frame + adverse-selection mechanism) was not diagnosable from logs in the field; it required postmortem analysis. Stop loss on experimental strategies should trigger after 3 losing trades, not after capital is depleted.

---

## Current DISCOVER Parameters (unchanged since 2026-05-11 09:37 UTC)

| Parameter | Value | Location |
|---|---|---|
| Direction | DOWN only | discover_strategy.py:172 |
| Assets | ETH only | discover_strategy.py:150 (BTC blocked f7bbef4) |
| ask range | 0.10 – 0.40 | discover_strategy.py:174 |
| rem window | 60 – 180s | discover_strategy.py:172 |
| arb_sum gate | < 0.99 | discover_strategy.py:193 |
| PT exit | bid ≥ 0.99 | main.py:1292 |
| T-15 exit | asyncio task | discover_strategy.py:~220 |
| T-5 backup | DISCOVER_DEADLINE | main.py:1371 |
| Stake | $3 target | discover_strategy.py:83 |

---

## Investigation 1: Cross-Exchange Lead-Lag

HYPOTHESIS: Positive Binance spot velocity in 5s before entry (`pre_entry_momentum_pct`) predicts YES resolution.
RESULT: n=0 — BOND disabled since 2026-05-10 21:25 UTC. Field not logged by DISCOVER path.
MATH: pre_entry_momentum_pct = (spot_now − spot_5s_ago) / spot_5s_ago × 100 (BOND-only)
CONCLUSION: **INCONCLUSIVE**
FAILURE_MET: Cannot evaluate. BOND disabled. DISCOVER's arb_sum signal is structurally orthogonal to Binance spot velocity — arb mispricing is a supply/demand pricing gap, not a momentum signal. Not porting this investigation to DISCOVER.

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
FAILURE_MET: Cannot evaluate. `term_tok_tick_count_5s` is BOND-specific. In DISCOVER, the `arb_sum < 0.99` gate already requires a live peer ask — thin/dead markets have no peer ask, arb_sum computation fails, filtered before entry. Tick count adds no marginal signal value over arb_sum for DISCOVER.

---

## Investigation 3: Dead Drift Signature

HYPOTHESIS: Dead market entries (`|term_token_delta_5s| < 0.005`) underperform active entries.
RESULT:

| Group | n | WR |
|---|---|---|
| Dead drift (\|delta_5s\| < 0.005) | 0 | N/A |
| Active (\|delta_5s\| ≥ 0.005) | 0 | N/A |

CONCLUSION: **INCONCLUSIVE**
FAILURE_MET: Cannot evaluate. `term_token_delta_5s` is BOND-specific. Note for record: prior shadow evidence (pre-BOND-disable) suggested flat-price entries resolved YES *more* often than directional entries — contradicting the hypothesis. Not porting.

---

## Investigation 4: Asset-Specific Edge

HYPOTHESIS: One asset consistently outperforms others in the last 48h.
RESULT: ETH is the only active asset (BTC blocked commit f7bbef4; SOL blocked since 2026-05-10 22:10 UTC). Per-asset comparison impossible with single asset live.

Last known multi-asset data (commit 43146df basis, 4-day, n=259 DISCOVER trades):
- ETH EV=+$3.11/trade CI=[+$0.08, +$6.36]
- BTC EV=+$0.66/trade CI=[−$0.95, +$3.47]

CONCLUSION: **INCONCLUSIVE** (n=0 for BTC/SOL in 48h window; single-asset environment precludes comparison)
No reweighting warranted.

---

## DISCOVER-Native Investigations (Active Research Agenda)

All four BOND investigations remain obsolete while BOND is disabled. DISCOVER-specific investigations ordered by priority:

### Investigation A: arb_sum Depth as Conviction Signal (Priority 1 — UNCHANGED)

HYPOTHESIS: Deeper mispricing (lower arb_sum_yes_no) → higher DOWN-token YES resolution rate.
MATH: `arb_sum = YES_ask + NO_ask`. Values < 0.99 = combined pricing gap. Deeper gap = sharper signal.
VARIABLES: `arb_sum_yes_no` (already in `discover_signal.jsonl` on VPS)
BUCKETS: [0.00, 0.85), [0.85, 0.92), [0.92, 0.99)
PROPOSED_GATE: `arb_sum_yes_no < X` floor in `discover_strategy._should_fire()` line ~193
FAILURE_CRITERIA: WR spread < 5pp across buckets, or n < 20 per bucket.
IMPLEMENTATION_COST: Zero — field already logged.

**IMPORTANT filter note:** `discover_signal.py`'s `matches()` still gates at `ask <= 0.55` (pre-tighten). Live strategy gates at `ask <= 0.40` (commit 43146df). Any analysis MUST apply `best_ask <= 0.40` filter. Without it, arb_sum analysis is contaminated by the dead-EV ask range (41% of records).

VPS analysis script (filter-corrected):
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
    arb = sig.get('arb_sum_yes_no', 0.0) or 0.0
    b = '<0.85' if arb < 0.85 else ('0.85-0.92' if arb < 0.92 else '0.92-0.99')
    buckets[b]['n'] += 1
    if outcome:
        buckets[b]['wins'] += 1

for b, v in sorted(buckets.items()):
    wr = v['wins']/v['n'] if v['n'] else 0
    print(f"{b}: n={v['n']} WR={wr:.1%}")
```

---

### Investigation B: peer_age_ms as Quote-Staleness Filter (Priority 2)

HYPOTHESIS: Stale peer quotes (`peer_age_ms` > threshold) produce spurious arb_sum < 0.99 readings — actual arb_sum at fill time may be ≥ 1.0.
MATH: `peer_age_ms = int((now − peer_ob.ts) × 1000)` — ms since last WS update on peer token OB.
VARIABLES: `peer_age_ms` (in `discover_signal.jsonl`, already logged)
BUCKETS: [0, 100ms), [100ms, 500ms), [500ms+]
PROPOSED_GATE: Skip entry if `peer_age_ms > X` in `discover_strategy._should_fire()`
FAILURE_CRITERIA: WR spread < 5pp across age buckets.

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

HYPOTHESIS: Within 60–180s rem window, later entries (60–90s) have less reversal risk but fewer opportunities.
VARIABLES: `seconds_to_resolution` (in `discover_signal.jsonl`)
BUCKETS: [60, 90s), [90, 120s), [120, 180s)
FAILURE_CRITERIA: WR spread < 5pp or n < 20 per bucket.

---

### Investigation D: PT99 vs T-15 Exit Mix (Priority 4)

HYPOTHESIS: With PT raised 0.95→0.99, what fraction of DISCOVER positions exit via PT99 vs T-15?
VARIABLES: `exit_reason` in `trades.jsonl`
MATH: `pct_pt99 = count(exit_reason=='PROFIT_TARGET') / total_DISCOVER_trades`
FAILURE_CRITERIA: n < 20 total DISCOVER trades.

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

## Shadow Recorder Drift Alert — discover_signal.py (UNRESOLVED)

`discover_signal.py`'s `matches()` still uses `ask <= 0.55` (pre-tighten). Live strategy gates at `ask <= 0.40` (commit 43146df, 2026-05-11 08:28). Shadow recorder fires on ask 0.40–0.55 signals that live bot will never trade — contaminates all analysis by ~41%.

**Fix (one line in `data/shadow/discover_signal.py`):**
```python
# Change:
if not (0.10 <= ask <= 0.55):
# To:
if not (0.10 <= ask <= 0.40):
```

Not a live-trading blocker, but every shadow analysis run without this fix requires an explicit post-hoc `best_ask <= 0.40` filter. Recommend fixing this session.

---

## New Research Flag: Market Creation Monitor

`analytics/market_creation_monitor.py` (commits 828f397, 302b771) was added 2026-05-11 20:17 UTC. Purpose: passive watch for cheap-ask windows during market initialization. Findings so far:

- REST /book at T=0 shows seed at ASK=0.99/BID=0.01 — NOT cheap asks
- Within ~60s MMs seed at 0.50/0.50 and /book goes 404 (WS-only)
- No cheap ask (< 0.20) observed in any initialization state
- Hypothesis: observed bot behavior was an inverted-seed bug (ASK=0.01) that predates current infrastructure

**Verdict:** Market creation exploit appears to be a closed window. Monitor is useful as passive validation but should not be traded without n ≥ 20 confirmed cheap-ask observations.

---

## Priority Signal for Next Implementation

**No actionable signals this cycle — continue data collection.**

Rationale: All four mandated BOND investigations remain at n=0 (BOND disabled). The four DISCOVER investigations (A–D) require VPS SSH access to evaluate. The oracle_sweep disaster consumed the available implementation bandwidth and likely damaged the capital base.

**Highest priority this cycle is operational, not research:**

1. **Verify current bankroll** — Run on VPS: `python3 -c "import json; d=json.load(open('logs/bankroll.json')); print(d)"`. The $84.61 snapshot is 4 days stale. oracle_sweep's "$487 in positions" may have partially redeemed (settled tokens go to redeemer), but even 20% redemption = $97 loss on an $84 bankroll — a solvency question.
2. **Sync logs to git** — Manual one-command sync (VPS): `tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && git add logs/live_trades_recent.jsonl logs/bankroll.json && git commit -m "log sync $(date -u +%Y-%m-%dT%H:%M)" && git push origin claude/find-lag-parameter-rFQ0N`
3. **Enforce experimental strategy kill switch** — Any new sweep/exploit strategy should hard-stop after 3 consecutive losing positions, not run until capital is depleted.

If VPS sync succeeds and bankroll > $50 (above ruin floor), Investigations A and B can run immediately. Run Investigation A first; add one gate at a time.

---

## Infrastructure Alert — SSH (50 consecutive sessions)

Root cause unchanged: TCP port 22 egress blocked at sandbox network boundary. The longer this persists, the larger the gap between coded strategy and observable outcomes. The oracle_sweep disaster ($487 positions, unknown redemption rate) occurred with zero visibility from this sandbox.

Manual VPS sync command (one-time, 30 seconds):
```bash
cd /root/Klaus
python3 -c "import json; d=json.load(open('logs/bankroll.json')); print('capital:', d['capital'], 'trades:', d['total_trades'])"
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "log sync $(date -u +%Y-%m-%dT%H:%M)"
git push origin claude/find-lag-parameter-rFQ0N
```
