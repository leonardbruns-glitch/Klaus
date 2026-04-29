# Quantitative Audit — 2026-04-29 12:17 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (10th consecutive session)**

SSH binary not installed in sandbox. TCP port 22 to 85.137.174.86 returns EAGAIN
(filtered by proxy). HTTP proxy blocks raw-IP egress ("Host not in allowlist").
No `trades.jsonl` retrieved. No `post_exit.jsonl` retrieved.

| Session | Time (UTC) | SSH result |
|---|---|---|
| Audit 1 | 2026-04-27 ~18:42 | Timeout (10s) |
| Audit 2 | 2026-04-28 00:10 | Timeout (15s) |
| Scout   | 2026-04-28 00:42 | Port REFUSED |
| Audit 3 | 2026-04-28 04:44 | EAGAIN (port 22 closed) |
| Audit 4 | 2026-04-28 06:18 | EAGAIN |
| Audit 5 | 2026-04-28 12:08 | ssh binary not found; HTTP blocked |
| Scout 2 | 2026-04-28 12:32 | Same; partial data from git commits |
| Audit 7 | 2026-04-29 00:37 | paramiko installed; TCP EAGAIN; HTTP blocked |
| Audit 8 | 2026-04-29 06:16 | paramiko TCP EAGAIN; ports 80+443 "Host not in allowlist" |
| Scout 9 | 2026-04-29 12:11 | Same; commit-embedded analysis only |
| **Audit 10** | **2026-04-29 12:17** | **ssh binary not found; HTTP proxy blocked** |

---

## Partial Data — Bankroll Snapshot (git-committed)

`logs/bankroll.json` last pushed at commit `431a762` → **2026-04-29 04:59:11 UTC** (~7h old as of this report).

| Field | Value |
|---|---|
| capital | $34.28 |
| daily_start_capital | $15.95 |
| total_trades | 2025 |
| total_pnl | +$99.30 |
| consecutive_wins | 0 |

No newer bankroll snapshot committed since `431a762`.

---

## 6h Summary
n_trades=0 (no trades.jsonl) | WR=N/A | E=N/A | Kelly=N/A
0.80–0.84: n=0 WR=N/A E=N/A
0.84–0.88: n=0 WR=N/A E=N/A

INSUFFICIENT_DATA — threshold for ask/imbalance changes: n>=20 in 6h window. Not met.

## Loss Signatures
None in window — no data retrievable.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

## Hour Analysis (all-time, 0.80–0.88)
No raw trades.jsonl — using commit-embedded data from prior sessions.

| H | n | WR | PF | status |
|---|---|----|----|--------|
| 02 | 24 | 50% | 0.19 | **BLOCKED** (commit `95a05da`) |
| 03 | 10 | 14% | — | **BLOCKED** (commit `0686d29`, n<100 user override) |
| 05 | 55 | 58% | 0.21 | **BLOCKED** (commit `95a05da`) |
| 21 | 46 | 65% | 1.19 | active (unblocked `0ddb49e`) |
| all other | — | — | — | collecting data |

No hour has n>=100 with PF<0.80 → no new blocks warranted by audit rules.
No blocked hour has n>=100 with PF>=0.90 → no unblocks warranted by audit rules.

## Changes Since Last Audit (06:16 UTC → 12:17 UTC, Apr 29)

| Commit | Change | Audit Verdict |
|---|---|---|
| `9d974e2` | BC depth_ratio discriminator (n=70): depth<0.60→exit, >0.77→wick=20s; bypass 15s→10s | Hypothesis mode, sub-bucket n<100, monitor |
| `d3ac233` | BC wick 10s→15s for fast/mid; SNAP gate requires both snap_60<0 AND snap_30<0 | SNAP shadow-only (n=6), too early to activate |
| `947306c` | `term_spot_delta_5s` added to logging; scout report | Schema addition, no execution effect |

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (TCP/SSH blocked, HTTP proxy blocks IP egress).
n=0 in 6h window (threshold: n>=20 for ask/imbalance changes).
n<100 per blocked hour (threshold: n>=100 per hour for audit-driven block/unblock decisions).

## Current Parameters (confirmed from main.py)
| Parameter | Value | Source |
|---|---|---|
| min_ask | 0.80 | main.py:1750 |
| max_ask | 0.88 | main.py:1749 |
| min_imbalance | 0.20 | main.py:1804 |
| blocked_hours | {2, 3, 5} | main.py:1723 |
| stop_loss | -0.15 | main.py:1936 (`ask * 0.85`) |
| stake | 4.00 | CONFIG |

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.88,
  "min_imbalance": 0.20,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": [2, 3, 5]
}
```

**No parameter changes applied.** All values remain at current code state.
Reason: zero trade data retrieved — evidence base for modification: none.
All thresholds (n>=20 for 6h ask/imbalance, n>=100 per hour for blocks) unmet.

---

## Infrastructure Alert — Persistent (10 sessions)

The sandbox has no SSH binary and its HTTP proxy blocks arbitrary-IP egress.
This is a hard constraint — the audit cannot retrieve live logs without a data path change.
**~1,800+ trade records** estimated lost to analysis since first failure (~2 days ago).

### Remediation Options (ranked by effort)

**Option A — Push logs to GitHub (recommended, ~5 min setup):**
```bash
# on VPS: /etc/cron.d/push-logs
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json && \
  git commit -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N
```
Audit agent reads `logs/live_trades_recent.jsonl` from repo — no SSH needed.

**Option B — Domain-name HTTPS endpoint:**
VPS nginx reverse-proxy on a registered domain (not raw IP). Proxy may allow domain names.

**Option C — Console access (verify sshd state):**
Access VPS via provider web console, verify sshd running, check port/firewall config.

**Option D — Alternative port for SFTP/SCP:**
If sshd moved to non-standard port (e.g. 2222), test TCP reachability first.
