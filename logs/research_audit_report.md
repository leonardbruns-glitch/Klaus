# Klaus Research Audit — 2026-06-27T10:30Z

**Generated:** 2026-06-27T10:30Z  
**Snapshot:** 2026-06-27T10:10:40Z (age: 16 min, FRESH — within 6h gate)  
**Service:** active (restarted 2026-06-26T15:08 UTC after ~49h stall)  
**Capital:** $61.16 (bankroll.json saved_ts ~10:00 UTC)  
**Specialist reports:** exec_audit 07:13 UTC ✓ | calib_monitor 07:54 UTC ✓ | gatekeeper ~10:30 UTC ✓ | pnl_ledger 23:37 UTC Jun 25 (~35h old — borderline; exec_audit supersedes for current state)

---

## ⚠️ PRE-ANALYSIS ALARM

**Gatekeeper explicitly flags:** Bankroll $61.16 vs prior $198.28 = −$137.12 (−69.1%). This breaches:
- CLAUDE.md Rule 4 (Weekly Floor): bankroll < $75 → **HARD STOP, full review**
- CLAUDE.md Monthly Kill Switch: −20% threshold — FAR exceeded
- CLAUDE.md Rolling-20 WR: 5% (1/20) vs 30% flag threshold
- CLAUDE.md Rolling-20 PF: 0.012 vs 0.8 halt threshold

**Bot is live and posting NO despite all kill-switch conditions being met.**  
This is the most important fact in today's data. All analysis below is conditioned on this.

---

## 1. PRIMARY BOTTLENECK FOR COMPOUNDING

**ROI/turn is the binding constraint.** Rank: ROI/turn > equity deployed > turns/day > fills > dispersion.

The exec_audit confirms winner's curse on NO fills: **WR=21.3% on n=89 (post-Jun10, decision-grade boundary)**. Break-even WR at mean fill price $0.63 requires 63%. Net EV per fill: `0.213 × $7.81 − 0.787 × $5.00 = −$2.28/fill`. This is not noise at n=89.

**Capital trajectory:** $198 (Jun 24) → $57 (Jun 27, exec_audit) → $61 (snapshot 10:10, up from Munich YES partial PAIR_FAV fills). The recovery from $57→$61 is from Munich YES pair fills (MAKER-FILL 08:04 + 08:45 UTC, 5.5+3.5sh @ $0.51) — the PAIR_FAV YES leg, not resolution gains.

**Why this is the bottleneck and not frequency or capital:** Turns/day is ~0.81 (exec_audit §6), which is near the badatmath 1.0 benchmark. Capital is $61 with ~$35 free headroom — not the constraint. The product ROI/turn × turns/day × equity is negative because ROI/turn is negative on the STWA_RESOLVED path (−19% per pnl_ledger). No frequency or deployment increase fixes negative expected value.

**Structural cause:** June Northern Hemisphere seasonal heat bias. All 5 BAND_CITY_ALLOW cities (Chengdu, London, Beijing, Munich, Wuhan) are Northern Hemisphere. June = summer peak → temperatures systematically exceed historical band thresholds → YES resolves → NO loses. The fill cadence confirms: 78.7% of settled trades resulted in YES resolution (from exec_audit §4b). This is a directional regime mismatch, not calibration noise.

---

## 2. EXISTING-SYSTEM OPTIMIZATION

**What the four reports collectively imply:**

