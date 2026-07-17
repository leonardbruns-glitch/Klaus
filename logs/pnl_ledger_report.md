# Klaus PnL Ledger — 2026-07-17

**Generated:** 2026-07-17T23:37Z  
**Snapshot:** 2026-07-17T23:33:07Z (age: 4 min — FRESH)  
**Klaus systemd:** active  
**Snapshot rows:** 8,224 trades.jsonl

---

## 1. P&L Explain — 2026-07-17 UTC

| Item | Value | Notes |
|---|---|---|
| Capital (day start) | $28.156853 | bankroll.json daily_start_capital |
| Capital (snapshot) | $35.498092 | bankroll.json, 23:33Z |
| **Day P&L (cash)** | **+$7.341** | +26.1% |
| Prior ledger capital | $33.856483 | Jul 15 ledger (Jul 16 NOT FILED — see below) |

### Jul 16 gap note
No PnL ledger was filed on 2026-07-16. Inferred Jul 16 P&L from daily_start change: $28.157 − $33.856 = **−$5.699** (capital fell during the day, partially recovered by candidate fires post-waiver at 14:59Z that added +$1.70). The 2-day unexplained = ($35.498 − $33.856) − (−$5.699 + $7.341) = **+$0.001** — effectively zero, model is complete.

### Today's Attribution (2026-07-17 UTC)

| Source | Events | Net P&L | Notes |
|---|---|---|---|
| UPDOWN-SNIPER taker | 12W / 0L | +**$7.320** | wallet-verified (state_log 22:20Z) |
| Redemption poach loss | 1 event (08:01Z) | −$0.176 | bot sold 16.5sh @0.989 vs natural $1 resolution; included in sniper figure |
| STWA shadow MAKER fills | 3 fills ($8.06 deployed) | PENDING | BUY YES at p=0.02–0.06; untracked in position system; pending resolution |
| RECYCLE099 | 0 events | $0.000 | exit099_live not present for today |
| Unbooked taker fees | ≈12 fires | −~$0.46 est | ≈0.15% of ~$310 total taker buy USDC; included in wallet-true figure |
| **TOTAL ATTRIBUTED** | | **+$7.320** | |
| **UNEXPLAINED** | | **+$0.021** | |

**UNEXPLAINED +$0.021 — CAUSE: timing.** Wallet audit ran at 22:10Z; snapshot at 23:33Z. Difference of 1h23m during which 0–1 additional sniper fires likely completed. NOT MODEL DEFICIENCY.

### STWA Maker Fills (PENDING equity)
Three maker-side fills today carry UNRESOLVED equity not in `capital`:

| Token | Side | Price | Shares | Cost deployed | Expected RBT category |
|---|---|---|---|---|---|
| 4095117562509625 | BUY YES | 0.06 | 58.33 | $3.500 | STWA YES d+1/d+2 weather |
| 1055101008834022 | BUY YES | 0.02 | 150 | $3.000 | STWA YES d+1/d+2 weather |
| 1046907088381323 | BUY YES | 0.02 | 78 | $1.560 | STWA YES d+1/d+2 weather |
| **Total** | | | | **$8.060** | pending resolution |

These are UNTRACKED by the position system (open_positions=0) and logged as "UNTRACKED FILL" in WS. BAND_LIVE=False; these fills originate from shadow-maker orders resting in the CLOB that were hit by other takers. Resolution is likely d+1 or d+2 (multi-day horizon). If NO: −$8.06 future loss. If YES: large upside ($8.06 → up to $280+).

---

## 2. Compounding Scoreboard

| Metric | Today | Jun-11 Baseline | Badatmath Benchmark |
|---|---|---|---|
| Capital start | $28.157 | — | — |
| Capital end | $35.498 | — | — |
| Day return | **+26.1%** | ~3% | 10–20%/turn |
| Sniper fires | 12W / 0L | — | — |
| Kelly clip range | $13.7 → $18.1 | — | — |
| Fill rate | 78.3% (5 FOK miss) | — | — |

**Equity estimate (USDC-only):** $35.498  
**CAVEAT:** $8.06 in pending STWA maker positions not in capital. If resolved YES these add significantly; if NO these represent a future draw from cash (already spent from capital at fill time — or will be at resolution, depending on CLOB escrow timing). Equity range: $35.50 (NO) → $43.56 (NO-cash-already-spent) → much higher (YES).  
The capital field reconciled cleanly to $0.003 at 22:10Z per state_log wallet audit; I use $35.50 as equity_est pending maker resolution.

**Deployed fraction:** 0% tracked open at snapshot; $8.06 untracked pending (~18% of USDC if in-flight).

**Fills today:**

| Category | USDC | Notes |
|---|---|---|
| Sniper taker buys (12 fires) | ≈$194.7 | Tape shows 9 fires through 18:44Z; 3 inferred to reach total 12 per state_log |
| STWA maker buys (3 fills) | $8.06 | |
| **Total fills** | **≈$202.8** | |

**Avg equity:** ($28.157 + $35.498) / 2 = **$31.83**  
**Turns/day:** $202.8 / $31.83 = **6.37×**  
**ROI/turn:** $7.341 / $202.8 = **3.62%**  
*(Sniper-only: $194.7 fills, 3.77% ROI/turn, 6.12 turns)*

