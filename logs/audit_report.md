# Quantitative Audit — 2026-04-30 12:15 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (13th consecutive session)**

SSH binary not installed in sandbox. TCP port 22 returns EAGAIN/timeout.
paramiko installed this session but confirmed TCP-level block (TimeoutError on connect).
No `trades.jsonl` retrieved. No `post_exit.jsonl` retrieved.

| Session | Time (UTC) | Result |
|---|---|---|
| Audits 1–11 | 2026-04-27 – 2026-04-30 00:07 | SSH not found / EAGAIN / CF WAF 403 |
| **Audit 12** | **2026-04-30 12:15** | **paramiko installed; TCP timeout confirmed** |

---

## 6h Summary
n_trades=0 (no trades.jsonl) | WR=N/A | E=N/A | Kelly=N/A
0.70-0.84: n=0 WR=N/A E=N/A
0.84-0.92: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

Note: ask range was widened 0.80–0.88 → 0.70–0.92 on 2026-04-30 ~08:XX UTC (user instruction).
Analysis buckets updated to reflect live range.

## Loss Signatures
None in window — no data retrievable.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

## Hour Analysis (all-time, 0.70–0.92)
No raw trades.jsonl — embedding best available data from state_log and commit messages.
**n<100 per hour for all hours → no block/unblock decisions warranted by audit rules.**

| H  | n (est) | WR (est) | PF (est) | status |
|----|---------|----------|----------|--------|
| 02 | ~24     | ~50%     | 0.19     | **BLOCKED** (PF=0.19, user-override n<100) |
| 03 | ~10     | ~14%     | —        | **BLOCKED** (WR=14.3%, n=10 current strategy) |
| 05 | ~55     | ~58%     | 0.21     | **BLOCKED** (PF=0.21, user-override n<100) |
| 06 | ~17     | ~29%     | —        | **SOL ONLY BLOCKED** (WR=29%, CLOB 5-share min) |
| 21 | ~46     | ~65%     | 1.19     | active (unblocked `0ddb49e`) |
| all other | — | — | — | collecting data |

0.70-0.92 range is live since 2026-04-30 08:XX UTC — zero historical data in these buckets.
All new sub-ranges (0.70-0.80 and 0.88-0.92) require n≥100 before any block/unblock consideration.

---

## Changes Since Last Audit (2026-04-30 00:07 UTC → 2026-04-30 12:15 UTC)

| Commit | Change | Audit Verdict |
|---|---|---|
| `7088b39` | Ask range 0.80–0.88 → 0.70–0.92 | User instruction; no prior evidence on new buckets. COLLECT DATA. |
| `98534c3` | Loss-exit T-10s→T-5s continuous poll (bid<entry_price) | Conditional: n=235 sim unconditional cost -$29.09; conditional preserves winners |
| `b44277c` | T-10/T-5 conditional exit + T-4s unconditional TIME_EXIT | Predecessor commit (conditional version replaced this) |
| `5300379` | PAE: exit if bid ≥5% below entry for 20s continuous | t_adv>20s WR=29% n=623 net=-$805; strong n; correct direction |
| `f90ef19` | PAE timer reset requires 5s sustained recovery | Anti-whipsaw fix; reduces false timer resets on brief pops |
| `8dd7f01` | XP patch: _capture_resolution writes wop/entered_correctly to trades.jsonl | Data quality fix; 860 records backfilled |
| `9269982` | Stale ask gate tightened 999s→4s | 3-day n=72 stale≥4s net=-$35.07; dominant T02829/T02814 evidence; correct |
| `cfc081f` | state_log: record stale gate + T02829 correction | Logging/data quality only |

---

## Bankroll Snapshot (git-committed 2026-04-29 04:59 UTC — ~31h old)

| Field | Value |
|---|---|
| capital | $34.28 |
| total_trades | 2025 |
| total_pnl | +$99.30 |

State_log trajectory:
- 2026-04-29 16:XX: ruin-floor override at capital=$45.91
- 2026-04-29 19:XX: stake cap raised $4→$10 at capital=$32.45
- 2026-04-30 ~14:XX: T02829 correction shows capital_after 53.52→43.68 (most recent data point)

Capital appears to be oscillating in the $30–55 range. Stake at $10 means a 3-asset simultaneous
bad window = -$30 (worst case), which is ~65% drawdown from $43-55 range.

---

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (TCP timeout; SSH not installed).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n<100 per blocked hour (threshold: n≥100 for audit-driven block/unblock decisions).

**RISK FLAG — Ask range 0.70-0.92 live with zero historical data in new buckets.**
- 0.70-0.80 bucket: no prior WR/PF known; entry×1.12 TP=0.784-0.896 (achievable)
- 0.88-0.92 bucket: previously worst-performing bucket per prior audits; now open
- At $10 stake, a single 0.88-0.92 entry going to zero = -$10 (23-33% of estimated capital)
- COLLECT DATA on new buckets before evaluating; recommend monitoring closely

**INFRA ALERT (13th session) — git-sync cron still not installed on VPS.**
Recommended action from Audit 11 still pending. Every audit session loses all quantitative
analysis capability. ~3,000+ additional trade records estimated accumulated and unanalyzable
since first SSH failure (~4 days ago).

---

## Current Parameters (confirmed from main.py)
| Parameter | Value | Source | Changed since last audit |
|---|---|---|---|
| min_ask | 0.70 | main.py:1816 | YES (was 0.80) |
| max_ask | 0.92 | main.py:1815 | YES (was 0.88) |
| min_imbalance | 0.20 | main.py:1870 | no |
| blocked_hours | {2, 3, 5} | main.py:1786 | no |
| stop_loss (BC) | -2.0 (disabled) | main.py:813 | no |
| stake | $10.00 | config.py | no |

## SYSTEM_PATCH
```json
{
  "min_ask": 0.70,
  "max_ask": 0.92,
  "min_imbalance": 0.20,
  "stake": 10.00,
  "stop_loss": -2.0,
  "blocked_hours": [2, 3, 5]
}
```

**No parameter changes applied.** All values reflect current code state.
Reason: zero trade data retrieved — evidence base for modification: none.
All thresholds (n≥20 for 6h ask/imbalance, n≥100 per hour for blocks) unmet.
Note: ask range now 0.70-0.92 per user instruction; audit buckets updated accordingly.

---

## Infrastructure Alert — Persistent (13 sessions)

The sandbox has no SSH binary (TCP-level firewall confirmed by paramiko timeout).
HTTP/HTTPS reach the IP but Cloudflare returns 403 on all endpoints.
**~3,000+ trade records** estimated lost to analysis since first failure.

### Recommended immediate action (unchanged from Audit 11):
```bash
# On VPS: /etc/cron.d/push-logs
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N
```
Audit agent reads `logs/live_trades_recent.jsonl` from GitHub — no SSH required.
This is the only viable path given sandbox TCP constraints.

**Without this, the quantitative auditor cannot function. Every audit is a no-op.**
