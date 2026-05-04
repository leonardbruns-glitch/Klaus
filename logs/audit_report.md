# Quantitative Audit — 2026-05-04 12:17 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (27th consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 (native) | TCP timeout at 85.137.174.86:22 (20s ConnectTimeout) |
| HTTP/HTTPS port 443 | Cloudflare WAF blocks all requests |
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
Current gate: `if _term_imb < 0.20: continue` (main.py:2268); ETH override: `if _term_imb < 0.30` (main.py:2653).

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.80–0.88)
No trades.jsonl accessible. n=0 per hour — no block/unblock decisions possible (threshold: n≥100/hour).

| H | n | WR | PF | status |
|---|---|---|---|---|
| 00–23 | 0 | N/A | N/A | collecting data |

Current `bond_blocked_hours_utc` (config.py:157): `[0,2,3,4,5,6,7,17,19,23]`
Block threshold: n≥100 per hour AND PF<0.80.
Unblock threshold: n≥100 per hour AND PF≥0.90.
Cannot evaluate without data. No change to blocked_hours.

---

## Flags
**INSUFFICIENT_DATA** — VPS unreachable from sandbox (27th consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour all-time in this session (threshold: n≥100/hour for block/unblock decisions).

---

## Deployed Parameter State (from main.py / config.py)

| Parameter | Deployed value | Location |
|---|---|---|
| ask floor (elapsed≥120s, late-window) | 0.80 | main.py:2213 |
| ask floor (elapsed<120s, early-window) | 0.52 | main.py:2213 |
| max_ask | 0.92 | main.py:2211 (extended from 0.88, 2026-04-30) |
| min_imbalance (global) | 0.20 | main.py:2268 |
| min_imbalance (ETH) | 0.30 | main.py:2653 |
| bond_blocked_hours_utc | {0,2,3,4,5,6,7,17,19,23} | config.py:157 |
| stop_loss | ask×0.85 (−15%) | BOND_CATASTROPHIC, 8s wick filter |
| base_stake | $4.00 | config.py:27 (reduced from $10, 2026-05-04) |
| scaled_stake | $4.00 | config.py:34 (flat, heat-check disabled) |

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.92,
  "min_imbalance": 0.20,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": [0, 2, 3, 4, 5, 6, 7, 17, 19, 23]
}
```

**No parameter changes applied.**
Reason: zero trade data retrieved from VPS — evidence base for any modification: none.
INSUFFICIENT_DATA enforced per anti-sycophancy rules.

---

## Bankroll State (from git-tracked bankroll.json)
capital=$37.32 | total_trades=2605 | total_pnl=+$87.87 | saved_ts=1746160000 (2026-05-02 ~04:26 UTC)

Note: bankroll snapshot is ~56h stale. Estimated ~445 additional trades since snapshot (7.9/hr × 56h).

---

## Infrastructure Alert — Critical (27 consecutive sessions)

SSH port 22 is actively unreachable: TCP timeout at 15–20s. Port 443 blocked by Cloudflare WAF.

**Estimated WOP-era (May 1 21:00+) trades inaccessible:** ~530+ and growing (~7.9/hr × 67h).

All gate-relevant changes deployed since last data-backed audit remain unverifiable:
- Early-window entries (ask 0.52, elapsed<120s) — post-fix WR unknown
- T-50s unconditional exit for early entries — effect unknown
- Regime cooldown (T1≤-$7→5m) — trigger frequency unknown
- Per-asset sub-pattern gates (BTC daccel, ETH tok_d30, SOL elapsed) — WOP-era WR unknown
- 4-layer pre-entry regime gate system — effectiveness unknown
- Base stake reduction $10→$4 (2026-05-04) — impact on capital curve unknown

### Required action — push logs ONCE from VPS:
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

### Or install cron (every 30 minutes):
```bash
cat > /etc/cron.d/push-logs << 'EOF'
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N 2>/dev/null
EOF
chmod 644 /etc/cron.d/push-logs
```
