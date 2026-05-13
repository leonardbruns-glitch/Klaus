# Quantitative Audit — 2026-05-13 18:10 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (55th consecutive session)**

| Method | Result |
|---|---|
| SSH to root@85.137.174.86:22 | SSH binary absent in sandbox; TCP port 22 blocked at network boundary |
| /tmp/trades.jsonl | 0 real lines — SSH pull failed |
| /tmp/post_exit.jsonl | 0 lines — not retrieved |
| logs/trades.jsonl (git-tracked) | Not present — VPS has not synced to repo |
| logs/bankroll.json (local snapshot) | Readable — **UNCHANGED since 2026-05-08 19:26 UTC (118.7h stale)** |

**Bankroll snapshot** (ts=1778268412 / 2026-05-08 19:26 UTC — 4.9 days stale):
- capital: $84.61
- total_trades: 2,605
- total_pnl: +$87.87
- consecutive_wins: 0

> Bankroll snapshot **UNCHANGED** for 55 consecutive audit sessions. Actual live capital unknown.
> No new trade-level records accessible from this sandbox.

---

## AUDIT SCOPE CONFLICT — BOND Strategy Disabled (55th session)

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

## Active Strategy Parameters (ground truth from codebase)

### LDA — Late Direction Arb (deployed 2026-05-12 21:41 UTC)
Source: `strategy/late_direction_arb.py`

| Parameter | Value | Notes |
|---|---|---|
| ASK_FLOOR | 0.70 | line 25 |
| ASK_CEIL | 0.98 | line 26 |
| REM_MIN_S | 8.0s | line 28 |
| REM_MAX_S | 90.0s | line 29 |
| BNC_MOVE_MIN | 0.07% | line 30 |
| STAKE_USD | $5.00 | line 31 |
| BLOCKED_HOURS_UTC | {1} | line 32 — H01 shadow WR=88.6% wrong=9, n=79 |

Signal: Binance 5m-return direction. Shadow accuracy baseline: 96.6% (n=85 windows).

Recent LDA git changes (last 5 commits):
- `99411b6` lda: block H13 [120,300s) all assets — WR=70% n=87, volatile
- `b52690d` lda: block SOL H06/H22 [120,300s); reduce stake $2 for watch cells
- `4be747c` lda: block H00 — WR=66% n=106 CI=[56.6%,74.4%] (shadow May8-12)
- `8426702` lda: tighten [120,300s) zone — block negative-EV ask×rem×hour cells
- `07cc945` Audit 20260513-1249 — no patch required

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

6h window: 2026-05-13 12:10 UTC → 2026-05-13 18:10 UTC

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
INSUFFICIENT_DATA — 55th consecutive session with no VPS connectivity.
AUDIT_SCOPE_CONFLICT — BOND disabled 2026-05-10; audit framework targets non-active strategy.
NO_CHANGE — no parameter changes without data.

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
  "reason": "INSUFFICIENT_DATA — VPS unreachable (55th consecutive session). BOND disabled 2026-05-10; audit filter inapplicable. Active strategies: LDA + DISCOVER. No parameter changes without data."
}
```

---

## Infrastructure Alert — Critical (55 consecutive sessions)

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

**Note on audit framework**: With BOND disabled and LDA+DISCOVER active, a new audit framework targeting `signal_source=='LDA'` and `signal_source=='DISCOVER'` is needed. Key LDA fields: `entry_price`, `exit_price`, `exit_reason`, `hold_s`, `net_pnl`, `asset`, `bnc_move_pct`.
