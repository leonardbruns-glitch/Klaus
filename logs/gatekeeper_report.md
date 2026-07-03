# Klaus Gate-Keeper Ledger — 2026-07-03T12:43Z

**Snapshot:** 2026-07-03T12:43:16Z (age: 0h — FRESH)  
**Klaus systemd:** active  
**Bankroll:** $82.30 (+$3.26 vs prior $79.04)  
**Prior run:** 2026-07-02T12:45:00Z  

---

## Gate Status Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|------|---|------|----|-----|------|--------|-----|
| 1 BAND_YES | ~6,147 | +33 | — | — | BLOCKED | COLLECTING | N/A (CI sole blocker) |
| 2 BAND_NO_PAIR_FAV | ~272 | +6 | — | — | BLOCKED | COLLECTING | N/A (CI+EVOLVE dual-blocked) |
| 3 FILLED_VS_FIRED | ~107† | +10 | — | — | BLOCKED | COLLECTING | N/A (n≥100†; CI sole blocker) |
| 4 BASKET_EXIT | VOID | — | — | — | — | VOID | — |
| 5 THERMO_MAKER_NO | 3 | 0 | 33.3% | −66% | [−132.6, 0.7] | COLLECTING | Never (rate=0) |
| 6 M1_BETA_LOCKOUT | 31 | 0 | 74.2% | −0.6% | [−20.6, 24.4] | AMBIGUOUS | Never (rate=0) |
| 7 SUM_POSTED_0.70_0.85 | ~3,035 | ~0 | — | — | BLOCKED | COLLECTING | N/A (CI sole blocker) |

† Gate 3 crossed n=100 threshold this run (~107 est., was 97). CI still blocked — status stays COLLECTING. No flip.

---

## State Transitions vs Prior

No gates changed status.

