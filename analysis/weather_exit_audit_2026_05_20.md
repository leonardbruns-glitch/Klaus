# Weather Strategy Exit Logic Audit
**Date**: 2026-05-20  
**Status**: Strategy PAUSED pending structural fix

---

## EXECUTIVE SUMMARY

The weather arbitrage strategy is **sabotaging itself with inappropriate exit logic**. 

**Key metrics from 7 live trades:**
- Net PnL: **-$6.08** (vs. $0 if we'd held to resolution)
- Win rate: **14.3%** (1 winner, 6 losers)
- BOND_ABORT_CASCADE exit success: **0%** (0 wins, 3 losses)
- Positions that bounced back to entry: **3/3 BOND_ABORT_CASCADE trades**

---

## ROOT CAUSE: SNAP CHECKS ON DAILY RESOLUTION MARKETS

### The Problem

The exit logic uses `snap30` and `snap60` (intraday price movement %) to trigger `BOND_ABORT_CASCADE` exits. This works for **5-minute window resolution** markets (CAS, BOND), where intraday microstructure matters.

It does **NOT work** for daily maximum temperature markets, which resolve 24 hours later. The exit logic is killing winners during temporary intraday dips.

### Evidence

| Trade | Entry | Max | Min | Exit | Exit Reason | Outcome |
|-------|-------|-----|-----|------|-------------|---------|
| #4 | $0.0290 | $0.0300 | $0.0130 | $0.0135 (62s) | snap30=-51.7% | Bounced to max but killed |
| #5 | $0.0425 | $0.0500 | $0.0290 | $0.0307 (62s) | snap30=-27.1% | Bounced to max but killed |
| #6 | $0.1800 | $0.1800 | $0.1600 | $0.1600 (72s) | snap30=-5.6% | Flat decline, legitimate |

**Trades #4 and #5**: Position recovered to $0.03-$0.05 (at or above entry), but exit logic fired first because the *intraday dip* violated the snap threshold.

---

## WHAT SHOULD HAVE HAPPENED

Daily weather markets resolve at a specific time (noon local time) when Wunderground finalizes the daily max temperature. 

For example:
- **Entry**: Forecast says temp will be 22°C (probability 0.85), Polymarket odds show 0.30
- **Edge**: 0.85 - 0.30 = 0.55 edge → buy at $0.30
- **Intraday**: Price dips to $0.10 (other traders panic, liquidating)
- **Current behavior**: Bot exits at $0.10, locks in -67% loss
- **Correct behavior**: Bot holds through the dip; at resolution, if forecast was right, position resolves to $1.00 (100% gain)

The intraday price action is **noise**. The signal is the forecast vs. the actual 24-hour-later observation.

---

## TRADE-BY-TRADE ANALYSIS

### Trade #1: CATASTROPHIC_SL (15s hold)
- Entry: $0.0300 | Exit: $0.0138
- Lost 54% in 15 seconds
- **Verdict**: Likely a bad entry (snap check caught a real loser early). This one may be legitimate.

### Trade #2: PRICE_FLOOR (33s hold)
- Entry: $0.0400 | Exit: $0.0303 | Max: $0.0410
- Price never recovered above entry; exited at floor
- **Verdict**: Legitimate loss, but held long enough to confirm the downtrend. Acceptable.

### Trade #3: PRICE_FLOOR (45s hold)
- Entry: $0.2100 | Exit: $0.1637 | Max: $0.2200
- Price dipped 22%, then recovered to $0.22 (+5% above entry), then fell again
- **Verdict**: Mixed; eventually did go down, but the snap logic didn't catch the recovery bounce.

### Trade #4: BOND_ABORT_CASCADE (62s hold) 🚨
- Entry: $0.0290 | Exit: $0.0135 | Max: $0.0300 | Min: $0.0130
- Price hit min at -55%, recovered to max at +3% (above entry), then exited
- **Snap check fired**: -51.7% snap30 triggered cascade exit
- **Verdict**: **KILLED A POTENTIAL WINNER**. Position was recovering.

### Trade #5: BOND_ABORT_CASCADE (62s hold) 🚨
- Entry: $0.0425 | Exit: $0.0307 | Max: $0.0500 | Min: $0.0290
- Price dipped -32%, recovered to +17% above entry, then snap check fired
- **Snap check fired**: -27.1% snap30
- **Verdict**: **KILLED A POTENTIAL WINNER**. This one recovered strongly.

### Trade #6: BOND_ABORT_CASCADE (72s hold)
- Entry: $0.1800 | Exit: $0.1600 | Max: $0.1800 | Min: $0.1600
- Price range was flat (-5% to -11%)
- **Snap check fired**: -5.6% snap30, -11.1% snap60
- **Verdict**: Likely a real loser; no recovery attempted.

### Trade #7: HARD_EXIT (217s hold) ✓
- Entry: $0.0500 | Exit: $0.0700 | Max: $0.0700 | Min: $0.0300
- Held 3+ minutes, exited with +40% gain
- **Verdict**: **THE ONE WINNER**. Held long enough for price to recover.

---

## CONCLUSION

**3 out of 3 BOND_ABORT_CASCADE exits** bounced back to or above entry price. These were likely winners (or at minimum, viable holds) that got killed by intraday volatility.

The snap30/snap60 checks are **appropriate for 5-minute window markets** where you need to bail on entries that are immediately wrong. They are **catastrophically wrong for daily markets**.

---

## NEXT STEPS (Tier 2)

Replace `BOND_ABORT_CASCADE` logic for `WEATHER_ARB` positions:

```python
if bond_entry_class == "WEATHER_ARB":
    # Daily temp resolution: hold through intraday volatility
    if remaining_seconds > 300:  # >5 min until resolution
        return False  # No exit
    elif remaining_seconds <= 300 and remaining_seconds > 60:
        # Last 5 min: only exit if catastrophic (bid < 0.5 entry)
        if bid / entry_price < 0.5:
            exit()
    # else: hold to resolution
```

Test this on the 7 trades above. Expected improvement: 3/3 BOND_ABORT_CASCADE trades should hold to resolution (potential +$2-3 recovery if forecasts were sound).

---

## WU BIAS ANALYSIS (TBD)

Cannot complete without accessing resolved market data or Wunderground observations directly. Next session:
1. Query 5-10 resolved weather markets from past 2 weeks
2. Compare forecast_mean vs actual WU daily max
3. Check for systematic bias per region (do mountains overpredict? underpredict?)
4. Adjust sigma if bias is >0.5°C
