---
name: project-global-nms-feed
description: NMS feed expansion for weather strategy — live data sources faster than AWC, per-city coverage map
metadata:
  type: project
---

## Current NMS Coverage (as of 2026-05-26, commit fbfaff7c)

### Direct REST API (national_met.py)

16 stations via REST poll:

| Source | ICAOs | Gain vs AWC | Notes |
|---|---|---|---|
| DWD/BrightSky | EDDM (Munich), EDDB (Berlin) | ~7 min | No auth |
| FMI WFS | EFHK (Helsinki) | ~7 min | No auth |
| Singapore NEA | WSSS (Changi, station S24) | ~28 min | No auth, obs age ~2-7 min |
| IMGW Poland | EPWA (Warsaw) | ~10 min | No auth, hourly synoptic |
| NOAA NWS API | KLGA KORD KLAX KMIA KSFO KDAL KHOU KSEA KBKF KATL KAUS | ~9-12 min | No auth, free |

### WIS2 MQTT Push (wis2_synop.py)

Live on VPS, connected to globalbroker.meteo.fr:1883. Push-based: NMS members publish single-station BUFR bulletins per observation.

Architecture decisions:
- **Geometry pre-filter**: Use GeoJSON `geometry.coordinates` in each MQTT message to skip bulletins from stations not near target airports. Without this, `ar-smn` would download Puerto Madryn instead of Buenos Aires.
- **Message-ID dedup**: `id` field is unique per observation; multiple cache servers relay same message. Prevents 10x redundant downloads of the same BUFR.
- **Best-match per ICAO**: For multi-station bulletins (e.g. il-ims 83-station Israel SYNOP), picks the station closest to the target airport.

**Confirmed working** (validated in live 90s test 2026-05-26 17:30 UTC):

| ICAO | Airport | Temp observed | Source |
|---|---|---|---|
| LLBG | Ben Gurion, Israel | 21.8°C | il-ims multi-station BUFR |
| SBGR | São Paulo Guarulhos | 26.0-26.6°C | br-inmet single-station BUFR |
| FACT | Cape Town | 15.2-16.6°C | saws or similar |
| ZGSZ | Shenzhen | 29.9°C | CMA China |

**Not yet confirmed** (3-hourly SYNOP, need 18:00/00:00/06:00/12:00 UTC cycle):

| ICAO | Airport | Source | Notes |
|---|---|---|---|
| RJTT | Tokyo Haneda | jp-jma-gts-to-wis2 | 3-hourly at 00/06/12/18 UTC |
| UUWW | Moscow Vnukovo | ru-roshydromet | 3-hourly |
| SAEZ | Buenos Aires | ar-smn | geometry pre-filter tested (correct coordinates) |
| MMMX | Mexico City | mx-smn | single-station per message |
| WIHH | Jakarta Halim | id-bmkg | single-station per message |
| RCSS | Taipei Songshan | tw-cwb | not yet seen in tests |
| ZBAA/ZSPD/ZGGG/ZSQD | China (4 cities) | cn-cma | ZGSZ confirmed, others likely at 18:00 UTC cycle |
| LTFM | Istanbul | tr-mgm | not yet seen in tests |

**Why:** NWS gets hourly METARs faster than AWC's GTS ingest path. NEA is independently fresh. WIS2 covers countries with closed or no REST API.

## Known Download Issues

- UK Met Office direct (`metswitchpub.metoffice.gov.uk`): DNS not resolving from VPS → use S3 cache relay
- Belgium RMIB (`wis2node.meteo.be`): HTTP 403 → use KMA cache relay
- Malaysia (`wis2node.met.gov.my`): SSL certificate error
- Morocco (`wis2box.marocmeteo.ma`): SSL certificate error
- Peru (`wis.senamhi.gob.pe`): SSL certificate error

These all have S3/KMA/Saudi cache relays that work.

## Next Steps

**Quick wins (free API key registration, ~30 min each):**
1. **SynopticData** (US 1-min ASOS) — `customer.synopticdata.com/credentials/` — 2000 req/day free. Would upgrade US cities from ~10 min gain to ~40-50 min gain. Endpoint: `api.synopticdata.com/v2/stations/latest?stid={}&recent=5&units=metric`
2. **AEMET Spain** (LEMD Madrid) — `opendata.aemet.es` — free API key
3. **Météo-France** (LFPB Paris) — `portail-api.meteofrance.fr` — free key
4. **KNMI Netherlands** (EHAM Amsterdam) — `developer.dataplatform.knmi.nl` — free key

**How to apply:** Read this before any NMS coding session. Check `strategy/national_met.py` and `strategy/wis2_synop.py` for current state.
