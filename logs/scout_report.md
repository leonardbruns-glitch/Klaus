# Alpha Scout Report — 2026-05-03 12:13 UTC

**Method:** Commit-embedded analysis + bankroll.json + state_log.md + git log — VPS SSH unreachable (21st consecutive session)
**Connectivity:** SSH binary absent in sandbox. HTTP port 443 open but Cloudflare WAF "Host not in allowlist". Port 22 actively refused (not timeout) as of Audit-20.
**Data sources:** bankroll.json (saved_ts=1746160000 ≈ May 2 ~21:00 UTC), state_log.md, git commits 73a3140→627c5f3 (May 3 00:20–06:39 UTC).
**Bankroll snapshot:** capital=$37.32 (pre-May-3 session), total_trades=2605, total_pnl=$87.87.

---

## Changes Since Last Scout Report (May 3 00:20 UTC)

| Commit | Change | Embedded n |
|---|---|---|
| `627c5f3` | Min ask 0.75→0.80; BOND blocked hours re-enabled {0,2,3,4,5,6,7,17,19,23} | "All 19 May-3 trades were in blocked hours" (state_log) |

**Key embedded data point:** 19 BOND trades occurred between ~00:20–06:39 UTC, all in the newly re-blocked hour set. This distribution (all 19 trades in {H0,H2,H3,H4,H5,H6,H7,H17,H19,H23}) combined with the user instruction to re-block suggests these hours were loss-generating. Per-trade WR and PnL inaccessible (VPS).

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot momentum (`pre_entry_momentum_pct > 0`) in the 5s before entry predicts higher YES resolution rate.
**MATH:** `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago`

**STATUS: INCONCLUSIVE — 21st consecutive session, no trades.jsonl retrieved.**

Prior cycle established 5m-timeframe analog:

| Binance 5m regime | PF | n | Gate status |
|---|---|---|---|
| Slow bleed [-0.05%, -0.02%) | 0.95 | 233 | GATED (commit 4d0f416) |
| Fast fall (< -0.05%) | 2.31 | ≥20 (exact: VPS-blocked) | UNBLOCKED |
| Flat / positive | unknown | VPS-blocked | accumulating |

The 5s field (`pre_entry_momentum_pct`) remains unmeasured at any bucket level.

**RESULT:** n per 5s momentum bucket = 0 (no trades.jsonl). Cannot bucket.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Not applicable** — data inaccessible. Do not gate on 5s momentum until WOP-era n≥40 per bucket from live data.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low tick count (0–2 ticks in 5s before entry) = thin/dead market predicts lower YES resolution rate.

**STATUS: INCONCLUSIVE — tick count previously found uninformative; still unverified in WOP era.**

Prior finding (cycles 11–12): median tick count = 8 for both wins and losses. Zero WR separation. The related tok30 dead zone [18%, 26%) was gated in commit f874c1d (n=159, PF=0.75) — this is the structural analog to the tick-count hypothesis.

**RESULT:** n per tick bucket = 0 (VPS-blocked).
**PROPOSED_GATE:** Not proposed. Prior all-era data showed no separation. Tok30 dead zone subsumes the low-liquidity failure mode.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Yes (prior era)** — tick count showed <1pp WR spread across buckets in pre-WOP era data. WOP-era re-test pending n≥20 per bucket.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Dead market entries (|term_token_delta_5s| < 0.005) underperform active entries.
**MATH:** `term_token_delta_5s = ask_now - ask_5s_ago`

**STATUS: SIGNAL_CANDIDATE (carries forward) — WOP-era n insufficient.**

Pre-WOP all-era (n=677): WR=53% dead drift vs WR=65% active — **12pp gap, exceeds 5pp threshold.**
WOP-era dead-drift estimated n: ~8–12 (extrapolating ~5% dead-drift rate from estimated ~200+ WOP trades). Gate cannot be set until n≥40.

**New context this cycle:** With min_ask raised to 0.80, the entry pool is narrower. Tokens stalling at 0.80–0.84 are more likely to exhibit dead drift (price commitment is low). The dead-drift signal may be more pronounced in the new ask window — flag for measurement at VPS.

