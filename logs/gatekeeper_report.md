# STALL — Gate-Keeper 2026-07-25 | system_status=failed/unknown

> **ABORT CONDITION MET**: `system_status.txt` shows `failed / unknown` — not `active`.
> Snapshot age: < 1h (2026-07-25T09:03:24Z, fresh). Data-mirror still running.
> Shadow_grade.py and band_resolution_join.py inaccessible (system down + network blocked in remote env).
> G8 KILL FORMALIZATION IS IMMINENT — n≥100 threshold ETA bracket: Jul-24 evening – Jul-25 afternoon.
> Prior run: 2026-07-24T09:12:00Z. This run: 2026-07-25T09:03Z (estimated).

---

## GATE LEDGER

| Gate | n | +24h est | WR | ROI | CI 95% | Status | ETA to threshold |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES (per slice, d0/d1/d2 × off0/1/2 × band) | 934 resolved | 0 | 15.3% | +4.0%† | [-10.9%, +21.1%] | AMBIGUOUS | N/A — band dark day 19; n frozen |
| G2 BAND_NO (post-guard, ≥Jul-12) | 115 shadow | 0 | 68.7% | +1.3%† | [-11.9%, +12.7%] | AMBIGUOUS | N/A — band dark; live n=51 effectively REJECTED |
| G2 PAIR_FAV_YES (post-guard, ≥Jul-05) | 9 | 0 | — | — | — | COLLECTING | Indeterminate (band dark) |
| G2 PAIR_FAV_NO (post-guard, ≥Jul-05) | 9 | 0 | — | — | — | COLLECTING | Indeterminate (band dark) |
| G3 FILLED vs FIRED divergence | 75 filled | 0 | 17.3% filled | −75.8% | [-75.0%, -34.2%] | WATCH_ITEM | n≥40 met (CONFIRMED winner's curse) |
| G4 BASKET EXIT | — | — | — | — | — | **VOID** | Permanently retired 2026-06-22 |
| G5 THERMO_MAKER_NO (first 20 resolved) | 125 | 0 | — | 0.0% | [-9.0%, +2.0%] | **REJECTED** | Threshold met; human confirmed |
| G6 M1-BETA LOCKOUT (thin-margin [0.2,0.5)°C) | 31 | 0 | 74.2% | -0.6% | [-20.6%, +24.4%] | **REJECTED** | Threshold met; human confirmed |
| G7 SUM_POSTED [0.70, 0.85] slice | 382 | 0 | — | +11.5%† | [-11.4%, +38.9%] | AMBIGUOUS | n=100 met (382); CI straddles 0 + ROI is upper bound |
| **G8 UPDOWN_CROSSING p≥0.995 5m (post-cut)** | **88 confirmed** | **+7–23 est** | **95.45%** | **−$5.52 sim** | **[88.9%, 98.2%]** | **COLLECTING — KILL-LOCKED** | **n=100 ETA: Jul-24 eve – Jul-25 (bracket; may already be ≥100)** |

† ROI is UPPER BOUND — G3 winner's curse CONFIRMED (n=75 filled WR 17.3% vs sim 7.6%). No band re-enable argument may cite G1/G7 sim CI as evidence.

---

## STATE TRANSITIONS vs PRIOR RUN (2026-07-24T09:12Z)

**NEW this run:**
1. **SYSTEM FAILED**: Prior run `_run_meta.system_active_pass=true`; this run `failed/unknown`. Service last active 2026-07-24T10:09:19Z. No restart observed. Shadow_grade.py and band_resolution_join.py now inaccessible from the remote env (network-blocked) AND from the VPS (service down). All n values that require VPS-side scripts are frozen.
2. **band_dark_days: 18 → 19** (BAND_LIVE=False since 2026-07-06T22:08Z).
3. **G8 n estimate: 88 → ~95–111 (unconfirmed)**: At confirmed rate 7–16/day, 35h elapsed since last authoritative gate_ledger (Jul-23 22:05Z). Conservative (7/day): n≈95. Prior window rate (16/day): n≈111. **n=100 may already have been crossed — kill formalization pending authoritative shadow_grade.py confirmation.** Status held at COLLECTING pending confirmation; cannot auto-transition without authoritative count.

**Unchanged (0 new data):**
- G1, G2, G3, G5, G6, G7: zero new fires, fills, or resolutions since prior run.
- G4: VOID (permanent).
- Capital: $21.495442 unchanged (burn rate zero, all paths stopped).

---

## G8 KILL-LOCK MATH (immutable)

| Scenario | n | k (wins) | WR | vs BE=96.49% | Verdict |
|---|---|---|---|---|---|
| Confirmed baseline | 88 | 84 | 95.45% | −1.04pp below | KILL-LOCKED |
| Conservative est (+7 all-W) | 95 | 91 | 95.79% | −0.70pp below | KILL-LOCKED |
| Best-case at threshold | 100 | 96 | 96.00% | −0.49pp below | **KILL FIRES** |
| Min n to clear BE (0 further losses) | 114 | 110 | 96.49% | = | Theoretically pass (unrealistic: 0 losses over 26 more events) |
| Realistic (assume WR trends to 95%) | 114+ | <110 | <96.49% | below | **KILL** |

The 4 losses are locked. No realistic ask path clears BE. Kill fires at n≥100; the only question is when the authoritative count is obtained.

---

## PER-ASSET CELLS (G8, from gate_ledger Jul-23 21:56Z)

| Asset | n | WR | BE | Sim PnL | Verdict |
|---|---|---|---|---|---|
| BTC | 134 | 96.3% CI[91.6%,98.4%] | 96.3% | −$0.65 | **REJECTED** — CI-lo 91.6% vs BE 96.3%; p≥0.995 n=81 WR 95.1% −$4.81 |
| DOGE | 20 | 95.0% (19W/1L) | 96.1% | −$1.06 | COLLECTING |
| ETH | 38 | 100% (38W/0L) CI[90.8%,100%] | 96.8% | +$6.32 | COLLECTING — sole loss-free cell; CI-lo 90.8% << BE; mirrors pre-loss pattern of other cells |
| SOL | 17 | 94.1% (16W/1L) | 96.5% | −$2.36 | COLLECTING |
| XRP | 23 | 91.3% (21W/2L) | 96.1% | −$5.67 | COLLECTING — worst cell; p≥0.995 sub-slice 7W/2L −$7.74 |

Cross-cell read: 4/5 net-negative sim; BTC (only n≥100 cell) REJECTED. Pattern uniform: certainty-taker fails wherever n grows. ETH's 38/38 mirrors the pre-loss pattern every other cell showed.

---

## STRUCTURAL BLOCKERS (all active)

- UPDOWN_STOP: sniper CUT 2026-07-19T11:26Z (PF 0.79 < 0.80 charter rail, 27 settles)
- WIND-DOWN: BAND_LIVE=False since 2026-07-06T22:08Z (day 19)
- LDA_STOP: rolling-20 worst −$36.39 < −$30 threshold
- Capital $21.495 = 24.1% of ruin_floor $89.16 — all band paths mechanically blocked
- G3 winner's curse: sim CI is an upper bound; cannot cite G1/G7 to justify re-enable
- G5 THERMO / G6 M1-BETA: REJECTED; no reconsideration without human directive
- **System service: failed** — no automated recovery; human SSH required

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY this run.** No gates newly hit REJECTED (G5/G6 remain REJECTED, confirmed earlier).

**Pending formalization (triggered when G8 n≥100 confirmed):**

> **KILL UPDOWN_CROSSING CLASS** — pre-registered kill rule (state_log 2026-07-19T14:30Z):
> *"Point WR < BE at n≥100 → recommend class CLOSED."*
> Current n=88, estimated ≈95–111 (unconfirmed). Kill is mathematically certain regardless of future results (min n-to-clear = 114, zero further losses).
> **Action for human**: When VPS is restored and `shadow_grade.py --refetch` confirms n≥100:
> 1. Set `UPDOWN_CROSSING_ENABLED = False` (or equivalent flag)
> 2. Do NOT re-enable without fresh pre-registration and a clean candidate pool
> 3. Close the BTC cell immediately (n=134 REJECTED)
> 4. Do NOT promote ETH solo — same pattern, CI-lo << BE, likely pre-loss phase

**Urgent non-gate action:**

> **SYSTEM SERVICE FAILED** — `systemd: failed/unknown` since after 2026-07-24T10:09:19Z.
> Burn rate is zero (all paths stopped) so no capital risk from the failure.
> However: shadow accrual, watchdog, and gate_ledger refreshes are all paused.
> **Action for human**: SSH to VPS, diagnose systemd failure, restart when ready.

---

*Run: 2026-07-25T09:03Z (stall; system down) | Prior: 2026-07-24T09:12Z | Branch: claude/find-lag-parameter-rFQ0N*
