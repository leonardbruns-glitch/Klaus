# Klaus Research Audit — 2026-06-19T14:00Z

**Analyst:** Research Strategist (scheduled routine)
**Snapshot:** 2026-06-19T13:33:26Z (age < 1h — FRESH)
**System:** `klaus systemd: active` (uptime since 2026-06-19T00:17:28 UTC)
**Capital:** $281.04 (bankroll.json at snapshot) | $249.75 (gatekeeper 09:00 UTC) | delta +$31 in 4.5h (RECYCLE099 likely)
**CLAUDE.md tables:** drift — band_config.txt authoritative.
**Phase:** 1 (capital $281 < $600 Phase-2 threshold)

**Specialist reports consumed:**
- `exec_audit_report.md` — 2026-06-19 07:07 UTC ✓ VALID (<6h)
- `calib_monitor_report.md` — 2026-06-19 08:03 UTC ✓ VALID (<6h)
- `gatekeeper_report.md` — 2026-06-19 09:00 UTC ✓ VALID (<6h)
- `pnl_ledger_report.md` — 2026-06-18 23:37 UTC ✓ VALID (<36h)

**Data note:** `badatmath_watch.jsonl` most-recent ~100 entries carry all-null fields — the watcher's book-fetch path has failed (likely API schema change or process crash). Fill_join entries from earlier cycles (Wuhan, Atlanta, Miami, Buenos Aires, London — Jun 19 h00-02 UTC) are valid for market intelligence.

---

## 1. Primary Bottleneck for Compounding

**Bottleneck: Turns/day, crushed by a Jun-19 queue stall — $148 idle cash, 91% zero-post rate in hours 00–06 UTC.**

Compounding = ROI/turn × turns/day × equity deployed.

| Lever | Current | Target | Verdict |
|---|---|---|---|
| Turns/day | 0.74× (Jun 18); ~0 in h00-06 today | 1.0× | **Binding — queue stall** |
| ROI/turn (RECYCLE099) | +168% on exits | — | Healthy, not the bottleneck |
| ROI/turn (band resolution) | 0/75 = 0% WR Jun 18 | ~22% design | Broken streak, watch |
| Equity deployed (resting) | 3.2% | ~10-20% | Structurally limited by same-day resolution |

**Evidence (exec_audit §3):** Jun-19 zero-post rate = 91% vs 60-64% prior days. Average books = 0.2/80 — not saturated, not a fill-supply problem. Cash_preskip = $148 (70% of capital present and idle). Yes_resv_skip peaks 10.1/cycle at h05: the skip mechanism consumes the YES allocation without triggering a book poll.

**Root cause (exec_audit diagnosis):** `BAND_NO_CASH_RESERVE=0.30` (introduced Jun 18 15:10) combined with `BAND_PROPORTIONAL_QUEUE=False` (strict rank, same date). The startup burst at h00 posted 9 tokens across 1-2 productive cycles, filling all eligible d+2 YES resting slots. Subsequent cycles find no new eligible slots AND the NO-reserve check gates YES candidates before the book-fetch stage — even with $148 in cash. Hours 04-05 UTC (quietest global window) posted 0 across 23 cycles.

The stall is not cash-starvation, not a calibration failure, and not a fill-supply problem. It is a deployment-mechanics interaction: strict priority queue + large NO reserve + burst-then-nothing pattern in the early morning quiet window. The immediate effect is zero new RECYCLE099 feed from h00-07, and no new YES legs for tomorrow's RECYCLE pool. If sustained, RECYCLE099 exits dry out by Jun 21 when current inventory is exhausted.

**Why not dispersion/calibration as primary?** Dispersion ratio at 0.556 is the deeper structural risk, but it is a slow-moving threat with a gate (the $75 weekly floor and the -20%/month kill switch). The queue stall is operational and acute. Turns/day is the fastest multiplier in the compounding equation.

---

## 2. Existing-System Optimization

### A. Queue stall: yes_resv_skip mechanism starving h00-07 cycles (HIGH impact / LOW effort)

**Finding (exec_audit §3):** Yes_resv_skip = 7.2-10.1/cycle at h01-05; 100% zero-post at h04-05. Cash_preskip = $148 throughout. No_cands = 190+ per cycle (ample NO opportunities, none converting). The skip fires BEFORE the book-fetch stage, so nothing reaches the order placement path.

