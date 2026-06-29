# Research Audit — 2026-06-29
**Generated:** 2026-06-29T10:30Z | **Run by:** research-agent | **Snapshot:** 2026-06-29T10:21:03Z (9 min old — FRESH)
**System:** `active` (uptime since 2026-06-26T15:08:30Z, ~67h) | **Bankroll:** $80.86

---

## Pre-flight

| Check | Result |
|---|---|
| SNAPSHOT.md age | 9 min — PASS |
| System status | `active` — PASS |
| Specialist reports | exec_audit (07:07), calib_monitor (08:10), gatekeeper (09:13), pnl_ledger (23:37 Jun 28) — all ≤36h |

**Note:** `data/agent_context/research_status.md` last updated 2026-05-16, describes retired LDA strategy. Treated as background context only; specialist reports and band_config.txt are authoritative for current strategy state.

---

## 1 — Primary Bottleneck: Equity-Adjusted Turns/Day (0.43 vs benchmark ~1.0)

**Ranking justification:** ROI/turn is 30.9% (excellent, above badatmath 10–20% benchmark — PnL ledger). Capital-velocity turns/day is 1.03 (at benchmark — exec_audit). But equity-adjusted turns (fills/total_equity) = $66.63 / ~$154 = **0.43 — less than half of benchmark.** The bottleneck is not edge quality; it is inability to deploy during high-candidate periods.

**Mechanism (PnL ledger, Jun 28):** From 17:46–23:31 UTC (6.7 hours, ~80 STRUCT-BAND-Q cycles), the queue reported 13–15 viable NO candidates per cycle and executed zero. Every cycle showed `cash_preskip = 7–13`. Root cause: 14 resting positions × ~$5 nominal = ~$70 notional tied up, plus `BAND_NO_CASH_RESERVE=0.30` × $75 = $22.50 reserved → combined notional commitment exceeds available cash envelope. The bot sees a full menu of actionable edge every 5 minutes and cannot reach it.

**Quantified opportunity cost:** Each additional ~6 fills at 30.9% ROI/turn on $5 stake = ~$1.85/day forgone in the frozen window, compounding daily. Unlocking even one additional fill-cycle per evening would close ~40% of the gap to benchmark turns.

**This is the primary bottleneck.** YES parity, gate verdicts, and calibration are important second-order concerns, but none prevent deployment in the way the cash-reserve floor does today.

---

## 2 — Existing-System Optimizations

### 2a. BAND_NO_CASH_RESERVE 0.30 → 0.20

- **Source:** PnL ledger — 6.7h dead-cycle freeze, `cash_preskip` = 7–13/cycle in 17–23 UTC window
- **Mechanism:** Reserve floor at 0.30 × ~$80 = $24. Lowering to 0.20 releases ~$8 headroom → 1–2 additional $5 NO positions before hitting the floor
- **Expected delta:** +0.15–0.25 equity-adjusted turns/day during evening windows; ~+$0.50–1.00/day incremental P&L at current ROI/turn
- **Confidence:** HIGH — freeze mechanism precisely documented with cycle-level evidence
- **Effort:** LOW (single parameter, band_config.txt, restart)
- **Risk:** Marginally higher correlated-position risk at peak. Mitigated by 5-city narrow-start and RECYCLE099 velocity

### 2b. VPS Gamma Resolution Join (band_resolution_join.py)

- **Source:** Gatekeeper structural blocker #1 — BAND_NO (n=243), BAND_YES (n=5,999), SUM_POSTED (n=2,982), FILLED_VS_FIRED (n=60) all blocked by Gamma 403 from cloud container
- **Mechanism:** The script exists on VPS where Gamma API is accessible. One execution joins resolution truth to all accumulated fire records, enabling CI verdicts simultaneously
- **Expected delta:** Up to 4 gate verdicts; immediately confirms or rejects NO stake sizing (n=243 — the highest-leverage verdict pending)
- **Confidence:** HIGH (data accumulated; only network path missing)
- **Effort:** MEDIUM (user executes on VPS or schedules cron)
- **Risk:** None — read-only analysis

### 2c. d+2 YES sum_gate context (BAND_SUM_MAX=0.85)

- **Source:** Exec audit — yes_books = 0 in 746/746 STRUCT-BAND-Q cycles; d+2 sum_ask hitting 0.87–1.22 across all 5 cities; ALL standalone d+2 YES blocked by sum_gate
- **Mechanism:** BAND_YES_LIVE_MIN_DOUT=2 restricts YES to d+2; d+2 sum_ask in the 5-city allowlist consistently clears 0.85. The YES channel is structurally dark except for pair_fav (~1 event per 1.5 days)
- **Expected delta (shadow-only test):** YES shadow post rate from zero; if positive, creates BAND_YES gate data at d+2 post level
- **Confidence:** MEDIUM — cannot determine without testing whether sum_ask = 0.87–0.90 is genuine edge or market-rational pricing
- **Effort:** LOW (shadow-only, BAND_SHADOW=True, no capital)
- **Risk:** Zero at shadow stage; live promotion requires CI gate first

