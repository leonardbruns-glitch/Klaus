"""
Firm-clustering for the weather MMs found by mm_decode.py (read-only, no capital).

Question ([[project_mm_fingerprint_metagame]]): do the ~10 recurring cross-market
makers collapse into 2-3 operators (which would revive the 'dominant-bot' thesis),
or are they genuinely distinct controllers?

Method (what's feasible on the Alchemy FREE tier — getLogs is capped at a 10-block
range, so the gold-standard USDC funding-graph is NOT reachable here):
  classify each maker proxy by bytecode, then read its controller:
    - Polymarket Proxy Wallet (runtime 6080...): owner()  -> signing EOA
    - Gnosis Safe proxy:                          getOwners()
    - EIP-1167 minimal proxy (363d3d...5af43d...): embedded impl = wallet TEMPLATE
      (shared template != shared firm); owner is CREATE2-salt-derived, no on-chain getter.
  Cluster by owner EOA. Shared owner across makers => same firm.

VERDICT 2026-05-29: no collapse — resolvable makers map to all-distinct owners;
the unresolvable group shares only Polymarket's standard proxy template.
To go further (deployer/funder graph) needs a paid RPC or a free Polygonscan key.

Run: python3 analysis/weather/mm_cluster.py
"""
from __future__ import annotations
import json, urllib.request, time
from collections import Counter, defaultdict

DECODE_JSON = "analysis/weather/mm_decode_out.json"
OUT_JSON    = "analysis/weather/mm_cluster_out.json"
MIN_MARKETS = 3   # only cluster the systematic (cross-market) makers


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
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code}


def call(to, sel):
    return rpc("eth_call", [{"to": to, "data": sel}, "latest"]).get("result")


def classify(addr):
    """Return (kind, controller_or_impl)."""
    code = rpc("eth_getCode", [addr, "latest"]).get("result", "0x") or "0x"
    h = code[2:]
    # EIP-1167 minimal proxy: 363d3d373d3d3d363d73 <impl20> 5af43d82803e903d91602b57fd5bf3
    if h.startswith("363d3d373d3d3d363d73") and len(h) == 90:
        return "EIP1167", "0x" + h[20:60]
    # Polymarket proxy / Ownable owner() — try this FIRST (proxies answer it cleanly).
    o = call(addr, "0x8da5cb5b")
    if o and len(o) == 66 and int(o, 16) != 0:
        return "OWNABLE", "0x" + o[-40:]
    # Gnosis Safe getOwners() -> address[] (offset, length, then 32-byte words)
    go = call(addr, "0xa0e67e2b")
    if go and len(go) >= 194:
        body = go[2:]
        try:
            cnt = int(body[64:128], 16)
            ow = ["0x" + body[128 + i*64: 192 + i*64][-40:] for i in range(cnt)]
            ow = [w for w in ow if int(w, 16) != 0]
            if ow:
                return "SAFE", ",".join(ow)
        except Exception:
            pass
    return "UNRESOLVED", None


def main():
    d = json.load(open(DECODE_JSON))
    makers = [m["addr"] for m in d["top_makers"] if m["n_markets"] >= MIN_MARKETS]
    print(f"clustering {len(makers)} systematic makers (>= {MIN_MARKETS} markets)\n")

    rows = []
    owner_map = defaultdict(list)   # controller EOA -> [maker proxies]
    impl_map = Counter()
    kinds = Counter()
    for a in makers:
        kind, ctrl = classify(a)
        kinds[kind] += 1
        rows.append((a, kind, ctrl))
        if kind == "EIP1167":
            impl_map[ctrl] += 1
        elif kind in ("OWNABLE", "SAFE") and ctrl:
            for w in ctrl.split(","):
                owner_map[w.lower()].append(a)
        time.sleep(0.01)

    print(f"{'maker':<44}{'kind':<11}controller / impl")
    for a, kind, ctrl in rows:
        print(f"{a:<44}{kind:<11}{ctrl or '—'}")

    print(f"\nkinds: {dict(kinds)}")
    print(f"EIP-1167 shared templates (wallet TYPE, not firm): {dict(impl_map)}")

    shared = {w: ms for w, ms in owner_map.items() if len(ms) > 1}
    distinct_owners = len(owner_map)
    print(f"\ndistinct controller EOAs among resolvable makers: {distinct_owners}")
    if shared:
        print("SHARED owners (same firm):")
        for w, ms in sorted(shared.items(), key=lambda x: -len(x[1])):
            print(f"  {w} -> {len(ms)} makers: {ms}")
        verdict = "PARTIAL_COLLAPSE"
    else:
        print("SHARED owners: none -> NO firm-collapse among resolvable makers")
        verdict = "NO_COLLAPSE"

    unresolved = kinds.get("EIP1167", 0) + kinds.get("UNRESOLVED", 0)
    print(f"\nVERDICT: {verdict}  "
          f"({distinct_owners} distinct owners, 0 shared; "
          f"{unresolved} unresolvable Polymarket-template proxies — need paid RPC / "
          f"Polygonscan key for funder/deployer graph)")

    json.dump({
        "ts": time.time(), "n_makers": len(makers), "kinds": dict(kinds),
        "eip1167_shared_impls": dict(impl_map),
        "distinct_owner_eoas": distinct_owners,
        "shared_owners": {w: ms for w, ms in shared.items()},
        "verdict": verdict,
        "rows": [{"maker": a, "kind": k, "controller": c} for a, k, c in rows],
    }, open(OUT_JSON, "w"), indent=2)
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
