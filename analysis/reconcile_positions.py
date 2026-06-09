"""Read-only: reconcile positions.json against REAL Polymarket proxy balances.

Uses the bot's own CLOB client (queries the proxy/funder, not the EOA). For each
tracked WEATHER position, query CONDITIONAL balance to see whether the proxy still
holds the tokens (i.e. NOT manually sold). Also fetch live USDC cash. NO changes.
"""
import json
from pathlib import Path
from execution.order_manager import _build_clob_client
from config import CONFIG
from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType

client = _build_clob_client()
assert client is not None, "CLOB client unavailable"


def bal(asset_type, token_id=None):
    p = BalanceAllowanceParams(asset_type=asset_type,
                               signature_type=CONFIG.signature_type,
                               token_id=token_id)
    ba = client.get_balance_allowance(p)
    return float(ba.get("balance", 0)) / 1_000_000


cash = bal(AssetType.COLLATERAL)
print(f"USDC cash (proxy, fresh): ${cash:.4f}\n")

positions = json.loads((Path(__file__).parent.parent / "logs" / "positions.json").read_text())
print(f"{'token':<14} {'tag':<20} {'dir':<7} {'cost':>7} {'onchain_sh':>11} {'status'}")
held_cost = sold_cost = 0.0
keep, drop = [], []
for tid, p in positions.items():
    sh = bal(AssetType.CONDITIONAL, token_id=tid)
    cost = float(p.get("remaining_shares", 0)) * float(p.get("entry_price", 0))
    if sh > 0.5:
        held_cost += cost; keep.append(tid); status = "HELD"
    else:
        sold_cost += cost; drop.append(tid); status = "SOLD/GONE"
    print(f"{tid[:12]:<14} {p.get('bond_entry_class',''):<20} {p.get('direction',''):<7} "
          f"{cost:>7.2f} {sh:>11.2f} {status}")

print(f"\nHELD cost basis: ${held_cost:.2f} ({len(keep)})   SOLD: ${sold_cost:.2f} ({len(drop)})")
print(f"USDC cash now: ${cash:.2f}  => after cleanup, 5%/city budget = ${0.05*cash:.2f}")
print(f"true capital (cash+held) = ${cash + held_cost:.2f}")
print("\nDROP:\n" + json.dumps(drop))
