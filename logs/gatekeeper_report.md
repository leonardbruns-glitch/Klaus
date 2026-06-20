# Gate-Keeper Report — 2026-06-20

**Snapshot**: 2026-06-20T12:16:21Z (< 6h old ✓) | **System**: active ✓ | **Bankroll**: $213.11

---

## Gate Ledger

| Gate | n | +since prior | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| 1. BAND_YES | 4914 | +271 | — | — | [Gamma 403] | COLLECTING | n>>100; CI blocked |
| 2. BAND_NO_PAIR_FAV | 105 | +15 | — | — | [Gamma 403] | **COLLECTING ★n≥100** | CI blocked; VPS join needed |
| 3. FILLED_VS_FIRED | 100† | — | — | — | [CID join blocked] | COLLECTING | n>>40; join blocked |
| 4. BASKET_EXIT | ≈64‡ | +16 (est.) | — | — | [Gamma 403] | COLLECTING | ≈1.9d if archive fixed |
| 5. THERMO_MAKER_NO | 3 | +0 | 33.3% | −64.7% | [−130%, +0.7%] | COLLECTING | **STALLED** (0 fills Jun12–Jun20) |
| 6. M1_BETA_LOCKOUT | 31§ | +0 | 74.2% | −0.6% | [−20.6%, +24.4%] | COLLECTING | **STALLED** (0 thin-margin fires) |
| 7. SUM_POSTED_0.70_0.85 | 2331 | +157 | — | — | [Gamma 403] | COLLECTING | n>>100; CI blocked |

†Gate 3: 7d rolling window; Jun17 fills (n=69) aged out. Current window: Jun18=53, Jun19=35, Jun20=12 (to 09:01 UTC) = 100 total. YES=71 (71%), NO=29 (29%).

‡Gate 4: Prior confirmed 48; prior run's 16 pending Jun19 baskets (t_close Jun19–Jun20) now resolved but absent from archive — structural blocker. Jun20 rolling file has 1,665 all_green events, all with t_close ≥ 15:00 UTC today (future).

§Gate 6: n=31 carries provenance flag from prior runs; only 1 M1 trade verifiable from trades.jsonl (Moscow May-26, net_pnl=−$1.65, WEATHER/Moscow/M1_BETA_PROBE).

**No READY. No REJECTED. No status transitions from prior run.**

---

## Gate Detail

### Gate 1 — BAND_YES (scale-up gate)
- **n**: 4914 (prior 4643, +271)
- **Counting method**: unique (cid, days_out) from `quotes[]` inside `reason=fire` events in per-day band_struct_lite.jsonl — confirmed matching prior cross-checks (Jun15=765, Jun16=800, Jun17=679, Jun18=629 all verified against prior state exactly)
- **Delta breakdown**: Jun19 rest-of-day (185→230 = +45 legs) + Jun20 to 12:11 UTC (+226 legs) = +271
- **Jun20 rate**: 52 unique bands × avg 4.35 legs/band = 226 legs in ~12h ≈ 452 legs/full day
- **Status**: n=4914 >> threshold 100 per slice; **CI blocked — Gamma API returns 403 from container**. Band resolution join requires VPS-side `band_resolution_join.py` run on post-boundary data (boundary = Jun19 00:30 UTC, the 7th config change of Jun18 churn). Prior data is contaminated by 4 arch changes Jun17 + 7 on Jun18. VPS must target post-boundary legs only.
- **Clean-window data available**: Jun19 00:30 UTC → Jun20 12:11 UTC ≈ 271 post-boundary legs. Sufficient for per-slice CI on main slices once resolved.

### Gate 2 — BAND_NO + PAIR_FAV ★ THRESHOLD CROSSED
- **n**: 105 (prior 90, +15) — **crossed n=100 since last run**
- **Counting method**: unique cid from `reason=fire_no`, `reason=pair_fav`, `reason=pair_samebucket` events in per-day band_struct_lite.jsonl
- **Delta breakdown**: Jun19 rest-of-day (7→15 fire_no = +8) + Jun20 (+7 fire_no) = +15
- **By type** (Jun15-Jun20): fire_no=61, pair_fav=17, pair_samebucket=6 = 84 observed in 6d window; legacy Jun12-Jun14 carry = 21 (from prior accumulation); total n=105
- **Rate**: Jun18=20/day (peak), Jun19=15/day, Jun20=7 in 12h ≈ 14/day
- **Status**: COLLECTING. n≥100 threshold met, but **CI still blocked by Gamma 403**. Cannot be evaluated without resolution truth. VPS must run resolution join immediately. Once n≥100 resolved legs available, CI95 will determine READY/REJECTED/AMBIGUOUS.

