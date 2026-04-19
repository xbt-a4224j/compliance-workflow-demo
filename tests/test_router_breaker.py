from __future__ import annotations

import pytest

from compliance_workflow_demo.router import BreakerState, CircuitBreaker


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _breaker(clock: FakeClock, *, threshold: int = 3, cooldown: float = 10.0) -> CircuitBreaker:
    return CircuitBreaker(
        failure_threshold=threshold, cooldown_s=cooldown, time_fn=clock
    )


@pytest.mark.asyncio
async def test_starts_closed_and_admits_calls():
    breaker = _breaker(FakeClock())
    assert breaker.state is BreakerState.CLOSED
    assert await breaker.allow() is True


@pytest.mark.asyncio
async def test_opens_after_threshold_consecutive_failures():
    breaker = _breaker(FakeClock(), threshold=3)
    for _ in range(3):
        assert await breaker.allow() is True
        await breaker.record_failure()
    assert breaker.state is BreakerState.OPEN
    assert await breaker.allow() is False


@pytest.mark.asyncio
async def test_success_resets_failure_counter():
    breaker = _breaker(FakeClock(), threshold=3)
    await breaker.record_failure()
    await breaker.record_failure()
    await breaker.record_success()
    # Counter reset; needs full threshold of failures again to trip.
    for _ in range(2):
        assert await breaker.allow() is True
        await breaker.record_failure()
    assert breaker.state is BreakerState.CLOSED


@pytest.mark.asyncio
async def test_open_transitions_to_half_open_after_cooldown():
    clock = FakeClock()
    breaker = _breaker(clock, threshold=2, cooldown=10.0)

    # Trip it.
    await breaker.record_failure()
    await breaker.record_failure()
    assert breaker.state is BreakerState.OPEN
    assert await breaker.allow() is False

    # Not yet — cooldown not elapsed.
    clock.advance(9.9)
    assert await breaker.allow() is False
    assert breaker.state is BreakerState.OPEN

    # Cooldown elapsed: HALF_OPEN, admits one probe.
    clock.advance(0.2)
    assert await breaker.allow() is True
    assert breaker.state is BreakerState.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_admits_only_one_probe():
    clock = FakeClock()
    breaker = _breaker(clock, threshold=1, cooldown=1.0)
    await breaker.record_failure()
    clock.advance(2.0)

    assert await breaker.allow() is True   # probe admitted
    assert await breaker.allow() is False  # second concurrent caller blocked
    assert await breaker.allow() is False


@pytest.mark.asyncio
async def test_half_open_probe_success_closes_breaker():
    clock = FakeClock()
    breaker = _breaker(clock, threshold=1, cooldown=1.0)
    await breaker.record_failure()
    clock.advance(2.0)

    await breaker.allow()
    await breaker.record_success()
    assert breaker.state is BreakerState.CLOSED
    assert await breaker.allow() is True


@pytest.mark.asyncio
async def test_half_open_probe_failure_reopens_and_resets_cooldown():
    clock = FakeClock()
    breaker = _breaker(clock, threshold=1, cooldown=10.0)
    await breaker.record_failure()
    clock.advance(11.0)

    await breaker.allow()           # enter HALF_OPEN
    await breaker.record_failure()  # probe failed → OPEN, cooldown reset

    assert breaker.state is BreakerState.OPEN
    assert await breaker.allow() is False
    clock.advance(9.9)
    assert await breaker.allow() is False  # still in fresh cooldown
    clock.advance(0.2)
    assert await breaker.allow() is True   # fresh cooldown elapsed
