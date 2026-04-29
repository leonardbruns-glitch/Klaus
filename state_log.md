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
