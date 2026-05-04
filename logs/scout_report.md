# Alpha Scout Report — 2026-05-04 00:12 UTC

**Method:** Commit-embedded analysis — VPS SSH unreachable (24th consecutive session)
**Connectivity:** SSH binary absent in sandbox. HTTP/HTTPS port 443 open but Cloudflare WAF blocks all requests. No trades.jsonl or post_exit.jsonl retrievable.
**Data sources used:** git log (commits a66feb2, c557252, 240c68b, 60947b3, 84182bc since last scout 2026-05-03T1213), bankroll.json, state_log.md.
**Bankroll snapshot (May 2 ~04:26 UTC):** capital=$37.32, total_trades=2605, total_pnl=$87.87.
**WOP-era estimated trade count:** May-01 21:00 → May-04 00:12 = ~51h × ~7.9/hr ≈ **~403 WOP-era trades** (inaccessible).

---

## Changes Since Last Scout Report (May 3 12:13 UTC)

| Commit | Change | Embedded n |
|---|---|---|
| `60947b3` (17:05) | Dead-zone filters: 60m range/ER/ATR — logging only, gates OFF | Sunday flat session motivated; n collecting |
| `e528b20` (17:XX) | TP fires at entry×1.10 OR bid>=0.99 | — |
| `a66feb2` (19:03) | Per-asset gates: BTC daccel/accel_sustained/elapsed/depth, ETH imb/tok_d30/depth, SOL elapsed | May-01+ n=349, -$407 loss pool |
| `8b1605b` (19:52) | Allow early-window entries: ask floor 0.52 in first 2 min | — |
| `d49cfe2` (20:XX) | TP simplified to bid>=0.99 | — |
| `d092118` (21:14) | Disable BOND scale-in — n<100 | — |
| `c557252` (21:31) | Early-entry exits: T-50s unconditional + T-60s sell>0.90 | BOND_EXPIRED_UNSOLD n=42 -$310 |
| `240c68b` (21:50) | Regime cooldown: T1 ≤-$7→5m, T2 2nd≤-$5/30m→10m | 19d sim saves $221; ~6 T1/day |

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot momentum (`pre_entry_momentum_pct > 0`) in the 5s before entry predicts higher YES resolution rate.
**MATH:** `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago`

**STATUS: INCONCLUSIVE — 24th consecutive session, no trades.jsonl retrieved.**

The closest available analog is the BTC token-level acceleration signal from commit `a66feb2` (May-01+, n=349):

| BTC sub-pattern | n | WR | Note |
|---|---|---|---|
| daccel <= +0.01 (flat/negative accel) | 38 | 37% | GATED as of May 3 19:03 |
| accel_sustained = False | 54 | 43% | GATED as of May 3 19:03 |
| daccel > +0.01 AND accel_sustained | remainder | unknown | unblocked — accumulating |

`daccel` measures 5s token price acceleration (analog to 5s spot momentum, different instrument). This gate has been deployed. The 5s Binance spot `pre_entry_momentum_pct` remains unmeasured at bucket level.

**RESULT:** n per 5s Binance momentum bucket = 0 (VPS-blocked). Cannot bucket.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Not applicable** — data inaccessible. Do not gate on Binance 5s momentum until WOP-era n≥40 per bucket from live data.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low tick count (0–2 ticks in 5s before entry) = thin/dead market predicts lower YES resolution rate.

**STATUS: INCONCLUSIVE — 24th consecutive session, no trades.jsonl retrieved.**

Prior finding (pre-WOP, commit history): median tick count = 8 for both wins and losses. Zero WR separation. Tok30 dead zone [18%, 26%) (commit f874c1d, n=159, PF=0.75) subsumes the low-liquidity failure mode at a different timescale.

WOP-era tick data: still inaccessible. No per-bucket breakdown possible.

