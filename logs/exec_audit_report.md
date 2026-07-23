# Execution & Markout Audit — 2026-07-23

**Snapshot:** 2026-07-23T06:59:46Z | **System:** `klaus systemd: active` | **Audit branch:** `claude/find-lag-parameter-rFQ0N`

**Pre-flight:** Snapshot age ≤ 2h (mirror runs every 15 min, last push confirms active). System status present and active. Proceeding.

**Critical context:** `BAND_LIVE=False` since 2026-07-06 (equity drawdown trigger: $21.50 current vs $108.35 30d high-water). `BAND_NO_ENABLED=False` since 2026-07-02. All six pipeline sections reflect a live-posting idle state. Shadow mode continues running.

---

## Section 1 — Fill Tape (24h + 7d)

| Window | Fills (count) | $ Filled | YES | NO |
|--------|--------------|---------|-----|-----|
| 24h    | 0            | $0.00   | 0   | 0   |
| 7d     | 0            | $0.00   | 0   | 0   |

**By price band:** No data (no fills).  
**By city:** No data.  
**Median time-to-fill:** N/A.  
**Fill rate:** 0 filled / 0 posted = N/A.

Source: `maker_resting_state.json = {}`, `band_posted_state.json` last entry 2026-07-06, `maker_fills_recent.log` unreadable via MCP (file encoding/size issue — content confirmed empty via resting state and posted state cross-check). Last confirmed fill predates current 7d window (band was halted 2026-07-06, 17 days ago).

---

## Section 2 — NO-Parity Monitor

| Date       | New YES posts | New NO posts | NO share | Alert? |
|------------|--------------|--------------|----------|--------|
| 2026-07-23 | 0            | 0            | N/A      | —      |
| 2026-07-22 | 0            | 0            | N/A      | —      |
| (last 7d)  | 0            | 0            | N/A      | —      |

**Shadow fires (not live posts) for context:**
- 2026-07-22 `band_struct_lite`: 9 shadow fires, all YES-side (59 `yes_capture_shadow` records, 0 NO captures). `BAND_NO_ENABLED=False` — NO shadow firing also suppressed by design.
- 2026-07-23 (to 06:59 UTC): same pattern — all `md_shadow`, `live=False`, NO-side absent.

**NO-starvation fix status:** Fix was committed 2026-06-12. Unverifiable on live data since `BAND_NO_ENABLED` was explicitly set to `False` 2026-07-02 (independent shutdown). Fix correctness cannot be confirmed or denied from shadow data alone; requires `BAND_NO_ENABLED=True` to generate signal.

---

## Section 3 — Queue Health

No `[STRUCT-BAND-Q]` lines exist (no live band cycles running). `BAND_LIVE=False` means zero live quoting — no book fetch cycles, no cash_preskip, no books-used stats to report.

**Shadow engine activity (from `shadow_summary.json`):**

| Date       | thermo_maker rows | maker_shadow rows | maker_flow rows |
|------------|------------------|------------------|----------------|
| 2026-07-18 | 24,956           | 87,175           | 284,464        |
| 2026-07-19 | 30,602           | 109,087          | 264,483        |
| 2026-07-20 | 35,253           | 119,548          | 124,699        |
| 2026-07-21 | 37,140           | 105,754          | 267,292        |
| 2026-07-22 | 22,778           | 114,015          | 279,264        |
| 2026-07-23 | 6,538*           | 26,037*          | 44,005*        |

*Partial day to 06:59 UTC.

Shadow pricing is healthy and active — the engine is evaluating markets and generating shadow quote data. No fetch-starvation signal (book rows consistent across days). The shadow system is ready to post if `BAND_LIVE` is re-enabled.

**d+2 shadow fires today (from `band_struct_lite.jsonl`):**
Seoul (sum_ask=0.775, 4 legs), Tokyo (sum_ask=0.77, 5 legs), Chengdu (sum_ask=0.845, 5 legs), Taipei (sum_ask=0.82, 4 legs) — all `live=False`. d+1 markets all blocked by `sum_gate` (Σask 0.87–1.01, above BAND_SUM_MAX=0.85). d+0 markets mostly `converged` (mode_ask 0.33–0.56) or `no_band`.

---

## Section 4 — Resolution Markout (Fill Quality)

**n = 0 filled legs in 7d window.** No markout analysis possible.

Last fills occurred on or before 2026-07-06 (17 days ago). Resolution data for those fills would now be fully settled, but fill-side data is not in the current 7d `maker_fills_recent.log` window and the `band_struct_lite` archive does not extend to pre-shutdown dates in the accessible mirror.

Winner's-curse test: **cannot run** (n=0). No conclusion on adverse selection.

---

## Section 5 — Dead-Quote Reclaim

| Metric | Value |
|--------|-------|
| `maker_resting_state.json` entries | 0 |
| Quotes > 24h old | 0 |
| Quotes > 48h old | 0 |
| Reaped dead entries (7d log) | 0 |
| $ freed by reclaim | $0.00 |

Zero resting quotes — no open positions, no dead-quote accumulation. Reclaim engine has nothing to act on.

---

## Section 6 — Cash Velocity

| Metric | Value | Badatmath benchmark |
|--------|-------|---------------------|
| Capital (bankroll.json) | $21.495 | — |
| Resting $ | $0.00 | — |
| Fills $ (24h) | $0.00 | — |
| Turns/day | 0.00 | ~1.0 |
| Total PnL (inception) | −$75.40 | — |
| Consecutive wins | 0 | — |

Capital note: `$21.495` reflects wallet state as of snapshot; user manual sells and withdrawals are not tracked here — do not infer ruin or session PnL from this figure alone.

Velocity is structurally zero. The gap vs badatmath's ~1.0 turn/day benchmark is entirely explained by `BAND_LIVE=False`. There is no cash-deployment pathology to diagnose at this time.

---

## ALERTS

*(Only pre-registered alert conditions that actually fired are listed here.)*

**None.** All alert thresholds (NO-share < 25%, books pinned at 80, cash_preskip sustained > 200 with posted=0, quotes > 48h, markout winner's-curse) require live posting activity to evaluate. None fired.

---

## 3-Line Summary

- **Fills/day:** 0 — BAND_LIVE=False since 2026-07-06 (17 days idle); no posts, no fills, no resting orders.
- **NO-share:** N/A — no live posts on any day in the 7d window; shadow fires are YES-only (BAND_NO_ENABLED=False by design).
- **Binding execution constraint:** `BAND_LIVE=False` (equity drawdown trigger: $21.50 current vs $108.35 watermark). Shadow engine is healthy and pricing d+2 bands with valid sum_ask (0.77–0.85). The constraint is a capital/strategy gate, not an execution defect.
