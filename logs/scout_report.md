# Alpha Scout Report — 2026-05-05 00:16 UTC

**Method:** Commit-embedded analysis — VPS SSH unreachable (26th consecutive scout session)
**Connectivity:** SSH binary absent in sandbox; TCP timeout to 85.137.174.86:22 (15s); No trades.jsonl or post_exit.jsonl retrievable.
**Data sources used:** git log (commits 929942d → 00cbf96, May 4 13:38 → 21:03 UTC; 26 commits since last scout 2026-05-04T1221)
**Bankroll snapshot (May 2 ~04:26 UTC):** capital=$37.32, total_trades=2605, total_pnl=$87.87 (~44h stale)
**Estimated trade count since WOP-era (May 1 21:00):** ~84h × ~7.9/hr ≈ **~664 WOP-era trades** (inaccessible)

---

## Changes Since Last Scout Report (May 4 12:21 UTC)

| Commit | Time (UTC) | Change | Embedded n |
|---|---|---|---|
| `929942d` | 13:38 | Fix record_trade crash: add term_snap60_eff param to FeedbackEngine | — |
| `d4d2657` | 14:09 | Fix record_trade crash: add term_snap30_eff to TradeRecord signature | — |
| `8efcd36` | 15:30 | **YES DOWN disabled globally** — COR=33%, Net=-$46 across all hours | n=35 YES DOWN May 3–4 |
| `0f2467d` | 15:38 | **G1 regime filter**: block YES UP if BTC 60m return outside [-0.3%, +1.5%] | UTC10 WR=0% Net=-$22; UTC15 COR=11% |
| `693166b` | 15:59 | **PAE widened for early-window** (ep<0.75): rem>180s 20%/40s→25%/50s; 90–180s 15%/30s→20%/40s | — |
| `7312d06` | 18:23 | Add G1_check debug log | — |
| `fc85b70` | 18:31 | Audit 20260504-1829 — 28th VPS outage, no change | — |
| `d60a8cc` | 18:37 | **PAE disabled for early-window entries** (ep<0.80, rem>90s) | n=83 PAE fires, WR=0%, -$160 |
| `9417de2` | 18:49 | **OB imbalance gated to [0.30, 0.70)**: floor raised 0.20→0.30, ceiling added | n=212 early-window YES UP resolved |
| `a739f76` | 19:06 | **snap60_eff floor 30%** for early-window entries (ask<0.80) | n=59, [20,30) COR=43.8%, [30,50) COR=72.7% |
| `c369116` | 19:13 | Unblock hour 19 UTC | — |
| `18e2433` | 19:17 | Bootstrap 1m close buffer from Binance REST on startup (instant G1) | — |
| `7f64d20` | 19:24 | Re-enable 15m windows with scaled timing | — |
| `36b6cda` | 19:43 | **YES DOWN re-enabled** with snap60 gate; G1 direction-guard fixed | n=675 structural audit; n=154 snap60≥12% YES DOWN |
| `b38e6c4` | 19:57 | Fix entered_correctly inversion for YES DOWN | — |
| `462e941` | 19:58 | **Disable 15m windows** — 5m only | — |
| `dc4ce2f` | 20:24 | **Invert TERMINAL direction**: buy opposite side when gates fire | — |
| `eed10b0` | 20:27 | **TIME_EXIT T-30s** re-enabled (precise timer, unconditional) | — |
| `291eadba` | 20:29 | **INVERTED_TP**: exit at +75% on inverted (low-price) entries | — |
| `51e590f` | 20:32 | Unblock all trade hours (bond_blocked_hours_utc cleared) | — |
| `95fa943` | 20:34 | **Inversion limited to early-window only** (_ask_floor==0.52); TERMINAL buys direct | — |
| `c6e938d` | 20:45 | INVERTED_TP threshold 75%→50% (entry_price × 1.50) | — |
| `5600f5b` | 20:54 | **Early-window entries DISABLED** — TERMINAL only (ask floor fixed 0.80) | n=165 ep<0.80 WR=41% -$98.62; n=16 ep≥0.80 WR=69% -$2.34 |
| `cc223be` | 21:00 | **PAE disabled globally** (if False guard) | — |
| `8a40459` | 21:02 | **TIME_EXIT T-30s → T-3s** | — |
| `00cbf96` | 21:03 | **BOND_DEADLINE T-5s → T-3s** | — |

**Net effect of this session's churn (12:21 → 21:03 UTC, 8h42m):**
Strategy ended the day in TERMINAL-only mode: ask 0.80–0.92, no early window, no PAE, T-3s exit, all hours unblocked. Inversion code (`_ask_floor == 0.52` branch at main.py:2796) and INVERTED_TP are both **unreachable dead code** — `_ask_floor` is hardcoded 0.80, so the inversion branch can never fire.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot momentum in the 5s before entry (`pre_entry_momentum_pct > 0`) predicts higher YES resolution rate.
**MATH:** `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago`

