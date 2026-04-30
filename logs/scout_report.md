# Alpha Scout Report — 2026-04-30 00:28 UTC

**Method:** Commit-embedded analysis — VPS SSH unreachable (12th consecutive session)
**Connectivity:** TCP port 22 timeout (EAGAIN); TCP port 80 open but CF WAF returns "Host not in allowlist"; SSH binary absent from sandbox.
**Data sources used:** state_log.md, git commit messages (7f2fdd4→947306c), bankroll.json (saved 2026-04-29 04:59 UTC)
**Bankroll snapshot:** capital=$34.28, total_trades=2025, total_pnl=$99.30, daily_start=$15.95

---

## Investigation 1: Cross-Exchange Lead-Lag

**HYPOTHESIS:** Binance 5s spot momentum at entry (term_spot_delta_5s > 0.05%) predicts higher YES resolution rate — spot rising into window = confirmation bias favors YES at 0.80–0.88.

**STATUS: INCONCLUSIVE — n per bucket < 20**

- `term_spot_delta_5s` was added in commit `947306c` at 12:12 UTC Apr 29 (~12h before bankroll snapshot, ~16h before this report).
- Estimated trades since field went live: ~16h × ~2 trades/hr = ~32 total.
- Spread across 3 buckets (positive/flat/negative): ~10 per bucket maximum.
- n < 20 → no conclusion possible. Anti-sycophancy rule enforced.

**Context from prior proxy (1m kline, reverted at n=43):**
- "both-rising" (Binance 1m + 5m positive, UP-window): n=43, WR=51%
- Other regimes: WR=75–87%
- Gate reverted — cross-strategy contamination could not be ruled out at n=43.

**MATH:** `term_spot_delta_5s = (spot_now - spot_5s_ago) / spot_5s_ago × 100`
**PROPOSED_GATE:** positive/flat/negative split at ±0.05% — do not implement until n≥100 non-zero.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: n/a** — gate cannot be evaluated until n≥100 with field non-zero. Accumulate.

---

## Investigation 2: Tick Count as Toxicity Filter

**HYPOTHESIS:** Low tick count (thin/dead market, 0–2 ticks in 30s pre-entry) predicts lower YES resolution rate. High tick count = informed active flow = edge.

**STATUS: INCONCLUSIVE — no bucket-level data retrievable**

- `term_tok_tick_count_5s` (5s window): **DISCARD** (confirmed prior two cycles — wins and losses share median tick count = 8; zero separation).
- `term_tok_tick_count_30s` (30s window): Added in commit `b5fdc62` (~Apr 28 02:11 UTC → now ~46h old).
  - Estimated total trades with field: ~46h × ~2/hr = ~92.
  - Across 4 buckets (0–2, 3–5, 6–10, 11+): ~23 per bucket average — possibly above n=20.
  - **Critical confound:** snap gates added Apr 29 13:08–19:xx UTC (snap60 < 12% gate blocks zero-momentum entries). Low tick count entries that previously passed are now partially filtered by snap gates. Post-snap-gate tick count distribution is different from pre-gate data used to propose this investigation.
  - Without raw trades.jsonl: cannot bucket or compute WR. Cannot confirm n per bucket.
- **No commit-embedded n counts for this investigation in any of the last 15 commits.**

**PROPOSED_GATE:** min_tick_count_30s = TBD. Evaluate after snap-gate-aware data (post Apr 29 19:xx) accumulates to n≥80 total (≥20 per bucket).

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Not applicable** — n per bucket unverifiable. Note: snap gate interaction may make 30s tick count partially redundant — assess when raw data available.

---

## Investigation 3: Dead Drift Signature

**HYPOTHESIS:** Entries where the YES token price was flat in 30s pre-entry (|term_token_delta_30s| < 0.5% or term_tok_decel_ratio near 0) underperform active-momentum entries. Dead market = no genuine buyer conviction entering the terminal window.

**STATUS: SIGNAL_CANDIDATE — carry forward, not yet gateable**

- `term_tok_decel_ratio` added commit `b5fdc62` (~46h old). Estimated flat-drift TERMINAL trades with this field:
  - Total trades since field: ~92
  - Flat-drift fraction: ~11% (from prior commit `ba2b2f7` context)
  - Flat-drift TERMINAL entries with field populated: ~10
  - **n=10 is far below n≥40 threshold. Cannot gate.**

- Prior embedded signal (from commit `b5fdc62` + prior scout report):

