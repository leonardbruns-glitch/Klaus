# Klaus Gate-Keeper Report — 2026-07-23T09:00Z

**Run basis:** data-mirror snapshot 2026-07-23T09:00:25Z (age: ~0 min) | Prior state: 2026-07-22T09:02Z
**System status:** `klaus systemd: active` | Open positions: 0 | Bankroll: $21.495 | Band dark: day 17 | UPDOWN_STOP: active since Jul-19 11:26Z
**Network status:** ⚠ git fetch timed out again — `shadow_grade.py --refetch` and `band_resolution_join.py` could NOT run this session. G8 n sourced from EVOLVE commits (Jul-22 daily + evening). G1/G7 resolution n frozen. Shadow fires from band_struct_lite parsed via GitHub MCP fallback.

---

## GATE LEDGER

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA to threshold |
|---|---|---|---|---|---|---|---|
| **G1** BAND_YES (all slices) | 934 | 0 | 15.3% | +4.0%† | [-10.9, +21.1] | AMBIGUOUS | Indet. — band dark, cap $21.50 |
| **G2a** band_no_d1 (shadow) | 115 | 0 | 68.7% | +1.3% | [-11.9, +12.7] | AMBIGUOUS | N/A (BAND_NO=False) |
| **G2b** pair_fav_YES | 9 | 0 | N/A | N/A | [—, —] | COLLECTING | Indet. — band dark |
| **G2c** pair_fav_NO | 9 | 0 | N/A | N/A | [—, —] | COLLECTING | Indet. — band dark |
| **G3** FILLED_VS_FIRED | 75 | 0 | 17.3% | -75.8% | [-75.0, -34.2] | WATCH_ITEM ⚠ | N/A |
| **G4** BASKET_EXIT | VOID | — | — | — | — | **PERMANENTLY RETIRED** | — |
| **G5** THERMO_MAKER_NO | 125 | 0 | N/A | 0.0% | [-9.0, +2.0] | **REJECTED** | — |
| **G6** M1_BETA_LOCKOUT | 31 | 0 | 74.2% | -0.6% | [-20.6, +24.4] | **REJECTED** | — |
| **G7** SUM_POSTED [0.70,0.85] | 382 | 0 | N/A | +11.5%† | [-11.4, +38.9] | AMBIGUOUS | Indet. — band dark, n frozen |
| **G8** UPDOWN_CROSSING (post-cut) | 72* | +15 | 97.2% | sim only | [90.4%, 99.2%] | COLLECTING | n=100: ~Jul-25‡ / n=245: ~Aug-3‡ |

