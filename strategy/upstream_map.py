"""
Upstream-downstream synoptic pair map for the Confirmed Upstream Oracle strategy.

ALL pairs are empirically validated from 10yr ASOS daily max temperature data
(2015–2024, summer months Jun–Sep, lag-1 day Pearson r).
Methodology: analysis/weather/city_correlations.py, run 2026-05-22.

Only pairs with r >= 0.30 are included in DOWNSTREAM maps.
Pairs with r >= 0.55 are considered HIGH confidence (asterisked in comments).

Key empirical findings vs prior assumptions:
- Dallas → Chicago: r=0.25 (WEAK — removed despite meteorological intuition)
- Miami → Atlanta: r=0.13 (NEAR ZERO — removed)
- Denver → anything: <0.20 (removed; Rocky Mountains thermodynamically decouple Denver)
- EU pairs are exceptionally strong (r=0.60-0.72) — dense Atlantic westerly network
- Shanghai → Tokyo: r=0.54 (unexpected; East China Sea pathway)

SYNOPTIC_REGIONS: cities that share the same air mass simultaneously.
Used for coherence check: require ≥2 cities from same region at z > ANOMALY_Z_MIN.
Based on lag-0 proximity + lag-1 correlation structure.

DOWNSTREAM_SUMMER: Jun–Sep, heat dome / ridge propagation.
DOWNSTREAM_WINTER: Oct–Mar, cold front / polar vortex propagation.
"""
from __future__ import annotations

# ── Synoptic regions ──────────────────────────────────────────────────────────
SYNOPTIC_REGIONS: dict[str, list[str]] = {
    # US Southern Plains — heat dome, subtropical ridge
    # (dallas-austin r=0.73, dallas-houston r=0.63, houston-austin r=0.67 at lag-1)
    "us-south-plains": ["dallas", "houston", "austin"],

    # US Great Lakes / Midwest
    # (chicago-toronto r=0.70, chicago-nyc r=0.57)
    "us-midwest-ne": ["chicago", "toronto", "nyc"],

    # US Southeast
    # (dallas-atlanta r=0.44, chicago-atlanta r=0.40)
    "us-southeast": ["atlanta"],   # no strong internal peers; use solo z>2.5 threshold

    # US West Coast — marine-dominated, not a continental-air-mass region
    # (sf-la r=0.31; low coherence, use solo threshold)
    "us-west": ["san-francisco", "los-angeles"],

    # Western Europe — Atlantic westerly systems
    # (london-amsterdam r=0.72, london-paris r=0.70)
    "eu-west": ["london", "paris", "amsterdam"],

    # Central/Southern Europe — downstream of Atlantic systems
    # (paris-munich r=0.71, munich-milan r=0.64, munich-warsaw r=0.63)
    "eu-central": ["paris", "amsterdam", "munich", "milan"],

    # Iberian Peninsula — omega blocks, Mediterranean
    "eu-iberia": ["madrid"],   # isolated; use solo threshold

    # Northern/Eastern Europe
    # (warsaw-helsinki r=0.57, helsinki-moscow r=0.67, warsaw-moscow r=0.50)
    "eu-north-east": ["warsaw", "helsinki", "moscow"],

    # East Asia — East China Sea pathway
    # (shanghai-tokyo r=0.54, guangzhou-shenzhen r=0.52)
    "ea-yangtze": ["shanghai", "qingdao"],
    "ea-south-china": ["guangzhou", "shenzhen"],

    # Southern Hemisphere — no synoptic links between these cities (7000km+ apart)
    # Each treated as solo-region; ANOMALY_Z_SOLO (2.5) applies to all three
    "sh-buenos-aires": ["buenos-aires"],
    "sh-sao-paulo":    ["sao-paulo"],
    "sh-cape-town":    ["cape-town"],
}

