# Quantitative Audit — 2026-04-30 18:14 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (14th consecutive session)**

TCP port 22 to 85.137.174.86 timed out (paramiko confirmed, no SSH binary in sandbox).
No `trades.jsonl` retrieved. No `post_exit.jsonl` retrieved.

| Session | Time (UTC) | Result |
|---|---|---|
| Audits 1–11 | 2026-04-27 – 2026-04-30 00:07 | SSH not found / EAGAIN / CF WAF 403 |
| Audit 12 | 2026-04-30 00:08 | paramiko installed; TCP timeout confirmed |
| Audit 13 | 2026-04-30 12:15 | TCP timeout; no data |
| **Audit 14** | **2026-04-30 18:14** | **TCP timeout; no data** |

---

## 6h Summary
n_trades=0 (no trades.jsonl) | WR=N/A | E=N/A | Kelly=N/A
0.70-0.84: n=0 WR=N/A E=N/A
0.84-0.92: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None in window — no data retrievable.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

## Hour Analysis (all-time, 0.70–0.92)
No raw trades.jsonl — n<100 per hour for all hours → no block/unblock decisions warranted.

| H  | n (est) | WR (est) | PF (est) | status |
|----|---------|----------|----------|--------|
| 02 | ~24     | ~50%     | 0.19     | BLOCKED (PF=0.19, user-override n<100) |
| 03 | ~10     | ~14%     | —        | BLOCKED (WR=14.3%, n=10 current strategy) |
| 05 | ~55     | ~58%     | 0.21     | BLOCKED (PF=0.21, user-override n<100) |
| all other | — | — | — | collecting data |

0.70–0.92 range live since 2026-04-30 06:06 UTC. Zero historical data in 0.70–0.80 and 0.88–0.92 sub-buckets.

---

## Changes Since Audit 13 (2026-04-30 12:15 UTC → 18:14 UTC)

| Commit | Change | Audit Verdict |
|---|---|---|
| `b52fe72` | net_pnl corruption fix on EXTERNALLY_SOLD/partial fill (negative fee clamp now also resets net_pnl) | Data quality fix; correct; no parameter impact |

No parameter changes in this window.

---

## Bankroll Snapshot (git-committed 2026-04-29 04:59 UTC — ~37h old)

| Field | Value |
|---|---|
| capital | $34.28 |
| total_trades | 2025 |
| total_pnl | +$99.30 |
| saved_ts | 2026-04-29 04:59 UTC |

Capital is ~37h stale. Estimated live capital unknown.

---

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (TCP timeout; SSH not installed).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n<100 per blocked hour (threshold: n≥100 for audit-driven block/unblock decisions).

**RISK FLAG — Ask range 0.70-0.92 live with zero historical data in new buckets.**
- 0.70–0.80: no prior WR/PF known; TP at entry×1.12 still reachable
- 0.88–0.92: previously worst bucket per pre-widening audits
- At $10 stake, one 0.88–0.92 fill going to zero ≈ -$10 (~29% of last known $34.28 capital)
- Monitor closely; no changes until n≥20 in each bucket

---

## Current Parameters (confirmed from main.py)
| Parameter | Value | Line | Last changed |
|---|---|---|---|
| min_ask | 0.70 | 1816 | 2026-04-30 06:06 (commit 7088b39) |
| max_ask | 0.92 | 1815 | 2026-04-30 06:06 (commit 7088b39) |
| min_imbalance | 0.20 | 1870 | unchanged |
| blocked_hours | {2, 3, 5} | 1786 | unchanged |
| stop_loss | ask×0.85 (-15%) | 2071 | unchanged |
| stake | $10.00 | config.py | unchanged |
| d5s gate | 25% | 2044 | 2026-04-30 05:39 (commit 7720d7f) |
| stale ask gate | ≥4s | 1998 | 2026-04-30 12:10 (commit 9269982) |
| PAE | 20s at -5% | 972 | 2026-04-30 08:09 (commit 5300379) |
| snap60 low gate | <12% | 2014 | earlier |
| snap60 spike gate | >150% + <5s stale | 2034 | earlier |

## SYSTEM_PATCH
```json
{
  "min_ask": 0.70,
  "max_ask": 0.92,
  "min_imbalance": 0.20,
  "stake": 10.00,
  "stop_loss": -0.15,
  "blocked_hours": [2, 3, 5]
}
```

**No parameter changes applied.** All values reflect current code state.
Reason: zero trade data retrieved — evidence base for modification: none.

---

## Infrastructure Alert — Persistent (14 sessions)

The sandbox has no SSH binary and TCP port 22 is blocked at the network level.
**~4,000+ trade records** estimated accumulated and unanalyzable since first SSH failure (~4 days ago).

### Recommended action (unchanged from Audits 11–13):
```bash
# On VPS: /etc/cron.d/push-logs
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N
```
Audit agent reads `logs/live_trades_recent.jsonl` from GitHub — no SSH required.

**Without this cron, the quantitative auditor cannot function. Every audit is a no-op.**
