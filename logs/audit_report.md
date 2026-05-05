# Quantitative Audit — 2026-05-05 06:14 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (30th consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 (native binary) | SSH binary absent from sandbox |
| SSH port 22 (paramiko) | Port 22 TCP-CLOSED at 85.137.174.86 (errno 11) |
| SSH ports 2222, 8022 | TCP-CLOSED |
| HTTP port 80 | TCP-OPEN but returns 403 Forbidden |
| HTTPS port 443 | TCP-OPEN but returns 403 Forbidden |
| logs/live_trades_recent.jsonl (git) | File absent — cron sync not deployed |
| local logs/trades.jsonl | Absent (not tracked in git) |

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
Current gate (main.py:2299): `if not (0.30 <= _term_imb < 0.70): continue`
Comment cites: COR=75% n=75 in [0.3,0.7); COR=58% below 0.30; COR=58% at ≥0.70.

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
**INSUFFICIENT_DATA** — VPS unreachable from sandbox (30th consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour all-time in this session (threshold: n≥100/hour for block/unblock decisions).

---

## Deployed Parameter State (from main.py / config.py)

| Parameter | Deployed value | Location |
|---|---|---|
| ask floor | 0.80 (TERMINAL-only; early window disabled) | main.py:2243 |
| max_ask | 0.92 | main.py:2241 |
| min_imbalance | 0.30 (floor; ceiling 0.70 added) | main.py:2299 |
| bond_blocked_hours_utc | [] (all hours unblocked) | config.py:157 |
| stop_loss | ask×0.85 (−15%) | main.py:2775 |
| base_stake | $4.00 | config.py:27 |
| scaled_stake | $4.00 (heat-check disabled) | config.py:34 |
| BOND_TIME_EXIT | T-3s unconditional | main.py:1213 |
| BOND_DEADLINE | T-3s forced exit | main.py:1222 |

## Bankroll State (git-tracked bankroll.json)
capital=$37.32 | total_trades=2605 | total_pnl=+$87.87 | saved_ts=1746160000 (~2026-05-02 04:26 UTC)

Note: bankroll snapshot is stale by ~3 days. Bot has been running continuously since then.

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

## Infrastructure Alert — Critical (30 consecutive sessions)

SSH port 22 actively closed at 85.137.174.86. SSH binary absent in sandbox.
HTTP/HTTPS return 403 (Cloudflare WAF or firewall).

**Required action (one command on the VPS):**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Or deploy cron sync (every 30 minutes):**
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

Without log data, audit is structurally blocked. 30 sessions × ~5 min each = ~2.5 hours wasted.
The cron above is a 30-second fix that unblocks all future audits.
