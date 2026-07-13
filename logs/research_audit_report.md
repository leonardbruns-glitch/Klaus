# Research Audit — 2026-07-13T~UTC

**Snapshot**: `2026-07-13T08:58Z` (calib_monitor + gatekeeper both <4h at run time — FRESH ✅)
**System**: `active` ✅ (confirmed all three fresh reports + ESCALATIONS 10:46Z)
**Capital**: ~$39.40 (ESCALATIONS 10:46Z — actual CLOB wallet; ruin floor $89.16 waived by owner per explicit directive)
**⚠ STRATEGY PIVOT**: As of 2026-07-13T10:46Z, `klaus_updown_sniper.service` is LIVE (BTC 5/15m, $5 clips, day-stop −$6, 3-consecutive-loss halt, $15 max open). Sprint ladder DISARMED 09:25Z. Weather band, PAIR_FAV, and ladder all inactive.
**Specialist reports read**:
- `exec_audit_report.md` 2026-07-12T10:54Z ✅ (~25h — within 36h; PRE-PIVOT)
- `calib_monitor_report.md` 2026-07-13T07:58Z ✅ (fresh; PRE-PIVOT)
- `gatekeeper_report.md` 2026-07-13T09:00Z ✅ (fresh; PRE-PIVOT)
- `pnl_ledger_report.md` 2026-07-13T23:37Z ⚠ (ABORT — snapshot 22h stale; best-effort only)

**ESCALATIONS.md read (10:46Z pivot entry). PENDING_HUMAN.md read.**

---

## 1. Primary Bottleneck for Compounding

**Bottleneck: Capital survivability at $39.40 while the UPDOWN-SNIPER shadow gate accumulates to n≥100.**

The compounding formula is a secondary concern until the new strategy validates. The relevant question is whether the bot survives the ~36h shadow accumulation window at $5 clips with a −$6 day-stop.

The capital chain tells the story clearly:

| Event | Equity | Delta |
|---|---|---|
| Jul 10 22Z (last clean pnl report) | $163.16 | baseline |
| Jul 11 22:06Z (state_log, cash+open positions) | $205.76 | +$42.60 (ladder shot redemptions) |
| Jul 12 00:00Z (daily start) | $165.73 | −$40.03 (ladder shots at cost) |
| Jul 13 07:58Z (calib_monitor) | $87.40 | −$78.33 (PAIR_FAV + ladder resolutions) |
| Jul 13 09:00Z (gatekeeper) | $87.40 | flat (same snapshot) |
| **Jul 13 10:46Z (ESCALATIONS, floor waiver)** | **$39.40** | **−$48.00 (PAIR_FAV BUY-YES resolved NO)** |
| **Net Jul 10 → Jul 13** | | **−$123.76 (−75.8%)** |

**Attribution for the $48 Jul-13 intraday drop**: Gatekeeper at 09:00Z confirmed two large open PAIR_FAV BUY YES positions: 51.5sh@0.449 = ~$23.11 + 45sh@0.526 = ~$23.67 = ~$46.78 cost basis. These had not yet exited at 09:00Z. By 10:46Z equity was $39.40 — the $48 drop is almost exactly the cost of those positions resolving at ~0 (YES lost, temperature did not cooperate). This is consistent with the S3 dispersion inversion: the market had been pricing less uncertainty than temperatures deliver for 15 consecutive confirmed days.

**PAIR_FAV was the Jul 11 research audit's recommended single best action.** Its re-enable produced the largest single-week capital loss in the system's history. The G3 WATCH_ITEM (realized ROI −75.8% vs sim +7.6%, CI entirely negative [−75%, −34%]) had explicit causal expression: the co-fill protection assumed to insulate PAIR_FAV from adverse selection was insufficient — naked YES legs resolved against us rather than being paired.

Prior bottleneck ranking (equity deployed / turns/day / ROI) is entirely superseded. New ranking:
1. **Capital survivability** ($39.40, floor waived — two bad $5 days + day-stop could reach $27)
2. **Shadow gate at n≥100** (expected ~Jul 14 22Z; UPDOWN-SNIPER unvalidated in live execution)
3. **Fee structure verification** (makers free vs takers expensive at 50% odds — critical if order type is wrong)
4. All weather-band concerns → **SUSPENDED** (strategy inactive, revisit only if pivot fails)

