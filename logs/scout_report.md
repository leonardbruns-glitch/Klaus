# Alpha Scout Report — 2026-05-07 12:15 UTC

**Method:** Commit-embedded analysis + codebase field audit — VPS SSH unreachable (30th consecutive scout session)
**Connectivity:** SSH binary absent from sandbox; no trades.jsonl or post_exit.jsonl retrievable.
**Data sources used:** git log (commits since last scout 3c006ac, 2026-05-07 00:07 UTC → HEAD 054195d, 11:59 UTC; 14 commits from VPS bot); main.py + data/feeds.py codebase audit; state_log.md; prior scout report.
**Bankroll snapshot (stale — 2026-05-02 04:26 UTC):** capital=$37.32, total_trades=2605, total_pnl=+$87.87

---

## Changes Since Last Scout Report (2026-05-07 00:07 UTC)

Fourteen commits landed in 12 hours, all authored by Klaus Bot from the VPS. Major deployments:

| Commit | Time (UTC) | Change | Evidence base |
|---|---|---|---|
| `7a63a76` | ~10:10 | Adaptive G1 per-session bnc60m bands + session×direction stake matrix | n≥151 per cell (UP); n≥200 per cell (DOWN) |
| `0c07984` | ~10:40 | LATE DOWN G1: skip if bnc60m>0% | n=42 LATE DOWN macro-era; user override n<40 |
| `d54129e` | ~10:34 | DOWN×LDN rollback 0.5x→1.0x | era contamination: May5+ n=18 WR=83.3% +$7.99 |
| `233a396` | ~11:26 | Robust Stack: ask 0.92→0.88, imb 0.30→0.35, tok_d30 sandwich [5,60), Stage 3 shadow log | multi-cell cumulative; user-instructed |
| `fef03b4` | ~11:45 | ETH UP G1: skip if bnc60m>0% | n=53; user override |
| `054195d` | ~11:59 | BTC UP imb floor 0.35→0.50 | Full-era n=175; bucket [0.35,0.50) PF=0.40 net=-$160 |

The VPS is actively analyzing and deploying at high cadence. The era split (pre-May-5 vs May-5+) is now the dominant frame: pre-May-5 n=704 WR=62.8% avg -$0.13 vs May-5+ n=82 WR=81.7% avg +$0.15 for all DOWN trades. All historical analysis before May 5 should be weighted down or excluded.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot momentum in the 5s before entry predicts YES UP resolution.
**MATH:** `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago`

**STATUS: INCONCLUSIVE — n=0 directly retrievable. Critical field clarification from code audit.**

**Field identity correction (important):** `pre_entry_momentum_pct` as logged in trades.jsonl is NOT the 5s delta. From `main.py:3335`:
```python
pre_entry_momentum_pct = _ext_entry.spot_momentum_1m  # 60-second Binance lookback
```
The TRUE 5-second Binance velocity field is `velocity_5s_pct` (from `data/feeds.py:get_velocity_5s`). The mandate's investigation was unknowingly targeting the wrong field. The `pre_entry_momentum_pct` field is effectively a duplicate of the 1m family already exploited by deployed gates.

**Deployed coverage of the 1m signal:**
- YES DOWN: `bnc_dir_skip` skips when `bnc1m > 0%` (BTC rising = skip YES DOWN)
- YES UP: G1 per-session bands `[-0.05%,+0.25%]` / `[0%,+0.30%]` / `[+0.05%,+0.25%]`
- ETH UP: skip when `bnc60m > 0%` (n=53, avg -$1.39 when rising vs avg +$0.95 when falling)
- LATE DOWN: skip when `bnc60m > 0%` (n=42 LATE DOWN)

**Known contamination risk (live):** null-bnc1m YES DOWN (post-restart, ~60 min window): n=149 WR=65% PnL=-$35.72 vs bnc1m-available n=330 WR=68% PnL=+$11.23. The bnc5m fallback was added (commit 47b358d) then reverted (3b2d629). Gate silently disabled for ~60 min after every restart.

**The true uninvestigated field:** `velocity_5s_pct` — Binance aggTrade-based 5s spot velocity. Logged at every BOND entry. Gated ONLY at extreme spike threshold (>0.1% opposing direction). General directional effect never analyzed.

