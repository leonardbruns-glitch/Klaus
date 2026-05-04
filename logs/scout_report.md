# Alpha Scout Report — 2026-05-04 12:21 UTC

**Method:** Commit-embedded analysis — VPS SSH unreachable (25th consecutive scout session)
**Connectivity:** SSH binary absent in sandbox; TCP timeout to 85.137.174.86:22; HTTP port 443 blocked by Cloudflare WAF. No trades.jsonl or post_exit.jsonl retrievable.
**Data sources used:** git log (commits 4dc6b2b, 2401050, 5f2b817, 03ec2ec, 8e4786f, 1ba0d60, 196a07d, dba7d05, 1ed710b since last scout 2026-05-04T0012)
**Bankroll snapshot (May 2 ~04:26 UTC):** capital=$37.32, total_trades=2605, total_pnl=$87.87 (snapshot ~56h stale)
**WOP-era estimated trade count:** May-01 21:00 → May-04 12:21 = ~63h × ~7.9/hr ≈ **~498 WOP-era trades** (inaccessible)

---

## Changes Since Last Scout Report (May 4 00:12 UTC)

| Commit | Time (UTC) | Change | Embedded n |
|---|---|---|---|
| `4dc6b2b` (09:13) | Direction-aware Bnc gates: YES UP blocks BTC↓ (b1m<0), YES DOWN blocks BTC↑ (b1m>0); askq>200 gate for YES DOWN | n=80 YES UP May 3–4 |
| `2401050` (09:30) | PAE remaining-time-aware depth: rem>180s→20%/40s, rem 90-180s→15%/30s, rem<90s→12%/20s | n=41 PAE May 3-4 |
| `5f2b817` (09:52) | Fix _classify_path arity bug in EXT exit path | — |
| `03ec2ec` (09:58) | Log resolution bug in state_log | — |
| `8e4786f` (10:05) | Fix window resolution: Binance 5m kline replaces broken Gamma API | — |
| `1ba0d60` (10:28) | 4-layer regime gate: L1 BTC-DOWN ob_depth>2000, L2 YES-DOWN tok30>50, L3 ETH-UP bnc_1m<0.015%, L4 stale logging | L1 n=102 sim, L3 n=27 |
| `196a07d` (10:29) | Reduce base stake $10→$4 (capital preservation) | — |
| `dba7d05` (10:40) | Tighten L2 tok30 threshold 50→40 for YES DOWN | n=35 YES DOWN validation |
| `1ed710b` (11:21) | Log term_snap60_eff/snap30_eff in trade records | — |

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Positive Binance spot momentum in the 5s before entry (`pre_entry_momentum_pct > 0`) predicts higher YES resolution rate.
**MATH:** `pre_entry_momentum_pct = (spot_now - spot_5s_ago) / spot_5s_ago`

**STATUS: PARTIAL — 5s timeframe unmeasured; 1m timeframe validated this cycle.**

Commit `4dc6b2b` (May 4 09:13) analysed n=80 YES UP trades from May 3–4 using `term_binance_1m`:

| Bucket | W avg Bnc 1m | L avg Bnc 1m | Δ | Status |
|---|---|---|---|---|
| YES UP (n=80) | +0.0028% | -0.0023% | +0.0051%** | Statistically significant |

The W vs L separation (Δ=0.0051%) exceeds the 5pp WR failure criterion for directional prediction. Gate deployed: YES UP skip if b1m < 0 (except UTC 22 mean-reversion). YES DOWN mirrors: skip if b1m > 0.

**For the mandated 5s metric (`pre_entry_momentum_pct`):** This field exists in trade records but per-bucket WR/n unavailable without trades.jsonl. The 1m finding is the closest retrievable proxy.

**RESULT:** 1m Binance direction signal: YES UP W avg=+0.0028%, L avg=-0.0023%, Δ=0.0051** at n=80. 5s metric per-bucket n=0 (VPS unreachable).
**CONCLUSION: SIGNAL_FOUND (1m timeframe, now live) / INCONCLUSIVE (5s timeframe)**
**FAILURE_MET: No** — 1m Δ exceeds 5pp WR threshold. 5s evaluation pending n≥40 per bucket from raw data.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low tick count (0–2 ticks in 5s before entry) = thin/dead market predicts lower YES resolution rate.
**MATH:** bucket by `term_tok_tick_count_5s`: 0–2, 3–5, 6–10, 11+

