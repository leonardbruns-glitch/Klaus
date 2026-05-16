# Alpha Scout Report — 2026-05-16 06:00 UTC

**Method:** Codebase audit — VPS SSH unreachable (63rd consecutive session; TCP port 22 egress blocked from container).
**SSH binary:** not found in PATH. Ports 443/80 open to VPS but no HTTP API available.
**Trade data:** no `trades.jsonl` or `post_exit.jsonl` retrievable. Bankroll snapshot unchanged since 2026-05-08 19:26 UTC (7.8 days stale): capital=$84.61, total_trades=2,605, total_pnl=+$87.87.
**Commits read:** 7f831f0→b8aca4a (13 commits since last scout report at 2026-05-15 12:10 UTC).
**Data sources:** `strategy/late_direction_arb.py`, `analytics/lda_loss_analysis.py`, `data/shadow/timeline.py`, `data/shadow/_schema/v1.json`, `analytics/lda_live_performance.py`, `analytics/lda_asset_window_bnc.py`.

---

## MANDATE SCOPE CONFLICT — READ FIRST

All four investigation mandates target `signal_source == 'BOND'` fields (`term_tok_tick_count_5s`, `ob_imbalance`, `pre_entry_momentum_pct`, `binance_price_at_entry`).

**BOND has been disabled since 2026-05-10.** Every investigation yields n=0 under the strict mandate filter.

This report reframes each investigation for the live LDA strategy and its shadow schema. Field equivalences:

| Mandate field (BOND) | LDA equivalent | Logged in shadow? |
|---|---|---|
| `pre_entry_momentum_pct` | `binance_ret_5m_pct` (IS the primary signal) | yes |
| `term_tok_tick_count_5s` | none exact; proxy: `ask_stale_s` | yes |
| `term_token_delta_5s` | `tok_delta_5s` | yes |
| `binance_price_at_entry` | `binance_spot` | yes |
| `ob_imbalance` | `ob_imb_top3` | yes |

---

## Major Code Changes Since Last Scout Report (13 commits, 2026-05-15 12:10→2026-05-16 06:00 UTC)

| Commit | Change | Scout relevance |
|---|---|---|
| 94946da | **Flat $5 stake per entry, Kelly disabled** | Eliminates BNC-tier differentiation in sizing |
| b8aca4a | **B3 re-enabled; B2/B3 ask floor 0.75→0.55; all kill switches disabled** | Opens uncharted ask [0.55,0.70) zone |
| 8cff3e0 | B2 ask ceiling 0.80→0.85 | Mild expansion of B2 entry space |
| d0b7a18/7f831f0 | Audit no-patches | Infrastructure |

**Critical:** B3 [180,300s) was universally blocked since a prior user instruction. It is now re-enabled with ask floor 0.55. The last data showing B3 performance: ask [0.70,0.75) WR=44.7% n=38 net=-$75. The floor was previously at 0.75. Now it is 0.55, opening ask [0.55,0.70) — **uncharted territory with no shadow evidence.**

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS (LDA reframe):** When `binance_ret_15m_pct` agrees in direction with `binance_ret_5m_pct`, the 5m move is trend-following (durable); when they disagree, the 5m move is counter-trend (reversal risk → lower WR).

**MANDATE RESULT:** n=0 for `signal_source=='BOND'` / `pre_entry_momentum_pct`.

**LDA RESULT:**

`binance_ret_15m_pct` was added to the shadow timeline on 2026-05-15 (commit b8da3a0). The analysis code exists in `lda_loss_analysis.py` section 4i:

```python
# Section 4i (already written, runs on VPS):
aligned   = [v for v in has_15m if (v["bnc_15m"] > 0) == bnc_dir_up(v)]
divergent = [v for v in has_15m if v not in aligned]
```

The field has been in production shadow for ≤24 hours at time of writing. No shadow JSONL is accessible from this container.

**Structural observation (from `data/shadow/timeline.py`):**

```python
binance_ret_15m = self._binance_ret_15m(asset_up)
# = (spot_now - open_15m) / open_15m * 100
# Requires _spot_open_15m cache populated on VPS
```

