# Quantitative Audit — 2026-05-01 18:06 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (17th consecutive session)**

TCP port 22 to 85.137.174.86 — SSH binary absent from sandbox. No `trades.jsonl` retrieved. No `post_exit.jsonl` retrieved.

| Session | Time (UTC) | Result |
|---|---|---|
| Audits 1–11 | 2026-04-27 – 2026-04-30 00:07 | SSH not found / EAGAIN / CF WAF 403 |
| Audit 12 | 2026-04-30 00:08 | paramiko installed; TCP timeout confirmed |
| Audit 13 | 2026-04-30 12:15 | TCP timeout; no data |
| Audit 14 | 2026-04-30 18:14 | TCP timeout; no data |
| Audit 15 | 2026-05-01 00:05 | TCP timeout; no data |
| Audit 16 | 2026-05-01 06:10 | TCP timeout; no data |
| **Audit 17** | **2026-05-01 18:06** | **SSH binary absent; no data** |

---

## 6h Summary
n_trades=0 (no trades.jsonl) | WR=N/A | E=N/A | Kelly=N/A
0.70–0.84: n=0 WR=N/A E=N/A
0.84–0.92: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None in window — no data retrievable.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

## Hour Analysis (all-time, 0.70–0.92)
No raw trades.jsonl — n<100 per hour for all hours → no block/unblock decisions possible.

| H  | n     | WR      | PF   | status |
|----|-------|---------|------|--------|
| 00 | unk   | unk     | unk  | BLOCKED (user-instructed 2026-05-01) |
| 02 | unk   | unk     | 0.19 | BLOCKED (PF=0.19) |
| 03 | unk   | 14.3%   | unk  | BLOCKED (WR=14.3%) |
| 05 | unk   | unk     | 0.21 | BLOCKED (PF=0.21) |
| 12 | ≈130  | unk     | 0.31 | BLOCKED (15min analysis 2026-05-01; Net=-$179) |
| 13 | ≈151  | unk     | 0.42 | BLOCKED (15min analysis 2026-05-01; Net=-$122) |
| 23 | unk   | unk     | unk  | BLOCKED (user-instructed 2026-05-01) |
| all other | — | — | — | collecting data |

Note: ask range is currently 0.70–0.92 (widened 2026-04-30). All-time data in new range
buckets (0.70–0.80, 0.88–0.92) is insufficient. Block/unblock decisions require n≥100 per
hour in the current 0.70–0.92 range — not met.

---

## Changes Since Audit 16 (2026-05-01 06:10 UTC → 2026-05-01 18:06 UTC)

| Commit | Time (UTC) | Change | Audit Verdict |
|---|---|---|---|
| `68aee45` | 2026-05-01 | Block H12, H13 + 14:45–15:45 UTC (15min analysis; H12 n≈130 PF=0.31, H13 n≈151 PF=0.42) | Justified by n≥100 PF data; reflected in current blocked_hours |
| `65b8039` | 2026-05-01 | Extend 06:30 block to 06:25 UTC (PF=0.40 at 06:25–06:30, n=15) | Provisional, n=15 below n≥20 threshold for audit-driven change |
| `4888e08` | 2026-05-01 | Raise stake $4→$10 (user directive) | User-directed; outside audit scope (stake: NEVER change autonomously) |
| `eecfc71` | 2026-05-01 | PAE depth gate: suppress when trigger_depth <12% at 20s confirmation | Logic fix; no parameter impact |
| `f9179b7` | 2026-05-01 | Exit T-10s, PAE bypass T-30s, TP fixed 0.98 | Logic change; no parameter impact |
| `5d51b42` | 2026-05-01 | Fix LOCKED_SHARES: cancel resting sell order on balance error at attempt 1 | Bug fix; no parameter impact |

---

## Bankroll Snapshot

