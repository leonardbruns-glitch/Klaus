# Klaus Research Audit — 2026-07-23T1030Z

**Analyst**: Research Agent (claude-sonnet-4-6)  
**Data sources**: specialist reports from claude/find-lag-parameter-rFQ0N (all fresh: ≤24h); data-mirror snapshot 2026-07-23T10:16:06Z (age ~14 min — FRESH); system_status confirmed `active` in all three specialist reports.  
**Abort check**: Snapshot 14 min old — PASS. system_status `active` — PASS. Proceeding.

---

## Specialist Report Dates (freshness audit)

| Report | Timestamp | Age at run | Status |
|---|---|---|---|
| exec_audit_report.md | 2026-07-23T07:16Z | 3h | FRESH |
| calib_monitor_report.md | 2026-07-23T08:20Z | 1.7h | FRESH |
| gatekeeper_report.md | 2026-07-23T09:00Z | 1.0h | FRESH |
| pnl_ledger_report.md | 2026-07-22T23:37Z | 11h | FRESH (within 36h) |

All four reports present and current. No stale-data fallback needed.

---

## Current System State (summary)

| Field | Value |
|---|---|
| Bankroll | $21.495 (unchanged 5+ days; stale bankroll.json; CLOB unverified) |
| BAND_LIVE | False — day 17 (since 2026-07-06; capital $21.50 < ruin floor $89.16) |
| UPDOWN_STOP | Active (since 2026-07-19T11:26Z; PF 0.79 over 27 settles) |
| LDA | STOP (rolling-20 net −$36.39 < −$30 rail) |
| THERMO / M1 | REJECTED |
| All live fills (7d) | 0 |
| All turns/day | 0 |
| Disk | 85% at 23:26Z; ~250 MB/h growth rate; ~8–9 days to 94% critical |
| Equity vs kernel floor | $21.50 < $40 — all path re-arms blocked without owner authorization |

---

## Section 1 — Primary Bottleneck

**ZERO EQUITY DEPLOYED — all five trading paths halted simultaneously (day 17).**

Compounding formula: `ROI/turn × turns/day × equity_deployed = N/A × 0 × $21.50 = $0.00/day`.

The binding constraint is not a rate, a calibration, or a fill problem — it is the complete absence of any executable path. Rank assessment:

| Bottleneck | Rank | Status |
|---|---|---|
| Equity deployed | **1 — PRIMARY** | $0/day for 17 days; all paths disarmed |
| Turns/day | 2 | Structural zero downstream of equity deployed |
| ROI/turn | 3 | Irrelevant at turns=0 |
| Fills / NO-parity | 4 | Zero activity; shadow healthy but dark |
| Calibration / dispersion | 5 | Monitored; S3 worsening (real edge concern) |
| Data / reliability | 6 | Network blocked 3 consecutive runs; non-fatal for now |

Justification from specialist reports:
- **Exec audit**: "Velocity is structurally zero. The gap vs badatmath's ~1.0 turn/day benchmark is entirely explained by `BAND_LIVE=False`." (Section 6)
- **Gatekeeper FLAG-4**: "Klaus is running (systemd: active) but has no executable trading path. Capital $21.495 = 7.2% of original capital. Bot has no self-recovery path without explicit human restart decision on at least one path."
- **PnL ledger**: "Day 3 of consecutive zero-fill days [now day 4]. All live trading paths disarmed. Capital $21.495 is $18.51 below the $40 kernel floor that gates any re-arm."

The system is not optimizable in its current state. It is suspended, waiting for a binary human decision.

---

## Section 2 — Existing-System Optimization

With zero live fills, standard execution optimizations (queue rank, NO-parity, fill rate) have nothing to act on. Items relevant to the idle state:

### 2a. G8 Shadow Rate Acceleration (ALREADY OCCURRING)
- Prior rate: ~4/day (Jul-21); current: ~15/day (Jul-22→Jul-23)
- n=72 → ETA n=100 ~Jul-25. At 15/day, the AMBIGUOUS checkpoint arrives in 2 days.
- **Expected delta**: earlier KILL decision (or human checkpoint) → sooner capital reallocation
- **Confidence**: High (rate measurable; n=100 math deterministic — CI-lo ≈ 93.0%, far below BE=97.0%)
- **Effort**: None required — multi-asset shadow is already running. Do not restrict to BTC-only.

### 2b. Disk Management (ACTIVE CONCERN)
- 85% at 23:26Z 07-22, climbing at ~250 MB/h
- Next critical threshold (94%) in ~8–9 days
- **Expected delta**: G8 KILL decision would terminate updown shadow accumulation (~40MB/day from shadow), extend disk runway by weeks
- **Confidence**: High (known growth rate, known drivers)
- **Effort**: Low — KILL decision itself stops accumulation; for faster relief: SSH gzip + prune old hot directories
- Source: pnl_ledger Section 4 operational flags + exec audit Section 3

