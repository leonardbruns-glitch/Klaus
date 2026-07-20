# Klaus PnL Ledger — 2026-07-20

**Generated:** 2026-07-20T23:37Z  
**Snapshot:** 2026-07-20T23:34:16Z (3 min — FRESH)  
**System:** `## klaus systemd: active`  
**Snapshot HEAD:** 28f230560  

---

## Section 1 — P&L Explain (2026-07-20 UTC)

### Capital Anchors

| Source | Value | Notes |
|---|---|---|
| Prior ledger capital (Jul-19 close) | $21.495442 | CLOB-actual verified by Jul-19 22:05Z EVOLVE |
| Snapshot capital (23:34Z) | $21.495442 | bankroll.json; CLOB-actual verified by EVOLVE at 11:40Z and 22:05Z today |
| Day P&L | **$0.00** | $21.495442 − $21.495442 = $0 |
| bankroll.json saved_ts | 2026-07-19 ~midnight UTC | MODEL DEFICIENCY carry-over — write loop not triggered today (no fills/settles); mitigated by dual CLOB-actual verification |

**CLOB-actual verification:** Two EVOLVE entries (11:40Z and 22:05Z) explicitly confirm "wallet $21.495442 CLOB-actual == bankroll exact." Capital anchor is reliable despite stale bankroll.json.

### Fill Attribution (all legs, ts_close in 2026-07-20 UTC window)

| Entry Class | Side | Shares | Price | Cost | Net PnL | Outcome |
|---|---|---|---|---|---|---|
| *(none)* | — | — | — | — | $0 | fills=0 confirmed by exec audit commit |

**RECYCLE099:** exit099_live.jsonl absent for 2026-07-20 — $0.

### P&L Roll-Up

| Line | Amount |
|---|---|
| Bot fills (all entry classes) | **$0** |
| RECYCLE099 | **$0** |
| STWA resolutions today | **$0** (wallet unchanged; Jul-18 d+2 and Jul-17 d+3 still unresolved — see below) |
| **Sum attributed (realized)** | **$0.00** |
| **Unexplained** (capital_now − capital_prior − attributed) | **$0.00** |

### Unexplained: $0.00 — No Investigation Required

Trivially within materiality. No fills, no resolutions, no manual flows. Wallet verified CLOB-actual twice today at exactly the same value as the prior report close. **No MODEL DEFICIENCY flag this section.**

### STWA Pending Positions — Resolution Status

| Position | Deployed | d+2 Target | Status as of 23:34Z | Risk |
|---|---|---|---|---|
| Jul-17 (tokens 4095117 / 1055101 / 1046907) | $8.060 | **Jul-19** | **d+3 OVERDUE — still unresolved** | If NO: -$8.06; if YES: large payout (low-p entry) |
| Jul-18 (token 7094108612094851, 44.875sh@0.08) | $3.590 | **Jul-20 (today)** | **UNRESOLVED** — wallet unchanged all day | If NO: -$3.59; if YES: ~+$41.29 |
| Jul-19 (token 5717613767097074, 146.33sh@0.02) | $2.926 | Jul-21 (tomorrow) | Open, d+1, normal | If NO: -$2.93; if YES: ~+$143.40 |

**FLAG — Two STWA positions overdue:** Jul-17 (d+3) and Jul-18 (d+2 end-of-today). Neither has reflected in the CLOB-actual wallet. Since the wallet is independently verified, the only consistent explanation is that both markets remain **open and unresolved** as of the 23:34Z snapshot — resolution is pending, likely past local end-of-day in the relevant weather market's timezone. Monitor wallet tomorrow. If they resolved to $0 (loss), the wallet would have decreased; that it has not confirms they are still open.

---

## Section 2 — Compounding Scoreboard

### Fills and Turns

| Metric | 2026-07-20 | 2026-07-19 (prior) | 06-11 baseline |
|---|---|---|---|
| Fills USD | **$0** | $86.02 | $10–$40 |
| Day PnL | **$0.00** | -$16.07 | — |
| Start capital | $21.495 | $38.018 (EVOLVE) | ~$10 |
| End capital | $21.495 | $21.495 | — |
| Avg equity (midpoint) | $21.495 (flat) | $29.75 | — |
| Turns/day | **0** | 2.91 | 0.2–0.5 |
| ROI/turn | **N/A** | -18.69% | ~+3% |

Zero fills = zero turns. Bot is in collection/shadow mode; all live paths disarmed. This is not an execution failure — the sniper PF-rail correctly halted activity on Jul-19. Day 1 of zero-fill mode.

### Equity Estimate

| Component | Value | Confidence |
|---|---|---|
| Wallet capital (CLOB-actual, twice-verified) | $21.495 | **HIGH** |
| STWA open Jul-17 (at cost, d+3 overdue) | $8.060 | LOW — overdue, status unclear |
| STWA open Jul-18 (at cost, d+2 today) | $3.590 | LOW — unresolved |
| STWA open Jul-19 (at cost, d+1) | $2.926 | LOW — normal |
| **equity_est** | **$36.071** | LOW CONFIDENCE |

**CAVEAT:** equity_est range = $21.495 (full STWA write-down if all resolve NO) to $36.071 (cost-basis held). At entry prices of 0.02–0.08, fair value ≈ cost basis under efficient-market assumption. Do NOT use $36.071 for sizing decisions.

