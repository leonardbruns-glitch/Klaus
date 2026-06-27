# Gate-Keeper Report — 2026-06-27

**Run**: 2026-06-27 ~10:30 UTC  
**Snapshot**: 2026-06-27T08:54:46Z (age: ~1.6h — FRESH)  
**Bot**: active (restarted 2026-06-26 15:08 UTC; was down 49h since Jun24 08:04)  
**Bankroll**: $61.16 (prior run 2026-06-26 08:56: $198.28)  
**Total trades**: 8,002 | **Open positions**: 0 | **Shadow files**: 20  

> **BANKROLL ALARM (out of scope — flagged for human/PnL auditor):**  
> $61.16 vs $198.28 prior = −$137.12 (−69.1%). Breaches -25% weekly floor and -20% monthly kill  
> switch from CLAUDE.md. Bot is currently live and posting. Gate-keeper does not act on PnL —  
> flagged here for completeness only.

---

## 7-Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| BAND_YES (d+2 regime) | ~5,924 | +19 | BLOCKED | BLOCKED | BLOCKED | COLLECTING | n/a — CI blocked (Gamma 403) |
| BAND_NO_PAIR_FAV | ~227 | +14 | BLOCKED | BLOCKED | BLOCKED | COLLECTING | n/a — CI blocked (Gamma 403) |
| FILLED_VS_FIRED (7d window) | ~37 | −60† | BLOCKED | BLOCKED | BLOCKED | COLLECTING | n/a — CI blocked (Gamma 403) |
| BASKET_EXIT | — | — | — | — | — | **VOID** | Retired 2026-06-22 (tautological) |
| THERMO_MAKER_NO | 3 | 0 | 0.333 | −66% | [−132.6%, +0.7%] | COLLECTING | STALLED — engine paused, rate=0, n=20 unreachable |
| M1_BETA_LOCKOUT | 31 | 0 | 0.742 | −0.6% | [−20.6%, +24.4%] | **AMBIGUOUS** | STALLED 15+ days — metar_lockout.jsonl absent |
| SUM_POSTED [0.70,0.85] | ~2,958 | +4 | BLOCKED | BLOCKED | BLOCKED | COLLECTING | n/a — CI blocked (Gamma 403) |

†FILLED_VS_FIRED n shrank from 97 → ~37: rolling 7d window evicted pre-stall fills; 49h bot stall  
produced zero new fills. Not a data corruption — window rollover plus stall gap.

---

## State Transitions vs Prior (2026-06-26T08:56Z)

| Gate | Prior Status | Current Status | Δ |
|---|---|---|---|
| BAND_YES | COLLECTING | COLLECTING | No change — CI blocked; +19 legs (narrow-start regime ~17/day) |
| BAND_NO_PAIR_FAV | COLLECTING | COLLECTING | No change — CI blocked; +14 fires (10-14/day) |
| FILLED_VS_FIRED | COLLECTING | COLLECTING | n DROPPED 97→~37 (stall + 7d rollover) |
| BASKET_EXIT | VOID | VOID | No change |
| THERMO_MAKER_NO | COLLECTING | COLLECTING | No change — engine paused, n stuck at 3 |
| M1_BETA_LOCKOUT | COLLECTING | **AMBIGUOUS** | CI straddles 0; n=31 confirmed stalled 15+ days |
| SUM_POSTED [0.70,0.85] | COLLECTING | COLLECTING | No change — CI blocked; +4 legs (Chengdu Jun29 d2 sum=0.735) |

---

## Structural Blockers

1. **Gamma API 403 (cloud container)**: All fire-based ROI/CI computation blocked. This environment's  
   IP is blocked by Cloudflare WAF. WR, ROI, CI95 cannot be computed here for BAND_YES, BAND_NO_PAIR_FAV,  
   FILLED_VS_FIRED, or SUM_POSTED gates. VPS-side `band_resolution_join.py` cron runs daily at 09:45 UTC  
   and has been computing resolution truth since 2026-06-17 (last known state: n=3,418 resolved legs,  
   YES +7.6%, NO +3.7%, described as DECISION-READY on VPS). This routine cannot access or retrieve  
   that VPS-side result — structural gap, not fixable from cloud container.

2. **THERMO_MAKER_LIVE=False**: Engine paused 2026-06-23 (capital freed for NO_RESERVE phase 1).  
   No new THERMO fills since Jun23. Kill gate threshold n=20 is permanently unreachable at rate=0.  
   Gate will remain COLLECTING until engine is re-activated.

3. **metar_lockout.jsonl absent**: Shadow logger for M1β lockout missing from ALL shadow directories  
   Jun22–27 (15+ days). n=31 confirmed stalled. No new data accumulating in cloud-readable shadow  
   files. Standing rule triggered.

---

## Narrow-Start Regime Note

The 2026-06-26 narrow-start fix (commit 847a22fe5) changed YES fire rate from ~225 legs/day  
(pre-fix) to ~17-20 legs/day (post-fix: 5 cities × 1 first-fire/day × 3-4 legs at d+2 only).  
NO rate ~10-14/day. Fire counts above reflect post-fix accumulation only for the ~19h of bot  
uptime since restart at 15:08 UTC Jun26.

---

## PROPOSED ACTIONS (human review)

**No gates newly READY or REJECTED this run.** CI cleared for zero is the only threshold —  
current CI data is blocked for fire-based gates. The following are standing-rule flags.

---

### ACTION 1 — M1_BETA_LOCKOUT: Standing-Rule REVERT Recommendation

- **Gate**: M1_BETA_LOCKOUT  
- **Current state**: n=31, AMBIGUOUS, CI [−20.6%, +24.4%] straddles zero  
- **Condition met**: n<100 with >14 consecutive days of stall, metar_lockout.jsonl shadow logger  
  absent from all directories Jun22–27  
- **Standing rule**: If M1β lockout accumulation stalled >7 days and n<100, recommend REVERT  
  to 0.5C floor  
- **Recommended action**: Set `METAR_LOCKOUT_TEMP_FLOOR = 0.5` (revert to prior floor value);  
  disable lockout expansion until (a) shadow logger is restored and (b) n accumulates past 100  
- **Rationale**: At n=31, CI straddles zero — lockout has no demonstrated edge. Shadow logger  
  absence means the experiment produces zero new data. Reverting costs nothing; continuing  
  consumes capital opportunity on an unvalidated parameter expansion.  
- **Implementation**: Human flips flag. Do NOT implement automatically.

---

### TRACKING NOTE — THERMO_MAKER_NO (no action)

Engine paused Jun23 by capital priority decision (NO_RESERVE phase 1). Kill gate n=20 requires  
reactivation. If THERMO_MAKER_LIVE is set to True, the gate resumes from n=3. At that point  
WR=0.333, ROI=−66%, CI barely straddles 0 at [−132.6%, +0.7%] — close to REJECTED once more  
data accumulates. No action recommended — engine state is intentional.

---

*Gate-keeper routine complete. No flags were flipped. Human review required for PROPOSED ACTIONS.*  
*VPS-side CI data (DECISION-READY per Jun17 state_log entry) not accessible from this environment.*
