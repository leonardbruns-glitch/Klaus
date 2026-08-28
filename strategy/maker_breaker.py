"""MakerCircuitBreaker — code-failure protection for the locked-region maker
(2026-06-01).

This is NOT a strategy-drawdown halt (the user explicitly declined that). It trips
ONLY on BUG signatures of untested order-placement code — the dominant risk when
running the never-before-exercised maker_buy/cancel path against real capital:
  • runaway resting exposure (Σ stake of live resting orders exceeds a hard cap),
  • a failed / hung cancel (an order may be stuck on the book),
  • bankroll cratering below a hard floor.

Once tripped it latches (blocks all new maker orders) until a human re-arms via a
process restart. Self-contained and unit-testable — no engine imports.
"""
import time


class MakerCircuitBreaker:
    def __init__(self, max_exposure_usd: float = 15.0, min_bankroll_usd: float = 30.0):
        self.max_exposure_usd = float(max_exposure_usd)
        self.min_bankroll_usd = float(min_bankroll_usd)
        self._resting: dict[str, float] = {}   # order_id -> stake_usd live on book
        self.tripped: bool = False
        self.trip_reason: str = ""
        self.tripped_ts: float = 0.0

    def _trip(self, reason: str) -> None:
        if not self.tripped:
            self.tripped = True
            self.trip_reason = reason
            self.tripped_ts = time.time()

    def exposure_usd(self) -> float:
        return sum(self._resting.values())

    def register_resting(self, order_id: str, stake_usd: float) -> None:
        if order_id:
            self._resting[order_id] = float(stake_usd)

    def release(self, order_id: str) -> None:
        """Order filled or successfully cancelled — no longer at risk on the book."""
        self._resting.pop(order_id, None)

    def note_cancel_failure(self, order_id: str = "") -> None:
        """A cancel call failed → an order may be hung on the book. Trip immediately:
        a stuck order is the catastrophic failure mode of untested order code."""
        self._trip(f"cancel-failed:{str(order_id)[:12]}")

    def precheck(self, bankroll_usd: float, new_stake_usd: float) -> tuple[bool, str]:
        """Call BEFORE posting a new maker order. Returns (ok, reason). Any breach
        latches the trip for the session so no further maker orders are placed."""
        if self.tripped:
            return False, f"tripped:{self.trip_reason}"
        if bankroll_usd < self.min_bankroll_usd:
            self._trip(f"bankroll<{self.min_bankroll_usd:.0f}={bankroll_usd:.2f}")
            return False, self.trip_reason
        if self.exposure_usd() + float(new_stake_usd) > self.max_exposure_usd:
            self._trip(f"exposure>{self.max_exposure_usd:.0f}")
            return False, self.trip_reason
        return True, ""
