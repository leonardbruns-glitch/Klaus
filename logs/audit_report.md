# Quantitative Audit — 2026-05-14 00:15 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (56th consecutive session)**

| Method | Result |
|---|---|
| SSH to root@85.137.174.86:22 | SSH binary absent in sandbox; TCP port 22 blocked at network boundary |
| /tmp/trades.jsonl | 0 real lines — SSH pull failed |
| /tmp/post_exit.jsonl | 0 lines — not retrieved |
| logs/trades.jsonl (git-tracked) | Not present — VPS has not synced to repo |
| logs/bankroll.json (local snapshot) | Readable — **UNCHANGED since 2026-05-08 19:26 UTC (124.8h stale)** |

**Bankroll snapshot** (ts=1778268412 / 2026-05-08 19:26 UTC — 5.2 days stale):
- capital: $84.61
- total_trades: 2,605
- total_pnl: +$87.87
- consecutive_wins: 0

> Bankroll snapshot **UNCHANGED** for 56 consecutive audit sessions. Actual live capital unknown.
> No new trade-level records accessible from this sandbox.

---

## AUDIT SCOPE CONFLICT — BOND Strategy Disabled (56th session)

**CRITICAL: This audit framework targets `signal_source=='BOND'` trades exclusively.**

| Strategy | Status | Since |
|---|---|---|
| BOND_ENABLED | **False** | 2026-05-10 (window_sniper.py:133) |
| SNIPER_ENABLED | **False** | 2026-04-16 |
| MOM_ENABLED | **False** | 2026-04-22 |
| DISCOVER (active) | **True** | 2026-05-10 |
| LDA (active, newest) | **True** | 2026-05-12 21:41 UTC |

Even if VPS SSH were restored, the BOND audit filter (`signal_source=='BOND'`, `0.80<=entry_price<=0.88`) would return 0 trades for any window after 2026-05-10. This audit framework is **structurally inapplicable** to the current live state.

---

## Active Strategy Parameters (ground truth from codebase — as of 2026-05-14 00:15 UTC)

### LDA — Late Direction Arb
Source: `strategy/late_direction_arb.py`

| Parameter | Value | Notes |
|---|---|---|
| ASK_FLOOR | 0.60 | expanded from 0.70 (2026-05-13) |
| ASK_CEIL | 0.98 | line 26 |
| BID_MIN | 0.50 | line 27 |
| REM_MIN_S | 8.0s | line 28 |
| REM_MAX_S | 300.0s | extended; ask-conditional dead zones enforce tighter per-bucket |
| STAKE_USD | $5.00 | line 31 |
| STAKE_USD_REDUCED | $2.00 | trending-weak hour×bucket cells |
| BLOCKED_HOURS_UTC | {0, 1} | H00: WR=66% n=106; H01: WR=88.6% wrong=9 n=79 |
| _ALL_BLOCKED_LATE | {13} | WR=70% all-asset n=87, volatile ([120,300s) zone) |
| _SOL_BLOCKED_LATE | {6, 22} | WR=63%/57%, CI<77.3% baseline ([120,300s) zone) |
| _SOL_WATCH_LATE | {3, 13} | WR=68%/66% — $2 stake |
| _ETH_WATCH_LATE | {8, 9, 22} | WR=63%/69%/65% — $2 stake |
| BNC_DECAY_THRESHOLD | −0.03% | freshness re-check added 2026-05-13 20:52 UTC (fc5a87d) |

Signal: Binance 5m-return direction. Shadow accuracy baseline: 96.6% (n=85 windows).

### Changes Since Last Audit (2026-05-13 18:10 UTC)

**commit fc5a87d — BNC-decay freshness re-check**
- Added 500ms async re-fetch at order time; skip if signed bnc_ret < −0.03%
- Shadow validation (n=2,643 signal-windows, May 9-13):
  - Blocked cohort: WR=36% (113 losers, 64 winners killed) — 1.77:1 loser-to-winner kill ratio
  - Kept cohort WR lifted: **81.1% → 84.3%** (−17% relative loss-rate)
  - Holds in every cell: 3 assets, 2 directions, 4 ask buckets, 3 rem buckets, 5 days