### 2c. Isotonic Candidate — Do Not Promote Yet (S4 ALERT)
- Deployed: 47 days stale. Candidate: 07-21 refit, cron missed 07-22, n_live=3,733 frozen.
- New concern from calib monitor: candidate raises p_raw=0.15 by +0.023 in the exact zone (p_cal [0.2–0.3)) where today's ECE overconfidence is worst (|diff|=0.195, up from 0.036 yesterday).
- **Expected delta**: premature promotion risks worsening calibration where it is already failing
- **Confidence**: High (ECE deterioration is one-day spike; not yet confirmed trend, but risk is non-trivial)
- **Effort**: Medium — requires human review of tail and pre-plateau behavior; hold until cron health verified and ECE trend stabilizes

### 2d. G3 Winner's Curse — Blocks Band ROI Claims
- Confirmed at n=75 (CI entirely negative: [−75.0%, −34.2%]). G1 and G7 simulated ROI are upper bounds only; cannot be cited as positive evidence.
- **Expected delta**: N/A to compounding (band is dark); relevant as a gating condition on any future BAND re-enable decision
- **Confidence**: High (CI entirely negative at trend-grade n=75)
- **Effort**: None — gatekeeper tracks this; no action until n≥100

---

## Section 3 — Gate Pipeline Review

| Gate | n | Status | Next threshold | ETA | Accelerant |
|---|---|---|---|---|---|
| G8 UPDOWN_CROSSING | 72 | COLLECTING | n=100 (AMBIGUOUS) | ~Jul-25 | Multi-asset shadow already active; no further accelerant |
| G8 realistic pass | 72 | COLLECTING | n≈245–300 (best case) | Aug-3–7 | Requires zero further losses AND extended accumulation |
| G1 BAND_YES | 934 | AMBIGUOUS | n/a (G3 blocks re-cite) | — | Needs capital floor + dispersion recovery |
| G5 THERMO | 125 | REJECTED | — | — | No reconsideration without human directive |
| G6 M1_BETA | 31 | REJECTED | — | — | No reconsideration without human directive |

**G8 — the only active gate:**
- n=100 checkpoint arrives ~Jul-25 (2 days). At n=100 with 2 losses (98W/2L), Wilson CI-lo ≈ 93.0% vs BE=97.0% → AMBIGUOUS is the **certain** outcome, not READY.
- Math reality (gatekeeper FLAG-1): min-pass requires n≈245 (best case, zero further losses). Stochastic loss rate 2/72=2.8% implies ~4.8 additional losses expected by n=245 — each extends the minimum further. EVOLVE twice forecasts KILL as the realistic resolution.
- **What would accelerate USEFUL accumulation**: nothing. The rate (15/day) is already improved. The bottleneck is the statistical reality that 2 losses at n=72 require a very long streak to overcome. No breadth adjustment changes this math.
- **What the human should prepare**: KILL vs. EXTEND decision before n=100 arrives Jul-25. The three options from gatekeeper FLAG-1:
  1. KILL now — terminate shadow, free disk, begin next design
  2. Wait to n=100 → explicitly confirm AMBIGUOUS → then KILL
  3. Extend to n=300 — 15 more days at current rate, KILL still most likely outcome

No other gate is closer to READY. Promoting G5 or G6 from REJECTED requires a human directive not data.

---

## Section 4 — Assumption Attack

### Assumption 1: Dispersion premium persists (band edge thesis)
**Status: NOT SUPPORTED by current data. Threatened.**

- disp_ratio7 = 0.817, declining for 3 consecutive sessions (0.88 → 0.854 → 0.817)
- 0/6 settled days above the 1.10 threshold in the current 7d window (07-17..07-22)
- Day 21 of the inverted dispersion (S3 alert FIRING)
- At n≈98, one session from decision-grade n=100
- Regional breakdown (07-22): EU median=0.851, US/Other median=0.462 (severely inverted), Asia median=1.215 (only region above 1.0 on 07-22)

**What the calib monitor shows**: "The band's core premise — that markets overestimate temperature dispersion relative to what Chainlink resolves — is not supported by any settled day in the current 7d window." (Section 3, S3 alert)

Band is dark (BAND_LIVE=False), so no capital is at risk from this thesis failure. But it conditions any re-enable decision: the edge that powered the band strategy is not currently observable in settled data. Any re-enable absent a dispersion recovery would be betting on a thesis unsupported by the last 21 days of data.

**Asia carve-out signal**: Asia is the only sub-region showing disp_ratio>1.0 in recent data (Beijing 1.937, Chongqing 1.505, Chengdu 1.488 on 07-22). This is a directional signal only — n insufficient for a decision.

