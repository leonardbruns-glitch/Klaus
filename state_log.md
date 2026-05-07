# Klaus State Log

Session-altering decisions only. Read last 10 entries at the start of every session before any analysis.
Format: `YYYY-MM-DD HH:MM UTC | SYSTEM/ASSET | exact change | reason + evidence`

## 2026-05-07 ~11:XX UTC | ROBUST STACK / ALL | Ship Stage 1 + partial Stage 2 + Stage 3 shadow log | user-instructed Tier 2. (1) Ask ceiling 0.92→0.88 (main.py:2254); (2) Imbalance floor 0.30→0.35 with DOWN ceiling unchanged at 0.655, UP at 0.70 (main.py:2313); (3) tok_d30 sandwich [5,60) added before deadzone (main.py:~2616); (4) Stage 3 shadow log: trades passing all gates but with snap60_eff<25 emit `[SIGNAL_PASS][STAGE_3_REJECT]` for 48h tracking — Snap60 25% floor NOT enforced, Tier-C deferred (no spec yet).

## 2026-05-07 ~11:XX UTC | GATE / ETH UP | ETH UP G1 skip if Bnc60m > 0% (Tier 2, user override) | Forensic on imb-immune cells: ETH UP bnc60m≥0% n=38 avg -$1.39, bnc60m<0% n=15 avg +$0.95. cor%=57-64% across imb thresholds (not a base-rate issue) — orthogonal regime-selection problem. Symmetric to LATE DOWN gate. Mirrored in main.py just below G1_down_late_skip. Re-evaluate at n≥100 macro era. BTC DOWN deferred (different failure mode: inverted OB signal + sub-50% base rate; imb-immune AND bnc-immune).

## 2026-05-07 11:XX UTC | ENTRY / DOWN-LATE | G1 gate added: skip DOWN if Bnc60m > 0% in LATE session (18-24 UTC) | n=42 macro era, in-sample +$17.60 vs ungated -$2.92; load-bearing bucket [0,+0.25%) n=5 with ~$15 of edge from 1 BOND_EXPIRED_UNSOLD outlier; user override of n>=40 rule explicit "my call"; ASIA/LDN/US DOWN remain ungated; re-eval at n>=40 in [0,+0.25%) bucket alone

## 2026-05-07 11:XX UTC | SIZING / DOWN-LDN | rollback DOWN×LDN 0.5x → 1.0x | original n=171 evidence (avg -$0.47) was contaminated by pre-May-5 era (n=153 -$87.99); May 5+ era n=18 WR=83.3% +$7.99 +$0.44/trade — cell is profitable, 0.5x cut was costing ~$2/day; ALL DOWN sessions now 1.0x; era split: Apr24-May4 n=704 -$92.22 vs May5-May6 n=82 +$11.98

## 2026-05-07 10:XX UTC | SIZING / ALL | session×direction stake multipliers added | UP×ASIA 0.5x, UP×LDN 1.0x, UP×US 1.5x, UP×LATE 0.3x; DOWN×ASIA/US/LATE 1.0x, DOWN×LDN 0.5x; per-session pre-May7 evidence n>=151 deploy-grade; in-sample backtest May 5-7 -$210→+$29 (+$239 swing, ~50-70% expected OOS); applied AFTER snap30 blow-off cut, floor $5

## 2026-05-07 10:XX UTC | ENTRY / UP | G1 gate: per-session bands replace [-0.3,+1.5] universal | ASIA [-0.05,+0.25], LDN [0,+0.30], US [0,+0.30], LATE [+0.05,+0.25]; in-sample joint optimum on macro era n=145 pre-May7 + n=11 May7; ceiling tightening +1.50→+0.30 is dominant lever (UP avg -$0.37→+$0.18); on May 7 alone blocks 4 of 6 catastrophic UP losers

## 2026-05-06 21:XX UTC | SIZING / ALL | base_stake raised $20→$30; equity tiers floored at base_stake | user directive; May 6 PASS gates net=$73.72 WR=97.2% n=36; Tier 2 (14%=$25) is currently a no-op (below $30 base) until equity>$214; Tier 1 (18%=$32) still adds ~$2 boost

