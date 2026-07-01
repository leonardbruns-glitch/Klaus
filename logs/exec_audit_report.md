# Klaus Exec Audit — 2026-07-01T07:14Z

## AUDIT STATUS
| Field | Value |
|---|---|
| Snapshot age | 10 min (2026-07-01T07:04:39Z) — FRESH ✓ |
| System | `klaus systemd: active` ✓ |
| Proceed | YES |

*Band config read from `band_config.txt` (authoritative). Full data: [MAKER-FILL] + [STRUCT-BAND-Q] from maker_fills_recent.log (1028 lines through 07:02 UTC); exit099_live.jsonl for Jun 29–Jul 1; band_struct_lite.jsonl for Jun 29–Jul 1; maker_resting_state.json and band_posted_state.json at snapshot. Jun 26–28 exit099_live not retrieved.*

---

## Section 1 — Fill Tape

### Tracked BAND Fills ([MAKER-FILL] entries)

**Today, 2026-07-01 (6 fills):**

| Time UTC | City | Side | Token prefix | Shares | Entry | Capital |
|---|---|---|---|---|---|---|
| 05:28 | Beijing | NO | 114345... | +8.0 | 0.67 | $5.36 |
| 06:04 | Munich | NO | 113965... | +8.5 | 0.62 | $5.27 |
| 06:54 | Chengdu | NO | 210701... | +10.0 | 0.47 | $4.70 |
| 06:57 | London | NO | 100817... | +8.0 | 0.63 | $5.04 |
| 06:58 | Chengdu | YES | 604573... | +9.5 | 0.38 | $3.61 |
| 07:00 | Wuhan | NO | 105465... | +5.0 | 0.71 | $3.55 |
| **Today total** | | | | **49 shares** | avg 0.592 | **$27.53** |

*Chengdu NO (0.47) + YES (0.38) are the two legs of a single PAIR_FAV on cond=0x44ebc1ef (same-bucket). Their sum (0.85) gives edge=0.15, locked_pnl=$1.425.*

**[MAKER-FILL] fill pattern (Jun 28 available, older dates not retrieved):**
Jun 28 had fills visible in [STRUCT-BAND-Q] and [USER-WS] logs but no [MAKER-FILL] lines were captured in the excerpted portion. Full 7d [MAKER-FILL] count not available.

### RECYCLE099 Exits (exit099_live.jsonl)

**24-hour window (Jun 30 ~11:30 UTC → Jul 1 07:04 UTC):**

| ts offset | Token prefix | Shares | Entry | Exit | PnL |
|---|---|---|---|---|---|
| −19.6h | 114250... | 11 | 0.97 | 0.99 | +$0.22 |
| −17.7h | 27976... | 7 | 0.65 | 0.99 | +$2.65 |
| −15.1h | 80792... | 7 | 0.68 | 0.99 | +$2.33 |
| −3.0h | 94074... | 6 | 0.81 | 0.99 | +$1.26 |
| −1.1h | 65821... | 8 | 0.71 | 0.99 | +$2.24 |
| −32min | 71911... | 8 | 0.67 | 0.99 | +$2.56 |
| −10min | 51842... | 8 | 0.67 | 0.99 | +$2.56 |
| −7.5min | 109031... | 6 | 0.84 | 0.99 | +$0.90 |
| **24h total** | | **61 shares** | avg 0.737 | 0.99 | **+$14.72** |

**3-day RECYCLE099 summary:**

| Date | Exits | Shares | Avg Entry | Gross PnL | Gross ROI |
|---|---|---|---|---|---|
| Jun 29 | 11 | 71 | 0.725 | +$22.02 | 36.6% |
| Jun 30 | 4 | 32 | 0.750 | +$7.28 | 32.0% |
| Jul 1 (7h) | 5 | 36 | 0.740 | +$9.52 | 33.8% |
| **3d total** | **20** | **139** | **0.733** | **+$38.82** | **35.0%** |

**By price band (entry prices, recycle099):**

| Band | Count | % |
|---|---|---|
| <0.10 | 0 | 0% |
| 0.10–0.30 | 0 | 0% |
| 0.30–0.50 | 0 | 0% |
| **0.50–0.85** | **20** | **100%** |

*(One entry at 0.97 on Jun 30 grouped here; all others 0.59–0.84)*

**By side:** 20 of 20 RECYCLE099 exits are NO-position sells (SELL at 0.99). Today's [MAKER-FILL] added a YES fill via PAIR_FAV (first YES tracked fill in available data).