```python
# Run on VPS against logs/trades.jsonl
import json, time
from collections import defaultdict
trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
cutoff = time.time() - 48 * 3600
bond = [t for t in trades
        if t.get("signal_source") == "BOND"
        and t.get("is_live") is True
        and t.get("ts_open", 0) >= cutoff]

for label, grp in [
    ("vel>0 / YES UP",   [t for t in bond if t.get("bond_outcome_direction","up")=="up"   and t.get("velocity_5s_pct",0) > 0]),
    ("vel≤0 / YES UP",   [t for t in bond if t.get("bond_outcome_direction","up")=="up"   and t.get("velocity_5s_pct",0) <= 0]),
    ("vel<0 / YES DOWN", [t for t in bond if t.get("bond_outcome_direction","up")=="down" and t.get("velocity_5s_pct",0) < 0]),
    ("vel≥0 / YES DOWN", [t for t in bond if t.get("bond_outcome_direction","up")=="down" and t.get("velocity_5s_pct",0) >= 0]),
]:
    if len(grp) < 20: print(f"{label}: n={len(grp)} — INCONCLUSIVE"); continue
    wins = sum(1 for t in grp if t.get("net_pnl",0) > 0)
    gw = sum(t["net_pnl"] for t in grp if t.get("net_pnl",0)>0) or 0
    gl = abs(sum(t["net_pnl"] for t in grp if t.get("net_pnl",0)<0)) or 1
    print(f"{label}: n={len(grp)} WR={wins/len(grp):.0%} PF={gw/gl:.2f} net=${sum(t.get('net_pnl',0) for t in grp):.2f}")
```

**RESULT:** No direct data.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET:** Cannot evaluate — n=0. Field identity now clarified: mandate was testing the wrong field. The actual 5s velocity signal (`velocity_5s_pct`) is ungated and uninvestigated.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low `term_tok_tick_count_5s` (thin book, dead market) predicts worse WR for BOND entries.

**STATUS: INCONCLUSIVE — n=0 directly retrievable. No commit-embedded evidence found for this field.**

**Code audit finding:** Both `term_tok_tick_count_5s` (5s count) and `term_tok_tick_count_30s` (30s count) are logged in every BOND trade (`main.py:1370-1371`). Neither appears in any commit message, state_log, or audit report — they have never been analyzed despite ~2000+ BOND trades where these fields are populated.

**Related deployed signal:** `term_ask_stale_s ≥ 4s` is gated (stale ask = bad). Tick count covers the same information domain continuously rather than via the stale threshold.

| Bucket | n | WR | PF |
|---|---|---|---|
| 0–2 ticks | 0 | N/A | N/A |
| 3–5 ticks | 0 | N/A | N/A |
| 6–10 ticks | 0 | N/A | N/A |
| 11+ ticks | 0 | N/A | N/A |

**PROPOSED_GATE:** Cannot set — no data.
**CONCLUSION: INCONCLUSIVE**

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Dead market entries (`|term_token_delta_5s| < 0.005`) underperform active entries.

**STATUS: INCONCLUSIVE — n=0 directly retrievable. Partial structural evidence from code and commits.**

**Architecture clarification:** `DEAD_DRIFT` in the codebase is an EXIT-PHASE classifier set during the hold period (flat MFE + gradual MAE), not an entry signal. The mandate targets entry-time flat token delta.

**Partial signal from commit data:** snap30 floor was raised 10%→10.5% (2026-05-06) after two DEAD_DRIFT-pattern losses: T03785 BTC -$19.65 and T03798 BTC -$16.95, both at snap30_eff=10.39%. These entered with minimal 30s momentum and fell into DEAD_DRIFT exit state. The 5s delta (`term_token_delta_5s`) at entry time is a finer-grained version of the same effect — catches tokens already stalling at entry even if the 30s snapshot is borderline.

**Deployed overlap:** The tok_d30 sandwich `[5, 60)` (Robust Stack, 2026-05-07) gates the 30s token delta below 5%. The 5s delta dead-drift hypothesis adds granularity below the 5% threshold that the 30s sandwich would still pass.