## 2026-05-06 20:XX UTC | SIZING / ALL | equity-pct stake tiers added | Tier 1: snap60≥50% → 18% of equity; Tier 2: snap60≥20%+rem≥75s → 14% of equity; base_stake used otherwise; blow-off gate still applies after; user-authorised May 6

## 2026-05-06 19:XX UTC | ENTRY / ETH | snap60 floor raised to 15% (both dirs) | ETH [12,14) WR=0% pnl=-$39.08 (n=2): T03742 -$19.84 H20, T03746 -$19.24 H22; both pass all other gates; [15,20) loss already blocked by H12:30 25% gate; 1 FP T03760 +$2.67 at 14.86%; Tier 2 user-authorised; re-eval at n≥40

## 2026-05-06 18:XX UTC | ENTRY / ALL | snap30 floor raised 10% → 10.5% | [10,10.5) bucket since May5 06:00: WR=33% pnl=-$34.70 (n=3); both BTC DEAD_DRIFT losses T03785 -$19.65 and T03798 -$16.95 had snap30_eff=10.39%; 1 FP ETH DEAD_DRIFT +$1.89; [10.5,11) clean (1W 0L); Tier 2 user-authorised; re-eval at n≥40

## 2026-05-06 14:XX UTC | ENTRY / ALL | snap60 floor raised to 25% during 12:30–13:30 UTC | 5/5 H12:30–13:30 losses over 2 days had snap60<25% (T03720 18.6%, T03722 0%, T03783 19.4%, T03785 16.4%; T03784 at 31.8% was execution bug not signal); recurring neg-risk lock + BOND_EXPIRED_UNSOLD failures at this window make weak entries unacceptably risky at $20 stake; Tier 2 user-authorised; re-eval at n≥100

## 2026-05-06 | ENTRY / DOWN | imb ceiling: 0.70 → 0.655 for YES DOWN only | YES DOWN [0.655,0.70) n=39 net=-$6.67; YES UP same range net=+$21.32 (kept at 0.70); direction-specific via _imb_ceil; Tier 2 user-authorised; re-eval at n≥100

## 2026-05-06 | ENTRY / DOWN | snap60 floor: 12% → 13% for YES DOWN only | YES DOWN [12,13) n=32 net=-$11.74; YES UP same range net=+$18.85 (kept at 12%); direction-specific via _snap60_floor; Tier 2 user-authorised; re-eval at n≥100

## 2026-05-06 | ENTRY / ALL | snap30 ceiling: 120% → 80% (universal) | [80,120) bot-wide net -$24.71: DOWN saves $29.67, UP costs only $4.96; safe to apply universally; Tier 2 user-authorised; re-eval at n≥100

## 2026-05-05 | ENTRY / ETH | eth_sust_skip gate added: block ETH when tok_d30≤0.5% OR tok_d60≤0.5% | forensic audit 06:00–14:00 UTC: n=13 ETH, 0 winners had sust=False; T03710_ETH (-$4.57) entered on tok_d30=0% bypassing eth_tokd30_skip via 0.0 exemption; Tier 2 user-authorised

## 2026-05-05 | ENTRY / ALL | rem>90s entries blocked — TERMINAL zone only (25–90s) | user instruction

---

## 2026-04-27 | ENTRY / ALL | ask range lowered 0.84→0.80 | 0.82–0.84 PF=1.03 (n=114); 0.80–0.82 raw PF=0.87 (n=115) wick-adj PF=1.24 expected with wick filter

## 2026-04-27 | RISK / ALL | OB imbalance gate set at ≥0.20 | imb≥0.20: PF=1.27 Net=+$24.18 (n=234); imb<0.20 trades lost $22.51

## 2026-04-27 | RISK / ALL | BOND stake cap set at $4.00 / min 5 shares floor | proving T-10s crash risk before scaling; prior cap $10

## 2026-04-28 13:08 UTC | HOURS / ALL | blocked H02, H05, H21 | H02 PF=0.19, H05 PF=0.21 (user override of n<100 rule, n was sufficient directionally)

## 2026-04-28 15:46 UTC | EXIT / ALL | BC wick window extended 10s→18s for late-hold trades (hold>35s) | directional: late holds more likely genuine crash; no n≥100 evidence

