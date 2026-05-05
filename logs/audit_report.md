# Quantitative Audit — 2026-05-05 18:05 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (31st consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 | TCP timeout at 85.137.174.86 (ConnectTimeout=10s) |
| logs/live_trades_recent.jsonl (git) | File absent — cron sync not deployed |
| local logs/trades.jsonl | Absent (not tracked in git) |
| local logs/post_exit.jsonl | Absent |

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A
0.80–0.84 bucket: n=0 WR=N/A E=N/A
0.84–0.88 bucket: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None determinable — no data retrievable.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.80–0.88)
No trades.jsonl accessible. n=0 per hour — no block/unblock decisions possible (threshold: n≥100/hour).

| H | n | WR | PF | status |
|---|---|---|---|---|
| 00–23 | 0 | N/A | N/A | collecting data |

Current `bond_blocked_hours_utc` (config.py:157): `[]` (all hours unblocked)
Block threshold: n≥100 per hour AND PF<0.80.
Unblock threshold: n≥100 per hour AND PF≥0.90.
Cannot evaluate without data. No change to blocked_hours.

---

## Flags
**INSUFFICIENT_DATA** — VPS unreachable from sandbox (31st consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour all-time in this session (threshold: n≥100/hour for block/unblock decisions).

---

## Deployed Parameter State (from main.py / config.py)

| Parameter | Deployed value | Location |
|---|---|---|
| ask floor | 0.80 | main.py (TERMINAL gate) |
| max_ask | 0.92 | main.py |
| min_imbalance | 0.30 (floor; ceiling 0.70) | main.py |
| bond_blocked_hours_utc | [] (all hours unblocked) | config.py:157 |
| stop_loss | ask×0.85 (−15%) | main.py |
| base_stake | $4.00 | config.py:27 |
| scaled_stake | $4.00 (heat-check disabled) | config.py:34 |

## Bankroll State (git-tracked bankroll.json — stale ~3 days)
capital=$37.32 | total_trades=2605 | total_pnl=+$87.87 | saved_ts=1746160000 (~2026-05-02 04:26 UTC)

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.92,
  "min_imbalance": 0.30,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": []
}
```

**No parameter changes applied.**
Reason: zero trade data retrieved from VPS — evidence base for any modification: none.
INSUFFICIENT_DATA enforced per anti-sycophancy rules.

---

## Infrastructure Alert — Critical (31 consecutive sessions)

SSH port 22 connection timed out at 85.137.174.86. SSH binary confirmed installed this session but port unreachable.
HTTP/HTTPS previously returned 403 (Cloudflare WAF or firewall).

**Required action — run ONE of these on the VPS to unblock all future audits:**

**Option A: Manual one-time sync**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Option B: Deploy cron sync (every 30 minutes)**
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

Without log data, audit is structurally blocked. 31 sessions wasted.
The cron above is a 30-second fix that unblocks all future audits permanently.
