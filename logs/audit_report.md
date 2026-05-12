# Quantitative Audit — 2026-05-12 18:12 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (51st consecutive session)**

| Method | Result |
|---|---|
| SSH to root@85.137.174.86:22 | TCP port 22 egress blocked at network boundary |
| /tmp/trades.jsonl | 0 lines — SSH pull failed |
| /tmp/post_exit.jsonl | 0 lines — SSH pull failed |
| logs/trades.jsonl (git-tracked) | not present |
| logs/bankroll.json (local snapshot) | readable — UNCHANGED since 2026-05-08 19:26 UTC |

**Bankroll snapshot** (ts=1778268412 / 2026-05-08 19:26 UTC — 4 days stale):
- capital: $84.61
- total_trades: 2,605
- total_pnl: +$87.87
- consecutive_wins: 0
- daily_start_capital: $15.95 (stale)

> Bankroll snapshot **UNCHANGED** for 51 consecutive audit sessions. No new trade-level records
> are accessible from this sandbox. All analysis sections reflect **INSUFFICIENT_DATA**.

---

## AUDIT SCOPE CONFLICT — BOND Strategy Disabled

**CRITICAL: This audit framework targets `signal_source=='BOND'` trades exclusively.**

| Strategy | Status | Since |
|---|---|---|
| BOND_ENABLED | **False** | 2026-05-10 |
| SNIPER_ENABLED | **False** | 2026-04-16 |
| MOM_ENABLED | **False** | 2026-04-22 |
| DISCOVER (active) | **True** | 2026-05-10 |

Even if VPS SSH were restored, the BOND audit filter would return 0 trades for any window
after 2026-05-10. This audit framework is **structurally inapplicable** to the current live state.
Active strategy is **DISCOVER** (ETH-only, DOWN direction, ask 0.10–0.40).

---

## Confirmed Current Parameters (from main.py / window_sniper.py — ground truth)

| Parameter | Code Location | Current Value | Audit Prompt Assumed | Delta |
|---|---|---|---|---|
| min_ask (_ask_floor) | main.py:2454 | **0.78** | 0.80 | −0.02 |
| max_ask (_ask_max) | main.py:2452 | **0.93** | 0.88 | +0.05 |
| min_imbalance | main.py | **0.0 (neg blocked)** | 0.20 | — |
| bond_blocked_hours | config.py | **[]** | [] | none |
| stop_loss | main.py | **−15%** (ask×0.85) | −15% | none |
| BOND_ENABLED | window_sniper.py:133 | **False** | (assumed True) | — |

**Active DISCOVER parameters:**

| Parameter | Value | Location |
|---|---|---|
| Direction | DOWN only | discover_strategy.py:168 |
| Assets | ETH only (BTC blocked: live −$18.48 n=13) | discover_strategy.py:150 |
| ask range | 0.10 – 0.40 | discover_strategy.py:174 |
| rem window | 60 – 180s | discover_strategy.py:138 |
| arb_sum gate | < 0.99 | discover_strategy.py:196 |
| PT exit | bid ≥ 0.99 | main.py:1318 |
| Stake | $3 target | discover_strategy.py:58 |

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
INSUFFICIENT_DATA — 51st consecutive session with no VPS connectivity.
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
  "reason": "INSUFFICIENT_DATA — VPS unreachable (51st consecutive session). BOND disabled 2026-05-10; audit filter inapplicable to current live state (DISCOVER active: ETH-only DOWN). No parameter changes without data."
}
```

---

## Infrastructure Alert — Critical (51 consecutive sessions)

**Root cause**: TCP port 22 egress blocked at sandbox network boundary.
No trade data has been accessible for 51 consecutive audit sessions.

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

**Note:** With BOND disabled and DISCOVER active, a new audit framework scoped to DISCOVER
trades is also needed. Key fields: `signal_source`, `arb_sum_yes_no`, `entry_price`,
`exit_price`, `hold_s`, `net_pnl`, `exit_reason`, `asset`.
