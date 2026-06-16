# Gate-Keeper Validation Report — 2026-06-16T09:29Z

**Snapshot age**: 28 min (2026-06-16T09:01:09Z) — VALID
**System**: `klaus systemd: active` (uptime since 2026-06-15 05:52 UTC)
**Capital**: $239.15
**Prior run**: 2026-06-15T10:35:00Z (+ addendum 10:49Z)

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA to threshold |
|------|---|------|----|-----|------|--------|-----------------|
| BAND_YES (all slices) | 1,584‡ | +239 | — | unverified | unverified | COLLECTING | N/A (CI blocked) |
| BAND_NO + PAIR_FAV | 39 post-fix | +2 (NO), +0 (PAIR_FAV) | — | unverified | unverified | COLLECTING | rate stalled — see below |
| FILLED_VS_FIRED | 153 | +11 | — | net +$58.56★ | n/a | COLLECTING | n>40 ✓ (watch item) |
| BASKET_EXIT | 6,103 (new scope) | +501 | — | uncomputable | — | COLLECTING | n>>100, metric blocked |
| THERMO_MAKER_NO | 3 resolved | +0 | 33% (1/3) | — | — | COLLECTING | kill gate ~20 far off — see below |
| M1_BETA_LOCKOUT | 1 | 0 | — | — | — | COLLECTING | dormant |
| SUM_POSTED_0.70–0.85 | 1,211‡ | +115 | — | unverified | unverified | COLLECTING | N/A (CI blocked) |

‡ Per-cid (Gate 1) / per-(cid,days_out,side) (Gate 7) first-fire dedup, computed fresh this run from `band_struct_lite.jsonl` across the 6 dated shadow dirs actually available in `data-mirror` (Jun 11–16; Jun 10 not mirrored). Numbers are not directly comparable to prior runs' Jun10-anchored cumulative counts — see per-gate detail for the day-by-day reconciliation.

★ Not a gate ROI — see Gate 3 detail. This is the corrected, audit-consistent realized cash P&L for the band system since Jun 11, replacing a flawed re-derivation this run almost shipped (see "Methodology Trap" below).

**No gate transitioned to READY or REJECTED this run. All 7 remain COLLECTING**, same as Jun 13/14/15.

---

## State Transitions vs Prior

None. The structural blocker is unchanged: `band_resolution_join.py` ran successfully end-to-end this run (proving the canonical-validator layout reconstruction works) but resolved **0 of 3,100 deduped legs** — `gamma-api.polymarket.com` returns HTTP 403 from this container on every batch. This is the same block documented 06-13/14/15; today's run reconfirms it rather than discovering anything new.

---

## ⚠️ Methodology Trap Caught This Run (read before trusting any future FILLED_VS_FIRED number)

This run initially computed Gate 3 by filtering `trades.jsonl` for `bond_entry_class=="WEATHER_STRUCT_BAND"` and `exit_reason=="STWA_RESOLVED"`: n=115 (98 YES + 17 NO), **WR=5.1% YES / 17.6% NO, bootstrap CI95 = [−95.7%,−61.0%] / [−100.0%,−36.2%] — i.e. a catastrophic, statistically airtight loss.**

That number is **wrong**, and it is wrong for a reason already diagnosed by a human audit on **2026-06-14 05:55 UTC** (state_log line 746), which this run almost reproduced blind: `STWA_RESOLVED` only captures band positions held to actual settlement — **all the losers**. Winning band positions get cashed out early via the RECYCLE099 cascade-sell (sold at ~$0.99 once a win is locked in, logged separately in `exit099_live.jsonl`, never reaching `STWA_RESOLVED`). Filtering on `STWA_RESOLVED` alone is a survivorship-bias filter that keeps only losses.

**Corrected accounting (extends the 06-14 audit's window through today):**

| Component | n | PnL |
|---|---|---|
| RECYCLE099 winner cash-outs (Jun 11–16) | 61 | +$292.80 |
| STWA_RESOLVED losers (Jun 11–16, WEATHER_STRUCT_BAND) | 101 | −$236.25 |
| BAND_MERGE pair completions (Jun 11–16) | 5 | +$2.01 |
| **Honest band-era net** | **167** | **+$58.56** |

This roughly matches the 06-14 audit's own partial-day estimate (+$52.68 as of 05:55 that morning, before most of the window's RECYCLE099 sells had happened) — consistent, not contradictory. The band system is realized **flat-to-slightly-positive** over the last 5+ days, not the −80% to −100% a naive STWA_RESOLVED filter implies.

