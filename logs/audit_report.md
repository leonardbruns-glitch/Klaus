# Quantitative Audit — 2026-05-05 00:20 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (29th consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 (native binary) | SSH binary absent from sandbox |
| SSH port 22 (paramiko/asyncssh) | Libraries absent; port 22 TCP-closed at 85.137.174.86 |
| HTTP port 80 | Open but blocked by curl allowlist |
| HTTPS port 443 | Open but blocked by curl allowlist |
| logs/live_trades_recent.jsonl (git) | File absent — cron sync not deployed |
| local logs/trades.jsonl | Absent (not tracked in git) |

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
Current gate (main.py:2297): `if not (0.30 <= _term_imb < 0.70): continue`
Comment cites: COR=75% n=75 in [0.3,0.7); COR=58% below 0.30; COR=58% at ≥0.70.

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.80–0.88)
No trades.jsonl accessible. n=0 per hour — no block/unblock decisions possible (threshold: n≥100/hour).

| H | n | WR | PF | status |
|---|---|---|---|---|
| 00–23 | 0 | N/A | N/A | collecting data |

Current `bond_blocked_hours_utc` (config.py:157): `[]` (all hours unblocked — commit 51e590f)
Block threshold: n≥100 per hour AND PF<0.80.
Unblock threshold: n≥100 per hour AND PF≥0.90.
Cannot evaluate without data. No change to blocked_hours.

---

## Flags
**INSUFFICIENT_DATA** — VPS unreachable from sandbox (29th consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour all-time in this session (threshold: n≥100/hour for block/unblock decisions).

---

## Changes Since Last Audit (20260504-1829 / commit fc85b70)

| Commit | Change |
|---|---|
| `00cbf96` | BOND_DEADLINE T-5s → T-3s (align with TIME_EXIT) |
| `8a40459` | BOND_TIME_EXIT T-30s → T-3s (unconditional exit at T−3) |
| `cc223be` | Disable BOND PAE entirely |
| `5600f5b` | Disable early window entries — TERMINAL only; ask floor fixed at 0.80 |
| `c6e938d` | INVERTED_TP threshold 75%→50% (entry_price × 1.50) |
| `95fa943` | Inversion early-window only; late/TERMINAL buys as signalled |
| `51e590f` | Unblock all trade hours (bond_blocked_hours_utc cleared to []) |
| `291eadb` | Add INVERTED_TP: exit at +75% profit on inverted entries |
| `eed10b0` | Time exit at T-30s: re-enable precise timer, unconditional |
| `462e941` | Invert TERMINAL direction: buy opposite side when signal fires |
| `b38e6c4` | Disable 15m windows — 5m only |
| `6b3cba7` | Fix entered_correctly inverted for YES DOWN trades |
| `36b6cda` | Re-enable YES DOWN with snap60 gate active; fix G1 gate direction |
| `7f64d20` | Re-enable 15m windows with scaled entry timing |
| `18e2433` | Bootstrap 1m close buffer from Binance REST on startup for instant G1 |
| `c369116` | Unblock hour 19 UTC for BOND entries |
| `a739f76` | Raise snap60_eff floor to 30% for early-window entries (ask<0.80) |
| `9417de2` | Gate imb to [0.30, 0.70): floor raised, ceiling added |
| `d60a8cc` | Disable PAE for early-window entries (ep<0.80, rem>90s) |

**Net strategy effect (vs last audit):**
- TERMINAL-only entries with ask fixed at [0.80, 0.92]; early window (ask<0.80) disabled
- Time exits compressed to T-3s (from T-30s); PAE disabled
- INVERTED_TP: profit-taking at +50% on inverted entries
- Imbalance gate tightened to [0.30, 0.70) with ceiling added
- All hours unblocked (was: {0,2,3,4,5,6,7,17,19,23})
- All unverifiable without raw data.

---

## Deployed Parameter State (from main.py / config.py)

| Parameter | Deployed value | Location |
|---|---|---|
| ask floor | 0.80 (TERMINAL-only; early window disabled) | main.py:2241 |
| max_ask | 0.92 | main.py:2239 |
| min_imbalance | 0.30 (floor raised from 0.20; ceiling 0.70 added) | main.py:2297 |
| bond_blocked_hours_utc | [] (all hours unblocked) | config.py:157 |
| stop_loss | ask×0.85 (−15%) | BOND_CATASTROPHIC, wick filter |
| base_stake | $4.00 | config.py:27 |
| scaled_stake | $4.00 (heat-check disabled) | config.py:34 |
| BOND_TIME_EXIT | T-3s unconditional | main.py:1219 |
| BOND_DEADLINE | T-3s forced exit | main.py:1219 |
| BOND PAE | DISABLED | commit cc223be |
| Early window entries | DISABLED (ask floor fixed at 0.80) | commit 5600f5b |
| INVERTED_TP | +50% exit on inverted entries | main.py:1157 |

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.80,
  "max_ask": 0.92,
  "min_imbalance": 0.30,
  "stake": 4.00,
  "stop_loss": -0.15,
  "blocked_hours": []
}
```

**No parameter changes applied.**
Reason: zero trade data retrieved from VPS — evidence base for any modification: none.
INSUFFICIENT_DATA enforced per anti-sycophancy rules.

---

## Bankroll State (from git-tracked bankroll.json)
capital=$37.32 | total_trades=2605 | total_pnl=+$87.87 | saved_ts=1746160000 (~2026-05-02 04:26 UTC)

Note: bankroll snapshot is stale. Bot has been running continuously since then.

---

## Infrastructure Alert — Critical (29 consecutive sessions)

SSH port 22 actively closed at 85.137.174.86. SSH binary absent in sandbox.
Curl outbound blocked by allowlist for VPS IP.

**Required action — push logs from VPS (one command):**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Or install cron sync (every 30 minutes):**
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

Without log data, audit is structurally blocked. Every session spends time re-discovering the same dead ends. The cron above is a 30-second fix.