| Population | WR | Source |
|---|---|---|
| Flat token \|d30\| < 0.5% | 53% | commit b5fdc62, n=~subset of 677 (pre-OB-gate era) |
| Overall TERMINAL | 65% | same baseline |

  - 12pp gap exceeds 5pp monitoring threshold. Carries forward.
  - **New context this cycle:** snap60 < 12% gate (added Apr 29 19:xx) now blocks the lowest-momentum entries. Some flat-drift entries may already be caught by snap60 < 12% (both signal low pre-entry momentum). The surviving flat-drift entries that pass snap60 ≥ 12% are a subset with ask price rising (snap60 high) but YES token flat (drift ~0). This is a distinct and potentially interesting population — momentum in the bid/ask spread but not in the token price itself.
  - **Do not gate yet.** Accumulate flat-drift TERMINAL trades post snap-gate era. Flag if term_tok_decel_ratio < 0.10 shows higher WR discrimination than raw |d30|.

**CONCLUSION: SIGNAL_CANDIDATE (carry forward)**
**FAILURE_MET: Not applicable** — n=~10 flat-drift TERMINAL entries, threshold is n≥40. Re-evaluate in ~15h when n≥40 is approached.

---

## Investigation 4: Asset-Specific Edge

**STATUS: INCONCLUSIVE — no per-asset 48h WR/PF/net_pnl breakdown without raw trades.jsonl**

**Available commit-embedded data (48h window Apr 28–30):**

| Asset | Data point | Source |
|---|---|---|
| SOL | Spread analysis n=70 (snap-era Apr28-29): spread 1-2% WR=73%, spread 7-10% WR=33% | commit 55ebdad |
| SOL | SOL H06 WR=29% (n=17) — blocked | commit 9c2dd92 |
| ETH | T02682 flash-crash FP loss $4.90 (BC disable gap bug) — fixed | state_log |
| ETH | TIME_EXIT net=-$17.76 (n=19), DEADLINE net=+$48.54 (n=67) — all assets combined | commit 1912b74 |
| BTC | T02722 snap60 spike (-$2.43 at 19:04 UTC) | commit b2728d9 |
| BTC | T02669 logging bug (cancel-race): exit=0.81 logged, actual fill=0.46, ~-$1.79 real | state_log |

- Total trades in 48h: ~2 trades/hr × 48h = ~96; per-asset split ~32 each.
- n=32 per asset > n=20 threshold, but WR/PF cannot be computed from these data points.
- From CLAUDE.md: BTC historical WR weakest (1.40× score multiplier), ETH discounted (0.90×). No 48h confirmation available.

**CONCLUSION: INCONCLUSIVE**
**FAILURE_MET: Yes** — n≥20 per asset likely met, but per-asset WR/PF uncomputable without raw data. This investigation is structurally blocked until VPS connectivity is restored.

---

## New Signal Investigation: Snap60 Magnitude Band Analysis

**HYPOTHESIS:** Within the currently permitted snap60 range (12–150%), WR is not uniform. There is a momentum sweet spot (likely 20–60%) above which blow-off reversal risk increases, below which conviction is marginal.

**EVIDENCE FROM COMMITS (embedded n counts):**

| snap60 range | WR | Net | n | Status |
|---|---|---|---|---|
| < 5% | 50% | negative | ~8 (5h sample, Apr 29) | BLOCKED since Apr 29 19:xx |
| 5–12% | 55% | net-negative | ~subset of 255 (2d sim Apr28-29) | BLOCKED since Apr 29 19:xx |
| > 150% + stale < 5s | blocked | — | 1 trigger (T02722 BTC) | BLOCKED |
| 12–150% (active zone) | unknown | unknown | ~bulk of entries | **under-analyzed** |

- snap60 > 150% (spike) is gated. snap60 < 12% is gated. The band 12–150% is a wide range with no internal structure examined.
- Hypothesis: 12–40% (confirming momentum, not blowing off) = highest WR. 40–80% = neutral/decreasing. 80–150% = increased reversal risk (partial blow-off).
- Failure criteria: WR spread < 5pp across bands at n≥20 per band.

**MATH:**
```python
# snap60 band analysis — run on VPS with trades.jsonl
import json, statistics
trades = [json.loads(l) for l in open("logs/trades.jsonl") if l.strip()]
bond = [t for t in trades
        if t.get("signal_source") == "BOND"
        and t.get("is_live") is True
        and t.get("term_pre_snap_60s") is not None]

b_low  = [t for t in bond if 12 <= t["term_pre_snap_60s"] < 40]
b_mid  = [t for t in bond if 40 <= t["term_pre_snap_60s"] < 80]
b_high = [t for t in bond if 80 <= t["term_pre_snap_60s"] <= 150]

for label, bucket in [("snap12-40%", b_low), ("snap40-80%", b_mid), ("snap80-150%", b_high)]:
    if not bucket:
        print(f"{label}: n=0")
        continue
    wins = [t for t in bucket if t.get("net_pnl", 0) > 0]
    pnl  = sum(t.get("net_pnl", 0) for t in bucket)
    w_pnl = sum(t["net_pnl"] for t in wins)
    l_pnl = abs(sum(t["net_pnl"] for t in bucket if t.get("net_pnl",0) <= 0))
    pf   = w_pnl / l_pnl if l_pnl > 0 else float("inf")
    print(f"{label}: n={len(bucket)} WR={len(wins)/len(bucket):.1%} PF={pf:.2f} net={pnl:+.2f}")
```