## 2026-04-28 19:41 UTC | ENTRY / ALL | adversarial audit: removed flat-drift gate (|drift|<0.02), binance both-rising gate, snap30 in-hold abort; unblocked H21 | gates added below n=100; cross-strategy contamination (TREND→TERMINAL); H21 in-range WR=65% PF=1.19 (n=46) positive

## 2026-04-28 19:41 UTC | EXIT / ALL | BC wick reset: fast/mid hold buckets back to 10s (late stays 18s) | part of adversarial audit rollback; depth_ratio analysis not yet run

## 2026-04-29 05:15 UTC | HOURS / ALL | blocked H03 | WR=14.3% Net=-$6.77 (n=10, Apr24+Apr29, 0.80–0.88 range)

## 2026-04-29 10:01 UTC | EXIT / ALL | BC wick fast/mid 10s→15s (late stays 18s) | post-adversarial-audit: 34% BC exits are flash crashes recoverable within 15s

## 2026-04-29 10:40 UTC | EXIT / ALL | BC wick replaced: depth-aware (depth_ratio=min_price/entry_price); <0.60→wait=0s, 0.60–0.77→wait=15s, >0.77→wait=20s; bypass threshold 15s→10s remaining | depth_ratio is actual discriminator (n=70 matched pairs); bypass 79% FP at 10–15s remaining

## 2026-04-29 12:41 UTC | EXIT / ALL | BOND_CATASTROPHIC SL fully disabled (_sl_threshold=-1.0) | 85% FP rate (n=127 Apr28–29); actual pnl -$95 vs +$62 counterfactual if held; break-even FP rate 60.4%

## 2026-04-29 13:08 UTC | ENTRY / ALL | snap60 pre-entry gate: skip if term_pre_snap_60s < 0.0 (token falling in 60s pre-entry window) | WR=32.5% when snap60<0 vs 91.9% when snap60>0 (n from Apr28–29 session analysis)

## 2026-04-29 13:33 UTC | INFRA / ALL | window outcome capture fixed: concurrent _capture_resolution() task fires at T+5s post-window; exit_reason now recorded in resolution records | old code ran at T+120s; TIME_EXIT token gone by then; only 6 time-exit resolution records existed historically

## 2026-04-29 13:52 UTC | HOURS / SOL | blocked SOL H06 (06:00–06:29 UTC) | WR=29% (n=17); $1.50 reduced stake not feasible (CLOB 5-share min ≈$4.00 at ask 0.80); block is equivalent risk reduction

## 2026-04-29 14:XX UTC | EXIT / ALL | TIME_EXIT moved T-2s→T-4s (bond_exit_sec 2→4) | TIME_EXIT WR 74–90% vs DEADLINE WR 88–97% across all assets Apr28+; DEADLINE at T-3s was firing before T-2s timer, making it primary exit; T-4s makes TIME_EXIT primary and avoids snap events; DEADLINE remains safety net at T-3s

## 2026-04-29 14:XX UTC | INFRA / ALL | Fix cancel AttributeError: cancel→cancel_orders (py_clob_client_v2); SELL cancel-race REST-first recovery | py_clob_client_v2 removed cancel(), renamed to cancel_orders([id]); every resting SELL was hitting cancel-race path; secondary bug: pop_fill_for_token returned stale BUY fill → exit_price=entry_price (observed T02669_BTC: logged exit=0.81, actual PM=0.46, real loss ~$1.79 vs logged -$0.04)

## 2026-04-29 15:XX UTC | EXIT / ALL | BC disable fixed: _sl_threshold -1.0→-2.0 | -1.0 fired at bond_move=-1.0 (price→0.000); T02682_ETH flash-crashed to 0 at T-4.6s, bypass fired, exited at 0.010, resolved YES at 0.99 — $4.90 FP loss; -2.0 is unreachable (max loss=-1.0), BC truly disabled including bypass path

## 2026-04-29 16:XX UTC | EXIT / ALL | PROFIT_TARGET early exit added: sell when bid ≥ 0.99, min 0.98 execution guaranteed | cascade_sell starts at 0.99×bid=0.9801; PROFIT_REASONS→allow_stepdown=False so if bid has moved below limit the order rests and Guard 1 returns clean (no sub-0.98 fill); fires before BOND_DEADLINE/TIME_EXIT

