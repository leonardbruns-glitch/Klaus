# Gate-Keeper Report — 2026-07-11T09:03Z

**Snapshot**: `2026-07-11T09:03:02Z` (age: 0 min at run time — FRESH)
**System**: `klaus systemd: active` — PASS
**Bankroll**: $163.164 (prior run: $204.064 — **-$40.90 in 24h, band dark, sprint/ladder only**)
**Band status**: DARK day 5 (BAND_LIVE=False since 2026-07-06T22:08Z)
**Freeze**: EXPIRED 2026-07-10T21:53Z ✓
**Equity rail**: $163.16 > $111.45 — MET ✓
**Open positions**: 0
**Pre-reg blocker**: pair_fav n>=40 UNMET (n=9, frozen)
**07-12 structural slot**: TOMORROW — band re-enable decision pending

---

## Gate Ledger

| Gate | n | +24h | WR | ROI | CI95 | Status | ETA |
|---|---|---|---|---|---|---|---|
| G1 BAND_YES | 934 resolved | +0 | 15.3% | +4.0% | [−10.9, +21.1] | **AMBIGUOUS** | Frozen day 5; n/a while dark |
| G2a BAND_NO (shadow) | 115 resolved | +0 | 68.7% | +1.3% | [−11.9, +12.7] | **AMBIGUOUS** (shadow) / REJECTED (live n=51 WR=39.2%) | Disabled (BAND_NO_ENABLED=False) |
| G2b PAIR_FAV YES | 9 pairs live | +0 | n/a | n/a | n/a | **COLLECTING** | Frozen; est. ~8.3d from re-enable at ~11 pairs/day |
| G2c PAIR_FAV NO | 9 live / 32 CF | +0 | n/a (CF n/a) | n/a (CF +52.9%) | n/a ([+12.6,+85.5] CF) | **COLLECTING** | Frozen; est. ~8.3d from re-enable at ~11 pairs/day |
| G3 FILLED_VS_FIRED | 37 filled | +0 | n/a | n/a | n/a | **COLLECTING** | Frozen; 3 fills to n=40 watch; n/a while band dark |
| G4 BASKET_EXIT | — | — | — | — | — | **VOID** (permanently retired Jun-22) | — |
| G5 THERMO_MAKER_NO | 125 resolved | +0 | n/a | 0.0% | [−9.0, +2.0] | **REJECTED** ✓ | Done (THERMO_MAKER_LIVE=False Jun-23) |
| G6 M1_BETA_LOCKOUT | 31 resolved | +0 | 74.2% | −0.6% | [−20.6, +24.4] | **REJECTED** ✓ | Done (M1_BETA_PROBE_ENABLED=False Jul-06) |
| G7 SUM_POSTED [0.70,0.85] | 382 resolved | +0 | n/a | +11.5% | [−11.4, +38.9] | **AMBIGUOUS** | Frozen; need ~1,528 more at ~50/day = ~30.6d from re-enable |

---

## Status Transitions vs Prior Run (2026-07-10T09:00Z)

**NONE.** Fifth consecutive frozen day. All gate n-values unchanged.

- G1, G2a, G7 remain AMBIGUOUS. CI straddles zero on all three; cannot transition to READY without new resolved data.
- G2b, G2c, G3 remain COLLECTING. Zero new fires while BAND_LIVE=False.
- G5, G6 remain REJECTED. Actions complete, flags set; no revisit.
- G4 VOID. Permanent.

---

## Shadow Post Confirmation (band_struct_lite Jul-07 → Jul-11)

Verified via band_struct_lite.jsonl for 2026-07-10 (191 records) and 2026-07-11 (130 records):
- All records are `"record": "md_shadow"` evaluations with `reason: "no_band"` or `reason: "sum_gate"`.
- **Zero `post` records** in either day. Confirmed dark.
- Jul-11 shadow dir contains only `band_struct_lite.jsonl` + `stwa_pricer_eval_s50.jsonl`; no `thermo_maker.jsonl` or `metar_lockout.jsonl` in dated directories (those loggers are in `data/shadow/` hot dir only — both disabled, no new fires expected).