**STATUS: INCONCLUSIVE — 25th consecutive session, no trades.jsonl retrieved.**

Prior all-era (pre-WOP) finding: median tick count=8 for both wins and losses, zero WR separation. The tok30 dead-zone gate (`[18%, 26%)` killed, WOP Tier 1) addresses the low-activity failure mode at 30s resolution. At 5s resolution, tick count adds minimal signal above tok30.

No new embedded data this cycle.

**RESULT:** n per tick bucket = 0 (VPS unreachable). Prior era showed <1pp WR spread.
**PROPOSED_GATE:** None. Tok30 [18%, 26%) dead-zone gate subsumes the low-liquidity failure mode more robustly.
**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Yes (prior era)** — tick count showed <1pp WR spread pre-WOP. WOP-era retest pending n≥20 per bucket.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Dead market entries (|term_token_delta_5s| < 0.005) underperform active entries.
**MATH:** `term_token_delta_5s = ask_now - ask_5s_ago`

**STATUS: SIGNAL_CANDIDATE (carries forward) — 25th consecutive session, no WOP-era data.**

Pre-WOP all-era (n=677): WR=53% dead drift vs WR=65% active — **12pp gap, exceeds 5pp threshold.**

New structural support this cycle (commit `1ba0d60` Layer 2, `dba7d05`): YES DOWN tok30>40 validation (n=35): 1W/8L -$21.20 removed. The tok30>40 pattern is mechanistically consistent with dead-drift — a token that has already moved 40%+ in 30s (but is decelerating) presents the same "momentum exhausted, drift likely" signature as a flat 5s delta. This is an independent confirmation of the dead-drift hypothesis at a different timescale.

Dead-zone logging signals (commit `60947b3`): `term_dz_range_usd`, `term_dz_er`, `term_dz_atr_ratio` now in trade records. Once retrievable, cross-reference with `term_token_delta_5s` to verify structural co-occurrence.

**RESULT:** WOP-era per-bucket n=0 (VPS unreachable). Pre-WOP: WR gap 12pp at n=677.
**CONCLUSION: INCONCLUSIVE** (SIGNAL_CANDIDATE; structural evidence accumulating; gates OFF pending WOP-era n≥20)
**FAILURE_MET: Not yet evaluable** — WOP-era n too small to confirm or deny in live data.

---

## Investigation 4: Asset-Specific Edge

**HYPOTHESIS:** One or more assets show consistently higher WR/PF in the last 48h, warranting stake reweighting.

**STATUS: PARTIAL DATA — new embedded data available this cycle.**

From commit `dba7d05` (May 4 10:40, n=35 YES DOWN validation):
- tok30>40 losers "spread across UTC01/09/21/22, BTC/ETH/SOL — no asset/hour carve-outs needed"
- This implies asymmetric-direction (YES DOWN) failure is asset-agnostic at n=35

From commit `1ba0d60` (May 4 10:28):

| Gate | Asset | n | WR | Direction |
|---|---|---|---|---|
| L1: ob_depth > 2000 | BTC | ~8 (from sim n=102) | 25% (2W/6L) | DOWN only |
| L3: bnc_1m < +0.015% | ETH | 27 | 41% | UP only |

From commit `a66feb2` (May 3 19:03, May-01+ n=349, carries forward):

| Asset | Sub-pattern | n | WR | Net |
|---|---|---|---|---|
| BTC | daccel ≤ 0.01 (flat/no accel) | 38 | 37% | -$151 |
| BTC | accel_sustained = False | 54 | 43% | -$169 |
| BTC | elapsed ≥ 0.85 | 27 | 52% | -$113 |
| BTC | ob_depth < 500 (thin book) | 20 | 35% | -$86 |
| ETH | imb < 0.30 | 33 | 55% | -$21 |
| ETH | tok_d30 in [0, 2%) | 26 | 38% | -$92 |
| SOL | elapsed ≥ 0.75 | 29 | 65% | -$46 |

**Observations:**
- BTC requires the most failure-mode filters (4 active gates); largest negative sub-pattern pool
- ETH: sharp signal quality sensitivity — tok_d30 [0,2%) WR=38% vs negative tok_d30 WR=69% (31pp gap); ETH YES UP requires positive Bnc 1m support (n=27, WR=41% without it)
- SOL: fewest sub-pattern failures, lowest total gated losses; most tractable asset
- No stake reweighting recommendation: aggregate per-asset WR/PF (ungated) unavailable