### Gate 3 — FILLED vs FIRED (winner's-curse watch)
- **n (current window)**: 100 (7d rolling; Jun17 fills aged out)
- **Window**: Jun18=53, Jun19=35, Jun20=12 (to 09:01 UTC)
- **Fill balance**: YES=71 (71%), NO=29 (29%). NO fill rate improved from 13.2% at prior snapshot to 29% — consistent with favNO TOP priority activated Jun19 00:30 UTC.
- **Prior cumulative n=291 is no longer usable**: Jun16 (77) and Jun17 (69) fills aged out of the rolling log. The current observable window for resolution join = 100 fills.
- **Status**: COLLECTING. n=100 exceeds n=40 threshold for filled-leg resolution join. **CID join is blocked from container**. VPS must execute the filled-vs-fired divergence analysis on this window before Jun18 fills also age out (~5 days from now).
- **Watch item**: Paris NO +5.5 sh @ 0.98 (Jun18 14:18:40, cond=0x6f518f8f). Price 0.98 > BAND_NO_MAX=0.85 — outside band NO range. Likely thermo-sourced (see Gate 5). VPS to verify via token_id join to thermo_maker candidates.

### Gate 4 — BASKET EXIT (cash green baskets)
- **n**: ≈64 estimated (prior confirmed 48 + ~16 Jun19 baskets inferred from prior pending count)
- **Jun15** per-day archive: 19 resolved basket-city-days (consistent with prior)
- **Jun16–Jun18** per-day archives: absent from data-mirror (structural gap — no per-day basket JSONL created)
- **Jun19 baskets**: Prior run identified 16 pending (t_close Jun19–Jun20); these elapsed but data rolled off the root file when Jun20 started. Unverifiable; counted as +16 estimated.
- **Jun20 root file**: 1,665 all_green events; ALL t_close ∈ [15:00 UTC Jun20, 07:00 UTC Jun21] — none resolved yet.
- **Status**: COLLECTING. **Structural blocker persists**: per-day basket archives absent for Jun16+. ROI computation impossible. At ~19 resolved/day, n≥100 would be ~Jun23 — but blocked on data infrastructure, not count rate.

### Gate 5 — THERMO MAKER NO (pre-registered kill gate: n=20)
- **n resolved**: 3 (prior 3, +0 confirmed)
- **WR**: 1/3 = 33.3% | **ROI**: −64.7% | **CI95**: [−130%, +0.7%] (barely straddles 0 — upper bound +0.7%)
- **Prior 3 resolved**: +$0.11 @ 0.98, −$5.67 @ 0.81, −$5.39 @ 0.98
- **STALLED 8+ days**: thermo_maker.jsonl has 15,199 candidates today (scanning active; 7,734 with no_ask set) but zero fire records in any file. No new fills in maker_fills_recent.log (Jun18–Jun20 window) attributable to thermo.
- **Possible 4th fill (unconfirmed)**: Paris NO +5.5 sh @ 0.98 (Jun18 14:18:40, cond=0x6f518f8f). BAND_NO_MAX=0.85, so this price is outside the band NO range. Paris thermo candidate today: "39°C or higher" with no_ask=0.999 (extreme heat market — consistent pattern). If confirmed thermo AND resolves adversely: n=4, and with 3 losses out of 4 the CI flips clearly negative → pre-emptive REJECTED territory approaching kill gate.
- **Direction**: CI upper = +0.7% — one additional adverse fill at any price pushes CI fully negative. The stall at n=3 with near-negative CI is a holding pattern: status is COLLECTING by the letter of the rules (n=3 < threshold 20), but the data that exists is directionally negative.

### Gate 6 — M1-BETA LOCKOUT (thin-margin [0.2,0.5)C slice)
- **n**: 31§ (provenance flagged) / 1 verified
- **WR**: 74.2% (flagged) | **ROI**: −0.6% | **CI95**: [−20.6%, +24.4%] (straddles 0)
- **New probe fire (not qualifying)**: Moscow Jun20, phase=result, L3, depth_c=0.5°C, bucket [18.5,19.5)°C, running_max_c=20.0°C, fill_status=FILLED @ 0.95, 21.0 sh. depth_c=0.5°C is at the boundary of [0.2,0.5)C window — does NOT qualify (gate monitors depth_c strictly in [0.2,0.5)). This fire does NOT increment Gate 6 n.
- **metar_lockout.jsonl**: 0 lines (empty — schema v2 records candidates only; no thin-margin fires logged)
- **Verified trade count**: Only Moscow May-26 (net_pnl=−$1.65, WEATHER/Moscow/M1_BETA_PROBE) in trades.jsonl. 1 data point.
- **STALLED 10+ days**: No thin-margin [0.2,0.5)C slice fires detected. Possible explanations: (a) thin-margin lockout conditions rarely met in current weather regime; (b) schema v2 doesn't log fires; (c) the firing path is blocked upstream.
- **Standing rule (Jun09)**: Once n≥100 with WR≥95% AND +EV → keep; else REVERT to 0.5°C floors.

