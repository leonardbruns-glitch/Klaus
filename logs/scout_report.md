# Alpha Scout Report — 2026-05-06 12:10 UTC

**Method:** Commit-embedded analysis — VPS SSH unreachable (28th consecutive scout session since VPS became unreachable; 34th session total with this blocker)
**Connectivity:** SSH binary present (openssh-client 9.6p1), but TCP port 22 to 85.137.174.86 times out (~15s). Egress blocked from sandbox (firewall or VPS unreachable). No trades.jsonl or post_exit.jsonl retrievable.
**Data sources used:** git log (commits 9b88027 → b9056f6, May 6 00:07 → 10:52 UTC; 5 commits since last scout)
**Bankroll snapshot (stale — 2026-05-02 04:26 UTC):** capital=$37.32 (pre-$50 deposit), total_trades=2605, total_pnl=+$87.87

---

## Changes Since Last Scout Report (2026-05-06 00:07 UTC)

| Commit | Time (UTC) | Change |
|---|---|---|
| `2169759` | ~04:26 | **BUG FIX**: Resolution corrector was inverting exit_price for YES DOWN trades — `_wop=0.0` (down) → `min(0.0, 0.99)=0.0` instead of `0.99`. YES DOWN wins logged as losses, YES DOWN losses logged as wins. Fix: use `_entered_correctly` flag. Affects all historical YES DOWN `exit_price_uncertain` records in trades.jsonl. |
| `ae6707d` | ~05:07 | **NEW TOOL**: `analytics/lag_detector.py` — simultaneous Binance aggTrade WS + Polymarket CLOB market WS subscriber, ms-precision lag measurement. Logs to `logs/lag_ws_events.jsonl`. Run `python3 analytics/lag_detector.py --duration 3600` on VPS. |
| `b9056f6` | ~10:52 | **FIX lag_detector**: Token re-discovery every 4 min (5m windows expire; old token list went silent after ~22 min). Also fixes `direction_match` → `dir_match` key mismatch in summary. |

**Net effect:** YES DOWN trade history in logs is now corrected. The cross-exchange lag detector is built and ready to run on VPS.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot momentum in the 5s before entry (`pre_entry_momentum_pct > 0`) predicts higher YES resolution rate for YES UP entries.
**MATH:** `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago`

**STATUS: INCONCLUSIVE — n=0 retrievable (28th consecutive cycle)**

**Data note (critical):** Commit `2169759` fixed a resolution corrector bug that inverted exit_price for all `exit_price_uncertain` YES DOWN trades. Any prior analysis of YES DOWN P&L from trades.jsonl is corrupted. Investigation 1 is YES UP only (direction-guarded Binance gate already deployed since May 4), so this does not affect the deployed gate logic, but it does mean any mixed-direction analysis in prior cycles would be skewed.

**New tool available:** `analytics/lag_detector.py` directly measures the Binance→Polymarket repricing lag at ms precision. If the lag is consistently > 2–3s, our 5s `pre_entry_momentum_pct` window captures a real signal. If the lag is sub-500ms, the signal is already arbed away before our entry fires. Run on VPS: `python3 analytics/lag_detector.py --duration 3600 && python3 analytics/lag_detector.py --summarize`

**RESULT:** No data. Cannot bucket `pre_entry_momentum_pct`.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Cannot evaluate — n=0**

---

## Investigation 2: Tick Count Filter

**HYPOTHESIS:** Low tick count (`term_tok_tick_count_5s` ≤ 2) = thin/dead market = adverse selection. High tick count = informed flow = better WR.

**STATUS: INCONCLUSIVE — n=0 retrievable (28th consecutive cycle)**

**RESULT:** No data.

| Bucket | n | WR | PF |
|---|---|---|---|
| 0–2 ticks | 0 | N/A | N/A |
| 3–5 ticks | 0 | N/A | N/A |
| 6–10 ticks | 0 | N/A | N/A |
| 11+ ticks | 0 | N/A | N/A |

**PROPOSED_GATE:** Cannot set min_tick_count — no data.
**CONCLUSION: INCONCLUSIVE**