**RESULT:** n=0 (VPS-blocked). WOP-era bucket counts unavailable.
**CONCLUSION: INCONCLUSIVE** (SIGNAL_CANDIDATE from prior era)
**FAILURE_MET: Not yet evaluable** — WOP-era n too small to confirm or deny.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One or more assets (BTC/ETH/SOL) show consistently higher WR/PF in the WOP era, warranting stake reweighting.

**STATUS: INCONCLUSIVE — n < 20 per asset in WOP window (VPS-blocked).**

Prior state_log embedded evidence:

| Asset | Signal | Evidence | Era |
|---|---|---|---|
| ETH | tok_delta_30s ≥ 100% blocked | WR=42.9% (n=7) — Tier 2 | pre-WOP |
| BTC | snap60 [20,30%) tested then reverted | n=18 <30, CI crossed zero | pre-WOP |
| SOL | spread ≤ 3% gate | WR=73% (n=26), spread>3% drag | pre-WOP |

WOP-era per-asset n is unknown. The NEG_RISK_LOCK bug (fixed commit dd3cd5c) contaminated BTC/SOL data on May 2 — 17/21 stuck trades unreliable for per-asset WR calculation.

**RESULT:** No per-asset WOP breakdown available.
**CONCLUSION: INCONCLUSIVE** — n < 20 per asset in clean WOP window. No reweighting recommendation.
**FAILURE_MET: Yes** — insufficient n per asset per anti-sycophancy rules.

---

## New Investigation A: PAE False-Positive Rate (PRIORITY — data accumulating since May 2 21:01 UTC)

**STATUS: PENDING — traj_snaps.jsonl began logging May 2 21:01 UTC (~15h ago as of this report).**

**HYPOTHESIS:** A significant fraction (≥30%) of PAE-20s exits are false positives — the token recovers to profitable resolution within the remaining window time, but we've already exited.

**Why this matters at $10 stake:**
- YES exit (hold to resolution) = walk to 0.99 = +$1.18 typical gain
- PAE fires = exit at bid ≈ entry_price × 0.95 ≈ -$0.50 to -$1.00
- Each false positive costs ~$1.50–$2.00 relative to hold-to-resolution

**MATH:**
```python
import json
from collections import defaultdict

snaps = [json.loads(l) for l in open("logs/traj_snaps.jsonl") if l.strip()]
trades_raw = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
trades = {t["open_ts"]: t for t in trades_raw
          if t.get("signal_source") == "BOND" and t.get("is_live") is True}

pos = defaultdict(list)
for s in snaps:
    pos[s["open_ts"]].append(s)

for thresh in [10, 15, 20, 25, 30]:
    triggered = [ts for ts, slist in pos.items()
                 if any(s.get("pae", 0) >= thresh for s in slist)]
    tp_trades = [trades[ts] for ts in triggered if ts in trades]
    fp = [t for t in tp_trades if t.get("net_pnl", 0) > 0]
    print(f"PAE t>={thresh}s: n_triggered={len(triggered)} "
          f"FP_rate={len(fp)}/{max(len(tp_trades),1)} "
          f"({len(fp)/max(len(tp_trades),1):.0%})")
```

**Failure criteria:** FP rate difference < 15pp across thresholds → 20s is near-optimal; no change.
**Action threshold:** n≥50 traj_snaps positions with pae>0.

---

## New Investigation B: tok30 Interior Bands [0–18%) and [26–30%) — Gap Fill

**STATUS: PENDING — WOP-era data needed.**

Known tok30 structure from commit f874c1d:

| tok30 band | PF | n | Status |
|---|---|---|---|
| [0%, 18%) | unknown | VPS-blocked | may contain loss sub-bands |
| [18%, 26%) | 0.75 | 159 | GATED |
| [26%, 30%) | unknown | VPS-blocked | transition zone |
| ≥30% | 1.05–1.83 | not per-band | UNBLOCKED |