| Group | n | WR | PF |
|---|---|---|---|
| Dead drift (\|Δ5s\| < 0.005) | 0 | N/A | N/A |
| Active (\|Δ5s\| ≥ 0.005) | 0 | N/A | N/A |

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET:** Cannot evaluate — n=0. Structural overlap with snap30/tok_d30 gates means 5s version may yield marginal marginal signal; worth testing but lower priority than Investigation 1.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset (BTC/ETH/SOL) consistently outperforms others in the last 48h.

**STATUS: INCONCLUSIVE — n=0 direct 48h data. Full-era commit-embedded data violates 48h window requirement.**

**Full-era data (all-time — era contamination exists pre-May-5; annotated accordingly):**

| Asset | Direction | n (era) | PF | net | Gate state |
|---|---|---|---|---|---|
| BTC UP | YES UP | 175 at imb≥0.35 | 0.40 | -$161 | imb floor now 0.50; PF=1.08 at ≥0.50 (n=106) |
| BTC DOWN | YES DOWN | unquantified | <1.0 | negative | DEFERRED — "imb-immune AND bnc-immune" |
| ETH UP | YES UP | 53 macro-era | split | bnc60m≥0%: avg -$1.39; bnc60m<0%: avg +$0.95 | G1 skip bnc60m>0% deployed |
| SOL UP | YES UP | 103 | 1.37 | positive | imb≥0.35 (already optimal) |

**48h window (May 5-7) inferred from commits:**
- BTC UP: ≥6 wipeout trades blocked by new imb gate (-$152); 4 night-cluster losses H21-H04 (-$115)
- DOWN (all assets, May5-6): n=82 WR=81.7% avg +$0.15 net +$11.98

**CONCLUSION: INCONCLUSIVE — n < 20 per asset in 48h window. No reweighting warranted.**
**Observation (not a gate):** SOL UP is the healthiest cell (PF=1.37, no further gating needed). BTC DOWN is structurally broken at all gate settings — the single largest unresolved cell. See NEW-C below.

---

## New Variables for Investigation (This Cycle)

### NEW-A: `velocity_5s_pct` — True 5s Binance spot momentum (High priority)

The field the mandate's Investigation 1 was trying to analyze. `pre_entry_momentum_pct` is the 1m version (already gated). `velocity_5s_pct` is the actual 5-second spot velocity at order placement — orthogonal time horizon from both G1 (bnc60m) and bnc_dir_skip (bnc1m).

- **Definition:** % price change over last 5s from Binance aggTrade stream (`feeds.py:get_velocity_5s`)
- **Hypothesis:** YES UP with falling/flat spot (vel_5s ≤ 0) has lower WR than rising spot (vel_5s > 0); symmetric for YES DOWN
- **Current gate:** Only extreme spike suppression at >0.1% opposing direction (`main.py:2011`)
- **Failure criteria:** WR difference < 5pp per direction bucket, or n < 20 per bucket
- **Run snippet:** See Investigation 1 above

### NEW-B: `term_tok_tick_count_5s` bucketed by direction (Medium priority)

2000+ untouched data points. DOWN token books may be systematically thinner than UP token books; direction-specific tick floor may outperform a universal gate.

```python
def tick_bucket(n):
    if n <= 2: return "0-2"
    if n <= 5: return "3-5"
    if n <= 10: return "6-10"
    return "11+"

for direction in ["up", "down"]:
    by_tick = defaultdict(list)
    for t in bond:
        if t.get("bond_outcome_direction","up") == direction:
            by_tick[tick_bucket(t.get("term_tok_tick_count_5s",0))].append(t)
    print(f"--- YES {direction.upper()} ---")
    for b in ["0-2","3-5","6-10","11+"]:
        grp = by_tick[b]
        if not grp: print(f"  {b}: n=0"); continue
        wins = sum(1 for t in grp if t.get("net_pnl",0) > 0)
        print(f"  {b}: n={len(grp)} WR={wins/len(grp):.0%} net=${sum(t.get('net_pnl',0) for t in grp):.2f}")
```

### NEW-C: BTC DOWN base-rate investigation (High priority — VPS-flagged, unresolved)

