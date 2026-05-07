# Quantitative Audit — 2026-05-07 00:12 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (36th consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 to 85.137.174.86 | `Connection timed out` — egress blocked from sandbox network |
| paramiko (Python SSH) | `TimeoutError: timed out` — same root cause, TCP blocked |
| logs/live_trades_recent.jsonl (git) | Absent — cron sync not deployed |
| local logs/trades.jsonl | Absent (not git-tracked) |
| local logs/post_exit.jsonl | Absent |

> SSH binary absent from sandbox. Paramiko installed and attempted — TCP port 22 egress blocked at network level.
> No trade data is accessible. All analysis sections reflect INSUFFICIENT_DATA.

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A
0.80–0.84 bucket: n=0 WR=N/A E=N/A
0.84–0.92 bucket: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None determinable — no data retrievable.

## OB Imbalance
No data available.

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.80–0.92)
No trades.jsonl accessible. n=0 per hour — no block/unblock decisions possible (threshold: n≥100/hour).

| H | n | WR | PF | status |
|---|---|---|---|---|
| 00–23 | 0 | N/A | N/A | collecting data |

Current `bond_blocked_hours_utc` (config.py:151): `[]` (all hours unblocked)
Block threshold: n≥100 per hour AND PF<0.80.
Unblock threshold: n≥100 per hour AND PF≥0.90.
Cannot evaluate without data. No change to blocked_hours.

---

## Flags
**INSUFFICIENT_DATA** — SSH blocked from sandbox (36th consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour all-time in this session (threshold: n≥100/hour for block/unblock decisions).

---

## Deployed Parameter State (from main.py + config.py)

| Parameter | Deployed value | Location |
|---|---|---|
| ask floor | 0.80 | main.py:2256 |
| max_ask | 0.92 | main.py:2254 (extended from 0.88 on 2026-04-30) |
| min_imbalance | 0.30 | main.py:2313 — UP:[0.3,0.7), DOWN:[0.3,0.655) |
| bond_blocked_hours_utc | [] (all hours unblocked) | config.py:151 |
| stop_loss | ask×0.85 (−15%) | main.py (BOND_CATASTROPHIC) |
| base_stake | $30.00 | config.py:27 (raised 20→30 on 2026-05-06) |
| scaled_stake | $30.00 (heat-check disabled) | config.py:28 |
| snap60 floor (UP) | 12% (ETH: 15%; 12:30–13:30: 25%) | main.py:2532–2537 |
| snap60 floor (DOWN) | 13% (ETH: 15%; 12:30–13:30: 25%) | main.py:2532–2537 |
| snap60 early-window floor | 30% (ask<0.80) | main.py:2560 |
| snap60 overbought cap | 120% (skip) | main.py:2578 |
| tok_d60 reversal gate | <−5% blocks entry | main.py:2552 |

## Recent Commits (since last audit)

| Commit | Change |
|---|---|
| `2b8fdf7` | H21 TERMINAL: tighten rem cap to 60s + gate tok_d30>=35 |
| `c666111` | Fix base_stake $30 not applied to BOND orders (hardcoded $20 cap in manager.py) |
| `dbe9f07` | Raise base_stake $20→$30; floor equity tiers at base_stake |
| `f96e37a` | Add equity-pct stake tiers: snap60≥50%→18%, snap60≥20%+rem≥75s→14% of equity |
| `1b68cf3` | Raise ETH snap60 floor to 15% (both dirs) |
| `455f1ec` | Raise snap30 floor 10%→10.5% |

## Bankroll State (git-tracked bankroll.json — stale ~5 days)
capital=$37.32 | total_trades=2605 | total_pnl=+$87.87 | saved_ts=1746160000 (~2026-05-02 04:26 UTC)

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.92,
  "min_imbalance": 0.30,
  "stake": 30.00,
  "stop_loss": -0.15,
  "blocked_hours": []
}
```

**No parameter changes applied.**
Reason: zero trade data retrieved from VPS — evidence base for any modification: none.
INSUFFICIENT_DATA enforced per anti-sycophancy rules.

---

## Infrastructure Alert — Critical (36 consecutive sessions)

**Root cause**: Sandbox network blocks outbound TCP port 22 (confirmed: paramiko times out on TCP connect to 85.137.174.86:22). SSH binary also absent from sandbox.

**Required action — run ONE of these on the VPS to unblock all future audits:**

**Option A: Manual one-time sync (30 seconds)**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Option B: Deploy cron sync (every 30 minutes, permanent fix)**
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

Without log data, audit is structurally blocked for the 36th consecutive session.
The cron above is a 30-second fix that unblocks all future audits permanently.
