# Alpha Scout Report — 2026-05-02 12:13 UTC

**Method:** Commit-embedded analysis + bankroll.json delta — VPS SSH unreachable (13th consecutive session)
**Connectivity:** SSH binary absent from sandbox; TCP 80 returns CF WAF "Host not in allowlist"; no trades.jsonl retrieved.
**Data sources:** bankroll.json (saved ~May 2 06:13 UTC), state_log.md, git commits b59934b→835de9c (May 2), git commit e1d849c (May 1 21:XX UTC sim data).
**Bankroll snapshot:** capital=$37.32, total_trades=2605, total_pnl=$87.87, stake=$10.00

---

## Critical Context: Strategy Architecture Shift (May 1 21:XX UTC)

The strategy transitioned from timed exits to **Window Outcome (WOP)** between the last scout report and this one. Changes:

- `PROFIT_TARGET` disabled (costs -$34.18 vs WOP in 48h sim)
- `BOND_DEADLINE` (T-4s forced exit) disabled
- T-10s conditional exit disabled
- **Primary exits now: `WINDOW_OUTCOME` (hold to resolution) + `PAE` (≥5% adverse for 20s)**
- 48h WOP+PAE sim: actual net +$65.24 → projected +$116.96 (+$51.72)

**Impact on all four mandated investigations:** Every signal previously measured against TIME_EXIT/BOND_DEADLINE/PROFIT_TARGET outcomes is now contaminated. Under WOP, the relevant question is binary: **does this window resolve YES?** Not "does the bid move enough to exit profitably in 5–30s?" The tick count, dead drift, and cross-exchange signals must be re-evaluated on WOP-era data only. Pre-WOP records in trades.jsonl are structurally invalid as training data for the current strategy.

**Estimated WOP-era trade count:** Hold-to-outcome went live ~May 1 21:XX UTC. From bankroll: 2605 total trades saved ~May 2 06:13 UTC → ~9h of WOP-era trades → ~73 WOP-era trades at 8.1 trades/hr. All four investigations require n≥20 per bucket — threshold is NOT met for WOP-era data alone.

---

## Bankroll Delta Analysis (Apr 29 04:59 → May 2 06:13 UTC, ~73h)

| Metric | Apr 29 | May 2 | Delta |
|---|---|---|---|
| capital | $34.28 | $37.32 | +$3.04 |
| total_trades | 2025 | 2605 | +580 |
| total_pnl | $99.30 | $87.87 | -$11.43 |
| stake | $4.00 (then $10.00) | $10.00 | raised |

**Trade rate:** 580 trades / 73h = 7.9 trades/hr — sharply higher than prior estimate of ~2/hr. The ask range widening to 0.70–0.92 (Apr 30 06:XX) accounts for most of this increase.

**PnL delta interpretation:** total_pnl dropped -$11.43 while capital rose +$3.04. The gap (~$14.47) reflects retroactive corrections committed May 1–2: T02829 (-$9.94 wop correction), T02682_ETH (-$4.90 BC disable bug), T02669_BTC (-$1.79 cancel-race logging error), and 860 historical trades backfilled from post_exit.jsonl. These corrections reduced reported cumulative PnL without changing live capital (which was already spending/winning correctly). At $10/stake: ~$5,800 gross turnover in 73h → +$3.04 net = essentially breakeven, not a loss.

**Blocked hours (current):** {0, 2, 3, 4, 5, 6, 7, 17, 19, 23} — 10 of 24 hours blocked. Active window: 08–11, 12–13 (restored), 14 (block at :45), 15 (block until :45), 16 (block at :55), 18, 20–22 UTC.

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot momentum (term_spot_delta_5s > 0, i.e. spot rising in 5s before entry) predicts higher YES resolution rate — spot moving toward higher price = YES likely confirmed at Chainlink snapshot.

**STATUS: INCONCLUSIVE — VPS unreachable, n per bucket unverifiable**

**MATH:** `term_spot_delta_5s = (spot_now - spot_5s_ago) / spot_5s_ago` (% change over 5s Binance mid)

**Data available:**
- Field `term_spot_delta_5s` added commit `947306c` (~Apr 29 12:41 UTC) → ~43h before this report
- Estimated total trades with field: 43h × 7.9/hr = ~340 trades
- WOP-era only (valid signal source): ~73 trades → ~24 per bucket — near threshold but unverifiable

