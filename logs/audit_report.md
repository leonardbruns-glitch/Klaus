# Quantitative Audit — 2026-05-01 06:10 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (16th consecutive session)**

TCP port 22 to 85.137.174.86 — SSH binary absent from sandbox. `paramiko` installed but TCP
handshake times out. No `trades.jsonl` retrieved. No `post_exit.jsonl` retrieved.

| Session | Time (UTC) | Result |
|---|---|---|
| Audits 1–11 | 2026-04-27 – 2026-04-30 00:07 | SSH not found / EAGAIN / CF WAF 403 |
| Audit 12 | 2026-04-30 00:08 | paramiko installed; TCP timeout confirmed |
| Audit 13 | 2026-04-30 12:15 | TCP timeout; no data |
| Audit 14 | 2026-04-30 18:14 | TCP timeout; no data |
| Audit 15 | 2026-05-01 00:05 | TCP timeout; no data |
| **Audit 16** | **2026-05-01 06:10** | **TCP timeout; no data** |

---

## 6h Summary
n_trades=0 (no trades.jsonl) | WR=N/A | E=N/A | Kelly=N/A
0.80–0.84: n=0 WR=N/A E=N/A
0.84–0.88: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None in window — no data retrievable.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

## Hour Analysis (all-time, 0.80–0.88)
No raw trades.jsonl — n<100 per hour for all hours → no block/unblock decisions warranted.

| H  | n (est) | WR (est) | PF (est) | status |
|----|---------|----------|----------|--------|
| 00 | unknown | WR=53% Net=-$13.83 n=26 (per commit e66edb6) | — | BLOCKED (user-instructed 2026-05-01) |
| 02 | unknown | Net=-$12.74 | 0.19 (pre-range-widening) | BLOCKED (PF=0.19) |
| 03 | unknown | WR=14.3% n=10 Net=-$6.77 | — | BLOCKED (WR=14.3%) |
| 05 | unknown | Net=-$12.48 | 0.21 (pre-range-widening) | BLOCKED (PF=0.21) |
| 23 | unknown | WR=53% Net=-$13.83 n=26 (combined 00+23 per commit) | — | BLOCKED (user-instructed 2026-05-01) |
| all other | — | — | — | collecting data |

Note: ask range widened 0.70–0.92 on 2026-04-30 06:06. All-time data in new buckets
(0.70–0.80, 0.88–0.92) is insufficient. No unblock/block decisions possible without n≥100
per hour in 0.70–0.92 range.

---

## Changes Since Audit 15 (2026-05-01 00:05 UTC → 2026-05-01 06:10 UTC)

| Commit | Time (UTC) | Change | Audit Verdict |
|---|---|---|---|
| `e66edb6` | 2026-05-01 04:53 | Block hours 00+23 UTC (user-instructed; 7h WR=53% Net=-$13.83 n=26) | Parameter change; reflected in SYSTEM_PATCH |
| `c3e8d5a` | 2026-05-01 05:24 | Block 04:45–05:00 UTC (44% WR vs 80% rest-of-H04 n=9) and 16:55–17:45 UTC (33% WR vs 62% rest-of-H17 n=9) | Intra-hour minute gates; n<100 — provisional, watch for reversion |
| `d6aab62` | 2026-05-01 05:52 | Log RSI + ask VWAP at entry (observation only, no gating) | No parameter impact; observation pipeline |
| `7f3a653` | 2026-05-01 05:58 | Fix RSI/VWAP: freeze snapshot at remaining=90s (pre-entry) not at-signal | Correctness fix; no parameter impact |

---

## Bankroll Snapshot

| Field | Value | Note |
|---|---|---|
| capital (git) | $34.28 | Committed 2026-04-29 04:59 UTC (~49h stale) |
| capital (commit ref) | ~$50.48 | Referenced in c3f088c at 2026-04-30 21:34 UTC |
| total_trades (git) | 2025 | As of 2026-04-29 04:59 UTC |
| total_pnl (git) | +$99.30 | As of 2026-04-29 04:59 UTC |

Live capital and trade count unknown (VPS unreachable).

---

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (SSH binary absent + TCP blocked).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n<100 per blocked hour (threshold: n≥100 for audit-driven block/unblock decisions).

**RISK FLAG — Intra-hour minute gates (c3e8d5a) based on n=9 per window. Below n≥20 threshold.**
- 04:45–05:00 block: n=9, provisional; may revert if sample was coincidentally bad.
- 16:55–17:45 block: n=9, provisional; same caveat.
- Both gates narrow the trading window by ~60 and ~50 minutes respectively.
- Recommend revisiting once n≥20 per sub-window is available from live data.

---

## Current Parameters (confirmed from main.py git state)
| Parameter | Value | Line | Last changed |
|---|---|---|---|
| min_ask | 0.70 | main.py:1845 | 2026-04-30 06:06 (commit 7088b39) |
| max_ask | 0.92 | main.py:1844 | 2026-04-30 06:06 (commit 7088b39) |
| min_imbalance | 0.20 | main.py:1870 | unchanged |
| blocked_hours | {0, 2, 3, 5, 23} | main.py:1809 | 2026-05-01 04:53 (commit e66edb6) |
| stop_loss | ask×0.85 (−15%) | main.py | unchanged |
| stake | $4.00 | config.py | 2026-04-30 21:34 (commit c3f088c) |
| thin_snap30 gate | snap30<0 AND depth<200 | main.py | 2026-04-30 20:02 (commit a105a6e) |
| PAE | 20s at −5% | main.py | 2026-04-30 08:09 (commit 5300379) |
| stale ask gate | ≥4s | main.py | 2026-04-30 12:10 (commit 9269982) |
| minute gate 06:30–07:30 UTC | all assets | main.py:1812-1813 | prior |
| minute gate 04:45–05:00 UTC | all assets | main.py:1816 | 2026-05-01 05:24 (commit c3e8d5a) |
| minute gate 16:55–17:45 UTC | all assets | main.py:1819 | 2026-05-01 05:24 (commit c3e8d5a) |
| minute gate H06 SOL only | 06:00–06:29 UTC | main.py:1822 | prior |
| RSI + ask VWAP | observation only (frozen at remaining=90s) | main.py:1778-1797 | 2026-05-01 05:52/05:58 |

## SYSTEM_PATCH
```json
{
  "min_ask": 0.70,
  "max_ask": 0.92,
  "min_imbalance": 0.20,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": [0, 2, 3, 5, 23]
}
```

**No parameter changes applied.** Values reflect actual current code state.
Reason: zero trade data retrieved — evidence base for modification: none. INSUFFICIENT_DATA enforced.

---

## Infrastructure Alert — Persistent (16 sessions)

The sandbox has no SSH binary and TCP port 22 is blocked at the network level.
Estimated **~6,000–8,000+ trade records** accumulated and unanalyzable since first SSH failure (~5+ days ago).

### Recommended action (unchanged from Audits 11–15):
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
