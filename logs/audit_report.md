# Quantitative Audit — 2026-05-13 06:17 UTC

## Data Collection Status
**FAILED — VPS UNREACHABLE (53rd consecutive session)**

| Method | Result |
|---|---|
| SSH to root@85.137.174.86:22 | SSH binary absent in sandbox; TCP port 22 blocked at network boundary (connect_ex=11) |
| Port 443/80 | Open but returns "Host not in allowlist" — Cloudflare WAF |
| paramiko (Ed25519) | Installed; connect times out (5s) — port 22 not routable |
| /tmp/trades.jsonl | 0 real lines — SSH pull failed |
| /tmp/post_exit.jsonl | 0 lines — not retrieved |
| logs/trades.jsonl (git-tracked) | Not present — VPS has not run manual sync |
| logs/bankroll.json (local snapshot) | Readable — **UNCHANGED since 2026-05-08 19:26 UTC (106.9h stale)** |

**Bankroll snapshot** (ts=1778268412 / 2026-05-08 19:26 UTC — 4.5 days stale):
- capital: $84.61
- total_trades: 2,605
- total_pnl: +$87.87
- consecutive_wins: 0
- daily_start_capital: $15.95 (stale, pre-oracle_sweep)

> Bankroll snapshot **UNCHANGED** for 53 consecutive audit sessions. Actual live capital unknown
> and may be materially lower after oracle_sweep ($487 positions, 2026-05-11 18:50 UTC).
> No new trade-level records are accessible from this sandbox.

---

## AUDIT SCOPE CONFLICT — BOND Strategy Disabled (53rd session)

**CRITICAL: This audit framework targets `signal_source=='BOND'` trades exclusively.**

| Strategy | Status | Since |
|---|---|---|
| BOND_ENABLED | **False** | 2026-05-10 (window_sniper.py:133) |
| SNIPER_ENABLED | **False** | 2026-04-16 |
| MOM_ENABLED | **False** | 2026-04-22 |
| DISCOVER (active) | **True** | 2026-05-10 |
| LDA (active, newest) | **True** | 2026-05-12 21:41 UTC |

Even if VPS SSH were restored, the BOND audit filter (`signal_source=='BOND'`, `0.80<=entry_price<=0.88`) would return 0 trades for any window after 2026-05-10. This audit framework is **structurally inapplicable** to the current live state.

---

## Active Strategy Parameters (ground truth from codebase, verified this session)

### LDA — Late Direction Arb (newest, deployed 2026-05-12 21:41 UTC)
Source: `strategy/late_direction_arb.py`

| Parameter | Value | Notes |
|---|---|---|
| ASK_FLOOR | 0.70 | line 25 |
| ASK_CEIL | 0.98 | line 26 — reverted from 0.93 (62% n-reduction too steep) |
| BID_MIN | 0.50 | line 27 |
| REM_MIN_S | 8.0s | line 28 |
| REM_MAX_S | 90.0s | line 29 |
| BNC_MOVE_MIN | 0.07% | line 30 — all reversals were at <0.056% |
| STAKE_USD | $5.00 | line 31 |
| BLOCKED_HOURS_UTC | {1} | line 32 — H01 shadow WR=88.6% wrong=9, n=79 |

Signal: Binance 5m-return direction (spot vs open_5m). Shadow accuracy baseline: 96.6% (n=85 windows). LDA exits via bid≥0.999 PROFIT_TARGET or BOND_DEADLINE at T-3s.

Shadow data: n=1,631 windows analysed. BNC_MOVE_MIN=0.07% achieves 99.8% accuracy on shadow, +66% trade count vs higher threshold.

### DISCOVER — ETH-only DOWN (active)
Source: `strategy/discover_strategy.py`

| Parameter | Value | Location |
|---|---|---|
| Direction | DOWN only | line 172 |
| Assets | ETH only (BTC blocked) | line 150 |
| ask range | 0.10 – 0.40 | line 174 |
| rem window | 60 – 180s | line 138 |
| arb_sum gate | < 0.99 | line 193 |
| PT exit | bid ≥ 0.99 | main.py:1318 |
| Stake | $3 target | line 58 |

### BOND Parameters (for audit reference — BOND disabled since 2026-05-10)

