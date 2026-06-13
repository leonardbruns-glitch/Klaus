# Klaus Gate-Keeper Report — 2026-06-13

| field | value |
|---|---|
| snapshot_ts (UTC) | 2026-06-13T09:03:51Z |
| snapshot_age | 0.44 hours |
| system_status | klaus systemd: active |
| bankroll | $244.49 |
| total_trades | 7342 (7342 WEATHER/weather, updown, misc) |
| prior_state | {} (first run — all +24h = n) |

**ABORT CHECK: PASS** — age 0.44h < 6h, system active.

**RESOLUTION JOIN: FAILED** — Gamma API returns 403 Forbidden from VPS (Cloudflare block). Zero resolved legs across all gates requiring outcome data. All ROI/WR/CI metrics are N/A. Status forced to COLLECTING for all ROI-dependent gates regardless of n.

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES per slice | 1539 legs | +1539 | N/A | N/A | N/A | COLLECTING | — |
| G2 BAND_NO + PAIR_FAV | 14 (post-fix) | +14 | N/A | N/A | N/A | COLLECTING | ~12d |
| G3 FILLED vs FIRED | 116 fills | +116 | N/A | N/A | N/A | COLLECTING | (count ok, ROI pending) |
| G4 BASKET EXIT | 38 basket-days | +38 | N/A | N/A | N/A | COLLECTING | ~3d to n=100 |
| G5 THERMO MAKER-NO | 13 candidates | +13 | N/A | N/A | N/A | COLLECTING | ~1d to n=20 |
| G6 M1-BETA LOCKOUT | 1 trade | +1 | N/A | N/A | N/A | COLLECTING | indeterminate |
| G7 SUM-POSTED 0.70-0.85 | 284 legs | +284 | N/A | N/A | N/A | COLLECTING | (count ok, ROI pending) |

---

## Gate Detail

### Gate 1 — BAND YES per slice (threshold n=100 per slice)
- **Source:** band_struct_lite.jsonl (all days 2026-06-09 to 2026-06-13)
- **Total fires:** 2074 raw → 1539 deduped YES legs (first-fire per cid×days_out×YES)
- **Unique markets:** 986 condition IDs
- **Top slices by n (deduped first-fire):**
  | Slice (days_out × offset × price_band) | n |
  |---|---|
  | d=2, off=1, ask∈[0.10,0.20) | 145 |
  | d=1, off=2, ask∈[0.00,0.10) | 113 |
  | d=2, off=2, ask∈[0.10,0.20) | 108 |
  | d=1, off=1, ask∈[0.20,0.30) | 107 |
  | d=2, off=1, ask∈[0.20,0.30) | 98 |
  | d=2, off=0, ask∈[0.20,0.30) | 96 |
  | d=1, off=0, ask∈[0.30,0.40) | 82 |
  | d=1, off=1, ask∈[0.10,0.20) | 82 |
- **Resolution:** 0 resolved (Gamma API 403 from VPS)
- **Status:** COLLECTING — top 4 slices exceed n=100 by count, but ROI cannot be computed without resolution truth. The gate CI condition (CI_lower > 0) cannot be evaluated.
- **ETA:** Blocked on resolution API access, not data volume.

### Gate 2 — BAND NO + PAIR_FAV (threshold n=100, counting from 2026-06-12)
- **Source:** band_struct_lite.jsonl, reason=fire_no, from 2026-06-12 (NO-starvation fix date)
- **Pre-fix legs (excluded):** 71 (2026-06-11 era, starvation bug active)
- **Post-fix legs:** 14 (9 on 2026-06-12, 5 on 2026-06-13)
- **Daily rate:** ~7/day post-fix
- **Resolution:** 0 (Gamma API 403)
- **Status:** COLLECTING — n=14, threshold=100, ETA ~12 days at current rate
- **Note:** NO-starvation fix deployed 2026-06-12 13:05 UTC. Valid accumulation started that date.

### Gate 3 — FILLED vs FIRED divergence (threshold n=40 filled)
- **Source:** maker_fills_recent.log (MAKER-FILL entries)
- **Total MAKER-FILL lines:** 219 (129 registered, 90 share additions)
- **Unique filled tokens:** 116 across 39 cities (YES and NO sides)
- **Threshold check:** n=116 > 40 ✓ (count gate passed)
- **Resolution:** 0 (Gamma API 403) — cannot compute fill ROI vs fire ROI
- **Winner's-curse gap:** Cannot compute without resolution; watch item open
- **Status:** COLLECTING — count threshold exceeded but ROI join blocked by Gamma access
- **Filled-by-side:** ~118 registered fill events; YES-heavy (Jeddah 8, Beijing 7, Moscow 7 top cities)

### Gate 4 — BASKET EXIT (threshold n=100 basket-days)
- **Source:** basket_exit_shadow.jsonl (started 2026-06-12 per state_log 06:14)
- **Total records:** 9,961 snapshots across 38 unique city-date baskets
- **Resolved basket-days** (t_close < snapshot_ts): **5**
  | City | all_green | cash_value | max_hold | cost |
  |---|---|---|---|---|
  | chongqing 2026-06-12 | False | 0.013 | 13.995 | 5.217 |
  | london 2026-06-12 | False | 5.340 | 5.500 | 5.390 |
  | munich 2026-06-12 | False | 10.745 | 10.750 | 8.400 |
  | madrid 2026-06-12 | False | 0.004 | 8.187 | 4.503 |
  | karachi 2026-06-12 | False | 0.003 | 6.844 | 0.684 |