---

## 2. Existing-System Optimization

The weather band system is retired by the pivot. The "existing system" going forward is the UPDOWN-SNIPER and its shadow recorder. Three items:

### A. Verify maker vs taker order type in updown_sniper.py — highest urgency
**Finding (ESCALATIONS + PENDING_HUMAN 10:46Z)**: "fee-wall premise falsified (true fee 0.07·p·(1−p), takers only, makers free)." At p=0.95: taker fee = 0.07×0.95×0.05 = 0.33% per fill on notional. At $5 clip: ~$0.017/fill in fees. Against the stated ROI range (+1–7%/fill), the low end (+1%) yields +$0.05 gross, fee $0.017, net +$0.033 — viable but fee is 34% of gross at the floor. If MAKER orders are used: fee = $0. The difference is significant at the low end.

**Expected delta**: Zero-cost verification; changes how EV is computed at n=100 gate.
**Confidence**: High — fee formula is confirmed from research.
**Effort**: `grep -n "order_type\|GTC\|FOK\|maker\|taker" strategy/updown_sniper.py` on VPS, 5 minutes.

### B. Day-stop positioning is appropriate — no change needed
At $39.40 equity, −$6 day-stop = −15.2% intraday risk. Two consecutive stop-days → $27.40. This is tight but correct for validation phase. The -$6 stop prevents a single catastrophic session from wiping the bankroll. The 3-consecutive-loss halt adds further protection. **Do not loosen either guard during shadow accumulation.**

### C. Tracker restart bug remains a standing deficiency — lower priority
pnl_ledger Section 1: positions placed in a prior session do not sync from CLOB state on restart, producing unmanaged capital outflow. The PAIR_FAV losses may partly reflect this. For the UPDOWN-SNIPER (directional taker/maker entries that close within the same 5/15m window), tracker continuity is less critical — but any restart mid-window leaves an orphaned open position. Fix when sniper validates; not urgent now.

---

## 3. Gate Pipeline Review

All weather gates are **suspended** (strategy inactive). The only active accumulation gate is:

| Gate | n | Status | ETA |
|---|---|---|---|
| **UPDOWN_SHADOW n≥100** | Pre-registered | **COLLECTING** | **~Jul 14 22Z** |
| G1 BAND_YES | 934 | SUSPENDED | ∞ (band dark) |
| G3 FILLED_VS_FIRED | 75, WATCH_ITEM | SUSPENDED | ∞ (band dark) |
| G5 THERMO | 125 | REJECTED ✓ | done |
| G6 M1β | 31 | REJECTED ✓ | done |

**What would accelerate accumulation without degrading expectancy**: Nothing. Shadow gate must collect real market observations from live BTC 5/15m windows. Do NOT increase clip size or entry frequency to speed up accumulation — at $39.40 bankroll, larger clips increase ruin probability faster than they accelerate gate crossing. The ~36h timeline is governed by BTC updown window cadence, not by our stake.

**Pre-registered GO/NO-GO at n=100**: WR ≥0.90 AND net-of-fee ROI ≥+0.5%/fill. If both met → scale to full authorized rails. If either fails → halt sniper immediately.

---

## 4. Assumption Attack

The weather band's load-bearing assumptions are now moot (strategy inactive). The UPDOWN-SNIPER carries three:

### Assumption 1: Near-certainty fills (0.90–0.99) have WR ≥0.95 in live BTC execution
**Status: UNVALIDATED — shadow data resolves in ~36h.**

Research basis (ESCALATIONS state_log 10:35Z): "stable +EV niche = buying near-certainty (0.90–0.99) in the final 15–120s, WR 0.95–1.00, +1–7%/$ net." The claim is grounded in CLOB trade tape analysis (taker_trades_2026-05-15 and 2026-05-24_28 parquets in data/). The niche hypothesis: at T−60s to T−120s with the underlying BTC move already resolved, near-certainty Chainlink confirmation is priced correctly but the market hasn't yet compressed to 0.99+ because smaller bots are slower.

