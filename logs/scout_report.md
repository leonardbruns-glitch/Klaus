# Alpha Scout Report — 2026-05-07 00:07 UTC

**Method:** Commit-embedded analysis + codebase field audit — VPS SSH unreachable (29th consecutive scout session)
**Connectivity:** SSH binary absent from sandbox; TCP port 22 to 85.137.174.86 times out. No trades.jsonl or post_exit.jsonl retrievable.
**Data sources used:** git log (commits 2169759 → 2b8fdf7, 2026-05-06 04:26 → 22:17 UTC; 6 commits since last scout); main.py code analysis for un-gated logged fields
**Bankroll snapshot (stale — 2026-05-02 04:26 UTC):** capital=$37.32, total_trades=2605, total_pnl=+$87.87

---

## Changes Since Last Scout Report (2026-05-06 12:10 UTC)

| Commit | Time (UTC) | Change |
|---|---|---|
| `351f2e2` | ~13:18 | snap60 floor raised 12%→25% during 12:30–13:30 UTC (5/5 H12 losses had snap60_eff<25%) |
| `fe26969` | ~13:53 | Real-time reversal gate: tok_d60<−5% blocks entry (May5 n=89: catches 5 losses −$52.45, costs 5 wins $3.94, net +$48.51) |
| `040b15d` | ~14:09 | Fix EXT exit logging: 8s CLOB retry before recording exit_price=0.0 |
| `455f1ec` | ~16:xx | snap30 floor raised 10%→10.5% ([10,10.5) WR=33% pnl=−$34.70, n=3) |
| `1b68cf3` | ~17:xx | ETH snap60 floor raised to 15% (both dirs): [12,14) WR=0% pnl=−$39.08 |
| `f96e37a` | ~18:xx | Equity-pct stake tiers: snap60≥50%→18%, snap60≥20%+rem≥75s→14% of equity |
| `dbe9f07` | ~19:xx | Raise base_stake $20→$30; floor equity tiers at base_stake |
| `c666111` | ~20:xx | Bug fix: $30 base_stake not applied to BOND orders (hardcoded $20 cap in manager.py) |
| `2b8fdf7` | ~22:17 | H21 TERMINAL: rem cap 60s + tok_d30≥35 gate (n=78 H21: combined saves +$59 vs baseline) |

**Net effect:** 9 changes in 10 hours after last scout report, all from VPS-side analysis. The bot IS running and analyzing live data — the cron sync recommendation from prior cycles remains the only blocker for scout-side analysis.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot momentum in the 5s before entry (`pre_entry_momentum_pct > 0`) predicts higher YES resolution rate for YES UP entries.
**MATH:** `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago`

**STATUS: INCONCLUSIVE — n=0 retrievable (29th consecutive cycle)**

**Deployment context:** The direction-aware Binance 1m gate (bnc_dir_skip) was added 2026-05-04, derived from this hypothesis applied at 1m resolution. W avg=+0.0028%, L avg=−0.0023%, Δ=0.0051%**. The 5s version (`pre_entry_momentum_pct` / `term_spot_delta_5s`) remains ungated — it may carry residual signal not captured by the 1m gate. A parallel field `velocity_5s_pct` (Binance 5s velocity from WS aggTrades) is also logged but ungated.

**New data needed (run on VPS):**
```python
import json, time
from collections import defaultdict
trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
cutoff = time.time() - 48 * 3600
bond = [t for t in trades
        if t.get("signal_source") == "BOND"
        and t.get("is_live") is True
        and t.get("ts_open", 0) >= cutoff]
up = [t for t in bond if t.get("bond_outcome_direction") == "up"]
# Bucket pre_entry_momentum_pct
for label, grp in [("mom<0", [t for t in up if t.get("pre_entry_momentum_pct",0) < 0]),
                   ("mom≥0", [t for t in up if t.get("pre_entry_momentum_pct",0) >= 0])]:
    if not grp:
        print(f"{label}: n=0"); continue
    wins = sum(1 for t in grp if t.get("net_pnl", 0) > 0)
    print(f"{label}: n={len(grp)} WR={wins/len(grp):.0%}")
```

**RESULT:** No data.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Cannot evaluate — n=0**

---

## Investigation 2: Tick Count Filter

**HYPOTHESIS:** Low tick count (`term_tok_tick_count_5s` ≤ 2) = thin/dead market = adverse selection. High tick count = informed flow = better WR.

**STATUS: INCONCLUSIVE — n=0 retrievable (29th consecutive cycle)**