*G8: n=72 confirmed by EVOLVE commits (Jul-22 daily n=65, Jul-22 evening n=72). `shadow_grade.py --refetch` blocked; using EVOLVE journal as source.
†ROI for G1 and G7 are UPPER BOUND (G3 winner's curse, n=75, CI entirely negative). No band re-enable may cite these as positive evidence.
‡ETA uses ~15/day rate (Jul-22 24h window); rate is uncertain — see FLAG-2 for range.

---

## STATE TRANSITIONS vs PRIOR (2026-07-22T09:02Z)

### G8: n=57→72 (+15), SECOND LOSS OCCURRED — status COLLECTING (unchanged)

**This is the only substantive change this run.**

| Metric | Prior (Jul-22) | Current (Jul-23) | Delta |
|---|---|---|---|
| n_post_cut | 57 | 72 | +15 |
| W/L | 56W/1L | 70W/2L | +14W / +1L |
| WR | 98.25% | 97.22% | −1.03 pp |
| CI-lo (Wilson 95%) | 90.7% | **90.4%** | −0.3 pp |
| CI-hi | 99.5% | 99.2% | −0.3 pp |
| Gap to BE=97.01% | CI-lo 6.3 pp below | CI-lo **6.6 pp below** | widened |
| Rate est. | ~4/day (12h window) | **~15/day** (24h window) | revised up |

**2nd loss locks in:** The second post-cut loss occurred during Jul-22 (confirmed at n=65, 63W/2L in EVOLVE daily). By EVOLVE evening (n=72, 70W/2L) no further losses. WR 97.22% is 0.21 pp above BE=97.01%, but Wilson CI-lo at 90.4% is 6.6 pp below BE. Status: COLLECTING, no change to formal classification, but math warning materially updated (see FLAG-1).

**XRP cell first loss:** EVOLVE evening (Jul-22) notes "xrp cell first loss (17W/1L −$1.50)". Per-asset breakdown needs refresh via shadow_grade.py when network is accessible. Prior state per-asset rows are stale.

---

### All other gates: no change

- G1: n=934, AMBIGUOUS. Shadow fires continue: today (Jul-23 through 09:00 UTC) 4 fires on d+2 markets (Seoul 0.775, Tokyo 0.770, Chengdu 0.845, Taipei 0.820). Yesterday (Jul-22): 9 fires, 5 in G7 gate (confirmed by band_struct_lite parse). Resolution n frozen (join blocked).
- G2a: n=115, BAND_NO_ENABLED=False. Shadow fires ongoing, unresolvable.
- G2b/G2c: n=9 each, frozen, band dark.
- G3: n=75, WATCH_ITEM. No new fills. 4 Exec Auditor backlog items (Jul-16 SELL@0.96, Jul-18 SELL@0.92, Jul-18 BUY@0.08, Jul-19 orphan BUY@0.02) still unclassified; n held at 75.
- G4: VOID, no change.
- G5: n=125, REJECTED. Shadow file growing inertly.
- G6: n=31, REJECTED. metar_min_lockout.jsonl growing inertly.
- G7: n=382, AMBIGUOUS. Today: 4 shadow fires all in [0.70,0.85] gate (Seoul/Tokyo/Chengdu/Taipei d+2 Jul-25). Resolution n frozen. Pending: Seoul d+1 from Jul-22 = Jul-23 market resolves TODAY — eligible for next join.

---

## PROPOSED ACTIONS (human review)

**No gate newly hit READY or REJECTED this run. Zero flag/param changes proposed.**

The human decision needed on G8 threshold (FLAG-1) is not a gatekeeper action — it is a standing open question from prior run, now made more urgent by the 2nd loss arrival.

---

## FLAGS FOR HUMAN AWARENESS

---

### FLAG-1 🚨 G8 MATH UPDATE: 2ND LOSS RAISES MINIMUM PASS THRESHOLD TO n≈245

**Prior warning (1 loss):** "Minimum n=200 to clear Wilson CI (199W/1L → CI-lo=97.2%)."
**Current math (2 losses):** n=200 is no longer sufficient.

Wilson CI-lo analysis for n=200 with 2 losses: 198W/2L → p=0.990 → CI-lo=**96.4%** < BE=97.0% → **FAIL**.

| Scenario | WR | Wilson CI-lo | vs BE=97.01% | Verdict |
|---|---|---|---|---|
| n=100, 0 more losses (98W/2L) | 98.0% | 93.0% | FAIL −4.0 pp | — |
| n=200, 0 more losses (198W/2L) | 99.0% | 96.4% | **FAIL −0.6 pp** | — |
| n=245, 0 more losses (243W/2L) | 99.2% | 97.1% | PASS +0.1 pp | min threshold |
| n=300, 0 more losses (298W/2L) | 99.3% | 97.6% | PASS +0.6 pp | comfortable |

n=245 is the **best-case minimum** (zero further losses). Observed loss rate 2/72 = 2.8%. Expected additional losses from n=72 to n=245 = ~4.8. Each additional loss extends the minimum n further. The EVOLVE's "pass-branch unreachable before n≈400-3000" accounts for this stochastic reality.

**Updated human decision options:**
1. **EXTEND threshold to n=300** — practical minimum accounting for likely future losses; ~15 days at current rate.
2. **KILL now** — EVOLVE has twice flagged KILL as the realistic outcome. No capital at risk (UPDOWN_STOP active). Terminates ~2 weeks of shadow accumulation.
3. **Wait to n=100 (~Jul-25) then decide** — Gate will be AMBIGUOUS at n=100 regardless (CI-lo≈93.0% far below BE). Human can reassess with n=100 data.

The prior recommendation of extending threshold to n=200 is now mathematically invalid. **Human confirmation of the new target (n=300 or KILL) is needed before n=100 arrives (~Jul-25).**

---

### FLAG-2 ⚡ G8 RATE UNCERTAINTY: RANGE 4–15/day

Measured rate windows:
- Jul-21 09:07Z → Jul-21 evening: +2 in ~12h = **~4/day**
- Jul-21 evening → Jul-22 evening: +15 in ~24h = **~15/day**
- Implied Jul-22 evening → Jul-23 09:00Z: +6-8 in ~11h ≈ **13-17/day**

Jul-22 appears to have been an active session. The Jul-21 slow window may be a local minimum. Until shadow_grade.py runs and returns a clean count, the true rate is bracketed at [4, 15]/day. ETAs:

| Target n | At 15/day | At 4/day |
|---|---|---|
| n=100 (+28 events) | ~Jul-25 | ~Jul-29 |
| n=245 (+173 events) | ~Aug-3 | ~Sep-14 |
| n=300 (+228 events) | ~Aug-7 | ~Oct-4 |

At 15/day, n=100 arrives within 2 days — AMBIGUOUS is already the certain outcome at n=100 (math above). The human decision on threshold extension or KILL is urgent regardless of which rate is correct.

---

### FLAG-3 🔌 NETWORK BLOCKED — THIRD CONSECUTIVE RUN

git fetch has timed out for the third consecutive gatekeeper run. Consequences:
- G8: shadow_grade.py not runnable; n count relies on EVOLVE commit journal (reliable but manual).
- G1/G7: band_resolution_join.py blocked. Jul-22 d+1 fires (Seoul Jul-23) resolve **today** — these will be missed until network recovers.
- G3: maker_fills_recent.log not fetchable; G3 fill join stale at n=75.
- Accumulating shadow-vs-resolved divergence in G1/G7: shadow fires accumulate daily, resolved n frozen at 934/382.

This is a recurring structural issue, not a one-time transient. Either the VPS network connectivity for this agent (scheduled on-web session) is consistently degraded, or the git server is rate-limiting agent fetch attempts. Recommend: VPS SSH session to run joins directly.

---

### FLAG-4 💀 ZERO ACTIVE TRADING PATHS — DAY 17

All revenue paths halted simultaneously:
- **UPDOWN/Sniper:** STOP since Jul-19 (PF 0.79 over 27 settles; UPDOWN_STOP file present)
- **BAND:** dark since Jul-06, day 17 (capital $21.50 < ruin floor $89.16)
- **LDA:** STATUS=STOP (worst rolling-20 = −$36.39 below −$30 threshold)
- **THERMO/M1:** REJECTED

Klaus is running (systemd: active, uptime since Jul-17) but has no executable trading path. Capital $21.495 = 7.2% of original capital. Bot has no self-recovery path without explicit human restart decision on at least one path.

---

## STRUCTURAL BLOCKERS (unchanged)

1. `UPDOWN_STOP` active since 2026-07-19T11:26Z — PF 0.79 over 27 settles
2. `BAND_LIVE=False` since 2026-07-06T22:08Z — day 17; capital $21.50 < ruin floor $89.16
3. **G3 winner's curse CONFIRMED** (n=75, filled WR 17.3% vs sim 7.6%; CI entirely negative) — no band/sniper re-enable may cite G1/G7 sim-CI as positive evidence
4. G5 THERMO and G6 M1: REJECTED — no reconsideration without explicit human directive
5. LDA STOP active
6. G8: 2nd loss locks minimum pass threshold at n≈245 (best case) to n≈300-400 (realistic); n=200 recommendation now invalid

---

*Gatekeeper agent run complete. Report-only. No code or flag changes made.*
*Prior state SHA: fcc315f96 (gatekeeper commit Jul-22) | Data snapshot: 239c2daeb9 (data-mirror Jul-23 09:00Z)*
*G8 source: EVOLVE journal commits Jul-22 daily (n=65 63W/2L) and Jul-22 evening (n=72 70W/2L); shadow_grade.py not run this session.*
