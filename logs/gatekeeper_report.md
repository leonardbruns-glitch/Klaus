# Gate-Keeper Report — 2026-07-21T09:07Z

**Snapshot**: 2026-07-21T09:07:20Z (age: <1h — FRESH)
**Klaus systemd**: active | **Capital**: $21.495 (24.1% of ruin floor $89.16)
**Structural posture**: UPDOWN_STOP active (cut 2026-07-19T11:26Z) | Band dark day 15 (BAND_LIVE=False since Jul-06)

---

## Gate Ledger

| Gate | n (resolved) | +24h Δ | WR | ROI (sim) | CI 95% | Status | ETA to thresh |
|---|---|---|---|---|---|---|---|
| **G8 UPDOWN_CROSSING post-cut** (p≥0.995 5m multi-asset) | **38** | **+36** | **97.4%** (37W/1L) | +$0.61 | [86.5%, 99.5%] | **COLLECTING** | ~2.3d (~Jul-23) |
| G1 BAND_YES (per-slice YES gate) | 934 | +0 | 15.3% | +4.0%† | [-10.9%, +21.1%] | AMBIGUOUS (extended) | N/A — over thresh, straddles 0 |
| G2a BAND_NO d1 (shadow CI) | 115 | +0 | 68.7% | +1.3%† | [-11.9%, +12.7%] | AMBIGUOUS (extended) | N/A — over thresh, straddles 0 |
| G2b PAIR_FAV_YES | 9 | +0 | N/A | N/A | N/A | COLLECTING (frozen) | Indeterminate (band dark) |
| G2c PAIR_FAV_NO | 9 | +0 | N/A | N/A | N/A | COLLECTING (frozen) | Indeterminate (band dark) |
| G3 FILLED_vs_FIRED (winner's curse) | 75 filled | +0 | 17.3% filled | -75.8% actual | [-75.0%, -34.2%] | WATCH_ITEM (confirmed) | N/A — permanent watch item |
| G4 BASKET_EXIT | VOID | — | — | — | — | VOID (retired Jun-22) | N/A |
| G5 THERMO_MAKER_NO | 125 | +0 | — | ~0% net fees | [-9.0%, +2.0%] | **REJECTED** | N/A |
| G6 M1_BETA_LOCKOUT | 31 | +0 | 74.2% | -0.6% | [-20.6%, +24.4%] | **REJECTED** | N/A (human decision) |
| G7 SUM_POSTED [0.70,0.85] | 382 | +0 | — | +11.5%† | [-11.4%, +38.9%] | AMBIGUOUS (extended) | N/A — over thresh, straddles 0 |

† = UPPER BOUND. G3 WATCH_ITEM (winner's curse CONFIRMED, n=75, filled WR 17.3% vs sim) means all sim ROIs for G1/G7 are upper bounds. Do not use them as re-enable evidence.

**Per-asset cells (G8, informational):**

| Asset | n graded | WR | BE | p≥0.995 sub-n | Status |
|---|---|---|---|---|---|
| BTC | 95 | 96.8% CI[91.1%,98.9%] | 96.6% | 56 (−$0.51) | COLLECTING (closest to n=100) |
| ETH | 12 | 100% | 96.8% | 4 | COLLECTING |
| XRP | 8 | 100% | 96.6% | 2 | COLLECTING |
| SOL | 4 | 100% | 95.6% | 1 | COLLECTING |
| DOGE | 3 | 100% | 95.0% | 1 | COLLECTING |

BTC sub-slice CI at p≥0.995: [87.9%, 99.0%] vs BE 96.5% — CI straddles BE even in the leading cell.

---

## State Transitions Since Prior Run (2026-07-20T09:09Z)

**UPDOWN_CROSSING (G8)**: n_post_cut **2 → 38** (+36 events). Multi-asset shadow (eth/sol/xrp/doge, enabled Jul-19 19:05Z) now fully scoring via shadow_grade.py --refetch (Jul-20 21:59Z). 37W/1L. Point WR (97.4%) recovered above BE (97.0%) — it had briefly dipped below at n=25 (11:30Z Jul-20, WR=96.0% < BE=96.7%) then rebounded. CI-lo 86.5% remains far below BE 97.0%. **Neither PASS nor KILL triggered.** Kill rule armed.

No other status changes. Seven of eight active gates are frozen (band dark, no new resolutions).

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED this run. No flag or parameter changes recommended.**

The only gate approaching a decision is G8 UPDOWN_CROSSING. ETA to n=100: ~Jul-23 at current rate (26.4 events/day, multi-asset). At n=100, two outcomes are possible:
- CI-lo > BE (0.9701) → READY (triggers owner-floor re-waiver request + min-size restart vote)
- Point WR < BE at n=100 → KILL (recommend class CLOSED, sniper remains cut)

The gap between CI-lo (86.5%) and BE (97.0%) is 10.5 percentage points. At n=100 with 1 loss in 38 so far, even 0 additional losses would yield CI-lo ≈ 93.3% — still below BE. To clear CI-lo > BE at n=100, the rate would need to be near-perfect. **At current 37W/1L trajectory, the likely outcome at n=100 is continued COLLECTING or KILL, not PASS.** Human should be alert to that.

---

## Standing Structural Blockers

1. **UPDOWN_STOP**: sniper CUT Jul-19 11:26Z (PF rail, candidate tape PF=0.79 over 27 settles). Zero fires since. Shadow accruing free.
2. **BAND_LIVE=False**: wind-down since Jul-06 22:08Z. Day 15. Zero band resolutions possible. G1/G7/G2 n counts frozen.
3. **Capital $21.50 < ruin floor $89.16 (24.1%)**: all band paths and NEG_RISK/RECYCLE mechanically blocked. Engine running in shadow/shadow-only mode.
4. **Winner's curse G3**: filled WR 17.3% vs sim (gap CI entirely negative, n=75). Blocks all G1/G7 sim-CI arguments. Exec Auditor backlog 4 unclassified fills still outstanding (Jul-16/18/19); n conservatively held at 75.
5. **G5 THERMO / G6 M1_LOCKOUT**: both REJECTED; shadow files growing inertly; no reconsideration without explicit human directive.

---

## Alert

**G8 n jumped 2→38 in 24h (+36):** Multi-asset shadow now properly accruing after Jul-19 19:05Z enable. Rate compressed ETA from 5-22d estimate to ~2.3d. Tonight's EVOLVE run will include next --refetch grade. Watch for the BTC sub-slice to cross n=100 independently (~5 events remaining at ~2-3 BTC events/day). Even then, per-asset CI gate has its own BE and must clear independently before any per-asset promotion vote.

**Intraday note**: n=38 is the last Gamma-truth grade (Jul-20 21:59Z). Overnight Jul-20→Jul-21 shadow fires are accumulating but not yet resolved in the count. Expect n_post_cut ~50-60 after tonight's EVOLVE --refetch.