If `_spot_open_15m` is not warm, the field emits 0.0 (not None). The analysis code treats 0.0 as "no 15m move" and misclassifies those records. Validate that `_spot_open_15m` is non-zero before trusting any 15m alignment analysis.

**MATH:**
```python
bnc_15m_aligned = (
    rec.get("binance_ret_15m_pct", 0.0) * rec.get("binance_ret_5m_pct", 0.0) > 0
)
# True  = both signals same direction (durable momentum)
# False = counter-trend OR 15m flat/cold cache (ambiguous — validate first)
```

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: yes** — field added ≤24h ago; n<20 by definition. Re-run after 2026-05-22. Validate `_spot_open_15m` cache is warm on VPS before trusting results.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS (LDA reframe):** `ask_stale_s` (seconds since token ask last changed) proxies for market activity. High staleness = dead/thin market = entry fills at toxic price = lower WR.

**MANDATE RESULT:** n=0 for `term_tok_tick_count_5s` (BOND-specific field, not in LDA shadow schema).

**LDA RESULT:**

`ask_stale_s` IS logged in the LDA shadow schema (logged in `data/shadow/timeline.py` as `"ask_stale_s": ask_stale_s`). It is loaded in `lda_loss_analysis.py` as `"ask_stale": r.get("ask_stale_s")` and included in the WIN/LOSS feature comparison (FEAT_LABELS row `("ask_stale", "Ask stale (s)")`).

**Critical structural note: dead-market interpretation inverts by ask zone.**

- **B1 high-ask (ask=0.78):** ask moves frequently as late bettors push price. High staleness = stalled consensus = illiquid = bad.
- **B3 low-ask (ask=0.62):** ask may be stale because there is WIDE consensus on direction. Stale at low ask = locked-in price = predictable = potentially good.

No analysis file buckets `ask_stale_s` by ask zone. The feature comparison in `lda_loss_analysis.py` computes a single mean across all ask zones — confounded by the ask zone. The newly-opened B3 ask [0.55,0.70) zone will dominate this confound.

**PROPOSED GATE (requires n_loss ≥ 50 per cell before implementing):**
```python
# Only for B1 high-ask entries:
if rem_bucket == 1 and ask >= 0.75 and ask_stale_s > 30.0:
    return  # dead market at B1 high-ask = toxic entry
# Do NOT apply stale filter at B3 low-ask without separate per-bucket evidence
```

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: yes** — no local shadow data. Run `lda_loss_analysis.py` on VPS and check the `Ask stale (s)` feature row for |Δ| > 20% with n_loss ≥ 20. If found, follow up with per-bucket breakdown before gating.

---

## Investigation 3: Dead Drift

**HYPOTHESIS:** Token price flat before entry (`|tok_delta_5s| < 0.5%`) predicts lower WR vs active entries.

**MANDATE RESULT:** n=0 for `term_token_delta_5s` (BOND-specific field name).

**LDA RESULT:**

LDA shadow field `tok_delta_5s` is the direct equivalent, logged in `data/shadow/timeline.py` as `tok_d5 = (latest_ask - ref5) / ref5 * 100.0`. It is loaded in `lda_loss_analysis.py` as `"tok_delta5"` and included in the WIN/LOSS feature comparison.

The live strategy (`strategy/late_direction_arb.py`) does **not** gate on `tok_delta_5s`. No floor or ceiling is applied.

**Key structural argument: dead drift semantics differ by bucket.**

| Bucket | Dead drift (|tok_delta_5s| < 0.5%) implication |
|---|---|
| B3 [180-300s] | Market hasn't repriced the Binance move yet → front-run opportunity (GOOD signal, not bad) |
| B1 [60-120s] | Market stagnant near resolution → locked consensus or thin liquidity (ambiguous) |
| B0 [8-60s] | Stagnant at high ask → strong consensus, no reversal risk (GOOD) |

**The mandate's gate (skip if dead drift) is structurally INVERTED for B3.** A flat token at B3 with a strong Binance move is exactly the front-run setup LDA is designed to capture: Polymarket hasn't yet digested the Binance signal.

Naively applying `|tok_delta_5s| < 0.005` → skip would block B3 front-run entries where stagnation is the entry signal, not a disqualifier.

