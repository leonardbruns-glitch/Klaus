"""Build the weather trade tape + resolution join used by conservation_alpha.py.

Parses logs/shadow/hot/<date>/maker_flow.jsonl (polled executed-trade feed), dedups by
(txHash, asset, side, outcome, price, size), keeps daily-high-temperature events, and
writes /tmp/wx_temp.parquet. Then fetches per-bucket resolutions from Gamma by event slug
into /tmp/res_by_slug.json.
"""
import glob, json, urllib.request, urllib.parse, time
import pandas as pd


def build_tape():
    seen, rows = set(), []
    for fn in sorted(glob.glob("logs/shadow/hot/*/maker_flow.jsonl")):
        for l in open(fn):
            try:
                r = json.loads(l)
            except Exception:
                continue
            k = (r.get("transactionHash"), r.get("asset"), r.get("side"),
                 r.get("outcome"), r.get("price"), r.get("size"))
            if k in seen:
                continue
            seen.add(k)
            rows.append((r.get("timestamp"), r.get("eventSlug"), r.get("slug"), r.get("conditionId"),
                         r.get("asset"), r.get("outcome"), r.get("side"), r.get("price"),
                         r.get("size"), r.get("proxyWallet"), r.get("transactionHash")))
    df = pd.DataFrame(rows, columns=["ts", "event", "slug", "cid", "token", "outcome",
                                     "side", "price", "size", "wallet", "tx"])
    df = df.dropna(subset=["ts", "price", "event"])
    for c in ("ts", "price", "size"):
        df[c] = df[c].astype(float)
    df["yes_px"] = [p if str(o).lower() == "yes" else 1.0 - p
                    for o, p in zip(df["outcome"], df["price"])]
    df = df[df["event"].str.contains("highest-temperature", na=False)].sort_values("ts")
    df.to_parquet("/tmp/wx_temp.parquet")
    return df


def fetch_res(df):
    gj = lambda u: json.load(urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))
    res = {}
    for i, s in enumerate(df["event"].dropna().unique()):
        try:
            ev = gj("https://gamma-api.polymarket.com/events?slug=%s" % urllib.parse.quote(s))
        except Exception:
            continue
        for m in (ev[0].get("markets", []) if ev else []):
            op = m.get("outcomePrices")
            if isinstance(op, str):
                try:
                    op = json.loads(op)
                except Exception:
                    op = None
            if not op or len(op) < 2:
                continue
            try:
                yp = float(op[0])
            except Exception:
                continue
            if yp > 0.98 or yp < 0.02:
                res["%s||%s" % (s, m.get("slug"))] = 1 if yp > 0.5 else 0
        if i % 40 == 0:
            time.sleep(0.2)
    json.dump(res, open("/tmp/res_by_slug.json", "w"))
    return res


if __name__ == "__main__":
    df = build_tape()
    print("temp fills:", len(df), "events:", df["event"].nunique())
    res = fetch_res(df)
    print("resolved buckets:", len(res))