## 2026-04-29 16:XX UTC | KILL_SWITCH / ALL | Ruin floor override: user instructed no halt at capital=$45.91 (<$50 floor) | explicit user decision; bot continues running

## 2026-04-29 16:XX UTC | ENTRY / ALL | Ask-history gate added: skip if term_ask_stale_s ≥ 999.0 | T02684 (-$1.52) and T02685 (-$4.27) entered with no scan-loop history; snap60/snap30 defaulted to 0.0 (neutral), bypassing both gates; gate blocks blind entries directly

## 2026-04-29 18:XX UTC | ENTRY / ALL | 3 snap gates added: snap60<5% skip; snap30>300% skip; snap60>150%+mage<3s skip | 5h analysis (n=54 active): snap60 0-5% bucket WR=50% net=-$4.32; snap30>300% caught SOL blow-off (0 FP, highest win s30=235%); snap60>150%+fresh caught 2 reversals (1 FP: 14:39 ETH +$0.60); combined WR 68.5%→76.2% net +$6.52; n<100 per bucket — user-authorised Tier 2

## 2026-04-29 19:XX UTC | ENTRY / ALL | snap60 gate raised 5%→12% | 2-day sim (n=255 Apr28-29): snap60 5-12% bucket WR=55% net negative; raising threshold drops these borderline entries; user-authorised Tier 2

## 2026-04-29 19:XX UTC | ENTRY / ALL | snap60 spike gate stale threshold 3s→5s | T02722 BTC (-$2.43): snap60=171% stale=4.1s slipped through 3s gate; same pumped+stale pattern gate targets; n=1 trigger

## 2026-05-02 | ENTRY / ALL | snap60 ≥ 120% unconditional block (replaces prior >150%+fresh gate) | WR=62.5% net+$8.69 sim (n=16); catches T02723_SOL -$6.88, T02572_BTC -$3.23; prior >150%+fresh is strict subset — removed; user-authorised Tier 2

## 2026-05-02 | ENTRY / ETH | ETH tok_delta_30s ≥ 100% block | WR=42.9% lift=5.7x (n=7); ETH 30s overextension; BTC/SOL same zone WR=100% → ETH-specific only; user-authorised Tier 2

## 2026-05-02 | ENTRY / ALL | snap30 gate overhauled: 2 new gates | (1) snap30<0 unconditional block: n=144 net=-$7.50, removed depth<200 condition (144 trades bypassed it); (2) snap30 [5,10%) block: decel zone n=43 WR=67% but avg_loss=-$2.39 net=-$6.68 (T03199_BTC -$9.72 was 7.46%); 0-5% (n=49 net=+$19.78) and 10%+ both kept

## 2026-05-02 | EXIT / ALL | Scale-in guard: block if bond_remaining < 45s | T03169_BTC -$20.86: entered rem=34s, scale-in fired at rem=13s doubling position to $19.96, PROFIT_TARGET sell failed (CLOB error), resolved NO; 45s ensures time to exit full position before window

## 2026-05-02 | LOGGING / ALL | BOND_EXPIRED_UNSOLD window_outcome_price fixed | was always 0.0 (PM API shows 0 for expired tokens); now passes 1.0 when bid≥0.80 at close (YES settlement), 0.0 when bid<0.05 (NO)

## 2026-05-02 | ENTRY / BTC | BTC snap60 [20,30%) gate APPLIED then REVERTED | strict re-eval: REJECT — sub-bucket inverts between BTC/ETH (regime flip), bootstrap CI crosses zero (P(neg)=85%), n=18<30, jackknife flips positive on 20% removal; classified as regime-boundary overfit; monitor at n≥40

## 2026-04-29 19:XX UTC | ENTRY / SOL | SOL spread≤3% gate added | spread 1-2% bucket WR=73% net=+$9.18 dir_acc=92% (n=26); spread>3% net=-$12.17 drag; snap+spread≤3 only profitable SOL combo: n=22 WR=64% net=+$2.47 sim=+$2.27; user-authorised Tier 2

## 2026-04-29 19:XX UTC | EXIT / ALL | PROFIT_TARGET changed fixed 0.99→relative entry×1.12 | 2-day sim: +12% TP converts 13 big losses to wins (+$21.60) vs capping 78 winners earlier (-$18.39); net +$7.26 vs actual exits; avg max_fav of losers=8.4% (not used — too early), winners avg=16.6%; 12% is sweet spot