**Deployment context:** `term_tok_tick_count_30s` (distinct ask price changes in last 30s) is also logged. Neither 5s nor 30s tick count has been gated. The `term_ask_stale_s` field (seconds since ask last changed) is a complementary signal — already gated at ≥4s (losers T02829 −$9.94, T02814 −$7.22 in 4–7s zone). The stale<1.0 zone (active repricing) shows 13W/17L (43% WR) in sim — not gated, logging only.

**RESULT:** No data.

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

**STATUS: INCONCLUSIVE — n=0 retrievable (29th consecutive cycle)**

**Deployment context:** The extreme end of this signal IS already gated: `d5s_blowoff > 25%` was added with n=49 (WR=43%, PF=0.47, net=−$18.4 vs rest WR=66%, PF=1.15, net=+$25.7). The dead drift hypothesis (very LOW delta) is distinct and ungated. Related: snap30 floor was raised to 10.5% to catch the lowest-momentum trades ([10,10.5) WR=33%, pnl=−$34.70, n=3). The dead drift hypothesis using 5s delta is a finer-grained version of this same effect.

**New related field (ungated):** `term_tok_decel_ratio` (d5s/d30s, clamped [−3,3]) — gated only at ≥2.0 for YES UP (n=2, WR=0%). The range [0, 2.0) has never been analyzed. If decel_ratio < 0.5 (5s momentum is less than half of 30s momentum), the move may be stalling.

**RESULT:** No data.

| Group | n | WR | PF |
|---|---|---|---|
| Dead drift (|Δ5s| < 0.005) | 0 | N/A | N/A |
| Active (|Δ5s| ≥ 0.005) | 0 | N/A | N/A |

**CONCLUSION: INCONCLUSIVE**

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset (BTC/ETH/SOL) outperforms others in TERMINAL BOND strategy in the last 48h.

**STATUS: INCONCLUSIVE — n=0 retrievable directly. Partial data from commit-embedded evidence.**

**Commit-extracted data (all-time, not 48h — use with caution):**

| Asset | Gate-derived WR | pnl | n | Notes |
|---|---|---|---|---|
| BTC | ~43% (btc_daccel flat n=38) / ~43% (not_sust n=54) | −$151 / −$169 | 38/54 | Two major loss pools found and gated |
| ETH | 38% flat_tok_d30 [0,2) | −$92 | n=26 | 0% WR at snap60 [12,14) n=small |
| SOL | 65% late entry (elapsed≥0.75) | −$46 | n=29 | spread>3%: −$12.17 drag |

These are the populations that TRIGGERED gates, so they represent the worst-performing buckets, not overall WR. Actual WR on live trades that PASSED all gates is unknown without trades.jsonl.

**RESULT:** No 48h data.

| Asset | n (48h) | WR | PF | Avg net_pnl |
|---|---|---|---|---|
| BTC | 0 | N/A | N/A | N/A |
| ETH | 0 | N/A | N/A | N/A |
| SOL | 0 | N/A | N/A | N/A |

**CONCLUSION: INCONCLUSIVE — n < 20 per asset in accessible window. No reweighting warranted.**

**Note (ETH):** The ETH sust gate (tok_d30>0.5% AND tok_d60>0.5%) was deployed on n=13. Still needs validation at n≥50.

---

## New Variables for Investigation (added this cycle)

Six logged fields with no gate and sufficient theoretical basis for analysis. Run these against trades.jsonl on VPS.

### NEW-1: `term_tok_decel_ratio` in [0.0, 2.0)
- **Definition:** d5s/d30s (5s token delta / 30s token delta), clamped [−3, 3]
- **Hypothesis:** decel_ratio < 0.5 = momentum stalling before entry = adverse resolution
- **Gate threshold gated at:** ≥2.0 YES UP only (n=2, n too small — Tier2 note in code)
- **Failure criteria:** WR difference between decel<0.5 and decel≥0.5 less than 5pp

```python
for label, grp in [("decel<0.5", [t for t in bond if 0 < t.get("term_tok_decel_ratio",1) < 0.5]),
                   ("decel≥0.5", [t for t in bond if t.get("term_tok_decel_ratio",1) >= 0.5])]:
    if not grp: print(f"{label}: n=0"); continue
    wins = sum(1 for t in grp if t.get("net_pnl", 0) > 0)
    pf_g = sum(t["net_pnl"] for t in grp if t.get("net_pnl",0) > 0) or 0
    pf_l = abs(sum(t["net_pnl"] for t in grp if t.get("net_pnl",0) < 0)) or 1
    print(f"{label}: n={len(grp)} WR={wins/len(grp):.0%} PF={pf_g/pf_l:.2f}")
```

