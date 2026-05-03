# Alpha Scout Report — 2026-05-03 00:20 UTC

**Method:** Commit-embedded analysis + bankroll.json + state_log.md + git log — VPS SSH unreachable (19th consecutive session)
**Connectivity:** SSH installed this session (openssh-client apt); port 22 timed out; port 443 open but CF WAF "Host not in allowlist"; no trades.jsonl retrieved.
**Data sources:** bankroll.json (saved ~May 2 06:13 UTC), state_log.md, git commits b9198d3→550202d (May 2 12:13–21:01 UTC), main.py gate configuration.
**Bankroll snapshot:** capital=$37.32 (last known; pre-NEG_RISK_LOCK-fix), total_trades=2605, total_pnl=$87.87, stake=$10.00

---

## Architecture Changes Since Last Report (May 2 12:13 UTC)

Major changes embedded since scout cycle 13:

| Commit | Change | Embedded n |
|---|---|---|
| `4d7511b` | Scale-in guard bond_remaining≥45s; snap30 [10%,120%) unified | snap30<0: n=144 net=-$7.50; [5,10%) n=43 net=-$6.68; [0,5%) n=49 net=+$19.78 |
| `14920e5` | snap30 gate unified to [10%,120%) | <10% n=1461 net-negative; ≥120% n=33 net=-$8.18 |
| `4ed1b99` | Ask floor 0.70→0.75; BOND_TRAIL_TP +10% activation, 5% trail | 0.70–0.75 -$1.34/trade worst bucket |
| `f874c1d` | tok30 [18,26) dead zone blocked | [18,22) PF=0.71 n=71; [22,26) PF=0.78 n=88; combined n=159 PF=0.75 net=-$32.57 |
| `4d0f416` | Binance slow-bleed gate [-0.05%,-0.02%) | n=233 PF=0.95 net=-$8.47; fast falls PF=2.31 |
| `e3f7f7e` | CW=3 pause REVERTED (user) | n=117 PF=0.62 data preserved but gate removed |
| `f91ed67` | All hours unblocked — fresh data accumulation | Prior blocked set {0,2,3,4,5,6,7,17,19,23} preserved in comments |
| `4d1a15a` | Fix: term_ fields lost on restart (24% of data was 0.0) | 451/1877 historical trades had null term_ fields — now fixed |
| `dd3cd5c` | NEG_RISK_LOCK fix | 17/21 May 2 stuck trades were this bug; contaminated BTC/SOL data on May 2 |
| `550202d` | 5s traj_snaps.jsonl logging begins | PAE/MFE/MAE trajectories now accumulating |

---

## Investigation 1: Cross-Exchange Lead-Lag (Binance 5s Momentum)

**HYPOTHESIS:** Positive Binance spot momentum (pre_entry_momentum_pct > 0) in the 5s before entry predicts higher YES resolution rate. Spot rising → YES token resolving correctly.

**STATUS: INCONCLUSIVE — 5s field not directly gated; proxy signal at 5m found and implemented**

**MATH:** `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago` (% change, 5s Binance mid)

**Embedded proxy data (term_binance_5m_pct, n=233 slow-bleed + n=X fast-fall):**

The 5m timeframe analog has been investigated and gated this cycle:

| Regime | PF | n | Status |
|---|---|---|---|
| Spot slow-bleed [-0.05%, -0.02%) | 0.95 | 233 | GATED (commit 4d0f416) |
| Spot fast-fall (< -0.05%) | 2.31 | n≥20 (exact: VPS-blocked) | NOT GATED (profitable) |
| Spot flat / positive | unknown | VPS-blocked | data accumulating |

**Key insight — non-monotonic speed structure:** The direction of spot movement is less predictive than the SPEED. A fast Binance drop (< -0.05%) is strongly profitable (PF=2.31) while a slow bleed (-0.05% to -0.02%) is marginally losing (PF=0.95). Proposed explanation: fast drops are already reflected in the Chainlink snapshot reference; the 5m window's YES/NO determination is anchored to T=-5m price, so a very recent fast drop doesn't shift the 5m bar — the YES token remains likely to resolve correctly. Slow bleeds erode the T=-5m advantage continuously, pulling resolution toward NO.

**5s field (pre_entry_momentum_pct) remains unmeasured:** The 5m signal does NOT answer whether 5s Binance momentum provides additional predictive power. It may be noisy (faster timeframe, more mean-reverting) or may replicate the non-monotonic pattern.

