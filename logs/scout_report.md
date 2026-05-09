# Alpha Scout Report — 2026-05-09 10:15 UTC

**Method:** Commit-embedded analysis + shadow pipeline data extraction + codebase audit — VPS SSH unreachable (31st consecutive scout session)
**Connectivity:** SSH binary available (openssh-client installed) but TCP port 22 egress blocked at sandbox network boundary. No direct trades.jsonl or post_exit.jsonl retrievable.
**Data sources used:** git log (commits since last scout 3597881, 2026-05-07 12:15 UTC → HEAD 2c3b550, 2026-05-09 09:28 UTC; 34 commits from VPS bot); main.py + analytics/ codebase audit; state_log.md; bankroll.json; shadow pipeline commit messages with embedded n and WR data.
**Bankroll snapshot (bankroll.json in repo):** capital=$84.61, total_trades=2605, total_pnl=+$87.87, saved_ts≈2026-05-05/06 (last git sync). Stake cap at $7 per trade (active drawdown mode).

---

## Changes Since Last Scout Report (2026-05-07 12:15 UTC)

34 commits landed in 46 hours. Major deployments — all VPS-authored from shadow pipeline data:

| Commit | Time (UTC) | Change | Evidence base |
|---|---|---|---|
| `d40ca92` | 05-08 21:17 | ask_max 0.92→0.95; ob_imb floor 0.20 only; snap30/snap60 gates removed | shadow: imb≥0.20 YES=88.6%, ask[0.92,0.95) YES=92.5% n=1724 |
| `a3459e1` | 05-08 19:18 | PT 0.99→0.95; BOND_PT95_TIMEOUT +30s; stake cap $10 | live n=219, 4d: +$155 sim, cat-rate 33× reduction |
| `8fff5c9` | 05-08 19:22 | Stake cap $10→$7 | User instruction — active drawdown mode |
| `d3d49d8` | 05-08 23:01 | PT95_TIMEOUT conditional on bid < entry_price | Phase 2 shadow n=246: T+30s winners +2–6% / losers −22%; hard timeout cut 55% of PT hitters |
| `09e27ae` | 05-08 23:22 | snap30/snap60 all gates removed (Model A) | Phase 2 ablation n=499: snap30/snap60 Pearson r=0.71 (redundant); ob_imb orthogonal |
| `2c3b550` | 05-09 09:28 | **BUG FIX**: direction-aware resolution join for YES-DOWN tokens | All prior DOWN shadow analysis corrupted (resolved_yes was UP-direction for DOWN joins) |
| `61ac630` | 05-09 09:11 | Shadow Phase 2: 6 new signal fields + anti-overfitting analytics | Adds binance_ret_1m_pct, binance_ret_60m_pct, vpin_score, tok_delta_5s, tok_decel_ratio, ask_stale_s |

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot velocity in the 5s before entry (`velocity_5s_pct`) predicts YES UP resolution; negative velocity predicts YES DOWN (spot → token lead-lag at 5s resolution).
**MATH:** `pre_entry_momentum_pct = (spot_now − spot_5s_ago) / spot_5s_ago × 100` via Binance aggTrade WS

**STATUS: INCONCLUSIVE — n=0 directly retrievable. Shadow pipeline captures 30s/60s Binance returns but NOT the 5s velocity field.**

**Structural context from code audit:**
- `velocity_5s_pct` IS logged in trades.jsonl at every BOND entry (main.py:3618)
- The only live gate on this field: extreme opposing spike >0.1% (`_VEL_THRESHOLD_SPIKE = 0.001`, main.py:2133) — directional effect in the normal range (-0.1% to +0.1%) is ungated
- Shadow Phase 2 (commit 61ac630, deployed 2026-05-09 09:11) adds `binance_ret_1m_pct` and `binance_ret_60m_pct` to market_timeline but NOT `velocity_5s_pct` (the 5-second Binance spot velocity)
- `signal_analysis.py` continuous signals list: includes `binance_ret_30s_pct`, `binance_ret_60s_pct`, `binance_ret_1m_pct`, `binance_ret_60m_pct` — 5s field absent
- **Gap**: the tok5_gate (token 5s delta) covers the TOKEN side. The Binance SPOT side at 5s resolution has no corresponding shadow field for correlation analysis.

