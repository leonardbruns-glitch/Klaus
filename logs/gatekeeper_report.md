# Gate-Keeper Report — 2026-08-15T09:13Z

**STALL #26 — ABORT: `systemd: failed/unknown` (day 22 since 2026-07-24 shutdown). Service status is not `active`.**

Snapshot: `2026-08-15T09:06:16Z` (fresh, 7 min old). Abort triggered by service-status check only. No new data accumulated on any gate.
Bankroll: $88.750373 (unchanged, 22 days zero-activity). All trading paths disabled: `BAND_LIVE=False`, `BAND_NO_ENABLED=False`, `STWA_REGULAR_YES_ENABLED=False`, `STWA_REGULAR_NO_ENABLED=False`.

---

## Gate Ledger

| gate | n | +24h | WR | ROI | CI95 | status | ETA |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES per slice (d0/1/2 × off 0/1/2 × price band) | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark since 2026-07-25 [21d]; band_struct_lite never in data-mirror) |
| G2 BAND_NO + PAIR_FAV legs | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark 21d; exit099_live dark since 2026-07-07 [39d]; BAND_NO_ENABLED=False since 2026-07-02) |
| G3 FILLED-vs-FIRED divergence | null | 0 | — | — | — | COLLECTING | ∞ (trades.jsonl last live row 2026-07-19; no fills 27d; no maker fills expected) |
| G4 BASKET_EXIT (cash green baskets) | null | 0 | — | — | — | COLLECTING | ∞ (basket_exit_shadow dark since 2026-07-07 [39d]; absent from shadow_summary) |
| G5 THERMO upper-tail maker-NO | null | 0 | — | — | — | COLLECTING | ∞ (thermo_maker dark since 2026-07-25 [21d]; absent from shadow_summary) |
| G6 M1-beta METAR lockout slices | null | 0 | — | — | — | COLLECTING | ∞ (metar_lockout dark since 2026-07-25 [21d]; absent from shadow_summary) |
| G7 SUM_POSTED [0.70,0.85] slice | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark 21d; band_struct_lite never existed; sum_posted field unavailable) |

---

## State Transitions vs Prior Run (2026-08-14T09:31Z)

None. All gates remain COLLECTING/null (stall day 21 → 22). Zero n accumulated. All shadow files remain dark.

---

## PROPOSED ACTIONS (human review)

None. No gate has newly reached READY or REJECTED.

**Context**: System intentionally stopped since 2026-07-24 (owner directive, EVOLVE 2026-07-26). Gatekeeper cannot accumulate n without active trading. Stall loop continues until Klaus is restarted on VPS or owner formally closes these gates.
