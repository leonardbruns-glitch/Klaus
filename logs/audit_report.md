# Quantitative Audit — 2026-05-15 18:14 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (61st consecutive session)**

| Method | Result |
|---|---|
| SSH to root@85.137.174.86:22 | Connection timeout — TCP port 22 egress blocked from this environment |
| /tmp/trades.jsonl | 0 real trade lines — SSH failed before transfer |
| /tmp/post_exit.jsonl | 0 lines — not retrieved |
| logs/trades.jsonl (git-tracked) | Not present — VPS has not synced to repo |
| logs/bankroll.json (local snapshot) | **UNCHANGED since 2026-05-08 19:26 UTC (166.8h stale)** |

**Bankroll snapshot** (ts=1778268412 / 2026-05-08 19:26 UTC — 6.9 days stale):
- capital: $84.61
- total_trades: 2,605
- total_pnl: +$87.87
- consecutive_wins: 0

> Bankroll snapshot **UNCHANGED** for 61 consecutive audit sessions. Actual live capital unknown.

---

## AUDIT SCOPE CONFLICT — BOND Strategy Disabled (61st session)

**This audit framework targets `signal_source=='BOND'` trades exclusively.**

| Strategy | Status | Since |
|---|---|---|
| BOND_ENABLED | **False** | 2026-05-10 |
| SNIPER_ENABLED | **False** | 2026-04-16 |
| MOM_ENABLED | **False** | 2026-04-22 |
| DISCOVER (active) | **True** | 2026-05-10 |
| LDA (active, newest) | **True** | 2026-05-12 21:41 UTC |

BOND audit filter (`signal_source=='BOND'`, `0.80<=entry_price<=0.88`) returns 0 trades for any window after 2026-05-10. This framework is **structurally inapplicable** to the current live state.

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A

6h window: 2026-05-15 12:14 UTC → 2026-05-15 18:14 UTC

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
INSUFFICIENT_DATA — 61st consecutive session with no VPS connectivity.
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
  "reason": "INSUFFICIENT_DATA — VPS unreachable (61st consecutive session). BOND disabled 2026-05-10; audit filter inapplicable. Active strategies: LDA + DISCOVER. No parameter changes without data."
}
```

---

## Active Strategy Parameters (ground truth from codebase — 2026-05-15 18:14 UTC)

### LDA — Late Direction Arb (strategy/late_direction_arb.py)
Latest commits: B2 ask ceiling raised 0.80→0.85; flat $5 stake; H03+H23 globally blocked.

| Parameter | Value | Notes |
|---|---|---|
| ASK_FLOOR | 0.60 | |
| ASK_CEIL | 0.98 | 0.994→0.98 (entries >0.98 near-zero margin) |
| BID_MIN | 0.50 | both tokens wrong side if bid<0.50 |
| REM_MIN_S | 8.0s | |
| BLOCKED_HOURS_UTC | {0, 1, 2, 3, 19, 23} | H00/H01 shadow May8-12; H02 n=18 WR=22%; H03 B2 gap; H19 n=18 WR=72% net=-$50; H23 n=7 WR=29% -$186 |
| _ALL_BLOCKED_LATE [120-300s) | {3, 5, 6, 7, 12, 15} | asset-agnostic |
| _ALL_BLOCKED_LATE_B1 [60-120s) | {4, 5, 12, 15} | H07 unblocked 2026-05-15 |
| _ETH_BLOCKED_LATE | {0, 8, 9, 13, 16, 21, 22} | |
| _BTC_BLOCKED_LATE [120-300s) | {8} | H17 unblocked 2026-05-15 (n=7 WR=86% net=+$17) |
| _BTC_BLOCKED_B3 [180-300s) | {1, 4, 18, 21, 23} | |
| B3 [180-300s) | **re-enabled 2026-05-15** | ask range 0.70-<0.80 (dead zones apply) |
| Kill switches | **disabled** | all ruin/drawdown halts off per user instruction |

### BOND Parameters (audit reference — BOND disabled since 2026-05-10)

| Parameter | Code Location | Current Value | Audit Prompt Assumed | Delta |
|---|---|---|---|---|
| min_ask (_ask_floor) | main.py:2521 | **0.78** | 0.80 | −0.02 |
| max_ask (_ask_max) | main.py:2519 | **0.93** | 0.88 | +0.05 |
| min_imbalance | main.py:2578 | **0.0 (gate inactive)** | 0.20 | — |
| bond_blocked_hours_utc | config.py:151 | **[]** | [] | none |
| stop_loss | main.py | **−15%** | −15% | none |
| BOND_ENABLED | window_sniper.py:133 | **False** | (assumed True) | — |

---

## Infrastructure Alert — Critical (61 consecutive sessions)

**Root cause**: TCP port 22 egress is blocked from the cloud audit environment. SSH client installs but cannot connect. Cannot reach VPS at 85.137.174.86.

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

**Note on audit framework conflict**: BOND has been disabled for 5 days; LDA+DISCOVER are live. A new audit framework targeting `signal_source=='LDA'` is needed. Key LDA fields: `entry_price`, `exit_price`, `exit_reason`, `hold_s`, `net_pnl`, `kline_pnl`, `asset`, `bnc_move_pct`, `bnc_decay_skip`, `rem_bucket`.
