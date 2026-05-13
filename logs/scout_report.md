# Alpha Scout Report — 2026-05-13 UTC

**Method:** Codebase audit — VPS SSH unreachable (51st consecutive scout session)
**Connectivity:** SSH binary absent in sandbox; TCP port 22 egress blocked at network boundary. `trades.jsonl` and `post_exit.jsonl` inaccessible.
**Data sources used:** git log HEAD=04e03cb; full reads of `state_log.md`, `logs/bankroll.json`, `strategy/late_direction_arb.py`, `analytics/lda_live_performance.py`, `analytics/lda_asset_window_bnc.py`, prior scout report.
**Bankroll snapshot:** $84.61 (ts=2026-05-08 19:26 UTC, 5 days stale). Current capital unknown pending VPS sync.

---

## STRATEGY CONTEXT MISMATCH — READ FIRST

The scout mandate targets BOND/TERMINAL strategy (`signal_source=='BOND'`, ask 0.80–0.88, T-25 to T-90s). **BOND has been disabled since 2026-05-10 21:25 UTC.** The active strategy is **LDA (Late Direction Arb)**, deployed 2026-05-12 21:41 UTC. All four mandated investigations use BOND-specific fields (`term_tok_tick_count_5s`, `term_token_delta_5s`) that LDA does not log. `pre_entry_momentum_pct` is logged by LDA but means something structurally different — it IS the signal, not a predictor of the signal.

All four mandated investigations are INCONCLUSIVE. Pivot sections below address LDA-native equivalents.

---

## Investigation 1: Cross-Exchange Lead-Lag

HYPOTHESIS: Positive Binance spot velocity in 5s before entry (`pre_entry_momentum_pct`) predicts YES resolution.
RESULT:

| Metric | Value | Source |
|---|---|---|
| LDA live direction WR | 93% (53/57 kline-resolved) | state_log 2026-05-13 |
| n_trades available | 0 locally | VPS SSH blocked |
| BOND field `pre_entry_momentum_pct` | Logged by LDA as `bnc_move_pct` | late_direction_arb.py:252 |

MATH: For BOND, `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago`. For LDA, `bnc_move_pct = (spot - open_5m) / open_5m × 100` — 5-minute candle return, not 5-second velocity.
CONCLUSION: **INCONCLUSIVE**
FAILURE_MET: Yes. BOND disabled n=0. LDA does log `pre_entry_momentum_pct` (mapped to `bnc_move_pct`) but the field semantics are incompatible: it's the primary signal direction gate, not a momentum overlay. The relevant LDA question is whether the **magnitude** of `bnc_move_pct` predicts direction WR — but data is on VPS only.

**LDA-native equivalent:** Does |bnc_move_pct| > 0.15% vs 0.07–0.15% produce higher direction WR? State log records n=7 kline losers with MAE_30s as most discriminating factor — magnitude of BNC signal not yet tested. Add `bnc_abs_pct` to next VPS analysis script once n_losers ≥ 20.

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
FAILURE_MET: Yes. `term_tok_tick_count_5s` is BOND-specific; LDA does not log or require it. LDA's vol_regime gate (`vol_regime != 'normal'` blocks entry) is the structural equivalent — it proxies token market activity via price volatility regime. Shadow evidence: vol_regime=normal WR=71% vs volatile=54% vs extreme=43% (n=1000+, commit 3b46962). This is implemented; investigation superseded.

---

## Investigation 3: Dead Drift Signature

HYPOTHESIS: Dead market entries (`|term_token_delta_5s| < 0.005`) underperform active entries.
RESULT:

| Group | n | WR |
|---|---|---|
| Dead drift (|delta_5s| < 0.005) | 0 | N/A |
| Active (|delta_5s| ≥ 0.005) | 0 | N/A |

CONCLUSION: **INCONCLUSIVE**
FAILURE_MET: Yes. BOND disabled n=0. `term_token_delta_5s` is BOND-specific. LDA's analogue is the BNC floor gate (|bnc_move_pct| < BNC_FLOOR → skip). BNC_FLOOR is adaptive by ask zone (0.05–0.10%) and filters flat-Binance windows before any Polymarket token check. Dead-drift detection is handled at the signal source (Binance kline), not Polymarket token level. No equivalent gap to investigate.

