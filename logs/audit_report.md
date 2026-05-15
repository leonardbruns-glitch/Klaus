# Quantitative Audit — 2026-05-15 00:05 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (58th consecutive session)**

| Method | Result |
|---|---|
| SSH to root@85.137.174.86:22 | `ssh` binary not found in environment |
| /tmp/trades.jsonl | 1 line = shell error string; 0 real trade lines |
| /tmp/post_exit.jsonl | 0 lines — not retrieved |
| logs/trades.jsonl (git-tracked) | Not present — VPS has not synced to repo |
| logs/bankroll.json (local snapshot) | **UNCHANGED since 2026-05-08 19:26 UTC (148.6h stale)** |

**Bankroll snapshot** (ts=1778268412 / 2026-05-08 19:26 UTC — 6.2 days stale):
- capital: $84.61
- total_trades: 2,605
- total_pnl: +$87.87
- consecutive_wins: 0

> Bankroll snapshot **UNCHANGED** for 58 consecutive audit sessions. Actual live capital unknown.

---

## AUDIT SCOPE CONFLICT — BOND Strategy Disabled (58th session)

**This audit framework targets `signal_source=='BOND'` trades exclusively.**

| Strategy | Status | Since |
|---|---|---|
| BOND_ENABLED | **False** | 2026-05-10 |
| SNIPER_ENABLED | **False** | 2026-04-16 |
| MOM_ENABLED | **False** | 2026-04-22 |
| DISCOVER (active) | **True** | 2026-05-10 |
| LDA (active, newest) | **True** | 2026-05-12 21:41 UTC |

BOND audit filter (`signal_source=='BOND'`, `0.80<=entry_price<=0.88`) would return 0 trades for any window after 2026-05-10. This framework is **structurally inapplicable** to the current live state.

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A

6h window: 2026-05-14 18:05 UTC → 2026-05-15 00:05 UTC

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
INSUFFICIENT_DATA — 58th consecutive session with no VPS connectivity.
AUDIT_SCOPE_CONFLICT — BOND disabled 2026-05-10; audit framework targets non-active strategy.
NO_CHANGE — no BOND parameter changes without data.

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.78,
  "max_ask": 0.93,
  "min_imbalance": 0.0,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": [],
  "change": false,
  "reason": "INSUFFICIENT_DATA — VPS unreachable (58th consecutive session). BOND disabled 2026-05-10; audit filter inapplicable. Active strategies: LDA + DISCOVER. No parameter changes without data."
}
```

---

## Active Strategy Parameters (ground truth from codebase — 2026-05-15 00:05 UTC)

### LDA — Late Direction Arb (strategy/late_direction_arb.py)

| Parameter | Value | Notes |
|---|---|---|
| ASK_FLOOR | 0.60 | expanded from 0.70 |
| ASK_CEIL | 0.98 | |
| BID_MIN | 0.50 | |
| REM_MIN_S | 8.0s | |
| B3 [180,300s) | **FULLY BLOCKED — all assets all hours** | user instruction 2026-05-14 |
| BLOCKED_HOURS_UTC | {0, 1} | H00 WR=66% n=106; H01 WR=88.6% n=79 (CI below baseline) |
| _ALL_BLOCKED_LATE | {3, 5, 6, 7, 12, 15} | [120,300s) bucket — EV negative all assets |
| _ALL_BLOCKED_LATE_B1 | {4, 5, 7, 12, 15} | [60,120s) bucket — EV negative all assets |
| _SOL_BLOCKED_B1 | {1, 10, 13, 14, 22} | SOL [60,120s) bad hours |
| _ETH_BLOCKED_B1 | {1, 2} | ETH [60,120s) bad hours |
| _BTC_BLOCKED_B1 | {13} | BTC [60,120s) bad hour |
| _SOL_BLOCKED_LATE | {10, 13, 16, 20, 21, 22} | SOL [120,300s) |
| _ETH_BLOCKED_LATE | {0, 8, 9, 13, 16, 17, 21, 22} | ETH [120,300s) |
| _BTC_BLOCKED_LATE | {17} | BTC B2+B3 bad |
| _BTC_BLOCKED_B3 | {1, 4, 18, 21, 23} | BTC B3-only bad hours |
| _SOL_BLOCKED_ALL | {7, 9} | SOL all buckets |

### Changes Since Last Audit (2026-05-14 18:09 UTC — 9 commits)

| Commit | Change |
|---|---|
| 4a750a6 | lda: block B3 [180,300s) all assets all hours — user instruction |
| b554350 | lda: block BTC B3 H21 — shadow n=15, thin |
| 040251c | lda: cumulative bucket Kelly targets — B3=50% B2=75% B1=100% of full fraction |
| 25d0d11 | lda: re-enable B3 ETH+BTC with new hour blocks; add SOL B1/B2 blocks |
| d02d7c8 | lda: block H05+H07 all assets B1+B2 — EV negative |
| 3076e41 | lda: block B3 [180,300s) for all assets — user instruction |
| 12a700a | lda: per-asset window Kelly cap |
| 9774288 | lda: BNC-tiered half-Kelly replaces flat two-tier stakes |
| 6eabbac | lda: ETH B1/B3 + BTC B1/B2/B3 hour gates |

### BOND Parameters (audit reference — BOND disabled since 2026-05-10)

| Parameter | Code Location | Current Value | Audit Prompt Assumed | Delta |
|---|---|---|---|---|
| min_ask (_ask_floor) | main.py:2521 | **0.78** | 0.80 | −0.02 |
| max_ask (_ask_max) | main.py:2519 | **0.93** | 0.88 | +0.05 |
| min_imbalance | main.py:2578 | **0.0 (gate inactive)** | 0.20 | — |
| _BLOCKED_HOURS | config.py | **[] (bond_blocked_hours_utc=[])** | [] | none |
| stop_loss | main.py | **−15%** | −15% | none |
| BOND_ENABLED | window_sniper.py | **False** | (assumed True) | — |

---

## Infrastructure Alert — Critical (58 consecutive sessions)

**Root cause**: `ssh` binary unavailable in audit agent environment; cannot reach VPS at 85.137.174.86.

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

**Note on audit framework**: With BOND disabled and LDA+DISCOVER active, a new audit framework targeting `signal_source=='LDA'` is needed. Key LDA fields: `entry_price`, `exit_price`, `exit_reason`, `hold_s`, `net_pnl`, `kline_pnl`, `asset`, `bnc_move_pct`, `bnc_decay_skip`, `rem_bucket`.