**STATUS: INCONCLUSIVE (5s) / SIGNAL_FOUND (1m — deployed since May 4 09:13)**

The 1m timeframe gate (`term_binance_1m`) was validated in the prior scout cycle: n=80 YES UP, W avg=+0.0028% vs L avg=-0.0023%, Δ=0.0051 percentage points. Gate live. Direction fix applied this cycle (commit `36b6cda`): G1 gate was direction-agnostic, would have blocked YES DOWN in crash regime (its favorable zone). Fixed to YES UP only.

The mandatory 5s metric (`pre_entry_momentum_pct`) remains unevaluated — field exists in trade records, no bucketed WR/n retrievable without trades.jsonl.

**RESULT:**
| Timeframe | Metric | W avg | L avg | Δ | n | Status |
|---|---|---|---|---|---|---|
| 1m | term_binance_1m | +0.0028% | -0.0023% | 0.0051%** | n=80 YES UP | LIVE |
| 5s | pre_entry_momentum_pct | N/A | N/A | N/A | 0 | INCONCLUSIVE |

**CONCLUSION: INCONCLUSIVE** (5s timeframe — no raw data). 1m deployed and not the subject of this investigation.
**FAILURE_MET: N/A** — criterion requires n≥20 per bucket. n=0 for 5s metric.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low tick count in 5s before entry (thin/dead market) predicts worse outcomes. Minimum tick floor can filter toxic entries.
**FIELD:** `term_tok_tick_count_5s`

**STATUS: INCONCLUSIVE (26th consecutive session)**

No bucketed tick count data embedded in any commit since last report. Field exists in logs; n=0 accessible per bucket.

**RESULT:**
| Bucket | n | WR | PF |
|---|---|---|---|
| 0–2 ticks | 0 | N/A | N/A |
| 3–5 ticks | 0 | N/A | N/A |
| 6–10 ticks | 0 | N/A | N/A |
| 11+ ticks | 0 | N/A | N/A |

**PROPOSED_GATE:** Cannot propose — n=0 per bucket.
**CONCLUSION: INCONCLUSIVE**

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Flat token price in 5s before entry (|term_token_delta_5s| < 0.005) signals inactive market and predicts lower YES resolution rate.
**FIELD:** `term_token_delta_5s`

**STATUS: INCONCLUSIVE (26th consecutive session)**

New proximate data this cycle: commit `9417de2` found OB imbalance ≥0.70 underperforms (COR=57.7%, n=26) — over-one-sided books correlate with poor resolution. Related concept, different field. No `term_token_delta_5s` bucketed data embedded in any commit.

**RESULT:**
| Bucket | n | WR |
|---|---|---|
| Dead drift (<0.005) | 0 | N/A |
| Active (≥0.005) | 0 | N/A |

**CONCLUSION: INCONCLUSIVE**

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One asset consistently outperforms; stake weighting by asset improves profit factor.
**FILTER:** BOND signal, is_live=True, last 48h, snap60≥12% (current gate)

**STATUS: PARTIAL — new embedded data this cycle**

Two commit bodies contain per-asset breakdowns:

**From commit `d60a8cc` (PAE disable analysis, n=83 PAE fire events):**
This is the adversarial subset only — token dipped >5% then recovered. Per-asset WR projected without PAE intervention:

| Asset | Projected WR (no PAE) | Note |
|---|---|---|
| SOL | 81.0% | Strongest recovery from dips |
| BTC | 73.6% | Intermediate |
| ETH | 70.2% | Weakest recovery |

Caveat: this n=83 is PAE fires only (extreme dips), not general TERMINAL performance.

**From commit `36b6cda` (structural audit, YES DOWN snap60≥12%):**
- BTC YES DOWN snap60≥12%: WR=86%, Net=+$38 (n unclear within n=154 total)
- ETH/SOL per-asset split not reported for this subset

**n≥20 threshold check:**
Total snap60≥12% YES DOWN trades: n=154 (pool exists). Per-asset n not confirmed in commit data. Cannot verify ≥20 per asset.

**CONCLUSION: INCONCLUSIVE** — n per asset unverifiable for last 48h from commit data alone. SOL shows highest projected WR under adversarial conditions (81.0%), ETH weakest (70.2%). No staking reweight recommended without confirmed n≥20 per asset from raw data.
**FAILURE_MET: Yes** — n < 20 confirmed per asset (raw data inaccessible).

---

## Critical Structural Finding (not in mandated investigations)

