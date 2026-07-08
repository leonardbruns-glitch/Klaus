# Klaus Research Audit — 2026-07-08T14:30Z

**Data sources:** data-mirror SNAPSHOT 2026-07-08T13:57:09Z (< 6h ✓) | system_status.txt: `Klaus systemd service: active (running)` ✓  
**Specialist reports:** exec_audit (07:07 UTC) ✓ | calib_monitor (08:07 UTC) ✓ | gatekeeper (09:07 UTC) ✓ | pnl_ledger (23:37 UTC Jul 7) ✓ — all within 36h ✓  
**Equity:** $136.77 = 61.4% of HW $222.90 | total_pnl all-time: −$75.40 | ruin floor: $89.16

**System state in one line:** BAND_LIVE=False since Jul 6 22:08 UTC (wind-down); only Sprint Ladder (4W/4L, n=8) and passive RECYCLE099 live; −14% intraday freeze active until 21:53Z tonight; all maker gates COLLECTING or REJECTED.

---

## 1. Primary Bottleneck: Calibration Staleness Blocking the Re-Enable Chain

**Bottleneck rank: calibration/dispersion** — upstream of equity deployed, turns/day, fills, and all gate decisions.

The compounding identity is `equity_deployed × turns/day × ROI/turn`. Currently:
- **Equity deployed in maker: $0** (BAND_LIVE=False; RECYCLE099 passive only)
- **Band turns/day: 0** (36h+ of zero fills post wind-down; exec_audit: "$0 revenue last 24h")
- **Sprint Ladder: the only P&L source** — +$28.41 yesterday (Tokyo −$21.37 loss + Singapore +$49.79 win); 4W/4L on n=8 shots total

The re-enable decision chains entirely through dispersion ratio: **disp_ratio = 0.817 < 1.10 threshold → G1 AMBIGUOUS → BAND_LIVE stays False → G2b/G2c pair fills cannot accumulate (require BAND_LIVE=True) → ETA "2.8d" is effectively infinite under the current config.**

The critical problem: **disp_ratio 0.817 is measured against a 32-day-stale isotonic recalibration map, using only proxy-lane σ (0.831), with the settled lane locked for 6 days** (calib_monitor: S4, S5). We cannot distinguish between:
- **(a) Real dispersion compression** — market regime shift, band has zero edge → stay off  
- **(b) Measurement artifact** — stale pipeline producing a false negative → band could re-enable safely

That distinction is worth the full $136.77 in potential maker deployment. No second-order analysis is credible until (a) vs (b) is resolved.

---

## 2. Existing-System Optimization

Derived from four specialist reports — per item: expected delta / confidence / effort.

**2a. Settled lane unlock + isotonic map rebuild** — HIGH IMPACT  
- *Source:* calib_monitor S4 (map 32d stale) + S5 (proxy σ below baseline) + gatekeeper G1 (AMBIGUOUS, disp_ratio)  
- *Problem:* band_resolution_join cron has not ingested settled data for 6 days. The Jun 17 state_log recorded an identical-pattern cron bug (`cd /root/Klaus` path missing). A 6-day unexplained gap strongly suggests recurrence.  
- *Expected delta:* If cron is broken and fresh settlement data shifts disp_ratio ≥ 1.10 → band re-enable eligible → restores ~$10/day maker revenue (exec_audit 7d baseline: $70.73/7d = $10.10/day when active).  
- *Confidence:* Medium (depends on bug vs genuine data absence; the Jun 17 precedent makes bug likely).  
- *Effort:* Low (30–60 min: log inspection + path fix + manual trigger + map rebuild).

**2b. RECYCLE099 pipeline starving** — MEDIUM IMPACT, no fix available  
- *Source:* exec_audit ($0 revenue 24h); state_log (+$139 lifetime since Jun 11, ~$5.15/day avg across ~27 active days, but zero since wind-down).  
- *Problem:* RECYCLE099 can only sell existing held positions. With zero new maker fills since Jul 6, no new inventory enters the pipeline. RECYCLE099 is a multiplier on band velocity, not independent alpha.  
- *Expected delta:* Recovers ~$5–10/day **only if** band re-enables (PA-1 dependency). No standalone fix.  
- *Effort:* Blocked — requires band re-enable first.

**2c. Intraday freeze lifts 21:53Z today (Sprint Ladder)** — LOW IMPACT, automated  
- *Source:* pnl_ledger (freeze active until 21:53Z); state_log (Sprint Ladder sleeve $145.36, 2 shots/day max).  
- *Expected delta:* ~$10.67/shot (8-shot lifetime avg) × potential 1 shot tonight if EVOLVE fires. No capital reallocation needed; EVOLVE handles automatically.  
- *Confidence:* Low-Medium (4W/4L = 50% WR on n=8 is uninformative; individual shot quality determines EV).  
- *Effort:* Zero (automated by EVOLVE daily actuator).

