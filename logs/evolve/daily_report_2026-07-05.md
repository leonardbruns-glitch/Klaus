# EVOLVE daily report — 2026-07-05 (21:53 UTC slot; morning slot died on session limit — this run covers the full day)

## Health & equity (first, per kernel)
- `klaus` **active** (restarted 22:07 after deploy, fresh `[WA]`/`[STRUCT-BAND-Q]` cycles verified). No CRASHLOOP flag. Liveness timer healthy.
- **Equity ≈ $222.90** (free USDC $196.83 + Munich ladder shot $26.07 at cost; bankroll tracker $221.48 after auto-correct). **New 30d high-water.** Sprint day 2.6 target $128 → ~+$95 ahead.
- **7d realized (trades.jsonl, ts_close): n=33, −$96.44, PF 0.09.** Honest decomposition: ~−$68 came from paths already cut (favNO tail cut 07-02, standalone YES cut 07-03); the post-cut residual bleed was the PAIR clipped slice, −$26.05 over n=10 — **acted on today (see below)**. Off-ledger positives not in trades.jsonl: RECYCLE099 sells, ladder wins (+$173 lifetime), Moscow lockout redemptions — reflected in the capital number.
- Rails: kernel floor $40 vs equity $222 — clear. Daily-loss halt **verified live** (daily_start reset to $87.17 at UTC midnight; today ended positive on redemptions). Wind-down rail clear (equity IS the HW). Path-cut PF rail: pair slice PF≈0.1 at n=16-18, formally below the n≥20 trigger — handled at mechanism level instead.

## Actions taken (1 live change of 2 allowed; 2nd slot deliberately unspent)
1. **PAIR clip-guard** (commit `365d59d04`, deployed + verified): skip pair posting when the Σ≤0.90 cap forces the NO quote >1¢ below its natural touch. Live-confirmed mechanism (posts today: qn 0.46 vs NO bid 0.55 = 9¢ behind; YES at touch) — "pairs" were degenerating to naked mode-YES posts, the structure cut 07-03. Fill tape 3.5d: 19 YES vs 5 NO fills (~26% co-fill); resolved one-sided YES n=10 WR 10% @ avg 0.46; slice 7d −$28..−$32. Genuine pairs (yb+nb ≤ 0.91) still post; clipped candidates now shadow-logged (`pair_clip_skip`) so the pre-registered `pair_clip_cofill` experiment accrues the counterfactual. This executes that experiment's own `action_if_confirmed` early, on risk grounds (n<40 slice was running live against the standing evidence gate).
2. Bookkeeping (non-capital): gate ledger refreshed from a fresh VPS `band_resolution_join` (n=788 resolved — window-relative; n dropped vs 07-04 because the hot-log window rolled); 4 ledger review-dates closed KEEP-verified (sprint30 equity regex, yes_capture glob, Seattle ladder reconcile, daily-loss halt wiring early-verified); experiments.jsonl updated.

## Actions REJECTED (and why — this list matters)
- **PAIR_FAV_SUM_MAX loosening** (research-audit §2b suggestion to fix "posting collapse"): rejected — it widens the exact naked-YES surface the co-fill data condemns. The posting collapse is the market being efficiently pinned (Σbid≈0.99), not a knob being too tight.
- **Ruin-floor comparator → tracked capital + ratchet $40→~$88** (weekly's spec'd lever): **deferred, not rejected.** The correct comparator needs ladder positions + resolved-pending redemptions, both of which live outside `risk.open_positions` — an evening unattended edit to the risk kernel with a live ladder shot pending is worse than one more day of the protective false-halt seam. Morning slot should do the full design: auto-correct already syncs `capital = cash + engine positions at cost` (main.py:455–492) but misses ladder shots and resolved-pending tokens.
- **Isotonic refit "cron diagnosis"** (research-audit best action): closed as NOT-broken — the cron runs; its guard held legitimately (cal_days 10 < 14 required; OOS candidate Brier worse than live map). The stale dispersion gauge is a calib-monitor windowing/plateau issue, not a VPS cron failure. Gauge unblocks as cal_days accrue (~4d).
- No standalone YES/NO re-enables: disp_ratio trigger not met (gauge stale, last 0.34–0.82 vs 1.10); live favNO stays rail-halted.

## Sprint ladder supervision (STEP 2b — monitor only, principal-authorized)
- Cron healthy (state mtime 22:00; silent-after-cap by design, 2/2 fires today). Settlement integrity OK: Tokyo settled WON +101.25sh (15:40Z); every prior FIRED shot settled <36h. Sleeve arithmetic exact: 8.69 + 97.00 (Seattle) + 101.25 (Tokyo) = **$206.94**.
- Lifetime: 6 fired / 3W (Shanghai, Seattle, Tokyo) / 1L (Munich 07-03) / 1 open — Munich 25°C $26.07 @ 0.47 (fired 08:20, edge −0.049 just inside the −0.05 gate, resolves ~22:00Z tonight).
- Flag (informational): sleeve ($206.94) now ≈ the whole account's free cash — the ladder's own $45/shot cap and $20 reserve check remain the effective bounds. No tuning warranted (zero-candidate days: none; resolved n=4 < 10 for gate-quality review).

## Experiments status
- `pair_clip_cofill` → ACTED-EARLY-SHADOW (see action 1); counterfactual accrual continues, review 07-19 stands.
- `pair_fav_sum090` → still COLLECTING-LIVE but ~dormant under the guard until books loosen to ≤0.91. Merges remain the only verified +EV pair mechanic (+$2.51/7d, n=5 records).
- `yes_capture_shadow`: 07-05 markout check — 92% adverse (med −2.9¢): the +103–126% would-post ROI is winner's-curse; stays informational.
- `band_dial_timeseries`: 24/90 days. `nhc_count_lock`: watchlist (Aug season). Others unchanged (THERMO/PEAKSCALP/M1β-thin REJECTED; BASKET_EXIT VOID).

## Standing risks
1. **Actuator slot reliability**: 3/11 daily slots have completed since 07-02 (session limits). Backlog check worked today, but a two-slot gap plus a losing streak would go unattended ~24h. (ESCALATIONS item stands: stagger slots / interactive review.)
2. **Ruin-floor seam** (protective): tracker can false-dip below $40 intraday on ladder fires while true equity is 5× that — engine pauses new posts until auto-correct. Fix spec'd for the morning slot.
3. **Equity concentration**: gains are ladder coin-flips (P(3+ of 4 @ ~0.45) ≈ 27%) + one lockout window — variance, not edge. Engine edge/turn remains ≈ 0; the honest compounding engine is still missing.
4. Calib dispersion gauge stale day 3 → band re-enable tree blocked until isotonic cal_days reach 14 (~4d).