## 2026-04-29 19:XX UTC | RISK / ALL | BOND stake cap raised $4→$10 | user instruction; capital $32.45 (below $50 ruin floor but user-overridden); 3-asset worst-case = -$30 on one bad window

## 2026-04-30 05:02 UTC | EXIT / ALL | PROFIT_TARGET cap added: min(entry×1.12, 0.99) | entry×1.12 exceeds 1.0 for fills above ep~0.884 (slippage entries); T02757_ETH held 30s at bid=0.99 without TP firing, hit flash crash at T-4s (-$4.37); cap ensures TP is always reachable

## 2026-04-30 06:XX UTC | ENTRY / ALL | d5s>25% gate added: skip if token rose >25% in 5s before entry | n=49 Apr28+: WR=43% PF=0.47 net=-$18.4; rest WR=66% PF=1.15 net=+$25.7; micro blow-off pattern; user-authorised Tier 2

## 2026-04-30 08:XX UTC | ENTRY / ALL | Ask range widened 0.80–0.88 → 0.70–0.92 | user instruction; TP entry×1.12 cap 0.99 unchanged (0.70×1.12=0.784 reachable); new buckets live, no prior evidence

## 2026-04-30 07:XX UTC | EXIT / ALL | Loss-exit window T-10s→T-5s: poll 0.5s, exit if bid < entry_price | unconditional T-10 was -$29.09 vs T-4s (n=235 Apr28-30): winners lost -$34.94, losers saved +$17.42; conditional version preserves winner upside while catching crashes for losing positions; T-4s remains unconditional fallback

## 2026-04-30 08:XX UTC | EXIT / ALL | PAE added: exit if bid ≥5% below entry for 20 continuous seconds | BC disabled; t_adv>20s trades WR=29% net=-$805 (n=623); tokens stuck below entry 20s+ resolve against us 70%+ of the time; clock resets on recovery above -5%; bypasses inside T-10s window (existing conditional exit handles that)

## 2026-04-30 ~14:XX UTC | ENTRY GATE / ALL | Stale ask threshold tightened 999s → 4s | 3-day sample: stale>=4s net=-$35.07 (n=72 blocked); dominant losers T02829 (-$9.94, stale=5.3s) and T02814 (-$7.22, stale=6.8s) in 4–7s zone; 7-10s WR=100% is n=12 (noise); 3-4s bucket (WR=92.3%) preserved

## 2026-04-30 ~14:XX UTC | DATA / ALL | XP tracking fixed: _capture_resolution() now patches trades.jsonl with wop/entered_correctly on resolution; 860 historical trades backfilled from post_exit.jsonl

## 2026-04-30 ~14:XX UTC | DATA / BTC | T02829 corrected: PAE fill at 0.83 was ghost order during spike, position never closed; wop=0.01, net_pnl corrected -$0.10→-$9.94, capital_after 53.52→43.68

## 2026-05-01 ~21:XX UTC | EXIT / ALL | PROFIT_TARGET disabled | costs -$34.18 vs WOP in 48h sim; YES windows walk to 0.99 at resolution — early exit at 0.98 caps gain for no benefit; primary exit now WINDOW_OUTCOME + PAE only

## 2026-05-01 ~21:XX UTC | HOURS / ALL | _BLOCKED_HOURS {0,2,3,4,5,6,7,17,19,23}; H12+H13 unblocked, H04+H06+H07+H17+H19 added | 48h WOP+PAE sim: H12/H13 were blocked on contaminated all-trades data (TERMINAL-era PF=2.07/0.88); H04/H06/H07/H17/H19 irredeemable — no gate produces PF≥1; sub-hour partial rules for these hours removed (superseded)

## 2026-05-02 | BUG / ALL | BOND_EXPIRED_UNSOLD stale-bid bug fixed: _g1_price forced to 0.0 | OB bid 5s post-expiry = our own resting PROFIT_TARGET at 0.99, not PM settlement; all EXPIRED_UNSOLD are NO outcomes; 4 today's fake-win trades corrected (-$37.13); window_outcome_price=0.0 hardcoded