**This is NOT a gate verdict.** It's an aggregate $ cash-flow number across heterogeneous leg sizes, not a bootstrapped per-leg ROI CI, and it still doesn't answer Gate 1/2's pre-registered question (resolution truth on the FIRES population, not just realized fills). It's reported here purely to (a) correct course before a false-alarm verdict shipped, and (b) leave a durable warning so the next agent reaching for `trades.jsonl` + `STWA_RESOLVED` doesn't repeat it. **Flag for the Exec Auditor**: a real bootstrapped WR/ROI on the corrected (RECYCLE099 + STWA_RESOLVED + BAND_MERGE) filled population, per side, would be a legitimate and valuable Gate 3 deliverable — this run did not have time to reconstruct clean per-leg stakes for it.

---

## Per-Gate Detail

### GATE 1 — BAND_YES *(scale-up gate; threshold n=100/slice)*

Fresh first-fire dedup from `band_struct_lite.jsonl`, Jun 11–16 (Jun 10 absent from mirror):

| Date | New unique cids | Cumulative (this window) |
|---|---|---|
| Jun 11 | 270 | 270 |
| Jun 12 | 297 | 567 |
| Jun 13 | 267 | 834 |
| Jun 14 | 257 | 1,091 |
| Jun 15 | 254 | 1,345 |
| Jun 16 (partial, ~38%) | 239 | **1,584** |

Jun 13/14 match the prior run's table exactly (267, 257); Jun 11/12 run higher here because this window has no Jun 10 baseline, so some cids that truly first-fired Jun 10 register as "new" on Jun 11 in this recompute. Directionally consistent with prior (1,381 cumulative through Jun 15); not worth false-precision reconciling further.

**Per-slice (days_out × offset), this window:**

| days_out | off=0 | off=1 | off=2 (shadow only, not posted live) |
|---|---|---|---|
| 0 | 215 | 387 | 93 |
| 1 | 237 | 456 | 386 |
| 2 | 270 | 503 | 437 |

All live-posted slices (off≤1; d+0 restricted to off=0 per `BAND_YES_MAX_OFF_D0=0`) are several multiples above n=100.

**CI**: canonical `band_resolution_join.py` run this session, full layout reconstruction per the runbook, resolved **0/3,100** legs (Gamma 403). Cannot certify CI_lower>0. Status unchanged: COLLECTING.

---

### GATE 2 — BAND_NO + PAIR_FAV *(threshold n=100, counting from 2026-06-12 13:05 UTC fix)*

**NO legs (post-fix), recomputed from `fire_no` records:**

| Date | New unique cids |
|---|---|
| Jun 12 (partial, post-13:05) | 3 |
| Jun 13 | 14 |
| Jun 14 | 18 |
| Jun 15 | 4 |
| Jun 16 | 0 |

**n = 39** (+2 vs prior estimate of 37). The accumulation rate has **stalled**, not continued at the prior ~12.6/day estimate: 18→4→0 over the last three days. At the current trailing rate this is no longer on pace for the prior "~Jun 20" ETA — recommend the human re-examine why NO fires dried up (cash allocation now favors YES breadth post the Jun 15 05:51 stake-floor change? NO candidates exhausted? worth a STRUCT-BAND-Q log check).

**PAIR_FAV legs**: still **0** confirmed (`pair_fav` reason count = 0 across all 6 days in the mirror). Unchanged from prior — PAIR-SHADOW (measure-only) logger is the active instrument here, not PAIR_FAV itself.

**Status**: COLLECTING.

---

### GATE 3 — FILLED_VS_FIRED *(watch threshold n=40 filled)*

From `maker_fills_recent.log` (rolling window, registered MAKER-FILL events):

| Metric | Value |
|---|---|
| Unique CIDs filled (gate n) | **153** (+11 vs prior 142) |
| YES fills | 127 |
| NO fills | 26 |

Watch threshold (n≥40) met since prior run. See the Methodology Trap section above for this run's corrected realized-PnL reconstruction (+$58.56 net, n=167 settled events Jun 11–16) — that is the closest this run gets to a winner's-curse read, and it does **not** show the catastrophic divergence a naive filter suggested. A clean per-leg bootstrapped comparison (filled-leg ROI vs all-fires ROI) remains blocked on the FIRES side (Gamma 403) and unattempted on the FILLED side pending proper per-leg stake reconstruction. Status: COLLECTING.

---

### GATE 4 — BASKET_EXIT *(threshold n=100 basket-days — definition stale, flagged again)*