**RESULT:** n per tick bucket = 0 (VPS-blocked).
**PROPOSED_GATE:** Not proposed. Prior all-era data showed no separation. Tok30 dead-zone gate addresses the low-activity failure mode more robustly.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Yes (prior era)** — tick count showed <1pp WR spread in pre-WOP era. WOP-era retest pending n≥20 per bucket.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Dead market entries (|term_token_delta_5s| < 0.005) underperform active entries.
**MATH:** `term_token_delta_5s = ask_now - ask_5s_ago`

**STATUS: SIGNAL_CANDIDATE (carries forward) — 24th consecutive session, no WOP-era data.**

Pre-WOP all-era (n=677): WR=53% dead drift vs WR=65% active — **12pp gap, exceeds 5pp threshold.**

**New context this cycle (commit `60947b3`, May 3 17:05):** Bot now logs three structural dead-zone signals:
- `term_dz_range_usd` — 60m BTC H/L range in USD (Sunday: ~$10 range motivated this commit)
- `term_dz_er` — Kaufman ER on 1m closes (0=chop, 1=trend)
- `term_dz_atr_ratio` — recent 15m ATR vs 4h baseline

These are **market-level dead-zone metrics** (complementary, different timescale to the token-level 5s delta). They do not subsume the 5s token delta signal but address the macro condition that produces dead-drift entries.

The Sunday flat-session motivation (`~$10 BTC range`) confirms the dead-drift hypothesis indirectly: flat macro conditions produce flat token behavior, which produces dead-drift entries, which underperform.

**RESULT:** n=0 (VPS-blocked). WOP-era bucket counts unavailable.
**CONCLUSION: INCONCLUSIVE** (SIGNAL_CANDIDATE from prior era, structural support growing)
**FAILURE_MET: Not yet evaluable** — WOP-era n too small to confirm or deny in live data.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One or more assets show consistently higher WR/PF in the last 48h, warranting stake reweighting.

**STATUS: PARTIAL DATA — aggregate per-asset WR/PF unavailable, but sub-pattern breakdown from May-01+ exists.**

From commit `a66feb2` (May 3 19:03, May-01+ n=349):

**BTC sub-patterns with negative WR:**
| Sub-pattern | n | WR | Net |
|---|---|---|---|
| daccel ≤ 0.01 (flat/no accel) | 38 | 37% | -$151 |
| accel_sustained = False | 54 | 43% | -$169 |
| elapsed ≥ 0.85 (late entry) | 27 | 52% | -$113 |
| ob_depth < 500 (thin book) | 20 | 35% | -$86 |

**ETH sub-patterns with negative WR:**
| Sub-pattern | n | WR | Net |
|---|---|---|---|
| imb < 0.30 | 33 | 55% | -$21 |
| tok_d30 in [0, 2%) (flat) | 26 | 38% | -$92 |
| ob_depth < 100 | 11 | 18% | -$65 |

**SOL sub-patterns with negative WR:**
| Sub-pattern | n | WR | Net |
|---|---|---|---|
| elapsed ≥ 0.75 (late entry) | 29 | 65% | -$46 |

**ADDITIONAL DATA (commit `c557252`, May 3 21:31):**
- BOND_EXPIRED_UNSOLD: 42 early-window entries held to expiry → -$310 total
- Fix deployed: T-50s unconditional exit + T-60s sell>0.90 for early entries

**Observations:**
- BTC has the deepest negative sub-pattern pool across 4 distinct filter dimensions
- ETH tok_d30 flat [0,2%) is the sharpest individual signal: WR=38% (n=26, -$92), with negative tok_d30 showing WR=69% → **31pp gap**
- SOL's late-entry loss pool (-$46) is the smallest; fewest filters needed
- Aggregate per-asset WR/PF (not filtered) cannot be computed from commit-embedded fragments

**CONCLUSION: PARTIAL DATA** — Sub-pattern evidence suggests ETH is most sensitive to signal quality (31pp WR swing on tok_d30 direction), BTC requires the most filters, SOL is most tractable overall. No stake reweighting recommendation without aggregate per-asset WR/PF from trades.jsonl.
**FAILURE_MET: Partially** — aggregate per-asset n likely ≥20, but raw per-asset WR/PF unavailable.