### Gate 7 — SUM_POSTED 0.70–0.85 (V3 gate extension)
- **n**: 2331 (prior 2174, +157)
- **Counting method**: unique (cid, days_out) from `quotes[]` inside `reason=fire` events where band `sum_posted` ∈ [0.70, 0.85], first-fire dedup per (cid, days_out)
- **Delta breakdown**: Jun19 rest-of-day (146→147 = +1) + Jun20 to 12:11 UTC (+156) = +157
- **Jun20**: 33 of 52 fired bands (63%) had sum_posted in [0.70,0.85] — these generated 156 of 226 legs
- **Status**: n=2331 >> threshold 100; **CI blocked by Gamma 403** (same as Gate 1). VPS resolution join required. Same clean-window boundary (Jun19 00:30 UTC+).

---

## State Transitions vs Prior (2026-06-19T09:00:00Z)

| Gate | Prior Status | Current Status | Change |
|---|---|---|---|
| 1. BAND_YES | COLLECTING | COLLECTING | n 4643→4914 (+271) |
| 2. BAND_NO_PAIR_FAV | COLLECTING | COLLECTING | n 90→105 (+15) **★ THRESHOLD CROSSED** |
| 3. FILLED_VS_FIRED | COLLECTING | COLLECTING | Jun17 aged out; current window n=100 |
| 4. BASKET_EXIT | COLLECTING | COLLECTING | n 48→≈64 est. (+16 Jun19 resolved, unverifiable) |
| 5. THERMO_MAKER_NO | COLLECTING | COLLECTING | STALLED +8d; CI barely positive (upper +0.7%) |
| 6. M1_BETA_LOCKOUT | COLLECTING | COLLECTING | New L3 fire non-qualifying; STALLED unchanged |
| 7. SUM_POSTED_0.70_0.85 | COLLECTING | COLLECTING | n 2174→2331 (+157) |

**No gates newly READY. No gates newly REJECTED.**

---

## PROPOSED ACTIONS (human review)

No gates have crossed the READY or REJECTED verdict this run. The binding blocker for 6 of 7 gates is the **Gamma 403 / resolution-join infrastructure gap from the container**. Actions proposed for human operator:

**[P1 — URGENT] Gate 2 VPS resolution join**: Gate 2 (BAND_NO_PAIR_FAV) crossed n=100 this run. This is the critical validation gate before any NO-side scaling. VPS must run the resolution join on fire_no/pair_fav/pair_samebucket events from the post-boundary window (Jun19 00:30 UTC onward). Without this join, NO-side cannot be declared READY or REJECTED. The rate is ~14/day — every day of delay adds noise to the clean window.

**[P2 — URGENT] Gate 1 & 7 VPS resolution join**: Gates 1 and 7 have been n>>100 for days; neither has a verdict. VPS band_resolution_join.py must run on post-boundary data (Jun19 00:30 UTC+) only. Lite files preserve first-fire dedup + all posts — lay them into logs/shadow/hot/$D/band_struct.jsonl layout before running.

**[P3 — INFRA] Gate 4 basket archive fix**: Per-day basket_exit_shadow.jsonl not being archived for Jun16+. 4 days of data already permanently lost. Fix the VPS archival cronjob or Gate 4 permanently stalls below n=100. If not fixable, consider alternative: snapshot current root file daily to per-day location before midnight UTC.

**[P4 — VERIFY] Gate 5 Paris NO fill**: Paris NO +5.5 sh @ 0.98 (Jun18 14:18, cond=0x6f518f8f) is priced outside BAND_NO_MAX=0.85 — likely thermo. VPS: join token_id `151302198882` (truncated) to thermo_maker candidates, retrieve resolution, compute PnL. If adverse → Gate 5 CI flips negative, approaching pre-REJECTED territory at n=4.

**[P5 — DATA] Gate 6 provenance reset**: VPS operator verify Gate 6 n=31 basis. If schema v1 metar_lockout records cannot be located, reset n=1. Flag to human for decision.

---

## Structural Blockers (persistent)

1. **Gamma API 403 from container** (3+ runs): All band gates require CLOB/Gamma winner-flag resolution. VPS-side resolution join is the only path to any READY/REJECTED verdict.
2. **Per-day basket archive gap** (Jun16+): Gate 4 data lost on daily rollover. Gate permanently stalled.
3. **Thermo zero-fire gap** (8+ days): Gate 5 has 7,734 actionable candidates but zero fires. Firing threshold may need inspection.

---

*Report generated: 2026-06-20T12:27:00Z | Counting verified: Jun15=765, Jun16=800, Jun17=679, Jun18=629 leg counts match prior state exactly.*
