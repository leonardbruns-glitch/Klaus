# Quantitative Audit — 2026-05-03 00:10 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (19th consecutive session)**

| Method | Result |
|---|---|
| SSH (port 22) | Binary absent from sandbox; command not found (exit 127) |
| HTTP/HTTPS | TCP open but Cloudflare WAF: "Host not in allowlist" |
| paramiko / fabric | Not installed |
| logs/live_trades_recent.jsonl (git) | File absent — cron sync never deployed |

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A
0.75–0.84 bucket: n=0 WR=N/A E=N/A
0.84–0.92 bucket: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None determinable — no data retrievable.

## OB Imbalance
No data available. Current gate: _term_imb < 0.20 → skip (main.py:2100).
Gate evidence from prior session: imb≥0.20 PF=1.27 Net=+$24.18 (n=234) vs imb≥0.10 PF=1.01 Net=+$1.67 (n=300).

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.75–0.92)
No trades.jsonl accessible. n<100 per hour confirmed → no block/unblock decisions possible.
All hours unblocked per commit f91ed67 (2026-05-02 ~12:XX UTC — after Audit 18).

| H  | n   | WR  | PF   | status |
|----|-----|-----|------|--------|
| 00-23 | unk | unk | unk | collecting data (all unblocked 2026-05-02 per f91ed67) |

Note: Re-block threshold is n≥100 per hour at PF<0.80. Current terminal-era data
volume is unknown but estimated ~250–350 trades/hour across all hours combined
since unblock, which is not per-hour. No block decision can be made.

---

## Changes Since Audit 18 (2026-05-02 12:21 UTC)

| Commit | Change | Notes |
|---|---|---|
| f91ed67 | Unblock all hours | Accumulate fresh terminal-era data |
| 4ed1b99 | Ask floor 0.70→0.75; BOND_TRAIL_TP at +10% peak | Raise floor from weak 0.70–0.74 zone; trailing stop added |
| f874c1d | tok30 dead zone [18, 26%) gate | Dead-drift zone pre-entry |
| 4d0f416 | Binance slow-bleed regime + cw=3 pause | Added then reverted |
| e3f7f7e | Revert cw=3 pause gate | User-undone |
| dd3cd5c | NEG_RISK_LOCK fix | 17/21 stuck trades May 2 caused by matched-orders timing |
| 5b0f53a | EXTERNALLY_SOLD exit_price correction | _capture_resolution overwrites at PM settlement |
| 550202d | 5s intra-hold bid trajectory snapshots to traj_snaps.jsonl | Data collection for future analysis |

## Bankroll Snapshot (bankroll.json saved ~2026-05-02 06:13 UTC)

| Field | Value |
|---|---|
| capital | $37.32 |
| daily_start_capital | $15.95 (stale — bankroll reset to $24 later on May 2) |
| total_trades | 2,605 |
| total_pnl | +$87.87 |
| stake | $10.00 (config.py) |

Note: state_log records bankroll reset to $24.00 on 2026-05-02 to match PM balance after
BOND_EXPIRED_UNSOLD fake-win correction (-$37.13). The $37.32 in bankroll.json predates
the correction. Actual live capital is approximately $24.00 + subsequent session P&L.

---

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (19th consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour (threshold: n≥100/hour for block/unblock decisions).

---

## Current Parameters (confirmed from main.py)

| Parameter | Value | Line | Notes |
|---|---|---|---|
| min_ask | 0.75 | main.py:2046 | Raised 0.70→0.75 commit 4ed1b99 (2026-05-02) |
| max_ask | 0.92 | main.py:2045 | Extended from 0.88 on 2026-04-30 |
| min_imbalance | 0.20 | main.py:2100 | Unchanged; PF=1.27 (n=234) vs 0.10 gate PF=1.01 |
| blocked_hours | set() | main.py:1964 comment | All unblocked per f91ed67 (2026-05-02) |
| stop_loss | ask×0.85 (−15%) | main.py | BC disabled; PAE gate active |
| stake | $10.00 | config.py | Raised from $4 user directive 2026-05-01 |
| max_open_positions | 2 | config.py | Unchanged |
| entry_window | 25–90s remaining | main.py | Unchanged |
| OB stale gate | ≥3s | main.py | Unchanged |
| snap60 gate | [12%, 120%) | main.py | <12%: WR=55% net-neg; ≥120%: WR=62.5% net -$8.18 |
| snap30 gate | [10%, 120%) | main.py | Unified gate |
| tok30 dead zone | skip [18%, 26%) | main.py:f874c1d | Dead-drift zone |
| BOND_TRAIL_TP | +10% peak trailing | main.py | Added 4ed1b99 |

**Note:** Audit prompt stated min_ask=0.80, max_ask=0.88, blocked_hours=[] — outdated.
Actual code values above supersede the prompt's stated defaults.

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.75,
  "max_ask": 0.92,
  "min_imbalance": 0.20,
  "stake": 10.00,
  "stop_loss": -0.15,
  "blocked_hours": []
}
```

**No parameter changes applied.** Values reflect actual current code state.
Reason: zero trade data retrieved from VPS — evidence base for any modification: none.
INSUFFICIENT_DATA enforced per anti-sycophancy rules.

---

## Infrastructure Alert — Persistent (19 sessions)

The sandbox has no SSH binary, port 22 is closed on VPS, and HTTP/HTTPS are CF-WAF blocked.
Estimated **~12,000–16,000+ trade records** accumulated and unanalyzable since first SSH failure (~7 days ago).

### Required action (unchanged from Audits 11–18):
```bash
# On VPS: /etc/cron.d/push-logs (install ONCE)
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N
```
Audit agent reads `logs/live_trades_recent.jsonl` from GitHub — no SSH required.

**Without this cron, the quantitative auditor cannot function. Every audit is a no-op.**
**19 consecutive no-op sessions.**