**2d. M1β + MIN_LOCKOUT offline — no near-term fix**  
- *Source:* band_config.txt (M1_BETA_PROBE_ENABLED=False, MIN_LOCKOUT_LIVE=False by wind-down protocol).  
- M1β WR 98.7% OOS (state_log Jun 9) but capacity near-zero. Cannot safely re-enable before wind-down protocol formally clears (no date set; human review required).  
- *Expected delta:* Minimal capacity (<$1/day estimated) even at full re-enable; deprioritize.

---

## 3. Gate Pipeline Review

From gatekeeper_report (09:07 UTC):

| Gate | Status | Progress | ETA | Accelerant |
|---|---|---|---|---|
| G1 — BAND_YES | AMBIGUOUS | disp_ratio 0.817 / need 1.10 | Market regime or settled-lane fix | Settled lane debug (PA-1) |
| G2a — BAND_NO | REJECTED | Insufficient EV evidence | None | None |
| G2b — PAIR_FAV_YES | COLLECTING | 9/40 co-fills | **∞** (BAND_LIVE=False) | Band re-enable → G1 → PA-1 |
| G2c — PAIR_FAV_NO | COLLECTING | 9/40 co-fills | **∞** (BAND_LIVE=False) | Band re-enable → G1 → PA-1 |
| G3 — FILLED_VS_FIRED | COLLECTING | 37/100 | **∞** (BAND_LIVE=False) | Same dependency |
| G4 — BASKET_EXIT | VOID | Permanently retired Jun 22 | — | — |
| G5 — THERMO_MAKER | REJECTED | EV≈0 confirmed | None | None |
| G6 — M1β thin-margin | REJECTED | Rejected | None | None |
| G7 — SUM_POSTED | COLLECTING | Below threshold | Unknown | Band fills |

**Deadlock structure:** G1 (disp_ratio) is the keystone gate. All collecting gates (G2b, G2c, G3, G7) accumulate only via live band fills, which require G1 to clear first. G1 clears only when disp_ratio ≥ 1.10, which depends on either (a) natural market regime recovery or (b) fresh settled-lane measurement proving the 0.817 reading is stale/incorrect.

**What would accelerate accumulation without degrading EV:** The only lever is the settled-lane / isotonic rebuild (PA-1). City-breadth expansion (BAND_CITY_ALLOW is currently 5 cities) could increase fill rate once the band is live, but is irrelevant until G1 clears. No gate is near a genuine READY verdict today without PA-1.

---

## 4. Assumption Attack

**A1: Dispersion premium persists** (implied σ > realized σ → maker YES/NO fill at premium)

- *Supporting:* Historical YES ROI +7.6% (n=3,275 from Jun 17 data — decision-grade); band generated $70.73 in last 7 active days (exec_audit); RECYCLE099 +$139 cumulative (mechanism proven).  
- *Threatening:* disp_ratio = 0.817 (inverted — market pricing *less* uncertainty than model baseline). Proxy σ 0.831 vs baseline σ 0.994 = −16.4% below baseline. The premium has not merely shrunk; it has reversed in the proxy lane. If this reading is accurate and persistent, YES band EV is negative. But the settled lane has been dark for 6 days — we cannot confirm whether the reversal is real or a measurement artifact from the 32d-stale isotonic map (calib_monitor S4, S5).  
- **Verdict: THREATENED by live proxy data; unresolvable until settled lane is unblocked. This is the single most important unknown in the system today.**

**A2: Fills are not adversely selected** (maker fills represent uninformed takers, not informed counter-parties systematically beating the band)

- *Supporting:* No exec_audit red flags on markout in the last active period. Same-bucket pair structure provides natural hedge. Fill-vs-fired gate at n=37/100 (not yet decision-grade).  
- *Threatening:* Moscow false lockout (−$24.65) was data-feed corruption (SPECI/interim-ob divergence), not adverse selection per se. But it demonstrates the system can silently build 104.5-share concentrated positions on corrupt oracle data. With isotonic map 32d stale, recalibration inputs degrade — band could post at systematically wrong prices without knowing it. This is oracle-failure adverse selection, not counter-party selection, but the loss mechanism is identical.  
- **Verdict: Counter-party adverse selection not confirmed as active threat. Oracle-failure tail risk is real, partially fixed (Moscow), but likely has sibling cities (see E3). Net: manageable with cross-validation guard.**

**A3: Recycle velocity scales** (RECYCLE099 compounds maker fills into additional turns/day)

