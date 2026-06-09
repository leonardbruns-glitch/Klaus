"""
On-chain MM identifier for Polymarket weather markets (read-only, no capital).

Answers step-1 of the MM-fingerprinting hypothesis ([[project_mm_fingerprint_metagame]]):
HOW MANY distinct bots actually MAKE these markets, and how concentrated is flow?

Path: weather trades (data-api) -> transactionHash -> Polygon receipt ->
decode OrderFilled logs on the Polymarket CTF/NegRisk exchanges.

EMPIRICALLY VALIDATED event layout (2026-05-29, see state_log):
  OrderFilled topic0 = 0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee
  emitted by exchanges 0xe2222d27... (CTF) and 0xe1111800... (NegRisk).
  topics[1]=orderHash, topics[2]=maker, topics[3]=taker.
  Per matched tx the exchange emits:
    - N "maker-fills":  topics[3]=the crossing trader, topics[2]=the resting MAKER (the MM)
    - 1 "taker-fill" :  topics[2]=the crossing trader, topics[3]=the OPERATOR (constant addr)
  Ground-truth check used to derive this: data-api /trades.proxyWallet == TAKER only.
  In a 206-event sample, t2-or-t3 matched a known taker in 206/206 (clean partition).

The behavioral MM = the recurring address on the MAKER side of maker-fills. We count
maker-fill frequency + market breadth per address and report concentration. If 2-3
addresses dominate across many markets -> fingerprintable -> meta-game alive.

Run: python3 analysis/weather/mm_decode.py
Out: analysis/weather/mm_decode_out.json  (+ stdout report)
"""
from __future__ import annotations
import json, time, urllib.request
from collections import Counter, defaultdict

ORDERFILLED_TOPIC = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
MARKET_SCAN     = 120    # weather markets to pull trades from
RECEIPT_CAP     = 300    # cap RPC receipt calls
OUT_JSON        = "analysis/weather/mm_decode_out.json"


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


def addr(topic):  # last 20 bytes of a 32-byte topic
    return ("0x" + topic[-40:]).lower()


