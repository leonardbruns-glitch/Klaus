#!/usr/bin/env python3
"""
WIS2 BUFR decode debug — subscribe for 3 minutes, download first accessible
BUFR per data-centre, decode and report ALL station lat/lons + temp, and show
which of our target airports match.

Run: python3 analysis/weather/wis2_debug.py
"""
import io
import json
import os
import sys
import tempfile
import time
import urllib.request
from collections import defaultdict

# ── Target airports ────────────────────────────────────────────────────────────
_TARGETS = {
    "RJTT": (35.55, 139.78),
    "UUWW": (55.59,  37.26),
    "SBGR": (-23.44,-46.47),
    "SAEZ": (-34.82,-58.54),
    "MMMX": (19.44, -99.07),
    "LLBG": (32.00,  34.87),
    "WIHH": (-6.13, 106.65),
    "RCSS": (25.07, 121.55),
    "FACT": (-33.96,  18.60),
    "ZBAA": (40.08, 116.59),
    "ZSPD": (31.14, 121.81),
    "ZGSZ": (22.64, 113.81),
    "ZGGG": (23.39, 113.30),
    "ZSQD": (36.27, 120.37),
    "LTFM": (41.26,  28.74),
}
_MAX_DIST = 0.5

def _closest(lat, lon):
    best, bd = None, _MAX_DIST
    for icao, (alat, alon) in _TARGETS.items():
        d = ((lat-alat)**2 + (lon-alon)**2)**0.5
        if d < bd:
            bd, best = d, icao
    return best, bd

# ── BUFR decode — show ALL stations, not just matches ─────────────────────────
def decode_bufr_verbose(bufr_bytes: bytes, origin: str):
    try:
        import eccodes
    except ImportError:
        print("eccodes not installed")
        return

    with tempfile.NamedTemporaryFile(suffix=".bufr", delete=False) as f:
        f.write(bufr_bytes)
        tmppath = f.name

    n_msgs = 0
    n_subsets_total = 0
    n_valid_coords = 0
    n_valid_temp = 0
    matches = []

    try:
        with open(tmppath, "rb") as fh:
            while True:
                bfr = eccodes.codes_bufr_new_from_file(fh)
                if bfr is None:
                    break
                n_msgs += 1
                try:
                    eccodes.codes_set(bfr, "unpack", 1)

                    def _get(key):
                        try: return eccodes.codes_get(bfr, key)
                        except: return None

                    def _get_arr(key):
                        try: return eccodes.codes_get_array(bfr, key)
                        except: return None

                    n_sub = _get("numberOfSubsets") or 1
                    n_subsets_total += n_sub

                    def _to_list(v, n):
                        if v is None: return [None]*n
                        try: return list(v)
                        except TypeError: return [v]*n

                    lats   = _to_list(_get_arr("latitude"),         n_sub)
                    lons   = _to_list(_get_arr("longitude"),        n_sub)
                    t_raw  = _get_arr("airTemperature")
                    if t_raw is None:
                        t_raw = _get_arr("#1#airTemperature")
                    temps  = _to_list(t_raw,                        n_sub)

                    for i, (lat, lon, t_k) in enumerate(zip(lats, lons, temps)):
                        if lat is None or lon is None:
                            continue
                        try:
                            flat, flon = float(lat), float(lon)
                        except:
                            continue
                        if abs(flat) > 90 or abs(flon) > 180:
                            continue
                        n_valid_coords += 1

                        icao, dist = _closest(flat, flon)
                        if icao is not None:
                            temp_c = None
                            if t_k is not None:
                                try:
                                    tv = float(t_k)
                                    if tv < 1e9:
                                        temp_c = round(tv - 273.15, 1)
                                        n_valid_temp += 1
                                except:
                                    pass
                            matches.append((icao, flat, flon, dist, temp_c))

                except Exception as e:
                    print(f"  [decode] subset error: {e}")
                finally:
                    eccodes.codes_release(bfr)
    except Exception as e:
        print(f"  [decode] file error: {e}")
    finally:
        os.unlink(tmppath)

    print(f"  {origin}: {n_msgs} messages, {n_subsets_total} subsets, "
          f"{n_valid_coords} valid coords, {n_valid_temp} with temp")
    if matches:
        for icao, lat, lon, dist, temp_c in sorted(matches):
            print(f"    MATCH {icao}: lat={lat:.2f} lon={lon:.2f} dist={dist:.3f}° "
                  f"temp={temp_c}°C")
    else:
        print(f"    (no target airports matched)")


# ── MQTT listener ─────────────────────────────────────────────────────────────
downloaded_origin_counts: dict = defaultdict(int)
MAX_DOWNLOADS_PER_ORIGIN = 3
LISTEN_SECONDS = 1800

seen_topics = defaultdict(int)

def _try_download(href: str, origin: str):
    try:
        req = urllib.request.Request(href, headers={"User-Agent": "wis2-debug/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        print(f"\n  [DL OK] {len(data)/1024:.1f} KB from {origin}")
        decode_bufr_verbose(data, origin)
    except Exception as e:
        print(f"  [DL FAIL] {origin}: {e}")

def run():
    import paho.mqtt.client as mqtt
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor(max_workers=4)

    def on_connect(client, userdata, flags, rc, props=None):
        if rc == 0 or str(rc) == "Success":
            client.subscribe("cache/a/wis2/#", 0)
            client.subscribe("origin/a/wis2/#", 0)
            print("[WIS2] connected, subscribed")
        else:
            print(f"[WIS2] connect failed rc={rc}")

    def on_message(client, userdata, msg):
        topic = msg.topic
        # Only SYNOP
        if "synop" not in topic and "surface-based" not in topic:
            return

        # Extract origin (data centre ID = segment after wis2/)
        parts = topic.split("/")
        # topic is like: cache/a/wis2/br-inmet/data/core/weather/...
        origin = parts[3] if len(parts) > 3 else "unknown"

        seen_topics[origin] += 1

        if downloaded_origin_counts[origin] >= MAX_DOWNLOADS_PER_ORIGIN:
            return

        try:
            j = json.loads(msg.payload)
            links = j.get("links", [])
            for lnk in links:
                if "bufr" in lnk.get("type", "").lower():
                    href = lnk.get("href", "")
                    if href.startswith("http"):
                        downloaded_origin_counts[origin] += 1
                        print(f"\n[WIS2] downloading from {origin} (#{downloaded_origin_counts[origin]}): {href[:80]}")
                        executor.submit(_try_download, href, origin)
                        break
        except Exception as e:
            print(f"  [parse] {e}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set("everyone", "everyone")

    print(f"[WIS2] connecting to globalbroker.meteo.fr:1883 ...")
    client.connect("globalbroker.meteo.fr", 1883, keepalive=60)

    deadline = time.time() + LISTEN_SECONDS
    while time.time() < deadline:
        client.loop(timeout=1.0)

    executor.shutdown(wait=True, cancel_futures=True)
    client.disconnect()

    print("\n=== Summary: SYNOP origins seen ===")
    for origin, count in sorted(seen_topics.items(), key=lambda x: -x[1]):
        dl = downloaded_origin_counts.get(origin, 0)
        status = f"downloaded {dl}x" if dl else "not downloaded"
        print(f"  {origin}: {count} msgs — {status}")

if __name__ == "__main__":
    run()