| Parameter | Code Location | Current Value | Audit Prompt Assumed | Delta |
|---|---|---|---|---|
| min_ask (_ask_floor) | main.py:2488 | **0.78** | 0.80 | −0.02 |
| max_ask (_ask_max) | main.py:2486 | **0.93** | 0.88 | +0.05 |
| min_imbalance | main.py | **0.0 (gate inactive)** | 0.20 | — |
| _BLOCKED_HOURS | N/A in main.py | **[] (not in use)** | [] | none |
| stop_loss | main.py | **−15%** (ask×0.85) | −15% | none |
| BOND_ENABLED | window_sniper.py:133 | **False** | (assumed True) | — |

---

## 6h Summary
n_trades=0 (no trades.jsonl retrieved) | WR=N/A | E=N/A | Kelly=N/A

6h window: 2026-05-13 00:17 UTC → 2026-05-13 06:17 UTC

0.80-0.84: n=0 WR=N/A E=N/A
0.84-0.88: n=0 WR=N/A E=N/A

---

## Loss Signatures
None in window — no data accessible.

---

## OB Imbalance
No data accessible.

---

## Slippage
avg_slippage_entry=N/A

---

## Hour Analysis (all-time, 0.80-0.88 BOND filter)
No data accessible. n=0 for all hours. No block/unblock decisions possible.

| H | n | WR | PF | status |
|---|---|---|---|---|
| all | 0 | — | — | collecting data (VPS unreachable + BOND disabled) |

---

## Flags
INSUFFICIENT_DATA — 53rd consecutive session with no VPS connectivity.
AUDIT_SCOPE_CONFLICT — BOND disabled 2026-05-10; audit framework targets non-active strategy.
NO_CHANGE — No parameter changes without data.

---

## SYSTEM_PATCH
```json
{
  "min_ask": 0.78,
  "max_ask": 0.93,
  "min_imbalance": 0.0,
  "stake": 5.00,
  "stop_loss": -0.15,
  "blocked_hours": [],
  "change": false,
  "reason": "INSUFFICIENT_DATA — VPS unreachable (53rd consecutive session). BOND disabled 2026-05-10; audit filter inapplicable to current live state. Active strategies: LDA (T-8 to T-90s, ask 0.70-0.98, BNC_MOVE_MIN=0.07%, shadow acc 96.6%) and DISCOVER (ETH-only DOWN). No parameter changes without data."
}
```

> Note: SYSTEM_PATCH values reflect current codebase state. Audit prompt assumed min_ask=0.80/max_ask=0.88 but those are not current — the live bot has _ask_floor=0.78 and _ask_max=0.93 (BOND disabled regardless).

---

## Infrastructure Alert — Critical (53 consecutive sessions)

**Root cause**: SSH binary absent from sandbox; TCP port 22 egress blocked at network boundary.
**paramiko available** (installed this session via pip) but connection times out — confirming port-level block, not binary absence.

**Required action — run ONE of these on the VPS:**

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

**Note:** With BOND disabled and LDA+DISCOVER active, a new audit framework is needed. Key LDA fields:
`signal_source=='LDA'`, `entry_price`, `exit_price`, `exit_reason`, `hold_s`, `net_pnl`, `asset`,
`bnc_move_pct`. DISCOVER fields: `signal_source=='DISCOVER'`, `arb_sum_yes_no`, `peer_age_ms`.

---

## LDA Development Summary (from git log, since LDA deployment 2026-05-12 21:41 UTC)

| Commit | Change |
|---|---|
| 310d1bd | lda: revert ceil to 0.98 — 62% n reduction too steep |
| e833c76 | lda: ceil 0.98→0.93, block H01 |
| 019a5d1 | lda: per-asset per-window bnc gates (shadow n=1631) |
| 4a2667d | analytics: LDA asset x window x bnc breakdown |
| 683a31e | analytics: LDA breakdown by window size and asset |
| a105813 | lda: raise exit threshold to 0.999 |
| d01cc99 | lda: lower ask ceiling 0.994→0.98 |

LDA is actively being tuned from shadow data (n=1,631 shadow windows). Current BLOCKED_HOURS_UTC={1} (H01 shadow WR=88.6% wrong=9, n=79 — only flagged hour at n<100 threshold but excluded as conservative measure).