**What threatens this assumption**: Selection bias — only windows where the underlying move was clear produce 0.90+ asks; windows where the outcome is ambiguous at T−60s stay below 0.90 and are not traded. The WR of 0.95–1.00 may be an artifact of conditioning on entry opportunity (you only enter when the setup is clear) rather than a structural market inefficiency. The shadow gate at n=100 will test this: if live WR tracks shadow WR, the selection bias is "real edge"; if live WR degrades vs shadow, the entry condition needs refinement.

**Today's reports**: No sniper fills visible yet (service armed 10:46Z; reports all generated pre-pivot). First live fills expected from next BTC 5m window after 10:46Z. Shadow recorder (`klaus_updown_shadow.service`) was running before today.

### Assumption 2: Near-certainty liquidity is deep enough ($5 clips, no market impact)
**Status: PLAUSIBLE — well-supported by flow size, not yet live-tested.**

"~$55k/day of such flow, dispersed across 200+ wallets" (state_log 10:35Z). $5 clip = 0.009% of daily flow → negligible market impact. This assumption is robust as long as the $55k/day figure is current. If the near-certainty niche has been exploited by additional bots since the historical tape analysis, available liquidity at 0.90–0.99 may have compressed.

**What threatens this**: The 2.7s average arbitrage window in the standard arb niche (CLAUDE.md research) shows the market tightens fast as participants multiply. If near-certainty fills are now being competed for, the 15–120s window compresses toward T−5s where Chainlink uncertainty makes the trade unviable.

### Assumption 3: Fee structure is maker-free; sniper submits maker orders at favorable prices
**Status: UNVERIFIED — single highest-value verification needed today.**

Fee formula confirmed: `0.07·p·(1−p)`, takers only, makers free. At p=0.95: taker rate = 0.33%. Whether the sniper uses maker vs taker orders determines the actual breakeven. See Experiment 1.

---

## 5. Market Intelligence — Market Census (Day 13 mod 3 = 1)

**Rotation**: [1] Market census — new weather cities/products, depth changes. **Scope adjustment**: Active strategy is UPDOWN-SNIPER (BTC 5/15m). Weather census deferred while strategy is inactive. Reporting BTC updown market structure.

**BTC 5/15m updown market structure (from CLAUDE.md, data/, prior research):**

| Market type | Cadence | Windows open simultaneously | Chainlink resolution |
|---|---|---|---|
| BTC 5m updown | :00/:05/:10/:15... | 2–3 (current + next pre-order window) | T=0 snapshot (NOT TWAP) |
| BTC 15m updown | :00/:15/:30/:45 | 2–3 | T=0 snapshot |

**Chainlink timing and the sniper entry window**: Chainlink heartbeat uncertainty is 10–30s at any given T=0. Entry at T−60s to T−120s avoids this. The CLAUDE.md spec explicitly documents `no_trade_last_sec=60` — the sniper should inherit this gate. If it doesn't, entries in the T−30s to T−1s window face unquantifiable settlement risk. Verification of this gate (Experiment 1) covers both order type AND timing.

**Fee arithmetic at p=0.95** (taker scenario, $5 clip):
- Fill: 5 / 0.95 = 5.26 shares at $0.95
- On resolution (YES wins): 5.26 × $1.00 = $5.26 gross
- Fee: $5 × 0.0033 = $0.017
- Net profit: $0.26 − $0.017 = $0.243 = +4.9% on $5 deployed
- This is solidly in the +1–7% range and viable.

**At p=0.90** (lower entry bound, taker):
- Fill: 5 / 0.90 = 5.56 shares
- Fee: $5 × 0.07 × 0.90 × 0.10 = $0.032
- Net profit if YES wins: $0.556 − $0.032 = $0.524 = +10.5%
- But if YES loses: −$5 − $0.032 = −$5.032 (near-certain loss)
- WR must be ≥0.95 for EV>0 at p=0.90: 0.95×$0.524 + 0.05×(−$5.032) = $0.498 − $0.252 = **+$0.246** → EV positive if WR≥0.95 holds.

**Competitor context**: 200+ wallets identified in this niche. Standard arb window is 2.7s (sub-100ms bots dominate). The near-certainty sniping niche is distinct from standard arb — it requires no latency advantage, only patience to wait for T−60s confirmation. Competition is via position-size, not speed. The $55k/day flow figure suggests the niche is not yet saturated.