**PROPOSED ANALYSIS (run on VPS):**
```python
# Add to lda_loss_analysis.py — bucket tok_delta5 by rem_bucket:
def _rem_bucket(rem):
    if rem < 60: return 0
    if rem < 120: return 1
    if rem < 180: return 2
    return 3

for rb in range(4):
    sub = [v for v in all_rows if _rem_bucket(v["rem"]) == rb]
    dead = [v for v in sub if abs(v.get("tok_delta5") or 0.0) < 0.5]
    active = [v for v in sub if abs(v.get("tok_delta5") or 0.0) >= 0.5]
    for label, group in [("dead", dead), ("active", active)]:
        if len(group) < 5: continue
        wr = sum(v["correct"] for v in group) / len(group)
        print(f"B{rb} {label}: n={len(group)} WR={wr:.1%}")
```

**CONCLUSION: INCONCLUSIVE — AND MANDATE HYPOTHESIS LIKELY INVERTED FOR B3**
**FAILURE_MET: yes** — no local shadow data. However, DO NOT implement the mandate's gate without per-bucket analysis. For B3 entries, the prior expectation is that dead drift is a positive predictor, not negative.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** BTC vs ETH show systematically different WR after current blocking rules; flat $5 stake may be mispriced relative to per-asset edge.

**MANDATE RESULT:** n=0 for 48h BOND data. SOL blocked by user instruction 2026-05-15 (live n=178 WR=53.4% net=-$791). Asset universe is now BTC+ETH only.

**LDA RESULT — Structural analysis from code:**

Per-asset block asymmetry is significant:

| Dimension | ETH blocks | BTC blocks |
|---|---|---|
| B3 [180,300s) hours | H00,H08,H09,H13,H16,H21,H22 = **7 hours** | H01,H04,H08,H18,H21,H23 = **6 hours** |
| B1 [60,120s) hours | H01,H02 (ETH-specific) + ALL_BLOCKED_LATE_B1 | H13 (BTC-specific) + ALL_BLOCKED_LATE_B1 |

ETH has more per-asset B3 blocks (7 hours vs 6), all derived from shadow evidence (e.g., H00 EV=-1.24 n=32, H08 EV=-0.754 n=25). If these blocks are accurate, ETH trades remaining after filtering should show HIGHER WR than BTC (more negatives removed).

**Implication of flat $5 stake (commit 94946da):** Under the previous BNC-tiered Kelly system, HIGH tier (BNC ≥ 0.10%) staked 22% of bankroll (~$18.6 at $84.61). LOW tier (BNC < 0.07%) staked only 1.5% (~$1.27). Flat $5 collapses this 14× range to 1×. LOW tier entries now stake 5/84.61 = 5.9% of bankroll — 4× more than before.

If ETH WR is materially higher than BTC WR (likely given tighter blocking), ETH is under-staked relative to its edge at flat $5. This won't be actionable until n ≥ 20 per asset.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: yes** — n<20 per asset in accessible data. Docstring states combined n=69 direction WR=89.7%. When n ≥ 20 per asset: run `analytics/lda_live_performance.py` on VPS. If ETH WR > BTC WR by ≥ 5pp and n ≥ 20 each, consider a 1.25× multiplier on ETH stake vs BTC.

---

## Priority Signal for Next Implementation

**Risk flag: B3 ask [0.55,0.70) zone opened 2026-05-15 with zero shadow evidence**

This is not a signal to ADD. It is a structural risk opened by commit b8aca4a that must be monitored.

**Context:** The last evidence before the floor change: ask [0.70,0.75) at B3 showed WR=44.7% n=38 net=-$75. The floor was at 0.75 (later briefly at 0.69, then 0.75 again). Now it is 0.55. The ask [0.55,0.70) zone has no shadow record.

**Why the zone MIGHT work:** At ask=0.62, the BNC adaptive floor requires ≥ 0.10% move (raised from 0.07% when ask < 0.70). If LDA WR at strong BNC signals is 90%+, buying at 0.62 and winning at $1.00 is EV = 0.90 × 0.38/0.62 - 0.10 × 1.0 - fee ≈ +0.45 per $ staked. Massive positive EV if WR holds.

