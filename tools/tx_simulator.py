"""
Defensive transaction simulator for Web3 middleware.
Intercepts calldata before submission and returns Success or a decoded revert reason.
"""

import asyncio
import os
from dataclasses import dataclass
from typing import Optional

from eth_abi import decode as abi_decode
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

# Signature hashes for standard revert/panic ABI encoding
_ERROR_SIG = bytes.fromhex("08c379a0")  # Error(string)
_PANIC_SIG  = bytes.fromhex("4e487b71")  # Panic(uint256)

_PANIC_CODES = {
    0x00: "generic compiler assert",
    0x01: "assert() false",
    0x11: "arithmetic overflow/underflow",
    0x12: "division or modulo by zero",
    0x21: "invalid enum conversion",
    0x22: "corrupted storage byte array",
    0x31: "pop() on empty array",
    0x32: "array index out of bounds",
    0x41: "out of memory",
    0x51: "uninitialised function pointer",
}

SIMULATE_TIMEOUT_S = 0.10  # 100 ms hard cap


@dataclass(frozen=True)
class SimResult:
    success: bool
    gas_estimate: Optional[int]   # set on success
    revert_reason: Optional[str]  # set on failure


def _decode_revert_bytes(data: bytes) -> str:
    """Decode a revert payload returned by eth_call into a human-readable string."""
    if not data:
        return "execution reverted (no reason)"

    if data[:4] == _ERROR_SIG:
        try:
            (reason,) = abi_decode(["string"], data[4:])
            return f"Error: {reason}"
        except Exception:
            pass

    if data[:4] == _PANIC_SIG:
        try:
            (code,) = abi_decode(["uint256"], data[4:])
            label = _PANIC_CODES.get(int(code), "unknown panic")
            return f"Panic(0x{int(code):02x}): {label}"
        except Exception:
            pass

    # Custom error — return selector + raw hex for the caller to decode
    selector = data[:4].hex()
    return f"CustomError(0x{selector}) payload=0x{data[4:].hex() or '<empty>'}"


async def simulate_transaction(
    *,
    rpc_url: str,
    to: str,
    data: str,
    sender: str = "0x0000000000000000000000000000000000000000",
    value: int = 0,
    block: str = "latest",
) -> SimResult:
    """
    Simulate a transaction via eth_estimateGas → eth_call fallback.

    Args:
        rpc_url: HTTP(S) or WS RPC endpoint.
        to:      Contract address (checksummed or not).
        data:    Calldata hex string (with or without 0x prefix).
        sender:  msg.sender for the simulation (default: zero address).
        value:   msg.value in wei (default: 0).
        block:   Block tag — "latest", "pending", or hex block number.

    Returns:
        SimResult(success=True, gas_estimate=N, revert_reason=None)
        SimResult(success=False, gas_estimate=None, revert_reason="<reason>")

    Raises:
        asyncio.TimeoutError if the RPC round-trip exceeds SIMULATE_TIMEOUT_S.
    """
    w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))

    to_addr   = AsyncWeb3.to_checksum_address(to)
    from_addr = AsyncWeb3.to_checksum_address(sender)
    calldata  = data if data.startswith("0x") else f"0x{data}"

    tx_params = {
        "to":    to_addr,
        "from":  from_addr,
        "data":  calldata,
        "value": value,
    }

    async def _run() -> SimResult:
        # --- Phase 1: eth_estimateGas (fast path, fails on revert) ---
        try:
            gas = await w3.eth.estimate_gas(tx_params, block)
            return SimResult(success=True, gas_estimate=gas, revert_reason=None)
        except Exception as est_err:
            # eth_estimateGas throws on revert; fall through to eth_call for the reason
            est_msg = str(est_err)

        # --- Phase 2: eth_call to extract the revert payload ---
        try:
            await w3.eth.call(tx_params, block)
            # eth_call succeeded → the estimate_gas failure was non-revert (gas limit, etc.)
            return SimResult(
                success=False,
                gas_estimate=None,
                revert_reason=f"gas estimation failed (call succeeded): {est_msg}",
            )
        except Exception as call_err:
            raw = getattr(call_err, "data", None)

            if isinstance(raw, str):
                raw_bytes = bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)
            elif isinstance(raw, (bytes, bytearray)):
                raw_bytes = bytes(raw)
            else:
                # Some providers embed the reason in the message directly
                return SimResult(
                    success=False,
                    gas_estimate=None,
                    revert_reason=str(call_err),
                )

            return SimResult(
                success=False,
                gas_estimate=None,
                revert_reason=_decode_revert_bytes(raw_bytes),
            )

    return await asyncio.wait_for(_run(), timeout=SIMULATE_TIMEOUT_S)


# ---------------------------------------------------------------------------
# CLI entry point for quick testing
# ---------------------------------------------------------------------------
async def _main() -> None:
    import argparse, json

    parser = argparse.ArgumentParser(description="Simulate a transaction before submission.")
    parser.add_argument("--rpc",    required=True, help="RPC endpoint URL")
    parser.add_argument("--to",     required=True, help="Contract address")
    parser.add_argument("--data",   required=True, help="Calldata hex")
    parser.add_argument("--sender", default="0x0000000000000000000000000000000000000000")
    parser.add_argument("--value",  type=int, default=0, help="msg.value in wei")
    parser.add_argument("--block",  default="latest")
    args = parser.parse_args()

    import time
    t0 = time.perf_counter()
    try:
        result = await simulate_transaction(
            rpc_url=args.rpc,
            to=args.to,
            data=args.data,
            sender=args.sender,
            value=args.value,
            block=args.block,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(json.dumps({
            "success":       result.success,
            "gas_estimate":  result.gas_estimate,
            "revert_reason": result.revert_reason,
            "elapsed_ms":    round(elapsed_ms, 2),
        }, indent=2))
    except asyncio.TimeoutError:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(json.dumps({"error": "timeout", "elapsed_ms": round(elapsed_ms, 2)}, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
