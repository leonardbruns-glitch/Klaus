# Quantitative Audit — 2026-05-04 18:29 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (28th consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 (native binary) | SSH binary absent; apt-get install failed (network timeout at 185.125.190.81:80 during package download) |
| SSH port 22 (paramiko Python) | TCP timeout at 85.137.174.86:22 (15s ConnectTimeout) |
| HTTP/HTTPS port 443 | Cloudflare WAF blocks all requests |
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
Current gate (main.py:2282): `if _term_imb < 0.20: continue`
ETH override (main.py:2683): `if token.asset == "ETH" and _term_imb < 0.30: continue`

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
**INSUFFICIENT_DATA** — VPS unreachable from sandbox (28th consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour all-time in this session (threshold: n≥100/hour for block/unblock decisions).

---

## Changes Since Last Audit (20260504-1217 / commit 1485e2e)

| Commit | Time (UTC) | Change |
|---|---|---|
| `929942d` | ~12:17 | Fix record_trade crash: add term_snap60_eff param to FeedbackEngine |
| `d4d2657` | ~12:17 | Fix record_trade crash: add term_snap30_eff to signature and TradeRecord |
| `8efcd36` | ~post-12:17 | **YES DOWN disabled globally** — COR=33%, Net=-$46 across all hours |
| `0f2467d` | ~post-12:17 | **G1 regime filter**: block YES UP when BTC 60m return outside [-0.3%, +1.5%] |
| `693166b` | ~post-12:17 | **PAE widened for early-window entries** (ep<0.75): rem>180s 20/40s → 25/50s; 90-180s 15/30s → 20/40s |

**Net strategy effect:** Universe reduced to YES UP only. Two new filters cut YES UP further (G1 60m regime; already-live Bnc dir/other gates). PAE less trigger-happy on early entries. All unverifiable without raw data.

---

## Deployed Parameter State (from main.py / config.py)

| Parameter | Deployed value | Location |
|---|---|---|
| ask floor (elapsed≥120s, late-window) | 0.80 | main.py:2220 |
| ask floor (elapsed<120s, early-window) | 0.52 | main.py:2220 |
| max_ask | 0.92 | main.py:2218 (extended from 0.88, 2026-04-30) |
| min_imbalance (global) | 0.20 | main.py:2282 |
| min_imbalance (ETH) | 0.30 | main.py:2683 |
| bond_blocked_hours_utc | {0,2,3,4,5,6,7,17,19,23} | config.py:157 |
| stop_loss | ask×0.85 (−15%) | BOND_CATASTROPHIC, 8s wick filter |
| base_stake | $4.00 | config.py:27 (reduced from $10, 2026-05-04) |
| YES DOWN | DISABLED globally | main.py:2235 (COR=33%, Net=-$46) |
| G1 regime gate | YES UP blocked if BTC 60m < -0.3% or > +1.5% | main.py:2568 |
| PAE early-entry (ep<0.75, rem>180s) | 25% depth, 50s hold | main.py:1093 |
| PAE early-entry (ep<0.75, rem 90-180s) | 20% depth, 40s hold | main.py:1096 |

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
capital=$37.32 | total_trades=2605 | total_pnl=+$87.87 | saved_ts=1746160000 (~2025-05-02 04:26 UTC)

Note: bankroll snapshot pre-dates current session. Estimated 445+ additional trades at ~7.9/hr.

---

## Infrastructure Alert — Critical (28 consecutive sessions)

SSH port 22 actively unreachable: TCP timeout 15s at 85.137.174.86:22.
SSH apt-get install fails: Ubuntu package mirror unreachable from sandbox.

**Required action — push logs ONCE from VPS:**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Or install cron (every 30 minutes):**
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
