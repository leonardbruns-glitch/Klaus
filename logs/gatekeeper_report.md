# Gate-Keeper Report — 2026-06-24

**Run:** 2026-06-24T12:15:09Z snapshot | **System:** `klaus systemd: active` (commit ec5c218a7)  
**Capital:** $224.59 | **Branch:** `claude/find-lag-parameter-rFQ0N`

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|------|---|------|----|-----|------|--------|-----|
| 1 BAND_YES per slice | 5,905 | +229 | — | — | null | **COLLECTING** | Gamma 403 — VPS only |
| 2 BAND_NO + PAIR_FAV | 213 | +36 | — | — | null | **COLLECTING** | Gamma 403 — VPS only |
| 3 FILLED_VS_FIRED | 97 (7d) | +33 | — | — | null | **COLLECTING** | Gamma 403 — VPS only |
| 4 BASKET_EXIT | 33 | — | 100% | +145.5% | — | **VOID** | Retired Jun22 (4 fatal flaws) |
| 5 THERMO_MAKER_NO | 3 | 0 | 33.3% | −66.0% | [−132.6%, +0.7%] | **COLLECTING** | ∞ — engine paused |
| 6 M1_BETA_LOCKOUT | 31 | 0 | 74.2% | −0.6% | [−20.6%, +24.4%] | **COLLECTING** | ∞ — engine stalled |
| 7 SUM_POSTED [0.70–0.85] | 2,954 | +130 | — | — | null | **COLLECTING** | Gamma 403 — VPS only |

*WR/ROI/CI = null for gates 1/2/3/7: resolution join requires Gamma API, which returns 403 from container. VPS must run `analysis/weather/band_resolution_join.py`.*

---

## State Transitions vs Prior Run (2026-06-23T12:29:31Z)

No status transitions since prior run. All gates remain COLLECTING.

**Significant deltas:**

- **Gate 1 (BAND_YES):** +229 new (cid, days_out) legs. Rate: ~225 YES legs/day (Jun24 pace; elevated vs ~104/day post-restart per prior note — likely effect of BAND_PX_CEIL raise 0.30→0.45 deployed Jun24 08:03).
- **Gate 2 (BAND_NO):** +36 new unique cids. Rate: ~30 NO legs/day (down from ~44/day rate cited Jun23; consistent with favNO cap dynamics and NO daily cap fix Jun23 18:28).
- **Gate 3 (FILLED_VS_FIRED):** −5 net (102→97). All new fills since prior (n=33) are **NO only** (side: NO=49, YES=0 since Jun23 12:29). YES maker fills at zero since NO-only mode (`no_reserve=1.00`). 7d rolling window; log starts Jun21, no Jun17-20 data visible.
- **Gate 5 (THERMO_MAKER_NO):** n=3, no change. Engine **PAUSED** Jun23 18:40 UTC (state_log: "pause thermo, free ~$25 cash for band-NO compounding"). 5 resting THERMO buys cancelled; 1 THERMO SELL_EXIT @0.99 still active on CLOB. CI upper bound = +0.7% barely straddles zero — one more loss flips REJECTED.
- **Gate 6 (M1_BETA_LOCKOUT):** n=31, no change. Engine stalled. 1 WEATHER_M1_PROBE SELL_EXIT still resting on CLOB (@0.99, 20 shares). No new M1_PROBE fires; no WEATHER_M1_PROBE signal source in recent trades.
- **Gate 7 (SUM_POSTED):** +130 new legs. Jun24 fraction of total YES fires in [0.70–0.85] sum_posted window: 130/225 = 57.8%.

**New shadow logger active (unregistered gate):**  
`YES_CAPTURE_SHADOW` wired Jun23 19:45 (state_log). Accumulating d+2 YES would-post legs at ask 0.10–0.45 (now includes 0.25–0.45 zone per Jun24 08:03 price ceiling raise). Current: **330 unique (cid, days_out, off)** first-fires since wire-up; 18.8% (62/330) in 0.25–0.45 zone. Analyzer: `analysis/weather/band_yes_capture_join.py`. Target: n≥100 then run join. State_log target: "run in ~3-4d" from Jun23 → earliest join window **Jun26–Jun27**.