- **all_green resolved:** 0 (no basket has all legs currently liquid + profitable at snapshot)
- **Trend note:** State_log 2026-06-12 cited n=8 trend (ex-post, 5/6 favored cashing). Current live logger shows 0 all_green at resolution — likely because bids collapse to near-zero by t_close. This is consistent with state_log 2026-06-12 06:55 finding (lockout-salvage falsified: bid books empty at resolution time).
- **Daily rate:** ~25 basket-days/day (38 in ~1.5 days). ETA to n=100 total: ~2.5 days.
- **Status:** COLLECTING — n=38, threshold=100

### Gate 5 — THERMO upper-tail maker-NO (threshold n=20 RESOLVED)
- **Source:** today_thermo_maker.jsonl + 2026-06-08/thermo_maker.jsonl
- **Total records:** 9,271 (all record_type=thermo_maker_candidate)
- **Unique tokens:** 75 (by token_id)
  - end_date=2026-06-08: 3 tokens
  - end_date=2026-06-12: 10 tokens (potentially resolved)
  - end_date=2026-06-13: 62 tokens (today, not yet resolved)
- **Potentially resolved (end_date < 2026-06-13):** 13 tokens
- **With no_ask field populated:** 3,081 records; mean no_ask=0.985 (upper tail confirmed)
- **Resolution:** 0 (Gamma API 403) — cannot determine winners
- **Status:** COLLECTING — 13 candidates near threshold of 20; blocked on resolution join
- **ETA:** ~1-2 days if resolution access restored or tomorrow's batch adds >7 more candidates

### Gate 6 — M1-beta lockout slices (threshold n=100)
- **Source:** metar_lockout.jsonl (all 0 rows across all dates) + trades.jsonl WEATHER_M1_PROBE
- **metar_lockout rows:** 0 across 2026-06-08 to 2026-06-13
- **WEATHER_M1_PROBE trades:** 1 (Moscow 2026-05-26, BOND_ABORT_CASCADE exit, -$1.65)
- **Thin-margin [0.2,0.5)C slice fires:** 0 logged
- **Status:** COLLECTING — n=1 effective observation; logger appears inactive (metar_lockout not firing)
- **ETA:** Indeterminate; logger needs investigation (0 rows suggests logger disabled or slice condition never met)
- **Note:** Rule: n≥100 AND WR≥95% AND +EV = keep; else recommend REVERT to 0.5C floors. With n=1 and logger silent, cannot evaluate. Recommend checking METAR_LOCKOUT_ENABLED flag.

### Gate 7 — SUM-POSTED 0.70-0.85 slice (threshold n=100)
- **Source:** band_struct_lite.jsonl, YES legs where sum_ask ∈ [0.70, 0.85]
- **Deduped legs in slice:** 284 (out of 1539 total YES legs)
- **Daily accumulation:** by date: {2026-06-09: 8, 2026-06-11: 50, 2026-06-12: 126, 2026-06-13: 100}
- **Threshold check:** n=284 > 100 ✓ (count gate passed)
- **Resolution:** 0 (Gamma API 403) — cannot compute ROI
- **Status:** COLLECTING — count threshold exceeded; blocked on resolution join
- **ETA:** Blocked on resolution API access, not data volume.

---

## State Transitions vs Prior State

Prior state was `{}` (first run). All gates initialized fresh.

**No transitions** — all gates move from (nonexistent) to COLLECTING.

---

## PROPOSED ACTIONS (human review)

**No gates reached READY or REJECTED this run.**

All 7 gates are in COLLECTING status. The blocking issue is uniform: **Gamma API returns 403 Forbidden from the VPS** (Cloudflare WAF block on this IP/ASN), preventing resolution joins for all gates.

**Recommended action (not implementing):**
1. **Gamma API resolution access**: Run `band_resolution_join.py` from a non-blocked IP (e.g., QuantVPS Dublin or via curl_cffi impersonation) to get resolution truth. Alternatively, fetch resolutions via the Polygon on-chain outcome prices.
2. **Gate 1/7**: Both have n well above threshold. Once resolution is available, these gates could flip READY or REJECTED quickly.
3. **Gate 6 (M1-beta lockout)**: Investigate why metar_lockout.jsonl produces 0 rows. If the logger is disabled, Gate 6 cannot accumulate. Check `METAR_LOCKOUT_SHADOW_ENABLED` flag or equivalent.
4. **Gate 4 (basket exit)**: Logger only 1.5 days old; ETA ~3 days to n=100 total, then resolution needed. No action warranted yet.
5. **Gate 5 (thermo)**: 13 potentially-resolved candidates, threshold=20. With resolution access, this gate could report in 1-2 days.

**Capital safety**: No gate transitions mean no parameter changes recommended. Current BAND_LIVE=True, STWA_REGULAR_YES_ENABLED=False, STWA_REGULAR_NO_ENABLED=False remain unchanged pending gate decisions.

---

*Generated by Klaus Gate-Keeper Validator | 2026-06-13*
