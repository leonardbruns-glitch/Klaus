# Gate-Keeper Report — 2026-08-13T09:15Z

**STALL #24 — ABORT: `systemd: failed/unknown` (day 20 since 2026-07-24 shutdown). Service status is not `active`.**

Snapshot: `2026-08-13T09:08:16Z` (fresh, NOT > 6h old). Abort triggered by service-status check only.
Bankroll: $88.750373 (unchanged, 20 days zero-activity). All trading paths disabled: `BAND_LIVE=False`, `BAND_NO_ENABLED=False`, `STWA_REGULAR_YES_ENABLED=False`, `STWA_REGULAR_NO_ENABLED=False`.

---

## Gate Ledger

| gate | n | +24h | WR | ROI | CI95 | status | ETA |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES per slice (d0/1/2 × off 0/1/2 × price band) | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark since 2026-07-25 [19d]; band_struct_lite never existed in data-mirror) |
| G2 BAND_NO + PAIR_FAV legs | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark 19d; exit099_live dark since 2026-07-07 [37d]; BAND_NO_ENABLED=False since 2026-07-02) |
| G3 FILLED-vs-FIRED divergence | null | 0 | — | — | — | COLLECTING | ∞ (trades.jsonl last live row 2026-07-19; no fills in 25 days; no maker fills expected) |
| G4 BASKET_EXIT (cash green baskets) | null | 0 | — | — | — | COLLECTING | ∞ (basket_exit_shadow dark since 2026-07-07 [37d]; absent from shadow_summary) |
| G5 THERMO upper-tail maker-NO | null | 0 | — | — | — | COLLECTING | ∞ (thermo_maker dark since 2026-07-25 [19d]; absent from shadow_summary) |
| G6 M1-beta METAR lockout slices | null | 0 | — | — | — | COLLECTING | ∞ (metar_lockout dark since 2026-07-25 [19d]; absent from shadow_summary) |
| G7 SUM_POSTED [0.70,0.85] slice | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark 19d; band_struct_lite never existed; sum_posted field source unavailable) |

All gate shadow files confirmed absent from `data/shadow_summary.json`. Active loggers today: badatmath_watch, count_lock, maker_flow, minmax_coherence, flb_screener, updown_sniper/snap_* — none are gate inputs for G1–G7. All gate shadow loggers have been dark for 19–37 days.

---

## State Transitions vs Prior Run (2026-08-12T09:17Z)

None. All 7 gates frozen at `n=null, COLLECTING`. +24h = 0 on every gate. No transitions possible while service is down.

---

## PROPOSED ACTIONS (human review)

None. No gate has reached READY or REJECTED this run.

**Standing action (unchanged since 2026-07-26, now day 20 of stall):**
SSH to VPS → `sudo systemctl start klausbot` → verify `active (running)`. Gate accumulation is completely frozen while service is down. Every live shadow logger for G1–G7 has been dark for 19–37 days. The data-mirror timer continues to run (snapshots fresh every 15 min), but all trading-path shadow loggers produce zero rows. Bankroll is safe and unchanged at $88.750373; no new losses, but zero evidence accumulation toward any gate threshold.

---

*run_ts: 2026-08-13T09:15:00Z | stall_count: 24 | prior_run: 2026-08-12T09:17:00Z | abort: systemd_failed_day20*
