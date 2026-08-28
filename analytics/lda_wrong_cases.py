"""Find all wrong-direction LDA cases in shadow data (bnc >= 0.07%)."""
import json, glob, os, datetime

SHADOW_ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "shadow", "hot")

resolutions = {}
for wr_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/window_resolution.jsonl"))):
    with open(wr_path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("window_size_s", 0) != 300:
                continue
            resolutions[(r["condition_id"], r["window_end_ts"])] = r

first_fire = {}
for mt_path in sorted(glob.glob(os.path.join(SHADOW_ROOT, "*/market_timeline.jsonl"))):
    with open(mt_path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("record_type") != "market_timeline":
                continue
            if r.get("window_size_s", 0) != 300:
                continue
            rem  = r.get("seconds_to_resolution", 0.0)
            ask  = r.get("best_ask", 0.0)
            bid  = r.get("best_bid", 0.0)
            bnc  = r.get("binance_ret_5m_pct", None)
            if not (8 <= rem <= 90):
                continue
            if not (0.70 <= ask <= 0.994):
                continue
            if bid < 0.50:
                continue
            if bnc is None or abs(bnc) < 0.07:
                continue
            odir    = r.get("outcome_dir", "")
            bnc_dir = "up" if bnc > 0 else "down"
            if bnc_dir != odir:
                continue
            key = (r["condition_id"], r["window_end_ts"])
            if key not in first_fire or rem > first_fire[key]["rem"]:
                first_fire[key] = {
                    "rem":   rem,
                    "odir":  odir,
                    "asset": r.get("asset", ""),
                    "bnc":   bnc,
                    "ts":    r.get("ts_s", 0),
                    "wend":  r["window_end_ts"],
                    "ask":   ask,
                }

wrong = []
for key, ff in first_fire.items():
    res = resolutions.get(key)
    if not res:
        continue
    correct = (ff["odir"] == "up") == res["moved_up"]
    if not correct:
        wrong.append(ff)

wrong.sort(key=lambda x: abs(x["bnc"]))

print(f"Total wrong-direction cases (bnc>=0.07%): {len(wrong)}")
print()
print(f"{'UTC time':<22} {'asset':<6} {'bnc':>10} {'rem':>6} {'odir':<6} {'ask':>6}")
print("-" * 58)
for ff in wrong:
    ts_str = datetime.datetime.utcfromtimestamp(ff["ts"]).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts_str:<22} {ff['asset']:<6} {ff['bnc']:>+10.4f}% {ff['rem']:>5.0f}s {ff['odir']:<6} {ff['ask']:>6.3f}")