# ── Summer downstream map (Jun–Sep) ───────────────────────────────────────────
# Entries sorted by empirical Pearson r (descending).
# r values shown are lag-1d summer ASOS correlations.
DOWNSTREAM_SUMMER: dict[str, list[str]] = {
    # US Southern Plains → Southeast + Northeast corridor
    "dallas":       ["austin",    # r=0.73 ★★★
                     "houston",   # r=0.63 ★★★
                     "atlanta",   # r=0.44 ★★
                     "nyc"],      # r=0.33 ★  (lag-2 entry; enter if anomaly is ≥2.5σ)

    "houston":      ["austin",    # r=0.67 ★★★
                     "atlanta"],  # r=0.32 ★

    "austin":       ["dallas",    # r=0.73 (bidirectional — whoever peaks first is trigger)
                     "houston",   # r=0.67
                     "atlanta"],  # r=0.33 ★

    # US Midwest → Northeast corridor
    "chicago":      ["toronto",   # r=0.70 ★★★
                     "nyc",       # r=0.57 ★★★
                     "atlanta"],  # r=0.40 ★★

    "toronto":      ["nyc"],      # r=0.47 ★★

    "atlanta":      ["nyc"],      # r=0.33 ★

    "nyc":          ["toronto"],  # r=0.47 (reverse of chicago→toronto; NYC→Toronto is real)

    # US West Coast (weak, marine-driven; only fire on solo z>2.5)
    "san-francisco": ["los-angeles"],  # r=0.31 ★  (offshore-flow events only)

    # Western Europe → Central Europe (Atlantic westerly conveyor)
    "london":       ["amsterdam",  # r=0.72 ★★★
                     "paris",      # r=0.70 ★★★
                     "munich",     # r=0.56 ★★★
                     "milan"],     # r=0.50 ★★

    "paris":        ["munich",     # r=0.71 ★★★
                     "amsterdam",  # r=0.67 ★★★
                     "milan",      # r=0.58 ★★★
                     "warsaw"],    # r=0.41 ★★

    "amsterdam":    ["munich",     # r=0.62 ★★★
                     "warsaw",     # r=0.50 ★★
                     "milan"],     # r=0.46 ★★

    # Iberian Peninsula (omega blocks → Central/Southern Europe)
    "madrid":       ["milan",      # r=0.64 ★★★ (strongest Madrid pair empirically)
                     "munich",     # r=0.45 ★★
                     "paris"],     # r=0.45 ★★

    # Central Europe → Eastern Europe
    "munich":       ["milan",      # r=0.64 ★★★
                     "warsaw"],    # r=0.63 ★★★

    # Northern Europe
    "warsaw":       ["helsinki",   # r=0.57 ★★★
                     "moscow"],    # r=0.50 ★★

    "helsinki":     ["moscow"],    # r=0.67 ★★★

    # East Asia — East China Sea / Pacific westerly pathway
    "shanghai":     ["tokyo",      # r=0.54 ★★★
                     "qingdao",    # r=0.44 ★★
                     "taipei"],    # r=0.38 ★

    "guangzhou":    ["shenzhen",   # r=0.52 ★★★
                     "taipei"],    # r=0.28 (borderline; only fire on z>2.5)

    "qingdao":      ["tokyo"],     # r=0.43 ★★

    "beijing":      ["qingdao",    # r=0.43 ★★
                     "shanghai"],  # r≈0.35 (estimated; Beijing→Shanghai lag-1 not directly measured)
}

# ── Winter downstream map (Oct–Mar) ──────────────────────────────────────────
# Cold front / polar vortex propagation.
# Note: US winter directions often REVERSE vs summer (cold fronts push south).
# European pairs are largely symmetric (Atlantic westerlies year-round).
# US winter empirical data not collected; using meteorological reasoning
# with reduced confidence (mark as MEDIUM confidence).
DOWNSTREAM_WINTER: dict[str, list[str]] = {
    # US: Arctic cold pushes southward from Great Lakes
    "chicago":      ["dallas",     # cold front SSE, ~24-36h
                     "houston",    # cold front SSS, ~36-48h
                     "atlanta"],   # cold front SSE, ~24-36h

    "toronto":      ["chicago",    # cold front SSW, ~12-24h
                     "nyc"],       # winter nor'easters move NE; reverse

    "nyc":          ["atlanta"],   # cold air spills south along Appalachians

    # US West — Pacific systems track NE
    "seattle":      ["san-francisco"],   # Pacific lows track SE→NE; weak

    # European pairs are approximately symmetric year-round (Atlantic westerlies)
    "london":       ["amsterdam", "paris", "munich"],
    "paris":        ["munich", "amsterdam", "milan", "warsaw"],
    "amsterdam":    ["munich", "warsaw"],
    "munich":       ["milan", "warsaw"],
    "madrid":       ["milan", "paris"],
    "warsaw":       ["helsinki", "moscow"],
    "helsinki":     ["moscow"],

    # East Asia: Siberian cold pushes SE in winter
    "beijing":      ["qingdao", "shanghai"],
    "shanghai":     ["taipei", "tokyo"],
    "qingdao":      ["tokyo"],
}


def get_downstream(city: str, month: int) -> list[str]:
    """Return downstream cities for a given upstream trigger city and calendar month."""
    if 6 <= month <= 9:
        return DOWNSTREAM_SUMMER.get(city, [])
    else:
        return DOWNSTREAM_WINTER.get(city, [])


def get_synoptic_region(city: str) -> str | None:
    """Return the synoptic region slug for a city, or None if not found."""
    for region, cities in SYNOPTIC_REGIONS.items():
        if city in cities:
            return region
    return None


def get_region_cities(city: str) -> list[str]:
    """Return all cities in the same synoptic region as the given city."""
    region = get_synoptic_region(city)
    if region is None:
        return [city]
    return SYNOPTIC_REGIONS[region]


def is_isolated_region(city: str) -> bool:
    """True if city is in a single-city or isolated region (use solo z threshold)."""
    cities = get_region_cities(city)
    return len(cities) <= 1