**WR by momentum bucket:** Cannot compute — n=0 from trades.jsonl.

**RESULT:** No quantitative outcome data. Shadow infrastructure does not yet capture velocity_5s_pct for cross-window analysis.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET:** Cannot evaluate — n=0. Structural gap confirmed: shadow lacks the 5s Binance spot field needed for this investigation. Adding `velocity_5s_pct` to shadow market_timeline is a prerequisite.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low `term_tok_tick_count_5s` (thin/dead book in 5s before entry) predicts lower WR for BOND entries.

**STATUS: INCONCLUSIVE — n=0 directly retrievable.**

**Structural context from code audit:**
- `term_tok_tick_count_5s` and `term_tok_tick_count_30s` computed at main.py:2512 and logged in every BOND trade (main.py:2614–2615) and in trades.jsonl (main.py:1492–1493)
- Shadow market_timeline records 1Hz OB snapshots but does NOT log per-second tick counts; the field is trades.jsonl-only
- No commit message, state_log entry, or shadow analysis references this field in 2605 trades
- Related deployed signal: `term_ask_stale_s ≥ 4s` gate (stale ask = thin book proxy) — tick count is the continuous version of the same signal

| Bucket | n | WR | PF |
|---|---|---|---|
| 0–2 ticks | 0 | N/A | N/A |
| 3–5 ticks | 0 | N/A | N/A |
| 6–10 ticks | 0 | N/A | N/A |
| 11+ ticks | 0 | N/A | N/A |

**PROPOSED_GATE:** Cannot set — no outcome data.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET:** Cannot evaluate — n=0.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Dead market entries (`|term_token_delta_5s| < 0.005`) underperform active entries.

**STATUS: INCONCLUSIVE on the 5s field specifically. Available 30s data CONTRADICTS the hypothesis direction.**

**Critical finding from shadow data (commit d40ca92, shadow n=499, n=1724):**

The snap30 gate was removed because the data showed the OPPOSITE of dead drift toxicity:
- snap30 [0, 10.5%) YES rate = **90.2%** — this is the "nearly flat / low momentum" zone
- snap30 [10.5%, 80%) YES rate = **84.0%** — this is the "active momentum" zone
- Implication: at 30s resolution, flat-to-low pre-entry token movement predicts HIGHER YES probability than elevated momentum

This directly contradicts the dead drift hypothesis at the 30s window. The snap30 gate was removed because the low-momentum zone outperforms.

**Partial 5s coverage (tok5_gate calibration, commit c9e3e5c, May6-7 n=52 UP trades):**
- tok_d5 in [5, 10%] = 100% WR (n=9) — the ACTIVE zone is best for UP
- tok_d5 > 10% = 4 losers avg −$22 vs 7 winners ($21) — overbought = snap-back
- tok_d5 in [2, 5%] = losers attributed to snap60 failures, not velocity itself
- **The "dead drift" zone (tok_d5 ≈ 0) was NOT identified as a loss cluster in this data**

| Group | n | WR | Notes |
|---|---|---|---|
| Dead drift (\|Δ5s\| < 0.5%) | 0 | N/A | Not separable from trades.jsonl |
| Active (Δ5s ≥ 0.5%) | 52 (UP) | varies | tok5_gate calibrated on adverses only |

**CONCLUSION: INCONCLUSIVE on 5s specifically; 30s analog CONTRADICTS hypothesis**
**FAILURE_MET:** No direct 5s data. The 30s evidence goes the wrong way — low-momentum entries appear statistically BETTER, not worse. This weakens the prior for the 5s version. Lowest priority of the four investigations.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset (BTC/ETH/SOL) consistently outperforms others in the last 48h (May 7–9 UTC).

**STATUS: INCONCLUSIVE — n=0 direct 48h data. Shadow pipeline data not broken down by asset in commit messages.**

**Structural finding (CRITICAL — commit 2c3b550, 2026-05-09 09:28):**