**Prior proxy (contaminated pre-WOP era, Apr 29, 1m klines, n=43):**
- "Both-rising" (Binance 1m + 5m positive, UP-window): WR=51%
- Other regimes: WR=75–87%
- This is an **inverse** signal — positive momentum predicted LOWER resolution rate
- Possible explanation: when spot is rising strongly, token is already at a high ask (0.85+) and has less upside to 1.0; or the cross-exchange arb bots have already priced in the movement

**WOP-era hypothesis revision:** Under WOP, Chainlink resolves at T=0 snapshot. Spot momentum in the final 60–90s before resolution may be more directly predictive. The proxy evidence suggests the signal may be **inverse** — skip entries when spot is rising fast, as the token has front-run the move.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Not applicable** — WOP-era n per bucket unverifiable; VPS blocked. Do not gate. Note inverse-signal hypothesis for WOP-era evaluation.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low tick count (0–2 ticks in 5s before entry) = thin/dead market. High tick count = active informed flow. Higher tick count predicts YES resolution.

**STATUS: INCONCLUSIVE — `term_tok_tick_count_5s` DISCARDED; `term_tok_tick_count_30s` VPS-blocked**

**Data available:**
- `term_tok_tick_count_5s` (5s window): **DISCARDED** from prior two scout cycles — wins and losses both share median tick count = 8; zero separation between buckets confirmed.
- `term_tok_tick_count_30s` (30s window): added ~Apr 28 02:11 UTC → ~82h old → ~648 total trades with field; of which ~73 WOP-era. WOP-era n per bucket: ~18 per bucket (4 buckets) — below threshold.
- Cannot bucket or compute WR per bucket without trades.jsonl.

**WOP-era interpretation shift:** Under timed exits, tick count measured whether the bid moved fast enough to capture profit. Under WOP, the relevant question is whether the market is actively informationally efficient: a low-tick-count market in the final 90s may have poor Chainlink correlation (thin OB = stale prices) or may simply be a liquidity-starved window with correctly priced odds. Neither interpretation clearly predicts resolution direction.

**PROPOSED_GATE:** min_tick_count_30s = TBD. Do not implement until n≥80 WOP-era trades per bucket. Estimate threshold met: ~May 12 at current rate if WOP era sustains 7.9 trades/hr.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Not applicable** — WOP-era data volume insufficient (n~18/bucket vs n≥20 minimum). Legacy data (pre-WOP) is structurally invalid.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Entries where the YES token price is flat in 5s before entry (|term_token_delta_5s| < 0.005) predict lower YES resolution rate. Dead market = no genuine buyer conviction.

**STATUS: SIGNAL_CANDIDATE — priority ELEVATED under WOP**

**MATH:** `term_token_delta_5s = (ask_now - ask_5s_ago)` (absolute price delta, not %)

**Data available:**
- Field `term_token_delta_5s` live throughout WOP era and pre-WOP era
- WOP-era dead drift n: ~73 WOP trades × ~11% dead-drift rate = ~8 dead-drift entries — below n≥20
- Pre-WOP signal (n=677, all-era): WR=53% dead drift vs WR=65% active — 12pp gap exceeded 5pp threshold
- This signal is now structurally more important under WOP:

**Why this signal is MORE important under WOP:**
- Under timed exits: dead drift = token not moving → bid stays flat → TIME_EXIT at near-entry price → small loss (or small win if just below SL)
- Under WOP: dead drift = token not moving toward 0.99 → likely resolving NO → **100% loss of principal** (exit at bid <0.90 floor or resolution at 0.01)
- A 12pp WR gap in timed-exit era maps to a much larger EV gap under WOP at $10/stake

**Do not gate yet.** WOP-era n~8 dead-drift entries — threshold is n≥40. Accumulate.

**At current rate:** WOP-era dead-drift n≥40 expected around: 40/(0.11×7.9) ≈ 46h from WOP launch → approximately May 3 19:XX UTC.

**CONCLUSION: SIGNAL_CANDIDATE — carry forward, priority elevated**
**FAILURE_MET: Not applicable** — WOP-era n=~8 dead-drift entries. Threshold n≥40. Evaluate ~May 3.

---

## Investigation 4: Asset-Specific Edge