| Finding | Source | Expected Δ | Confidence | Effort |
|---|---|---|---|---|
| 0 new posts in 81+ Jun-27 cycles — market exhaustion in 5-city set | exec_audit §3 | No new NO exposure today (good, not a bug to fix) | Confirmed | n/a |
| Expanding BAND_CITY_ALLOW would increase posting frequency | exec_audit §3 | +N posts/day but identical or worse WR (same NH summer bias) | High | Easy — but WRONG move |
| BAND_NO_STAKE=$5 is 8.2% of $61 bankroll — stake disproportionate to capital | pnl_ledger §4 | Each new NO fill = catastrophic % loss if resolved against | Confirmed | Stake parameter change |
| RECYCLE099 exits (8 SELL_EXIT resting) are the only profitable path (+33–68% ROI) | exec_audit §4c, pnl_ledger §2 | Letting these resolve at $0.99 recovers $56 notional | High | n/a — already working |
| BAND_NO_MIN=0.52: all fills in 0.52-0.85 band; no sub-band WR granularity available from cloud | exec_audit §1 | Sub-band WR split could isolate better cells — but WR=21% overall makes any sub-band optimization secondary | Medium | Requires VPS-side join |
| Isotonic plateau (0.30–0.90 → 0.38) degrades p_cal utility; candidate map is WORSE | calib_monitor §S4 | Neither map provides useful probability discrimination in the core range | Confirmed | Do not deploy candidate |

**Conclusion for §2:** No existing-system optimization is valid while ROI/turn is negative at n=89. Optimizing post frequency, city list breadth, or stake distribution is rearranging deck chairs. The one optimization that matters is halting new NO exposure until the seasonal hypothesis is validated or falsified.

---

## 3. GATE PIPELINE REVIEW

| Gate | n (current) | +24h rate | Status | Nearest-READY path |
|---|---|---|---|---|
| BAND_YES (d+2) | ~5,924 posted legs | +17–20/day | COLLECTING — CI blocked (Gamma 403 from cloud) | VPS-side band_resolution_join.py already has n=3,418 resolved at YES +7.6% per Jun-17 state_log. Human needs to run VPS-side CI check. |
| BAND_NO_PAIR_FAV | ~227 | +10–14/day | COLLECTING — CI blocked | Same VPS dependency |
| FILLED_VS_FIRED | ~37 (shrunk from 97 via 49h stall + 7d rollover) | 0 new posts today | COLLECTING — CI blocked | Needs fresh fills; 49h stall gap hurt this counter badly |
| THERMO_MAKER_NO | 3 | 0 (paused) | STALLED — engine off since Jun 23 | Requires THERMO_MAKER_LIVE=True; n=3 start; WR=0.333, CI [−132.6%, +0.7%] at n=3 → near-REJECTED once n accumulates |
| M1_BETA_LOCKOUT | 31 | 0 (stalled) | **AMBIGUOUS → recommend REVERT** | metar_lockout.jsonl shadow absent 15+ days; standing rule triggered |
| SUM_POSTED [0.70,0.85] | ~2,958 | +4/day | COLLECTING — CI blocked | Same VPS dependency |

**Acceleration levers (without degrading expectancy):**
- BAND_YES gate is the most actionable. VPS has n=3,418 with CI data. One human check of VPS-side band_resolution_join.py output could declare this gate READY or REJECTED today. This is the fastest path to a positive-EV live leg.
- FILLED_VS_FIRED: n fell from 97→37 due to stall. Resuming any posting (even YES) will replenish this counter. Do NOT expand posting solely to push this counter — the underlying fill quality is the variable.

**M1_BETA_LOCKOUT:** Standing-rule action flagged by gatekeeper (ACTION 1): revert METAR_LOCKOUT_TEMP_FLOOR to 0.5°C. n=31, stalled, shadow logger absent. At n<100 and >14 days of no new data, continuing the experiment consumes nothing but blocks the floor parameter from being useful. See PROPOSED ACTIONS below.

---

## 4. ASSUMPTION ATTACK

The three load-bearing assumptions of the BAND-V3 system today:

**A. Dispersion premium persists** (market-implied σ > true realized σ → YES/NO band prices are mispriced in our favor)
- Calib monitor: **ALERT — ratio_7d = 0.75 (threshold ≥1.10)**. Model-implied σ=0.84°C < realized miss error=1.00°C across all regions (US=0.65, EU=0.80, Asia=0.79).
- Critical caveat (calib_monitor §S3): This measures p_cal-implied σ, NOT market ask-implied σ. The isotonic plateau (0.30–0.90 all → p_cal=0.38) artificially compresses p_cal, understating model-implied σ. The true market-implied dispersion from book asks is unmeasurable until `book_mid` is logged.
- **Verdict: UNVALIDATED. Cannot confirm or deny the dispersion premium without book_mid data. The ratio=0.75 from model probabilities is a warning signal, not a falsification — but the assumption is not supported by current evidence.**

