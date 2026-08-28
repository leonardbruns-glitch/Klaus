"""
Behavioral fingerprint of the weather MMs (read-only, no capital).

Make-or-break test for [[project_mm_fingerprint_metagame]]: are the ~10 recurring
cross-market makers SLOW & DETERMINISTIC (=> modelable/predictable) or adaptive/noisy?

We decode OrderFilled DATA (non-indexed makerAssetId/takerAssetId/amounts) to recover,
per fill: maker, exact PRICE (= the maker's posted limit price; the taker crosses to it),
side, token, and via metar_lockout token map -> city + YES/NO + bucket. Cadence from
data-api trade timestamps (free; no extra RPC).

Signal we can read cleanly from FILLS:
  - PRICE discipline: do they post at a few repeated / whole-cent price points? (deterministic)
  - breadth: #cities, #buckets, YES vs NO, tail (<0.10/>0.90) share
  - side discipline: pure seller / pure buyer / two-sided
  - cadence: median gap between fills, fills/day, active span
NOTE: fill SIZE is chopped by the taker, so sizing-templates are read from book data
(metar_lockout), not here.

Run: python3 analysis/weather/mm_fingerprint.py
Out: analysis/weather/mm_fingerprint_out.json
"""
from __future__ import annotations
import json, time, glob, urllib.request
from collections import Counter, defaultdict
from statistics import median, pstdev

ORDERFILLED_TOPIC = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
MARKET_SCAN  = 120
RECEIPT_CAP  = 420
DECODE_JSON  = "analysis/weather/mm_decode_out.json"
OUT_JSON     = "analysis/weather/mm_fingerprint_out.json"
LOCKOUT_GLOB = "logs/shadow/hot/*/metar_lockout.jsonl"


def _rpc_url():
    for line in open(".env"):
        if line.startswith("POLYGON_RPC_URL="):
            return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no POLYGON_RPC_URL")


RPC = _rpc_url()


def rpc(method, params):
    req = urllib.request.Request(RPC, data=json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read()).get("result")


def get(url):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "k"}), timeout=15).read())


def load_token_map():
    """token_id (str) -> (city, side 'YES'/'NO', lo_c, hi_c) from metar_lockout logs."""
    tm = {}
    for fp in glob.glob(LOCKOUT_GLOB):
        try:
            for line in open(fp):
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                city = r.get("city")
                lo, hi = r.get("bucket_lo_c_padded"), r.get("bucket_hi_c_padded")
                y, n = r.get("token_id"), r.get("no_token_id")
                if y and y not in tm:
                    tm[str(y)] = (city, "YES", lo, hi)
                if n and n not in tm:
                    tm[str(n)] = (city, "NO", lo, hi)
        except Exception:
            continue
    return tm