**Why it might NOT work:** The token at ask=0.62 is already pricing in 62% certainty. If the Binance signal at BNC 0.10% is less informative than at higher asks (because the market has already partially repriced), WR could be 60-70%, not 90%. At 60% WR: EV = 0.60 × 0.38/0.62 - 0.40 × 1.0 ≈ -0.03 (slightly negative EV after fees).

**Monitoring gate (implement immediately):**
```python
# Variable: b3_low_ask_wr
# In lda_loss_analysis.py — extend section 4b:
b3_low = [v for v in all_rows
          if v["rem"] >= 180 and 0.55 <= v["ask"] < 0.70]
b3_high = [v for v in all_rows
           if v["rem"] >= 180 and 0.70 <= v["ask"] < 0.80]
for label, sub in [("B3 ask[0.55,0.70)", b3_low), ("B3 ask[0.70,0.80)", b3_high)]:
    if not sub:
        print(f"{label}: n=0 (collecting)")
        continue
    wr = sum(v["correct"] for v in sub) / len(sub)
    avg_ask = sum(v["ask"] for v in sub) / len(sub)
    ev = wr * 5.0 * (1 - avg_ask) / avg_ask - (1 - wr) * 5.0
    flag = " *** REVERT FLOOR" if wr < 0.60 and len(sub) >= 20 else ""
    print(f"{label}: n={len(sub)} WR={wr:.1%} avg_ask={avg_ask:.3f} EV/trade={ev:+.3f}{flag}")
```

**Kill trigger:** If shadow or live data shows WR < 0.60 at n ≥ 20 for B3 ask [0.55,0.70), raise ask floor back to 0.70 immediately.

**No implementation this cycle — await shadow data accumulation.**

---

## Secondary Observation: `arb_sum_yes_no` — Unanalyzed Field

`arb_sum_yes_no = YES_ask + NO_ask` is logged in every shadow tick. In a frictionless market it equals 1.0 exactly. In practice:

- arb_sum > 1.05: both tokens overpriced → implicit taker cost above quoted spread → bad for LDA
- arb_sum < 1.00: underpriced → maker opportunity (not our model)

This field appears in `lda_loss_analysis.py` FEAT_LABELS as `("arb_sum", "Arb sum yes+no")` and is included in the WIN/LOSS feature comparison, but **no gate or threshold has been derived from it.** If WIN arb_sum is significantly lower than LOSS arb_sum (|Δ| > 5% with n_loss ≥ 20), entries at high arb_sum are consuming edge through implicit spread cost.

**Proposed check when VPS accessible:**
```python
# From lda_loss_analysis.py output, examine: "Arb sum yes+no | WIN mean/med | LOSS mean/med | Δ"
# If |Δ| > 5% and n_loss >= 20:
#   Proposed gate: skip entry if arb_sum > 1.06
```

Failure criteria: if WIN arb_sum and LOSS arb_sum differ by < 2%, discard.

---

## Cycle Summary

| Investigation | Field | Status | Next action |
|---|---|---|---|
| 1: 15m/5m lead-lag | `binance_ret_15m_pct` | INCONCLUSIVE (field 1 day old) | Re-run 2026-05-22; validate cache warm |
| 2: Tick count / stale | `ask_stale_s` | INCONCLUSIVE (no local data) | Run `lda_loss_analysis.py` on VPS; check ask_stale WIN/LOSS Δ |
| 3: Dead drift | `tok_delta_5s` | INCONCLUSIVE — mandate hypothesis INVERTED for B3 | Per-bucket analysis required; do not gate B3 on dead drift |
| 4: Asset edge | BTC vs ETH WR | INCONCLUSIVE (n<20) | Track as live data accumulates; check at n=20 per asset |

**No actionable signals this cycle.** The highest-priority observation is a risk flag: B3 ask [0.55,0.70) was opened 2026-05-15 with no evidence. Monitor WR accumulation in shadow; if WR < 0.60 at n=20, revert floor to 0.70 immediately.

Continue data collection. Re-run scout after 2026-05-22 when `binance_ret_15m_pct` shadow has 7+ days of records.