---

## Investigation 4: Asset-Specific Edge

HYPOTHESIS: One asset consistently outperforms others in the last 48h.
RESULT:

| Asset | n_live (48h) | Direction WR | BOND_RNO_premature | Notes |
|---|---|---|---|---|
| BTC | Unknown (VPS) | Unknown | 0/8 (0%) | Cleanest exit timing |
| ETH | Unknown (VPS) | Unknown | Unknown | Active; DISCOVER S2 co-running |
| SOL | Unknown (VPS) | Unknown | 13/25 (52%) | Worst premature exit rate |

Source: state_log 2026-05-13 (BOND_RESOLVED_NO threshold analysis, n=57 total kline-resolved trades).

CONCLUSION: **INCONCLUSIVE** (n per asset unknown; full breakdown on VPS only)
FAILURE_MET: Yes — n < 20 verified per asset within 48h window (exact split unavailable).

**Observable finding (no reweighting warranted yet):** SOL has a systematic exit timing problem — 52% of SOL kline-wins were booked as losses via premature BOND_RESOLVED_NO exit (bid drops to 0 post-window before oracle settles at ~35s). Fix deployed: `_rno_threshold` raised 60s→180s (main.py:1454). BTC unaffected (0/8). This is an exit quality issue, not a signal quality issue; SOL direction WR is presumably similar to BTC/ETH but masked. Do not stake-weight against SOL until post-fix data confirms the gap is real.

---

## LDA-Native Investigations (Active Research Agenda)

These replace the obsolete BOND investigations for the current strategy epoch.

### Investigation A: BNC Magnitude as Conviction Gate (Priority 1)

HYPOTHESIS: Higher |bnc_move_pct| → higher direction WR. Weak Binance moves (0.07–0.10%) produce more wrong-direction LDA entries than strong moves (>0.15%).
MATH: `bnc_abs_pct = abs(bnc_move_pct)`. Buckets: [0.07, 0.10%), [0.10, 0.15%), [0.15%+].
VARIABLES: `pre_entry_momentum_pct` in `trades.jsonl` for `bond_entry_class == 'LDA'`.
CURRENT DATA: n=7 kline losers in live LDA (state_log 2026-05-13). MAE_30s most discriminating (23.5% losers vs 5.9% winners) but n too small. Recheck at n_losers ≥ 20.
FAILURE_CRITERIA: WR spread < 5pp across magnitude buckets, or n < 20 per bucket.
PROPOSED_GATE: `abs(bnc_move_pct) >= X%` floor in `strategy/late_direction_arb.py` `schedule_if_ready()`.

VPS analysis snippet:
```python
import json
from collections import defaultdict

trades = [json.loads(l) for l in open('/root/Klaus/logs/trades.jsonl') if l.strip()]
lda = [t for t in trades if t.get('bond_entry_class') == 'LDA' and t.get('is_live') and t.get('entered_correctly') is not None]

buckets = defaultdict(lambda: {'n': 0, 'wins': 0})
for t in lda:
    bnc_abs = abs(t.get('pre_entry_momentum_pct', 0.0) or 0.0)
    b = '<0.10%' if bnc_abs < 0.10 else ('<0.15%' if bnc_abs < 0.15 else '0.15%+')
    buckets[b]['n'] += 1
    if t['entered_correctly']:
        buckets[b]['wins'] += 1

for b, v in sorted(buckets.items()):
    wr = v['wins']/v['n'] if v['n'] else 0
    print(f"{b}: n={v['n']} WR={wr:.1%}")
```

---

### Investigation B: MAE_30s as Early-Exit Predictor (Priority 2)