**RESULT:** n per 5s momentum bucket: 0 (VPS unreachable). Cannot bucket by pre_entry_momentum_pct.

**CONCLUSION: INCONCLUSIVE** — 5s field unmeasured. 5m proxy SIGNAL_FOUND and gated.
**FAILURE_MET: Not applicable** — VPS blocked. 5m data gated via separate path. Do not add 5s gate until WOP-era n≥40 per bucket from live data.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low tick count (0–2 ticks in 5s before entry) = thin/dead market predicts lower YES resolution rate.

**STATUS: INCONCLUSIVE — tick count uninformative; related tok30 DELTA signal found and gated**

**Discarded evidence:**
- `term_tok_tick_count_5s`: DISCARDED cycles 11–12. Median tick count = 8 for both wins and losses. Zero separation.
- `term_tok_tick_count_30s`: WOP-era n < 20 per bucket (VPS-blocked). Remains unverifiable.

**Related signal found this cycle — tok30 delta non-monotonic structure (commit f874c1d):**

| tok30 band | PF | n | Status |
|---|---|---|---|
| [18%, 22%) | 0.71 | 71 | GATED |
| [22%, 26%) | 0.78 | 88 | GATED |
| ≥30% | 1.05–1.83 | not reported per band | NOT GATED (profitable) |
| [0%, 18%) | unknown | VPS-blocked | accumulating |
| [26%, 30%) | unknown | VPS-blocked | gap in data |

The tok30 delta signal is NOT the same as tick count (frequency), but it subsumes the spirit of the investigation: mid-momentum tokens (18–26% in 30s) systematically underperform. This is a "partial commitment" pattern — the token has moved enough to look like a strong entry, but not so far that resolution is near-certain.

**PROPOSED_GATE:** min_tick_count_30s = TBD. Do not implement until WOP-era n≥20/bucket (VPS-blocked). The tok30 dead zone gate already captures the related structural failure mode.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Yes — tick count specifically shows no separation. Related delta signal found via tok30.**

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Dead market entries (|term_token_delta_5s| < 0.005) predict lower YES resolution rate vs active entries.

**STATUS: SIGNAL_CANDIDATE — ELEVATED priority; carries forward; contradictory 30s signal noted**

**MATH:** `term_token_delta_5s = ask_now - ask_5s_ago` (absolute price delta, YES token)

**Embedded evidence:**

Pre-WOP all-era (n=677 decomposed): WR=53% dead drift vs WR=65% active — **12pp gap, exceeds 5pp threshold.**
WOP-era dead-drift n: estimated ~8 (unchanged from last cycle). Gate cannot be set until n≥40.

**Contradictory 30s signal from this cycle:**

The snap30 [0,5%) zone (very low token momentum in 30s) was found net=+$19.78 (n=49, PROFITABLE). This is the OPPOSITE of the dead-drift hypothesis at the 30s timeframe — flat tokens in 30s do WELL. This creates a contradiction with the 5s dead drift signal:

| Timeframe | Signal | Direction | n | Conclusion |
|---|---|---|---|---|
| 5s delta |  dead drift WR gap | negative predictor | n=677 pre-WOP | 12pp gap |
| 30s snap | near-zero snap30 (0-5%) | POSITIVE predictor | n=49 | profitable |

Possible resolution: the 30s window measures whether the token has recently started moving toward YES; flat 30s = just starting, fresh entry, good risk/reward. The 5s window measures whether the token is actively trading right now; dead 5s = liquidity vacuum, wide spread, adverse execution.

These may both be correct simultaneously. A token with snap30=+3% and term_token_delta_5s=+0.001 is simultaneously "fresh 30s momentum" and "dead 5s" — different phenomena.

**Under WOP:** dead 5s entry = token not yet committed toward 0.99 → PAE risk higher → EV loss magnified at $10/stake. Priority remains ELEVATED.

**Do not gate.** WOP-era dead-drift n~8. Threshold n≥40. Expected to cross threshold ~May 5 at 7.9 trades/hr × 11% dead-drift rate.

**CONCLUSION: SIGNAL_CANDIDATE — carry forward, contradictory 30s context noted**
**FAILURE_MET: Not applicable** — WOP-era n=~8 dead-drift entries. Threshold n≥40.

---

## Investigation 4: Asset-Specific Edge

