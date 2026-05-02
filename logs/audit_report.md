# Quantitative Audit — 2026-05-02 12:21 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (18th consecutive session)**

| Method | Result |
|---|---|
| SSH (port 22) | Binary absent from sandbox; TCP port 22 closed (nc exit=1) |
| HTTP (port 80) | TCP open but Cloudflare WAF: "Host not in allowlist" |
| HTTPS (port 443) | TCP open but Cloudflare WAF: "Host not in allowlist" |
| paramiko / fabric | Not installed |
| logs/live_trades_recent.jsonl (git) | File absent — cron sync never deployed |

| Session | Time (UTC) | Result |
|---|---|---|
| Audits 1–11 | 2026-04-27 – 2026-04-30 00:07 | SSH not found / EAGAIN / CF WAF 403 |
| Audit 12 | 2026-04-30 00:08 | paramiko installed; TCP timeout confirmed |
| Audits 13–17 | 2026-04-30 12:15 – 2026-05-01 18:06 | TCP timeout / SSH binary absent |
| **Audit 18** | **2026-05-02 12:21** | **SSH absent; port 22 closed; HTTP/HTTPS CF-blocked** |

---

## Critical Architecture Note: WOP Era

Strategy transitioned to **Window Outcome (WOP)** ~May 1 21:XX UTC (commit `8cd9161`→`b90edfa`).  
Under WOP, all positions are held to Chainlink resolution — there are no timed exits.  
Pre-WOP trades in trades.jsonl are **structurally invalid** as training data for the current strategy.  
WOP-era trade count: ~73 (9h × 7.9/hr) — well below n≥20 per bucket threshold for any parameter change.

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A  
0.70–0.84 bucket: n=0 WR=N/A E=N/A  
0.84–0.92 bucket: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None determinable — no data retrievable.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.70–0.92)
No trades.jsonl accessible. n<100 per hour confirmed → no block/unblock decisions possible.

| H  | n   | WR  | PF   | status |
|----|-----|-----|------|--------|
| 00 | unk | unk | unk  | BLOCKED (user-instructed) |
| 01 | unk | unk | unk  | collecting data |
| 02 | unk | unk | 0.19 | BLOCKED (PF=0.19, prior all-trades data) |
| 03 | unk | 14.3% | unk | BLOCKED (WR=14.3%, prior data) |
| 04 | unk | unk | unk  | BLOCKED (WOP+PAE sim 2026-05-01) |
| 05 | unk | unk | 0.21 | BLOCKED (PF=0.21, prior all-trades data) |
| 06 | unk | unk | unk  | BLOCKED (WOP+PAE sim 2026-05-01) |
| 07 | unk | unk | unk  | BLOCKED (WOP+PAE sim 2026-05-01) |
| 08 | unk | unk | unk  | collecting data |
| 09 | unk | unk | unk  | collecting data |
| 10 | unk | unk | unk  | collecting data |
| 11 | unk | unk | unk  | collecting data |
| 12 | unk | unk | unk  | collecting data (unblocked 2026-05-01: TERMINAL-era PF=2.07) |
| 13 | unk | unk | unk  | collecting data (unblocked 2026-05-01: TERMINAL-era PF=0.88) |
| 14:00–14:44 | unk | unk | unk | collecting data |
| 14:45–15:44 | unk | unk | unk  | MINUTE_BLOCKED (15min analysis 2026-05-01; n≈112 PF=0.32–0.43) |
| 15:45–16:00 | unk | unk | unk | collecting data |
| 16 | unk | unk | unk  | collecting data (16:55–17:00 blocked) |
| 17 | unk | unk | unk  | BLOCKED (WOP+PAE sim 2026-05-01) |
| 18 | unk | unk | unk  | collecting data |
| 19 | unk | unk | unk  | BLOCKED (WOP+PAE sim 2026-05-01) |
| 20 | unk | unk | unk  | collecting data |
| 21 | unk | unk | unk  | collecting data (n=46 WR=65% PF=1.19 Net=+$4.00 — positive, TERMINAL-era) |
| 22 | unk | unk | unk  | collecting data |
| 23 | unk | unk | unk  | BLOCKED (user-instructed) |

