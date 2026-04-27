# Quantitative Audit — 2026-04-27 18:42 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE**

SSH connection to `root@85.137.174.86:22` timed out after 10s. No trade data could be retrieved.

Local state (`logs/bankroll.json`): `total_trades=0`, `capital=109.66`. This is the local dev environment — no trades have run here.

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
INSUFFICIENT_DATA — VPS SSH timeout. No trades.jsonl retrieved. Cannot compute any metrics.

Minimum thresholds not met:
- 6h ask/imbalance analysis requires n>=20 per bucket (have: 0)
- Hour block analysis requires n>=100 per hour (have: 0)

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

**No parameter changes applied.** All values remain at current defaults. Reason: zero trade data — no evidence base for any modification.

## Action Required
1. Verify VPS health: `ping 85.137.174.86` / check provider console.
2. Once VPS is reachable, re-run audit: data volume may now meet n>=20 threshold.
3. Check if `/root/Klaus/logs/trades.jsonl` exists on VPS (bot may not have traded yet).