| Optimization | Δ | Confidence | Effort | Priority |
|---|---|---|---|---|
| Reserve 0.30→0.20 | +$0.5–1.0/day | HIGH | LOW | 1 |
| VPS Gamma join | 4 gate verdicts | HIGH | MEDIUM | 2 |
| YES sum_gate shadow | data collection | MEDIUM | LOW | 3 |

---

## 3 — Gate Pipeline Review

**Source:** gatekeeper_report.md (09:13 UTC)

| Gate | n | n_gate | CI | Status | Nearest path |
|---|---|---|---|---|---|
| BAND_NO + PAIR_FAV | 243 | 100 | BLOCKED | COLLECTING | VPS Gamma join |
| BAND_YES | 5,999 | 100 | BLOCKED | COLLECTING | VPS Gamma join |
| SUM_POSTED 0.70–0.85 | 2,982 | 100 | BLOCKED | COLLECTING | VPS Gamma join |
| FILLED_VS_FIRED | 60 | 100 | BLOCKED | COLLECTING (~40 watch) | ~3 days + VPS join |
| M1_BETA_LOCKOUT | 31 | 100 | AMBIGUOUS | STALLED 17d | Human: revert floor |
| THERMO_MAKER_NO | 3 | 20 (kill) | n/a | FROZEN | Re-arm or kill |

No gate newly hit READY or REJECTED this cycle.

**Standing rule (M1_BETA_LOCKOUT, 4th consecutive run):** Stalled 17 days, 0 accumulation, 0 placed orders. Standing rule from 2026-06-09 triggered (stalled >2 weeks → REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5°C). Human action required — unactioned for 4 runs.

**What accelerates WITHOUT degrading expectancy:**

City breadth: Jun-26 state_log markout analysis (n=1,421 fills, trend-grade) showed Chengdu +28%, London +9%, Munich +7%, Beijing ~0%. Adding one borderline-clean 6th city to BAND_CITY_ALLOW increases BAND_NO fire rate ~5.5 → ~7/day, shortening FILLED_VS_FIRED ETA from ~3 days to ~2 days. Gate: city must show markout trend above −1.2% (matching Beijing floor). Breadth only, not stake.

---

## 4 — Assumption Attack

### Assumption 1: Dispersion premium persists

Calib monitor S3 fires 8th consecutive day (ratio 1.096 < 1.10 threshold). Its alarm logic: implied σ should exceed true σ for YES spread-capture to be +EV. Implied σ = 1.096C; realized denominator is stale (Gamma unavailable 3 cycles).

**Critical context from state_log Jun 24 (sigma_reality analysis, n=211 city-days):** "VERDICT: market is UNDER-dispersed (implied 0.81 < realized 1.1–1.6) ⇒ over-dispersion premise DEAD/inverted; BUT model-free WR−ask gap on near-mode YES (0.10–0.45) ≈ 0 (mean +0.01) ⇒ buckets ~fairly priced, band not bleeding from dispersion. Real edge = MAKER spread-capture + 0.25-0.45 underpricing + MERGE-LOOP velocity."

The dispersion gauge tracks badatmath's theoretical premise — not our live edge mechanism. The Jun-24 audit already declared this assumption dead and replaced it. Implied σ rising to 1.096 from 0.81 is directionally positive for our mechanism (wider ladders = more spread to capture).

**Threat level: LOW-MEDIUM.** Gauge fires on a premise we've superseded. True risk is if the Jun-24 conclusion was itself wrong (n=211, trend-grade). The Gamma join would resolve this — it provides realized σ directly.

**Support:** 30.9% ROI/turn on 8 resolved legs; 12 consecutive wins (bankroll.json). If edge were inverted, p(12+ consecutive wins at <50% true win prob) ≈ 0.4% — unlikely.

### Assumption 2: Fills are not adversely selected

Winner's curse: our NO maker bids get filled when the taker has unfavorable information. The FILLED_VS_FIRED gate (n=60, ~3 days to n=100) is the direct test.

**Context:** Jun-26 state_log adverse-selection analysis found western-city YES fills at d+0/d+1 had −12% to −28% markout. The narrow-start execution fix (Jun 26) was specifically designed to isolate d+2 window and clean cities where markout is +10.7%. NO fills in clean cities show positive trend markouts.

**Threat level: LOW for NO in current narrow-start config.** The fix targets the identified risk. 12 consecutive wins supports this.

**Gap:** CI cannot be computed without Gamma join. At n=60 fills, the winner's-curse test — the existential risk question — is the most important unresolved data question in the system. 3 days away.