- *Supporting:* +$139 cumulative since Jun 11 proves mechanism works when band feeds it inventory.  
- *Threatening:* BAND_LIVE=False for 36h+ → zero new maker fills → no new positions entering the recycling pipeline. RECYCLE099 is structurally downstream of band fills; it cannot self-sustain or scale independently. The pipeline input is currently zero.  
- **Verdict: Assumption is correct in principle, but currently produces zero revenue because band is off. Not a broken assumption — a broken input.**

---

## 5. Market Intelligence — Platform Mechanics (day-of-month 8 mod 3 = 2)

Scope: fee schedule / maker-rebate / liquidity-rewards changes since last check (Jun 10, state_log).

**Known stable facts (no changes detected in state_log through Jul 7):**
- Fee reform 2026-03-30: 8 new categories added; weather market (temp band) taker fee at ~1.56% at 50% odds, near 0% at extremes. No subsequent revision recorded.
- Maker rebate: 100% of taker fees redistributed to makers (structural policy, unchanged).
- Tick size: 0.01 for temperature band markets (standard; no change).

**Implication for current regime:** At disp_ratio ≤ 1.0 (dispersion compressed), the maker rebate (~1.56% at mid-market, declining toward extremes) is the **floor on band EV**. At posting price ~0.44 (near YES band center), taker fee is sub-1.56% but still positive. If the dispersion premium has genuinely collapsed, maker rebate alone is insufficient to justify the operational risk — but it is not zero.

**Delta vs prior state:** No new mechanics detected from available data. shadow_summary.json chunks 08–12 (Jul 5–Jul 8 period) were not retrieved; any platform announcements in the last 3 days are not visible. No action triggered.

---

## 6. Three Experiments

**E1: Settled Lane Debug — Is 6-day staleness a cron bug?**
- *Hypothesis:* band_resolution_join cron has a path/environment bug (identical pattern to Jun 17 fix: missing `cd /root/Klaus`) preventing settlement ingestion for 6 days. A bug here means disp_ratio 0.817 is measured against a 32d-stale map, potentially producing a false negative on band edge.
- *Data:* systemd cron logs for band_resolution_join; Polymarket settlement timestamps for 51-city markets past 6 days.
- *Time:* 30–60 min (EVOLVE task).
- *Cost:* $0 capital.
- *Success metric:* Cron log shows failures + manual trigger ingests ≥1 settled market + map rebuilt + fresh disp_ratio computed.
- *Decision if yes (bug found):* Fix cron; rebuild isotonic map within 24h; re-evaluate G1 with fresh measurement. If refreshed disp_ratio ≥ 1.10, band re-enable becomes eligible.
- *Decision if no (cron healthy, genuine data absence):* disp_ratio 0.817 is the current true reading. Band stays off with full confidence. Investigate market resolution timing or data sourcing.

**E2: Proxy Dispersion Forensic — Is σ compression real or a measurement artifact?**
- *Hypothesis:* Proxy lane σ = 0.831 (vs baseline 0.994) could result from: (a) genuine seasonal temperature variance compression in July for the 5-city allow-list (chengdu, london, beijing, munich, wuhan), (b) a proxy σ measurement change (e.g., ob_delta windowing), or (c) competitor maker activity tightening bid-ask spreads. Cases (a)/(c) are market-real; case (b) is a measurement bug. If seasonal (a), the fix is expanding to higher-σ cities in summer, not waiting for regime recovery.
- *Data:* Raw temperature range data for the 5 active cities from metar obs (past 14d realized); compare realized σ to proxy lane σ = 0.831.
- *Time:* 1–2 hours (analysis; no code changes).
- *Cost:* $0.
- *Success metric:* Realized σ ≥ 0.994 (baseline) while proxy reads 0.831 → measurement bug; realized σ ≈ 0.831 → compression is real.
- *Decision if measurement bug:* Patch proxy σ calculation; recompute disp_ratio.
- *Decision if real compression (seasonal):* Audit full 51-city σ rankings for July; promote higher-σ cities to BAND_CITY_ALLOW; schedule quarterly seasonal σ review.

**E3: Moscow Sibling Hunt — Which other cities share the METAR oracle vulnerability?**
- *Hypothesis:* Moscow false lockout (−$24.65) was SPECI/interim-ob divergence between two METAR sources. The M1β oracle may carry identical vulnerability in other cities with high SPECI frequency (coastal airports, mountainous terrain, frontal zones). A census before M1β re-enable would prevent the next Moscow-scale loss.
- *Data:* metar_lockout.jsonl + m1_beta_probe.jsonl from shadow (all dates); compute per-city M1β probe events; flag cities where SPECI vs routine METAR routine diverge by >1°F during probe window.
- *Time:* 1–2 hours (analysis only; M1_BETA_PROBE_ENABLED=False → no live risk).
- *Cost:* $0.
- *Success metric:* ≥3 cities identified with Moscow-pattern vulnerability.
- *Decision if siblings found:* Implement cross-validation guard (require 2 concordant sources before triggering lockout) for those cities before M1β re-enable; prioritize low-risk cities for first re-enable.
- *Decision if Moscow was unique:* Re-enable M1β for full city set once wind-down protocol clears; lower risk profile confirmed.