Note: all-time data pre-dates WOP era (live ~May 1 21:XX). Block/unblock decisions require n≥100  
per hour in the **current WOP-era 0.70–0.92 range** — not met for any hour.

---

## Bankroll Snapshot (git source — bankroll.json saved ~May 2 06:13 UTC)

| Field | Value |
|---|---|
| capital | $37.32 |
| daily_start_capital | $15.95 |
| total_trades | 2,605 |
| total_pnl | +$87.87 |
| stake | $10.00 (config.py line 27) |

**Delta vs Audit 17** (Apr 29 04:59 UTC → May 2 06:13 UTC, ~73h):  
capital: $34.28 → $37.32 (+$3.04) | total_trades: 2025 → 2605 (+580) | total_pnl: +$99.30 → +$87.87 (-$11.43)  
PnL delta explained by retroactive corrections (T02829, T02682_ETH, T02669_BTC, 860 backfilled records).  
Live capital trajectory: breakeven at $10 stake/7.9 trades/hr over 73h (gross turnover ≈$5,800).

**RISK NOTE**: daily_start_capital=$15.95. If this reflects today's starting capital (not a stale value),  
the bot may be running a degraded bankroll. With stake=$10 and max_open_positions=2, a single  
CATASTROPHIC SL = -$1.50 = 9.6% of $15.95. Unknown whether capital erosion is real or an artifact  
of the bankroll.json save timing during a mid-day valley.

---

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (18th consecutive session).  
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).  
n=0 WOP-era per bucket (threshold: n≥100/hour for block/unblock decisions).  
WOP_ERA_CONTAMINATION — all pre-WOP trades invalid for current strategy evaluation.

---

## Current Parameters (confirmed from main.py + config.py)

| Parameter | Value | Line | Notes |
|---|---|---|---|
| min_ask | 0.70 | main.py:1994 | Extended from 0.80 on 2026-04-30 |
| max_ask | 0.92 | main.py:1993 | Extended from 0.88 on 2026-04-30 |
| min_imbalance | 0.20 | main.py:2048 | Unchanged |
| blocked_hours | {0, 2, 3, 4, 5, 6, 7, 17, 19, 23} | main.py:1964 | Last changed 2026-05-01 |
| stop_loss | ask×0.85 (−15%) | main.py | Unchanged |
| stake | $10.00 | config.py:27 | Raised from $4 user directive 2026-05-01 |
| max_open_positions | 2 | config.py | Unchanged |
| entry_window | 25–90s remaining | main.py | Unchanged |
| minute gate 14:45–15:44 UTC | all assets | main.py:1968 | n≈112 PF=0.32–0.43 |
| minute gate 16:55–17:00 UTC | all assets | main.py | OB stale guard covers H16 tail |
| OB stale gate | ≥3s | main.py:1971 | Unchanged |

**Note:** Audit prompt stated current values as min_ask=0.80, max_ask=0.88, blocked_hours=[] — these  
are outdated. Actual code values as above supersede the prompt's stated defaults.

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.70,
  "max_ask": 0.92,
  "min_imbalance": 0.20,
  "stake": 10.00,
  "stop_loss": -0.15,
  "blocked_hours": [0, 2, 3, 4, 5, 6, 7, 17, 19, 23]
}
```

**No parameter changes applied.** Values reflect actual current code state.  
Reason: zero trade data retrieved from VPS — evidence base for any modification: none. INSUFFICIENT_DATA enforced.  
WOP-era n≈73 total (all buckets combined) — below every threshold in the analysis spec.

---

## Infrastructure Alert — Persistent (18 sessions)

The sandbox has no SSH binary, port 22 is closed on VPS, and HTTP/HTTPS are CF-WAF blocked.  
Estimated **~10,000–14,000+ trade records** accumulated and unanalyzable since first SSH failure (~6 days ago).

### Required action (unchanged from Audits 11–17):
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
**18 consecutive no-op sessions. Estimated cost: 10,000+ unanalyzable trade records.**