### Assumption 2: Fills are not adversely selected
**Status: CONTRADICTED by G3 at n=75 (trend-grade, CI entirely negative).**

- G3 confirmed: filled WR=17.3% vs sim WR=7.6%; CI=[−75.0%, −34.2%] entirely negative
- No new fills since Jul-6 (17 days idle), so no new data to update this finding
- **What exec audit shows**: "Winner's-curse test: **cannot run** (n=0). No conclusion on adverse selection." But G3's prior finding stands at n=75 — the CI is too negative to be noise.

This finding does not affect current operations (all paths dark), but it means any future BAND re-enable must first explain G3 or restructure the quoting logic to avoid the adverse selection pathway.

### Assumption 3: Recycle velocity scales (RECYCLE099)
**Status: UNTESTABLE at zero live activity.**

- exit099_live.jsonl absent for 07-22 (no live convergence sells)
- Shadow engine shows consistent band_struct pricing (d+2: Seoul 0.775, Tokyo 0.770, Chengdu 0.845, Taipei 0.820), which is the feedstock for RECYCLE099
- No live fills → no live recycling → cannot validate scaling
- This assumption can only be tested when BAND_LIVE=True and sum_gate conditions are met

---

## Section 5 — Market Intelligence (day 23 mod 3 = 2 → Platform Mechanics)

**Primary constraint**: This scheduled agent runs without VPS SSH access and without external browser access. Polymarket docs/announcements cannot be independently fetched this session (network blocked for git fetch; web access through proxy required but not tested for external sites).

**Inferred from shadow data (exec audit Section 3)**:
- Shadow engine pricing d+2 bands at sum_ask=0.77–0.845, consistent with the BAND_SUM_MAX=0.85 gate config; no sign of market structure change in pricing
- thermo_maker.jsonl generating 22K–37K rows/day (healthy product volume)
- maker_flow rows 124K–284K/day — suggesting consistent order-book activity in weather markets
- d+1 markets showing sum_gate block (Σask 0.87–1.01, above cap): either normal volatility or possible spread widening

**Delta vs state_log knowledge**: Cannot compute without external access to docs.polymarket.com. Flag for VPS session.

**One structural note from gatekeeper**: Seoul d+1 from Jul-22 (= Jul-23 market) resolves **today**. This is a resolution event that could update G1/G7 n-counts if band_resolution_join.py is run via SSH today. The network block is preventing this.

---

## Section 6 — Three Experiments