A direction-aware resolution join bug was active in all shadow analysis since Phase 1 launch (2026-05-08 07:40). The window_resolution table stores one record per `(condition_id, window_end_ts)` using the FIRST scheduling call's `outcome_dir` — which is always `"up"` in practice. YES-DOWN tokens joining on this key received UP-direction `resolved_yes`, inverting their outcome labels. **All prior shadow analysis of DOWN trades is corrupted — the "YES" label was systematically wrong for DOWN tokens.**

This means:
- The ob_imb ≥ 0.20 gate calibration (imb≥0.20 YES=88.6%, d40ca92) used combined UP+DOWN data. The UP component is clean; the DOWN component was label-inverted. The 88.6% figure is suspect for any DOWN-specific claim.
- The per-asset ceilings removal ("no shadow evidence differentiating by asset") may be partially an artifact of label corruption on DOWN assets.
- Fix deployed at 09:28 UTC today. All shadow DOWN analysis from 2026-05-08 through 2026-05-09 09:28 must be re-run after 24–48h of clean data accumulates.

**Available full-era inference (pre-May-5 contaminated, annotated):**

| Asset | Direction | Status |
|---|---|---|
| BTC UP | YES UP | imb floor raised 0.35→0.50→0.20; current n unknown |
| BTC DOWN | YES DOWN | Shadow labels corrupted (2c3b550). Structural losses all-era. Highest priority for re-analysis. |
| ETH UP | YES UP | G1 bnc60m gate active; shadow labels clean (UP) |
| ETH DOWN | YES DOWN | Shadow labels corrupted (2c3b550). |
| SOL UP | YES UP | PF=1.37 full-era (prior report). Healthiest cell. Shadow labels clean (UP) |
| SOL DOWN | YES DOWN | depth<100 gate deployed. Shadow labels corrupted (2c3b550). |

**CONCLUSION: INCONCLUSIVE — n < 20 per asset in 48h window. Resolution bug fix makes all DOWN data unreliable until shadow re-runs ≥48h.**

---

## Critical Infrastructure Finding — Resolution Bug (Non-Optional)

**Commit 2c3b550 (2026-05-09 09:28 UTC) — direction-aware resolution join fixed.**

This is the highest-priority finding this cycle. The bug caused `resolved_yes` to be inverted for all YES-DOWN tokens in shadow analysis since Phase 1 launch (2026-05-08 07:40). Specifically:
- `gate_relaxation.py` and `signal_analysis.py` both affected
- Any gate threshold set from shadow data for DOWN trades must be treated as derived from inverted labels
- The fix is deployed. Clean DOWN data will accumulate starting 2026-05-09 09:28 UTC.
- **Do not make DOWN-specific gate changes based on shadow data until n≥50 clean DOWN records accumulate (est. 24–36h).**

The UP-direction shadow data (BTC UP, ETH UP, SOL UP) was NOT affected by this bug and remains valid.

---

## New Variables for Investigation (This Cycle)

### NEW-A: `velocity_5s_pct` in shadow market_timeline (High priority — unchanged from prior cycle)

The shadow Phase 2 (61ac630) adds `binance_ret_1m_pct` and `binance_ret_60m_pct` but omits the 5s Binance spot velocity — the true uninvestigated cross-exchange lead-lag field. Add to shadow market_timeline and signal_analysis CONTINUOUS_SIGNALS:

```python
# In data/shadow/timeline.py, after binance_ret_1m_pct assignment:
try:
    vel_5s, _ = self.feed.get_velocity_5s(token.asset)
    row["binance_vel_5s_pct"] = round(vel_5s * 100, 4) if vel_5s is not None else None
except Exception:
    row["binance_vel_5s_pct"] = None

# In analytics/signal_analysis.py CONTINUOUS_SIGNALS list:
"binance_vel_5s_pct",
```

**Failure criteria:** WR difference < 5pp between positive/negative velocity buckets per direction (UP and DOWN analyzed separately; DOWN data not valid until post-bug-fix accumulation).

### NEW-B: Clean DOWN analysis post-bug-fix (High priority — timing-gated)

