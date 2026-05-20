# Weather Forecaster Backtest POC — Implementation Plan

**Status**: Framework ready, awaiting data source integration  
**Date**: 2026-05-20  
**Objective**: Identify which forecaster (AROME, DWD, JMA, CMA, BOM, ECMWF, GFS) was most accurate per city

---

## WHAT WE HAVE

✅ **Backtest framework** (`weather_backtest_poc.py`):
- Market analysis pipeline
- Edge calculation logic  
- Forecaster accuracy ranking
- Coordinate tracking system
- Simulated entry/exit logic

✅ **City coordinates**: All 65 cities with exact lat/lon (airport references)

✅ **Data sources identified**:
- Polymarket: PolymarketData API or Resolved Markets API
- Forecasts: Open-Meteo Previous Runs API
- Reality: NOAA CDO or Wunderground

---

## CRITICAL ISSUE: Coordinate Matching

**Problem**: We use airport coordinates (e.g., Paris → LFPB 48.97°N, 2.44°E), but:
- Polymarket resolves against **Wunderground stations** (not airports)
- Wunderground uses METAR stations which may be at different locations
- **Example**: Paris Wunderground uses "Paris-Le Bourget" (not CDG), which is close but not identical

**Solution**: Before running the full POC, we MUST:

1. **Verify each city's Wunderground station** against Polymarket documentation
   - Polymarket market descriptions include the WU station URL
   - Example: "Highest temperature in Paris on May 21? Resolves against WU station FRXX0011"
   
2. **Update CITY_COORDS** with exact Wunderground station coordinates if different

3. **Create a mapping table**: city → Wunderground station ID + coords

---

## IMPLEMENTATION PATH (Phases)

### Phase 1: Coordinate Verification (30 min)
**Goal**: Ensure we're matching against the right stations

**Steps**:
1. Pick 3 cities (Paris, Tokyo, New York)
2. Go to Polymarket and find a recent resolved weather market for each
3. In market description, note which Wunderground station was used for resolution
4. Check if our CITY_COORDS matches WU station location
5. If different, update coordinates in our mapping
6. Create `CITY_WU_STATION_MAP` with verified stations

**Output**: Verified coordinate list with WU station IDs

### Phase 2: Data Source Testing (1 hour)
**Goal**: Connect real API data sources

**Steps**:

**A. Get Resolved Polymarket Markets**
```python
# Option 1: PolymarketData API
GET https://api.polymarketdata.co/v1/markets?search=weather&resolved=true&limit=20
# Returns: ~10-20 resolved weather markets from last 30 days

# Option 2: Resolved Markets API  
GET https://api.resolvedmarkets.com/markets?type=weather&status=resolved
# Returns: Resolved markets with outcomes
```

**B. Get NOAA Historical Observations**
```python
# NOAA CDO API (requires free token from https://www.ncei.noaa.gov/cdo-web/)
GET https://www.ncei.noaa.gov/cdo-web/api/v2/data?stationid=GHCND:USW00013874&datatypeid=TMAX&startdate=2026-05-15&enddate=2026-05-21
# Returns: Daily max temperatures for a station
```

**C. Get Historical Forecasts from Open-Meteo**
```python
# Previous Runs API — get forecast from N days ago for today's weather
# This simulates "what would forecaster have said at entry time"
GET https://api.open-meteo.com/v1/forecast?latitude=48.86&longitude=2.35&models=arome,dwd_icon_d2,ecmwf,gfs&past_days=5&forecast_days=1
# Returns: Historical forecast runs with different lead times
```

**Output**: Working data pipeline (fetch → parse → validate)

### Phase 3: Mini-Backtest (2 hours)
**Goal**: Run backtest on 5 recent markets

**Steps**:
1. Manually identify 5 resolved Polymarket weather markets (use Polymarket website)
2. For each market:
   - Note: city, resolution_date, actual_temp (from WU), entry_price
   - Fetch forecasts from Open-Meteo Previous Runs for each model
   - Calculate edges and simulate entries
   - Compare to actual outcome
3. Run through `weather_backtest_poc.py` analysis pipeline
4. Output: Which forecaster was best for each city?