### Experiment A: STWA Resolution Verification
**Hypothesis**: The Jul-19 YES leg (146.33 shares @ $0.02 = $2.926 at cost) has resolved YES and ~$143+ is currently in the Polymarket USDC wallet, undetected by bankroll.json (which was written midnight 07-22 and hasn't updated).

**Data**: SSH to VPS → check CLOB wallet USDC balance via py_clob_client or direct RPC → compare to bankroll.json $21.495.

**Time**: 15 minutes. **Cost**: $0.

**Success metric**: CLOB wallet shows balance ≥ $140 (expected if Jul-19 YES leg paid out at $1.00/share for 146.33sh = $146.33 net of the $2.93 cost already booked).

**Decision if YES (balance ~$165)**: Capital clears kernel floor ($40), weekly floor ($75), and ruin floor ($50). Reassess all path re-arms. G8 KILL becomes a non-crisis event. Band re-enable with Asia-restricted config becomes discussable pending dispersion recovery.

**Decision if NO (balance ~$21.50)**: Positions went to zero. Confirm $21.50 as true capital. Formal wind-down plan for G8 KILL at n≈100 (Jul-25). Begin next-strategy design phase.

---

### Experiment B: G8 KILL Confirmation at n=100
**Hypothesis**: When G8 reaches n=100 (~Jul-25, 2 days), CI-lo will be ~93.0% (Wilson 95%), far below BE=97.0%, definitively confirming KILL via the gate formula.

**Data**: Run `shadow_grade.py --refetch` via SSH when n crosses 100 (check via EVOLVE commit or SSH direct).

**Time**: 1h VPS session. **Cost**: $0.

**Success metric**: n=100 confirmed; Wilson CI-lo computed. Decision point: CI-lo < BE → KILL gate; CI-lo ≥ BE → (extremely unlikely per math) extend.

**Decision if CI-lo < BE** (near-certain): Execute KILL procedure — disable updown shadow accumulation (stop ~40 MB/day disk growth), close gatekeeper_state.json for G8, open design-phase planning for next strategy. Free up disk, compute. Human confirms.

**Decision if CI-lo ≥ BE** (extremely unlikely, requires all remaining observations to be wins): Extend gate to n=200; recompute minimum pass threshold.

---

### Experiment C: Asia Sub-Region Dispersion Isolation
**Hypothesis**: Asia cities have maintained disp_ratio > 1.10 as a sub-region in the last 7 settled days (07-17..07-22), even while the global 7d median sits at 0.817.

**Data**: Extract per-city ratios from existing s50 data and calib_monitor_state.json per-day city-level ratio table. Analysis code exists in `analysis/weather/` — no new code needed. Run via SSH or in this agent session using existing data.

**Time**: 2h. **Cost**: $0.

**Success metric**: Asia sub-region 7d median disp_ratio ≥ 1.10 with n ≥ 15 city-days. (07-22 data alone shows Asia median 1.215, but we need the 7d window to confirm persistence.)

**Decision if YES (Asia disp_ratio7 ≥ 1.10)**: Pre-register an Asia-restricted BAND configuration as a candidate for review when capital floors are cleared. Quantify the expected edge degradation from excluding EU and US/Other cities (reduces market count but preserves dispersion premium).

**Decision if NO (Asia disp_ratio7 < 1.10 in 7d window)**: Global inversion is uniform. No regional carve-out salvages the band thesis. Dispersion edge must be waited for across all regions.

---

## Section 7 — Single Best Action

**SSH to VPS today and verify the CLOB wallet USDC balance.**

This action has the highest (compounding impact × P(success)) / effort ratio of any option available:
- P(success): material — STWA Jul-19 YES leg (146.33sh) is overdue-unresolved per pnl_ledger Section 5; the market either resolved YES (→ +$143) or NO/expired (→ $0). The ledger has been flagging this as a wildcard for multiple sessions. This uncertainty should have been resolved within 24–48h of the Jul-19 market resolution date; the answer is already in the wallet.
- Compounding impact: transformative if YES (capital $21.50 → ~$165; all kernel/ruin/weekly floors cleared; path re-arm becomes possible); closure if NO (confirm $21.50, begin wind-down).
- Effort: one SSH session, 15 minutes.

**Concrete first step**: `ssh {vps} "python3 -c 'from py_clob_client.client import ClobClient; c=ClobClient(...); print(c.get_balance())'"` or equivalent wallet check command.

**Specialist report citations**:
- pnl_ledger_report.md Section 5: "STWA wildcard: Jul-19 YES leg (146.33sh) could deliver ~+$143 to wallet without any bot action. This event, if it occurs, will appear as a large unexplained capital jump — attribute to STWA FIRST."
- gatekeeper_report.md FLAG-4: "Klaus is running but has no executable trading path. Capital $21.495 = 7.2% of original. Bot has no self-recovery path without explicit human restart decision."
- exec_audit_report.md Section 6: "Capital: $21.495 ... Capital note: `$21.495` reflects wallet state as of snapshot; user manual sells and withdrawals are not tracked here — do not infer ruin or session PnL from this figure alone."

The PnL ledger explicitly notes this is not confirmed from CLOB. Until the wallet is directly inspected, the equity range is [$21.50, $167+]. The CLOB check resolves this.

---

## PROPOSED ACTIONS (human review)

1. **SSH CLOB wallet check today** (Experiment A): Verify Jul-19 STWA YES leg resolution. Determines whether capital is $21.50 or ~$165+. Informs all downstream decisions. Priority: URGENT (overdue 4+ days).

2. **G8 threshold decision before Jul-25**: Confirm whether to KILL now, wait to n=100, or extend to n=300. The gatekeeper math (FLAG-1) is clear: n=200 is now insufficient (198W/2L CI-lo=96.4% < BE=97.0%); n=245 is the best-case minimum. With stochastic losses, KILL is the realistic resolution. Human should not arrive at n=100 (~Jul-25) without a decision framework in place.

3. **Hold isotonic candidate** (S4 follow-up): Do not promote to deployed until (a) cron health on VPS is verified, (b) the ECE [0.2–0.3) worsening trend (|diff| 0.036→0.195 in one day) is checked over 3 sessions, and (c) tail behavior at p_raw=1.0 and pre-plateau zone p_raw=0.15 is reviewed with human sign-off.

4. **Disk monitoring**: At 85% and ~250 MB/h, next crisis (~94%) is 8–9 days away. G8 KILL will reduce shadow accumulation. If KILL is delayed, schedule a disk-prune SSH session by Jul-28.

5. **Resolve G3 before any band re-enable**: Winner's curse is confirmed at n=75 (CI entirely negative). Any BAND re-enable design must explicitly address the adverse-selection pathway, not just cite G1/G7 simulation ROI.

---

*Report-only. No code, config, or gate changes made this session.*  
*All claims backed by: exec_audit_report.md (07:16Z), calib_monitor_report.md (08:20Z), gatekeeper_report.md (09:00Z), pnl_ledger_report.md (23:37Z 07-22), data-mirror snapshot (10:16:06Z 07-23).*
