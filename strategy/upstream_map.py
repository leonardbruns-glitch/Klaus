"""
Upstream-downstream synoptic pair map for the Confirmed Upstream Oracle strategy.

Physics basis:
- SYNOPTIC_REGIONS: cities that experience the same air mass simultaneously.
  Coherence check requires ≥2 cities in the same region showing anomaly in same direction.
- DOWNSTREAM_MAP: given an upstream trigger city, which cities will the air mass reach
  within 12-48h. Based on seasonal climatological steering flow (500mb winds).
  Lags are approximate — used for market discovery (look for tomorrow's markets).

Seasonal variants:
- DOWNSTREAM_SUMMER: June–September (ridge/heat-dome patterns, high-pressure steering)
- DOWNSTREAM_WINTER: October–March (trough/cold-front patterns, polar-vortex steering)
- For April–May and October: use DOWNSTREAM_SUMMER as default (transition months lean warm)

Lat/lon reference for propagation direction:
  US heat moves NNE in summer (Bermuda High steering flow, ~15-20kt at 500mb → ~300mi/day)
  US cold moves SSE in winter (Arctic high retrograde flow)
  European heat moves NE (omega blocks, ~10-15kt → ~200mi/day)
"""
from __future__ import annotations

# Cities that experience the same synoptic air mass simultaneously.
# Use for coherence check: require ≥2 cities from same region showing z>ANOMALY_Z.
SYNOPTIC_REGIONS: dict[str, list[str]] = {
    # US South / Southern Plains — heat dome, subtropical ridge
    "us-south-plains": ["dallas", "houston", "austin"],

    # US Midwest — downstream of Southern Plains heat
    "us-midwest": ["chicago", "atlanta"],

    # US West — Pacific ridge / offshore flow events
    "us-west-coast": ["los-angeles", "san-francisco", "seattle"],

    # US Southwest interior — desert heat dome
    "us-southwest": ["los-angeles"],  # single city; relax coherence to z>2.5 alone

    # US Northeast
    "us-northeast": ["nyc", "toronto"],

    # Western Europe — Iberian/Atlantic omega blocks
    "eu-west": ["madrid", "paris", "london"],

    # Central Europe — downstream of western heat
    "eu-central": ["paris", "amsterdam", "munich", "milan"],

    # Northern Europe
    "eu-north": ["amsterdam", "warsaw", "helsinki"],

    # East Asia — Pacific subtropical ridge
    "ea-east-china": ["shanghai", "beijing", "guangzhou", "shenzhen"],

    # Southeast Asia — monsoon/heat
    "sea": ["singapore", "jakarta"],

    # Southern Hemisphere / isolated — no regional coherence check; use z>2.5 solo
    "sh-isolated": ["buenos-aires", "sao-paulo", "cape-town"],
}

# Summer (Jun–Sep): heat dome propagation NNE along Gulf/Atlantic coast and interior plains.
# Lags in hours are approximate; "24h" means "enters downstream city tomorrow."
DOWNSTREAM_SUMMER: dict[str, list[str]] = {
    # Southern Plains → Midwest → Great Lakes
    "dallas":       ["austin", "chicago", "atlanta"],
    "houston":      ["dallas", "austin", "atlanta"],
    "austin":       ["dallas", "houston"],

    # Great Lakes / Northeast corridor
    "chicago":      ["nyc", "toronto"],
    "atlanta":      ["nyc"],

    # Pacific Coast → Southwest interior (marine push reverses for cold)
    "san-francisco": ["los-angeles", "seattle"],
    "seattle":      ["san-francisco"],
    "los-angeles":  ["san-francisco"],

    # Europe: Iberian heat → France → Central Europe (omega block NE propagation)
    "madrid":       ["paris", "london", "milan"],
    "paris":        ["amsterdam", "munich", "london"],
    "london":       ["amsterdam", "paris"],
    "amsterdam":    ["warsaw", "munich", "helsinki"],
    "munich":       ["warsaw", "milan"],

    # East Asia: South China → Yangtze Valley → North China
    "guangzhou":    ["shanghai", "shenzhen"],
    "shenzhen":     ["guangzhou", "shanghai"],
    "shanghai":     ["beijing"],
    "beijing":      ["shanghai"],

    # No strong summer propagation pairs for: nyc, denver, miami, tokyo, singapore,
    # jakarta, toronto, mexico-city, buenos-aires, sao-paulo, cape-town, tel-aviv,
    # moscow, warsaw, helsinki, milan, taipei, qingdao — these only act as targets
}

# Winter (Oct–Mar): cold front propagation SSE, polar vortex intrusion.
DOWNSTREAM_WINTER: dict[str, list[str]] = {
    # Arctic cold pushes south through Great Plains
    "chicago":      ["dallas", "houston", "atlanta", "nyc"],
    "toronto":      ["chicago", "nyc"],
    "nyc":          ["atlanta"],

    # Winter Pacific systems (warm+wet) move NE
    "san-francisco": ["seattle", "los-angeles"],
    "seattle":      ["san-francisco"],

    # European winter: Atlantic lows track NE
    "london":       ["amsterdam", "paris"],
    "paris":        ["munich", "milan", "amsterdam"],
    "madrid":       ["paris"],
    "amsterdam":    ["warsaw", "helsinki"],
    "moscow":       ["warsaw", "helsinki"],

    # East Asia winter: Siberian cold pushes SE
    "beijing":      ["shanghai", "qingdao"],
    "shanghai":     ["guangzhou", "shenzhen", "taipei"],
}


def get_downstream(city: str, month: int) -> list[str]:
    """Return downstream cities for a given upstream trigger city and calendar month."""
    if 6 <= month <= 9:
        return DOWNSTREAM_SUMMER.get(city, [])
    else:
        return DOWNSTREAM_WINTER.get(city, [])


def get_synoptic_region(city: str) -> str | None:
    """Return the synoptic region slug for a city, or None if not in any region."""
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