**Example output**:
```
Market 1: Paris, 2026-05-19
  Actual: 23°C
  Best forecaster: AROME (error -0.2°C)
  Best edge offered: ECMWF (edge +0.12)
  Would have won? Yes (entered at 0.40, resolved at 1.0)
  
Market 2: Tokyo, 2026-05-18
  Actual: 25°C
  Best forecaster: JMA (error +0.1°C)
  Best edge offered: JMA (edge +0.15)
  Would have won? Yes (entered at 0.35, resolved at 1.0)
```

**Output**: Proof that framework works on real data

### Phase 4: Full POC Backtest (4-6 hours)
**Goal**: Run across all 30+ resolved markets, all 65 cities where data exists

**Steps**:
1. Fetch ALL resolved weather markets from Polymarket (Jan 2026 - May 2026, ~50-200 markets)
2. Filter to cities in our CITY_COORDS list
3. For each market:
   - Verify coordinates match WU station
   - Fetch forecast + actual
   - Analyze via framework
4. Aggregate results:
   - Per city: Which forecaster was most accurate?
   - Per city: Which offered best average edge?
   - Per forecaster: Which cities is it best for?
5. Output ranking table: City → Best Forecaster (with accuracy metrics)

**Output**: Definitive ranking to inform Tier 1C implementation

---

## DATA DEPENDENCIES

### Required before Phase 2:

**A. Verified City-to-WU-Station Mapping**
```python
CITY_WU_STATION_MAP = {
    "Paris": {
        "wunderground_station": "FRXX0011",  # From Polymarket market description
        "lat": 48.9694,
        "lon": 2.4414,
        "city_name": "Paris-Le Bourget"
    },
    "Tokyo": {
        "wunderground_station": "RJTT",
        "lat": 35.5494,
        "lon": 139.7798,
        "city_name": "Tokyo-Haneda"
    },
    # ... etc for all 65 cities
}
```

**B. NOAA CDO API Token**
- Go to https://www.ncei.noaa.gov/cdo-web/
- Sign up (free)
- Generate token
- Store in environment variable: `NOAA_CDO_TOKEN`

---

## QUESTIONS FOR USER

Before proceeding, please clarify:

1. **Coordinate verification**: Can you provide Wunderground station IDs for 3-5 of our cities so we can verify our coords are correct?
   - Or: Can you access Polymarket and note the WU station from recent weather market descriptions?

2. **API access**: Do you have/want a NOAA CDO token, or should we scrape Wunderground directly?

3. **Time budget**: 
   - Quick POC (Phase 1-3): ~4 hours total → answer for 5 cities
   - Full backtest (Phase 1-4): ~8 hours total → answer for all 65 cities

4. **Accept**: Should we proceed with Phase 1 (coordinate verification) as next step?

---

## EXPECTED OUTCOMES

After full POC backtest, we'll have:

✅ **Accuracy rankings** by city (which forecaster was closest to actual temp)
✅ **Edge rankings** by city (which offered best fair_prob - poly_price)
✅ **Recommendation** for each city: Use AROME, DWD, JMA, CMA, BOM, ECMWF, or GFS
✅ **Confidence level** (based on sample size n per city)

**Example**: 
```
City           | Best Forecaster | Accuracy | Avg Edge | Recommendation
Paris          | AROME           | ±0.3°C   | +0.12    | ✅ Use AROME (n=8)
Tokyo          | JMA             | ±0.5°C   | +0.10    | ✅ Use JMA (n=6)
New York       | NOAA NWS        | ±0.4°C   | +0.11    | ✅ Use NWS API (n=12)
Beijing        | CMA             | ±0.8°C   | +0.05    | ⚠️ Marginal (n=4)
Sydney         | BOM             | ±0.2°C   | +0.14    | ✅✅ Use BOM (n=9)
```

This ranking will drive **Tier 1C** implementation: region-aware model selection.

---

## BLOCKED ON

- User confirmation of coordinate verification approach
- User decision on full vs. mini POC scope
- NOAA CDO token (or decision to use WU scraping instead)