### Assumption 3: Recycle velocity scales

RECYCLE099 posts $0.99 exit orders after NO fills; resolution convergence drives fills, recycling cash. Assumption: RECYCLE099 exits keep pace with new fills.

**Threat level: LOW.** PnL ledger Jun 28: 8 RECYCLE099 exits, all winners, $12.533 gross P&L. Cash-freeze pattern is caused by reserve constraints, not recycle slowing. Two recycle paths: (a) RECYCLE099 pre-resolution exit at $0.99, and (b) on-chain settlement at $1.00 (~$19.758 explained capital increase Jun 28 = Jun-26 d+2 positions settling). Both paths return capital.

**Risk:** If SELL_EXIT resting orders (82 shares at $0.99 in book — exec_audit) age past resolution without filling, capital returns via on-chain path with 12–48h lag instead of immediate intra-day recycle. This extends cash-freeze periods. BAND_PAIR_RECLAIM_AGE_S=8h guards pair legs.

---

## 5 — Market Intelligence (Day 29 mod 3 = 2: Platform Mechanics)

**No direct API access to docs.polymarket.com.** Reporting from available data only.

**Delta vs state_log knowledge:**

**1. Maker rebate accumulation — pUSD verification pending (new finding).**
PnL ledger computed cumulative expected rebate = **$1.783** (formula: `shares × 0.05 × p×(1−p) × 0.25`), exceeding the $1.00 minimum payout threshold. State_log did not track cumulative totals. If no pUSD payout has been received in the funder wallet since the maker era began (~Jun 10), either the fee tier assignment is incorrect, the rebate formula overstates (it assumes exclusive maker share, not proportional), or there is a payout lag. The Chengdu pair YES fill at p=0.50 (p×(1−p)=0.25 max) is the highest single-fill rebate earner this session — confirm it is categorized as "weather" maker-side.

**2. No other platform mechanic changes detected.** band_config.txt comments through Jun 29 show no fee schedule revisions since Jun 18. The Jun-24 BAND_BELL and BAND_PX_CEIL changes were strategy parameters, not platform fees. Fee structure remains: maker rebates from taker fee pool, dynamic taker ~3.15% at 50% odds, near-0% at extremes.

**Action item from this section:** Verify Polygon funder wallet for pUSD inflows ≥$1.00 since Jun 10.

---

## 6 — Experiments

### Experiment A: BAND_NO_CASH_RESERVE sensitivity test (0.30 → 0.20, 24h)

**Hypothesis:** Reducing the cash reserve floor from 30% (~$24) to 20% (~$16) releases ~$8 headroom during the evening cash-freeze window (17–23 UTC), enabling 2–3 additional NO fills per evening.

**Data:** STRUCT-BAND-Q `posted/cycle` and `cash_preskip` in 17–23 UTC; compare to observed 7–13 preskip/cycle baseline (PnL ledger Jun 28).

**Time:** 24h pilot (one evening window)

**Cost:** ~$8 additional peak exposure (~1–2 extra concurrent NO positions). Within 5-city narrow-start risk envelope.

**Success metric:** `cash_preskip` in 17–23 UTC drops to ≤3/cycle AND `posted/cycle` in that window increases to ≥0.5/cycle.

**Decision if yes:** Adopt 0.20 as new baseline; monitor correlated-exposure events (e.g., same-direction adverse outcomes across multiple cities same day).

**Decision if no (preskip stays high):** Binding constraint is SELL_EXIT resting count, not reserve → investigate reducing SELL_EXIT age or accelerating pair reclaim (BAND_PAIR_RECLAIM_AGE_S currently 8h).

---

### Experiment B: d+2 YES sum_gate shadow sensitivity (BAND_SUM_MAX 0.85 → 0.90, shadow-only, 48h)

**Hypothesis:** d+2 YES markets with sum_ask in [0.85, 0.90] represent genuine edge (≥10¢/sh locked above fee threshold), and BAND_SUM_MAX=0.85 is the sole mechanical blocker preventing YES d+2 posts. Exec_audit documents sum_ask = 0.87–0.90 in multiple city/day combinations.

**Data:** yes_capture_shadow fire count per day at threshold 0.90; distribution of sum_ask for shadow fires; any sum_ask > 0.90 (stale-ask artifacts, not genuine edge).

**Time:** 48h shadow accumulation, zero capital.

**Cost:** Zero (BAND_SHADOW=True, no live capital affected).

**Success metric:** ≥5 shadow YES fires/day with sum_ask ≤ 0.90; median sum_ask of those fires ≤ 0.89.

**Decision if yes:** Raise BAND_SUM_MAX to 0.90 in shadow. Wait for n=100 shadow YES fires + YES gate CI (from VPS Gamma join) before promoting live.