**B. Fills are not adversely selected** (maker NO bids are hit by uninformed flow, not by counterparties who know the temperature is running hot)
- Exec audit: WR=21.3% (n=89, post-Jun10), break-even=63%. EV=−$2.28/fill. Winner's curse alert FIRES.
- Jun 21–25 daily table: STWA_RESOLVED losses $278 vs exit099 gains $266 over 5 days. 20/20 consecutive STWA_RESOLVED losses (pnl_ledger).
- badatmath_watch (today): badatmath is buying YES (Miami YES @ $0.06, Seoul YES, Denver YES). badatmath may literally be the counterparty hitting Klaus's resting NO bids — they have a systematic YES-bias in June that is the informed side of the trade.
- **Verdict: DEFINITIVELY BROKEN at n=89. The NO bids are being hit by informed YES-buyers in a June NH summer regime. This assumption failure is the root cause of all capital loss.**

**C. Recycle velocity scales** (exit099 path generates sufficient returns to offset losses and compound capital)
- Exec audit §4c: exit099 ROI positive across all price bands (+627% at <$0.50, +68.8% at $0.50–$0.65, +44.8% at $0.65–$0.79, +5.6% at >$0.85). 4 exits/day on a 6h active Jun-25 session.
- Structural math (pnl_ledger §5): Each STWA_RESOLVED loss = $5-6. Each RECYCLE099 gain = $2-3. Break-even requires >2 RECYCLE exits per STWA_RESOLVED loss. Jun-25: 4 RECYCLE exits vs 4 STWA losses → precisely at break-even. In higher-loss days (16 STWA losses Jun-24), the math is structurally negative regardless of RECYCLE velocity.
- **Verdict: RECYCLE path is profitable and reliable. However, it cannot scale to offset STWA_RESOLVED losses at the current fill rate. The path HOLDS in isolation but fails as a standalone compounding strategy when STWA_RESOLVED losses 2.4x the RECYCLE gains.**

---

## 5. MARKET INTELLIGENCE (Day 27 mod 3 = 0 → Competitor Posture)

**badatmath_watch Jun 26–27 deltas (from shadow_summary.json hot/ excerpts):**

| Date | Record | City | Outcome | Price | Detect Lag |
|---|---|---|---|---|---|
| Jun 26 (first) | fill_join | Denver 86-87°F | YES | $0.33 | 129.9s |
| Jun 26 (last) | fill_join | Seoul Jun 26 | YES | — | 57.5s |
| Jun 27 (first) | fill_join | Miami 88-89°F | YES | $0.06 | 141.7s |
| Jun 27 (last, ~10:06 UTC) | ladder scan | Helsinki Jun 28 | — | — | building book |