**STATUS: INCONCLUSIVE — data contaminated; n insufficient per clean WOP+NEG_RISK_LOCK-fix era**

**Contamination events affecting May 2 per-asset data:**

1. **NEG_RISK_LOCK bug (commit dd3cd5c):** 17/21 stuck trades on May 2 caused by BTC fill locking SOL token as "matched orders." This contaminated BOTH BTC (phantom locked fills) and SOL (failed exits) on May 2. Fix deployed May 2 ~16:XX UTC.
2. **BOND_EXPIRED_UNSOLD stale-bid bug:** EXPIRED_UNSOLD records were incorrectly logged as wins (bid=0.99 from resting PROFIT_TARGET). 4 corrected trades, $37.13 fake-win correction. Affected all assets.
3. **term_ fields lost on restart:** 451/1877 (24%) historical trades logged all term_ fields as 0.0. Fix deployed May 2 17:29 UTC. Per-asset WR/PF computed from this contaminated data is invalid.

**Embedded per-asset fragments (pre-contamination-fix):**

| Asset | Zone | n | WR | Net PnL | Source |
|---|---|---|---|---|---|
| BTC | snap60 [20,30%) | 18 | 67% | -$11.70 | commit 2ec72a9 (pre-WOP) |
| ETH | snap60 [20,30%) | 17 | ~50% | +$1.04 | commit 2ec72a9 (pre-WOP) |
| SOL | snap60 [20,30%) | unknown | 93% | positive | commit 2ec72a9 (pre-WOP) |
| BTC | tok30 dead zone (all) | embedded in 159 total | n/a | n/a | commit f874c1d |

**Note on stake-weighted impact:** At $10/stake, per-asset WR/PF differences translate to large EV gaps. BTC [20,30%) snap60: EV=-$0.64/trade (avg_win=$0.54, avg_loss=-$3.04). But this zone is now fully blocked by snap30 gate [10%,120%) — BTC snap60=25% typically corresponds to snap30 near 10-20% which falls in the dead zone. Gate overlap may eliminate this specific BTC pathology without needing an asset-specific fix.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Yes — n per asset in clean WOP+post-bug-fix era is effectively 0; contamination chain invalidates May 2 per-asset analysis.**

---

## New Investigation A: Binance 5m Non-Monotonic Speed Structure (CARRY FORWARD)

**HYPOTHESIS:** Spot move speed is more predictive than direction. Fast drops before YES entry are profitable (priced into 5m reference); slow bleeds are destructive (continuously erode YES margin); positive momentum unknown.

**EVIDENCE (commit 4d0f416, n=233 slow-bleed, n=X fast-fall):**

| Regime | PF | n | Action |
|---|---|---|---|
| Slow-bleed [-0.05%, -0.02%) | 0.95 | 233 | **GATED** |
| Fast-fall (< -0.05%) | 2.31 | n≥20 | **ALLOWED** |
| Flat / slow-positive (unknown) | ? | VPS-blocked | collecting |
| Fast-positive (> +0.05%?) | ? | VPS-blocked | collecting — likely bad per inverse hypothesis |

**Gap to fill:** The POSITIVE side of `term_binance_5m_pct` is uncharacterized. Strong positive spot 5m momentum may be the worst entry (token has already over-priced the move, reversal risk high) — prior scout report noted inverse-signal hypothesis.

**MATH:**
```python
# Run on VPS against WOP-era trades.jsonl
import json, datetime
trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
wop_epoch = datetime.datetime(2026, 5, 1, 21, 0).timestamp()
bond = [t for t in trades
        if t.get("signal_source") == "BOND"
        and t.get("is_live") is True
        and t.get("ts", 0) >= wop_epoch
        and t.get("term_binance_5m_pct") is not None
        and t.get("term_binance_5m_pct") != 0.0]

bands = [
    ("fast_neg", None, -0.05),
    ("slow_bleed", -0.05, -0.02),
    ("flat", -0.02, +0.02),
    ("slow_pos", +0.02, +0.05),
    ("fast_pos", +0.05, None),
]
for label, lo, hi in bands:
    b = [t for t in bond if
         (lo is None or t["term_binance_5m_pct"] >= lo) and
         (hi is None or t["term_binance_5m_pct"] < hi)]
    if not b: print(f"{label}: n=0"); continue
    wins  = [t for t in b if t.get("net_pnl", 0) > 0]
    net   = sum(t.get("net_pnl", 0) for t in b)
    gross_w = sum(t["net_pnl"] for t in wins) or 0
    gross_l = abs(sum(t["net_pnl"] for t in b if t.get("net_pnl", 0) <= 0)) or 1e-9
    print(f"{label}: n={len(b)} WR={len(wins)/len(b):.1%} PF={gross_w/gross_l:.2f} net={net:+.2f}")
```

