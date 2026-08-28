"""Smoke test for Tier 1 shadow recorders.

Pure unit-style verification: exercises emit_token_trade (v2 with tx_hash) and
emit_ob_delta with synthetic WS event payloads, captures emitted rows via a
fake pipeline, and asserts schema correctness.

No live bot, no network, no real WS. Run with: python3 tests/smoke_tier1.py
"""
import sys
sys.path.insert(0, "/root/Klaus")

from collections import namedtuple
from data.shadow.trade import emit_token_trade, SCHEMA_VERSION as TRADE_SV
from data.shadow.ob_delta import emit_ob_delta, SCHEMA_VERSION as OBD_SV


# --- Fake pipeline that captures emitted records
class FakePipeline:
    def __init__(self):
        self.records = []
    def emit(self, rec):
        self.records.append(rec)


# --- Minimal fake token + feed + bot
FakeToken = namedtuple("FakeToken", "asset condition_id outcome_direction side market_type window_end_ts")
FakeOB = namedtuple("FakeOB", "bids asks")

class FakeFeed:
    def __init__(self, token, ob=None):
        self.tokens = {"tok_1": token}
        self.order_books = {"tok_1": ob} if ob else {}

class FakeBot:
    def __init__(self, feed):
        self.feed = feed


def assert_eq(a, b, label):
    assert a == b, f"FAIL {label}: expected {b!r}, got {a!r}"
    print(f"  PASS {label}")


def assert_in(needle, haystack, label):
    assert needle in haystack, f"FAIL {label}: {needle!r} not in {haystack!r}"
    print(f"  PASS {label}")


def assert_close(a, b, label, eps=1e-9):
    assert abs(a - b) < eps, f"FAIL {label}: {a} vs {b}"
    print(f"  PASS {label}")


# =================================================================
print("=== Phase A: token_trade schema v2 ===")
print(f"  SCHEMA_VERSION = {TRADE_SV}")
assert_eq(TRADE_SV, 2, "schema bumped to 2")

pipe = FakePipeline()
token = FakeToken(
    asset="BTC", condition_id="0xcond1", outcome_direction="up",
    side="YES", market_type="updown", window_end_ts=2_000_000_900,
)
bot = FakeBot(FakeFeed(token))

# Synthetic last_trade_price WS event with transaction_hash + fee_rate_bps
ev_trade = {
    "asset_id": "tok_1",
    "market": "0xcond1",
    "price": "0.83",
    "size": "12",
    "side": "BUY",
    "fee_rate_bps": "25",
    "transaction_hash": "0xdeadbeef" + "0" * 56,
    "timestamp": "1716000000000",
}
emit_token_trade(pipe, bot, "tok_1", ev_trade)
assert_eq(len(pipe.records), 1, "one record emitted")
rec = pipe.records[0]
assert_eq(rec["record_type"], "token_trade", "record_type")
assert_eq(rec["schema_version"], 2, "schema_version in record")
assert_eq(rec["transaction_hash"], "0xdeadbeef" + "0" * 56, "transaction_hash captured")
assert_eq(rec["fee_rate_bps"], 25.0, "fee_rate_bps captured as float")
assert_eq(rec["side"], "BUY", "side preserved")
assert_close(rec["price"], 0.83, "price preserved")

# Missing tx_hash + fee_rate_bps (must not crash; empty/None)
pipe.records.clear()
ev_no_hash = {"price": "0.5", "size": "10", "side": "SELL"}
emit_token_trade(pipe, bot, "tok_1", ev_no_hash)
assert_eq(len(pipe.records), 1, "no-hash event still emits")
rec = pipe.records[0]
assert_eq(rec["transaction_hash"], "", "empty tx_hash when absent")
assert_eq(rec["fee_rate_bps"], None, "None fee_rate when absent")

# =================================================================
print("\n=== Phase B1: ob_delta recorder ===")
print(f"  SCHEMA_VERSION = {OBD_SV}")
assert_eq(OBD_SV, 1, "ob_delta schema v1")

# Build OB snapshot (top 5 bids + 5 asks); price_change with one BUY at L1, one SELL at L3
fake_ob = FakeOB(
    bids=[(0.82, 100.0), (0.81, 50.0), (0.80, 30.0), (0.79, 20.0), (0.78, 10.0), (0.70, 99.0)],
    asks=[(0.83, 50.0), (0.84, 30.0), (0.85, 25.0), (0.86, 20.0), (0.87, 15.0), (0.95, 200.0)],
)
bot.feed.order_books["tok_1"] = fake_ob