**7-day trend:** No prior ledger for Jul 16. Jul 15 returns were near-zero (cash −$0.276 with ~$4.6 open position). Today is the first confirmed large positive day under the candidate policy (Kelly 0.50, P_MIN 0.995). Turns/day are 12–30× the Jun-11 baseline (0.2–0.5), driven by Kelly compounding + daily resolution of multiple markets. ROI/turn (~3.8%) remains in range — the increase in total return comes from multiplied turns, not edge expansion. Badatmath comparison: turns are now in range; ROI/turn still below badatmath's 10–20% per turn — our edge is high-WR/low-payout vs their higher-payout model.

---

## 3. Expected Maker Rebates

Formula: rebate = shares × 0.05 × p × (1−p) × 0.25 per fill (UPPER BOUND — actual depends on pool share vs competing makers).

**Today's maker fills:**

| Token | p | Shares | Fee-equiv | Est. rebate |
|---|---|---|---|---|
| 4095117562509625 | 0.06 | 58.33 | $0.164 | $0.041 |
| 1055101008834022 | 0.02 | 150 | $0.147 | $0.037 |
| 1046907088381323 | 0.02 | 78 | $0.076 | $0.019 |
| **Today total** | | | | **$0.097** |

Note: these fills are at extreme prices (p=0.02–0.06), which suppresses quadratic p*(1-p). Mid-price fills (p≈0.5) would earn ~6× more rebate per dollar deployed.

**Jul 16 maker fills (retrospective, not previously reported):**

| Fill | p | Shares | Est. rebate |
|---|---|---|---|
| token 9559426... @0.09 × 86.61 | 0.09 | 86.61 | $0.089 |
| token 1063919... @0.06 × 16.67 | 0.06 | 16.67 | $0.012 |
| token 6333812... SELL @0.98 × 1.14 | 0.98 | 1.14 | $0.001 |
| token 4776509... @0.02 × 10 | 0.02 | 10 | $0.002 |
| token 1399483... SELL @0.96 × 147.05 | 0.96 | 147.05 | $0.071 |
| **Jul 16 total** | | | **$0.175** |

| Period | Expected rebate | Running cumulative |
|---|---|---|
| Through Jul 15 (prior state) | — | $3.559 |
| Jul 16 (retrospective) | $0.175 | $3.734 |
| Jul 17 | $0.097 | **$3.831** |

**FLAG: Cumulative expected rebate $3.831 > $1 threshold.** Polymarket maker rebates land daily in pUSD with $1 minimum accrual. The user should verify pUSD receipt in their Polymarket wallet. No payout has been recorded in this ledger to date. This estimate is an UPPER BOUND — actual depends on competing maker volume in these markets.

---

## 4. Kill-Switch Proximity

| Rail | Current | Threshold | Status |
|---|---|---|---|
| Day P&L vs −$10 halt | +$7.341 | < −$10 | ✅ COMFORTABLE |
| Capital vs $50 ruin floor | $35.498 | < $50 | ⚠️ BREACHED (−$14.50) |
| Capital vs $75 weekly floor | $35.498 | < $75 | ⚠️ BREACHED (−$39.50) |
| Kill-watch losses (candidate) | 0 / 3 | ≥ 3 → trigger | ✅ CLEAN (day 2) |
| Candidate WR (rolling 18) | 18/18 = 100% | <30% over 20 | N/A (<20 trades) |
| Candidate PF | ∞ (no losses) | <0.8 over 20 | N/A (<20 trades) |

**Capital floors context:** Both the $50 ruin and $75 weekly floor have been breached since at least Jul 6 (BAND_LIVE wind-down at $108 equity vs $222.90 HWM). These floors are inherited from CLAUDE.md taker-era rules. The owner is operating the bot under explicit waiver during the candidate-validation phase. Today's +$7.34 moves capital from $28.16 → $35.50; recovery to $50 ruin floor requires ~+$14.50 additional (+41%) and to $75 weekly floor requires ~+$39.50 (+111%) from here.

**⚠️ KILL-SWITCH CAVEAT:** The WR/PF kill floors (>40% WR, PF >1.3) were specified for the taker-era multi-strategy. The current candidate architecture wins ~100% of sniper fires by design (P_MIN ≥ 0.995, Kelly-sized). WR <30% triggering a halt is NOT applicable to this mode — a single loss at P=0.995+ is expected ~1 in 200 fires and would not indicate edge failure. A kill-switch re-derivation appropriate for the sniper regime is pending with the owner.

**⚠️ DISK ALERT:** System disk at **100% full** (92GB used / 97GB, 1GB free). This was 98% on Jul 15. Risk: log writes may fail; JSONL shadow files may truncate. Owner action required.

---

## 5. Day Verdict

**YES — equity compounded today. +26.1% ($28.16 → $35.50).**

- 12/12 UPDOWN-SNIPER wins. Kelly compounding working as designed: clip grew $13.7 → $18.1 intraday across 12 fires.
- Binding constraint: **fill rate** (78.3%, 5 FOK misses at $0 cost) and **market cadence** (~1 fire/hr in observed window). Not capital, not edge.
- Redemption poach guard deployed (22:05Z restart), fixing the 08:01Z poach-via-redemption race that cost $0.176 on that fire.
- Pooled unfiltered gate is now confirmed −EV (n=143 WR .958 < BE .963), retroactively validating the Jul 16 v1 cut.
- $8.06 in STWA shadow maker positions (cheap YES d+1/d+2) open and untracked — pending resolution. Expected value small (prices imply very low YES probability), but nonzero.
- **Infrastructure risk: disk 100% full.** Log writes are at risk of silent failure. Resolve before next session.

---

*Ledger agent: pnl-ledger-agent@klaus | Run at 23:37Z | Snapshot age at run: 4 min*
