# Quantitative Audit — 2026-05-03 06:23 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (20th consecutive session)**

| Method | Result |
|---|---|
| SSH port 22 | CLOSED (nc -z exit 1 — not timeout, actively refused) |
| SSH ports 2222, 2022, 8022, 22022, 1022 | All CLOSED |
| HTTP port 80 | Cloudflare WAF: "Host not in allowlist" |
| HTTPS port 443 | TCP open but Cloudflare WAF blocks all requests |
| logs/live_trades_recent.jsonl (git) | File absent — cron sync still not deployed |

**New finding this session:** Port 22 now returns immediate refusal (exit 1, not timeout).
Previous sessions showed timeout (exit 255). VPS may have firewall rule change, or SSH daemon stopped.

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A
0.75–0.84 bucket: n=0 WR=N/A E=N/A
0.84–0.92 bucket: n=0 WR=N/A E=N/A

**INSUFFICIENT_DATA** — threshold for ask/imbalance changes: n≥20 in 6h window. Not met.

## Loss Signatures
None determinable — no data retrievable.

## OB Imbalance
No data available. Current gate: `_term_imb < 0.20 → skip` (main.py:2100).
Prior evidence: imb≥0.20 PF=1.27 Net=+$24.18 (n=234) vs imb≥0.10 PF=1.01 Net=+$1.67 (n=300).

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.75–0.92)
No trades.jsonl accessible. n<100 per hour confirmed → no block/unblock decisions possible.
All hours unblocked per commit f91ed67 (2026-05-02 ~12:XX UTC — after Audit 18).

| H  | n   | WR  | PF   | status |
|----|-----|-----|------|--------|
| 00-23 | unk | unk | unk | collecting data (all unblocked 2026-05-02 per f91ed67) |

Re-block threshold: n≥100 per hour at PF<0.80. Cannot evaluate without data.

---

## Flags
INSUFFICIENT_DATA — VPS unreachable from sandbox (20th consecutive session).
n=0 in 6h window (threshold: n≥20 for ask/imbalance changes).
n=0 per hour (threshold: n≥100/hour for block/unblock decisions).

---

## Current Parameters (confirmed from main.py)

| Parameter | Value | Line | Notes |
|---|---|---|---|
| min_ask | 0.75 | main.py:2046 | Raised 0.70→0.75 commit 4ed1b99 (2026-05-02) |
| max_ask | 0.92 | main.py:2045 | Extended from 0.88 on 2026-04-30 |
| min_imbalance | 0.20 | main.py:2100 | PF=1.27 (n=234) vs 0.10 gate PF=1.01 |
| blocked_hours | set() | (comment main.py:2024) | All unblocked per f91ed67 (2026-05-02) |
| stop_loss | ask×0.85 (−15%) | BOND_CATASTROPHIC | BC with 8s wick filter |
| stake | $10.00 | config.py | User-raised from $4 on 2026-05-01 |
| max_open_positions | 2 | config.py | Unchanged |
| entry_window | 25–90s remaining | main.py:2035 | Unchanged |
| OB stale gate | ≥3s | main.py | Unchanged |
| tok30 dead zone | skip [18%, 26%) | main.py | Dead-drift zone gate |
| BOND_TRAIL_TP | +10% peak trailing | main.py | Added 4ed1b99 |

**Note:** Audit prompt states min_ask=0.80, max_ask=0.88, blocked_hours=[] — these are outdated.
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

## Infrastructure Alert — Critical (20 consecutive sessions)

SSH port 22 is now actively CLOSED (not just filtering/timing out as in prior sessions).
Port 80 returns CF WAF block. Port 443 is open but CF-proxied and blocks API requests.
**Estimated ~13,000–18,000+ trade records accumulated and unanalyzable.**

The audit agent is completely blind. Every session is a no-op.

### Required action — install cron on VPS (one-time):
```bash
# Run on VPS at root@85.137.174.86
cat > /etc/cron.d/push-logs << 'EOF'
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N
EOF
chmod 644 /etc/cron.d/push-logs
```
Audit agent reads `logs/live_trades_recent.jsonl` from GitHub — no SSH required.

### SSH diagnostics (this session):
- Port 22: `nc -z -w 3 85.137.174.86 22` → exit 1 (CLOSED)
- Port 443: `nc -z -w 3 85.137.174.86 443` → exit 0 (Cloudflare WAF)
- SSH client: installed this session via `apt-get install openssh-client`
- Conclusion: VPS firewall is blocking all SSH ports, or sshd is down

**Without log sync to git, the quantitative auditor cannot function.**