**Decision if no (shadow fires still 0, or all sum_ask > 0.90):** d+2 YES books are genuinely expensive for the current 5-city set; sum_gate is correctly calibrated at 0.85. Redirect YES exposure entirely to pair_fav (d+0). Consider widening BAND_PAIR_FAV_YES_MIN/MAX range as alternative YES channel.

---

### Experiment C: City 6 breadth probe — NO only, 72h

**Hypothesis:** Adding one additional city to BAND_CITY_ALLOW with NO-only flag (not YES) increases BAND_NO fire rate ~5.5 → ~7/day, accelerating FILLED_VS_FIRED to n=100 in 2 days rather than 3, without degrading per-city expectancy.

**Data:** Per-city markout signal from band_struct_lite fires for the new city; fire count delta; adverse-fill flags.

**Time:** 72h (generates ~15–21 new NO fires from City 6 → trend-grade markout signal)

**Cost:** ~$5 × ~6 fires/day = ~$30 additional notional over 72h. Returns via RECYCLE099/on-chain at normal velocity.

**Success metric:** New city fires ≥15 in 72h; per-city markout trend ≥ −5% (matching Beijing ~0% floor in current allowlist).

**Decision if yes:** Retain city in BAND_CITY_ALLOW. Expand to YES when both city markout and BAND_YES gate CI clear.

**Decision if no (markout < −5%):** Remove city. Confirms narrow 5-city set is optimally calibrated; no breadth expansion until Gamma join provides city-level CI.

---

## 7 — Single Best Action

**Run `band_resolution_join.py` on the VPS (or add to cron), unblocking CI for all four Gamma-blocked gates.**

**Justification from specialist reports:**
- Gatekeeper (verbatim): "VPS-side resolution join (band_resolution_join.py) is the only path to CI verdicts." Structural blocker #1.
- BAND_NO+PAIR_FAV has n=243 fills — 2.4× the n=100 decision threshold — but operates without a single CI-grade outcome measurement. Every capital allocation decision depends on this verdict.
- FILLED_VS_FIRED reaches n=100 in ~3 days. The winner's-curse test (existential for the NO-maker strategy) will be testable then. The join must be operational.
- Calib monitor (S3, 8th day): cannot clear without Gamma-joined realized σ data. Monitoring has been structurally dark on its primary metric for 5 cycles.
- One VPS command unblocks 4 simultaneous verdicts.

**P(success):** 0.85 (script exists on VPS, data accumulated; Gamma API accessible from VPS — confirmed by system architecture)

**Compounding impact × P(success) / effort = maximum of all available actions**

**Concrete first step:**
```bash
# On the VPS:
python3 analysis/weather/band_resolution_join.py --help
# confirm it runs, then:
python3 analysis/weather/band_resolution_join.py
# verify output; push any new resolution files to data-mirror
```

**Secondary action (independent, immediate, no gate dependency):**
BAND_NO_CASH_RESERVE 0.30 → 0.20 via band_config.txt edit + bot restart. Addresses the 6.7h cash-freeze window documented by PnL ledger. First step: edit `BAND_NO_CASH_RESERVE = 0.20` in `strategy/stwa_engine.py` → `systemctl restart klaus`. 2-minute action, no analytical dependencies.

---

## PROPOSED ACTIONS (human review)

1. **[SINGLE BEST] Run `band_resolution_join.py` on VPS** — unblocks CI for BAND_NO (n=243), BAND_YES (n=5,999), SUM_POSTED (n=2,982), pre-positions FILLED_VS_FIRED (n=60, ~3 days to threshold). Concrete first step: see §7.

2. **[LOW EFFORT, HIGH IMPACT] BAND_NO_CASH_RESERVE 0.30 → 0.20** — addresses 6.7h cash-freeze (PnL ledger Jun 28, ~80 dead cycles with 13–15 viable candidates/cycle). Expected +$0.5–1.0/day. Pilot 24h.

3. **[SHADOW, NO CAPITAL] d+2 YES sum_gate test BAND_SUM_MAX 0.85 → 0.90** — 48h shadow, zero capital, determines whether sum_gate is binding or correctly calibrated. Run as Experiment B.

4. **[CARRY-FORWARD, HUMAN ONLY] M1_BETA_LOCKOUT — REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5°C** — stalled 17 days, standing rule unactioned 4 runs. Gatekeeper: "Human action required. Do NOT implement automatically."

5. **[VERIFY] pUSD maker-rebate receipt** — estimated $1.783 cumulative (above $1.00 minimum threshold). Check Polygon funder wallet for pUSD inflows since Jun 10. 5-minute check.

---

## Context Drift Note

`data/agent_context/research_status.md` was last updated 2026-05-16 and describes the retired LDA strategy. It is dead context for current analysis. Specialist reports + band_config.txt are the live sources. Flagged for awareness — if other agents use this file for briefing, they will receive wrong strategy context.