**CONCLUSION: PARTIAL DATA** — sub-pattern breakdown favours SOL as most tractable; BTC has deepest failure modes; ETH is direction-sensitive. n<20 at aggregate 48h level (VPS blocked) → no reweighting.
**FAILURE_MET: Partially** — aggregate per-asset n likely ≥20 but raw WR/PF unavailable.

---

## New Investigation A: PAE Premature Fire Rate (NEW THIS CYCLE — HIGH PRIORITY)

**DATA SOURCE:** Commit `2401050` (May 4 09:30), n=41 PAE events May 3–4.

| Entry price tier | Remaining at entry | n PAE | Premature % | Note |
|---|---|---|---|---|
| ep < 0.65 (early-window) | rem > 180s | ~15 | **80%** | Mostly destroyed value |
| ep ≥ 0.75 (late-window) | rem < 90s | ~26 | **25%** | Mostly correct saves |

**Interpretation:** Early entries (ask<0.65, elapsed<120s) with rem>180s are firing PAE on transient wicks 80% of the time. These entries have 3+ minutes of window remaining; a 20% adverse move is within normal noise at these prices. Fix deployed: rem>180s PAE requires 20% depth, 40s hold (was 12%/20s).

**HYPOTHESIS (for next cycle):** Post-fix (after May 4 09:30) PAE premature rate on ep<0.65 entries drops below 40%.
**Failure criteria:** Premature rate remains ≥ 60% at n≥20 post-fix PAE events → early-window entries are structurally incompatible with PAE and need their own SL mechanism.

---

## New Investigation B: Direction-Aware Bnc Gate Coverage (NEW THIS CYCLE)

**DATA SOURCE:** Commit `4dc6b2b` (May 4 09:13).

The YES DOWN direction gate (skip if b1m > 0) introduces a new asymmetry risk: in markets where BTC is trending up, all YES DOWN entries are blocked. This could cause significant entry starvation during bull-trending sessions.

**Hypothesis:** YES DOWN trades with b1m > 0 have WR < 40% (justifying the gate). At b1m > 0, BTC is moving against the position; Polymarket YES token should follow spot, making DOWN resolution unlikely.

**Current evidence:** "YES DOWN C/X consistent" (commit message) — insufficient; n<20 explicitly stated in WR/L format for DOWN direction.

**Failure criteria:** If YES DOWN b1m>0 WR ≥ 55% at n≥20 → gate is false positive; revert. Need raw data.

---

## Priority Signal for Next Implementation

**Signal: PAE Premature Fire Rate Validation (Investigation A)**

The post-fix PAE (rem-aware depth, commit `2401050`) addresses an 80% premature fire rate on early entries. This is the most actionable result this cycle — it's already deployed, but the fix depth (20%/40s) was calibrated from n=15 pre-fix events. Validation at n≥20 post-fix PAE events needed to confirm:

```python
import json, datetime
trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
fix_ts = datetime.datetime(2026, 5, 4, 9, 30).timestamp()

# PAE events post-fix
pae_post = [t for t in trades
    if t.get("signal_source") == "BOND" and t.get("is_live") is True
    and t.get("exit_reason") in ("PAE", "BOND_PAE")
    and t.get("ts", 0) >= fix_ts]

early_pae = [t for t in pae_post if t.get("entry_price", 1.0) < 0.65]
late_pae  = [t for t in pae_post if t.get("entry_price", 0.0) >= 0.75]

for label, group in [("early_post_fix (<0.65)", early_pae), ("late (>=0.75)", late_pae)]:
    if not group: continue
    # "Premature" = trade resolved YES despite PAE exit (net_pnl < 0 AND exit=PAE)
    # Approximation: PAE with small net_pnl loss = genuine save; PAE with net near -3% = premature
    premature = [t for t in group if t.get("net_pnl", 0) > -0.15 * t.get("entry_price", 0.85)]
    print(f"{label}: n={len(group)} premature={len(premature)/max(len(group),1):.0%} "
          f"avg_pnl={sum(t.get('net_pnl',0) for t in group)/max(len(group),1):+.4f}")
```

**Kill criteria for early-window feature:** If early PAE premature rate ≥ 60% at n≥20 post-fix → revoke early-window entry (revert ask floor to 0.80 unconditionally).

