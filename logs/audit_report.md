# Quantitative Audit — 2026-05-06 06:10 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (33rd consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 | Installed (openssh-client 9.6p1 now present), but `ssh: connect to host 85.137.174.86 port 22: Connection timed out` |
| logs/live_trades_recent.jsonl (git) | File absent — cron sync not deployed |
| local logs/trades.jsonl | Absent (not tracked in git) |
| local logs/post_exit.jsonl | Absent |

> Previous sessions failed with `ssh: command not found`. This session: SSH binary is installed, but egress to port 22 from this sandbox is blocked (firewall or VPS down). The VPS or network between sandbox and VPS must be investigated.

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A
0.80–0.84 bucket: n=0 WR=N/A E=N/A
0.84–0.92 bucket: n=0 WR=N/A E=N/A

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

Current `bond_blocked_hours_utc` (config.py:156): `[]` (all hours unblocked)
Block threshold: n≥100 per hour AND PF<0.80.
Unblock threshold: n≥100 per hour AND PF≥0.90.
Cannot evaluate without data. No change to blocked_hours.

---

## Flags
**INSUFFICIENT_DATA** — SSH port 22 timeout from sandbox (33rd consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour all-time in this session (threshold: n≥100/hour for block/unblock decisions).

---

## Deployed Parameter State (from main.py + config.py)

| Parameter | Deployed value | Location |
|---|---|---|
| ask floor | 0.80 | main.py:2254 |
| max_ask | 0.92 | main.py:2252 (extended from 0.88 on 2026-04-30) |
| min_imbalance | 0.30 | main.py:2311 `if not (0.30 <= _term_imb < _imb_ceil):` |
| bond_blocked_hours_utc | [] (all hours unblocked) | config.py:156 |
| stop_loss | ask×0.85 (−15%) | main.py (BOND_CATASTROPHIC) |
| base_stake | $20.00 | config.py:27 (raised $4→$20 per user directive 2026-05-05) |
| scaled_stake | $20.00 (heat-check disabled) | config.py:33 |

## Bankroll State (git-tracked bankroll.json — stale ~4 days)
capital=$37.32 | total_trades=2605 | total_pnl=+$87.87 | saved_ts=1746160000 (~2026-05-02 04:26 UTC)
Note: a $50+ deposit was made 2026-05-05; actual current capital unknown without VPS access.

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.92,
  "min_imbalance": 0.30,
  "stake": 20.00,
  "stop_loss": -0.15,
  "blocked_hours": []
}
```

**No parameter changes applied.**
Reason: zero trade data retrieved from VPS — evidence base for any modification: none.
INSUFFICIENT_DATA enforced per anti-sycophancy rules.

---

## Infrastructure Alert — Critical (33 consecutive sessions)

**Previous failure mode**: `ssh` binary absent (`command not found`)
**Current failure mode**: `ssh` binary installed; `connect to host 85.137.174.86 port 22: Connection timed out`

This indicates either:
1. The VPS is down or unreachable
2. This sandbox's outbound port 22 is blocked by firewall rules
3. The VPS firewall is blocking this sandbox's IP range

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

Without log data, audit is structurally blocked. 33 sessions wasted.
The cron above is a 30-second fix that unblocks all future audits permanently.