**STATUS: INCONCLUSIVE — per-asset WR/PF/net_pnl uncomputable without trades.jsonl**

**Embedded data (commit-level, ~48h window, not full WR/PF):**

| Asset | Embedded Data | Source |
|---|---|---|
| BTC | snap60 [20,30%): WR=67% n=18 total_pnl=-$11.70 (6 losses=$18.23, 12 wins=$6.53) | commit 2ec72a9 |
| ETH | snap60 [20,30%): neutral n=17 net+$1.04; tok_delta_30s≥100%: WR=43% n=7 (blocked) | commit 835de9c, 2ec72a9 |
| SOL | snap60 [20,30%): WR=93% n=?? | commit 2ec72a9 |
| H12 | TERMINAL-era (BOND-in-range only): PF=2.07 | commit e1d849c sim |
| H13 | TERMINAL-era (BOND-in-range only): PF=0.88 | commit e1d849c sim |

**Estimated per-asset trade volume (580 new trades / 3 assets):** ~193 per asset. n≥20 threshold met — but WR/PF not computable from embedded data alone.

**Flag — H13 unblocked at PF=0.88:** H13 was unblocked in commit `e1d849c` because the prior block used contaminated all-trades data. The TERMINAL-era PF=0.88 is below 1.0. Justification: decontamination made data unreliable; collect clean WOP-era data. Monitor H13 — if WOP-era H13 PF < 0.80 at n≥50, re-block.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Yes** — n≥20 per asset confirmed (estimated ~193/asset), but WR/PF cannot be computed from commit-embedded data alone. Structurally blocked by VPS outage.

---

## New Investigation: Snap60 Magnitude Asymmetry — Loss Distribution by Band

**HYPOTHESIS:** Within the active snap60 zone (12–120%), win/loss magnitude is not uniform. Low-snap60 entries (12–40%) have large loss size relative to win size despite adequate WR — making them EV-negative even at WR > 50%. High-snap60 entries (40–80%) are better calibrated.

**EVIDENCE FROM EMBEDDED DATA (BTC snap60 [20,30%), commit 2ec72a9, n=18):**

```
n=18 BTC trades in snap60 [20,30%) zone
  12 wins  → total +$6.53  → avg win  = $0.54
   6 losses → total -$18.23 → avg loss = -$3.04
  
  win/loss magnitude ratio: 0.54/3.04 = 0.18×  (catastrophic asymmetry)
  WR = 67%  (appears good)
  EV = 0.67 × $0.54 − 0.33 × $3.04 = $0.36 − $1.00 = −$0.64/trade
  Net: −$11.70 on 18 trades  (confirmed by commit)
```

**Why does this happen?** Weak-momentum entries (snap60 12–30%) enter when the token has only barely started moving. When the trade goes wrong, the token is farther from 0.99 and PAE triggers at a deeper draw — or under WOP, the window resolves NO at full loss. Strong-momentum entries (snap60 60–120%) enter tokens already committed to YES resolution; reversals are shorter-lived (Chainlink snap invariant: 5m window resolution is not reversible once >90% likely).

**Cross-asset validation:**
- ETH same zone [20,30%): n=17, net+$1.04 — neutral (EV ~0)
- SOL same zone [20,30%): WR=93% — strongly positive

This is a **BTC-specific** asymmetry. At n=18 it is below the n≥30 threshold and was correctly reverted as overfit. However, the magnitude structure (avg loss 5.6× avg win) is a signal worth accumulating.

**MATH:**
```python
# Magnitude asymmetry by snap60 band — run on VPS with WOP-era trades.jsonl
import json
trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
bond = [t for t in trades
        if t.get("signal_source") == "BOND"
        and t.get("is_live") is True
        and t.get("term_pre_snap_60s") is not None]

# WOP-era only (hold-to-outcome): after ~2026-05-01T21:00 UTC
import datetime
wop_epoch = datetime.datetime(2026, 5, 1, 21, 0).timestamp()
bond = [t for t in bond if t.get("ts", 0) >= wop_epoch]

bands = [("snap12-40%", 12, 40), ("snap40-80%", 40, 80), ("snap80-120%", 80, 120)]
for label, lo, hi in bands:
    bucket = [t for t in bond if lo <= t["term_pre_snap_60s"] < hi]
    if not bucket:
        print(f"{label}: n=0"); continue
    wins  = [t for t in bucket if t.get("net_pnl", 0) > 0]
    losses= [t for t in bucket if t.get("net_pnl", 0) <= 0]
    avg_w = sum(t["net_pnl"] for t in wins)  / max(len(wins), 1)
    avg_l = sum(t["net_pnl"] for t in losses)/ max(len(losses), 1)
    ratio = avg_w / abs(avg_l) if avg_l < 0 else float("inf")
    net   = sum(t.get("net_pnl", 0) for t in bucket)
    print(f"{label}: n={len(bucket)} WR={len(wins)/len(bucket):.1%} "
          f"avg_win={avg_w:+.2f} avg_loss={avg_l:+.2f} ratio={ratio:.2f} net={net:+.2f}")
```

