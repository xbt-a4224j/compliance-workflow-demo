from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Per-provider failure short-circuit.

    State machine:
      CLOSED    : calls flow normally; transient failures increment a counter
      OPEN      : calls short-circuit; entered after `failure_threshold` consecutive
                  transients; transitions to HALF_OPEN once `cooldown_s` has elapsed
      HALF_OPEN : exactly one in-flight probe is admitted; success → CLOSED, failure
                  → OPEN (and the cooldown clock resets)

    Only TransientError counts toward failures (record_failure is the caller's
    contract). PermanentError is bad config / bad request — the breaker has no
    business reacting to it.
    """

    failure_threshold: int = 3
    cooldown_s: float = 10.0
    name: str = ""
    time_fn: Callable[[], float] = time.monotonic

    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _probe_in_flight: bool = field(default=False, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> BreakerState:
        return self._state

    async def allow(self) -> bool:
        """Decide whether to admit the next call. Mutates state on transition."""
        async with self._lock:
            if self._state is BreakerState.CLOSED:
                return True

            if self._state is BreakerState.OPEN:
                assert self._opened_at is not None
                if self.time_fn() - self._opened_at < self.cooldown_s:
                    return False
                # cooldown elapsed: enter HALF_OPEN, admit one probe
                self._state = BreakerState.HALF_OPEN
                self._probe_in_flight = True
                return True

            # HALF_OPEN: only one concurrent probe at a time
            if self._probe_in_flight:
                return False
            self._probe_in_flight = True
            return True

    async def record_success(self) -> None:
        async with self._lock:
            self._state = BreakerState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._probe_in_flight = False

    async def record_failure(self) -> None:
        async with self._lock:
            self._probe_in_flight = False
            if self._state is BreakerState.HALF_OPEN:
                # The probe failed: snap back to OPEN, reset cooldown clock.
                self._state = BreakerState.OPEN
                self._opened_at = self.time_fn()
                return

            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._state = BreakerState.OPEN
                self._opened_at = self.time_fn()