---

## VPS Join Status (band_resolution_join.py)

- Prior state noted join expected at 2026-07-10 ~11:23Z.
- EVOLVE commit (07-10 evening) logged "rails clear + freeze expired, 0 live changes" — no explicit confirmation join ran.
- With band dark since 07-06, any join would pick up only marginal settlement of pre-dark-era legs already counted in n=934. Effect: trivially small, within noise.
- **No VPS join increment applied this run.** Git fetch blocked (network timeout); SSH unavailable. G1 n=934 held; flag for VPS operator verification.

---

## Bankroll Alert

| | Value |
|---|---|
| Bankroll at prior run (07-10T09:00Z) | $204.064 |
| Bankroll now (07-11T09:03Z) | $163.164 |
| Change | **−$40.90 (−20.0%)** |
| Band deployed | $0 (dark) |
| Source | Sprint/ladder strategy (untracked fills in maker_fills_recent.log) |

Sprint/ladder fills visible in maker_fills_recent.log (Jul-08 → Jul-11): mix of BUY entries at 0.35–0.55 and SELL exits at 0.992–0.996. Several BUYs in the Jul-09/10/11 window have no corresponding SELL in the log (possible NO resolutions, i.e., losses). Open positions = 0 as of snapshot, so all positions settled. The −$40.90 net change implies ladder losses exceed ladder wins in this window.

**This is a −20.0% single-day drawdown on the sprint/ladder engine while band is dark. Warrants Exec Auditor review.**

---

## G2c Counterfactual Note (not a gate verdict)

PAIR_FAV_NO counterfactual (VPS join 07-07 EVOLVE): n=32, ROI=+52.9%, CI=[+12.6, +85.5]. CI lower positive.
- n=32 is a **trend only** — below 40 threshold, well below 100 gate threshold.
- Do not re-enable PAIR_FAV_NO or BAND_LIVE on this signal alone.
- Combined per-pair n=30 ROI=+13.0% (07-09 EVOLVE).

---

## 07-12 Structural Decision Context

Tomorrow's structural slot will determine:
1. **BAND_LIVE re-enable path**: shadow-posting mode vs. amending the pair n>=40 condition
2. **Equity condition MET**: $163.16 > $111.45 rail ✓; freeze expired ✓
3. **Binding pre-reg condition UNMET**: pair_fav n=9, need n>=40 — accumulation only possible while BAND_LIVE=True (chicken-and-egg)
4. **S3 dispersion gauge**: UNBLOCKED per 07-10 EVOLVE, but trigger NOT met (Jul 3-10: 1/8 days ≥1.10, median-city ≤0.80 all days)

---

## PROPOSED ACTIONS (Human Review)

**No newly READY or REJECTED gates this run.**

No flag changes recommended from gate data alone.

**Advisory only (not gate-driven):**
- [ ] **Exec Auditor**: Investigate ladder −$40.90 drawdown (07-10T09Z → 07-11T09Z). Identify which sprint tokens resolved NO. Assess if ladder risk parameters need review.
- [ ] **07-12 structural slot**: Decide BAND_LIVE re-enable path — shadow-posting mode (resolves chicken-and-egg for pair accumulation) vs. condition amendment. G2c trend is compelling but n<40.
- [ ] **VPS operator**: Confirm band_resolution_join.py ran at 07-10 11:23Z; publish G1/G7 marginal increment if any. Gate-keeper used n=934/382 from 07-10 state; increment expected <10 resolved.

---

*Gate-Keeper automated run. REPORT ONLY — no strategy code or flags modified.*
*Prior state: logs/gatekeeper_state.json on claude/find-lag-parameter-rFQ0N @ 2026-07-10T09:00Z*
