#!/usr/bin/env python3
"""Inspect actual Polymarket API response structure."""

import requests
import json
import os

# Load API key
api_key = None
env_path = "/root/Klaus/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("CLOB_API_KEY="):
                api_key = line.split("=", 1)[1]
                break

if not api_key:
    print("❌ CLOB_API_KEY not found")
    exit(1)

session = requests.Session()
session.headers.update({
    'Authorization': f'Bearer {api_key}',
    'User-Agent': 'Klaus Weather Validator'
})

# Fetch markets
print("Fetching markets...")
url = "https://clob.polymarket.com/markets"
params = {
    'search': 'weather',
    'limit': 5,
}

resp = session.get(url, params=params, timeout=15)

print(f"Status: {resp.status_code}")
print(f"\nResponse sample (first 2000 chars):\n")

try:
    data = resp.json()
    print(json.dumps(data, indent=2)[:2000])
except:
    print(resp.text[:2000])

# Try to extract first market and print full structure
print("\n" + "="*80)
print("FIRST MARKET FULL STRUCTURE:")
print("="*80)

try:
    data = resp.json()
    markets = data.get('data', data.get('markets', []))
    if markets:
        print(json.dumps(markets[0], indent=2))
except Exception as e:
    print(f"Error: {e}")
