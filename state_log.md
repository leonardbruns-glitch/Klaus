# Klaus State Log

Session-altering decisions only. Read last 10 entries at the start of every session before any analysis.
Format: `YYYY-MM-DD HH:MM UTC | SYSTEM/ASSET | exact change | reason + evidence`

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

## 2026-05-02 | ENTRY / BTC | BTC snap60 [20,30%) block | WR=66.7% total_pnl=-$11.70 (n=18); 12 wins sacrificed ($6.53, 3 are fee-losers) vs 6 losses recovered ($18.23), net +$11.70; ETH same zone neutral (net+$1.04) → BTC-specific only; user-authorised Tier 2

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