**Key observations:**
1. badatmath is trading YES in June (opposite side to Klaus's NO). Their fills are in cheap YES buckets ($0.06 at Miami = very long shot) — consistent with the PAIR_FAV YES strategy of picking off mispriced tails.
2. Detect lag 57–142s: within the 30s–2min macro edge window but this is for weather markets, not macro news. Their lag is market scanning lag, not information lag.
3. badatmath is building the Helsinki d+1 book at 10:06 UTC — the exact d+1 horizon that Klaus's BAND_NO_MIN_DOUT=1 gates cover. They are scanning the same markets Klaus would post NO on.
4. **Structural competitor insight:** badatmath (YES-buyer) is the most likely counterparty to Klaus's resting NO bids. When Klaus posts NO at $0.70 (YES equivalent: $0.30), badatmath buys the YES at $0.30 as part of their YES-scanning strategy. Klaus's band is providing badatmath with cheap YES liquidity in a summer regime where YES is mispriced cheap by Klaus but correctly priced as a buy by badatmath.
5. **Leaderboard delta:** badatmath fill sizes $0.35–$1.19/fill (small), consistent with maker accumulation. Volume appears lower than the Jun-17 state_log mentions ($4.2M/yr top wallets). No new leaderboard data accessible from cloud.

---

## 6. THREE EXPERIMENTS

### Experiment 1 — Hemisphere Segmentation (Seasonal Adverse Selection Test)
**Hypothesis:** The winner's curse is latitude-specific. Northern Hemisphere cities in June (summer, above-historical temps) → YES resolves → NO loses. Southern Hemisphere cities in June (winter, below-historical temps) → NO should resolve → SH NO has a positive edge offset to current WR.  
**Data needed:** Join 89 NO-fill resolved trades (trades.jsonl) with city hemisphere metadata. Split WR by NH vs SH. VPS-side analysis only (full trades.jsonl, Gamma resolution join).  
**Time/cost:** 1 VPS-side Python analysis run, ~30 min, zero capital.  
**Success metric:** SH NO WR ≥40% at n≥20 (trend-grade) with CI clearing zero.  
**Decision-if-yes:** BAND_CITY_ALLOW = {Buenos Aires, São Paulo, Sydney, Cape Town, +other SH cities}; BAND_NO_ENABLED=True for SH only. Resumption with empirical edge.  
**Decision-if-no:** Adverse selection is universal (not seasonal) → model failure, not seasonal bias → deeper strategy review before any resumption.  
**Value-of-information:** High. Separates a recoverable regime-mismatch from a fundamental strategy failure.

---

### Experiment 2 — VPS YES Gate CI Check (Fastest Path to Positive-EV Live Strategy)
**Hypothesis:** The BAND_YES gate at d+2 has positive EV already (state_log Jun-17: YES +7.6%, n=3,418 VPS-computed). Cloud can't access Gamma to compute this — but the VPS already has it. If CI clears zero, live YES posting at d+2 can resume using the mirrored YES strategy with a clean adverse-selection profile (badatmath is successfully buying YES in this market).  
**Data needed:** Human runs VPS-side `band_resolution_join.py --gate BAND_YES` and reports WR, ROI, CI95.  
**Time/cost:** 10 min VPS shell time, zero capital, n=3,418 exists.  
**Success metric:** CI95 lower bound > 0 on YES ROI (one-tailed: YES has positive expected return).  
**Decision-if-yes:** Enable BAND_YES live at d+2, BAND_BASE_STAKE=$1 (reduced from $3), 20-fill live validation before scaling. Simultaneously set BAND_NO_ENABLED=False.  
**Decision-if-no:** YES edge was illusory at n=3,418 — pause all band trading and conduct full strategy review.  
**Value-of-information:** Highest. This is the single most decision-ready piece of data in the system and it's sitting idle on the VPS.

---

### Experiment 3 — book_mid Logging for True Dispersion Gauge
**Hypothesis:** True market-implied σ (from book ask prices at each pricer eval snapshot) exceeds the 1.10 threshold for the dispersion gauge. The current ratio=0.75 uses p_cal as a proxy for market-implied σ, but the isotonic plateau makes p_cal a poor proxy. If the market correctly prices higher uncertainty than p_cal implies, the dispersion premium exists but is being measured with the wrong instrument.  
**Data needed:** Add `book_mid = (best_bid + best_ask) / 2` to the pricer shadow logger at each eval snapshot. After 24h accumulation, calib_monitor can compute the true market-implied σ.  
**Time/cost:** Small code change (logging addition only, not strategy), 24h data accumulation, zero capital.  
**Success metric:** ratio_7d computed from book_mid ≥ 1.10 within 3 days.  
**Decision-if-yes:** Dispersion premium confirmed → adverse selection is seasonal not structural → resume band NO in SH cities (or after summer).  
**Decision-if-no:** True market-implied σ < realized σ from book prices → no dispersion premium exists → model-based band strategy has no edge → halt band strategy permanently.  
**Value-of-information:** High. Resolves the calib_monitor's critical caveat and either validates or definitively kills the band edge hypothesis.

---

## 7. SINGLE BEST ACTION

**Halt new NO posting immediately (BAND_NO_ENABLED=False).** Allow existing 8 SELL_EXIT positions to resolve via RECYCLE099.

**Basis:**
- **exec_audit_report:** Winner's curse ALERT fires at n=89. EV=−$2.28/fill. Capital down 73% in 3 days.
- **gatekeeper_report:** Bankroll alarm — $61.16 breaches CLAUDE.md weekly floor ($75) and monthly kill-switch (−20%) simultaneously. Multiple kill-switch conditions met.
- **calib_monitor_report:** Dispersion assumption UNVALIDATED (ratio=0.75, alert fires). Foundation of band edge is unconfirmed.
- **pnl_ledger_report (Jun 25):** Rolling-20 WR=5%, PF=0.012, both far below CLAUDE.md halt thresholds. 20/20 consecutive STWA_RESOLVED losses.

**Today's state provides a natural pause:** 0 new NO posts in 81 cycles today (market exhaustion in 5-city set). The bot cannot post anyway. Formalizing this as BAND_NO_ENABLED=False prevents new NO exposure when d+1/d+2 dates roll in tomorrow for Chengdu, London, Beijing, Munich, Wuhan.

**Concrete first step (human action):** On VPS, set `BAND_NO_ENABLED = False` in band_config.txt. Then immediately run VPS-side `band_resolution_join.py --gate BAND_YES` (Experiment 2). If YES CI clears zero, flip `BAND_YES_LIVE_MIN_DOUT=2` and `BAND_NO_ENABLED=False` simultaneously — this pivots from adverse-selected NO to the mirrored YES strategy in one step, without stopping the compounding engine.

**Why this over expanding to SH cities first:** Hemisphere segmentation (Experiment 1) is the right diagnostic but takes more time. The VPS YES gate check (Experiment 2) can be done in 10 minutes and either opens a proven-EV path or closes the book on the band strategy entirely. The best action maximizes expected value weighted by speed and resolution certainty.

---

## PROPOSED ACTIONS (human review)

**PA-1 (Immediate): Halt new BAND_NO posting**  
Set `BAND_NO_ENABLED = False` on VPS. The 5-city market exhaustion makes today safe regardless, but tomorrow's d+1/d+2 rollover will expose the engine to new markets without this flag. Capital at $61.16 is below the CLAUDE.md weekly floor; continuing to post NO compounds losses at an expected −$2.28/fill.  
*Gating condition:* Override only if VPS YES gate CI check (PA-2) simultaneously shows YES is positive-EV.

**PA-2 (Same day): VPS YES Gate CI Check**  
Run `band_resolution_join.py --gate BAND_YES` on VPS. Report WR, ROI, CI95 on n=3,418 resolved YES legs. This data is already computed by the VPS-side cron (last known state Jun 17: +7.6%). If CI clears zero: enable BAND_YES live at d+2 with stake $1, 20-fill trial. If CI straddles zero: suspend all band trading pending Experiment 1 (hemisphere segmentation).

**PA-3 (Same day): M1_BETA_LOCKOUT revert**  
Set `METAR_LOCKOUT_TEMP_FLOOR = 0.5°C` (revert to prior floor). Shadow logger absent 15+ days, n=31 stalled. No new data accumulating. Reverting costs nothing; continuing burns opportunity on an unvalidated parameter expansion. *(Also flagged as gatekeeper ACTION 1.)*

**PA-4 (Within 24h): book_mid logging**  
Add `book_mid` to pricer shadow logger at each eval snapshot. Enables the dispersion gauge to measure market-implied σ vs model-implied σ — the measurement needed to confirm or falsify the band strategy's foundational assumption.

---

*Research-agent@klaus. REPORT-ONLY: no code, config, or strategy edits were made. All state-altering recommendations above require human review before implementation.*