**Python snippet (run on VPS):**
```python
import json, time
from collections import defaultdict

trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
cutoff = time.time() - 48 * 3600
term = [t for t in trades
        if t.get("signal_source") == "BOND"
        and t.get("is_live") is True
        and t.get("entry_price", 0) >= 0.80
        and t.get("ts", 0) >= cutoff]

def bucket(tc):
    if tc <= 2:  return "0-2"
    if tc <= 5:  return "3-5"
    if tc <= 10: return "6-10"
    return "11+"

by_bucket = defaultdict(list)
for t in term:
    tc = t.get("term_tok_tick_count_5s", 0) or 0
    by_bucket[bucket(tc)].append(t)

for b in ["0-2", "3-5", "6-10", "11+"]:
    group = by_bucket[b]
    if not group:
        print(f"{b}: n=0"); continue
    wins = sum(1 for t in group if t.get("net_pnl", 0) > 0)
    pf_g = sum(t["net_pnl"] for t in group if t.get("net_pnl", 0) > 0) or 0
    pf_l = abs(sum(t["net_pnl"] for t in group if t.get("net_pnl", 0) < 0)) or 1
    print(f"{b}: n={len(group)} WR={wins/len(group):.0%} PF={pf_g/pf_l:.2f}")
```

---

## Investigation 3: Dead Drift

**HYPOTHESIS:** Dead market entries (`|term_token_delta_5s| < 0.005`) underperform active entries.

**STATUS: INCONCLUSIVE — n=0 retrievable (28th consecutive cycle)**

**RESULT:** No data.

| Group | n | WR | PF |
|---|---|---|---|
| Dead drift (\|Δ\| < 0.005) | 0 | N/A | N/A |
| Active (\|Δ\| ≥ 0.005) | 0 | N/A | N/A |

**CONCLUSION: INCONCLUSIVE**

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset (BTC/ETH/SOL) outperforms others in TERMINAL BOND strategy and deserves reweighted stake.

**STATUS: INCONCLUSIVE — n=0 retrievable (28th consecutive cycle)**

**RESULT:** No data.

| Asset | n (48h) | WR | PF | Avg net_pnl |
|---|---|---|---|---|
| BTC | 0 | N/A | N/A | N/A |
| ETH | 0 | N/A | N/A | N/A |
| SOL | 0 | N/A | N/A | N/A |

**CONCLUSION: INCONCLUSIVE — n < 20 per asset; no reweighting warranted**

**Note:** ETH `sust` gate (tok_d30 > 0.5% AND tok_d60 > 0.5%) was deployed 2026-05-05 based on n=13 ETH trades (0/13 winners had sust=False). This gate remains unvalidated on larger n.

---

## Priority Signal for Next Implementation

**No actionable signals this cycle — continue data collection.**

The strongest candidate remains the tick count filter (Investigation 2), which has never been evaluated due to 28 consecutive cycles of data inaccessibility. No signal reaches SIGNAL_FOUND threshold this cycle.

**Data quality note (not a new signal, but affects all future analysis):**

Commit `2169759` fixed a resolution corrector bug: YES DOWN `exit_price_uncertain` trades had inverted exit_price before ~2026-05-06 04:26 UTC. When VPS data becomes accessible, filter corrupted records with:
```python
# Corrupted: YES DOWN + exit_price_uncertain + ts before fix
CORRUPT_CUTOFF = 1746505590  # ~2026-05-06 04:26 UTC
is_clean = not (
    t.get("direction") == "YES DOWN"
    and t.get("exit_price_uncertain")
    and t.get("ts", 9e9) < CORRUPT_CUTOFF
)
```

---

## Infrastructure Alert — Critical (28 consecutive scout sessions)

**VPS SSH unreachable from sandbox.**

| Method | Status |
|---|---|
| SSH binary | Present (openssh-client 9.6p1) |
| TCP port 22 to 85.137.174.86 | **TIMEOUT** (~15s) — sandbox firewall blocks outbound port 22, or VPS firewall blocks this IP, or VPS is down |
| cron sync to git | Not deployed — no live_trades_recent.jsonl in repo |

**Fix (run ONE of these on VPS — unblocks all future scout cycles permanently):**

**Option A: One-time manual sync**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Option B: Cron sync (every 30 minutes)**
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

**Option C: Run lag_detector on VPS and commit output**
```bash
cd /root/Klaus
python3 analytics/lag_detector.py --duration 3600
git add logs/lag_ws_events.jsonl
git commit -m "lag detector 1h run $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```
This answers Investigation 1 directly at ms precision without needing trades.jsonl.

Without log data, all four mandated investigations remain structurally blocked.