def main():
    targets = {m["addr"] for m in json.load(open(DECODE_JSON))["top_makers"] if m["n_markets"] >= 3}
    tmap = load_token_map()
    print(f"target systematic makers: {len(targets)} | token map entries: {len(tmap)}")

    # 1) weather markets
    cids = []
    for closed in ("false", "true"):
        for ev in get(f"https://gamma-api.polymarket.com/events?tag_slug=weather&limit=200&closed={closed}&active=true"):
            for m in ev.get("markets", []):
                q = m.get("question", "").lower()
                if ("highest temperature in" in q or "lowest temperature in" in q) and m.get("conditionId"):
                    cids.append(m["conditionId"])
    cids = list(dict.fromkeys(cids))

    # 2) trades -> tx maps (takers, cid, timestamp), grouped per cid for stratified sampling
    tx_taker = defaultdict(set)
    tx_cid, tx_ts = {}, {}
    cid_txs = defaultdict(list)
    for cid in cids[:MARKET_SCAN]:
        try:
            tr = get(f"https://data-api.polymarket.com/trades?market={cid}&limit=500")
        except Exception:
            continue
        for t in tr:
            h = t.get("transactionHash")
            if not h:
                continue
            if h not in tx_taker:
                cid_txs[cid].append(h)
            tx_taker[h].add(t.get("proxyWallet", "").lower())
            tx_cid.setdefault(h, cid)
            tx_ts.setdefault(h, t.get("timestamp"))
        time.sleep(0.02)
    known_takers = set().union(*tx_taker.values()) if tx_taker else set()

    order, i = [], 0
    while len(order) < min(RECEIPT_CAP, len(tx_taker)):
        added = False
        for cid in cid_txs:
            if i < len(cid_txs[cid]):
                order.append(cid_txs[cid][i]); added = True
                if len(order) >= RECEIPT_CAP:
                    break
        if not added:
            break
        i += 1
    print(f"txs:{len(tx_taker)} | known takers:{len(known_takers)} | decoding {len(order)} receipts")

    # 3) decode OrderFilled incl. data fields; learn operator; keep maker-fills only
    raw = []   # (maker, taker, price, shares, side, token, cid, ts)
    n_done = 0
    for h in order:
        rc = rpc("eth_getTransactionReceipt", [h])
        if not rc:
            continue
        n_done += 1
        cid, ts = tx_cid.get(h), tx_ts.get(h)
        for lg in rc.get("logs", []):
            tp = lg.get("topics", [])
            if len(tp) < 4 or tp[0].lower() != ORDERFILLED_TOPIC:
                continue
            d = lg["data"][2:]
            mAsset = int(d[0:64], 16); tAsset = int(d[64:128], 16)
            mAmt = int(d[128:192], 16); tAmt = int(d[192:256], 16)
            maker = ("0x" + tp[2][-40:]).lower(); taker = ("0x" + tp[3][-40:]).lower()
            if mAsset == 0:
                side, token, shares, usd = "BUY", tAsset, tAmt / 1e6, mAmt / 1e6
            else:
                side, token, shares, usd = "SELL", mAsset, mAmt / 1e6, tAmt / 1e6
            price = usd / shares if shares else 0.0
            raw.append((maker, taker, price, shares, side, str(token), cid, ts))
        time.sleep(0.01)

    # operator = the address most seen as taker(t3) when maker(t2) is a known taker:
    op = Counter(taker for (maker, taker, *_r) in raw if maker in known_takers)
    operator = op.most_common(1)[0][0] if op else None
    print(f"OrderFilled events:{len(raw)} | operator(exchange):{operator}")

    # 4) keep MAKER-FILLS (t3=taker is a real trader, not the operator) for target makers
    fp = defaultdict(lambda: {"prices": [], "shares": [], "side": Counter(),
                               "tokens": set(), "cities": Counter(), "yn": Counter(),
                               "ts": []})
    kept = 0
    for maker, taker, price, shares, side, token, cid, ts in raw:
        is_maker_fill = (taker in known_takers) or (operator and taker != operator and maker != operator and taker not in known_takers and maker not in known_takers)
        if not is_maker_fill:
            continue
        if maker not in targets:
            continue
        kept += 1
        f = fp[maker]
        f["prices"].append(round(price, 4)); f["shares"].append(round(shares, 2))
        f["side"][side] += 1; f["tokens"].add(token)
        if ts:
            f["ts"].append(int(ts))
        meta = tmap.get(token)
        if meta:
            f["cities"][meta[0]] += 1; f["yn"][meta[1]] += 1
    print(f"maker-fills attributed to targets: {kept}\n")

    def whole_cent(p):  # posted at a round 1-cent price point?
        return abs(round(p * 100) - p * 100) < 1e-6

    rows = []
    for mk, f in fp.items():
        pr = f["prices"]
        if not pr:
            continue
        n = len(pr)
        topp = Counter(pr).most_common(3)
        gaps = []
        ts = sorted(f["ts"])
        for a, b in zip(ts, ts[1:]):
            gaps.append(b - a)
        rows.append({
            "maker": mk, "fills": n, "n_tokens": len(f["tokens"]), "n_cities": len(f["cities"]),
            "side": dict(f["side"]), "yes_no": dict(f["yn"]),
            "price_mean": round(sum(pr) / n, 3), "price_std": round(pstdev(pr), 3) if n > 1 else 0.0,
            "tail_share": round(sum(1 for p in pr if p < 0.10 or p > 0.90) / n, 2),
            "whole_cent_share": round(sum(1 for p in pr if whole_cent(p)) / n, 2),
            "top_prices": [{"p": p, "n": c} for p, c in topp],
            "top_price_concentration": round(sum(c for _, c in topp) / n, 2),
            "median_gap_s": int(median(gaps)) if gaps else None,
            "active_span_h": round((ts[-1] - ts[0]) / 3600, 1) if len(ts) > 1 else 0.0,
            "cities": dict(f["cities"].most_common(6)),
        })
    rows.sort(key=lambda r: -r["fills"])

    print(f"{'maker':<14}{'fl':>4}{'tok':>4}{'cty':>4}{'side(B/S)':>11}{'YES/NO':>9}"
          f"{'p_mean':>7}{'p_std':>7}{'tail':>6}{'cent%':>7}{'topPx%':>8}{'gap_s':>8}")
    for r in rows:
        s = f"{r['side'].get('BUY',0)}/{r['side'].get('SELL',0)}"
        yn = f"{r['yes_no'].get('YES',0)}/{r['yes_no'].get('NO',0)}"
        print(f"{r['maker'][:12]:<14}{r['fills']:>4}{r['n_tokens']:>4}{r['n_cities']:>4}{s:>11}{yn:>9}"
              f"{r['price_mean']:>7.3f}{r['price_std']:>7.3f}{r['tail_share']:>6.2f}"
              f"{r['whole_cent_share']:>7.2f}{r['top_price_concentration']:>8.2f}"
              f"{str(r['median_gap_s']):>8}")

    # aggregate determinism read
    if rows:
        big = [r for r in rows if r["fills"] >= 5]
        print(f"\n=== determinism summary (makers with >=5 fills, n={len(big)}) ===")
        print(f"  median whole-cent price share : {round(median([r['whole_cent_share'] for r in big]),2)}")
        print(f"  median top-3-price concentration: {round(median([r['top_price_concentration'] for r in big]),2)}")
        print(f"  median price std               : {round(median([r['price_std'] for r in big]),3)}")
        print(f"  pure one-sided makers (B or S=0): {sum(1 for r in big if 0 in (r['side'].get('BUY',0), r['side'].get('SELL',0)))}/{len(big)}")

    json.dump({"ts": time.time(), "operator": operator, "events": len(raw),
               "maker_fills_kept": kept, "makers": rows}, open(OUT_JSON, "w"), indent=2)
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
