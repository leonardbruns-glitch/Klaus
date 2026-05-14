# Quantitative Audit — 2026-05-14 18:09 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (57th consecutive session)**

| Method | Result |
|---|---|
| SSH to root@85.137.174.86:22 | Connection timed out (30s) |
| /tmp/trades.jsonl | 1 line = SSH error string; 0 real lines |
| /tmp/post_exit.jsonl | 0 lines — not retrieved |
| logs/trades.jsonl (git-tracked) | Not present — VPS has not synced to repo |
| logs/bankroll.json (local snapshot) | **UNCHANGED since 2026-05-08 19:26 UTC (142.7h stale)** |

**Bankroll snapshot** (ts=1778268412 / 2026-05-08 19:26 UTC — 5.9 days stale):
- capital: $84.61
- total_trades: 2,605
- total_pnl: +$87.87
- consecutive_wins: 0

> Bankroll snapshot **UNCHANGED** for 57 consecutive audit sessions. Actual live capital unknown.

---

## AUDIT SCOPE CONFLICT — BOND Strategy Disabled (57th session)

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

6h window: 2026-05-14 12:09 UTC → 2026-05-14 18:09 UTC

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
INSUFFICIENT_DATA — 57th consecutive session with no VPS connectivity.
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
  "reason": "INSUFFICIENT_DATA — VPS unreachable (57th consecutive session). BOND disabled 2026-05-10; audit filter inapplicable. Active strategies: LDA + DISCOVER. No parameter changes without data."
}
```

---

## Active Strategy Parameters (ground truth from codebase — 2026-05-14 18:09 UTC)

### LDA — Late Direction Arb
Source: `strategy/late_direction_arb.py`

| Parameter | Value | Notes |
|---|---|---|
| ASK_FLOOR | 0.60 | expanded from 0.70 |
| ASK_CEIL | 0.98 | |
| BID_MIN | 0.50 | |
| REM_MIN_S | 8.0s | |
| REM_MAX_S | 300.0s | ask-conditional dead zones enforce per-bucket |
| BLOCKED_HOURS_UTC | {0, 1} | H00 WR=66% n=106; H01 WR=88.6% n=79 (CI below baseline) |
| _ALL_BLOCKED_LATE | {3, 6, 12, 15} | [120,300s) bucket — EV negative all assets |
| _ALL_BLOCKED_LATE_B1 | {4, 15} | [60,120s) bucket — EV negative all assets |
| _SOL_BLOCKED_LATE | {10, 13, 22} | [120,300s) SOL-specific |
| _SOL_BLOCKED_ALL | {7, 9} | all buckets — user instruction 2026-05-14 |
| _ETH_BLOCKED_LATE | {16} | [120,300s) ETH-specific |
| _ETH_WATCH_LATE | {8, 9, 22} | $2 stake pending n≥100 |
| BTC B3 stake | $10 | rem [120,180s), WR=79% n=802 |
| BTC B1 base stake | $10 | rem [60,120s) BNC<0.08%, WR=94% n=198 |
| BTC B1 strong stake | $20 | BNC≥0.08%, WR=97% n=36 |
| BTC B2 base stake | $15 | rem [8,60s) BNC<0.08%, WR=90% n=127 |
| BTC B2 strong stake | $20 | BNC≥0.08%, WR=100% n=17 (trending) |
| ETH B3/B1/B2 base | $10 | strong tier at $20 (BNC≥0.07%) |
| SOL B3/B1 base | $10 | B1 strong $15 (BNC≥0.08%) |
| BNC_DECAY_THRESHOLD | −0.03% | freshness re-check at order time |

### Changes Since Last Audit (2026-05-14 00:15 UTC — 10 commits)

**6e24a05 — block all 15m windows**
- BTC 15m bnc>=0.10 partial-allow logic removed: 15m windows fully blocked

**64a90b7 — SOL H10/H13 + ETH H16 B3 blocks; ETH B1 H16 ask floor 0.80**
- SOL [120,300s): H10 WR=72% n=18, H13 WR=61% n=28 — both added to _SOL_BLOCKED_LATE
- ETH [120,300s): H16 WR=72% n=18 — added to _ETH_BLOCKED_LATE
- ETH [60,120s) H16: ask floor raised 0.60→0.80

**c5ce1c9 — flat two-tier stakes for ETH and SOL**
- Removed $7 Kelly cap; ETH and SOL each get asset-specific base/strong flat stakes

**19e8f11 — BTC two-tier stakes raise B1/B2 on BNC≥0.08%**
- B1 strong: $17→$20 (WR=97% n=36); B2 strong: trending, $20

**776484b — BTC rebalance: B3 $20→$10, B2 $5→$15**
- B3 Kelly lower than earlier estimate (WR=79%); B2 closer to $15 half-Kelly

**acd7241 — block BTC B4 (rem>=180s)**
- Kelly=0% at all BNC thresholds from market_timeline data

**0454bcc — 4-bucket dedup**
- One entry per rem zone (B4/B3/B1/B2) per window; prevents double-filling same zone

**7dfac11 — BTC bucket-based stakes**
- Initial stake differentiation: B4=$5, B3=$20, B1=$10, B2=$5

**855473b — unblock H13 from B1 and B2 (user instruction)**
- H13 removed from _ALL_BLOCKED_LATE and _ALL_BLOCKED_LATE_B1

**ad6da58 — SOL B3 ask ceiling 0.98→0.97**

### BOND Parameters (audit reference — BOND disabled since 2026-05-10)

| Parameter | Code Location | Current Value | Audit Prompt Assumed | Delta |
|---|---|---|---|---|
| min_ask (_ask_floor) | main.py:2521 | **0.78** | 0.80 | −0.02 |
| max_ask (_ask_max) | main.py:2519 | **0.93** | 0.88 | +0.05 |
| min_imbalance | main.py:2578 | **0.0 (gate inactive)** | 0.20 | — |
| _BLOCKED_HOURS | config.py:151 | **[] (bond_blocked_hours_utc=[])** | [] | none |
| stop_loss | main.py | **−15%** | −15% | none |
| BOND_ENABLED | window_sniper.py | **False** | (assumed True) | — |

---

## Infrastructure Alert — Critical (57 consecutive sessions)

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
