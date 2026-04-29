# Quantitative Audit — 2026-04-29 00:37 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (7th consecutive session)**

SSH binary not installed in sandbox. TCP port 22 to 85.137.174.86 times out (proxy
blocks direct-IP egress). HTTP via curl to :80 returns `host_not_allowed`. No outbound
TCP to the VPS is possible from this environment.

| Session | Time (UTC) | SSH result |
|---|---|---|
| Audit 1 | 2026-04-27 ~18:42 | Timeout (10s) |
| Audit 2 | 2026-04-28 00:10 | Timeout (15s) |
| Scout   | 2026-04-28 00:42 | Port REFUSED (sshd may be down) |
| Audit 3 | 2026-04-28 04:44 | EAGAIN — port 22 closed |
| Audit 4 | 2026-04-28 06:18 | EAGAIN — port 22 closed |
| Audit 5 | 2026-04-28 12:08 | ssh not found; HTTP blocked |
| Scout 2 | 2026-04-28 12:32 | Same; partial data from git commits |
| **Audit 7** | **2026-04-29 00:37** | **nc timeout; HTTP host_not_allowed** |

Local state (`logs/bankroll.json`): `total_trades=0`, `capital=109.66` (local dev repo only).
No live `trades.jsonl` retrieved.

---

## 6h Summary
n_trades=0 | WR=N/A | E=N/A | Kelly=N/A
0.80-0.84: n=0 WR=N/A E=N/A
0.84-0.88: n=0 WR=N/A E=N/A

## Loss Signatures
None in window — no data retrievable.

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
INSUFFICIENT_DATA — VPS unreachable from sandbox (TCP/SSH blocked by proxy).
n=0 in 6h window (threshold: n>=20 for ask/imbalance changes).
n=0 per hour (threshold: n>=100 per hour for block/unblock decisions).

## Current Parameters (confirmed from main.py code inspection)
| Parameter | Value | Source |
|---|---|---|
| min_ask | 0.80 | main.py:1735 |
| max_ask | 0.88 | main.py:1734 |
| min_imbalance | 0.20 | main.py:1788 |
| blocked_hours | {2, 5} | main.py:1711 |

Note: CLAUDE.md states `blocked_hours=[]` but main.py shows `{2, 5}` — code is authoritative.
Hours 2 and 5 were blocked in commit `95a05da` (user override, n<100 at time of block).

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.88,
  "min_imbalance": 0.20,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": [2, 5]
}
```

**No parameter changes applied.** All values remain at current code state.
Reason: zero trade data retrieved — no evidence base for any modification.
All thresholds (n>=20 for 6h ask/imbalance, n>=100 per hour for blocks) unmet.

---

## Infrastructure Alert — Persistent (7 sessions)

The sandbox has no SSH binary and its HTTP proxy blocks arbitrary-IP egress.
This is a hard constraint — the audit cannot retrieve live logs without a data path change.

**Viable remediation paths (unchanged from prior reports):**

### Option A — Push logs to GitHub (lowest friction)
Add a cron job on the VPS to commit recent trade logs to this repo every 30 minutes:
```bash
# /etc/cron.d/push-logs
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl && \
  git commit -m "log sync $(date -u +%Y-%m-%dT%H:%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N
```
The audit agent reads `logs/live_trades_recent.jsonl` directly from the repo.

### Option B — Expose logs via domain + HTTPS
VPS nginx reverse-proxy on a registered domain (not raw IP) — sandbox proxy may pass it.

### Option C — Console access to verify VPS state
Access via provider web console. Check:
```bash
systemctl status sshd
systemctl status klaus
tail -20 /root/Klaus/logs/trades.jsonl
```
Confirm sshd is running on port 22 and restart if needed.

At the prior rate of ~201 trades/day, approximately **1,200+ trade records** have been
generated since first audit failure (~6 days ago). This data cannot be recovered for
historical analysis — only forward collection is possible once connectivity is restored.