def main():
    # 1) collect city daily-max/min weather markets (active + recent)
    cids = []
    for closed in ("false", "true"):
        for ev in get(f"https://gamma-api.polymarket.com/events?tag_slug=weather&limit=200&closed={closed}&active=true"):
            for m in ev.get("markets", []):
                q = m.get("question", "").lower()
                if ("highest temperature in" in q or "lowest temperature in" in q) and m.get("conditionId"):
                    cids.append(m["conditionId"])
    cids = list(dict.fromkeys(cids))
    print(f"city weather markets found: {len(cids)}  (scanning first {MARKET_SCAN})")

    # 2) pull trades -> tx -> known takers (data-api proxyWallet = taker) + tx->cid
    tx_taker = defaultdict(set)   # txHash -> {taker proxyWallet}
    tx_cid   = {}                 # txHash -> first cid we saw it under
    cid_txs  = defaultdict(list)  # cid -> [txHash...] (for stratified sampling)
    taker_side = Counter()
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
            taker_side[t.get("side", "?")] += 1
        time.sleep(0.02)
    known_takers = set().union(*tx_taker.values()) if tx_taker else set()
    print(f"unique txs: {len(tx_taker)} | markets w/ txs: {len(cid_txs)} | known takers: {len(known_takers)} | data-api side: {dict(taker_side)}")

    # stratified receipt order: round-robin across markets so the RECEIPT_CAP budget
    # covers MANY markets (reveals cross-market maker recurrence) instead of front-loading
    # all receipts into the first few markets.
    order = []
    i = 0
    while len(order) < min(RECEIPT_CAP, len(tx_taker)):
        added = False
        for cid in cid_txs:
            if i < len(cid_txs[cid]):
                order.append(cid_txs[cid][i])
                added = True
                if len(order) >= RECEIPT_CAP:
                    break
        if not added:
            break
        i += 1

    # 3) decode OrderFilled from receipts; classify maker-fill vs taker-fill
    exchanges = Counter()
    # pass A: collect raw (maker_pos=t2, taker_pos=t3) pairs + learn operator
    raw = []   # (cid, t2, t3)
    n_done = 0
    n_of = 0
    for h in order:
        rc = rpc("eth_getTransactionReceipt", [h])
        if not rc:
            continue
        n_done += 1
        cid = tx_cid.get(h)
        for log in rc.get("logs", []):
            tp = log.get("topics", [])
            if len(tp) < 4 or tp[0].lower() != ORDERFILLED_TOPIC:
                continue
            n_of += 1
            exchanges[log.get("address", "").lower()] += 1
            raw.append((cid, addr(tp[2]), addr(tp[3])))
        time.sleep(0.01)
    print(f"receipts decoded: {n_done} | OrderFilled events: {n_of}")
    print(f"exchange contracts: {dict(exchanges)}")

    # learn operator = most common t3 among taker-fills (t2 is a known taker)
    op_votes = Counter(t3 for _, t2, t3 in raw if t2 in known_takers)
    operator = op_votes.most_common(1)[0][0] if op_votes else None
    print(f"inferred operator: {operator}  (votes={op_votes.most_common(3)})")

    # 4) classify each OrderFilled
    maker_fills = Counter()        # maker addr -> # maker-fills
    maker_markets = defaultdict(set)  # maker addr -> {cid}
    maker_as_taker = Counter()     # maker addr also seen crossing as taker
    cls = Counter()
    for cid, t2, t3 in raw:
        if t3 in known_takers:
            kind = "MAKER_FILL"           # t2 = MM maker
        elif t2 in known_takers:
            kind = "TAKER_FILL"           # t3 = operator
        elif operator is not None and t3 == operator:
            kind = "TAKER_FILL"           # taker we didn't query; t2 = that taker
        elif operator is not None and t2 == operator:
            kind = "OP_AS_MAKER"          # operator self-listed (rare)
        else:
            kind = "MAKER_FILL_INFERRED"  # neither known; t3 is an unqueried taker, t2 = maker
        cls[kind] += 1
        if kind in ("MAKER_FILL", "MAKER_FILL_INFERRED"):
            maker_fills[t2] += 1
            if cid:
                maker_markets[t2].add(cid)
        if t2 in known_takers:
            maker_as_taker[t2] += 1

    print(f"\nclassification: {dict(cls)}")
    tot = sum(maker_fills.values()) or 1
    print(f"\n=== DISTINCT MAKERS (the MMs): {len(maker_fills)} ===  total maker-fills: {tot}")
    print(f"{'maker address':<44}{'mk_fills':>9}{'%':>7}{'#mkts':>7}{'also_taker':>11}")
    for a, c in maker_fills.most_common(20):
        print(f"{a:<44}{c:>9}{100*c/tot:>6.1f}%{len(maker_markets[a]):>7}{maker_as_taker.get(a,0):>11}")

    mk_sorted = [c for _, c in maker_fills.most_common()]
    def share(n): return 100*sum(mk_sorted[:n])/tot

    print(f"\nMAKER-side concentration (= the liquidity providers):")
    for n in (1, 2, 3, 5, 10):
        if len(mk_sorted) >= n:
            print(f"  top-{n:<2} makers = {share(n):.1f}% of maker-fills")

    # cross-market recurrence = the fingerprintability signal: a systematic MM makes
    # MANY markets; a one-off maker is stuck to a single market.
    n_mkts_sampled = len({c for c, _, _ in raw if c})
    breadth = sorted(((len(maker_markets[a]), a, maker_fills[a]) for a in maker_fills), reverse=True)
    multi = [b for b in breadth if b[0] >= 3]
    print(f"\ncross-market recurrence (markets sampled here: {n_mkts_sampled}):")
    print(f"  makers in >=3 distinct markets: {len(multi)}  (these are the systematic MMs)")
    print(f"  makers in exactly 1 market    : {sum(1 for b in breadth if b[0]==1)}  (one-off / market-local)")
    for nm, a, fills in breadth[:8]:
        print(f"    {a}  {nm} markets, {fills} maker-fills")

    out = {
        "ts": time.time(),
        "weather_markets": len(cids),
        "markets_scanned": min(MARKET_SCAN, len(cids)),
        "txs": len(tx_taker),
        "receipts_decoded": n_done,
        "orderfilled_events": n_of,
        "exchanges": dict(exchanges),
        "operator": operator,
        "classification": dict(cls),
        "distinct_makers": len(maker_fills),
        "total_maker_fills": tot,
        "top_makers": [
            {"addr": a, "maker_fills": c, "pct": round(100*c/tot, 2),
             "n_markets": len(maker_markets[a]), "also_taker": maker_as_taker.get(a, 0)}
            for a, c in maker_fills.most_common(40)
        ],
        "concentration": {f"top{n}": round(share(n), 2) for n in (1, 2, 3, 5, 10) if len(mk_sorted) >= n},
        "markets_sampled_in_receipts": n_mkts_sampled,
        "makers_in_ge3_markets": len(multi),
        "makers_in_1_market": sum(1 for b in breadth if b[0] == 1),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