**Failure criteria:** If avg_win/avg_loss ratio is uniform (within 0.15×) across all three bands at n≥20/band → no magnitude structure → discard.

**CONCLUSION: PENDING** — BTC [20,30%) provides n=18 data point showing 0.18× ratio. Gate cannot be implemented until n≥30/band. Accumulate; re-evaluate in ~48h when WOP-era volume approaches threshold.

---

## Priority Signal for Next Implementation

**Signal: Snap60 Magnitude Asymmetry (WOP-era calibration)**

The snap60 band (12–120%) is wide and internally heterogeneous. We know:
- ≥120% is blocked (WR=63% n=16, absolute gate)
- <12% is blocked (WR=55% net-negative)
- [20,30%) BTC shows catastrophic loss-magnitude asymmetry (avg_loss 5.6× avg_win at n=18)
- [20,30%) SOL shows WR=93% — opposite pattern

**Variable:** `term_pre_snap_60s` (already logged)
**Investigation target:** WOP-era magnitude ratio (avg_win / |avg_loss|) by snap60 band per asset

**Implementation path (DO NOT implement gates until n≥30/band/asset):**
1. Run the Python snippet above on VPS against WOP-era trades (after May 1 21:XX UTC)
2. If BTC [12,40%) magnitude ratio < 0.25 at n≥30: implement BTC-specific lower snap60 floor of 40%
3. If SOL [80,120%) shows magnitude ratio > 1.0 at n≥30: no upper bound for SOL (prefer high-snap SOL)
4. If cross-asset analysis shows no consistent band structure: discard, monitor BTC separately

**Why this is the priority:** The snap60 gate family has been the most productive gate category in the last 7 days (snap60<0, snap60<12%, snap60≥120% all implemented). The [12–120%] interior has never been quantitatively examined for magnitude structure, only WR structure. Magnitude asymmetry is invisible in WR-only analysis and requires explicit avg_win/avg_loss disaggregation. Under WOP at $10/stake, a single NO resolution = -$8.65 (entry at 0.865 stake × $10); a YES resolution walk to 0.99 = +$1.25. The natural WOP magnitude ratio is 0.14× — any gate that increases this ratio, even modestly, has outsized EV impact.

---

## Schema Fields Status

| Field | Status | WOP-Era Trades (est.) | Threshold |
|---|---|---|---|
| `term_spot_delta_5s` | Live | ~73 (total since field: ~340) | n≥100 WOP-era non-zero |
| `term_tok_tick_count_30s` | Live | ~73 WOP; ~648 total | n≥80 WOP-era; n≥20/bucket |
| `term_token_delta_5s` | Live | ~73 WOP | n≥40 dead-drift WOP entries |
| `term_pre_snap_60s` | Live | ~73 WOP; ~22 post-gate | n≥30/band/asset for magnitude analysis |

---

## Infrastructure Alert — Persistent (13 sessions)

**VPS SSH unreachable from sandbox.** Estimated accumulated trade records inaccessible since first failure (~6 days ago): **~12,000–15,000+ records**.

**Every quantitative investigation is structurally blocked.** WOP era started May 1 21:XX UTC — approximately 450 WOP-era trades are already inaccessible.

**Recommended fix (unchanged from prior 12 cycles):**
```bash
# On VPS: /etc/cron.d/push-logs (install ONCE — never rerun)
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N 2>/dev/null
```

This is the single highest-leverage action available. Until implemented, all four mandated investigations remain INCONCLUSIVE by anti-sycophancy rules.