Unique (city, t_close) all_green baskets across the full mirrored window (Jun 12–16; Jun 11 file empty): **6,103** (+501 in today's file alone). Still dramatically n>>100 under the expanded 22-city scope flagged on Jun 15.

**Cash-out vs hold metric: still uncomputable.** This run attempted a wall-clock proxy (last logged snapshot per basket where `t_close < now`, check `all_green`) and got 5,324 "resolved-and-all-green" — which is **not trustworthy** (it contradicts the prior run's careful same-day check of "0 resolved-and-all_green," and is exactly the kind of price-drift/staleness proxy the anti-sycophancy rules prohibit substituting for Gamma resolution truth). Discarded; not reported as a finding. Gate 4 still needs the human to redefine the canonical basket-day unit before this gate can move at all.

**Status**: COLLECTING (unchanged).

---

### GATE 5 — THERMO_MAKER_NO *(kill gate: first 20 resolved)*

**Revised down from prior estimate.** Prior runs estimated "~23 candidates past resolution date" / "≤12–15 placed bets" from candidate-log heuristics. This run instead found the actual placed-and-resolved trades directly, via `bond_entry_class=="WEATHER_THERMO"` in `trades.jsonl` (the correct tag — `signal_source` never contains "THERMO", it's generic `WEATHER/{city}/WEATHER_MAKER`):

**n = 3 confirmed resolved** (all `STWA_RESOLVED`, no RECYCLE099 censoring detected — checked candidate-token overlap with recycle exits, 0 overlap): PnL +$0.11, −$5.67, −$5.39. WR = 1/3. Per the pre-registered discipline, **n=3 is just a count, not a trend, not a decision.**

This materially revises the ETA: at ~3 resolved in the ~5 days since the strategy went live (06-11 22:40), reaching the kill gate of 20 resolved is **much further out than the prior "~3–5 days" estimate** — more likely several weeks at the current pace, unless placement frequency increases.

**Status**: COLLECTING.

---

### GATE 6 — M1_BETA_LOCKOUT *(threshold n=100)*

Unchanged: **n=1** (Moscow, net_pnl=−$1.65, `bond_entry_class=="M1_BETA_PROBE"`). `metar_lockout.jsonl` is empty across all 6 mirrored days — zero new shadow activity. Strategy dormant.

**Status**: COLLECTING — dormant.

---

### GATE 7 — SUM_POSTED_0.70–0.85 *(threshold n=100)*

Fresh recompute, first-fire per (cid, days_out, side='YES') dedup, sum_posted at fire time:

| Date | New in [0.70,0.85] |
|---|---|
| Jun 11 | 123 |
| Jun 12 | 263 |
| Jun 13 | 209 |
| Jun 14 | 265 |
| Jun 15 | 236 |
| Jun 16 (partial) | 115 |

**n = 1,211** this window (+115 today). Jun 13 matches prior run exactly (209); other days run somewhat higher, consistent with the same Jun-10-baseline-missing effect noted in Gate 1. Already far past threshold; CI blocked by the same Gamma 403 as Gate 1.

**Status**: COLLECTING.

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED. No flag/param changes recommended this run** — the anti-sycophancy rule is explicit that n≥threshold without CI_lower>0 is not a verdict, and this run's only candidate "decision-grade" finding (the −80%/−95% CI on naive STWA_RESOLVED filtering) turned out to be the known survivorship-bias artifact, not real evidence. Carrying forward open items from prior runs, unchanged:

1. **Push per-leg `band_resolution_join.py` output to data-mirror from the VPS** (where Gamma is reachable) — still the single action that unblocks Gates 1, 2, and 7. Confirmed again this run that the container-side join executes correctly against the runbook's reconstructed layout but is 100% network-blocked (0/3,100 resolved).
2. **Gate 4 definition refresh** — basket-day unit ambiguous under the 22-city scope expansion; still unresolved since Jun 15.
3. **Kill-switch staleness** (not a gate, flagging again since it's still live): `bankroll.json` still shows `daily_start_capital=$15.95` against current capital $239.15 — the −$10/day loss halt cannot fire at any realistic drawdown. This was flagged 06-15 in the prior report's operational notes and remains unfixed as of this snapshot. Out of this agent's report-only scope to fix, but worth a direct escalation if no Tier-3 action has been taken.
4. **Gate 2 NO-leg rate stall** (new observation this run) — post-fix NO fires dropped to 0 today after peaking at 18/day on Jun 14. Worth a STRUCT-BAND-Q log check to see if this is cash-starvation (YES breadth change competing for the same pool) or candidate exhaustion.