**Notable changes:**
- **FILLED_VS_FIRED:** n crossed 100 threshold (~107 est., +10 in 24h at ~10.7/day rate). CI blocked — no status flip yet.
- **M1_BETA_LOCKOUT:** DAY 21 stall (was day 20). Proposal unactioned DAY 6 (was day 5). Escalating.
- **SUM_POSTED_0.70_0.85:** Rate ~0 in past 24h. All Jul 03 YES fires have sum_posted 0.55–0.65, below the [0.70, 0.85] slice. Market-cycle effect: Jul 05 d+2 markets just opened (low liquidity). No n change. Prior +16/day rate will recover as markets mature.
- **Bankroll:** $82.30 (+$3.26 vs yesterday's $79.04). Exit099 recycles today: +$2.56 +$2.33 +$2.88 = **+$7.77** (3 recycles).

---

## PROPOSED ACTIONS (human review)

### BAND_NO_PAIR_FAV — No new action required
EVOLVE auto-halt (Jul 02 06:14Z, 7d n=51 WR=39.2% PF breach) already acted. EVOLVE verdict is the independent rejection signal; gate CI result would be consistent with REJECTED if Gamma unblocked. No additional flag flip needed.

### M1_BETA_LOCKOUT — REVERT METAR_LOCKOUT_TEMP_FLOOR to 0.5°C *(ESCALATED)*
**Gate:** M1_BETA_LOCKOUT  
**Action:** Set `METAR_LOCKOUT_TEMP_FLOOR` back to 0.5°C.  
**Reason:** n=31 AMBIGUOUS (CI straddles 0; ROI=−0.6%, CI95=[−20.6, 24.4]). metar_lockout.jsonl absent from ALL shadow directories checked: 2026-07-03, 2026-07-02, 2026-07-01. Rate=0 for 21 consecutive days. Gate n=100 permanently unreachable. Standing rule triggered Jun 13 (>14 days stall → revert). Proposal standing since Jun 27 — **now day 6 unactioned**. No edge proven; CI cannot prove one at rate=0. Revert is the CI-compliant decision.  
**Standing since:** 2026-06-27T10:30Z  
**Human required:** YES — flag/config change needed.

---

## Gate Detail Notes

### Gate 1 — BAND_YES (n~6,147, COLLECTING)
Gamma 403 is sole blocker. n~6,147 >> threshold 100 per slice. Rate: ~33 YES legs/day from band_struct_lite (today: London/Munich/Beijing/Chengdu/Wuhan d+2 Jul 05 fires plus pair_fav d0/d+1 YES posts). BAND_YES_LIVE_MIN_DOUT=2 (d+2 only); BAND_CITY_ALLOW: 5 cities. CI requires CLOB winner flags from Gamma — impossible from this sandbox. VPS-side `band_resolution_join.py` is the only path.

### Gate 2 — BAND_NO_PAIR_FAV (n~272, COLLECTING — dual-blocked)
Standalone band-NO halted (BAND_NO_ENABLED=False, Jul 02 06:14Z EVOLVE rail). Pair_fav NO legs STILL ACCUMULATING: ~6 pair_fav NO legs since prior — Munich Jul 04 d+2 (Jul 02 ~18:52Z), Chengdu d0 (Jul 03 ~02:35Z), Wuhan d0 (Jul 03 ~03:59Z), London Jul 05 d+2 (Jul 03 ~04:11Z), Beijing Jul 04 d+1 (Jul 03 ~06:14Z), London Jul 04 d+1 (Jul 03 ~06:47Z). Rate ~5–6 pair_fav NO/day going forward. n=272 >> 100. Dual blocker: (a) Gamma 403 for CI; (b) EVOLVE halt = independent rejection signal. VPS join would unblock CI but EVOLVE verdict already signals REJECTED outcome.

### Gate 3 — FILLED_VS_FIRED (n~107, COLLECTING — threshold crossed)
Prior est. n=97 at Jul 02 12:45Z. Rate ~10.7/day → +10 in 24h → n~107 (crossed n=100 threshold). Exit099 recycles today: 3 recycles (+$7.77). Maker resting state: 5 SELL_EXIT orders (matched=0, resting at 0.99) + 1 active YES bid (Beijing Jul 04 d+1, 29526700..., partial fill 2/8.89 shares). Chengdu d0 pair merged, locked $0.89 today. CI blocked — Gamma 403. Winner's-curse watch ACTIVE. Note: FILLED_VS_FIRED CI join requires maker_fills_recent.log token cross-join to resolutions in addition to Gamma winner flags — more complex than BAND_YES join.

### Gate 4 — BASKET_EXIT (VOID)
Permanently retired Jun 22. No change.

### Gate 5 — THERMO_MAKER_NO (n=3, COLLECTING — stalled indefinitely)
Engine paused (THERMO_MAKER_LIVE=False since Jun 23 18:40). Rate=0. Kill gate n=20 unreachable. CI=[−132.6, 0.7] at n=3 is pure noise (straddles 0). No change since prior.

### Gate 6 — M1_BETA_LOCKOUT (n=31, AMBIGUOUS — DAY 21 STALL)
metar_lockout.jsonl absent from 2026-07-03, 2026-07-02, 2026-07-01 shadow directories. Rate=0. Gate n=100 permanently unreachable. WR=74.2%, ROI=−0.6%, CI95=[−20.6, 24.4] straddles zero — AMBIGUOUS is noise at n=31. Standing rule triggered Jun 13 (>14d stall → REVERT). Proposal standing since Jun 27, **now DAY 6 UNACTIONED**. Stall is structural (logger absent), not transient; no recovery expected without a code push.

### Gate 7 — SUM_POSTED_0.70_0.85 (n~3,035, COLLECTING)
CI blocked (Gamma 403). Rate ~0 in past 24h: all Jul 03 YES fires from band_struct_lite reviewed show sum_posted in [0.55–0.65], below the [0.70, 0.85] gate slice. Jul 02 fires (04:11Z, before prior snapshot) had sum_posted in [0.726–0.805] and contributed ~15 legs; those were already in prior n=3,035. Current low rate is market-cycle: d+2 markets for Jul 05 opened early (low sum_ask). Rate recovers when d+2 markets mature (~24–48h lag). n=3,035 >> 100; CI is sole blocker.

---

## Advisory

1. **VPS-side `band_resolution_join.py` is the critical path.** Unblocks CI for gates 1, 2, 3, and 7 simultaneously in one run. Overdue. Gate 3 has now crossed n=100 — CI is the only remaining gate for 4 gates.

2. **Jeddah expand_city fire (Jul 03 band_struct_lite, ts 1783068835):** Entry `{"city": "jeddah", "reason": "fire", "live": True, "sum_ask": 0.33}` appeared without a `"record": "md_shadow"` field. Jeddah is NOT in `BAND_CITY_ALLOW`. This entry likely originates from the expand_city scanner component (which appears to have separate code paths). Verify: (a) was a real order placed for Jeddah? (b) does `BAND_CITY_ALLOW` apply to this scanner path? If not, this is an off-allowlist live fire.

3. **5 SELL_EXIT resting orders:** London Jul 03 NO (894037...), Munich Jul 03 NO (33003077...), Munich Jul 04 YES (106499..., d+2 now d+1), Wuhan Jul 03 NO (42815563...), London Jul 04 YES (9512786...). All matched=0, resting at 0.99. Jul 03 positions resolve today; Jul 04 positions resolve tomorrow.

4. **Beijing Jul 04 YES pair (29526700...):** Partially filled (matched=2.0 of 8.89 shares). Still resting active maker bid at q=0.44. Paired NO order (69599736...) not in maker_resting_state — check if NO side filled first or if order was cancelled.

---

*Run: 2026-07-03T12:43Z | Snapshot age: 0h | Klaus: active | Branch: claude/find-lag-parameter-rFQ0N*
