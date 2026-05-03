# Quantitative Audit — 2026-05-03 18:08 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (23rd consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 | SSH binary absent in sandbox |
| HTTP/HTTPS port 443 | TCP open; Cloudflare WAF blocks all requests |
| logs/live_trades_recent.jsonl (git) | File absent — cron sync not deployed |
| local logs/trades.jsonl | Absent (not tracked in git) |

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A
0.80–0.84 bucket: n=0 WR=N/A E=N/A
0.84–0.88 bucket: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None determinable — no data retrievable.

## OB Imbalance
No data available.
Current gate: `if _term_imb < 0.20: continue` (main.py:2178).

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.80–0.88)
No trades.jsonl accessible. n=0 per hour — no block/unblock decisions possible (threshold: n≥100/hour).

| H | n | WR | PF | status |
|---|---|---|---|---|
| 00–23 | 0 | N/A | N/A | collecting data (bond_blocked_hours_utc={0,2,3,4,5,6,7,17,19,23} active) |

Re-block threshold: n≥100 per hour AND PF<0.80.
Unblock threshold: n≥100 per hour AND PF≥0.90.
Cannot evaluate without data. No change to blocked_hours.

---

## Flags
**INSUFFICIENT_DATA** — VPS unreachable from sandbox (23rd consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour all-time in this session (threshold: n≥100/hour for block/unblock decisions).

---

## Code Changes Since Last Audit (14:00 UTC today)

| Commit | Change |
|---|---|
| 436901a | Logging fix: persist bond_has_hist/accel_sustained/outcome_direction across restarts. Missing from _term_fields → restart positions logged False as stub default. Gates unaffected; logging artifact only. |

**No gate-relevant code changes since last audit.**

---

## Current Parameters (confirmed from code)

| Parameter | Value | Location | Notes |
|---|---|---|---|
| min_ask | 0.80 | main.py:2124 | Raised 0.75→0.80 commit 627c5f3 |
| max_ask | 0.92 | main.py:2123 | Extended 0.88→0.92 commit 2026-04-30 |
| min_imbalance | 0.20 | main.py:2178 | PF=1.27 (n=234); unchanged |
| bond_blocked_hours | {0,2,3,4,5,6,7,17,19,23} | config.py:157 | Re-enabled commit 627c5f3 |
| stop_loss | ask×0.85 (−15%) | BOND_CATASTROPHIC | 8s wick filter; autonomous change prohibited |
| stake | $10.00 flat | config.py:27 | Per user directive 2026-05-01 |
| max_open_positions | 2 | config.py | Unchanged |
| entry_window | 25–90s remaining | main.py:2093 | Unchanged |
| profit_target | min(entry×1.10, 0.99) | main.py | Changed commit 36e59f0 (was fixed 0.99) |

## Bankroll State (from git-tracked bankroll.json)
capital=$37.32 | total_trades=2605 | total_pnl=+$87.87 | saved_ts=1746160000

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.92,
  "min_imbalance": 0.20,
  "stake": 10.00,
  "stop_loss": -0.15,
  "blocked_hours": [0, 2, 3, 4, 5, 6, 7, 17, 19, 23]
}
```

**No parameter changes applied.**
Reason: zero trade data retrieved from VPS — evidence base for any modification: none.
INSUFFICIENT_DATA enforced per anti-sycophancy rules.

---

## Infrastructure Alert — Critical (23 consecutive sessions)

SSH port 22 is actively CLOSED (SSH binary absent in sandbox).
Port 443 open but Cloudflare WAF blocks all HTTP requests.

**Estimated ~14,000–19,000+ trade records accumulated and unanalyzable.**
WOP-era (post May 1 21:00 UTC) estimated: ~7.9/hr × ~69h ≈ **~545 WOP-era trades** completely inaccessible.

The TP threshold change (entry×1.10 vs fixed 0.99), cooldown persistence, and restart field persistence fix are all unverifiable without live data.

### Required action — push logs once from VPS:
```bash
# Run ONCE on VPS at root@85.137.174.86
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json logs/traj_snaps.jsonl
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

### Or install cron (every 30 minutes):
```bash
cat > /etc/cron.d/push-logs << 'EOF'
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json logs/traj_snaps.jsonl && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N 2>/dev/null
EOF
chmod 644 /etc/cron.d/push-logs
```
