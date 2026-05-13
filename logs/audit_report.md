# Quantitative Audit — 2026-05-13 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (52nd consecutive session)**

| Method | Result |
|---|---|
| SSH to root@85.137.174.86:22 | SSH binary absent in sandbox; TCP port 22 egress blocked at network boundary |
| /tmp/trades.jsonl | 0 real lines — SSH pull failed (file contains only error string) |
| /tmp/post_exit.jsonl | 0 lines — SSH pull failed |
| logs/trades.jsonl (git-tracked) | not present |
| logs/live_trades_recent.jsonl (git-tracked) | not present — VPS has not run manual sync |
| logs/bankroll.json (local snapshot) | readable — UNCHANGED since 2026-05-08 19:26 UTC (5 days stale) |

**Bankroll snapshot** (ts=1778268412 / 2026-05-08 19:26 UTC — 5 days stale):
- capital: $84.61
- total_trades: 2,605
- total_pnl: +$87.87
- consecutive_wins: 0
- daily_start_capital: $15.95 (stale, pre-oracle_sweep)

> Bankroll snapshot **UNCHANGED** for 52 consecutive audit sessions. Actual live capital unknown
> and may be materially lower after oracle_sweep ($487 positions, 2026-05-11 18:50 UTC).
> No new trade-level records are accessible from this sandbox.

---

## AUDIT SCOPE CONFLICT — BOND Strategy Disabled (52nd session)

**CRITICAL: This audit framework targets `signal_source=='BOND'` trades exclusively.**

| Strategy | Status | Since |
|---|---|---|
| BOND_ENABLED | **False** | 2026-05-10 |
| SNIPER_ENABLED | **False** | 2026-04-16 |
| MOM_ENABLED | **False** | 2026-04-22 |
| DISCOVER (active) | **True** | 2026-05-10 |
| LDA (active, newest) | **True** | 2026-05-12 21:41 UTC |

Even if VPS SSH were restored, the BOND audit filter (`signal_source=='BOND'`, `0.80<=entry_price<=0.88`) would return 0 trades for any window after 2026-05-10. This audit framework is **structurally inapplicable** to the current live state.

---

## Active Strategy Parameters (ground truth from codebase)

### LDA — Late Direction Arb (newest, deployed 2026-05-12 21:41 UTC)

| Parameter | Value | Location |
|---|---|---|
| ASK_FLOOR | 0.70 | late_direction_arb.py:25 |
| ASK_CEIL | 0.98 (reverted from 0.93 — 62% n-reduction too steep) | late_direction_arb.py:26 |
| BID_MIN | 0.50 | late_direction_arb.py:27 |
| REM_MIN_S | 8.0s | late_direction_arb.py:28 |
| REM_MAX_S | 90.0s | late_direction_arb.py:29 |
| BNC_MOVE_MIN | 0.07% | late_direction_arb.py:30 |
| STAKE_USD | $5.00 | late_direction_arb.py:31 |
| BLOCKED_HOURS_UTC | {1} | late_direction_arb.py:32 |

Signal: Binance 5m-return direction (spot vs open_5m). Shadow accuracy baseline: 96.6% (n=85 windows). LDA exits via bid≥0.999 PROFIT_TARGET or BOND_DEADLINE at T-3s.

### DISCOVER — ETH-only DOWN (active)

| Parameter | Value | Location |
|---|---|---|
| Direction | DOWN only | discover_strategy.py:172 |
| Assets | ETH only (BTC blocked) | discover_strategy.py:150 |
| ask range | 0.10 – 0.40 | discover_strategy.py:174 |
| rem window | 60 – 180s | discover_strategy.py:138 |
| arb_sum gate | < 0.99 | discover_strategy.py:193 |
| PT exit | bid ≥ 0.99 | main.py:1318 |
| Stake | $3 target | discover_strategy.py:58 |

### BOND Parameters (for audit reference — BOND disabled)

| Parameter | Code Location | Current Value | Audit Prompt Assumed | Delta |
|---|---|---|---|---|
| min_ask (_ask_floor) | main.py:2488 | **0.78** | 0.80 | −0.02 |
| max_ask (_ask_max) | main.py:2486 | **0.93** | 0.88 | +0.05 |
| min_imbalance | main.py | **0.0 (gate inactive)** | 0.20 | — |
| blocked_hours (BOND) | N/A (no _BLOCKED_HOURS in main.py) | **[]** | [] | none |
| stop_loss | main.py | **−15%** (ask×0.85) | −15% | none |
| BOND_ENABLED | window_sniper.py:133 | **False** | (assumed True) | — |

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A

0.80-0.84: n=0 WR=N/A E=N/A
0.84-0.88: n=0 WR=N/A E=N/A

---

## Loss Signatures
None in window — no data accessible.

---

## OB Imbalance
No data accessible.

---

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.80-0.88 BOND filter)
No data accessible. n=0 for all hours. No block/unblock decisions possible.

| H | n | WR | PF | status |
|---|---|---|---|---|
| all | 0 | — | — | collecting data (VPS unreachable + BOND disabled) |

---

## Flags
INSUFFICIENT_DATA — 52nd consecutive session with no VPS connectivity.
AUDIT_SCOPE_CONFLICT — BOND disabled 2026-05-10; audit framework targets non-active strategy.
NO_CHANGE — No parameter changes without data.

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.78,
  "max_ask": 0.93,
  "min_imbalance": 0.0,
  "stake": 3.00,
  "stop_loss": -0.15,
  "blocked_hours": [],
  "change": false,
  "reason": "INSUFFICIENT_DATA — VPS unreachable (52nd consecutive session). BOND disabled 2026-05-10; audit filter inapplicable to current live state. Active strategies: LDA (ETH/BTC/SOL, T-8 to T-90s, ask 0.70-0.98, shadow acc 96.6%) and DISCOVER (ETH-only DOWN). No parameter changes without data."
}
```

---

## Recent LDA Development (from git log, last 5 commits)

| Commit | Change |
|---|---|
| 310d1bd | lda: revert ceil to 0.98 — 62% n reduction too steep |
| e833c76 | lda: ceil 0.98→0.93, block H01 |
| 019a5d1 | lda: per-asset per-window bnc gates (shadow n=1631) |
| 4a2667d | analytics: LDA asset x window x bnc breakdown |
| 683a31e | analytics: LDA breakdown by window size and asset |

LDA is actively being tuned from shadow data (n=1,631 shadow windows analysed). Shadow baseline: 96.6% direction accuracy, PF≈6.3 (n=85). Strategy is in live validation at $5/trade stake.

---

## Infrastructure Alert — Critical (52 consecutive sessions)

**Root cause**: SSH binary absent from sandbox; TCP port 22 egress blocked at network boundary.

**Required action — run ONE of these on the VPS:**

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

**Note:** With BOND disabled and LDA+DISCOVER active, a new audit framework is needed. Key LDA fields:
`signal_source=='LDA'`, `entry_price`, `exit_price`, `exit_reason`, `hold_s`, `net_pnl`, `asset`,
`bnc_move_pct`. DISCOVER fields: `signal_source=='DISCOVER'`, `arb_sum_yes_no`, `peer_age_ms`.