VPS explicitly identified: "BTC DOWN: imb-immune AND bnc-immune — different failure mode." Sub-50% WR at every imbalance threshold even after bnc1m gating. The question is whether BTC DOWN has a structural directional bias (BTC 5m windows systematically resolve UP more than DOWN) or an hour/session-specific problem.

- **Hypothesis:** BTC DOWN has sub-50% base resolution rate in current regime, making YES DOWN entries systematically unprofitable regardless of OB signal. Check hour×session breakdown.
- **Failure criteria:** WR > 50% for BTC DOWN in any major session disproves systematic deficit

```python
sessions = {"ASIA":(0,8),"LDN":(8,13),"US":(13,18),"LATE":(18,24)}
btc_down = [t for t in bond if t.get("asset")=="BTC" and t.get("bond_outcome_direction","up")=="down"]
print(f"BTC DOWN total: n={len(btc_down)}")
for sess, (h0,h1) in sessions.items():
    grp = [t for t in btc_down if h0 <= (t.get("hour_utc") or int(t.get("ts_open",0))//3600%24) < h1]
    if len(grp) < 10: print(f"  {sess}: n={len(grp)} — thin"); continue
    wins = sum(1 for t in grp if t.get("net_pnl",0) > 0)
    print(f"  {sess}: n={len(grp)} WR={wins/len(grp):.0%} net=${sum(t.get('net_pnl',0) for t in grp):.2f}")
```

### NEW-D: null-bnc1m gate contamination fix (Infrastructure)

Not a signal — a data quality issue. null-bnc1m YES DOWN (post-restart ~60 min) silently disables bnc_dir_skip, letting through bad trades. The bnc5m fallback fix was reverted. Re-add it or log gate-disabled trades for separate tracking:

```python
# In main.py at the YES DOWN bnc_dir_skip block:
_bnc_down_ref = (
    _term_binance_1m if (_term_binance_1m is not None and _term_binance_1m != 0.0)
    else _term_binance_5m if (_term_binance_5m is not None and _term_binance_5m != 0.0)
    else None
)
if _token_dir == "down" and _bnc_down_ref is not None and _bnc_down_ref > 0.0:
    logger.info("[BOND] bnc_dir_skip %s/%s | DOWN src=%s val=%.4f%% — BTC rising, skip",
                token.asset, token.side,
                "b1m" if _term_binance_1m else "b5m", _bnc_down_ref)
    _b_mom_skip += 1; continue
```

---

## Priority Signal for Next Implementation

**`velocity_5s_pct` — the true 5s cross-exchange lead-lag signal (NEW-A).**

All four mandated investigations remain INCONCLUSIVE due to inaccessible trades.jsonl. However, this cycle's code audit revealed a material finding: the mandate's Investigation 1 (`pre_entry_momentum_pct`) targets the wrong field. The 1m momentum signal is already gated (G1, bnc_dir_skip). The uninvestigated 5-second version is `velocity_5s_pct`, logged in every BOND trade, gated only at extreme spike levels.

**Variable:** `velocity_5s_pct`
**Math:** `(price_now - price_5s_ago) / price_5s_ago × 100` via Binance aggTrade WS
**Proposed gate (if n≥20 per bucket and WR diff ≥5pp):** Skip YES UP when `velocity_5s_pct ≤ 0.0`; skip YES DOWN when `velocity_5s_pct ≥ 0.0`
**Implementation location:** main.py, immediately after the existing bnc_dir_skip block
**Failure criteria:** WR difference < 5pp between positive/negative velocity buckets per direction

Second priority: **NEW-C (BTC DOWN base-rate)** — the largest unresolved loss cell, VPS-identified but never quantified.

---

## Infrastructure Alert — Critical (30 consecutive scout sessions)

**Root cause:** SSH binary absent from sandbox. TCP port 22 egress blocked at network level.

**VPS IS running** — 14 VPS-authored commits in 12 hours today. Cron sync is the only blocker.

**One-time manual sync (30 seconds on VPS):**
```bash
cd /root/Klaus && tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
git add logs/live_trades_recent.jsonl logs/bankroll.json && \
git commit -m "manual log sync $(date -u)" && git push origin claude/find-lag-parameter-rFQ0N
```

**Permanent cron unblock:**
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