### NEW-2: `term_ask_stale_s` in [1.0, 4.0)
- **Definition:** seconds since ask last changed in scan-loop history
- **Context:** stale≥4s gated (losers T02829/T02814). stale<1.0 = log-only (sim: 13W/17L = 43% WR)
- **Hypothesis:** stale in [1, 2) zone is optimal; stale≥2 but <4 may have elevated loss rate
- **Failure criteria:** WR spread < 5pp across [0,1), [1,2), [2,4) buckets

```python
def stale_bucket(s):
    if s < 1.0: return "<1.0"
    if s < 2.0: return "1-2"
    if s < 4.0: return "2-4"
    return "≥4 (gated)"
by_stale = defaultdict(list)
for t in bond:
    by_stale[stale_bucket(t.get("term_ask_stale_s", 999))].append(t)
for b in ["<1.0","1-2","2-4","≥4 (gated)"]:
    grp = by_stale[b]
    if not grp: print(f"{b}: n=0"); continue
    wins = sum(1 for t in grp if t.get("net_pnl",0) > 0)
    print(f"{b}: n={len(grp)} WR={wins/len(grp):.0%}")
```

### NEW-3: `bond_llm_shadow_pnl` — LLM shadow validation
- **Definition:** what the LLM's shadow TP/SL would have made if executed
- **Hypothesis:** trades where `bond_llm_decision == "TAKE"` have higher WR than "SKIP" — validates LLM signal
- **Failure criteria:** WR difference < 5pp, or n < 20 per bucket

```python
for label, grp in [("LLM_TAKE", [t for t in bond if t.get("bond_llm_decision") == "TAKE"]),
                   ("LLM_SKIP", [t for t in bond if t.get("bond_llm_decision") == "SKIP"])]:
    if not grp: print(f"{label}: n=0"); continue
    wins = sum(1 for t in grp if t.get("net_pnl",0) > 0)
    shadow = sum(t.get("bond_llm_shadow_pnl", 0) for t in grp)
    print(f"{label}: n={len(grp)} WR={wins/len(grp):.0%} shadow_pnl=${shadow:.2f}")
```

### NEW-4: `pre_score` — Layer-1 composite quality gate (observation mode)
- **Definition:** composite pre-causal entry quality score (accel, daccel, edge, stab, vel, class)
- **Context:** deployed in observation mode only — never blocks trades
- **Hypothesis:** pre_score < 0.40 predicts loss; pre_score ≥ 0.60 predicts win
- **Failure criteria:** WR difference < 5pp across score buckets, or pre_score=0 in >50% of records (data not populated)

```python
for label, grp in [("pre<0.40", [t for t in bond if 0 < t.get("pre_score",0) < 0.40]),
                   ("pre≥0.40", [t for t in bond if t.get("pre_score",0) >= 0.40])]:
    if not grp: print(f"{label}: n=0"); continue
    wins = sum(1 for t in grp if t.get("net_pnl",0) > 0)
    pf_g = sum(t["net_pnl"] for t in grp if t.get("net_pnl",0) > 0) or 0
    pf_l = abs(sum(t["net_pnl"] for t in grp if t.get("net_pnl",0) < 0)) or 1
    print(f"{label}: n={len(grp)} WR={wins/len(grp):.0%} PF={pf_g/pf_l:.2f}")
```

---

## Priority Signal for Next Implementation

**No actionable signals this cycle — continue data collection.**

All four mandated investigations remain INCONCLUSIVE due to 29 consecutive cycles of VPS SSH inaccessibility. The strongest unvalidated candidate remains Investigation 2 (tick count filter) and NEW-1 (decel_ratio [0, 2.0) bucket) — both logged in every BOND trade, neither gated.

**VPS-side evidence this cycle (from commit messages):** The H21 gate (tok_d30≥35, rem≤60s) was deployed with n=78 H21 TERMINAL trades and saves +$59 combined. The ETH snap60 floor at 15% was deployed with limited n (small sample flag in audit_report). Both need validation at n≥100.

---

## Infrastructure Alert — Critical (29 consecutive scout sessions)

**Root cause:** Sandbox outbound port 22 blocked (confirmed TCP timeout to 85.137.174.86:22). No SSH binary in this environment.

**VPS IS running** — 9 commits pushed from VPS-side analysis in last 10 hours today, all from `Klaus Bot <bot@Klaus.local>`. The VPS can push to git. The following cron deploys in 30 seconds and unblocks all future scout cycles permanently:

**Option A: One-time manual sync (30 seconds)**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Option B: Cron sync (every 30 minutes, permanent)**
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

**Option C: Run analysis scripts and commit output**
```bash
cd /root/Klaus
python3 analytics/lag_detector.py --duration 3600
git add logs/lag_ws_events.jsonl
git commit -m "lag detector 1h run $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

Without log data, all four mandated investigations remain structurally blocked.