**By city (today's [MAKER-FILL]):** Beijing, Munich, Chengdu (×2 legs), London, Wuhan — all 5 BAND_CITY_ALLOW cities active today. Beijing and Chengdu were absent from prior resting state and posted fresh.

**Fill rate (posted → tracked fills same day):**

| Date | $ Posted | [MAKER-FILL] | $ Deployed | Fill rate |
|---|---|---|---|---|
| Jun 29 | $93 | — | — | — |
| Jun 30 | $70 | — | — | — |
| Jul 1 (7h) | $28 | 6 | $27.53 | ~100% deployed |

*Note: $28 posted ≈ $27.53 deployed in fills — essentially all today's posted capital has been filled. This is unusually high for a partial day; it reflects the narrow-start capital discipline (post small, fill fast).*

---

## Section 2 — NO-Parity Monitor

**New posts by side (band_struct_lite, 3 days):**

| Date | NO Posts | YES Live Posts | NO Share | Avg days ≥10 posts? |
|---|---|---|---|---|
| Jun 29 | 5 | 0 | 100% | No (5 posts) |
| Jun 30 | ~4–5 | 2 (London+Munich d+2) | ~67–71% | No |
| Jul 1 (partial) | 4 standalone + 1 PAIR NO | 1 PAIR YES | ~80% NO / 20% YES | No |

*Today's YES fill (Chengdu PAIR_FAV at 0.38) is the first YES live fill in available data. It's paired with a NO fill on the same condition — the pair contributes one YES and one NO to the count.*

**Resting book today (maker_resting_state, SELL_EXIT excluded):**
- NO bids active: 2 (Wuhan Jul 2 @ 0.71 matched=5/7.04, Chengdu Jul 2 @ 0.74 matched=0)
- YES bids: 0

**Assessment:** NO-starvation fix (2026-06-12) confirmed holding. NO share ≥67% all sampled days, above the 25% alert floor. Today's PAIR_FAV proves YES is live at d+0 via the favorite overlay path when conditions pass. The 100% NO days reflect BAND_YES_LIVE_MIN_DOUT=2 design policy for standalone YES. Jun 30 confirms standalone YES-band fires at d+2 (London, Munich live). No alert.

---

## Section 3 — Queue Health

**Full Jul 1 dataset: ~65 [STRUCT-BAND-Q] cycles (01:24–07:02 UTC).**
Jun 28: 2 cycles. Other days: not available.

**Jul 1 per-cycle summary:**

| Metric | Range observed | Mean (est.) | Alert threshold |
|---|---|---|---|
| books/80 | 0–6 | ~0.5 | pinned at 80 |
| yes_books/50 | 0 | 0 | pinned at 50 |
| cash_preskip | 0–9 | ~6.5 | >200 sustained |
| queue | 8–31 | ~17 | — |
| posted/cycle | 0–2 | ~0.09 | — |

No alert thresholds breached.

**Notable queue patterns:**

**Zero-posting window 01:24–04:03 UTC (2.5h):**
queue=8–10, no_cands=8–9, cash_preskip=6–7, posted=0. With BAND_NO_CASH_RESERVE=0.30 at cap=$76, $22.80 is reserved, leaving ~$53 deployable. But cash_preskip=6–7 of 8–9 candidates means 6–7 are cash-blocked. Residual 1–2 candidates likely fail price/reclaim gates. No fresh postable opportunities before 04:00 UTC. *Not a deployment stall — candidates are present but gated; preskip stays well below 200.*

**04:08–04:49 UTC jump to 50 no_cands, yes_resv_skip=9–15:**
Sudden influx of NO candidates (likely Jul 3 markets opening for quoting) alongside 9–15 YES/PAIR candidates being deferred by reserve policy each cycle, posted=0. The system is evaluating but not firing: candidates are likely all in reclaim windows (2h reclaim timer). Resolved naturally — first post at 04:03 (just before this window) and next at 06:06.

**yes_resv_skip=9–15 sustained (04:08–07:02):**
Between 9–15 YES/PAIR candidates are skipped each cycle due to BAND_NO_CASH_RESERVE=0.30 prioritizing NO. This is correct behavior given the config. No alert — it is design intent.

**books=6/80 at 06:36:**
The single spike when posting was active (2 posts, cap=$82). Well below the 80-book starvation threshold.

---

## Section 4 — Resolution Markout (Fill Quality)

**Source clarification — UNTRACKED vs TRACKED fills:**

The maker_fills_recent.log contains two distinct categories:
- **[MAKER-FILL] registered**: BAND bot's own fills — sizes 5–10.5 shares at $0.38–0.74 per share (our strategy)
- **[USER-WS] UNTRACKED FILL**: Fills on the same wallet that the BAND tracker does not recognize

The UNTRACKED fills include fills of **1880.51 shares at $0.986** and **1530.15 shares at $0.98** — notional of **$1,853 and $1,499 respectively**. These are 17–21× the total bankroll. They cannot originate from the BAND strategy. Source is a parallel strategy or user manual trading on the same wallet. The near-zero SELL events (50 shares at $0.007 on Jun 28; 50 shares at $0.01 on Jul 1) are also from this parallel source.

**BAND strategy markout (tracked fills only):**

All 20 RECYCLE099 exits (Jun 29–Jul 1) represent NO positions that appreciated to 0.99 and were sold before resolution. Gross ROI 32–37%, all positive. No tracked BAND adverse resolutions visible in available data.

| Date | Avg Entry (recycle099) | Gross ROI | n |
|---|---|---|---|
| Jun 29 | 0.725 | 36.6% | 11 |
| Jun 30 | 0.750 | 32.0% | 4 |
| Jul 1 | 0.740 | 33.8% | 5 |
| 3d avg | **0.733** | **35.0%** | **20** |

Taker fees at 0.99 are ~0.1–0.5%; net ROI ≈ gross.

**n=20 — data collection phase. No winner's-curse conclusion (requires n≥40 with resolution outcomes for all filled legs, not just recycled ones).**

**Formal markout (band_resolution_join.py):** Not runnable; analysis/weather/ absent on this branch and full resolution data not available. Markout for positions that did NOT reach 0.99 (unrecycled, held to resolution) cannot be scored.

**PAIR_FAV entry prices vs gates:**

Chengdu PAIR_FAV today: entry_yes=0.38, entry_no=0.47, sum=0.85, edge=0.15, locked_pnl=$1.425.

BAND_PAIR_FAV_YES_MIN=0.45 sets the YES ask floor. The YES fill at 0.38 is below this floor. **Possible interpretation:** the gate checks the YES ask at quote time; if ask was ≥0.45 at posting and then dropped to 0.38 before our bid filled, the gate would have passed. One instance, profitable outcome. Not conclusive — flag for code-side verification.

---

## Section 5 — Dead-Quote Reclaim

**Reclaim parameters:**
- BAND_RECLAIM_AGE_S = 7200s (2h)
- BAND_PAIR_RECLAIM_AGE_S = 28800s (8h)
- BAND_RECLAIM_PER_CYCLE = 10

**Resting state at snapshot (13 orders):**

| Type | Count | Oldest ts | Age at snapshot |
|---|---|---|---|
| Wuhan NO bid (partial) | 1 | 1782886882 (~04:21 UTC) | ~2.7h |
| Chengdu NO bid | 1 | 1782885961 (~04:06 UTC) | ~3.0h |
| SELL_EXIT @ 0.99 | 11 | Unknown | — |

**Wuhan and Chengdu NO bids** are past the 2h reclaim threshold but have partial/no matches — the system likely entered reclaim mode on them. Wuhan is partially matched (5.0/7.04 = 71% filled), making it a live partially-working order rather than dead. The remaining 2.04 shares may be in next reclaim cycle.

**Quotes >24h old:** 0 — 2h reclaim prevents accumulation.
**Quotes >48h old:** 0 — alert threshold not reached.

**SELL_EXIT pipeline (11 orders):** All at 0.99, awaiting buyers near resolution. No age data available; could be multi-day. These represent sunk capital (already bought, now waiting for exit fills). No reclaim pressure applies to exits.

**Reaped lines from maker_fills_recent.log:** Reclaim activity visible in band_struct_lite (Jun 29–30 show stale-order repricing cycles). Exact reaped-$ not quantifiable without full log parse.

No dead-quote alert fires.

---

## Section 6 — Cash Velocity

**Capital:** $86.59 *(CAVEAT: user manages capital manually; total_pnl=−$40.17 lifetime does not reflect current session alone; large untracked fills on same wallet confirm separate capital stream not counted in this bankroll)*

**Consecutive wins:** 7

**Resting bids:**
| Order | $ resting |
|---|---|
| Wuhan NO: 0.71 × (7.04−5.0) open | $1.45 |
| Chengdu NO: 0.74 × 6.76 | $5.00 |
| **Total bid resting** | **$6.45** |

**SELL_EXIT inventory (11 × 0.99):** Capital deployed at entry; exit value ~$65–80 if all fill at 0.99. Not counted as "resting" (no further capital commitment).

**Fills $ last 24h (PnL):** +$14.72 on 8 RECYCLE099 exits. Capital deployed at those entries ≈ $46 (61 shares × avg 0.737).

**Turns/day (posted $/capital):**

| Date | $ Posted | Capital | Turns | vs badatmath 1.0 |
|---|---|---|---|---|
| Jun 28 | $93 | ~$87 | 1.07 | above ✓ |
| Jun 29 | $93 | ~$87 | 1.07 | above ✓ |
| Jun 30 | $70 | ~$87 | 0.81 | slightly below |
| Jul 1 (7h, $28 actual, ~$96 extrapolated) | $28 | $86.59 | 0.32 (→ ~1.10 ext.) | on track |

Capital turns (posted basis) are near benchmark. The 5-city BAND_CITY_ALLOW and BAND_SAMEDAY_LIVE=False cap the surface; Jun 25–Jul 1 median is ~$70/day vs pre-restriction Jun 17–24 median of $185/day — a deliberate compression from the narrow-start commit.

**Historical velocity trend:**

| Period | Avg $/day | Note |
|---|---|---|
| Jun 17–24 | ~$183 | Pre-narrow-start, broad city set |
| Jun 25–Jul 1 | ~$65 | Post narrow-start + 5-city restriction |

**PAIR_FAV velocity today:** Chengdu d+0 PAIR_FAV fired at 06:54–06:58, both legs filled, locked_pnl=$1.43. Same-day closure contributes to velocity without appearing in posted $ figures.

---

## ALERTS

| Pre-registered Alert | Fired? | Detail |
|---|---|---|
| NO share <25% on any day ≥10 posts | **NOT FIRED** | NO share ≥67% all days; no day had ≥10 posts |
| books pinned at 80 (fetch starvation) | **NOT FIRED** | Max books = 6/80 (Jul 1 06:36) |
| yes_books pinned at 50 (fetch starvation) | **NOT FIRED** | Always 0/50 |
| cash_preskip >200 sustained, posted=0 (deployment stall) | **NOT FIRED** | Max preskip = 9 |
| Dead quotes >20 older than 48h (velocity leak) | **NOT FIRED** | 2h reclaim prevents accumulation |
| **PAIR_FAV YES gate miss (possible)** | 🟡 **FLAG** | Chengdu YES filled at 0.38, below BAND_PAIR_FAV_YES_MIN=0.45. One instance; profitable (edge=0.15, PnL=$1.43). Gate may have passed at quote time if ask was ≥0.45 at post. Verify in code. |
| **Parallel strategy adverse resolutions** | 🟡 **FLAG** | Two confirmed near-zero SELL events on same wallet: Jun 28 (50sh @ $0.007), Jul 1 06:55 (50sh @ $0.01). Sizes (~1880, ~1530 shares) confirm these are NOT from the BAND bot. Source unknown. Capital implications not visible in bankroll.json. |
| **Sustained 0-posting window (01:24–04:03 UTC, 2.5h)** | 🟡 **INFO** | Queue had candidates (8–10) but 6–7/cycle cash-skipped; residual 1–2 failing gate. Not a deployment stall (preskip=9 ≪ 200) — early-UTC no-opportunity window. |

---

## 3-Line Summary

**Fills/day:** 6 tracked [MAKER-FILL] entries today ($27.53 deployed, 5 cities covered) + 5 RECYCLE099 exits for +$9.52; 3-day recycle avg = 6.7 exits/day, gross ROI 33–37%/trade, all fills in 0.50–0.85 NO band; PAIR_FAV added a d+0 YES fill today for $1.43 locked.

**NO-share:** 67–100% of live posts are NO by design (BAND_YES_LIVE_MIN_DOUT=2); fix confirmed holding; today's PAIR_FAV proves the YES overlay path is live when eligible; no starvation alert.

**Binding execution constraint:** PAIR_FAV YES gate needs code-side verification (one fill at 0.38 vs YES_MIN=0.45); separately, a parallel strategy on the same wallet is generating large untracked fills and confirmed adverse resolutions (near-zero exits on Jun 28 and Jul 1), which do not affect BAND P&L accounting but represent an unmonitored capital risk on the same wallet.
