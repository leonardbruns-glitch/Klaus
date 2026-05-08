# Quantitative Audit — 2026-05-08 12:02 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (38th consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 to 85.137.174.86 | `ssh: command not found` — binary absent from sandbox |
| TCP connectivity | Port 22 egress blocked at sandbox network level |
| logs/live_trades_recent.jsonl (git) | Absent — cron sync not deployed |
| local logs/trades.jsonl | Absent (not git-tracked) |
| local logs/post_exit.jsonl | Absent |

> SSH binary absent from sandbox. TCP port 22 egress confirmed blocked at network level.
> No trade data is accessible. All analysis sections reflect INSUFFICIENT_DATA.

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A
0.78–0.84 bucket: n=0 WR=N/A E=N/A
0.84–0.92 bucket: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None determinable — no data retrievable.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.78–0.92)
No trades.jsonl accessible. n=0 per hour — no block/unblock decisions possible (threshold: n≥100/hour).

| H | n | WR | PF | status |
|---|---|---|---|---|
| 00–23 | 0 | N/A | N/A | collecting data |

Current `bond_blocked_hours_utc` (config.py): `[]` (all hours unblocked)
Block threshold: n≥100 per hour AND PF<0.80.
Unblock threshold: n≥100 per hour AND PF≥0.90.
Cannot evaluate without data. No change to blocked_hours.

---

## Flags
**INSUFFICIENT_DATA** — SSH blocked from sandbox (38th consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour all-time in this session (threshold: n≥100/hour for block/unblock decisions).

---

## Deployed Parameter State (from main.py + config.py)

| Parameter | Deployed value | Location |
|---|---|---|
| ask floor | 0.78 | main.py:2382 (0.80→0.78 2026-05-07) |
| max_ask | 0.92 | main.py:2380 (0.88→0.92 2026-05-07) |
| min_imbalance (ETH/SOL UP) | 0.35 | main.py:2451 |
| min_imbalance (BTC UP) | 0.50 | main.py:2446 |
| min_imbalance (DOWN) | 0.42 | main.py:2448 (0.35→0.42 2026-05-07) |
| bond_blocked_hours_utc | [] (all hours unblocked) | config.py:151 |
| stop_loss | ask×0.85 (−15%) | main.py:3091 (BOND_CATASTROPHIC) |
| base_stake | $50.00 | config.py:27 (30→50 2026-05-07) |
| scaled_stake | $50.00 (heat-check disabled) | config.py |
| snap60 floor (UP, normal) | 12% (ETH: 15%; 12:30–13:30: 25%) | main.py |
| snap60 floor (DOWN, normal) | 13% (ETH: 15%; 12:30–13:30: 25%) | main.py |
| snap60 early-window floor | 30% (ask<0.80) | main.py:2713 |
| tok5_gate (DOWN) | −3% blocks entry | main.py (Tier 2) |
| tok5_gate (UP) | +10% blocks entry | main.py (Tier 2) |

## Bankroll State (git-tracked bankroll.json — stale ~6 days)
capital=$37.32 | total_trades=2605 | total_pnl=+$87.87 | saved_ts=1746160000 (~2026-05-02 04:26 UTC)

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.78,
  "max_ask": 0.92,
  "min_imbalance_btc_up": 0.50,
  "min_imbalance_down": 0.42,
  "min_imbalance_other": 0.35,
  "stake": 50.00,
  "stop_loss": -0.15,
  "blocked_hours": []
}
```

**No parameter changes applied.**
Reason: zero trade data retrieved from VPS — evidence base for any modification: none.
INSUFFICIENT_DATA enforced per anti-sycophancy rules.

---

## Infrastructure Alert — Critical (38 consecutive sessions)

**Root cause**: Sandbox network blocks outbound TCP port 22 (confirmed: ssh binary absent; TCP connect to 85.137.174.86:22 blocked at network level). No trade data has been accessible for 38 consecutive audit sessions.

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

Without log data, the audit is structurally blocked for the 38th consecutive session.