HYPOTHESIS: Token price drop > X% within 30s of LDA entry predicts kline loss reliably enough to cut early.
MATH: `mae_30s_pct = (min_bid_30s - entry_price) / entry_price × 100`. Winners avg -5.9%, losers avg -23.5% (state_log 2026-05-13, n=7 losers — recheck at n≥20).
VARIABLES: `traj_snaps` or `hold_path` shadow records joinable to `trades.jsonl` via `(token_id, ts_open)`.
CURRENT DATA: n=7 losers — below threshold for shipping. Do not gate until n_losers ≥ 20.
FAILURE_CRITERIA: LDA_LOSER_CUT precision < 70% at n ≥ 20 losers (same bar used for BOND_LOSER_CUT).
PROPOSED_GATE: `mae_30s_pct < -15%` → `LDA_LOSER_CUT` early exit at T+30s (mirroring BOND_LOSER_CUT structure at main.py:877).

---

### Investigation C: Ask Zone EV by Rem Bucket (Priority 3) — Shadow Data Available

HYPOTHESIS: Ask<0.70 entries at rem>90s (newly unlocked cells) have positive EV but lower WR than ask≥0.70.
CURRENT DATA: Grid scan n=1000+ shadow observations. Dead2 removed (EV+$0.81 n=27 at [0.80,0.90)×[90,120), EV+$0.42 n=80 at [120,180)). New cells [0.60,0.80)×[90,300] also positive (commit 3b46962).
CONCERN: At ask=0.60, bid≥0.99 PT requires 65% token price gain. Transaction cost at entry ~1.5% (fee). EV positive in shadow but hasn't run live. Check first 20 live trades in new ask zone before raising stake.
VPS SCRIPT: `python3 analytics/lda_asset_window_bnc.py` (already written, reads shadow logs).

---

### Investigation D: SOL Post-Fix Performance (Priority 4)

HYPOTHESIS: SOL kline direction WR is ≥ ETH after BOND_RESOLVED_NO threshold fix (60s→180s).
BASIS: Pre-fix, 52% of SOL kline-wins were premature exits. Fix deployed same session (state_log 2026-05-13). SOL was never unwhitelisted.
VERIFICATION: Run `lda_live_performance.py` on VPS after collecting 20+ post-fix SOL trades. If SOL WR matches ETH/BTC, stake weighting is symmetric. If still underperforming at n≥20, investigate market structure (SOL oracle settlement timing differs from BTC — SOL Chainlink heartbeat 10s vs BTC 30s?).
FAILURE_CRITERIA: n < 20 SOL trades post-fix.

---

## Priority Signal for Next Implementation

**No actionable signals this cycle — continue data collection.**

Rationale:
- All four mandated BOND investigations remain at n=0 (BOND disabled, architecture changed).
- LDA Investigation A (BNC magnitude gate): n_losers=7 — below n=20 floor. Do not ship.
- LDA Investigation B (MAE_30s early cut): same constraint, n_losers=7.
- LDA Investigation C (ask zone EV): shadow evidence positive, but live n in new cells = 0 yet. Wait 20 live entries in ask<0.70 zone before raising stake or adding limits.
- LDA Investigation D (SOL fix): fix deployed today; no post-fix data yet.

**Highest priority this cycle is operational:**
1. **Verify current bankroll** — `bankroll.json` is 5 days stale; oracle_sweep damage ($487 positions, unknown redemption) may have partially recovered via Redeemer, but actual figure unknown.
2. **Sync logs** — Run on VPS:
   ```bash
   cd /root/Klaus
   tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
   git add logs/live_trades_recent.jsonl logs/bankroll.json
   git commit -m "log sync $(date -u +%Y-%m-%dT%H:%M)"
   git push origin claude/find-lag-parameter-rFQ0N
   ```
3. **Monitor LDA loser accumulation** — At n_losers ≥ 20, run Investigation A and B immediately. Expected timeline at current trade rate: ~2–4 days.

---

## Infrastructure Alert — SSH (51 consecutive sessions)

Root cause unchanged: TCP port 22 egress blocked at sandbox network boundary.
**Manual VPS sync is the only path to actionable analysis. Every cycle without it widens the gap between coded strategy and observable outcomes.**

Current strategy velocity (LDA active since 2026-05-12 21:41, ~36 hours ago): at 93% direction WR and $5/trade, expected gross PnL ≈ +$X — exact figure unknown without live data.
