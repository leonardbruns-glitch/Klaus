"""LDA breakdown: asset × window size × bnc zone."""
import json, glob, os

SHADOW_ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "shadow", "hot")
STAKE = 5.0

resolutions = {}
for wr_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/window_resolution.jsonl"))):
    with open(wr_path) as f:
        for line in f:
            r = json.loads(line)
            resolutions[(r["condition_id"], r["window_end_ts"], r.get("window_size_s", 300))] = r["moved_up"]

first_fire = {}
for mt_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/market_timeline.jsonl"))):
    with open(mt_path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("record_type") != "market_timeline":
                continue
            wsz = r.get("window_size_s", 300)
            if wsz not in (300, 900):
                continue
            rem = r.get("seconds_to_resolution", 0.0)
            ask = r.get("best_ask", 0.0)
            bid = r.get("best_bid", 0.0)
            bnc = r.get("binance_ret_5m_pct", None)
            if not (8 <= rem <= 90):
                continue
            if not (0.70 <= ask <= 0.98):
                continue
            if bid < 0.50:
                continue
            if bnc is None or abs(bnc) < 0.07:
                continue
            odir = r.get("outcome_dir", "")
            if ("up" if bnc > 0 else "down") != odir:
                continue
            asset = r.get("asset", "UNK")
            key = (r["condition_id"], r["window_end_ts"], wsz)
            if key not in first_fire or rem > first_fire[key]["rem"]:
                first_fire[key] = {"rem": rem, "odir": odir, "ask": ask,
                                   "bnc": bnc, "asset": asset, "wsz": wsz}

rows = []
for key, ff in first_fire.items():
    res = resolutions.get(key)
    if res is None:
        continue
    ff["correct"] = (ff["odir"] == "up") == res
    rows.append(ff)

bnc_bands = [
    (0.07, 0.10, "0.07-0.10%"),
    (0.10, 0.15, "0.10-0.15%"),
    (0.15,  99,  "0.15%+   "),
]

hdr = f"{'asset':>5} {'window':>6} {'bnc_zone':>12}  {'n':>5} {'wrong':>6} {'wr':>7} {'avg_ask':>8} {'ev/trade':>9}"
print(hdr)
print("-" * len(hdr))

for asset in ["BTC", "ETH", "SOL"]:
    for wsz, wlabel in [(300, "5m"), (900, "15m")]:
        for blo, bhi, blabel in bnc_bands:
            subset = [r for r in rows
                      if r["asset"] == asset
                      and r["wsz"] == wsz
                      and blo <= abs(r["bnc"]) < bhi]
            n = len(subset)
            if n == 0:
                continue
            nc = sum(1 for r in subset if r["correct"])
            wr = nc / n
            avg_ask = sum(r["ask"] for r in subset) / n
            ev = wr * STAKE * (1 - avg_ask) / avg_ask - (1 - wr) * STAKE - STAKE * 0.01
            flag = "  <<< NEG EV" if ev < 0 else ("  <<< LOW WR" if wr < 0.92 else "")
            print(f"{asset:>5} {wlabel:>6} {blabel:>12}  {n:>5} {n-nc:>6} {wr:>7.1%} {avg_ask:>8.4f} {ev:>9.4f}{flag}")
        print()
    print()