**MATH:**
```python
import json, datetime
trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
wop_epoch = datetime.datetime(2026, 5, 1, 21, 0).timestamp()
bond = [t for t in trades
        if t.get("signal_source") == "BOND"
        and t.get("is_live") is True
        and t.get("ts", 0) >= wop_epoch
        and t.get("term_token_delta_30s") is not None]

bands = [(0,6),(6,12),(12,18),(18,26),(26,30),(30,60),(60,None)]
for lo, hi in bands:
    b = [t for t in bond if
         t["term_token_delta_30s"] >= lo and (hi is None or t["term_token_delta_30s"] < hi)]
    if not b: print(f"tok30 [{lo},{hi}): n=0"); continue
    wins = [t for t in b if t.get("net_pnl", 0) > 0]
    gl = abs(sum(t["net_pnl"] for t in b if t.get("net_pnl", 0) <= 0)) or 1e-9
    gw = sum(t["net_pnl"] for t in wins) or 0
    net = sum(t.get("net_pnl", 0) for t in b)
    print(f"tok30 [{lo},{hi}): n={len(b)} WR={len(wins)/len(b):.0%} PF={gw/gl:.2f} net={net:+.2f}")
```

**Failure criteria:** PF spread across [0–18%) sub-bands < 0.2× → no further granularity needed.
**Action threshold:** n≥20 per band.

---

## Priority Signal for Next Implementation

**Signal: PAE False-Positive Rate Calibration (traj_snaps.jsonl)**

traj_snaps.jsonl has been accumulating since May 2 21:01 UTC (~15h). With ~7.9 trades/hr × ~15h ≈ 118 trades, and estimating ~15–20% trigger PAE, we likely have ~18–24 PAE-triggering positions in traj_snaps. Not quite at n≥50 threshold yet — evaluate again next cycle (~May 4).

**If VPS log sync is deployed before next cycle:** Run Investigation A first. It is the single highest-leverage unmeasured variable — directly controlling exit behavior on every losing position at $10 stake.

**If VPS remains unreachable:** No actionable signals this cycle — continue data collection. All four mandated investigations INCONCLUSIVE due to data inaccessibility, not signal absence.

---

## Current Gate Summary (as of 2026-05-03 12:13 UTC)

| Gate | Value | n (embedded) | Status |
|---|---|---|---|
| ask range | [0.80, 0.92] | pre-0.80 floor performance: VPS-blocked | LIVE (raised 0.75→0.80 today) |
| snap30 | [10%, 120%) | n=1461 sub-10%; n=33 ≥120% | LIVE |
| snap60 | ≥12% (< 0 blocked too) | n=255 2d sim | LIVE |
| tok30 dead zone | skip [18%, 26%) | n=159 PF=0.75 | LIVE |
| binance slow-bleed | skip [-0.05%, -0.02%) | n=233 PF=0.95 | LIVE |
| OB imbalance | ≥0.20 | n=234 PF=1.27 vs lose $22.51 | LIVE |
| ask staleness | ≥4s skip | n=72 net=-$35.07 | LIVE |
| scale-in guard | bond_remaining ≥45s | T03169 -$20.86 causal event | LIVE |
| BOND blocked hours | {0,2,3,4,5,6,7,17,19,23} UTC | 19 May-3 trades in this set | RE-ENABLED today |
| PAE | ≥5% adverse 20s continuous | WOP era primary exit | LIVE |
| ETH tok30 ≥100% | blocked | WR=42.9% (n=7) Tier-2 | LIVE |
| d5s > 25% | blocked | n=49 PF=0.47 | LIVE |
| BOND_TRAIL_TP | REMOVED | costs -$34.18 vs WOP | REMOVED |

---

## Infrastructure Alert — Persistent (21 sessions)

**VPS SSH unreachable from sandbox.** Port 22 actively refused. No JSONL data retrievable. All four mandated investigations remain INCONCLUSIVE by anti-sycophancy rules.

Estimated WOP-era (post May 1 21:00 UTC) trade count: ~7.9/hr × ~63h ≈ **~497 WOP-era trades** completely inaccessible.

**Required action (21st request):**
```bash
# On VPS: run ONCE to push current logs
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json logs/traj_snaps.jsonl
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

Or install as cron (runs every 30 minutes):
```bash
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json logs/traj_snaps.jsonl && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N 2>/dev/null
```

Without this, the quantitative investigations cannot advance beyond commit-embedded fragments.