| Field | Value | Note |
|---|---|---|
| capital (git) | $34.28 | Committed 2026-04-29 04:59 UTC (~61h stale) |
| stake | $10.00 | Raised from $4 per user directive 2026-05-01 |
| total_trades (git) | 2025 | As of 2026-04-29 04:59 UTC |
| total_pnl (git) | +$99.30 | As of 2026-04-29 04:59 UTC |

Live capital and trade count unknown (VPS unreachable). With stake at $10 and no loss limit
data, every CATASTROPHIC SL hit represents 29% of the last-known $34.28 bankroll.

**RISK FLAG**: stake raised to $10 while bankroll state is unknown. If live capital is still
near $34.28, a single -15% SL on a 2-position book = -$3.00 = 8.8% bankroll drawdown per
5-min window. Max drawdown kill switch = $75 from $300 — not immediately at risk, but live
capital unknown for 61+ hours.

---

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (SSH binary absent).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n<100 per blocked hour in new 0.70–0.92 range (threshold: n≥100 for audit block/unblock).

**RISK FLAG — 06:25 block extension (65b8039): n=15, below n≥20 audit threshold.**
- Provisional; may revert if sample was coincidentally bad.

**RISK FLAG — 04:45–05:00 + 16:55–17:45 minute gates (c3e8d5a): n=9 each.**
- Both gates remain provisional. No new data to confirm or reverse.

---

## Current Parameters (confirmed from main.py + config.py)

| Parameter | Value | Line | Last changed |
|---|---|---|---|
| min_ask | 0.70 | main.py:1856 | 2026-04-30 06:06 (commit 7088b39) |
| max_ask | 0.92 | main.py:1855 | 2026-04-30 06:06 (commit 7088b39) |
| min_imbalance | 0.20 | main.py:1910 | unchanged |
| blocked_hours | {0, 2, 3, 5, 12, 13, 23} | main.py:1820 | 2026-05-01 (commit 68aee45) |
| stop_loss | ask×0.85 (−15%) | main.py | unchanged |
| stake | $10.00 | config.py:27 | 2026-05-01 (commit 4888e08) |
| entry_window | 25–90s remaining | main.py:1845 | prior |
| PAE | 20s at −5%, bypass T-30s | main.py | 2026-05-01 (f9179b7) |
| TP | fixed 0.98 | main.py | 2026-05-01 (f9179b7) |
| thin_snap30 gate | snap30<0 AND depth<200 | main.py | 2026-04-30 (a105a6e) |
| stale ask gate | ≥3s (OB snapshot age) | main.py:1852 | prior |
| minute gate 06:25–07:15 UTC | all assets | main.py:1824 | 2026-05-01 (65b8039) |
| minute gate 04:45–05:00 UTC | all assets | main.py:1827 | 2026-05-01 (c3e8d5a) |
| minute gate 14:45–15:45 UTC | all assets | main.py:1830 | 2026-05-01 (68aee45) |
| minute gate 16:55–17:45 UTC | all assets | main.py:1833 | 2026-05-01 (c3e8d5a) |
| LOCKED_SHARES fix | cancel resting sell on balance error | execution/ | 2026-05-01 (5d51b42) |

## SYSTEM_PATCH
```json
{
  "min_ask": 0.70,
  "max_ask": 0.92,
  "min_imbalance": 0.20,
  "stake": 10.00,
  "stop_loss": -0.15,
  "blocked_hours": [0, 2, 3, 5, 12, 13, 23]
}
```

**No parameter changes applied.** Values reflect actual current code state.
Reason: zero trade data retrieved — evidence base for modification: none. INSUFFICIENT_DATA enforced.

---

## Infrastructure Alert — Persistent (17 sessions)

The sandbox has no SSH binary and TCP port 22 is blocked at the network level.
Estimated **~8,000–12,000+ trade records** accumulated and unanalyzable since first SSH failure (~6 days ago).

### Recommended action (unchanged from Audits 11–16):
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