**vs. badatmath benchmark:** Their ~1.0× equity/day at 10–20%/turn. Today: 0× at N/A. Jul-19: 2.91× at -18.69%. Binding constraint is the sniper CUT removing our only active fill path — not a fundamental edge problem.

---

## Section 3 — Expected Maker Rebates

### Today's Maker Fills

No maker fills today. Expected rebate = $0.

### Cumulative Expected Rebate

| Period | Expected rebate (UPPER BOUND) |
|---|---|
| Through Jul-19 (prior state) | $3.917 |
| Jul-20 (today) | +$0.000 |
| **Cumulative through Jul-20** | **$3.917** |

Formula: shares × feeRate(0.05) × p × (1−p) × rebate_share(0.25). No new fills today; cumulative unchanged.

**⚠ USER ACTION REQUIRED:** $3.917 exceeds the $1 minimum pUSD accrual threshold. Payouts land daily in pUSD. This flag was first raised in the Jul-19 report and remains open. Please verify pUSD receipt in Polymarket wallet. Actual payout depends on your share of the competing maker pool — $3.917 is a ceiling, not a guarantee.

---

## Section 4 — Kill-Switch Proximity

### Quantitative Rails

| Signal | Threshold | Value | Status |
|---|---|---|---|
| Day PnL vs halt | ≥ -$10 | **$0.00** | ✅ CLEAR |
| Capital vs ruin floor | ≥ $50 | **$21.495** | ❌ BREACHED — owner-waived carry-over |
| Capital vs weekly floor | ≥ $75 | **$21.495** | ❌ BREACHED — owner-waived carry-over |
| Week PnL | > -20%/month equiv | **-82% week** ($120→$21.50) | ❌ SEVERE — per EVOLVE weekly 467dbded4 |
| Post-cut gate n | ≥ 100 | **n=38** (22:05Z) | Collecting — ~2 days to decision |
| Post-cut point WR | > BE 0.9701 | **0.9737** (37W/1L) | Point ABOVE BE (recovered from 0.960 at 11:30Z) |
| Post-cut CI-lo | > BE 0.9701 | **0.865** | Far under — no re-enable signal |
| Rolling 20 WR (all-hist) | > 40% | 97.45% (n=157) | Per taker-era spec: inapplicable |

### Path States

| Path | State | Notes |
|---|---|---|
| UPDOWN sniper | **CUT** | PF-rail 11:26Z Jul-19; owner-registered |
| Post-cut re-enable gate | n=38/100, CI far | Kill or pass decision ~Jul-22 |
| BAND_LIVE | Disarmed Jul-6 | Equity < 50% HW ($222.90) |
| BAND_NO_ENABLED | Disarmed Jul-2 | 7d WR 39.2% -EV |
| STWA_REGULAR_YES | Disabled Jun-5 | -EV per calibration curve |
| STWA_REGULAR_NO | Disabled Jun-11 | 0 fires in 48h while armed |
| BAND_PAIR_FAV | Shadow only | BAND_LIVE=False → no live fires |
| MAKER_SHADOW | Active (shadow) | Shadow-only; zero live fires today |
| Open positions | 0 tracked | $14.576 STWA untracked pending |

### Weather Band Status

Settled disp_ratio Jul-15..Jul-19: 1.097 / 1.003 / 0.967 / 0.849 / 1.106 — band re-enable NOT met (requires sustained ≥1.10; Jul-19 grazes it, not sustained). Jul-20 partial-day read excluded (not-yet-settled per EVOLVE 22:05Z). NEG_RISK/RECYCLE alive ([WA] 21:57Z) but ruin_floor-blocked.

**Disk:** 87% per Jul-20 system_status — up from 83% post-cleanup (Jul-19). Warrants monitoring; 13G free remaining.

### ⚠ WR/PF Kill-Switch Caveat (mandatory)

WR and PF floor thresholds were specified for the taker era. The sniper by design achieves ~97% WR; a single loss does not indicate strategy failure. The PF-rail at 11:26Z Jul-19 is the appropriate per-strategy risk instrument. **Do NOT recommend a halt on WR alone.** Kill-switch re-derivation proposal remains pending with the owner. Proximity table above is reported for transparency; the PF-rail already fired.

---

## Section 5 — Day Verdict

**FLAT — equity neither compounded nor declined.**  
Day PnL: **$0.00 (0.0%)**  
Week PnL: **-82%** ($120 → $21.50)

Binding constraint: **all live paths disarmed.** Sniper PF-rail fired Jul-19 11:26Z; zero activity since. Bot is in correct posture — pure collection/shadow mode, accruing post-cut gate data (n=38, ~40 ticks/day). Gate decision arrives ~Jul-22: if point WR holds above BE and CI-lo clears BE at n=100, re-enable is possible; if point drops below BE, UPDOWN CROSSING class closes permanently.

STWA pending ($14.576 total at cost) unresolved as of 23:34Z — including overdue Jul-17 (d+3) and Jul-18 (d+2 today). Resolution expected imminently; monitor wallet.

Operational flag from prior ledger carries forward: **bankroll.json write-cadence MODEL DEFICIENCY** — file not written since Jul-19 midnight. Mitigated today by two EVOLVE CLOB-actual checks. Fix investigation on VPS remains open.

*Report generated by PnL Ledger agent at 2026-07-20T23:37Z. Data source: data-mirror branch snapshot 2026-07-20T23:34:16Z.*