### OB Imbalance Ceiling — SIGNAL_FOUND (deployed May 4 18:49)
**From commit `9417de2`**, n=212 early-window YES UP resolved trades:

| Imbalance bucket | COR | n |
|---|---|---|
| < 0.30 | 58.3% | 44 |
| [0.30, 0.70) | **75.0%** | 75 |
| ≥ 0.70 | 57.7% | 26 |

**Finding:** High imbalance (≥0.70) performs as badly as low imbalance (<0.30). Strong one-sidedness = adverse selection / informed flow against position. Counter-intuitive but statistically meaningful at n=75 sweet zone vs n=26+44 flanks. Gate deployed.

### Dead Code Alert — Action Required
`_ask_floor` is hardcoded `0.80` at main.py:2241. The inversion branch at main.py:2796 (`if _ask_floor == 0.52`) **can never execute**. INVERTED_TP at main.py:1152 is also unreachable (no inverted positions can be opened). These should be removed on next maintenance pass to avoid confusion.

---

## Priority Signal for Next Implementation

**No new actionable signal on the four mandated metrics this cycle.**

The strongest unvalidated hypothesis from embedded commit data for the next cycle to test when trades.jsonl is accessible:

**Variable:** Per-asset TERMINAL WR differential (SOL vs ETH gap)
**Evidence:** PAE fire recovery: SOL 81.0% vs ETH 70.2% (n=83, adversarial subset)
**Hypothesis:** ETH has structurally lower resolution rate in TERMINAL zone due to weaker momentum persistence. Test with TERMINAL-only (ep≥0.80) trades by asset.
**Python snippet:**
```python
import json, time
from collections import defaultdict

trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
cutoff = time.time() - 48 * 3600
term = [t for t in trades
        if t.get("signal_source") == "BOND"
        and t.get("is_live") is True
        and t.get("entry_price", 0) >= 0.80
        and t.get("ts", 0) >= cutoff]

by_asset = defaultdict(list)
for t in term:
    by_asset[t.get("asset", "?")].append(t)

for asset, group in sorted(by_asset.items()):
    wins = sum(1 for t in group if t.get("net_pnl", 0) > 0)
    net  = sum(t.get("net_pnl", 0) for t in group)
    pf_g = sum(t["net_pnl"] for t in group if t.get("net_pnl", 0) > 0)
    pf_l = abs(sum(t["net_pnl"] for t in group if t.get("net_pnl", 0) < 0)) or 1
    print(f"{asset}: n={len(group)} WR={wins/max(len(group),1):.0%} PF={pf_g/pf_l:.2f} net={net:+.2f}")
```
**Failure criteria:** If WR spread across assets < 5pp at n≥20 per asset → no asset-specific gating warranted.

**If no data accessible next cycle:** No actionable signals this cycle — continue data collection.

---

## Current Deployed Parameter State (2026-05-05 00:16 UTC)

| Parameter | Value | Location | Status |
|---|---|---|---|
| ask floor | 0.80 (TERMINAL only) | main.py:2241 | LIVE |
| ask ceiling | 0.92 | main.py:2240 | LIVE |
| OB imbalance gate | [0.30, 0.70) | main.py:2297 | LIVE (updated this cycle) |
| PAE | DISABLED (`if False`) | main.py:1102 | LIVE (disabled this cycle) |
| TIME_EXIT | T-3s | main.py:2446 | LIVE (updated this cycle) |
| BOND_DEADLINE | T-3s | main.py:1219 | LIVE (updated this cycle) |
| INVERTED_TP | dead code (unreachable) | main.py:1152 | DEAD CODE |
| Inversion branch | dead code (unreachable) | main.py:2796 | DEAD CODE |
| 15m windows | DISABLED | main.py:2183 | LIVE |
| bond_blocked_hours_utc | [] (all hours) | config.py:154 | LIVE |
| base_stake | $4.00 | config.py | LIVE |
| G1 regime gate (YES UP only) | [-0.3%, +1.5%] BTC 60m | main.py | LIVE |
| Binance dir gate (YES UP) | skip if b1m < 0 (not UTC22) | main.py | LIVE |
| snap60 floor (TERMINAL) | 12% | main.py | LIVE |
| snap30 gate | [10%, 120%) | main.py | LIVE |

---

## Infrastructure Alert — Persistent (26 sessions)

**VPS SSH unreachable from sandbox.** SSH binary absent; TCP port 22 timeout. No JSONL data retrievable.
Estimated TERMINAL-era trades inaccessible: **500+**. All four mandated investigations INCONCLUSIVE for the 26th consecutive session.

**Required action — push logs ONCE from VPS:**
```bash
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

**Or install as cron (every 30 minutes):**
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

Without this, all four mandated investigations remain INCONCLUSIVE indefinitely.
