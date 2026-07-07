# Gate-Keeper Report — 2026-07-07

Generated: 2026-07-07T09:03:16Z | Snapshot age: <6h ✓ | System: active ✓  
Prior run: 2026-07-06T09:10:00Z | Capital: $42.02 (daily_start $108.35; −$66.33 sprint ladder today)  
**Wind-down active** (Jul06 22:10Z): BAND_LIVE=False, M1_BETA_PROBE_ENABLED=False, MIN_LOCKOUT_LIVE=False

---

## Gate Ledger

| # | Gate | n (resolved/live) | +24h live | +24h shadow | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|---|---|
| G1 | BAND_YES (standalone paused, dout=9) | 934 resolved | +0 | +120 shadow | 15.3% | +4.0% | [−10.9%, +21.1%] | **AMBIGUOUS** | VPS join needed; disp_ratio 0.82 << 1.10 re-enable |
| G2a | BAND_NO (BAND_NO_ENABLED=False) | 51 live / 115 shadow | +0 | +0 | 39.2% live | neg EV | CI straddles 0 (shadow); live effectively rejected | **REJECTED** (live) / AMBIGUOUS (shadow) | Disabled; live n insufficient |
| G2b | PAIR_FAV_YES (post-guard, live) | **9** | **+4** | n/a | null | null | null | **COLLECTING** | ~2.8d from re-enable (rate 11/day); rate=0 now |
| G2c | PAIR_FAV_NO (post-guard, live) | **9** | **+4** | n/a | null | null | null | **COLLECTING** | ~8.3d to n=100 from re-enable; rate=0 now |
| G3 | FILLED_VS_FIRED (fills vs all-fires ROI) | 37 fills | +0 | n/a | null | null | null | **COLLECTING** | 3 fills to n=40 watch trigger; rate=0 (BAND_LIVE=False) |
| G4 | BASKET_EXIT | VOID | — | — | — | — | — | **VOID** | Permanently retired Jun22 |
| G5 | THERMO_MAKER_NO | 125 | +0 | +0 | null | ≈0% | — | **REJECTED** | Action done (THERMO_MAKER_LIVE=False since Jun23) |
| G6 | M1_BETA_LOCKOUT (thin-margin [0.2,0.5)°C) | 31 | +0 | +0 | 74.2% | −0.6% | [−20.6%, +24.4%] | **REJECTED** | Action done (M1_BETA_PROBE_ENABLED=False; floor=0.5°C) |
| G7 | SUM_POSTED [0.70,0.85] band fires | >>100 shadow fires | +0 live | +109 shadow | null | null | null | **COLLECTING** | CI sole blocker; VPS `band_resolution_join.py` overdue |

**n < threshold = COLLECTING; n ≥ threshold AND CI_lower > 0 = READY; n ≥ threshold AND CI_upper ≤ 0 = REJECTED; CI straddles 0 = AMBIGUOUS**

---

## State Transitions vs Prior (2026-07-06T09:10:00Z)

**Changed (+2 gates updated):**
- **PAIR_FAV_YES**: COLLECTING n=5 → COLLECTING **n=9** (+4)  
  New post-guard live fires: Shanghai 10:28Z, Beijing 12:01Z, Chongqing 13:58Z, Munich 14:06Z (all Jul06 d+0, all pre-wind-down). Accumulation stopped at wind-down 22:08Z.
- **PAIR_FAV_NO**: COLLECTING n=5 → COLLECTING **n=9** (+4)  
  Same 4 pairs as above (co-posted YES+NO legs).

**Unchanged:** G1 BAND_YES, G2a BAND_NO, G3 FILLED_VS_FIRED, G4 BASKET_EXIT, G5 THERMO_MAKER, G6 M1_BETA_LOCKOUT, G7 SUM_POSTED — no status changes.

**Data note (G1 shadow fires):** +120 shadow fires since prior run: 12 pre-wind-down from Jul06 archive (1 before prior cutoff + 11 after, all with `live: true`), plus 108 post-restart from today's hot band_struct.jsonl (Jul06 22:08Z–Jul07 09:03Z). Three fires in the Jul06 archive at 23:44Z, 01:04Z, 03:46Z are marked `live: true` post-wind-down — these are from the restarted process where `live` reflects market acceptability, not actual posting (no corresponding tokens in band_posted_state.json Jul07 entry). n_fires updated: 6163 → 6283.

---

## Wind-Down Status

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Equity | $42.02 | ≥$111.45 (50%×$222.90 HW) | ❌ BELOW — wind-down active |
| Daily PnL today | −$66.33 (sprint ladder) | −14% of daily_start | Daily halt: −$15.17; breached |
| Re-enable condition | equity ≥50%×HW AND pair n≥40 trend | n=9/40 AND $42/$111 | Not met on either leg |

Capital trajectory since prior run: $141.74 (Jul06 09:10Z) → $108.35 (Jul06 22:08Z wind-down trigger) → $42.02 (Jul07 09:03Z). Today's loss: sprint ladder shots at Jul07 00:00Z (56sh @ $0.37, $20.72) and 02:00Z (94.75sh @ $0.46, $43.59) = ~$64.31 (authorized coin-flips per owner directive).

---

## PROPOSED ACTIONS (Human Review)

**No gates newly hit READY or REJECTED this run.**

This section lists only newly actionable verdicts. None exist today.

---

### Advisory (informational — gatekeeper does not implement)

**[URGENT] G7 SUM_POSTED [0.70,0.85]:**  
CI remains the sole blocker for this gate. n>>100 deduped shadow fires has been true for weeks. The VPS can close this gate in one run:
```bash
python3 analysis/weather/band_resolution_join.py   # with sum_posted ∈ [0.70,0.85] filter on deduped first-fire legs
```
This is cloud-blocked (Gamma API 403); only EVOLVE on VPS can execute. Verdict (READY or REJECTED) would immediately inform whether to restore the V3 gate extension. Escalating priority: every day without this join leaves a potentially-valid slice unscaled or an invalid slice unrejected.

**[MONITORING] G2b/G2c PAIR_FAV accumulation frozen:**  
n=9 (need 40 for trend verdict, 100 for scale-up gate). With BAND_LIVE=False, rate=0. Re-enable requires equity ≥$111.45; at $42.02 with sprint-ladder EV near zero, timeline is uncertain. Clock will restart automatically when BAND_LIVE flips True.

**[MONITORING] G3 FILLED_VS_FIRED:**  
n=37, 3 fills short of the n=40 watch trigger. Rate=0 with BAND_LIVE=False. When band activity resumes, EVOLVE should immediately queue fill-vs-fire ROI comparison to check for winner's-curse divergence.

**[NOTE] G1 BAND_YES disp_ratio:**  
disp_ratio 0.82 locked 4 days (per research audit Jul06). Re-enable tree requires disp_ratio ≥1.10 ×5d. Standalone YES correctly paused. No action until calib monitor reports disp_ratio recovery.
