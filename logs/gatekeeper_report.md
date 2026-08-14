# Gate-Keeper Report — 2026-08-14T09:31Z

**STALL #25 — ABORT: `systemd: failed/unknown` (day 21 since 2026-07-24 shutdown). Service status is not `active`.**

Snapshot: `2026-08-14T09:31:16Z` (fresh, NOT > 6h old). Abort triggered by service-status check only.
Bankroll: $88.750373 (unchanged, 21 days zero-activity). All trading paths disabled: `BAND_LIVE=False`, `BAND_NO_ENABLED=False`, `STWA_REGULAR_YES_ENABLED=False`, `STWA_REGULAR_NO_ENABLED=False`.

---

## Gate Ledger

| gate | n | +24h | WR | ROI | CI95 | status | ETA |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES per slice (d0/1/2 × off 0/1/2 × price band) | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark since 2026-07-25 [20d]; band_struct_lite never existed in data-mirror) |
| G2 BAND_NO + PAIR_FAV legs | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark 20d; exit099_live dark since 2026-07-07 [38d]; BAND_NO_ENABLED=False since 2026-07-02) |
| G3 FILLED-vs-FIRED divergence | null | 0 | — | — | — | COLLECTING | ∞ (trades.jsonl last live row 2026-07-19; no fills 26+ days; no maker fills expected) |
| G4 BASKET_EXIT (cash green baskets) | null | 0 | — | — | — | COLLECTING | ∞ (basket_exit_shadow dark since 2026-07-07 [38d]; absent from shadow_summary) |
| G5 THERMO upper-tail maker-NO | null | 0 | — | — | — | COLLECTING | ∞ (thermo_maker dark since 2026-07-25 [20d]; absent from shadow_summary) |
| G6 M1-beta METAR lockout slices | null | 0 | — | — | — | COLLECTING | ∞ (metar_lockout dark since 2026-07-25 [20d]; absent from shadow_summary) |
| G7 SUM_POSTED [0.70,0.85] slice | null | 0 | — | — | — | COLLECTING | ∞ (band_struct dark 20d; band_struct_lite never existed; sum_posted field source unavailable) |

---

## State Transitions vs Prior Run (2026-08-13T09:15Z)

None. All gates remain COLLECTING/null (stall day 20 → 21). No n accumulated. No shadow files have come back online.

---

## PROPOSED ACTIONS (human review)

None. No gate has newly reached READY or REJECTED.

**Context for the human**: System has been intentionally stopped since 2026-07-24 (owner directive, documented in EVOLVE 2026-07-26). The gatekeeper cannot accumulate n without active trading. The stall loop will continue producing null reports until:
1. Klaus is restarted on VPS and shadow loggers resume, OR
2. Owner formally closes these gates as no-longer-applicable.