**Weather market census**: Shadow scanner found 13 fire events on Jul 12 (normal cadence). No new weather cities or products detected from accessible logs. S3 dispersion gauge still firing (≤0.80 ratio, 15 consecutive confirmed days). Weather band cannot re-enable until dispersion gauge ≥1.10 for 5 consecutive days — condition not met and cannot be evaluated without VPS data. Weather census deferred to next audit when strategy may be relevant.

---

## 6. Three Experiments

### Experiment 1: Verify order type and timing gate in updown_sniper.py
**Hypothesis**: The sniper submits MAKER bids (not TAKER market orders) and enforces the T−60s to T−120s entry window (not T<60s where Chainlink uncertainty spikes).
**Data needed**: `strategy/updown_sniper.py` order placement section.
**Time**: Today, 5 minutes.
**Cost**: Zero.
**Success metric**: Order type confirmed MAKER (GTC limit at or below ask); entry gate excludes T<60s remaining.
**Decision if confirmed**: Fee model is maker-free as assumed; EV calculations are as stated; proceed to shadow gate at n=100.
**Decision if taker orders found**: Recalculate EV floor at +0.33% taker fee drag. Low-end ROI (+1%) drops from +$0.033 net to +$0.016 net per $5 clip. Still positive but thin — flag to owner. If entry gate misses T<60s, add the gate immediately (kernel-adjacent protective fix).

### Experiment 2: Shadow gate readout at n≥100 (~Jul 14 22Z)
**Hypothesis**: n≥100 shadow fills show WR ≥0.90 and net-of-fee ROI ≥+0.5% per fill at the pre-registered (0.90–0.99 ask, T−60s to T−120s) condition.
**Data needed**: UPDOWN shadow log output from `klaus_updown_shadow.service`.
**Time**: ~Jul 14 22Z (scheduled ~36h from arm).
**Cost**: $5/clip × live fills during accumulation; shadow fills themselves are free.
**Success metric**: WR ≥0.90 AND mean net ROI ≥+0.5%/fill (conservative vs the +1% stated floor).
**Decision if both met**: Scale to full authorized parameters ($5 clips, $15 max open). Notify owner.
**Decision if either fails**: HALT sniper immediately. Diagnose failure mode before any further live capital commitment. Do NOT increase stake to recover.

### Experiment 3: Capital reconciliation — verify the $48 Jul-13 intraday drop
**Hypothesis**: The $47.41 drop ($87.40 at 09:00Z → $39.40 at 10:46Z) is fully explained by the two PAIR_FAV BUY YES positions (51.5sh@0.449 + 45sh@0.526 = ~$46.78 cost) resolving at ~0 (YES lost).
**Data needed**: VPS `maker_fills_recent.log` for SELL/exit entries after 09:00Z Jul 13; on-chain wallet balance check.
**Time**: 15 minutes, VPS.
**Cost**: Zero.
**Success metric**: Sum of position costs ≈ observed equity drop (±$2 tolerance); no residual unexplained outflow.
**Decision if positions fully explain the drop**: PAIR_FAV is confirmed fatal. Ensure `BAND_PAIR_FAV_ENABLED=False` is hardcoded and cannot re-enable via any automated path.
**Decision if residual unexplained**: Additional capital outflow from untracked source — likely another tracker restart orphan. Investigate before any new deployment.

---

## 7. Single Best Action

**Action: Read `strategy/updown_sniper.py` order-placement code on VPS today (5 minutes), confirm maker order type and T≥60s entry gate, then hold position — do not interfere with shadow accumulation until n≥100 gate fires at ~Jul 14 22Z.**

**Citations from specialist reports:**