---

## Resolution Blocker (Critical Path)

**Gamma API returns 403 from this container.** All four n≥threshold gates (1/2/3/7) are stuck at COLLECTING despite having well over 100× the required resolution count. The `band_resolution_join.py` script exists in the repo and was validated on its layout (1,489 deduped legs from 6-day window confirmed). The script runs cleanly to the Gamma fetch step and then hangs/times out.

**Root cause (prior research):** Container ASN is blocked by Cloudflare WAF. Gamma API accessible from QuantVPS Dublin (the live VPS). No workaround from container.

**Required action:** VPS operator runs on the live VPS:
```bash
cd /root/Klaus
python3 analysis/weather/band_resolution_join.py
# Then: python3 analysis/weather/band_yes_capture_join.py  (when n>=100, ~Jun26-27)
```

---

## PROPOSED ACTIONS (human review)

**No gates newly hit READY or REJECTED this run.** No flag changes recommended.

### Informational items for human review:

**1. Thermo paused → gate collection frozen**  
Gate 5 (THERMO_MAKER_NO) has n=3 resolved, WR=33.3%, ROI=−66%, CI upper=+0.7%. Engine paused Jun23 18:40 to free $25 cash for band-NO compounding. Gate will never reach kill threshold (n=20) while engine is off. Decision needed: (a) accept that THERMO is permanently shelved and mark gate VOID, or (b) schedule a validation period at reduced stake to collect the remaining 17 resolutions. Currently neither — gate is stuck in COLLECTING with zero accumulation rate.

**2. M1_BETA_LOCKOUT stalled → standing rule exposure**  
Gate 6 (M1_BETA_LOCKOUT) has n=31/100, standing rule from Jun09: *"at n≥100, WR≥95% AND +EV = keep; else REVERT to 0.5°C floors."* Engine stalled; n will never reach 100. 1 M1_PROBE SELL_EXIT still resting on CLOB. The thin-margin [0.2,0.5)C slice is currently live with n=31 unresolved basis. Unverifiable provenance flag from prior state stands. Decision: REVERT to 0.5°C floors now (the standing rule says revert if n≥100 not met AND WR<95% — n never reaches 100 at 0 rate, so revert is the conservative default).

**3. All CI-gated scale-ups blocked by Gamma 403**  
Gates 1, 2, 3, 7 are all above n-threshold and accumulating. None can advance to READY/REJECTED without VPS running the resolution join. Every day of delay is capital deployed on unvalidated slices (Gate 2 BAND_NO is live at $5/fire, ~30 fires/day). Priority: **VPS operator must run `band_resolution_join.py` at earliest opportunity.**

**4. YES_CAPTURE_SHADOW n=330 → approaching join window**  
New d+2 YES validator has 330 first-fire observations (62 in the new 0.25–0.45 zone). ETA for `band_yes_capture_join.py`: Jun26–27 at ~285 legs/day pace. Suggest scheduling a gatekeeper run at that time. Not a registered gate yet — no action today.

---

## Notes

- Resolution join dedup confirmed: `band_resolution_join.py` ran to completion (with Gamma timeout) → 1,603 raw → 1,489 deduped legs (130 NO), 1,162 unique markets in 6-day window. First-fire dedup is functioning correctly.
- Gate 3 side shift: YES fills = 0 since Jun23 12:29 (NO-only mode confirmed by fill tape). Prior 60% YES → now 17% YES total in 7d window. Gate compares filled-leg ROI vs all-fires ROI; currently not computable without Gamma. This shift may introduce selection bias once the join runs: filled legs will be predominantly NO fills, fired legs include both sides.
- BAND_PX_CEIL raised Jun24 08:03 (d+1/d+2: 0.30→0.45, d+0 stays 0.25). YES fire rate elevated accordingly. Co-fill rate + markout validation target: "next 2-3d before scaling" per state_log.