**Mechanism:** In strict-rank mode (`BAND_PROPORTIONAL_QUEUE=False`), after the startup burst exhausts eligible d+2 YES slots (they're resting), subsequent cycles have no new YES candidates to post. With `BAND_NO_CASH_RESERVE=0.30`, the 30% NO reserve check runs against each YES candidate check — but if the skip counter `yes_resv_skip` is actually counting cycles where NO has no eligible candidates (rather than cycles where YES was gated by the reserve), the skip is a red herring and the real issue is YES slot exhaustion: all eligible d+2 YES slots are already resting in the book, so the cycle finds 0 new slots to quote.

**Expected delta:** Diagnosing and resolving this recovers 60-90 posting cycles/day in h00-07 UTC. Estimated impact: +20-30 fills/day × $3 avg stake = +$60-90 daily YES turnover. RECYCLE099 pipeline remains fed. **Confidence: HIGH (mechanism identified). Effort: LOW (VPS log: add YES headroom $ to [STRUCT-BAND-Q] entry, run 1 cycle).**

### B. NO parity chronic failure: 2-23% share vs ~50% target (HIGH impact / LOW effort)

**Finding (exec_audit §2):** All 5 measurable days below 25% alert threshold. Jun 15 extreme: 4 NO of 182 total posts (2.2%). Live resting book: 1 of 15 orders is NO (6.7%). Config has `BAND_NO_ENABLED=True`, d+1 favNO at rank 0 (highest priority), `BAND_NO_STAKE=5.0`, `BAND_NO_MIN=0.52`. The constraint is upstream of the `post` record.

**Likely mechanism:** `BAND_NO_SKIP_OFF1=True` eliminates ±1 shoulder NO bids. `BAND_NO_MIN=0.52` requires market mode-NO ask ≥ 0.52. Only d+1 favNO fires. If today's d+1 mode-NO asks are clustered below 0.52 (cool cities in June: mode bucket has high YES ask → low NO ask), the fire_no path returns nothing. With `no_cands=190+` per cycle (exec audit), the candidates exist on market but the min-ask filter or the days_out filter is eliminating them before post.

**Expected delta:** Restoring NO to 20-25% share adds ~15 NO fills/day × $5 = $75 daily NO turnover at +3.7% ROI = +$2.75/day net, compounding. More importantly, favNO posts at mode bucket → same-bucket PAIR_FAV opportunities (the merge engine). **Confidence: MEDIUM (mechanism plausible; fire_no path needs skip-reason logging to confirm). Effort: LOW (add reason= field to fire_no skip, 1h VPS).**

### C. Gate 1 (BAND_YES n=4643) and Gate 7 (SUM_POSTED n=2174) stuck at COLLECTING despite decision-grade n (MEDIUM impact / LOW effort)

**Finding (gatekeeper §1,7):** Both gates have n >> 100. Both blocked by Gamma 403 from the cloud container. VPS `band_resolution_join.py` was fixed Jun 17 (state_log) but resolved ROI is not surfacing in data-mirror — either the cron isn't writing back to the mirror branch, or the record types in scope don't include BAND_YES/SUM_POSTED legs.

**Expected delta:** Gate 1 verdict unlocks the scale-up decision (is selection edge +7.6% surviving adverse selection on all fires, not just resolved ones?). Gate 7 verdict answers the bid-ceiling question (is posting YES above 0.70 +EV?). Both have n >> 100 and are artificially blocked. **Confidence: HIGH (cron infrastructure confirmed working). Effort: LOW (VPS: verify cron output format matches data-mirror schema; push resolved ROI file).**

### D. Isotonic refit cron stalled (10 days, no new candidate) (MEDIUM impact / LOW effort)

**Finding (calib_monitor §4):** Candidate file byte-identical to Jun 09 version. The [0.6,0.7) ceiling artifact (p_cal capped at 0.63 vs true WR=0.977) mechanically compresses model-implied sigma, dragging the dispersion ratio lower. New refit on 5 days of fresh data would raise the ceiling and reduce the [0.2,0.4) overconfidence plateau.

**Expected delta:** Not quantifiable without running the refit, but calib report states this ceiling artifact is "the likely cause" of the dispersion ratio compression. If corrected, dispersion ratio could recover from 0.556 toward 0.70+, potentially validating the edge premise. **Confidence: MEDIUM (calibration is improving even without new map). Effort: LOW (VPS cron restart, 10 min).**

### E. Bot restart fragmentation (5+ restarts Jun 18, 80 untracked fill events) (MEDIUM impact / MEDIUM effort)

**Finding (pnl_ledger §2):** Each restart drops in-flight tracker state. 55 non-convergence untracked fills on Jun 18 create a shadow book whose resolution outcome is invisible to the ledger. Capital trajectory ($281 today) includes these shadows.

**Note:** Code change required — outside REPORT-ONLY scope. Flagged for user awareness. The shadow book is the most likely explanation for the capital anomaly ($281 at 13:33 vs $222 end of Jun 18).

---

## 3. Gate Pipeline Review

**No READY, no REJECTED this run. All gates COLLECTING.**

### Gate 2 — BAND_NO_PAIR_FAV (MOST URGENT)

- **n=90** (+8 from prior). ETA ~0.8 days. Will cross 100 today or Jun 20.
- Jun 18 fire_no=20 surge (after Jun 18 21:55 UTC favNO promotion) confirms the mechanism is firing.
- **Key blocker:** Gamma 403 from container → VPS `band_resolution_join.py` must run scoped to `fire_no/pair_fav/pair_samebucket` record types within 24h.
- **Breadth acceleration (no expectancy degradation):** Remove `BAND_NO_SKIP_OFF1=True` specifically for PAIR_FAV same-bucket legs (the YES leg IS the ±1 shoulder; skipping the NO pair of an already-posted ±1 YES leg is overly conservative). This adds ~50% more PAIR_FAV candidates without changing capital risk.
- **Pre-stage now:** Do not wait for n to cross 100 before staging the resolution join. Run the cron manually on the VPS tonight. Gate 2 verdict is the single most actionable data point in the pipeline.

### Gate 1 — BAND_YES (n=4643, n >> 100, CI permanently blocked)

- Accumulating at ~271/day. Scale-up decision waiting on Gamma 403 resolution.
- VPS manual join from Jun 17 (n=3,418, +7.6% conditional YES, every slice +EV) gives a strong prior. Gate needs the *net-of-all-fires* ROI, not just conditional-on-fill.
- No change in status this run.

### Gate 4 — BASKET_EXIT (n=48)

- 16 all-green baskets with t_close tonight/tomorrow (per gatekeeper). If they resolve, n jumps to ~64.
- ETA revised: ~2.4 days (52 more needed at ~19/day, assuming tonight's 16 resolve).
- Cannot accelerate the gate without distorting the all_green criterion. Keep collecting.

### Gate 5 — THERMO_MAKER_NO (STALLED, de-facto dead)

- n=3, WR=1/3, ROI=-64.7%, CI=[−130%, +0.7%]. **0 fills in 7+ days.** 12k+ candidates scanned/day with no materializing fills.
- Kill-gate requires n=20. At 0 fills/day, ETA is infinite.
- **Watch item:** If 0 fills through Jun 23, propose user decision to disable THERMO entirely (free its $15/day daily cap for band allocation). Not a unilateral action — user call.
- One more large loss flips the CI entirely negative. At n=3 this is noise but the directional signal is consistently adverse (2/3 trades are large losses at entries 0.81/0.98).

### Gate 6 — M1_BETA_LOCKOUT (STALLED, n unverified)

- n=31 carries a provenance flag (only 1 M1_BETA_PROBE trade in trades.jsonl; prior n=31 provenance not replicable from available data).
- WR=74.2% / ROI=-0.6% / CI straddles zero. 0 fires in 10+ days. No thin-margin [0.2,0.5)C candidates today.
- Low priority. No action.

---

## 4. Assumption Attack

### Assumption 1: Dispersion premium persists (market σ > true σ → band YES/NO spread profitable)

**STATUS: THREATENED. Ratio 0.556 (new low), every day below 0.60, trending worse.**

Evidence (calib_monitor §3):
- Model-implied σ = 0.842°C. Empirical true σ = 1.515°C. Ratio = 0.556.
- History: Jun 13: 0.62 → Jun 14: 0.835 (brief) → Jun 16: 0.589 → **Jun 19: 0.556 (lowest yet)**.
- All regions below 1.10: US 0.544, EU 0.569, ASIA 0.575. No region close to parity.
- Sign is **inverted**: model prices YES too low relative to true outcome distribution. The band sells implied σ of 0.84°C when the market resolves at 1.52°C — we are underpricing, not overpricing, dispersion.

**What supports it (partially):** Two structural confounders could make the ratio appear worse than the true edge:
1. Isotonic ceiling artifact: p_cal caps at 0.63 for high-confidence buckets (actual WR=0.977). This mechanically compresses model-implied σ. New isotonic refit could raise the ceiling.
2. The market-corrected dispersion ratio (using CLOB book midpoints rather than p_cal) was not computed this session (stwa_ladder_book.jsonl not in the dated subdirectory for calib_monitor). This is Experiment C.

The conditional-on-fill resolution ROI (+7.6%, n=3,418, Jun 17) also partially supports the edge — but that is the *selection* effect (which buckets get filled), not the dispersion premium per se.

**Verdict:** Do not scale YES capital. Treat YES band as fill-rate/merge-inventory play only. Edge verdict deferred to: (a) isotonic refit → see if dispersion ratio recovers, and (b) market-corrected ratio computation (Experiment C).

---

### Assumption 2: Fills are not adversely selected

**STATUS: THREATENED. YES fills: 40% adverse rate, −0.05¢/sh markout. Badatmath: 23% adverse, +1.19¢/sh.**

Evidence (state_log Jun 18 23:30-23:59; exec_audit fill analysis):
- Our YES maker markout by fill age: <5m = +1.57¢ (best), 30m-2h = −0.28¢, >6h = −1.07¢.
- The adverse bleed is **stale-order run-overs**, not queue position. Market trends to our stale price → fill on an informed directional move.
- The 2h reclaim (BAND_RECLAIM_AGE_S=2h) is *protective* — it removes orders before the worst >6h adverse zone. The churn fix (8h for pair legs) is correct for merge pairs (delta-neutral on co-fill).
- Structural: naked directional YES legs with 5% co-fill rate have no adverse-selection defense. Paired legs (badatmath's 40% co-fill) cancel adverse selection on co-fill. Gap cannot be closed without the merge engine (~$2k capital threshold).

**What supports it:** The 2h reclaim is in place. Jun 17 resolution join confirmed selection IS +EV conditional on fill (+7.6%). The adverse hits are concentrated in the >6h zone which is already partially addressed.

**Verdict:** Accept the ~1.3¢/sh adverse gap as structural until the merge engine activates at Phase 2 ($600). YES band posts serve as merge inventory ballast. Do not reduce 2h reclaim (it is protective). Do not lengthen reclaim on lone directional legs (worsens adverse).

---

### Assumption 3: RECYCLE099 velocity scales with position count

**STATUS: SUPPORTED — with a 24-48h dependency risk on YES inventory feed.**

Evidence (pnl_ledger §2 + today's data):
- Jun 17: 20 exits, +$87.45
- Jun 18: 26 exits, +$99.56 (96.6% offset of resolution losses)
- Jun 19 (to 13:33): 14 exit099 entries, capital +$31 vs 09:00 gatekeeper — pace tracking above Jun 17-18.
- Capital recovered from $221.68 (Jun 18 EOD) to $281.04 (Jun 19 13:33) = +$59.36 in ~14h. Attribution: RECYCLE099 exits on inventory accumulated Jun 14-17.

**Dependency:** RECYCLE099 requires existing YES positions to age toward $0.99. The Jun 19 queue stall (91% zero-post h00-07) adds zero new YES inventory today. Yesterday's YES ceiling cut to 0.30 (Jun 18 21:40) means new legs enter at ask 0.05-0.30 — takes 1-3 days to converge to $0.99. If today's stall persists through the peak window (13:00-16:00 UTC), tomorrow's RECYCLE099 feed is thin.

**Verdict:** Healthy for the next 24-48h on existing inventory. Watch exit099_live count. If exits/day drops below 10 by Jun 21, YES inventory is depleting faster than it's being replenished. Resolution of the queue stall is the priority to maintain RECYCLE feed.

---

## 5. Market Census (day-of-month 19 mod 3 = 1: new cities/products, depth changes)

**Source:** band_struct_lite.jsonl (Jun 19 to 13:33), badatmath_watch fill_join records (h00-02 UTC), stwa_ladder_book.jsonl (n=1,485 rows today)

### Cities active in today's posts/fills

**Our posts (band_struct_lite, Jun 19):**
- Taipei d+2 YES (lo 33.5-35.5°C, ask 0.14-0.18, stake $2.10)
- Milan d+1 NO (mode 33.5-34.5°C, ask 0.57, quoted $0.56, stake $5.00)
- Qingdao d+2 YES (sum_gate — 5 legs sum_ask 0.965)
- Cape Town d+2 YES (converged, mode_ask 0.33)
- Manila d+2 YES (converged, mode_ask 0.355)
- Lucknow d+2 YES (converged, mode_ask 0.405)
- Karachi d+2 YES (converged, mode_ask 0.445)

**Competitor fills (badatmath_watch fill_join, Jun 19 h00-02):**
- Wuhan d+0 28-31°C YES: price 0.028-0.31, sizes 1.99-30 sh, detect_lag 22-133s
- Atlanta d+0 86-87°F YES: price 0.23, size 6-52 sh
- Miami d+0 92-93°F YES: price 0.62, size 8-13 sh (high price → favorite mode)
- Houston d+0 90-91°F YES: price 0.43, size 8.77 sh
- NYC d+0 82-83°F YES: price 0.42, size 2.5-9.9 sh
- Buenos Aires d+0 15-17°C YES: price 0.018-0.40, sizes variable
- London d+1 27°C YES: price 0.35, size 3.14 sh
- Wuhan d+1 32°C YES: price 0.38, size 4.08 sh

### Depth snapshot (selected markets, stwa_ladder_book Jun 19)

| Market | Touch bid | Touch ask | Bid depth (3 levels) |
|---|---|---|---|
| Miami 92-93°F | 0.62 | 0.63 | 133.99 + 446 + 71 sh |
| NYC 82-83°F | 0.42 | 0.43 | 195.23 + 320 + 517.59 sh |
| Wuhan 28°C | 0.31 | 0.33 | 38 + 245 + 473 sh |
| Wuhan 30°C | 0.138 | 0.168 | 8 + 8.94 + 30 sh |
| Buenos Aires 15°C | 0.40 | 0.41 | 143.21 + 316 + 198 sh |
| London 27°C d+1 | 0.35 | 0.36 | 100.35 + 555 + 414 sh |

**Deltas vs Jun 16 census:**
- No new cities or product types detected. The 51-city coverage appears unchanged.
- US Fahrenheit depth (Miami, NYC, Houston, Atlanta) remains robust at 100-500 sh at touch — consistent with prior week.
- London d+1 depth (100.35 sh bid at 0.35) is normal; this is a market we could post in.
- **Notable:** Wuhan 28°C has 245+473 sh at bid−1/bid−2 = deep queue below touch. Our YES leg at 0.28-0.31 for d+1/d+2 would have significant queue depth above us. No anomalous depth changes observed.

**badatmath_watch watcher status:** The most-recent ~100 entries carry all-null fields (city, side, ask, bid, delta = null). The watcher process or API schema is broken. Fill_join data from h00-02 remains the last valid competitor intelligence. **VPS fix needed (P4 action).**

**Competitor posture reading from fills:** Wuhan fill_join shows simultaneous 3-bucket fills (28°C, 30°C, 31°C YES) at the same timestamp (detect_lag 54s from first to last fill). This is a multi-leg band sweep across the Wuhan ladder — the competitor (likely badatmath) is posting a full band on resolution resolution of the previous window's temperature. No unusual activity detected vs prior week.

---

## 6. Three Experiments

### Experiment A — Diagnose yes_resv_skip: YES headroom $ vs skip trigger

**Hypothesis:** The yes_resv_skip counter fires because eligible YES slots are fully exhausted (all d+2 YES surface is already resting after the h00 burst), NOT because the 30% NO reserve check is blocking individual candidates. If this is true, the fix is a per-slot dedup check ("skip this cycle if all eligible slots are resting") rather than adjusting the reserve fraction.

**Data:** Add one field to [STRUCT-BAND-Q]: `yes_headroom_usd` (computed YES allocation headroom at the point yes_resv_skip fires). If yes_headroom_usd > $10 and skip still fires → slot exhaustion (all eligible d+2 YES already resting). If yes_headroom_usd < $5 → the reserve fraction IS the gate.

**Time:** 30 min to add log field + 1 cycle to confirm. No trading change.

**Cost:** Zero.

**Success metric:** Clear discrimination between slot-exhaustion and reserve-fraction as the skip cause.

**Decision if slot-exhaustion:** Add per-slot check to skip the cycle gracefully when all eligible YES slots are resting (turns 91% zero-post rate into a correct "idle, nothing to post" state). Decision if reserve-fraction: reduce `BAND_NO_CASH_RESERVE` from 0.30 → 0.15 for h00-08 UTC (low NO candidate window).

---

### Experiment B — Gate 2 pre-stage: BAND_NO_PAIR_FAV verdict by Jun 20

**Hypothesis:** Gate 2 (n=90) crosses 100 tonight. VPS `band_resolution_join.py` runs scoped to `fire_no/pair_fav/pair_samebucket` and produces a CI-cleared ROI verdict by Jun 20 morning, enabling a real scale/kill decision on PAIR_FAV.

**Data:** Verify VPS cron record-type scope covers PAIR_FAV legs (Jun 17 fix was for the BAND_YES join; PAIR_FAV record types may not be in scope). If not, extend. Run manually now.

**Time:** 15 min to verify scope + trigger. 12-24h to get resolved ROI in data-mirror.

**Cost:** Zero.

**Success metric:** Gate 2 CI95 (at n≥100) has lower bound > 0 or upper bound < 0 — a decisive verdict either way.

**Decision if positive (CI LB > 0):** Scale PAIR_FAV — raise BAND_PAIR_FAV_YES_MAX from 0.70, increase stake. This is the merge engine activation that drives turns/day toward his 1.0×. Decision if negative (CI UB < 0): Disable BAND_PAIR_FAV_ENABLED, redirect 30% NO reserve to standalone favNO (validated +3.7%, n=133).

---

### Experiment C — Market-corrected dispersion ratio from stwa_ladder_book

**Hypothesis:** The model-implied dispersion ratio (0.556) is dragged down by the isotonic ceiling artifact. The *market-implied* dispersion ratio (CLOB book midpoints per bucket, not p_cal) may be above 1.10 — which would mean the market is over-dispersed vs true outcomes, the edge IS there, and our model underestimates it (fixable with isotonic refit). If market-implied ratio is also below 0.80, the edge is absent regardless of model quality.

**Data:** `stwa_ladder_book.jsonl` — n=1,485 rows today (in data-mirror shadow). Compute: for each city-day, take last PRE_PEAK record per interior bucket; compute implied σ from book midpoints `(ask+bid)/2`; compare to empirical true σ (1.515°C). This is the "market-corrected" computation the calib_monitor intended but couldn't run (ladder_book not in dated subdirectory at 08:03 UTC snapshot).

**Time:** 2h (Python analysis on VPS, data already available).

**Cost:** Zero.

**Success metric:** Market-corrected ratio > 1.10 on ≥3 of the last 5 days → edge exists at market level, model is the bottleneck (fix: isotonic refit). Market-corrected ratio < 0.80 → market has corrected, edge is structurally gone.

**Decision if yes (ratio > 1.10):** Treat dispersion alert as calibration-artifact, not structural-edge-loss. Prioritize isotonic refit cron restart immediately. Decision if no (ratio < 0.80):** Reduce YES band posting, increase focus on RECYCLE099 velocity as the sole non-calibration-dependent engine; report kill-switch proximity to user for review.

---

## 7. Single Best Action

**Pre-stage Gate 2 resolution join on VPS before n=100 crossing, to enable a BAND_NO_PAIR_FAV verdict by Jun 20.**

**Why this, now:**
1. Gatekeeper report: Gate 2 (n=90) crosses threshold in ~0.8 days. It is the only gate with an imminent, time-sensitive transition.
2. PAIR_FAV is currently operating at **top queue priority (rank 0, d+1 favNO)** with **30% of capital reserved** for it — but without a resolved ROI verdict. This is untested capital allocation at the head of the queue.
3. The verdict is calibration-independent: PAIR_FAV closes by merge (YES+NO co-fill → $0.99 redemption), not by dispersion premium.
4. The VPS infrastructure is confirmed working (Jun 17 state_log: manual run produced n=3,418 joins in one execution). This is not a code problem — it is a cron-scope and scheduling problem.
5. A positive verdict (CI LB > 0) enables scaling the one strategy that directly addresses the turns/day gap (from 0.74× toward 1.0×). A negative verdict enables redirecting the 30% reserve to the validated standalone favNO (+3.7%, n=133). Either outcome improves the system.

**Concrete first step:**
```
# On VPS
cd /root/Klaus
python3 analysis/weather/band_resolution_join.py --record-types fire_no,pair_fav,pair_samebucket
# Verify output written to data-mirror; check data/gatekeeper_gate2.json or equivalent
```
If the script's `--record-types` flag doesn't exist yet, scope it by filtering `band_struct.jsonl` for `reason in ('fire_no', 'pair_fav', 'pair_samebucket')` before the resolution join. This is a 15-minute VPS task.

Do this before going to sleep tonight so the verdict lands in data-mirror by morning.

---

## PROPOSED ACTIONS (human review)

No code changes. No config changes. All below require user decision.

**[P1 — URGENT, tonight]** Pre-stage Gate 2 resolution join on VPS. Scope: `fire_no/pair_fav/pair_samebucket`. Verify data-mirror push. ~15 min. Verdict expected by Jun 20 morning.

**[P2 — HIGH, 30 min]** Diagnose yes_resv_skip cause: add `yes_headroom_usd` to [STRUCT-BAND-Q] log. One-cycle confirmation. Determines whether the fix is reserve-fraction reduction or slot-exhaustion handling.

**[P3 — HIGH, 30 min]** Diagnose NO starvation: add `reason=<skip_reason>` to fire_no path. Identifies the specific gate killing NO candidates before post. Five consecutive days below 25% share with top-rank priority config suggests a hard filter (BAND_NO_MIN=0.52? days_out filter?) is more restrictive than intended.

**[P4 — MEDIUM, 10 min]** Fix badatmath_watch watcher. Most-recent ~100 entries are all-null (city, side, ask, bid). Restart watcher process or patch field extraction on VPS.

**[P5 — MEDIUM, 10 min]** Restart isotonic refit cron (stalled 10 days). Partial fix for dispersion ratio compression artifact. Also enables Experiment C interpretation — if the market-corrected ratio (Experiment C) shows edge, the isotonic refit is the fastest fix.

**[P6 — USER VERIFICATION NEEDED]** Confirm Jun 15-16 RECYCLE099 totals against Polymarket trade history. PnL ledger flagged: 4-day equity is -14.5% (adjusted, below -20% kill trigger) vs -20.8% (raw, at trigger). Gap = Jun 15-16 RECYCLE099. If those two days totaled < $30 combined, the kill switch is technically triggered for the month. User should verify and decide whether to continue under the adjusted frame.

**[P7 — WATCH item, Jun 23]** THERMO_MAKER_NO: 0 fills in 7+ days. If still 0 by Jun 23, propose user decision on disabling. The $15/day daily cap is currently allocated to a strategy with 0 firing rate. Not a unilateral disable — user call.

---

## Appendix: Capital trajectory

| Timestamp | Capital | Source |
|---|---|---|
| Jun 14 EOD | $279.96 | PnL ledger |
| Jun 18 EOD | $221.68 | PnL ledger |
| Jun 19 09:00 | $249.75 | Gatekeeper |
| Jun 19 13:33 | $281.04 | Bankroll.json |
| Jun 14→19 raw Δ | −$0.92 | ~flat (RECYCLE offset) |
| Jun 18→19 (14h) | +$59.36 | RECYCLE099 on prior inventory |

*The +$59 in 14h today is consistent with the RECYCLE099 rate ($87-99/day on 20-26 exits). It draws on YES inventory accumulated Jun 14-17. Tomorrow's RECYCLE rate depends on today's posting velocity — which was near-zero h00-07 (queue stall). Fixing the stall before the Jun 19 peak window (13:00-16:00 UTC) is the fastest way to preserve the inventory pipeline.*

---

*REPORT-ONLY: no code, config, or strategy changes made or recommended for unilateral implementation.*
*All state-altering recommendations listed under PROPOSED ACTIONS require human review.*
*Next scheduled research audit: 2026-06-20 (same window)*
