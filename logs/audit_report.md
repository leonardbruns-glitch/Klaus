# Quantitative Audit — 2026-04-28 04:44 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE**

SSH connection to `root@85.137.174.86:22` blocked at network layer (EAGAIN — not timeout).
This sandbox has no outbound TCP to arbitrary IPs; confirmed by socket-level probe (`connect()` → EAGAIN).
`trades.jsonl` and `post_exit.jsonl` could not be retrieved.

Prior attempts:
- 2026-04-28 00:10 UTC — TCP timeout (15s)
- 2026-04-28 04:44 UTC — TCP blocked (EAGAIN)

Local state (`logs/bankroll.json`): `total_trades=0`, `capital=109.66`.
This is the local dev repo — no trades have executed here.

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
| min_imbalance | 0.20 | main.py:1696 |
| blocked_hours | set() | main.py:1626 |

## Action Required
This audit must be run from a machine with SSH access to `85.137.174.86`. Steps:
```bash
# From a machine with network access to VPS:
chmod 600 .agent_ssh_key
ssh -i .agent_ssh_key root@85.137.174.86 "tail -n 3000 /root/Klaus/logs/trades.jsonl" > /tmp/trades.jsonl
ssh -i .agent_ssh_key root@85.137.174.86 "tail -n 2000 /root/Klaus/logs/post_exit.jsonl" > /tmp/post_exit.jsonl
```
Then re-run the audit analysis with the retrieved files.

If VPS has been unreachable for >6h, verify provider console for `85.137.174.86`
and confirm the bot process: `systemctl status klaus`.