## 2026-05-02 | CAPITAL / ALL | Bankroll reset to $24.00 to match PM balance | deposit ~$45 after -$37.13 fake-win correction brought logged capital to -$15.49; PM balance $24 is authoritative; daily_start_capital set to $24.00

## 2026-05-02 | SIGNAL / ALL | snap30 ≥120% performance: n=33 WR=66.7% net=-$8.18 (Tier 2) | sweet spot confirmed [10,120%); above 120% WR holds but avg-loss > avg-win (blow-off reversal); monitor at n≥100 before adding upper gate

## 2026-05-02 | BUG / ALL | NEG_RISK_LOCK exit failure fixed (execution/order_manager.py) | 17/21 May2 stuck trades caused by: BTC fill locks SOL token as "matched orders" in neg-risk pool; SOL sell retried immediately × 10, all fail in <2s before ~10s settlement clears; fix: detect "matched orders" in CLOB error, sleep 2s, retry; prior "regime halt" proposal was wrong — 84% of stuck losses were this single execution bug, not market regime

## 2026-05-02 | LOGGING / ALL | EXTERNALLY_SOLD exit_price corrected at resolution | when cascade_sell fails with balance=0 and no fills confirmed, exit_price was recorded as live bid (inaccurate); now flagged exit_price_uncertain=True and _capture_resolution overwrites exit_price/net_pnl/bankroll with PM resolution price when known

## 2026-05-03 ~06:XX UTC | ENTRY / ALL | Min ask raised 0.75→0.80 | User instruction. Floor was raised to 0.75 on 2026-05-02 but CLAUDE.md not updated (showed 0.70). Now 0.80.

## 2026-05-03 ~06:XX UTC | ENTRY / BOND | Blocked hours re-enabled for BOND: {0,2,3,4,5,6,7,17,19,23} UTC | User instruction. BOND was exempt from hour blocking (risk/manager.py explicitly skips BOND). All 19 May 3 trades were in blocked hours. Added check in BOND terminal scanner via bond_blocked_hours_utc config field.

## 2026-05-04 | STRATEGY / ALL | Inversion scoped to early window only | user instruction; _ask_floor==0.52 (rem>180s) → invert to partner; _ask_floor==0.80 (rem≤180s, TERMINAL zone) → buy signalled token directly

## 2026-05-04 | HOURS / ALL | All trade hours unblocked (bond_blocked_hours_utc=[]) | user instruction; previously blocked {0,2,3,4,5,6,7,17,23}

## 2026-05-04 | EXIT / ALL | INVERTED_TP added: exit at bid >= entry_price * 1.75 | user instruction; fires before 0.99 PROFIT_TARGET; inverted entries are low-priced (~0.10–0.20), +75% is reachable if signal direction reverses strongly

## 2026-05-04 | EXIT / ALL | TIME_EXIT re-enabled at T-30s | user instruction; bond_exit_sec 10→30; timer fires unconditional sell 30s before window close; previously disabled (holding to resolution)

## 2026-05-04 | STRATEGY / ALL | TERMINAL direction inverted: buy opposite side when gates fire | user instruction; when signal approves YES UP token, bot now finds partner token (same condition_id, opposite outcome_direction) and enters that instead; signal/tpsl/entered_correctly all updated to partner; INVERT_NO_PARTNER warning logged if partner has no ask

## 2026-05-07 06:45 UTC | GATE / YES UP | RUIN_FLOOR_BLOCK removed | user instruction; gate added autonomously, reverted on request

## 2026-05-04 | BUG / ALL | window_outcome_price was wrong for all historical trades | Gamma API outcomePrices collapses to ["0","0"] for ALL tokens after market close (CLOB price, not oracle settlement). This caused wop=0.0 for ~96% of trades since May 3 19:00 UTC — actual YES rate was 61%. Fix: replaced Gamma polling + CLOB fallback with Binance 5m kline (open vs close of exact 300s window), which shares the same grid as Polymarket windows and agrees with Chainlink >99% of the time. Wait increased 10s→35s for kline to fully close. entered_correctly threshold corrected 0.80→0.5 (wop now clean binary 0/1). Backfilled n=75 trades (May 3 19:00 UTC+) with correct values via Binance klines. All prior analysis using window_outcome_price or entered_correctly is invalid and must be re-run.