**Failure criteria:** No significant PF difference across buckets at n≥20 per bucket (< 0.3× PF spread).

**CONCLUSION: PENDING — positive-regime side unmeasured. Collect WOP-era data and re-evaluate.**

---

## New Investigation B: PAE False Positive Rate via traj_snaps.jsonl (PRIORITY NEW)

**HYPOTHESIS:** The 20s PAE clock is producing a material false positive rate (bid dips ≥5% below entry, clock starts, price recovers before 20s). Under WOP, false PAE exits leave open profit on the table.

**BACKGROUND:**
- BOND_CATASTROPHIC SL was disabled (Apr 29) at 85% FP rate (n=127)
- PAE (≥5% adverse for 20s continuous) was added Apr 30 as a replacement
- Current PAE threshold: 20s continuous
- traj_snaps.jsonl began logging May 2 21:01 UTC: `{open_ts, tok, el, rem, bp, mfe, mae, pae}`
  - `pae` = seconds continuously below entry price

**Why this is the priority new investigation:**
Under WOP at $10/stake:
- YES exit = walk to 0.99 = +$1.25 typical gain
- NO exit = full loss -$8.65 at ask=0.865
- PAE fires when `pae_clock ≥ 20s`
- If PAE has 40%+ FP rate (price recovers), we're exiting profitable positions at -$0.50 to -$1.00 instead of gaining +$1.25 — each FP costs ~$1.75

**MATH:**
```python
# Run on VPS once traj_snaps.jsonl has ≥50 records with pae>0
import json
snaps = [json.loads(l) for l in open("logs/traj_snaps.jsonl") if l.strip()]
# Group by open_ts
from collections import defaultdict
pos = defaultdict(list)
for s in snaps:
    pos[s["open_ts"]].append(s)

# For each position: did pae clock ever exceed 10s? 15s? 20s?
# Cross-reference with trade outcome in trades.jsonl
trades = {t["open_ts"]: t for t in 
          (json.loads(l) for l in open("logs/trades.jsonl") if l.strip())
          if t.get("signal_source") == "BOND"}
          
for thresh in [10, 15, 20, 30]:
    triggered = [ts for ts, slist in pos.items() if any(s["pae"] >= thresh for s in slist)]
    tp_trades  = [trades[ts] for ts in triggered if ts in trades]
    fp = [t for t in tp_trades if t.get("net_pnl", 0) > 0]  # PAE would fire but trade won
    print(f"PAE t≥{thresh}s: n_triggered={len(triggered)} "
          f"FP={len(fp)}/{len(tp_trades)} ({len(fp)/max(len(tp_trades),1):.0%})")
```

**Failure criteria:** If PAE 20s FP rate < 30%, current threshold is acceptable. If FP rate ≥ 50%, reduce to 15s or raise adverse threshold to 8%.
**Threshold to act:** n≥50 traj_snaps positions with pae > 0.

**CONCLUSION: PENDING — data began accumulating May 2 21:01 UTC. Evaluate next scout cycle.**

---

## New Investigation C: tok30 Interior Bands [0-18%) and [26-30%) (GAP FILL)

**HYPOTHESIS:** The tok30 signal has two known profitable zones (0-18% unknown, ≥30% PF 1.05-1.83) and one blocked zone (18-26% PF=0.75). The gap bands [0,18%) and [26,30%) need quantification.

**Evidence gaps from commit f874c1d:**

| tok30 band | PF | n | Status |
|---|---|---|---|
| [0%, 18%) | unknown | VPS-blocked | may include low-momentum entries at risk |
| [18%, 26%) | 0.75 | 159 | GATED |
| [26%, 30%) | unknown | VPS-blocked | transition zone to profitable regime |
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
    wins  = [t for t in b if t.get("net_pnl",0) > 0]
    gross_l = abs(sum(t["net_pnl"] for t in b if t.get("net_pnl",0) <= 0)) or 1e-9
    gross_w = sum(t["net_pnl"] for t in wins) or 0
    net = sum(t.get("net_pnl",0) for t in b)
    print(f"tok30 [{lo},{hi}): n={len(b)} WR={len(wins)/len(b):.0%} PF={gross_w/gross_l:.2f} net={net:+.2f}")
