# Quantitative Audit — 2026-04-28 06:18 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (4th consecutive session)**

SSH port 22 on `85.137.174.86` returns EAGAIN (connection refused / actively closed).
HTTP ports 80/443 return "Host not in allowlist" (sandbox proxy blocks arbitrary-IP egress).
No outbound TCP to port 22 is possible from this Claude Code sandbox.

| Session | Time (UTC) | SSH result |
|---|---|---|
| Audit 1 | 2026-04-27 ~18:42 | Timeout (10s) |
| Audit 2 | 2026-04-28 00:10 | Timeout (15s) |
| Scout   | 2026-04-28 00:42 | Port REFUSED (sshd may be down) |
| Audit 3 | 2026-04-28 04:44 | EAGAIN (blocked) |
| **Audit 4** | **2026-04-28 06:18** | **EAGAIN — port 22 closed** |

Local state (`logs/bankroll.json`): `total_trades=0`, `capital=109.66`.
This is the local dev repo — no live trades have executed here.

---

## 6h Summary
n_trades=0 | WR=N/A | E=N/A | Kelly=N/A
0.80-0.84: n=0 WR=N/A E=N/A
0.84-0.88: n=0 WR=N/A E=N/A

## Loss Signatures
None in window — no data available.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

## Hour Analysis (all-time, 0.80-0.88)
No data available — VPS unreachable, local logs empty.

| H | n | WR | PF | status |
|---|---|----|----|--------|
| all | 0 | — | — | collecting data |

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (TCP blocked). No trades.jsonl retrieved.

Minimum thresholds not met:
- 6h ask/imbalance patch requires n>=20 per bucket (have: 0)
- Hour block decisions require n>=100 per hour (have: 0)

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.88,
  "min_imbalance": 0.20,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": []
}
```

**No parameter changes applied.** All values remain at current defaults.
Reason: zero trade data — no evidence base for any modification.

## Current Parameters (confirmed from main.py)
| Parameter | Value | Source |
|---|---|---|
| min_ask | 0.80 | main.py:1650 |
| max_ask | 0.88 | main.py:1649 |
| min_imbalance | 0.20 | main.py:1703 |
| blocked_hours | set() | main.py:1626 |

## Infrastructure Alert
Port 22 has been closed/refused since at least 2026-04-28 00:42 UTC (~5.5h).
Prior two attempts showed timeout (filtered firewall); latest show refused (sshd down).

**Required action before next audit can produce any useful output:**

```
1. Access VPS via provider console (not SSH):
   - Check if VM is still running at 85.137.174.86
   - If running: sudo systemctl start sshd (or sshd restart)
   - Verify: netstat -tlnp | grep 22

2. Verify bot is still trading:
   - systemctl status klaus
   - tail -f /root/Klaus/logs/bot.log

3. Confirm trades.jsonl is being written:
   - wc -l /root/Klaus/logs/trades.jsonl
   - tail -5 /root/Klaus/logs/trades.jsonl
```

At the Apr 26 rate of ~201 trades/day, every 6h of VPS downtime = ~50 missed trade records.
