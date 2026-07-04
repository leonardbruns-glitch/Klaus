# EVOLVE daily report — 2026-07-04 (21:53 UTC run)

**First completed daily actuator run ever.** The 07-03 and 07-04 11:23/21:53 slots all
died on Claude session limits before doing any work (`run_daily_*.log`: "You've hit
your session limit", both primary and fallback model). This run is the loop's first
real execution; `ledger.jsonl` / `experiments.jsonl` / this report did not exist
before tonight.

## Health & equity
- `klaus` **active**; restarted 22:10 for tonight's deploy, verified (see below).
- **Equity $125.56** = cash $74.45 (keeper-logged free USDC) + positions at mark
  $51.11 (cost $56.20: Seattle ladder shot $43.74 + three PAIR_FAV d+1 YES legs
  ~$12.46). bankroll.json capital $100.94 excludes the ladder position (separate
  process) — known accounting seam, documented in the ledger.
- **7d realized (engine, trades.jsonl): −$73.20, PF 0.13, n=29** — the bleed is
  06-27→07-02 vintage from paths already cut (standalone YES band −45% tape → OFF
  07-03; favNO rail-halted 07-02). Post-cut days: 07-03 **+$1.16**, 07-04 **−$3.96**
  engine-side. No single path has ≥20 resolved in 7d → the PF<0.8 path-cut rail has
  no live target left.
- **Rails:** kernel floor $40 clear. Daily loss: today is net POSITIVE (+$63.50
  ladder win − $3.96 engine). Wind-down rail state (equity < 50% of trailing-30d
  high-water ~$250 bankroll-proxy) **persists** — the prescribed response (full
  attribution review + path cuts) was executed 07-03; accordingly tonight was run as
  a **no-optimization day**: the only live changes are tightens.
- ⚠ The 30d high-water itself is a bankroll-proxy figure inflated by marks that later
  resolved to $0 (07-03 audit); honest realized HW is lower but not precisely
  reconstructible. Conservative reading (rail breached) applied.

## Sprint-30 (day 1.1)
- **Ahead of trajectory: equity $125.56 vs target ~$101.3 → gap +$24.3.** Cause: the
  Shanghai ladder shot won (108.5 sh @ 0.40, +$63.50 net, $108.50 redeemed 16:33Z).
  This is ONE win at p≈ask≈0.40 — luck, not evidence of edge. Honest P($10k/30d)
  remains ~1–3% as logged 07-03.
- Ladder supervision (STEP 2b): cron healthy every 10 min (post-cap silence is by
  design — settlement checks continue; state file mtime advances). 2/2 fires used
  today. Seattle shot open (fired 18:10Z, ask 0.45, resolves ~07:00Z 07-05).
  **Settlement-integrity action:** ladder had recorded Seattle as 87.55 sh/$45.00
  from the POST-response fallback (`fetch_order_fills` returned no data); data-api
  ground truth is **97.00 sh / $43.74** → state reconciled (sleeve 78.50→79.76) so a
  win credits correctly.
- No gate tuning needed (candidates found and fired 2/2); no re-seed needed
  (sleeve $79.76).

## Actions taken (live-effect: 2/2 cap, both protective)
1. **M1β thin-margin REVERT 0.2→0.5°C** (`MIN_DEPTH_C` + `FATEDGE_MIN_DEPTH_C`,
   commit `2813daa1e`). Evidence: slice stalled 22d at n=31 WR 74.2% ROI −0.6% CI95
   [−20.6,+24.4]; the 06-09 widening was an n=24-28 override that never validated.
   $0 impact today — lockout capacity is zero. Review 07-18.
2. **Armed the dead 14% intraday daily-loss halt** (same commit).
   `maybe_reset_daily()` had zero callers and `last_utc_day` was never persisted, so
   `daily_start_capital` froze at $15.95 — the halt could never trip. Now wired into
   the 10s heartbeat. Expect a `DAILY_RESET` line at UTC midnight; review 07-06.
   Closes the 07-02 ESCALATIONS open item.

## Sensor/bookkeeping fixes (not counted vs cap)
- `ops/sprint30_equity.py`: cash regex matched a line bot.log never emits → every
  nightly row would be `cash=null`. Now parses the keeper's
  "Polymarket USDC balance (actual): $X". Verified: 74.4489.
- `analysis/weather/band_yes_capture_join.py`: relative glob + cron cwd=/root →
  "0 snapshots" for 3 days while the shadow logged 30-85 rows/day. Absolute path;
  verified 829 snapshots / 726 resolved. (The experiment was never dead — only its
  analyzer was blind. Same bug class as the 06-17 band_resolution_join cron fix.)
- Sprint-ladder state reconcile (above).
- Initialized `logs/evolve/ledger.jsonl`, `experiments.jsonl`,
  `gate_ledger_latest.md` (fresh VPS resolution join: n=1,067 resolved).

## Actions REJECTED (and the gate that stopped them)
- **Raise MAKER_CASH_FRAC 0.40→0.65** (research-audit item A, to unstarve PAIR_FAV):
  REJECTED — param set 07-03 20:05 (<72h anti-thrash freeze), deliberately, to
  protect the ladder's $20 reserve; and it's moot while sum_gate rejects all pair
  candidates (today's only pair cand failed Σ≤0.90 — market condition, not config).
  Re-examine after the freeze (07-06+) if pair candidates start clearing the Σ gate.
- **Any band re-enable / breadth increase**: REJECTED — disp_ratio 0.34–0.82 vs 1.10
  trigger, 7+ consecutive days; live tape −45% since 06-26; badatmath himself
  −$11.3k/7d in the same structure. Standing condition unchanged.
- **Acting on the YES-CAPTURE join (+126% ROI 0.30-0.45 d+2, n=398)**: REJECTED —
  would-post join, conditional-on-fill; the identical join class showed +8% while
  live fills realized −4.9%/−45%. Charter winner's-curse rule: maker-book/would-post
  data never justifies a live change. Needs a live-fill validation design first.
- **THERMO re-enable at any size**: REJECTED permanently (n=125 resolution join, EV
  −9..+2%/share ≈ 0) — formalized as KILLED in experiments.jsonl.

## Experiments (full inventory now in experiments.jsonl)
- COLLECTING: yes_capture_shadow (726 resolved, analyzer restored), band_dial
  (23/90 days), pair_fav Σ≤0.90 (9/side resolved — the only live engine flow).
- KILLED: peakscalp (07-03, n=427), thermo (n=125), m1β thin-margin (tonight),
  basket_exit (06-22, VOID).
- LIVE outside charter: sprint_ladder (principal-authorized, monitor-only).
- WATCHLIST: NHC named-storm count-locks (design + pre-register before Aug).

## Standing risks
1. **The actuator's own schedule is unreliable** — 4 of 5 daily slots so far died on
   Claude session limits before doing anything. If this recurs, the loop is blind on
   most days. Logged to ESCALATIONS (systemd units are kernel-protected; an
   interactive session should consider staggering slots away from limit-reset times
   or a cheaper fallback model).
2. Engine capital allocation: PAIR_FAV starved by Σ-gate (market) + $16-30 maker pool
   (deliberate). Turns/day ≈ 0 on the engine; RECYCLE099 has nothing new to recycle
   soon. Acceptable in survival posture; revisit with the 07-06 freeze expiry.
3. Ladder variance: modal outcome remains sleeve-loss within days; today's +$24
   cushion is one coin-flip. The $20 reserve + 2/day cap are the bounds.
4. bankroll.json vs ladder accounting seam (ladder positions invisible to engine
   capital) — equity must always be computed as keeper-cash + data-api positions,
   as done here and now nightly by the fixed sprint30_equity.py.