- **gatekeeper_report (09:00Z)**: "Two large open BUY fills visible (51.5 sh @0.449, 45 sh @0.526 — no exit yet in log)" and "Bankroll $87.40 < ruin_floor $89.16." The PAIR_FAV positions caused the floor breach — they are now confirmed closed at a loss, per the 10:46Z floor waiver event.
- **exec_audit_report (Jul 12 10:54Z)**: "Winner's-curse direction: Resting bids are getting hit selectively when the market moves against the quote... The gap is large enough at n=75 to warrant ongoing monitoring; cannot be dismissed as noise." The co-fill assumption in the Jul 11 research audit was wrong. This is the error that produced the $123.76 loss.
- **calib_monitor_report (07:58Z)**: "The edge is inverted. For 15 consecutive market-days (Jun 28–Jul 12), every confirmed day with an accessible official ratio has been below 1.10." Band must not re-enable; this condition has not changed and is not being addressed by the pivot.
- **ESCALATIONS (10:46Z)**: "Waiver is SCOPED: only `klaus_updown_sniper.service`, $5 clips, day-stop −$6, 3-consecutive-loss halt, $15 max open. All other live paths remain halted (ladder disarmed 09:25Z, engine ruin-floor armed)."

**Why the order type check is the single first step**: The entire fee model and EV floor depend on it. At $39.40 bankroll and $5 clips, the difference between maker (free) and taker (0.33%) fees is small in absolute dollars ($0.017/fill) but material as a fraction of the low-end profit ($0.033 net if maker; $0.016 net if taker at +1% ROI). More importantly, confirming the code behavior before the n=100 gate fires means the readout can be interpreted cleanly. If maker orders are confirmed and timing gate is correct, a WR≥0.90 result at n=100 is clean GO. If taker orders are found, the EV calculation needs adjustment before the GO decision.

**Concrete first step (today, VPS, 5 min)**:
```bash
grep -n "order_type\|GTC\|FOK\|FAK\|maker\|taker\|limit\|remaining\|60" /root/Klaus/strategy/updown_sniper.py | head -40
```
Post result to state_log.

**Concrete second step (Jul 14 ~22Z, scheduled)**:
Read shadow accumulation log. Compute WR and net-of-fee ROI at n≥100. Apply pre-registered GO/NO-GO criteria. Notify owner with recommendation.

**What NOT to do**: Do not increase clip size. Do not re-enable any weather or ladder path. Do not attempt to "recover" the $123.76 loss through larger positions. The loss is realized. The capital remaining ($39.40) is the entire bankroll — managing it conservatively while the shadow gate accumulates is the only correct posture.

---

## PROPOSED ACTIONS (human review — no strategy code or flags modified)

- [ ] **VPS TODAY (5 min)**: Check order type in `strategy/updown_sniper.py`. Confirm MAKER or TAKER. Post to state_log.
- [ ] **VPS TODAY (15 min)**: Run capital reconciliation for Jul 13 09:00Z → 10:46Z (Experiment 3). Confirm PAIR_FAV positions caused the $48 drop. Verify `BAND_PAIR_FAV_ENABLED=False` cannot auto-flip.
- [ ] **Jul 14 ~22Z (scheduled, ~36h from sniper arm)**: Read UPDOWN-SNIPER shadow gate at n≥100. Apply GO/NO-GO: WR≥0.90 AND net ROI≥+0.5%/fill. Notify owner with recommendation and full n-count.
- [ ] **ONGOING**: Preserve all sniper guards (−$6 day-stop, 3-consecutive-loss halt, $15 max open). Do NOT modify these during shadow accumulation.
- [ ] **DATA-MIRROR PUSH CADENCE** (pnl_ledger flag, second consecutive ABORT): The pnl_ledger 23:37Z report aborted again (22h 46m stale). Add a cron at 22:00Z or 23:00Z on VPS to push data-mirror. Without this, the day-end ledger permanently blind.
- [ ] **SUSPENDED (no action this cycle)**: All weather band items (PAIR_FAV, G3 winner's curse cross-tab, isotonic, dispersion gauge, ladder). Revisit only if UPDOWN-SNIPER fails and owner chooses to rebuild the weather system.

---

*Research audit 2026-07-13. Specialist reports: exec_audit Jul 12 10:54Z (25h, within 36h), calib_monitor Jul 13 07:58Z (fresh), gatekeeper Jul 13 09:00Z (fresh), pnl_ledger ABORT (22h stale, best-effort). ESCALATIONS.md pivot entry 10:46Z confirmed. REPORT ONLY — no strategy code or flags modified. SHA of prior report superseded: c3635b821dd6d0f74608ad24041674d31e7c9cb4.*
