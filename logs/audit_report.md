# Quantitative Audit — 2026-05-01 00:05 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (15th consecutive session)**

TCP port 22 to 85.137.174.86 — SSH binary absent from sandbox (confirmed Audit 12).
No `trades.jsonl` retrieved. No `post_exit.jsonl` retrieved.

| Session | Time (UTC) | Result |
|---|---|---|
| Audits 1–11 | 2026-04-27 – 2026-04-30 00:07 | SSH not found / EAGAIN / CF WAF 403 |
| Audit 12 | 2026-04-30 00:08 | paramiko installed; TCP timeout confirmed |
| Audit 13 | 2026-04-30 12:15 | TCP timeout; no data |
| Audit 14 | 2026-04-30 18:14 | TCP timeout; no data |
| **Audit 15** | **2026-05-01 00:05** | **SSH binary absent; no data** |

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
| 02 | unknown | unknown  | 0.19 (pre-range-widening) | BLOCKED (PF=0.19, prior audit) |
| 03 | unknown | unknown  | — (WR=14.3%, n=10) | BLOCKED (WR=14.3%, prior audit) |
| 05 | unknown | unknown  | 0.21 (pre-range-widening) | BLOCKED (PF=0.21, prior audit) |
| all other | — | — | — | collecting data |

Note: ask range widened 0.80–0.88 → 0.70–0.92 on 2026-04-30 06:06. Hour data in new buckets
(0.70–0.80, 0.88–0.92) is zero. No unblock/block decisions possible without n≥100 per hour
in 0.70–0.92 range.

---

## Changes Since Audit 14 (2026-04-30 18:14 UTC → 2026-05-01 00:05 UTC)

| Commit | Time (UTC) | Change | Audit Verdict |
|---|---|---|---|
| `a105a6e` | 2026-04-30 20:02 | Gate: thin_snap30 (snap30<0 AND depth<200); fix stage2_fallback | Logic fix; no parameter impact |
| `924808c` | 2026-04-30 20:31 | Fix: post-orphan reconcile skips when positions open; log CAPITAL_CORRECTION | Data quality fix; no parameter impact |
| `1c06ba2` | 2026-04-30 21:09 | Fix: PAE exit records entry_price as exit_price via stale WS fill | Critical P&L accuracy fix; no parameter impact |
| `c3f088c` | 2026-04-30 21:34 | Reduce stake $10→$4 (capital preservation, bankroll $50.48 near ruin floor) | **Stake change; reflected in SYSTEM_PATCH** |

---

## Bankroll Snapshot

| Field | Value | Note |
|---|---|---|
| capital (git) | $34.28 | Committed 2026-04-29 04:59 UTC (~43h stale) |
| capital (commit ref) | ~$50.48 | Referenced in c3f088c at 2026-04-30 21:34 UTC |
| total_trades (git) | 2025 | As of 2026-04-29 04:59 UTC |
| total_pnl (git) | +$99.30 | As of 2026-04-29 04:59 UTC |

Capital estimate at audit time: ~$50.48 (per most recent commit reference). Live capital unknown.

---

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (SSH binary absent).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n<100 per blocked hour (threshold: n≥100 for audit-driven block/unblock decisions).

**RISK FLAG — Ask range 0.70–0.92 live with zero analyzable data in new buckets.**
- 0.70–0.80: no prior WR/PF known; out-of-money territory, resolution uncertain
- 0.88–0.92: previously worst bucket per pre-widening audits
- At $4 stake, one 0.88–0.92 fill going to zero ≈ -$4 (~7.9% of ~$50 estimated capital)
- Stake reduction 10→4 materially reduces per-trade catastrophic exposure

---

## Current Parameters (confirmed from main.py + config.py)
| Parameter | Value | Line | Last changed |
|---|---|---|---|
| min_ask | 0.70 | main.py:1816 | 2026-04-30 06:06 (commit 7088b39) |
| max_ask | 0.92 | main.py:1815 | 2026-04-30 06:06 (commit 7088b39) |
| min_imbalance | 0.20 | main.py:1870 | unchanged |
| blocked_hours | {2, 3, 5} | main.py:1786 | unchanged |
| stop_loss | ask×0.85 (−15%) | main.py | unchanged |
| stake | $4.00 | config.py | 2026-04-30 21:34 (commit c3f088c) |
| thin_snap30 gate | snap30<0 AND depth<200 | main.py | 2026-04-30 20:02 (commit a105a6e) |
| PAE | 20s at −5% | main.py | 2026-04-30 08:09 (commit 5300379) |
| stale ask gate | ≥4s | main.py | 2026-04-30 12:10 (commit 9269982) |

## SYSTEM_PATCH
```json
{
  "min_ask": 0.70,
  "max_ask": 0.92,
  "min_imbalance": 0.20,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": [2, 3, 5]
}
```

**No parameter changes applied.** Values reflect actual current code state.
Reason: zero trade data retrieved — evidence base for modification: none. INSUFFICIENT_DATA enforced.

---

## Infrastructure Alert — Persistent (15 sessions)

The sandbox has no SSH binary and TCP port 22 is blocked at the network level.
Estimated **~5,000+ trade records** accumulated and unanalyzable since first SSH failure (~5 days ago).

### Recommended action (unchanged from Audits 11–14):
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