After 36h of shadow data accumulates (est. 2026-05-10 22:00 UTC), run `gate_relaxation.py` and `signal_analysis.py` on DOWN tokens only to check:
1. ob_imb threshold for DOWN: is 0.20 still the right floor with clean labels?
2. Asset breakdown: which DOWN asset has the worst base rate?
3. BTC DOWN structural check: does BTC DOWN still show sub-50% YES rate after label correction, or was the negative result an artifact?

```python
# Filter for clean post-fix data:
CLEAN_CUTOFF_TS = 1778387908  # 2026-05-09 09:28 UTC (commit 2c3b550)
down_rows = [r for r in shadow_rows
             if r.get("outcome_dir") == "down"
             and r.get("ts", 0) >= CLEAN_CUTOFF_TS]
```

### NEW-C: VPIN as informed-flow toxicity gate (Medium priority)

Phase 2 shadow now logs `vpin_score` (order-flow toxicity, requires `_trade_count > 50`). VPIN measures the fraction of buy vs sell imbalance in recent aggTrades — high VPIN = informed traders are active = adverse selection risk. Hypothesis: VPIN > 0.6 predicts lower YES rate for token entries (informed sellers moving against position).

The field is now in market_timeline (commit 61ac630). Will reach n≥50 per bucket in ~48h.

**Failure criteria:** WR difference < 5pp between VPIN > 0.6 and VPIN ≤ 0.6 cohorts, or n < 20 per bucket.

### NEW-D: `tok_decel_ratio` as momentum quality gate (Medium priority)

Phase 2 shadow also adds `tok_decel_ratio = min(3.0, max(-3.0, tok_delta_5s / tok_delta_30s))`. Values near 0 = token is decelerating versus its 30s momentum; values near 1+ = maintaining or accelerating. Hypothesis: entries with `tok_decel_ratio < 0` (5s direction opposes 30s trend) have lower YES resolution rate.

This is the same field already logged in trades.jsonl as `term_tok_decel_ratio` (main.py:2550) but never analyzed. The shadow now captures it for correlation analysis.

---

## Priority Signal for Next Implementation

**Add `binance_vel_5s_pct` to shadow market_timeline — 2 lines of code, immediate data accumulation.**

All four mandated investigations remain INCONCLUSIVE due to inaccessible trades.jsonl (31st consecutive session). The shadow pipeline is now the primary data source, but it is missing the 5s Binance spot velocity field — the exact signal that Investigation 1 targets.

This is a data collection blocker, not a gate blocker. The fix is:
1. Add `binance_vel_5s_pct` to `data/shadow/timeline.py` (4 lines)
2. Add it to `CONTINUOUS_SIGNALS` in `analytics/signal_analysis.py` (1 line)
3. After 48h accumulation, run `signal_analysis.py --days 3` to check Pearson r vs YES and monotonicity

**Second priority:** Wait for clean DOWN shadow data (≥2026-05-10 22:00 UTC) and re-run gate_relaxation.py on DOWN-only cohort to validate ob_imb=0.20 threshold with correct labels.

**Negative result of note:** The dead drift hypothesis (Investigation 3) is weakened by available 30s data. snap30 [0,10.5%) YES=90.2% > [10.5,80%) YES=84% is the opposite of the drift-toxicity prior. Until 5s-specific data is available, treat this investigation as low priority.

---

## Infrastructure Alert — SSH (31 consecutive sessions)

**Status:** TCP port 22 egress blocked at sandbox network boundary (openssh-client now installed; confirmed timeout not binary-absence).
**VPS IS running** — 34 VPS-authored commits in 46 hours. Shadow pipeline operational.

**One-time manual sync to unblock future scouts (30s on VPS):**
```bash
cd /root/Klaus && tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
git add logs/live_trades_recent.jsonl logs/bankroll.json && \
git commit -m "manual log sync $(date -u)" && git push origin claude/find-lag-parameter-rFQ0N
```

**Better: add `velocity_5s_pct` to shadow pipeline so cross-exchange lag analysis can proceed without trades.jsonl access.**