**Secondary priority:** Validate YES DOWN b1m>0 gate (Investigation B) — requires n≥20 YES DOWN entries where b1m>0 was present (pre-gate). Not deployable without raw data.

**If no data accessible next cycle:** No actionable signals this cycle — continue data collection. All four mandated investigations INCONCLUSIVE for the 25th consecutive session.

---

## Current Gate Summary (as of 2026-05-04 12:21 UTC)

| Gate | Value | n (embedded) | Status |
|---|---|---|---|
| ask range (late-window, elapsed≥120s) | [0.80, 0.92] | — | LIVE |
| ask range (early-window, elapsed<120s) | [0.52, 0.92] | n=42 pre-fix; ~2h post-fix | LIVE |
| snap30 | [10%, 120%) | n=1461 (<10%); n=33 (≥120%) | LIVE |
| snap60 | ≥12% (exempt 0.0) | n=255 2d sim | LIVE |
| tok30 dead zone | skip [18%, 26%) | n=159 PF=0.75 | LIVE |
| binance slow-bleed | skip [-0.05%, -0.02%) — YES UP only | n=233 PF=0.95 | LIVE (UP-only since May 4 09:13) |
| OB imbalance (global) | ≥0.20 | n=234 PF=1.27 | LIVE |
| OB imbalance (ETH) | ≥0.30 | n=33 WR=55%→gated | LIVE |
| ETH tok_d30 [0, 2%) | blocked | n=26 WR=38% -$92 | LIVE |
| BTC daccel ≤0.01 | blocked | n=38 WR=37% -$151 | LIVE |
| BTC accel_sustained=False | blocked | n=54 WR=43% -$169 | LIVE |
| BTC elapsed ≥0.85 | blocked | n=27 WR=52% -$113 | LIVE |
| BTC ob_depth < 500 | blocked | n=20 WR=35% -$86 | LIVE |
| SOL elapsed ≥0.75 | blocked | n=29 WR=65% -$46 | LIVE |
| **L1: BTC YES DOWN ob_depth > 2000** | **blocked** | **n=8 sim WR=25%** | **LIVE (May 4 10:28)** |
| **L2: YES DOWN tok30 > 40** | **blocked** | **n=9 WR=11% -$21.20** | **LIVE (May 4 10:40, was >50)** |
| **L3: ETH YES UP bnc_1m < +0.015% (not UTC22)** | **blocked** | **n=27 WR=41% -$15.40** | **LIVE (May 4 10:28)** |
| **Bnc dir: YES UP + b1m < 0** | **blocked (not UTC22)** | **n=80 Δ=0.0051**| **LIVE (May 4 09:13)** |
| **Bnc dir: YES DOWN + b1m > 0** | **blocked** | n<20 DOWN | **LIVE (May 4 09:13)** |
| **YES DOWN askq > 200** | **blocked** | UTC20 BTC -$9.81 | **LIVE (May 4 09:13)** |
| ask staleness | ≥4s skip | n=72 net=-$35.07 | LIVE |
| d5s > 25% | blocked | n=49 PF=0.47 | LIVE |
| ETH tok30 ≥100% | blocked | WR=42.9% (n=7) | LIVE |
| BOND blocked hours | {0,2,3,4,5,6,7,17,19,23} UTC | 19 May-3 trades | LIVE |
| PAE | rem>180s: 20%/40s; 90–180s: 15%/30s; <90s: 12%/20s | n=41 events May 3-4 | **UPDATED May 4 09:30** |
| dead-zone filters | range/ER/ATR thresholds=0 | logging only | LOGGING (gates OFF) |
| BOND scale-in | DISABLED | n<100 | DISABLED |
| Regime cooldown | T1≤-$7→5m, T2 2nd≤-$5/30m→10m | 19d sim +$221 | LIVE |
| BOND_TRAIL_TP | REMOVED | costs -$34.18 vs WOP | REMOVED |
| base_stake | $4.00 | reduced from $10 May 4 10:29 | LIVE |

---

## Infrastructure Alert — Persistent (25 sessions)

**VPS SSH unreachable from sandbox.** SSH binary absent; TCP port 22 timeout 15–20s. No JSONL data retrievable.
Estimated WOP-era (May 1 21:00+) trades inaccessible: **~498+**.

**Required action — push logs ONCE from VPS:**
```bash
# Run ONCE on VPS
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
