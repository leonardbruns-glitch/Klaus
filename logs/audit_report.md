# Quantitative Audit — 2026-05-10 18:07 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (46th consecutive session)**

| Method | Result |
|---|---|
| SSH to root@85.137.174.86:22 | TCP port 22 egress blocked at network boundary (ssh binary absent in sandbox) |
| /tmp/trades.jsonl | 0 lines — SSH pull failed |
| /tmp/post_exit.jsonl | 0 lines — SSH pull failed |
| logs/trades.jsonl (git-tracked) | not present |
| logs/bankroll.json (local snapshot) | readable — see below |

**Bankroll snapshot** (from `logs/bankroll.json`, ts=1778268412 / 2026-05-08 19:26 UTC):
- capital: $84.61
- total_trades: 2,605
- total_pnl: +$87.87
- consecutive_wins: 0
- daily_start_capital: $15.95 (stale — from last VPS-connected session)

> Root cause unchanged across 46 sessions: sandbox network blocks TCP port 22 egress.
> SSH binary is absent — the block is at the network boundary.
> No trade-level records (entry_price, exit_price, slippage, pnl, ob_imbalance) are accessible.
> All analysis sections below reflect **INSUFFICIENT_DATA**.

---

## Confirmed Current Parameters (from main.py / config.py — ground truth)

| Parameter | Code Location | Current Value | Notes |
|---|---|---|---|
| min_ask (_ask_floor) | main.py:2381 | **0.78** | Lowered from 0.80 on 2026-05-07 |
| max_ask (_ask_max) | main.py:2379 | **0.93** | Lowered from 0.95→0.93 on 2026-05-09 |
| min_imbalance (_term_imb gate) | main.py:2437–2438 | **0.0** | Negative imb blocked; positive imb passes |
| bond_blocked_hours_utc | config.py:151 | **[]** | All hours open |
| stop_loss | main.py | **−15%** (ask×0.85) | Unchanged |

> **Note**: The prompt "current values" (min_ask=0.80, max_ask=0.88, min_imbalance=0.20) are all stale.
> Code is the ground truth. Parameters confirmed by direct file reads this session.

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A

**Buckets (ask range, applied to actual floor=0.78 / ceil=0.93):**
- 0.78–0.84: n=0 WR=N/A E=N/A
- 0.84–0.93: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — ask/imbalance change threshold: n≥20 in 6h window. Not met.

## Loss Signatures
None determinable — no trade records accessible.

## OB Imbalance Breakdown
| Bucket | n | WR | PF |
|---|---|---|---|
| <0.00 (blocked via gate) | 0 | N/A | N/A |
| 0.00–0.20 | 0 | N/A | N/A |
| 0.20–0.30 | 0 | N/A | N/A |
| >0.30 | 0 | N/A | N/A |

Note: `min_imbalance` floor is 0.0 (relaxed 2026-05-09). Negative imb blocked at main.py:2437.

## Slippage
avg_slippage_entry=N/A (no data)

---

## Hour Analysis (all-time, 0.78–0.93 — actual current gates)
No trades.jsonl accessible. n=0 per hour — block/unblock threshold is n≥100/hour.

| H | n | WR | PF | status |
|---|---|---|---|---|
| 00–23 | 0 | N/A | N/A | collecting data |

Current `bond_blocked_hours_utc` (config.py:151): `[]` — all hours open.
Block criteria: n≥100/hour AND PF<0.80. **Not evaluable.**
Unblock criteria: hour in blocked set AND n≥100/hour AND PF≥0.90. **Not evaluable.**

No change to blocked_hours.

---

## Flags
- **INSUFFICIENT_DATA** — 6h n=0; all-time hour n=0; no trade records retrieved (46th consecutive session)
- No NEGATIVE_EDGE, OVERBET, or block/unblock decisions possible

## SYSTEM_PATCH
No change warranted. All patch conditions require trade data; none available.

```json
{
  "min_ask": 0.78,
  "max_ask": 0.93,
  "min_imbalance": 0.0,
  "stop_loss": -0.15,
  "blocked_hours": [],
  "change": false,
  "reason": "INSUFFICIENT_DATA — VPS unreachable, 0 trade records retrieved (46th consecutive session)"
}
```

---

## Infrastructure Alert — Critical (46 consecutive sessions)

**Root cause**: TCP port 22 egress blocked at sandbox network boundary. SSH binary is absent.
No trade data has been accessible for 46 consecutive audit sessions.

**Required action — run ONE of these on the VPS to unblock all future audits:**

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

Without log data, the audit is structurally blocked. Bankroll snapshot (2026-05-08 19:26 UTC) shows healthy state ($84.61, +$87.87 PnL on 2,605 trades) but parameter optimization is blind — no entry/exit details accessible.