**CONCLUSION: NOT YET RUN** — requires raw trades.jsonl from VPS. Ready to execute immediately on connectivity restore.
**Proposed gate (DO NOT implement until n≥20 per band):** Skip entry if snap60 > 80% (tentative upper bound; symmetric to existing < 12% lower bound). The 12–80% window would define the "confirmed momentum, not reverting" zone.

---

## Secondary Finding: PROFIT_TARGET ×1.12 Live Hit Rate

**HYPOTHESIS (not yet investigated):** The ×1.12 TP was validated on a 2-day simulation (n=255). In live trading post-implementation (Apr 29 ~19:xx UTC), TP hit rate may differ from sim due to slippage, Chainlink resolution timing, and bid liquidity near 0.98+.

**PENDING DATA:** Need `exit_reason == "PROFIT_TARGET"` records from post_exit.jsonl or trades.jsonl (post Apr 29 19:xx UTC). At ~2 trades/hr × 5h = ~10 live trades since implementation. Sim predicted 13/255 = 5% TP hit rate. Expect ~0–1 TP hit in the first 10 trades.

**Action:** Log `exit_reason` field distribution on first connectivity restore. If TP hit rate < 3% at n≥50, revisit TP level (may need lowering to ×1.08 for better fill rate at bid liquidity levels).

---

## Schema Fields Status

| Field | Status | Age | Trades accumulated (est.) | Threshold |
|---|---|---|---|---|
| `term_spot_delta_5s` | Live | ~16h | ~32 total | n≥100 non-zero |
| `term_tok_tick_count_30s` | Live | ~46h | ~92 total | n≥80 total; n≥20/bucket |
| `term_tok_decel_ratio` | Live | ~46h | ~92 total; ~10 flat-drift | n≥40 flat-drift TERMINAL |
| `term_pre_snap_60s` | Live | ~11h (snap-gate era) | ~22 post-gate | n≥20/band for snap60 band analysis |

---

## Priority Signal for Next Implementation

**Snap60 Magnitude Band Analysis — `term_pre_snap_60s`**

Current gate is binary (< 12% skip, > 150% skip). The interior band (12–150%) has no internal calibration. The signal can sharpen the upper bound.

```python
# Proposed gate (DO NOT implement until n>=20 per band):
# Skip if term_pre_snap_60s > 80 AND snap60 is not also gated by spike rule
# Hypothesis: snap60 80-150% = partial blow-off, WR decreasing

# Variable: term_pre_snap_60s (already logged)
# Math: percent change in ask price over 60s pre-entry (backward window)
# Gate direction: SKIP entry if term_pre_snap_60s > threshold_upper
# threshold_upper initial candidate: 80 (based on blow-off theory, needs n>=20 confirmation)

# Failure criteria: WR diff < 5pp between snap80-150% and snap12-40% at n>=20 per band → no gate
# Success criteria: WR diff > 5pp → implement upper bound (recommend snap12-80% as active zone)
```

**Why this is the priority:** snap gates have been the most productive gate category in 48h (snap60<12% removed borderline entries; snap60>150%+fresh caught spike reversals). The logical next step is internal calibration of the permitted zone. Field is already logged. Gate logic is a 2-line addition to existing snap block. No new infrastructure needed.

---

## Infrastructure Alert — Persistent (12 sessions)

**VPS SSH unreachable from sandbox.** All four mandated investigations are structurally blocked. Estimated trade records inaccessible since first failure: ~1,700+.

**Recommended fix (unchanged from prior cycles):** Push log sync from VPS cron every 30 min:
```bash
# /etc/cron.d/push-logs (on VPS — install once)
*/30 * * * * root cd /root/Klaus && tail -5000 logs/trades.jsonl > logs/live_trades_recent.jsonl && git add logs/live_trades_recent.jsonl logs/bankroll.json && git commit -m "log sync $(date -u +\%Y-\%m-\%dT\%H:\%M)" && git push origin claude/find-lag-parameter-rFQ0N 2>/dev/null
```

This is the single highest-leverage infrastructure action available. Until implemented, all quantitative scout investigations remain INCONCLUSIVE by the anti-sycophancy rules.