---

## New Investigation A: Early-Window Entry Performance (NEW THIS CYCLE — PRIORITY)

**DATA SOURCE:** Commits `8b1605b` (May 3 19:52), `c557252` (May 3 21:31).

**CONTEXT:** Early-window entry feature deployed May 3 19:52 (ask floor 0.52 for elapsed<120s). Within ~99 minutes, a critical exit failure was patched:

- BOND_EXPIRED_UNSOLD (early-window trades held to T-5s with no exit): **n=42, -$310 total**
- Root cause: no exit mechanism existed for positions with 50–180s remaining at parabolic prices
- Fix deployed May 3 21:31: T-50s unconditional exit + T-60s sell>0.90

**HYPOTHESIS:** Post-fix early-window entries (entry_price < 0.80, elapsed < 120s, post May 3 21:31 UTC) have WR and PF comparable to late-window entries (entry_price ≥ 0.80).

**MATH:**
```python
import json, datetime
trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
fix_ts = datetime.datetime(2026, 5, 3, 21, 31).timestamp()
early = [t for t in trades
    if t.get("signal_source") == "BOND" and t.get("is_live") is True
    and t.get("entry_price", 1.0) < 0.80 and t.get("ts", 0) >= fix_ts]
late  = [t for t in trades
    if t.get("signal_source") == "BOND" and t.get("is_live") is True
    and t.get("entry_price", 0.0) >= 0.80]
for label, group in [("early_post_fix (<0.80)", early), ("late (>=0.80)", late)]:
    wins = [t for t in group if t.get("net_pnl", 0) > 0]
    gl = abs(sum(t["net_pnl"] for t in group if t.get("net_pnl", 0) <= 0)) or 1e-9
    gw = sum(t["net_pnl"] for t in wins) or 0
    print(f"{label}: n={len(group)} WR={len(wins)/max(len(group),1):.0%} "
          f"PF={gw/gl:.2f} net={sum(t.get('net_pnl',0) for t in group):+.2f}")
```

**Failure criteria:** WR difference < 5pp between early-post-fix and late entries → early window has no distinct risk profile and can be retained as-is.
**Kill criteria:** Early-post-fix WR < 50% OR PF < 0.90 at n≥20 → remove early-window entry feature entirely.
**Action threshold:** n≥20 early entries after May 3 21:31 UTC.

---

## New Investigation B: Regime Cooldown Calibration

**DATA SOURCE:** Commit `240c68b` (May 3 21:50), 19-day simulation.

**EMBEDDED RESULT:**
- 19-day live simulation: regime cooldown saves ~$221 vs no cooldown
- ~6 T1 triggers/day (≈ once every 4h)
- T1 threshold: net_pnl ≤ -$7 (70% of $10 stake)

**ANALYSIS:**
At ask [0.80, 0.88], $10 stake: typical full loss ≈ -$8.30 (ask 0.83). T1 threshold -$7 triggers on ~50–60% of full losses (ask 0.80–0.84 range). PAE exits are smaller (-$0.50 to -$3.00) and do not trigger T1. T1 therefore targets genuine regime failures (resolved-NO, expired-unsold), not normal variance. Calibration appears reasonable; revalidate at n≥50 real T1 events.

**CONCLUSION: MONITOR** — no gate change warranted. Track T1 trigger count in live session logs.

---

## Priority Signal for Next Implementation

**Signal: Early-Window Entry Validation (Investigation A)**

The early-window feature (ask 0.52–0.79) was deployed May 3 19:52 and immediately produced a -$310 loss cluster from EXPIRED_UNSOLD. The fix (T-50s exit) was deployed at 21:31. At ~7.9 trades/hr and early entries representing an unknown fraction, approximately 2h of post-fix data exists as of 00:12 UTC — likely n=0–5 early entries, below the n=20 threshold.

