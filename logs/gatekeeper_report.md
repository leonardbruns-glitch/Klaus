# Klaus Gate-Keeper Report — 2026-06-17

**Generated:** 2026-06-17T10:23:53Z  
**Snapshot age:** 0.1h (limit 6h) ✓  
**Klaus systemd:** active (since 2026-06-17 06:45 UTC) ✓  
**Gamma API:** 403 BLOCKED from container — resolution truth unavailable for all band/basket gates  

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|------|---|------|----|-----|------|--------|-----|
| BAND_YES | 3,296 | +1,712¹ | N/A | N/A | BLOCKED (Gamma 403) | COLLECTING | n>>100; blocked on CI |
| BAND_NO_PAIR_FAV | 53 | +14² | N/A | N/A | BLOCKED (Gamma 403) | COLLECTING | ~7d (if PAIR_FAV 7/day) |
| FILLED_VS_FIRED | 179 | +26 | 98.5%³ | +$27.75 net⁴ | join blocked (CID truncation) | COLLECTING | watch item only |
| BASKET_EXIT | 6,254 | +151 | N/A | N/A | BLOCKED (unit defn + Gamma 403) | COLLECTING | N/A — blocker first |
| THERMO_MAKER_NO | 3 | 0 | 33.3% | −66.6% | [−100%, +2.0%] | COLLECTING | ~34d to kill-gate 20 |
| M1_BETA_LOCKOUT | 31⁵ | +30⁵ | 74.2% | −0.6% | [−21.9%, +25.0%] | COLLECTING | ~13d |
| SUM_POSTED_0.70–0.85 | 1,379 | +168 | N/A | N/A | BLOCKED (Gamma 403) | COLLECTING | n>>100; blocked on CI |

---

## Footnotes & Methodology Notes

¹ **BAND_YES n methodology change.** Prior run counted ~event-level first-fires (Jun11-16: 1,584). This run uses per-(cid, days_out) leg-level dedup (Jun12-17: 3,296). Canonical script (band_resolution_join.py) confirms 3,401 total deduped legs (3,324 YES+PAIR, 77 NO) from the same window. Difference ~2× reflects each fire event having multiple quote legs (median 3). The methodology is now consistent with how the script counts. Jun11 file absent from mirror; Jun17 is partial (10.3h). All counts far exceed the 100-leg threshold; the sole blocker is CI computation.

² **PAIR_FAV fires first appeared.** Gate 2 prior was NO-only (n=39, stalled). PAIR_FAV fires first logged Jun16 (n=11) and Jun17 (n=3) = 14 new. Combined NO+PAIR_FAV = 53. This is the first evidence of BAND_PAIR_FAV_ENABLED=True firing in shadow; prior runs saw zero. Deduped per (cid, days_out). NO rate fully stalled Jun16-17 (0 fires). Human check: was NO stall caused by the phantom-exposure cash-gate strangle fixed Jun17 06:45 UTC? Next 48h will clarify.

³ **FILLED_VS_FIRED WR.** 98.5% is exit099 (RECYCLE099 cascade-sell) winner rate — not the overall filled-leg WR. STWA_RESOLVED losers (held to settlement) bring the combined picture to +$27.75 net.

⁴ **Net band-era P&L declining.** Prior run +$58.56 (Jun11-16). This run +$27.75 (Jun11-17). Breakdown: exit099 +$383.15 (n=67 events, WR=98.5%) + STWA_RESOLVED −$358.07 (n=165) + BAND_MERGE +$2.66 (n=7). Six more RECYCLE099 winners but 64 more STWA_RESOLVED losers since Jun16. The June11-14 period drove the positive; Jun15-17 is net negative. The phantom-exposure fix (Jun17 06:45) may improve RECYCLE099 exit rate going forward.

⁵ **M1_BETA_LOCKOUT methodology error corrected.** Prior run reported n=1 using `bond_entry_class=='M1_BETA_PROBE'` (only 1 trade). Correct class is `WEATHER_M1_PROBE` (n=31 settled trades). The gate pre-registration references "WEATHER_M1_PROBE" explicitly. n=31 is correct from this run forward. WR=74.2% (23/31), ROI=−0.6%, CI95=[−21.9%, +25.0%] — straddles zero, AMBIGUOUS at current n; below 100 threshold so not a verdict. metar_lockout.jsonl is empty across all mirrored dates (shadow logger inactive or no candidates triggered).

---

## State Transitions vs Prior

| Gate | Prior Status | New Status | Change |
|------|-------------|------------|--------|
| BAND_YES | COLLECTING | COLLECTING | n recounted; methodology corrected |
| BAND_NO_PAIR_FAV | COLLECTING | COLLECTING | PAIR_FAV 0→14 (new signal); NO stalled |
| FILLED_VS_FIRED | COLLECTING | COLLECTING | maker_fills format changed to syslog; n=179 |
| BASKET_EXIT | COLLECTING | COLLECTING | n=+151; unit defn blocker persists |
| THERMO_MAKER_NO | COLLECTING | COLLECTING | Unchanged (0 new resolved) |
| M1_BETA_LOCKOUT | COLLECTING | COLLECTING | Methodology corrected: n 1→31 |
| SUM_POSTED_0.70–0.85 | COLLECTING | COLLECTING | n=+168 |

**No gate has transitioned to READY or REJECTED this run.**

---

## PROPOSED ACTIONS (human review)

No gate has newly hit READY or REJECTED. No flag changes are warranted by gate rules.

The following items warrant human attention but are not gate-triggered flag changes:

**A. Net band P&L declining trend.** +$27.75 Jun11-17 vs +$58.56 Jun11-16. Jun15-17 is net negative (64 STWA_RESOLVED losers outpacing 6 new exit099 winners). This is not a gate verdict but correlates with the phantom-exposure strangle diagnosed Jun17 06:45. Recommend: monitor next 48h exit099-vs-STWA_RESOLVED ratio after phantom-exposure fix.

**B. BAND_NO stall.** NO fires: 0 on Jun16, 0 on Jun17. PAIR_FAV starting to fill the gap but gate still COLLECTING. Phantom-exposure fix may restore NO posting — watch for NO fires resuming in next 24h before concluding NO is permanently suppressed.

**C. Gate 4 (BASKET_EXIT) unit definition.** n=6,254 but t_close has float jitter (sub-ms differences creating near-duplicate basket-days). Human must define canonical unit (e.g., round t_close to nearest second) before cash-out vs hold metric can be computed.

**D. Gate 6 methodology note for prior audit trail.** The prior run's n=1 for M1_BETA_LOCKOUT was incorrect (wrong bond_entry_class). The correct n=31 is still well below the 100 threshold and CI straddles zero — no action needed, just noting the prior report was mis-stated.

---

## System Notes

- **Gamma API 403** from this container is the primary blocker for gates 1, 2, 4, 7. The VPS cron (band_resolution_join.py) was fixed Jun17 05:45 UTC to have `cd /root/Klaus &&`. VPS should now be producing daily resolution joins independently. Human: check VPS cron output to see if resolutions are accumulating there.
- **BAND_LIVE=True.** The strategy is live and posting. Cap=~$246. NO cash reserve restored to 0.25 on Jun16. Phantom-exposure fix applied Jun17 06:45.
- **Bankroll:** $246.00 (from $209.31 start-of-band era; 4 consecutive wins currently).