```

**Failure criteria:** If PF difference across [0-18%) and [26-30%) bands < 0.2× → no further granularity needed in the tok30 gate.

**CONCLUSION: PENDING — WOP-era data needed. Run at VPS when n≥20 per band.**

---

## Priority Signal for Next Implementation

**Signal: PAE False Positive Rate Calibration (traj_snaps.jsonl)**

The traj_snaps.jsonl logging started May 2 21:01 UTC. By the next scout cycle (~May 4), there will be ~200 trajectory snapshots with PAE clock values. This is the single highest-leverage unmeasured parameter.

**Variable:** `pae_clock_s` in traj_snaps.jsonl; cross-referenced with trade outcome
**Current threshold:** 20s continuous ≥5% adverse
**Possible adjustment:** If FP rate ≥50% at 20s: raise threshold to 25s or increase adverse threshold to 8%
**Implementation gate:** n≥50 traj_snaps positions with pae > 0

**Python snippet (as above in Investigation B).**

**Failure criteria:** FP rate difference < 15pp across threshold candidates (10s/15s/20s/25s) → 20s is likely already near-optimal. No change.

---

## Current Gate Summary (as of May 3 00:20 UTC)

| Gate | Value | n (embedded) | Status |
|---|---|---|---|
| ask range | [0.75, 0.92] | 0.70–0.75 worst (-$1.34/trade) | LIVE |
| snap30 | [10%, 120%) | n=1461 sub-10%; n=33 ≥120% | LIVE |
| snap60 | ≥12% (< 0 blocked too) | n=255 2d sim | LIVE |
| tok30 dead zone | skip [18%, 26%) | n=159 PF=0.75 | LIVE |
| binance slow-bleed | skip [-0.05%, -0.02%) | n=233 PF=0.95 | LIVE |
| OB imbalance | ≥0.20 | n=234 PF=1.27 vs lose $22.51 | LIVE |
| ask staleness | ≥4s skip | n=72 net=-$35.07 | LIVE |
| scale-in guard | bond_remaining ≥45s | T03169 -$20.86 causal event | LIVE |
| hour blocks | ALL UNBLOCKED | prior set {0,2,3,4,5,6,7,17,19,23} | UNBLOCKED May 2 17:30 |
| BOND_TRAIL_TP | +10% activation, 5% trail | n=16 historical WR=69% | LIVE |
| PAE | ≥5% adverse 20s continuous | WOP era primary exit | LIVE |
| CW=3 pause | REVERTED | n=117 PF=0.62 data preserved | REVERTED |

---

## Infrastructure Alert — Persistent (19 sessions)

**VPS SSH unreachable from sandbox.** Port 22 timed out even with openssh-client now installed. Port 443 open but CF WAF blocks HTTP/HTTPS.

Estimated WOP-era (post May 1 21:00 UTC) trade count: ~2,500 trades at 7.9/hr × ~52h ≈ **~410+ WOP-era trades** completely inaccessible. Every investigation remains INCONCLUSIVE by anti-sycophancy rules.

**All four mandated investigations fail solely due to data access, not signal absence.** The tok30, binance_5m, snap30 discoveries this cycle came from commit-embedded data — a severely information-constrained source.

**Required action (19th request — highest priority in codebase):**
```bash
# On VPS: run ONCE manually or install as cron
*/30 * * * * root cd /root/Klaus && \
  tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && \
  git add logs/live_trades_recent.jsonl logs/bankroll.json logs/traj_snaps.jsonl && \
  git commit --allow-empty -m "log sync $(date -u +%%Y-%%m-%%dT%%H:%%M)" && \
  git push origin claude/find-lag-parameter-rFQ0N 2>/dev/null
```

**Alternative (manual, no cron):**
```bash
# On VPS: push current logs right now
cd /root/Klaus
tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl
git add logs/live_trades_recent.jsonl logs/bankroll.json logs/traj_snaps.jsonl
git commit -m "manual log sync $(date -u)"
git push origin claude/find-lag-parameter-rFQ0N
```

Without this, the quantitative investigations cannot advance beyond commit-embedded fragments.