**Next cycle action:** If trades.jsonl remains inaccessible, check commit messages for any new early-window exit events (BOND_EXPIRED_UNSOLD count, early-entry WR mentions). If data is accessible, run the math above immediately.

**If early-window shows PF < 1.0 at n=20:** revert ask floor to 0.80 unconditionally. The 0.52 floor reaches noise that the TERMINAL signal was not designed to trade.

**If no data accessible next cycle:** No actionable signals — continue data collection. All four mandated investigations INCONCLUSIVE for the 25th consecutive session.

---

## Current Gate Summary (as of 2026-05-04 00:12 UTC)

| Gate | Value | n (embedded) | Status |
|---|---|---|---|
| ask range (late-window) | [0.80, 0.92] | — | LIVE |
| ask range (early-window) | [0.52, 0.92] for elapsed<120s | n=42 pre-fix | LIVE (fix May 3 21:31) |
| snap30 | [10%, 120%) | n=1461 (<10%); n=33 (≥120%) | LIVE |
| snap60 | ≥12% (exempt 0.0) | n=255 2d sim | LIVE |
| tok30 dead zone | skip [18%, 26%) | n=159 PF=0.75 | LIVE |
| binance slow-bleed | skip [-0.05%, -0.02%) | n=233 PF=0.95 | LIVE |
| OB imbalance (global) | ≥0.20 | n=234 PF=1.27 | LIVE |
| OB imbalance (ETH) | ≥0.30 | n=33 WR=55%→gated | LIVE (May 3 19:03) |
| ETH tok_d30 [0, 2%) | blocked | n=26 WR=38% -$92 | LIVE (May 3 19:03) |
| BTC daccel ≤0.01 | blocked | n=38 WR=37% -$151 | LIVE (May 3 19:03) |
| BTC accel_sustained=False | blocked | n=54 WR=43% -$169 | LIVE (May 3 19:03) |
| BTC elapsed ≥0.85 | blocked | n=27 WR=52% -$113 | LIVE (May 3 19:03) |
| BTC ob_depth <500 | blocked | n=20 WR=35% -$86 | LIVE (May 3 19:03) |
| SOL elapsed ≥0.75 | blocked | n=29 WR=65% -$46 | LIVE (May 3 19:03) |
| ask staleness | ≥4s skip | n=72 net=-$35.07 | LIVE |
| scale-in guard | bond_remaining ≥45s | T03169 -$20.86 | LIVE |
| d5s > 25% | blocked | n=49 PF=0.47 | LIVE |
| ETH tok30 ≥100% | blocked | WR=42.9% (n=7) | LIVE |
| BOND blocked hours | {0,2,3,4,5,6,7,17,19,23} UTC | 19 May-3 trades | LIVE |
| PAE | ≥5% adverse 20s continuous | WOP primary SL | LIVE |
| dead-zone filters | range/ER/ATR thresholds=0 | logging only | LOGGING (gates OFF) |
| BOND scale-in | DISABLED | n<100 | DISABLED |
| Regime cooldown | T1≤-$7→5m, T2 2nd≤-$5/30m→10m | 19d sim +$221 | LIVE (May 3 21:50) |
| BOND_TRAIL_TP | REMOVED | costs -$34.18 vs WOP | REMOVED |

---

## Infrastructure Alert — Persistent (24 sessions)

**VPS SSH unreachable from sandbox.** SSH binary absent. No JSONL data retrievable.
Estimated WOP-era (May 1 21:00+) trades inaccessible: **~403**.

**Required action (24th request):** Push recent logs from VPS to branch `claude/find-lag-parameter-rFQ0N`:
```bash
# On VPS: run ONCE
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

Or install as cron (runs every 30 minutes):
```bash
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N 2>/dev/null
```

Without this, all four mandated investigations remain INCONCLUSIVE indefinitely.