- No parameters added; gate operates at order-send time inside `_fire_inner`

**commit 04e288a — kline_pnl ground-truth field**
- At resolution time, patch `kline_pnl` into every trade record:
  - WIN: `(1 − entry_price) × shares − fee`
  - LOSE: `−stake − fee`
- Analytical field only; `net_pnl` unchanged
- `lda_live_performance.py` updated to report kline_pnl vs net_pnl with exit drag
- 2,327 existing trades backfilled

### BOND Parameters (audit reference — BOND disabled since 2026-05-10)

| Parameter | Code Location | Current Value | Audit Prompt Assumed | Delta |
|---|---|---|---|---|
| min_ask (_ask_floor) | main.py:2520 | **0.78** | 0.80 | −0.02 |
| max_ask (_ask_max) | main.py:2518 | **0.93** | 0.88 | +0.05 |
| min_imbalance | main.py | **0.0 (gate inactive)** | 0.20 | — |
| _BLOCKED_HOURS | N/A | **[] (bond_blocked_hours_utc=[])** | [] | none |
| stop_loss | main.py | **−15%** | −15% | none |
| BOND_ENABLED | window_sniper.py:133 | **False** | (assumed True) | — |

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A

6h window: 2026-05-13 18:15 UTC → 2026-05-14 00:15 UTC

0.80-0.84: n=0 WR=N/A E=N/A
0.84-0.88: n=0 WR=N/A E=N/A

## Loss Signatures
None in window — no data accessible.

## OB Imbalance
No data accessible. Buckets all empty.

## Slippage
avg_slippage_entry=N/A

## Hour Analysis (all-time, 0.80-0.88 BOND filter)
No data accessible. n=0 for all hours. No block/unblock decisions possible.

| H | n | WR | PF | status |
|---|---|---|---|---|
| all | 0 | — | — | collecting data (VPS unreachable + BOND disabled) |

---

## Flags
INSUFFICIENT_DATA — 56th consecutive session with no VPS connectivity.
AUDIT_SCOPE_CONFLICT — BOND disabled 2026-05-10; audit framework targets non-active strategy.
NO_CHANGE — no BOND parameter changes without data.

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.88,
  "min_imbalance": 0.20,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": [],
  "change": false,
  "reason": "INSUFFICIENT_DATA — VPS unreachable (56th consecutive session). BOND disabled 2026-05-10; audit filter inapplicable. Active strategies: LDA + DISCOVER. No parameter changes without data."
}
```

---

## LDA Quality Signal (codebase-only, no live data)

The two commits since the last audit (04e288a, fc5a87d) represent qualitative improvements:
- BNC-decay re-check lifts kept-cohort WR by +3.2pp on n=2,643 shadow observations — statistically material (improvement is consistent across all asset/direction/ask/rem cells).
- kline_pnl field is a pure analytical improvement; no effect on live behavior.

No live performance regression observable from codebase alone. The BNC-decay change is additive (new gate, doesn't remove existing edge) and well-validated.

---

## Infrastructure Alert — Critical (56 consecutive sessions)

**Required action — run ONE of these on the VPS to unblock future audits:**

**Option A: Manual one-time sync (30 seconds)**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Option B: Deploy cron sync (every 30 minutes, permanent fix)**
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

**Note on audit framework**: With BOND disabled and LDA+DISCOVER active, a new audit framework targeting `signal_source=='LDA'` and `signal_source=='DISCOVER'` is needed. Key LDA fields: `entry_price`, `exit_price`, `exit_reason`, `hold_s`, `net_pnl`, `kline_pnl`, `asset`, `bnc_move_pct`, `bnc_decay_skip`.
