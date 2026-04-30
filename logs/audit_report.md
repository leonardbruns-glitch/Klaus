# Quantitative Audit — 2026-04-30 00:07 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (11th consecutive session)**

SSH binary not installed in sandbox. TCP port 22 returns EAGAIN (errno=11, filtered).
TCP 443/80 reach the VPS but return HTTP 403 (Cloudflare WAF).
No `trades.jsonl` retrieved. No `post_exit.jsonl` retrieved.

| Session | Time (UTC) | SSH result |
|---|---|---|
| Audits 1–5 | 2026-04-27 – 2026-04-28 | Timeout / EAGAIN |
| Scout 2 | 2026-04-28 12:32 | Same; partial data from git commits |
| Audits 6–10 | 2026-04-28 – 2026-04-29 12:17 | EAGAIN / ssh not found |
| **Audit 11** | **2026-04-30 00:07** | **ssh not found; HTTP 403 (CF WAF)** |

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
No raw trades.jsonl — using commit-embedded data from prior sessions.

| H  | n   | WR    | PF   | status |
|----|-----|-------|------|--------|
| 02 | 24  | 50%   | 0.19 | **BLOCKED** (PF=0.19, user override n<100) |
| 03 | 10  | 14%   | —    | **BLOCKED** (WR=14.3%, user override n<100) |
| 05 | 55  | 58%   | 0.21 | **BLOCKED** (PF=0.21, user override n<100) |
| 06 | 17  | 29%   | —    | **SOL ONLY BLOCKED** (WR=29%; CLOB 5-share min issue) |
| 21 | 46  | 65%   | 1.19 | active (unblocked `0ddb49e`) |
| all other | — | — | — | collecting data |

No hour has n≥100 with PF<0.80 → no new blocks warranted by audit rules.
No blocked hour has n≥100 with PF≥0.90 → no unblocks warranted by audit rules.

---

## Changes Since Last Audit (12:17 UTC Apr 29 → 00:07 UTC Apr 30)

| Commit | Change | Audit Verdict |
|---|---|---|
| `aec9ae9` | BOND_CATASTROPHIC SL disabled (_sl_threshold -1.0→-2.0); -2.0 unreachable | 85% FP confirmed (n=127); correct move |
| `f2866fd` | snap60 pre-entry gate: skip if term_pre_snap_60s < 0.0 | WR 32.5% vs 91.9% (commits); strong signal but n not disclosed |
| `1912b74` | TIME_EXIT moved T-2s→T-4s | Hypothesis mode; monitor via DEADLINE WR parity |
| `5d0c712` | Cancel AttributeError fix (cancel→cancel_orders) | Critical bug fix; was corrupting exit_price in every SELL cancel-race |
| `268fdee` | BC disable gap -1.0→-2.0; truly disables bypass path | T02682_ETH (-$4.90 FP catch) confirmed necessity |
| `35bc218` | PROFIT_TARGET: sell when bid ≥ entry×1.12 | 2d sim net +$7.26; n=255; user-authorised Tier 2 |
| `b762f29` | Ask-history gate: skip if term_ask_stale_s ≥ 999 | T02684 (-$1.52) + T02685 (-$4.27) catch; correct |
| `16193c3` | 3 snap gates: snap60<12%, snap30>300%, snap60>150%+fresh | 5h n=54; sub-n=100 per bucket; user-authorised Tier 2 |
| `7eab20a` | snap60 gate 5%→12%; stake cap $4→$10 | 2d sim n=255; stake scale is significant risk increase |
| `b2728d9` | snap60 spike stale 3s→5s | n=1 trigger (T02722 BTC -$2.43); empirically correct |
| `55ebdad` | SOL spread ≤3% gate | n=26 spread 1-2%, dir_acc=92%; user-authorised Tier 2 |
| `7eab20a` | PROFIT_TARGET entry×1.12 | 2d sim +$21.60 from converting losers; n=255; Tier 2 |

---

## Bankroll Snapshot (git-committed, 2026-04-29 04:59 UTC — ~19h old)

| Field | Value |
|---|---|
| capital | $34.28 |
| daily_start_capital | $15.95 |
| total_trades | 2025 |
| total_pnl | +$99.30 |
| consecutive_wins | 0 |

State log references $45.91 at ~16:XX UTC Apr 29 (ruin floor override) and $32.45 at ~19:XX UTC (stake cap decision). Implies ~$13 drawdown during the afternoon session 16:00–19:30 UTC Apr 29 before bankroll.json was last committed.

---

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (TCP/SSH blocked, HTTP 403 Cloudflare WAF).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n<100 per blocked hour (threshold: n≥100 for audit-driven block/unblock decisions).

**RISK FLAG — Stake cap raised $4→$10 with capital at $32.45.**
Worst-case 3-asset simultaneous entry = -$30 (92% drawdown from $32.45).
Per CLAUDE.md: weekly floor $7.50, ruin floor $5. User explicitly overrode. Logged; not autonomous.

---

## Current Parameters (confirmed from main.py)
| Parameter | Value | Source |
|---|---|---|
| min_ask | 0.80 | main.py:1770 |
| max_ask | 0.88 | main.py:1769 |
| min_imbalance | 0.20 | main.py:1824 |
| blocked_hours | {2, 3, 5} | main.py:1740 |
| stop_loss (BC) | -2.0 (disabled) | main.py:809 |
| stake | $10.00 | config.py:27 |

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.88,
  "min_imbalance": 0.20,
  "stake": 10.00,
  "stop_loss": -0.15,
  "blocked_hours": [2, 3, 5]
}
```

**No parameter changes applied.** All values remain at current code state.
Reason: zero trade data retrieved — evidence base for modification: none.
All thresholds (n≥20 for 6h ask/imbalance, n≥100 per hour for blocks) unmet.

---

## Infrastructure Alert — Persistent (11 sessions)

The sandbox has no SSH binary. HTTP/HTTPS reach the IP but Cloudflare returns 403 on all endpoints.
**~2,000+ trade records** estimated lost to analysis since first failure (~3 days ago).

### Recommended immediate action (Option A — git log sync):
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
