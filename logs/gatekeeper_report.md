# Gate-Keeper Report — 2026-08-11T09:15Z

**STALL #22 — ABORT: `systemd: failed/unknown` (day 18 since 2026-07-24 shutdown). Service status is not `active`.**

Snapshot: `2026-08-11T09:10:03Z` (fresh, NOT > 6h old). Abort triggered by service-status check only.
Bankroll: $88.750373 (unchanged). All trading paths disabled: `BAND_LIVE=False`, `BAND_NO_ENABLED=False`, `STWA_REGULAR_YES_ENABLED=False`, `STWA_REGULAR_NO_ENABLED=False`.

---

## Gate Ledger

| gate | n | +24h | WR | ROI | CI95 | status | ETA |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES per slice (d0/1/2 × off 0/1/2 × price band) | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark 17d; band_struct_lite never existed) |
| G2 BAND_NO + PAIR_FAV legs | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark 17d; exit099_live dark 35d; BAND_NO_ENABLED=False since 2026-07-02) |
| G3 FILLED-vs-FIRED divergence | null | 0 | — | — | — | COLLECTING | ∞ (trades.jsonl dead 2026-07-19; no fills in 23 days) |
| G4 BASKET_EXIT (cash green baskets) | null | 0 | — | — | — | COLLECTING | ∞ (basket_exit_shadow dark 35d; absent from shadow_summary) |
| G5 THERMO upper-tail maker-NO | null | 0 | — | — | — | COLLECTING | ∞ (thermo_maker dark 17d; absent from shadow_summary) |
| G6 M1-beta METAR lockout slices | null | 0 | — | — | — | COLLECTING | ∞ (metar_lockout dark 17d; absent from shadow_summary) |
| G7 SUM_POSTED [0.70,0.85] slice | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark 17d; band_struct_lite never existed) |

All gate shadow files confirmed absent from `data/shadow_summary.json` (no band_struct, exit099_live, basket_exit_shadow, thermo_maker, metar_lockout entries). Only active loggers today: badatmath_watch, maker_flow, minmax_coherence, count_lock, updown_sniper/snap_*, flb_screener.

---

## State Transitions vs Prior Run (2026-08-10T09:17Z)

None. All 7 gates frozen at `n=null, COLLECTING`. No data accumulated. No transitions possible.

---

## PROPOSED ACTIONS (human review)

None. No gate has reached READY or REJECTED this run.

Standing action (unchanged since 2026-07-26): **SSH to VPS → restart `klaus` systemd service → verify `active` status.** Gate accumulation is completely frozen while service is down. Data mirror timer continues to run (snapshot fresh), but all trading-path shadow loggers are dark.

---

*run_ts: 2026-08-11T09:15:00Z | stall_count: 22 | prior_run: 2026-08-10T09:17:00Z | abort: systemd_failed_day18*