pipe.records.clear()
ev_pc = {
    "event_type": "price_change",
    "market": "0xcond1",
    "asset_id": "tok_1",
    "timestamp": "1716000001000",
    "price_changes": [
        # BUY side L1: existing level at 0.82 with new size (a refill or partial cancel)
        {"asset_id": "tok_1", "price": "0.82", "size": "75", "side": "BUY", "hash": "0xa1"},
        # SELL side L3: 0.85 fully removed (size=0)
        {"asset_id": "tok_1", "price": "0.85", "size": "0", "side": "SELL", "hash": "0xa2"},
        # Deep level (rank 6+): 0.70 BUY — MUST be dropped by top-5 filter
        {"asset_id": "tok_1", "price": "0.70", "size": "50", "side": "BUY", "hash": "0xa3"},
        # Deep level: 0.95 SELL — MUST be dropped
        {"asset_id": "tok_1", "price": "0.95", "size": "150", "side": "SELL", "hash": "0xa4"},
    ],
}
emit_ob_delta(pipe, bot, "tok_1", ev_pc)
assert_eq(len(pipe.records), 2, "exactly 2 top-5 rows emitted; deep levels filtered")
r0 = pipe.records[0]
r1 = pipe.records[1]
assert_eq(r0["record_type"], "ob_delta", "ob_delta record_type")
assert_eq(r0["event_type"], "price_change", "event_type field")
assert_eq(r0["level_side"], "BUY", "first row BUY")
assert_close(r0["level_price"], 0.82, "first row price")
assert_eq(r0["level_rank"], 0, "first row rank 0 (L1)")
assert_eq(r0["asset"], "BTC", "asset tagged")
assert_close(r0["best_bid_at_event"], 0.82, "pre-event best_bid captured")
assert_close(r0["best_ask_at_event"], 0.83, "pre-event best_ask captured")
assert_eq(r1["level_side"], "SELL", "second row SELL")
assert_eq(r1["level_rank"], 2, "second row rank 2 (L3)")
assert_eq(r1["level_size"], 0.0, "size=0 (cancel) preserved")
assert_in("exchange_ts_ms", r0, "timing provenance present")
assert_in("ts_ms_local", r0, "local ts present")
assert_eq(r0["exchange_ts_ms"], 1716000001000, "exchange_ts_ms parsed from event")

# best_bid_ask event — single row, side=BBO
pipe.records.clear()
ev_bbo = {
    "event_type": "best_bid_ask",
    "market": "0xcond1",
    "asset_id": "tok_1",
    "timestamp": "1716000002000",
    "best_bid": "0.825",
    "best_ask": "0.832",
}
emit_ob_delta(pipe, bot, "tok_1", ev_bbo)
assert_eq(len(pipe.records), 1, "BBO event emits one row")
r = pipe.records[0]
assert_eq(r["level_side"], "BBO", "BBO side tag")
assert_close(r["best_bid_at_event"], 0.825, "bbo best_bid")
assert_close(r["best_ask_at_event"], 0.832, "bbo best_ask")
assert_eq(r["level_price"], None, "level_price None for BBO")

# Non-tracked event type (e.g. tick_size_change) — must emit nothing
pipe.records.clear()
emit_ob_delta(pipe, bot, "tok_1", {"event_type": "tick_size_change"})
assert_eq(len(pipe.records), 0, "tick_size_change ignored")

# Pathological price_changes (e.g. 30 items at top-5) — capped at 2*TOP_N
pipe.records.clear()
many = []
for i in range(30):
    # All within top-5 ranks somehow — but our level_rank check will drop most
    # Use the existing top-5 prices to ensure rank match
    many.append({"asset_id": "tok_1", "price": "0.82", "size": str(10 + i), "side": "BUY", "hash": f"0x{i:x}"})
ev_pc_many = {
    "event_type": "price_change",
    "market": "0xcond1",
    "asset_id": "tok_1",
    "timestamp": "1716000003000",
    "price_changes": many,
}
emit_ob_delta(pipe, bot, "tok_1", ev_pc_many)
assert len(pipe.records) <= 10, f"emitted {len(pipe.records)}, expected <= 10 (cap)"
print(f"  PASS pathological-event cap: {len(pipe.records)} <= 10")

# Token missing from feed — must not crash, must not emit
pipe.records.clear()
emit_ob_delta(pipe, bot, "unknown_tok", ev_pc)
assert_eq(len(pipe.records), 0, "unknown token ignored")

# pipeline None — must be safe
emit_ob_delta(None, bot, "tok_1", ev_pc)
print("  PASS pipeline=None tolerated")

# =================================================================
print("\n=== Combined verification ===")
# Send a token_trade then an ob_delta, verify both reach the same pipeline
pipe.records.clear()
emit_token_trade(pipe, bot, "tok_1", ev_trade)
emit_ob_delta(pipe, bot, "tok_1", ev_pc)
types = set(r["record_type"] for r in pipe.records)
assert_eq(types, {"token_trade", "ob_delta"}, "both record_types observed")
print(f"  PASS total rows captured: {len(pipe.records)}")

print("\n=== ALL TESTS PASSED ===")