---

## 7. Single Best Action

**Debug and fix the settled-lane cron (band_resolution_join), rebuild the isotonic map, and report a fresh disp_ratio.**

**Why this one:** Every downstream block in the system — G1 AMBIGUOUS, isotonic map 32d stale (calib_monitor S4), proxy σ unanchored to fresh settlements (S5), pair ETA infinite — shares a single root: 6 days of locked settled data. The Jun 17 state_log recorded an identical-pattern bug (`cd /root/Klaus` missing from band_resolution_join cron) that was silently killing the same pipeline. A 6-day gap with no logged cause is the same signature.

If the settled lane is broken and the fix shifts disp_ratio to ≥ 1.10: band re-enable becomes eligible immediately, converting the system from $0/day maker revenue to ~$10/day (exec_audit 7d baseline), plus RECYCLE099 pipeline restores, plus G2b/G2c/G3 accumulation resumes toward eventual READY verdicts. Expected compounding impact: ~$10/day on $136.77 = +7.3%/day when active.

If the cron is working and disp_ratio 0.817 is confirmed accurate: the band stays off with full confidence rather than uncertain ambiguity. The correct follow-on becomes E2 (seasonal σ forensic) to determine whether new cities or a proxy fix can restore the dispersion edge.

**Concrete first step (PROPOSED ACTION PA-1):** EVOLVE task — inspect systemd cron logs for `band_resolution_join`; if failing, apply `cd /root/Klaus` path fix (or equivalent); trigger manual settlement ingest; rebuild isotonic recalibration map; report new disp_ratio to calib_monitor. No trading config changes until human review of the fresh disp_ratio reading.

---

## PROPOSED ACTIONS (human review required before any implementation)

**PA-1 [HIGH PRIORITY]: Debug settled-lane cron + rebuild isotonic map**
- *Evidence:* calib_monitor S4/S5; gatekeeper G1 AMBIGUOUS; Jun 17 precedent (identical bug pattern)
- *Action:* EVOLVE task → inspect band_resolution_join cron logs → fix path if broken → trigger manual settlement ingest → rebuild isotonic map → report fresh disp_ratio
- *Reversible:* Yes (analysis + data ingest; no trading config changes)
- *Gate effect:* If disp_ratio clears ≥ 1.10, band re-enable becomes eligible (still requires pair n gate ~2.8d accumulation + human sign-off)
- *If not done:* System remains in calibration deadlock indefinitely; all collecting gates accumulate at zero rate

**PA-2 [MEDIUM PRIORITY]: Proxy Dispersion Forensic (E2)**
- *Evidence:* calib_monitor S5 (proxy σ 0.831 < baseline 0.994); seasonal timing (July = potential compression month for northern cities)
- *Action:* Run in parallel with PA-1; compare realized city σ to proxy lane σ; if seasonal, expand BAND_CITY_ALLOW to higher-σ cities
- *Reversible:* Yes (analysis only; city-list change is low-risk config tweak)
- *Trigger condition:* Run regardless of PA-1 outcome — provides independent σ measurement

**PA-3 [LOW PRIORITY]: Moscow Sibling Hunt (E3)**
- *Evidence:* state_log Jul 3 19:45 (Moscow −$24.65 false lockout); M1β re-enable is blocked by wind-down but will eventually be reconsidered
- *Action:* Pre-position risk assessment before M1β is re-enabled; identify vulnerable cities; add cross-validation guard for SPECI/METAR divergence
- *Trigger condition:* Run before any discussion of M1β re-enable

**WITHHELD — Requires fresh disp_ratio before discussion:**
- BAND_LIVE=True re-enable: requires disp_ratio ≥ 1.10 (fresh, post PA-1) AND pair n ≥ 40/side (≈2.8d after re-enable) AND intraday freeze clear (21:53Z tonight)
- M1β re-enable: requires wind-down protocol human clearance AND E3 sibling hunt complete

**AUTOMATED (no human action):**
- Sprint Ladder: EVOLVE daily actuator fires at 21:53Z freeze lift if qualifying d+0 market available. Monitor: next shot after freeze lift.

---

*Null finding logged cleanly:* No gate READY today. Correct output is PA-1 diagnostic + data collection. Compounding impact of doing PA-1 within 24h vs waiting: potentially 2.8+ days of band re-enable window foregone if disp_ratio clears on fresh measurement.
